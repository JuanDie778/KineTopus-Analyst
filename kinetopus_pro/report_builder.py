"""
Motor de Presentación Dual en Dos Etapas (`report.html` + `analysis.md`) — v0.3.1.

Implementa el enfoque geométrico puro multi-lente en dos etapas:
  - Etapa 1 (Cuantitativa pura, sin IA): guarda `report_bundle.npz` con el 100% del historial
    descargado y las 3 lentes (`2000v` Cian, `1000v` Ámbar, `500v` Violeta) proyectadas a `t+150`,
    junto con `narrative_template.json`, y genera un `report.html` interactivo autocontenido
    con selector de ventana `[120v | 500v | 1000v | 2000v | Todo el historial]`, selector de cono
    `[1000v | 2000v | 500v | Sin cono]` y selector de los 3 dashboards técnicos.
  - Etapa 2 (`--render-report <DIR>`): lee `narrative.json` (solo texto cualitativo escrito por el
    agente: titular, catalizadores, 3 insights, consenso web citado, paridad visual, traducción EDO,
    catalizadores CUSUM históricos y límites) y re-ensambla `report.html` y `analysis.md` inyectando
    el 100% de precios, porcentajes, probabilidades de toque, rangos y métricas desde el JSON.
"""

from __future__ import annotations

import base64
import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import jinja2
import numpy as np
import plotly.offline

from kinetopus_pro.headless_pipeline import KinetopusHeadlessPipeline


class KinetopusReportBuilder:
    """Constructor determinista de `report.html` y `analysis.md` con cifras blindadas."""

    _CACHED_PLOTLY_JS: Optional[str] = None
    TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

    @classmethod
    def _get_plotly_js(cls) -> str:
        if cls._CACHED_PLOTLY_JS is None:
            cls._CACHED_PLOTLY_JS = plotly.offline.get_plotlyjs()
        return cls._CACHED_PLOTLY_JS

    @staticmethod
    def _fmt_num(val: Optional[float]) -> str:
        if val is None or not np.isfinite(float(val)):
            return "N/D"
        v = float(val)
        av = abs(v)
        if av >= 1000.0:
            return f"{v:,.0f}"
        if av >= 10.0:
            return f"{v:,.2f}"
        return f"{v:,.4f}"

    @classmethod
    def _fmt_html_price(cls, val: Optional[float], currency: str = "$") -> str:
        if val is None or not np.isfinite(float(val)):
            return "N/D"
        return f"{currency}{cls._fmt_num(val)}"

    @classmethod
    def _fmt_md_price(cls, val: Optional[float], currency: str = "\\$") -> str:
        if val is None or not np.isfinite(float(val)):
            return "N/D"
        return f"{currency}{cls._fmt_num(val)}"

    @staticmethod
    def escape_md_dollars(text: str) -> str:
        """Escapa signos `$` literales fuera de backticks para evitar roturas KaTeX en Markdown."""
        if not text:
            return ""
        parts = re.split(r"(`[^`]*`)", str(text))
        out: List[str] = []
        for idx, chunk in enumerate(parts):
            if idx % 2 == 1:
                out.append(chunk)
            else:
                out.append(re.sub(r"(?<!\\)\$", r"\\$", chunk))
        return "".join(out)

    # ──────────────────────────────────────────────────────────────────────────
    # 1. Persistencia ligera de series (`report_bundle.npz`) y plantilla guía
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def save_report_bundle(
        cls, multi_result: Any, report_dir: Path, max_hist: Optional[int] = None
    ) -> Path:
        """
        Guarda las series numéricas completas necesarias para re-renderizar `report.html` en <0.5 s.
        Por defecto en v0.3.1 (`max_hist=None`) almacena el 100% del historial descargado y las
        3 lentes completas (`2000v`, `1000v`, `500v`) con su trayectoria y cono `t+150`.
        """
        report_dir.mkdir(parents=True, exist_ok=True)
        n_full = len(multi_result.raw_price_full)
        if max_hist is None or int(max_hist) <= 0:
            h0 = 0
        else:
            keep = min(int(max_hist), n_full)
            h0 = n_full - keep

        payload: Dict[str, Any] = {
            "n_full": np.array([n_full], dtype=np.int64),
            "h_start": np.array([h0], dtype=np.int64),
            "dates_hist": np.asarray(multi_result.dates_full[h0:], dtype="U20"),
            "close_hist": np.ascontiguousarray(multi_result.raw_price_full[h0:], dtype=np.float64),
        }

        ohlc = getattr(multi_result, "ohlc_full", None)
        if ohlc is not None and len(ohlc.get("close", [])) == n_full:
            payload["has_ohlc"] = np.array([1], dtype=np.int32)
            payload["open_hist"] = np.ascontiguousarray(ohlc["open"][h0:], dtype=np.float64)
            payload["high_hist"] = np.ascontiguousarray(ohlc["high"][h0:], dtype=np.float64)
            payload["low_hist"] = np.ascontiguousarray(ohlc["low"][h0:], dtype=np.float64)
        else:
            payload["has_ohlc"] = np.array([0], dtype=np.int32)

        for prefix, s_idx in (("ctx", 0), ("pri", 1), ("sen", 2)):
            slot = multi_result.lens_slots[s_idx] if len(multi_result.lens_slots) > s_idx else None
            if slot is not None and slot.available and slot.run_result is not None:
                res = slot.run_result
                arr = res.arrays
                seal_ok = bool(res.telemetry["reliability_seal"]["double_seal_summary"]["seal_passed"])
                payload[f"{prefix}_avail"] = np.array([1], dtype=np.int32)
                payload[f"{prefix}_win"] = np.array([int(slot.window_candles)], dtype=np.int32)
                payload[f"{prefix}_sealed"] = np.array([1 if seal_ok else 0], dtype=np.int32)
                payload[f"{prefix}_nom"] = np.ascontiguousarray(arr["nominal_smooth"], dtype=np.float64)
                payload[f"{prefix}_trigs"] = np.asarray(arr["cusum_triggers"], dtype=np.int64)
                payload[f"{prefix}_dates"] = np.asarray(arr["dates_active"], dtype="U20")
                payload[f"{prefix}_det"] = np.ascontiguousarray(arr["det_price_path"], dtype=np.float64)
                mc_p = arr["mc_price_percentiles"]
                if len(mc_p) == 5 and len(mc_p[0]) > 0:
                    payload[f"{prefix}_mc"] = np.ascontiguousarray(np.asarray(mc_p, dtype=np.float64))
                else:
                    payload[f"{prefix}_mc"] = np.empty((0, 0), dtype=np.float64)
            else:
                payload[f"{prefix}_avail"] = np.array([0], dtype=np.int32)

        bundle_path = report_dir / "report_bundle.npz"
        np.savez_compressed(bundle_path, **payload)
        return bundle_path

    @staticmethod
    def write_narrative_template(report_dir: Path, confluence: Dict[str, Any]) -> Path:
        """Escribe `narrative_template.json` con la estructura cualitativa geométrica esperada en Etapa 2."""
        ticker = confluence["metadata"]["dataset"]["ticker"]
        banner = confluence["hierarchy_verdict"].get("executive_banner", "Régimen vigente")
        template_obj = {
            "_instructions": (
                "Rellena únicamente texto cualitativo en español centrado en la geometría de las 3 curvas "
                "(2000v Cian, 1000v Ámbar, 500v Violeta), su distancia al precio y los cuartiles P25/P75, "
                "y guárdalo como `narrative.json`. NO incluyas tablas numéricas manuales ni menciones de "
                "barreras CUSUM de 1 vela: `kinetopus-analyze --render-report` inyecta todas las cifras."
            ),
            "headline": (
                f"Titular ejecutivo geométrico de 1 frase para {ticker} "
                f"(lectura '{banner}' frente a las 3 curvas y proyección t+150)."
            ),
            "scenarios_catalysts": {
                "base": "Qué condición de flujo o volumen mantiene al precio gravitando dentro del canal central P25–P75 hacia t+150.",
                "bullish": "Qué catalizador fundamental o empuje de flujo llevaría al precio sobre el cuartil P75 hacia P90–P95.",
                "bearish": "Qué evento adverso o deterioro de liquidez perforaría el soporte P25 hacia la cola P5–P10.",
            },
            "top_insights": [
                {
                    "title": "Idea clave 1 (Geometría y distancia a curvas)",
                    "body": "Lectura directa de la posición del precio frente a las curvas 2000v Cian, 1000v Ámbar y 500v Violeta.",
                },
                {
                    "title": "Idea clave 2 (Confluencia t+150 y cuartiles P25–P75)",
                    "body": "Lectura de alineación o divergencia entre las 3 pendientes proyectadas a t+150 y el cono central.",
                },
                {
                    "title": "Idea clave 3 (Consenso y riesgo estructural)",
                    "body": "Contraste frente al consenso externo de mercado y catalizadores históricos de régimen.",
                },
            ],
            "web_consensus": {
                "convergence_grade": "CONVERGENTE | DIVERGENTE | MIXTA",
                "summary": "Síntesis comparativa entre la geometría del motor y el consenso actual de analistas.",
                "sources": [
                    {
                        "source_name": "Medio o casa de análisis",
                        "date": "YYYY-MM-DD",
                        "stance": "Resumen breve de tesis o niveles",
                        "url": "https://...",
                    }
                ],
            },
            "visual_discrepancies": (
                "Confirmación de paridad visual/JSON tras inspeccionar hero.png y los 3 dashboards "
                "(1000v Ámbar, 2000v Cian, 500v Violeta), o matices visuales relevantes observados."
            ),
            "sindy_translation": "Traducción a lenguaje de mercado (amortiguamiento, fricción, empuje de volumen) de las EDOs de 1000v.",
            "cusum_catalysts": [
                {
                    "date": "YYYY-MM-DD",
                    "event": "Catalizador histórico real verificado en esa fecha de quiebre de régimen o pico de tensión CUSUM.",
                }
            ],
            "reading_limits": [
                "Las trayectorias t+150 combinan la extrapolación determinista (EDO SINDy o inercia amortiguada) con el cono empírico EWMA de los residuos del régimen activo.",
                "Los saltos exógenos graves modifican la curvatura mediante detección de cambio de régimen CUSUM en el laboratorio técnico.",
            ],
        }
        tpl_path = report_dir / "narrative_template.json"
        with open(tpl_path, "w", encoding="utf-8") as f:
            json.dump(template_obj, f, indent=2, ensure_ascii=False)
        return tpl_path

    # ──────────────────────────────────────────────────────────────────────────
    # 2. Narrativa por defecto (Etapa 1 sin IA) + Fusión con `narrative.json`
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def _build_default_narrative(
        cls, confluence: Dict[str, Any], pri_tel: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        ds = confluence["metadata"]["dataset"]
        hier = confluence["hierarchy_verdict"]
        ticker = ds["ticker"]
        last_p_txt = cls._fmt_html_price(ds["last_close_price"])

        curves_cmp = hier.get("curves_comparison", [])
        pri_row = next(
            (c for c in curves_cmp if c.get("role_code") == "PRINCIPAL_PREDICTIVA"),
            curves_cmp[0] if curves_cmp else {},
        )
        gap_txt = (
            f"distancia a curva 1000v {pri_row['gap_now_pct']:+.2f}%"
            if isinstance(pri_row.get("gap_now_pct"), (int, float))
            else "geometría 1000v activa"
        )
        r2_txt = (
            f"ajuste curva-precio R² {pri_row['curve_price_r2']:.3f}"
            if isinstance(pri_row.get("curve_price_r2"), (int, float))
            else ""
        )
        ret150 = pri_row.get("t150_center_return_pct")
        ret_txt = f" y proyección t+150 {ret150:+.2f}%" if isinstance(ret150, (int, float)) else ""

        headline = (
            f"{ticker} cotiza en {last_p_txt} bajo régimen '{hier['executive_banner']}' "
            f"({gap_txt}{(', ' + r2_txt) if r2_txt else ''}{ret_txt}; confianza física {hier['global_physical_confidence']})."
        )

        eqs = (pri_tel or {}).get("white_box_physics", {}).get("active_equations", ["0", "0"])
        eq_r = eqs[0] if eqs else "0"
        sindy_auto = (
            f"La ecuación diferencial activa de retorno ({eq_r}) gobierna la deriva determinista del régimen vigente "
            "mientras el volumen normalizado actúa como variable acoplada de amortiguamiento o impulso."
        )

        h_max = int(confluence["metadata"]["config"].get("horizon_steps", 150))
        audit_oos = bool(confluence["metadata"]["config"].get("audit_oos", False))
        oos_h = 90
        if pri_tel:
            oos_h = int(
                pri_tel.get("reliability_seal", {})
                .get("mini_walk_forward_oos", {})
                .get("eval_horizon_candles", 90)
            )

        limits = [
            (
                f"Las curvas proyectan t+{h_max} de forma simultánea en las 3 lentes (2000v Cian, 1000v Ámbar, 500v Violeta); "
                "los cuartiles P25–P75 miden dispersión empírica del régimen y no garantizan un suelo o techo rígido."
            ),
            (
                f"Auditoría Walk-Forward activada (--audit-oos hasta t+{oos_h})."
                if audit_oos
                else "Walk-Forward OOS desactivado por defecto en v0.3.1 (prioridad geométrica Curva-Precio; ejecute con --audit-oos si desea auditar cortes históricos)."
            ),
        ]
        if any(bool(c.get("geometric_fallback_used")) for c in curves_cmp):
            limits.append(
                "Al menos una lente activó amortiguamiento inercial geométrico al resultar degenerada o inestable su EDO SINDy puntual."
            )
        if pri_tel:
            reg_c = int(pri_tel.get("cusum_forensics", {}).get("active_regime_candles", 999))
            if reg_c < 120:
                limits.append(
                    f"El régimen vigente de 1000v es joven ({reg_c} velas), por lo que su pendiente proyecta la inercia reciente."
                )

        return {
            "headline": headline,
            "scenarios_catalysts": {
                "base": "Continuidad geométrica con el precio gravitando dentro del corredor probable P25–P75 de 1000v hacia t+150.",
                "bullish": "Expansión de tracción compradora capaz de superar el cuartil P75 y buscar la cola alcista P90–P95.",
                "bearish": "Pérdida de momento bajo el cuartil P25 con extensión hacia el borde inferior P5–P10 del abanico.",
            },
            "top_insights": [
                {
                    "title": "Geometría Principal (1000v · Ámbar)",
                    "body": f"{hier['executive_banner']} ({gap_txt}{(', ' + r2_txt) if r2_txt else ''}).",
                },
                {
                    "title": "Marea de Fondo (2000v · Cian)",
                    "body": f"Lectura estructural 2000v: {hier.get('context_tide_2000v', 'N/D')}.",
                },
                {
                    "title": "Sensor Táctico (500v · Violeta)",
                    "body": str(hier.get("tactical_alert_500v", "Sin sobresaltos recientes.")),
                },
            ],
            "web_consensus": {
                "convergence_grade": "PENDIENTE DE CONTRASTE WEB",
                "summary": (
                    "Vista cuantitativa generada en Etapa 1 directamente desde el motor. "
                    "Ejecute la Etapa 2 con `narrative.json` para incorporar el contraste con analistas externos."
                ),
                "sources": [],
            },
            "visual_discrepancies": "Paridad cuantitativa directa con las matrices del motor (pendiente de notas cualitativas de Etapa 2).",
            "sindy_translation": sindy_auto,
            "cusum_catalysts": [],
            "reading_limits": limits,
        }

    @classmethod
    def _merge_narrative(
        cls, default_nav: Dict[str, Any], user_nav: Optional[Dict[str, Any]]
    ) -> Tuple[Dict[str, Any], str]:
        if not user_nav:
            return default_nav, "cuantitativo"

        merged = dict(default_nav)
        if user_nav.get("headline"):
            merged["headline"] = str(user_nav["headline"]).strip()

        if isinstance(user_nav.get("scenarios_catalysts"), dict):
            sc = dict(default_nav["scenarios_catalysts"])
            for k in ("base", "bullish", "bearish"):
                if user_nav["scenarios_catalysts"].get(k):
                    sc[k] = str(user_nav["scenarios_catalysts"][k]).strip()
            merged["scenarios_catalysts"] = sc

        if isinstance(user_nav.get("top_insights"), list) and len(user_nav["top_insights"]) >= 1:
            ins_clean = []
            for item in user_nav["top_insights"][:3]:
                if isinstance(item, dict):
                    ins_clean.append(
                        {
                            "title": str(item.get("title", "Clave")).strip(),
                            "body": str(item.get("body", "")).strip(),
                        }
                    )
            while len(ins_clean) < 3:
                ins_clean.append(default_nav["top_insights"][len(ins_clean)])
            merged["top_insights"] = ins_clean

        if isinstance(user_nav.get("web_consensus"), dict):
            wc = dict(default_nav["web_consensus"])
            if user_nav["web_consensus"].get("convergence_grade"):
                wc["convergence_grade"] = str(user_nav["web_consensus"]["convergence_grade"]).strip()
            if user_nav["web_consensus"].get("summary"):
                wc["summary"] = str(user_nav["web_consensus"]["summary"]).strip()
            if isinstance(user_nav["web_consensus"].get("sources"), list):
                wc["sources"] = [
                    {
                        "source_name": str(s.get("source_name", "Fuente")).strip(),
                        "date": str(s.get("date", "")).strip(),
                        "stance": str(s.get("stance", "")).strip(),
                        "url": str(s.get("url", "")).strip(),
                    }
                    for s in user_nav["web_consensus"]["sources"]
                    if isinstance(s, dict)
                ]
            merged["web_consensus"] = wc

        for str_key in ("visual_discrepancies", "sindy_translation"):
            if user_nav.get(str_key):
                merged[str_key] = str(user_nav[str_key]).strip()

        if isinstance(user_nav.get("cusum_catalysts"), list):
            merged["cusum_catalysts"] = [
                {
                    "date": str(c.get("date", "")).strip(),
                    "event": str(c.get("event", "")).strip(),
                }
                for c in user_nav["cusum_catalysts"]
                if isinstance(c, dict)
            ]

        if isinstance(user_nav.get("reading_limits"), list) and len(user_nav["reading_limits"]) > 0:
            merged["reading_limits"] = [str(x).strip() for x in user_nav["reading_limits"] if str(x).strip()]

        return merged, "enriquecido"

    # ──────────────────────────────────────────────────────────────────────────
    # 3. Construcción del Gráfico Héroe Interactivo (Plotly + Selector Horizonte)
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_segmented_xy_with_nones(
        x_arr: np.ndarray,
        y_arr: np.ndarray,
        triggers: Sequence[int],
        dates_arr: Sequence[str],
        x_min_clip: float = 0.0,
    ) -> Tuple[List[Optional[float]], List[Optional[float]], List[str]]:
        """Inserta `None` en cada frontera CUSUM para cortar el trazo en Plotly sin escalones."""
        n = len(x_arr)
        clean_trigs = sorted({int(t) for t in triggers if 0 < int(t) < n})
        bounds = [0] + clean_trigs + [n]
        xs: List[Optional[float]] = []
        ys: List[Optional[float]] = []
        ds: List[str] = []

        for i in range(len(bounds) - 1):
            s_i, e_i = bounds[i], bounds[i + 1]
            if e_i <= s_i:
                continue
            sx = x_arr[s_i:e_i]
            sy = y_arr[s_i:e_i]
            sd = dates_arr[s_i:e_i]
            mask = sx >= x_min_clip
            if not np.any(mask):
                continue
            if xs:
                xs.append(None)
                ys.append(None)
                ds.append("")
            xs.extend(round(float(v), 2) for v in sx[mask])
            ys.extend(round(float(v), 4) for v in sy[mask])
            ds.extend(str(d)[:10] for d in np.asarray(sd)[mask])
        return xs, ys, ds

    @classmethod
    def _build_interactive_hero_spec(
        cls,
        bundle: Dict[str, Any],
        confluence: Dict[str, Any],
        pri_tel: Optional[Dict[str, Any]],
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]], str]:
        ds = confluence["metadata"]["dataset"]
        hier = confluence["hierarchy_verdict"]
        n_full = int(bundle["n_full"][0])
        h_start = int(bundle["h_start"][0])
        dates_hist = [str(d)[:10] for d in bundle["dates_hist"]]
        close_hist = np.asarray(bundle["close_hist"], dtype=np.float64)
        n_hist = len(close_hist)
        x_hist = np.arange(n_hist, dtype=np.float64)
        idx_today = max(0, n_hist - 1)
        last_p = float(ds["last_close_price"])
        h_max = int(confluence["metadata"]["config"].get("horizon_steps", 150))

        traces: List[Dict[str, Any]] = []
        shapes: List[Dict[str, Any]] = []
        annotations: List[Dict[str, Any]] = []

        # 1. Precio observado (Velas o Línea) sobre el 100% del historial guardado
        has_ohlc = int(bundle["has_ohlc"][0]) == 1
        if has_ohlc:
            open_h = np.asarray(bundle["open_hist"], dtype=np.float64)
            high_h = np.asarray(bundle["high_hist"], dtype=np.float64)
            low_h = np.asarray(bundle["low_hist"], dtype=np.float64)
            traces.append(
                {
                    "type": "candlestick",
                    "x": [int(v) for v in x_hist],
                    "open": [round(float(v), 4) for v in open_h],
                    "high": [round(float(v), 4) for v in high_h],
                    "low": [round(float(v), 4) for v in low_h],
                    "close": [round(float(v), 4) for v in close_hist],
                    "text": dates_hist,
                    "name": "Precio diario (OHLC)",
                    "increasing": {"line": {"color": "#10b981", "width": 1}, "fillcolor": "rgba(16,185,129,0.72)"},
                    "decreasing": {"line": {"color": "#f43f5e", "width": 1}, "fillcolor": "rgba(244,63,94,0.72)"},
                    "hoverinfo": "text+y",
                }
            )
        else:
            high_h = close_hist
            low_h = close_hist
            traces.append(
                {
                    "type": "scatter",
                    "mode": "lines",
                    "x": [int(v) for v in x_hist],
                    "y": [round(float(v), 4) for v in close_hist],
                    "customdata": dates_hist,
                    "name": "Precio de cierre",
                    "line": {"color": "#e2e8f0", "width": 1.6},
                    "hovertemplate": "Fecha: %{customdata}<br>Cierre: $%{y:,.2f}<extra></extra>",
                }
            )

        # 2. Tres lentes simultáneas: Curvas históricas + Proyección t+150 + Conos intercambiables
        # Orden de dibujado: 2000v (Cian) -> 500v (Violeta) -> 1000v (Ámbar protagonista al frente)
        lens_draw_specs = [
            {
                "prefix": "ctx",
                "default_win": "2000",
                "role_short": "Contexto",
                "color_name": "Cian",
                "line_color": "#22d3ee",
                "proj_color": "#67e8f9",
                "p5_fill": "rgba(34,211,238,0.08)",
                "p25_fill": "rgba(34,211,238,0.20)",
                "line_w": 2.0,
                "proj_w": 2.0,
            },
            {
                "prefix": "sen",
                "default_win": "500",
                "role_short": "Táctica",
                "color_name": "Violeta",
                "line_color": "#c084fc",
                "proj_color": "#d8b4fe",
                "p5_fill": "rgba(192,132,252,0.08)",
                "p25_fill": "rgba(192,132,252,0.20)",
                "line_w": 1.9,
                "proj_w": 1.9,
            },
            {
                "prefix": "pri",
                "default_win": "1000",
                "role_short": "Principal",
                "color_name": "Ámbar",
                "line_color": "#f59e0b",
                "proj_color": "#fbbf24",
                "p5_fill": "rgba(245,158,11,0.10)",
                "p25_fill": "rgba(245,158,11,0.24)",
                "line_w": 2.7,
                "proj_w": 2.6,
            },
        ]

        # Pre-escaneo de conos disponibles para decidir el cono por defecto (prioridad 1000 -> 500 -> 2000)
        avail_cones: List[str] = []
        lens_bundle_cache: Dict[str, Dict[str, Any]] = {}
        for lspec in lens_draw_specs:
            px = lspec["prefix"]
            if int(bundle.get(f"{px}_avail", [0])[0]) != 1:
                continue
            w_val = int(bundle[f"{px}_win"][0])
            w_key = str(w_val)
            nom_arr = np.asarray(bundle[f"{px}_nom"], dtype=np.float64)
            trigs_arr = [int(v) for v in bundle[f"{px}_trigs"].tolist()]
            dates_arr = [str(d)[:10] for d in bundle[f"{px}_dates"]]
            det_arr = np.asarray(bundle[f"{px}_det"], dtype=np.float64)
            mc_arr = np.asarray(bundle[f"{px}_mc"], dtype=np.float64)
            off_l = (n_full - len(nom_arr)) - h_start
            x_l = np.arange(len(nom_arr), dtype=np.float64) + off_l
            has_cone = len(det_arr) > 0 and mc_arr.shape == (5, len(det_arr))
            if has_cone:
                avail_cones.append(w_key)
            lens_bundle_cache[px] = {
                "win": w_val,
                "w_key": w_key,
                "nom": nom_arr,
                "trigs": trigs_arr,
                "dates": dates_arr,
                "x_l": x_l,
                "det": det_arr,
                "mc": mc_arr,
                "has_cone": has_cone,
            }

        if "1000" in avail_cones:
            default_cone_key = "1000"
        elif "500" in avail_cones:
            default_cone_key = "500"
        elif "2000" in avail_cones:
            default_cone_key = "2000"
        else:
            default_cone_key = "none"

        curve_trace_indices: List[int] = []
        det_trace_indices: List[int] = []
        cone_trace_map: Dict[str, List[int]] = {}
        cone_legend_indices: Dict[str, List[int]] = {}
        all_cone_indices: List[int] = []

        for lspec in lens_draw_specs:
            px = lspec["prefix"]
            ldata = lens_bundle_cache.get(px)
            if ldata is None:
                continue
            w_val = ldata["win"]
            w_key = ldata["w_key"]
            x_l = ldata["x_l"]
            nom_arr = ldata["nom"]
            trigs_arr = ldata["trigs"]
            dates_arr = ldata["dates"]
            det_arr = ldata["det"]
            mc_arr = ldata["mc"]

            xs_c, ys_c, ds_c = cls._build_segmented_xy_with_nones(x_l, nom_arr, trigs_arr, dates_arr, 0.0)
            curve_trace_indices.append(len(traces))
            traces.append(
                {
                    "type": "scatter",
                    "mode": "lines",
                    "x": xs_c,
                    "y": ys_c,
                    "customdata": ds_c,
                    "connectgaps": False,
                    "name": f"Curva {w_val}v · {lspec['color_name']} ({lspec['role_short']})",
                    "line": {
                        "color": lspec["line_color"],
                        "width": lspec["line_w"],
                        "dash": "solid",
                    },
                    "hovertemplate": f"Curva {w_val}v (%{{customdata}}): $%{{y:,.2f}}<extra></extra>",
                }
            )

            # Separadores verticales históricos CUSUM solo en la lente Principal (1000v)
            if px == "pri":
                for ti in trigs_arr[-4:]:
                    if 0 < ti < len(x_l) and x_l[ti] >= 0:
                        xv = float(x_l[ti])
                        shapes.append(
                            {
                                "type": "line",
                                "xref": "x",
                                "yref": "paper",
                                "x0": xv,
                                "x1": xv,
                                "y0": 0.0,
                                "y1": 1.0,
                                "line": {"color": "rgba(148,163,184,0.40)", "width": 1, "dash": "dash"},
                            }
                        )
                        annotations.append(
                            {
                                "x": xv,
                                "y": 0.98,
                                "xref": "x",
                                "yref": "paper",
                                "text": f"Nuevo régimen · {dates_arr[ti]}",
                                "showarrow": False,
                                "font": {"size": 10.5, "color": "#cbd5e1"},
                                "bgcolor": "rgba(15,23,42,0.86)",
                                "bordercolor": "#334155",
                                "borderwidth": 1,
                                "borderpad": 3,
                            }
                        )

            if len(det_arr) > 0:
                xf_join = [int(idx_today)] + [int(idx_today + 1 + k) for k in range(len(det_arr))]
                lbl_fut = ["Hoy"] + [f"t+{k + 1}" for k in range(len(det_arr))]

                # Cono probabilístico de esta lente (visible solo cuando se selecciona su botón)
                if ldata["has_cone"]:
                    is_def_cone = w_key == default_cone_key
                    p5 = [round(last_p, 4)] + [round(float(v), 4) for v in mc_arr[0]]
                    p25 = [round(last_p, 4)] + [round(float(v), 4) for v in mc_arr[1]]
                    p75 = [round(last_p, 4)] + [round(float(v), 4) for v in mc_arr[3]]
                    p95 = [round(last_p, 4)] + [round(float(v), 4) for v in mc_arr[4]]

                    idx_list: List[int] = []
                    leg_list: List[int] = []

                    # P95 (borde superior P5-P95)
                    idx_list.append(len(traces))
                    traces.append(
                        {
                            "type": "scatter",
                            "mode": "lines",
                            "x": xf_join,
                            "y": p95,
                            "customdata": lbl_fut,
                            "line": {"width": 0},
                            "hovertemplate": f"P95 {w_val}v (%{{customdata}}): $%{{y:,.2f}}<extra></extra>",
                            "showlegend": False,
                            "visible": is_def_cone,
                        }
                    )
                    # P5 (relleno tonexty P5-P95)
                    leg_p5 = len(traces)
                    idx_list.append(leg_p5)
                    leg_list.append(leg_p5)
                    traces.append(
                        {
                            "type": "scatter",
                            "mode": "lines",
                            "x": xf_join,
                            "y": p5,
                            "customdata": lbl_fut,
                            "fill": "tonexty",
                            "fillcolor": lspec["p5_fill"],
                            "line": {"width": 0},
                            "name": f"Banda P5–P95 ({w_val}v)",
                            "hovertemplate": f"P5 {w_val}v (%{{customdata}}): $%{{y:,.2f}}<extra></extra>",
                            "showlegend": is_def_cone,
                            "visible": is_def_cone,
                        }
                    )
                    # P75 (borde superior P25-P75)
                    idx_list.append(len(traces))
                    traces.append(
                        {
                            "type": "scatter",
                            "mode": "lines",
                            "x": xf_join,
                            "y": p75,
                            "customdata": lbl_fut,
                            "line": {"width": 0},
                            "hovertemplate": f"P75 {w_val}v (%{{customdata}}): $%{{y:,.2f}}<extra></extra>",
                            "showlegend": False,
                            "visible": is_def_cone,
                        }
                    )
                    # P25 (relleno tonexty P25-P75)
                    leg_p25 = len(traces)
                    idx_list.append(leg_p25)
                    leg_list.append(leg_p25)
                    traces.append(
                        {
                            "type": "scatter",
                            "mode": "lines",
                            "x": xf_join,
                            "y": p25,
                            "customdata": lbl_fut,
                            "fill": "tonexty",
                            "fillcolor": lspec["p25_fill"],
                            "line": {"width": 0},
                            "name": f"Banda probable P25–P75 ({w_val}v)",
                            "hovertemplate": f"P25 {w_val}v (%{{customdata}}): $%{{y:,.2f}}<extra></extra>",
                            "showlegend": is_def_cone,
                            "visible": is_def_cone,
                        }
                    )
                    cone_trace_map[w_key] = idx_list
                    cone_legend_indices[w_key] = leg_list
                    all_cone_indices.extend(idx_list)

                # Proyección determinista t+150 (SIEMPRE visible simultáneamente para las 3 lentes)
                det_join = [round(last_p, 4)] + [round(float(v), 4) for v in det_arr]
                det_trace_indices.append(len(traces))
                traces.append(
                    {
                        "type": "scatter",
                        "mode": "lines",
                        "x": xf_join,
                        "y": det_join,
                        "customdata": lbl_fut,
                        "name": f"Proyección {w_val}v t+{len(det_arr)} ({lspec['color_name']})",
                        "line": {"color": lspec["proj_color"], "width": lspec["proj_w"], "dash": "dash"},
                        "hovertemplate": f"Proyección {w_val}v (%{{customdata}}): $%{{y:,.2f}}<extra></extra>",
                    }
                )

        # 3. Línea vertical "Hoy"
        shapes.append(
            {
                "type": "line",
                "xref": "x",
                "yref": "paper",
                "x0": idx_today,
                "x1": idx_today,
                "y0": 0.0,
                "y1": 1.0,
                "line": {"color": "rgba(234,179,8,0.72)", "width": 1.3, "dash": "dashdot"},
            }
        )

        # 4. Cálculo exacto de ticks X y auto-escalado Y limpio para [120v | 500v | 1000v | 2000v | Todo] x Conos
        def _compute_x_ticks(x0_v: int, x1_v: int) -> Tuple[List[int], List[str]]:
            x_a = max(0, int(x0_v))
            x_b = min(idx_today + h_max, int(x1_v))
            if x_b <= x_a:
                x_b = x_a + 10
            vals_raw = [int(round(v)) for v in np.linspace(x_a, x_b, num=9)]
            vals_uniq = list(dict.fromkeys(vals_raw))
            lbls = [
                dates_hist[v] if 0 <= v < n_hist else f"t+{v - idx_today}"
                for v in vals_uniq
            ]
            return vals_uniq, lbls

        def _compute_y_bounds(x0_i: int, cone_key: str) -> List[float]:
            x0_c = max(0, min(idx_today, int(x0_i)))
            vals: List[np.ndarray] = [high_h[x0_c:], low_h[x0_c:]]
            for px_k, ldata in lens_bundle_cache.items():
                x_l = ldata["x_l"]
                nom_l = ldata["nom"]
                mask_l = x_l >= x0_c
                if np.any(mask_l):
                    vals.append(nom_l[mask_l])
                if len(ldata["det"]) > 0:
                    vals.append(ldata["det"])
                if cone_key != "none" and ldata["w_key"] == cone_key and ldata["has_cone"]:
                    mc_c = ldata["mc"]
                    vals.extend([mc_c[0], mc_c[4]])
            valid_segs = [a[np.isfinite(a)] for a in vals if len(a) > 0]
            if not valid_segs:
                return [round(last_p * 0.85, 4), round(last_p * 1.15, 4)]
            cat = np.concatenate(valid_segs)
            if len(cat) == 0:
                return [round(last_p * 0.85, 4), round(last_p * 1.15, 4)]
            ylo, yhi = float(np.min(cat)), float(np.max(cat))
            pad = (yhi - ylo) * 0.10 if yhi > ylo else max(abs(last_p) * 0.05, 1.0)
            return [round(ylo - pad, 4), round(yhi + pad, 4)]

        cone_keys_all = ["1000", "2000", "500", "none"]
        window_specs = [
            ("120", "120v", 120, False),
            ("500", "500v", 500, True),
            ("1000", "1000v", 1000, False),
            ("2000", "2000v", 2000, False),
            ("all", "Todo el historial", idx_today, False),
        ]

        presets: Dict[str, Dict[str, Any]] = {}
        window_buttons: List[Dict[str, Any]] = []
        for w_code, w_lbl, back_c, is_def_w in window_specs:
            x0_w = max(0, idx_today - int(back_c))
            x1_w = idx_today + h_max + 8
            tvals_w, ttext_w = _compute_x_ticks(x0_w, x1_w)
            y_by_cone = {ck: _compute_y_bounds(x0_w, ck) for ck in cone_keys_all}
            presets[w_code] = {
                "x_range": [x0_w, x1_w],
                "y_by_cone": y_by_cone,
                "tickvals": tvals_w,
                "ticktext": ttext_w,
                "label": w_lbl,
            }
            window_buttons.append({"key": w_code, "label": w_lbl, "default": is_def_w})

        # Readouts geométricos por cono activo (sin barreras CUSUM de 1 vela)
        cmp_by_win = {str(c["window_candles"]): c for c in hier.get("curves_comparison", []) if "window_candles" in c}
        mini_3curves_parts: List[str] = []
        for w_tag, c_lbl in (("2000", "2000v"), ("1000", "1000v"), ("500", "500v")):
            cr = cmp_by_win.get(w_tag)
            if cr and cr.get("available") and cr.get("t150_center_price") is not None:
                mini_3curves_parts.append(
                    f"{c_lbl}: {cls._fmt_html_price(cr['t150_center_price'])} ({cr['t150_center_return_pct']:+.1f}%)"
                )
        mini_3curves = " | ".join(mini_3curves_parts)

        cone_readouts: Dict[str, str] = {}
        for ck, clbl in (("1000", "1000v · Ámbar"), ("2000", "2000v · Cian"), ("500", "500v · Violeta")):
            cr = cmp_by_win.get(ck)
            if cr and cr.get("available") and cr.get("t150_center_price") is not None:
                cone_readouts[ck] = (
                    f"Cono activo {clbl} (t+{h_max}): Centro {cls._fmt_html_price(cr['t150_center_price'])} "
                    f"({cr['t150_center_return_pct']:+.2f}%) · Banda P25–P75: "
                    f"{cls._fmt_html_price(cr['t150_p25_price'])} – {cls._fmt_html_price(cr['t150_p75_price'])} · "
                    f"Rango P5–P95: {cls._fmt_html_price(cr['t150_p5_price'])} – {cls._fmt_html_price(cr['t150_p95_price'])}"
                    + (f"  |  3 Curvas t+{h_max}: [{mini_3curves}]" if mini_3curves else "")
                )
            else:
                cone_readouts[ck] = (
                    f"Cono {clbl} no disponible para este historial  |  Proyecciones t+{h_max}: [{mini_3curves}]"
                )
        cone_readouts["none"] = (
            f"Sin cono (solo curvas puras y trayectorias t+{h_max}): [{mini_3curves or 'Curvas geométricas activas'}]"
        )

        cone_buttons = [
            {
                "key": "1000",
                "label": "1000v",
                "color_dot": "#f59e0b",
                "available": "1000" in cone_trace_map,
                "default": default_cone_key == "1000",
            },
            {
                "key": "2000",
                "label": "2000v",
                "color_dot": "#22d3ee",
                "available": "2000" in cone_trace_map,
                "default": default_cone_key == "2000",
            },
            {
                "key": "500",
                "label": "500v",
                "color_dot": "#c084fc",
                "available": "500" in cone_trace_map,
                "default": default_cone_key == "500",
            },
            {
                "key": "none",
                "label": "Sin cono",
                "color_dot": "#94a3b8",
                "available": True,
                "default": default_cone_key == "none",
            },
        ]

        def_preset = presets["500"]
        x0_def, x1_def = def_preset["x_range"]
        yb_def = def_preset["y_by_cone"].get(default_cone_key, def_preset["y_by_cone"]["none"])
        def_readout = cone_readouts.get(default_cone_key, cone_readouts["none"])

        layout = {
            "paper_bgcolor": "#0f172a",
            "plot_bgcolor": "#0f172a",
            "font": {"family": "Inter, Segoe UI, sans-serif", "color": "#cbd5e1", "size": 12},
            "margin": {"l": 58, "r": 26, "t": 26, "b": 42},
            "hovermode": "x unified",
            "xaxis": {
                "range": [x0_def, x1_def],
                "tickmode": "array",
                "tickvals": def_preset["tickvals"],
                "ticktext": def_preset["ticktext"],
                "gridcolor": "#1e293b",
                "linecolor": "#334155",
                "rangeslider": {"visible": False},
            },
            "yaxis": {
                "range": yb_def,
                "gridcolor": "#1e293b",
                "linecolor": "#334155",
                "tickprefix": "$",
                "side": "right",
            },
            "legend": {
                "orientation": "h",
                "x": 0.0,
                "y": 1.11,
                "bgcolor": "rgba(9,13,22,0.82)",
                "bordercolor": "#334155",
                "borderwidth": 1,
                "font": {"size": 11},
            },
            "shapes": shapes,
            "annotations": annotations,
        }

        hero_spec = {
            "data": traces,
            "layout": layout,
            "presets": presets,
            "nav": {
                "idx_today": int(idx_today),
                "n_hist": int(n_hist),
                "h_max": int(h_max),
                "dates_hist": dates_hist,
                "default_window": "500",
                "default_cone": default_cone_key,
                "cone_buttons": cone_buttons,
                "cone_trace_map": cone_trace_map,
                "cone_legend_indices": cone_legend_indices,
                "all_cone_indices": all_cone_indices,
                "cone_readouts": cone_readouts,
                "curve_trace_indices": curve_trace_indices,
                "det_trace_indices": det_trace_indices,
            },
        }
        return hero_spec, window_buttons, def_readout

    # ──────────────────────────────────────────────────────────────────────────
    # 4. Vistas de Datos Comunes para HTML y Markdown (100% cifras del motor)
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def _build_structured_views(
        cls,
        confluence: Dict[str, Any],
        pri_tel: Optional[Dict[str, Any]],
        narrative: Dict[str, Any],
        for_markdown: bool = False,
    ) -> Dict[str, Any]:
        fmt_p = cls._fmt_md_price if for_markdown else cls._fmt_html_price
        ds = confluence["metadata"]["dataset"]
        cfg_meta = confluence["metadata"].get("config", {})
        audit_oos = bool(cfg_meta.get("audit_oos", False))
        hier = confluence["hierarchy_verdict"]
        lenses = confluence["lenses_ordered"]
        last_p = float(ds["last_close_price"])

        ctx_s = lenses[0]
        pri_s = lenses[1]
        sen_s = lenses[2]

        # Tarjeta de Régimen (100% geométrica, sin vetos OOS por defecto)
        p_cur_v = pri_s.get("curve_now_price")
        p_gap = pri_s.get("price_vs_spline_gap_pct")
        p_r2 = pri_s.get("curve_price_r2")
        p_mape = pri_s.get("curve_price_mape_pct")
        p_ret150 = (pri_s.get("t150_summary") or {}).get("center_return_pct")
        p_parts = []
        if p_cur_v is not None:
            p_parts.append(f"Curva {fmt_p(p_cur_v)} ({float(p_gap or 0.0):+.2f}%)")
        if p_r2 is not None:
            p_parts.append(f"Ajuste Curva-Precio R² {float(p_r2):.3f} (MAPE {float(p_mape or 0.0):.2f}%)")
        if p_ret150 is not None:
            p_parts.append(f"t+150 {float(p_ret150):+.2f}%")
        primary_sub = " · ".join(p_parts) if p_parts else str(pri_s.get("seal_human", "Geometría activa"))

        if not ctx_s.get("available"):
            ctx_title = "No disponible"
            ctx_sub = "Activo con menos de 2000 velas"
        else:
            ctx_title = ctx_s.get("human_regime", {}).get("state_label", "Marea activa")
            c_cur_v = ctx_s.get("curve_now_price")
            c_gap = ctx_s.get("price_vs_spline_gap_pct")
            c_r2 = ctx_s.get("curve_price_r2")
            c_ret150 = (ctx_s.get("t150_summary") or {}).get("center_return_pct")
            c_parts = []
            if c_cur_v is not None:
                c_parts.append(f"Curva {fmt_p(c_cur_v)} ({float(c_gap or 0.0):+.2f}%)")
            if c_r2 is not None:
                c_parts.append(f"R² {float(c_r2):.3f}")
            if c_ret150 is not None:
                c_parts.append(f"t+150 {float(c_ret150):+.2f}%")
            ctx_sub = " · ".join(c_parts) if c_parts else ctx_s.get("human_regime", {}).get("position_short", "")

        tac_det = hier.get("tactical_sensor_detail", {})
        alert_title = (
            "Alerta táctica activa" if tac_det.get("has_active_alert") else sen_s.get("human_regime", {}).get("state_label", "Pulso estable")
        )
        conf_sub = (
            f"Confluencia geométrica Curva-Precio 3 lentes + Walk-Forward (--audit-oos)"
            if audit_oos
            else "Confluencia geométrica de las 3 curvas, ajuste R² curva-precio y armonía direccional"
        )

        regime_card = {
            "primary_sub": primary_sub,
            "context_title": ctx_title,
            "context_sub": ctx_sub,
            "alert_title": alert_title,
            "confidence_sub": conf_sub,
        }

        # Escenarios geométricos centrados en las curvas y cuartiles P25/P75 (siempre activos)
        sc_raw = hier.get("executive_scenarios", {})
        sc_avail = bool(sc_raw.get("available"))
        sc_view: Dict[str, Any] = {"validated": sc_avail, "available": sc_avail}
        if sc_avail:
            b_obj = sc_raw["base"]
            u_obj = sc_raw["bullish"]
            d_obj = sc_raw["bearish"]
            sc_view.update(
                {
                    "horizon_step": sc_raw.get("horizon_step", "t+150"),
                    "base": {
                        "prob_fmt": f"{b_obj['touch_probability_pct']:.1f}%",
                        "stay_fmt": f"{b_obj['channel_survival_probability_pct']:.1f}%",
                        "trigger_fmt": f"Gravitación en corredor P25–P75 ({fmt_p(b_obj['trigger_low_price'])} – {fmt_p(b_obj['trigger_high_price'])})",
                        "target_fmt": f"{fmt_p(b_obj['target_price'])} ({b_obj['target_return_pct']:+.2f}%)",
                        "band_fmt": f"{fmt_p(b_obj['band_p25_price'])} – {fmt_p(b_obj['band_p75_price'])}",
                    },
                    "bullish": {
                        "prob_fmt": f"{u_obj['touch_probability_pct']:.1f}%",
                        "trigger_fmt": f"Consolidación sobre {fmt_p(u_obj['trigger_price'])} ({u_obj['trigger_pct_from_close']:+.2f}%)",
                        "target_fmt": f"{fmt_p(u_obj['target_price'])} ({u_obj['target_return_pct']:+.2f}%)",
                    },
                    "bearish": {
                        "prob_fmt": f"{d_obj['touch_probability_pct']:.1f}%",
                        "trigger_fmt": f"Debilidad sostenida bajo {fmt_p(d_obj['trigger_price'])} ({d_obj['trigger_pct_from_close']:+.2f}%)",
                        "target_fmt": f"{fmt_p(d_obj['target_price'])} ({d_obj['target_return_pct']:+.2f}%)",
                    },
                }
            )

        # Tabla comparativa de las 3 curvas (2000v Cian · 1000v Ámbar · 500v Violeta)
        curves_table: List[Dict[str, Any]] = []
        for c_item in hier.get("curves_comparison", []):
            w_c = int(c_item.get("window_candles", 0))
            if not c_item.get("available"):
                curves_table.append(
                    {
                        "window": f"{w_c}v",
                        "color_name": c_item.get("color_name", ""),
                        "role": c_item.get("role_label", ""),
                        "available": False,
                        "curve_now_fmt": "N/D",
                        "gap_now_fmt": "N/D",
                        "gap_30_fmt": "N/D",
                        "fit_r2_fmt": "N/D",
                        "fit_quality": "Sin historial",
                        "t150_center_fmt": "N/D",
                        "t150_iqr_fmt": "N/D",
                        "is_primary": c_item.get("role_code") == "PRINCIPAL_PREDICTIVA",
                    }
                )
                continue
            r2_c = c_item.get("curve_price_r2")
            mape_c = c_item.get("curve_price_mape_pct")
            g_now = c_item.get("gap_now_pct")
            g_30 = c_item.get("last_30c_mean_gap_pct")
            t150_p = c_item.get("t150_center_price")
            t150_r = c_item.get("t150_center_return_pct")
            curves_table.append(
                {
                    "window": f"{w_c}v",
                    "color_name": c_item.get("color_name", ""),
                    "role": c_item.get("role_label", ""),
                    "available": True,
                    "curve_now_fmt": fmt_p(c_item.get("curve_now_price")),
                    "gap_now_fmt": f"{float(g_now):+.2f}%" if isinstance(g_now, (int, float)) else "N/D",
                    "gap_30_fmt": f"{float(g_30):+.2f}%" if isinstance(g_30, (int, float)) else "N/D",
                    "fit_r2_fmt": (
                        f"{float(r2_c):.3f} (MAPE {float(mape_c or 0.0):.2f}%)"
                        if isinstance(r2_c, (int, float))
                        else "N/D"
                    ),
                    "fit_quality": str(c_item.get("curve_price_quality") or "N/D"),
                    "t150_center_fmt": (
                        f"{fmt_p(t150_p)} ({float(t150_r or 0.0):+.2f}%)"
                        if isinstance(t150_p, (int, float))
                        else "N/D"
                    ),
                    "t150_iqr_fmt": (
                        f"{fmt_p(c_item.get('t150_p25_price'))} – {fmt_p(c_item.get('t150_p75_price'))}"
                        if c_item.get("t150_p25_price") is not None
                        else "N/D"
                    ),
                    "is_primary": c_item.get("role_code") == "PRINCIPAL_PREDICTIVA",
                }
            )

        # Tabla de Niveles y Rangos Geométricos (SIN filas de invalidación CUSUM de 1 vela)
        levels_table: List[Dict[str, Any]] = [
            {
                "label": f"Precio último cierre ({ds['last_candle_date']})",
                "price_fmt": fmt_p(last_p),
                "ret_fmt": "0.00%",
                "iqr_fmt": "Referencia actual",
                "wide_fmt": "—",
                "note": "Dato observado",
                "highlight": True,
            }
        ]

        anchor_w = int(hier.get("anchor_window_candles", 1000))
        for r_item in hier.get("executive_ranges", []):
            levels_table.append(
                {
                    "label": f"Proyección {anchor_w}v · {r_item['horizon_label']} ({r_item['horizon_step']})",
                    "price_fmt": fmt_p(r_item["center_price"]),
                    "ret_fmt": f"{r_item['center_return_pct']:+.2f}%",
                    "iqr_fmt": f"{fmt_p(r_item['p25_price'])} – {fmt_p(r_item['p75_price'])}",
                    "wide_fmt": f"{fmt_p(r_item['p5_price'])} – {fmt_p(r_item['p95_price'])}",
                    "note": "Auditado Walk-Forward" if audit_oos else "Cono geométrico P25–P75",
                    "highlight": False,
                }
            )

        for c_item in hier.get("curves_comparison", []):
            w_c = int(c_item.get("window_candles", 0))
            if not c_item.get("available") or w_c == anchor_w or c_item.get("t150_center_price") is None:
                continue
            levels_table.append(
                {
                    "label": f"Proyección {w_c}v ({c_item.get('color_name', '')}) · t+150",
                    "price_fmt": fmt_p(c_item["t150_center_price"]),
                    "ret_fmt": f"{float(c_item['t150_center_return_pct'] or 0.0):+.2f}%",
                    "iqr_fmt": f"{fmt_p(c_item['t150_p25_price'])} – {fmt_p(c_item['t150_p75_price'])}",
                    "wide_fmt": f"{fmt_p(c_item['t150_p5_price'])} – {fmt_p(c_item['t150_p95_price'])}",
                    "note": f"Comparativa {c_item.get('role_label', '')}",
                    "highlight": False,
                }
            )

        # Tabla técnica de las 3 lentes (Parte 2.1)
        lenses_table: List[Dict[str, Any]] = []
        for s_item in (pri_s, ctx_s, sen_s):
            is_pri = s_item.get("role_code") == "PRINCIPAL_PREDICTIVA"
            c_name = s_item.get("color_name", "")
            if not s_item.get("available"):
                lenses_table.append(
                    {
                        "window": f"{s_item['window_candles']}v",
                        "color_name": c_name,
                        "role": s_item["role_label"],
                        "human_state": "No disponible",
                        "fit_r2_fmt": "N/D",
                        "r2_fmt": "N/D",
                        "oos_fmt": "N/D",
                        "t150_fmt": "N/D",
                        "cone_cal_fmt": "N/D",
                        "seal_fmt": "Sin historial",
                        "is_primary": is_pri,
                    }
                )
                continue

            cc = s_item.get("cone_calibration") or {}
            cov_iqr = cc.get("empirical_p25_p75_coverage_pct")
            if isinstance(cov_iqr, (int, float)):
                cone_txt = f"{cov_iqr:.1f}% ({cc.get('calibration_label', '')})"
            else:
                cone_txt = "No evaluado"

            c_r2_v = s_item.get("curve_price_r2")
            c_mape_v = s_item.get("curve_price_mape_pct")
            fit_txt = (
                f"{float(c_r2_v):.3f} ({float(c_mape_v or 0.0):.2f}%)"
                if isinstance(c_r2_v, (int, float))
                else "N/D"
            )
            oos_hr = s_item.get("oos_consensus_hr_pct")
            if audit_oos and isinstance(oos_hr, (int, float)):
                oos_txt = f"{oos_hr}% ({s_item.get('oos_effective_cuts')} cortes)"
            else:
                oos_txt = "Opcional (--audit-oos)"

            t150_s = s_item.get("t150_summary") or {}
            t150_txt = (
                f"{fmt_p(t150_s.get('center_price'))} ({float(t150_s.get('center_return_pct') or 0.0):+.1f}%)"
                if t150_s.get("center_price") is not None
                else "N/D"
            )

            lenses_table.append(
                {
                    "window": f"{s_item['window_candles']}v",
                    "color_name": c_name,
                    "role": s_item["role_label"],
                    "human_state": s_item.get("human_regime", {}).get("full_label", s_item.get("raw_direction", "N/D")),
                    "fit_r2_fmt": fit_txt,
                    "r2_fmt": f"{s_item.get('sindy_r2_score', 0.0):.3f}",
                    "oos_fmt": oos_txt,
                    "t150_fmt": t150_txt,
                    "cone_cal_fmt": cone_txt,
                    "seal_fmt": s_item.get("seal_human", s_item.get("seal_grade", "N/D")),
                    "is_primary": is_pri,
                }
            )

        # Vista EDOs SINDy 1000v (Parte 2.4)
        if pri_tel is not None:
            wb = pri_tel["white_box_physics"]
            eqs = wb.get("active_equations", [])
            cus_p = pri_tel["cusum_forensics"]
            stab_raw = wb.get("linear_stability_spectrum", {}).get("stability_regime", "")
            sindy_view = {
                "var_name": wb.get("state_variable", "r"),
                "eq_r": eqs[0] if len(eqs) > 0 else "0",
                "eq_v": eqs[1] if len(eqs) > 1 else "0",
                "regime_span": f"{cus_p['active_regime_candles']} velas (desde {cus_p['active_regime_start_date']})",
                "r2_fmt": f"{wb.get('active_r2_score', 0.0):.4f}",
                "stability_human": str(stab_raw).replace("_", " ").capitalize() if stab_raw else "Lineal acoplada",
            }
        else:
            sindy_view = {
                "var_name": "r",
                "eq_r": "N/D",
                "eq_v": "N/D",
                "regime_span": "N/D",
                "r2_fmt": "N/D",
                "stability_human": "No disponible",
            }

        # Vista Forense CUSUM (Parte 2.5)
        cat_map = {
            c["date"][:10]: c["event"]
            for c in narrative.get("cusum_catalysts", [])
            if c.get("date")
        }
        cusum_events: List[Dict[str, Any]] = []
        if pri_tel is not None:
            cus_p = pri_tel["cusum_forensics"]
            for brk in cus_p.get("macro_breaks", [])[-4:]:
                d_iso = str(brk["date"])[:10]
                is_up_b = "ALCISTA" in str(brk.get("break_type", ""))
                cusum_events.append(
                    {
                        "kind": f"Quiebre {'alcista' if is_up_b else 'bajista'} (1000v)",
                        "date": d_iso,
                        "price_fmt": fmt_p(brk.get("price_at_break")),
                        "metric_fmt": f"Retorno {brk.get('candle_return_pct', 0.0):+.2f}% · Score {brk.get('peak_cusum_score', 0.0):.2f}",
                        "catalyst": cat_map.get(d_iso, "Cambio estructural detectado en flujo retorno-volumen."),
                    }
                )
            pk = cus_p.get("window_max_tension_peak")
            if pk and pk.get("date"):
                d_pk = str(pk["date"])[:10]
                if not any(ev["date"] == d_pk for ev in cusum_events):
                    cusum_events.append(
                        {
                            "kind": "Pico máximo de tensión CUSUM (1000v)",
                            "date": d_pk,
                            "price_fmt": fmt_p(pk.get("price")),
                            "metric_fmt": f"Tensión {pk.get('peak_score', 0.0):.2f} / {cus_p['current_tension']['threshold_h']:.1f} ({pk.get('side', '')})",
                            "catalyst": cat_map.get(d_pk, "Episodio de máxima fricción frente a la curva suave."),
                        }
                    )
        # Añadir eventos tácticos recientes de 500v si no están ya
        for brk5 in sen_s.get("macro_breaks", [])[-2:]:
            d5 = str(brk5.get("date", ""))[:10]
            if d5 and not any(ev["date"] == d5 for ev in cusum_events):
                is_up5 = "ALCISTA" in str(brk5.get("break_type", ""))
                cusum_events.append(
                    {
                        "kind": f"Alerta quiebre corto plazo (500v · {'alza' if is_up5 else 'baja'})",
                        "date": d5,
                        "price_fmt": fmt_p(brk5.get("price_at_break")),
                        "metric_fmt": f"Score {brk5.get('peak_cusum_score', 0.0):.2f}",
                        "catalyst": cat_map.get(d5, "Ruptura táctica registrada por el sensor de 500 velas."),
                    }
                )

        if not cusum_events:
            cusum_events.append(
                {
                    "kind": "Régimen continuo sin quiebres",
                    "date": ds["last_candle_date"],
                    "price_fmt": fmt_p(last_p),
                    "metric_fmt": f"Tensión hoy {pri_s.get('cusum_tension_vs_h', '0.00 / 5.0')}",
                    "catalyst": "El activo permaneció dentro de sus umbrales de control en toda la ventana.",
                }
            )

        return {
            "regime_card": regime_card,
            "scenarios_view": sc_view,
            "curves_table": curves_table,
            "levels_table": levels_table,
            "lenses_table": lenses_table,
            "sindy_view": sindy_view,
            "cusum_events_view": cusum_events,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # 5. Generación de `analysis.md` (Orden Geométrico Puro v0.3.1)
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def _build_markdown_document(
        cls,
        confluence: Dict[str, Any],
        pri_tel: Optional[Dict[str, Any]],
        narrative: Dict[str, Any],
        hero_img_ref: str = "./hero.png",
        dash_1000_img_ref: str = "./lens_1000/dashboard.png",
        report_html_ref: Optional[str] = None,
        dash_2000_img_ref: Optional[str] = None,
        dash_500_img_ref: Optional[str] = None,
    ) -> str:
        esc = cls.escape_md_dollars
        ds = confluence["metadata"]["dataset"]
        hier = confluence["hierarchy_verdict"]
        views = cls._build_structured_views(confluence, pri_tel, narrative, for_markdown=True)
        rc = views["regime_card"]
        sc_v = views["scenarios_view"]

        lines: List[str] = []

        # ══════════════════════════════════════════════════════════════════════
        # PARTE 1: FICHA EJECUTIVA (100% Geométrica Multi-Lente)
        # ══════════════════════════════════════════════════════════════════════
        lines.append(f"# {ds['ticker']} — Diagnóstico KineTopus ({ds['last_candle_date']})")
        lines.append("")
        # Bloque 1.1: Titular
        lines.append(f"> **{esc(narrative['headline'])}**")
        if report_html_ref:
            lines.append(f"> \n> Versión interactiva autocontenida: [report.html]({report_html_ref})")
        lines.append("")

        # Bloque 1.2: Tarjeta de Régimen
        lines.append("## 1. Tarjeta de Régimen Geométrico")
        lines.append("")
        lines.append("| Dimensión | Lectura Actual | Detalle de Respaldo |")
        lines.append("| :--- | :--- | :--- |")
        lines.append(
            f"| **Precio último cierre** | **{cls._fmt_md_price(ds['last_close_price'])}** | Sesión `{ds['last_candle_date']}` ({ds['interval']} · {ds['calendar_mode']}) |"
        )
        lines.append(
            f"| **Lente principal (`1000v` · Ámbar)** | **{esc(hier['executive_banner'])}** | {esc(rc['primary_sub'])} |"
        )
        lines.append(
            f"| **Contexto estructural (`2000v` · Cian)** | {esc(rc['context_title'])} | {esc(rc['context_sub'])} |"
        )
        lines.append(
            f"| **Pulso táctico (`500v` · Violeta)** | {esc(rc['alert_title'])} | {esc(hier['tactical_alert_500v'])} |"
        )
        lines.append(
            f"| **Confianza geométrica** | **`{hier['global_physical_confidence']}`** | {esc(rc['confidence_sub'])} |"
        )
        lines.append("")

        # Bloque 1.3: Gráfico Héroe
        lines.append("## 2. Gráfico Héroe (3 Lentes t+150)")
        lines.append("")
        lines.append(f"![Gráfico Héroe {ds['ticker']}]({hero_img_ref})")
        lines.append("")

        # Bloque 1.4: Posición frente a las 3 curvas y proyección simultánea t+150
        lines.append("## 3. Posición del Precio frente a las 3 Curvas (`2000v` · `1000v` · `500v`)")
        lines.append("")
        lines.append(
            "| Lente | Rol | Curva Hoy | Dist. Precio vs. Curva | Ajuste Curva-Precio (`R²` / MAPE) | Proyección `t+150` | Cuartiles `P25–P75` (`t+150`) |"
        )
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for crow in views["curves_table"]:
            lines.append(
                f"| **`{crow['window']}` ({esc(crow['color_name'])})** | {esc(crow['role'])} | {crow['curve_now_fmt']} | "
                f"`{crow['gap_now_fmt']}` *(30v: `{crow['gap_30_fmt']}`)* | `{crow['fit_r2_fmt']}` | "
                f"**{crow['t150_center_fmt']}** | {crow['t150_iqr_fmt']} |"
            )
        lines.append("")

        # Bloque 1.5: 3 Escenarios con probabilidad de toque basados en cuartiles P25/P75
        lines.append("## 4. Escenarios Operativos (`1000v` · Cuartiles `P25/P75`)")
        lines.append("")
        if sc_v.get("validated"):
            hz_tag = sc_v["horizon_step"]
            cats = narrative["scenarios_catalysts"]
            lines.append(
                "| Escenario | Condición Geométrica (`P25/P75`) | Objetivo | Prob. de toque antes de `"
                + hz_tag
                + "` | Catalizador / Lectura |"
            )
            lines.append("| :--- | :--- | :--- | :--- | :--- |")
            lines.append(
                f"| **Base (Central)** | {sc_v['base']['trigger_fmt']} | **{sc_v['base']['target_fmt']}** *(banda P25–P75: {sc_v['base']['band_fmt']})* | **{sc_v['base']['prob_fmt']}** *(permanencia en canal: {sc_v['base']['stay_fmt']})* | {esc(cats['base'])} |"
            )
            lines.append(
                f"| **Expansión Alcista** | {sc_v['bullish']['trigger_fmt']} | **{sc_v['bullish']['target_fmt']}** | **{sc_v['bullish']['prob_fmt']}** | {esc(cats['bullish'])} |"
            )
            lines.append(
                f"| **Reversión Bajista** | {sc_v['bearish']['trigger_fmt']} | **{sc_v['bearish']['target_fmt']}** | **{sc_v['bearish']['prob_fmt']}** | {esc(cats['bearish'])} |"
            )
        lines.append("")

        # Bloque 1.6: Tabla de Niveles y Rangos (sin barreras CUSUM 1 vela)
        lines.append("## 5. Niveles, Proyecciones y Cuartiles `P25/P75`")
        lines.append("")
        lines.append(
            "| Referencia / Horizonte | Nivel Central / Precio | Variación vs. Hoy | Banda Probable (`P25–P75`) | Banda Amplia (`P5–P95`) | Lectura |"
        )
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for row in views["levels_table"]:
            lines.append(
                f"| **{esc(row['label'])}** | {row['price_fmt']} | `{row['ret_fmt']}` | {row['iqr_fmt']} | {row['wide_fmt']} | {esc(row['note'])} |"
            )
        lines.append("")

        # Bloque 1.7: 3 Insights
        lines.append("## 6. Tres Ideas Clave")
        lines.append("")
        for idx_i, ins in enumerate(narrative["top_insights"][:3], start=1):
            lines.append(f"{idx_i}. **{esc(ins['title'])}:** {esc(ins['body'])}")
        lines.append("")
        lines.append("---")
        lines.append("")

        # ══════════════════════════════════════════════════════════════════════
        # PARTE 2: LABORATORIO TÉCNICO (3 Lentes)
        # ══════════════════════════════════════════════════════════════════════
        lines.append("## Laboratorio Técnico")
        lines.append("")

        # Bloque 2.1: Tabla de las 3 lentes con Curva-Precio R² y t+150
        lines.append("### 2.1 Diagnóstico de las 3 Lentes")
        lines.append("")
        lines.append(
            "| Lente | Rol Jerárquico | Estado Geométrico | Curva-Precio `R²` (MAPE) | SINDy `R²` | `t+150` | Auditoría OOS | Cobertura Cono `P25–P75` | Lectura |"
        )
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for lrow in views["lenses_table"]:
            lines.append(
                f"| **`{lrow['window']}` ({esc(lrow['color_name'])})** | {esc(lrow['role'])} | {esc(lrow['human_state'])} | "
                f"`{lrow['fit_r2_fmt']}` | `{lrow['r2_fmt']}` | {lrow['t150_fmt']} | `{lrow['oos_fmt']}` | {esc(lrow['cone_cal_fmt'])} | {esc(lrow['seal_fmt'])} |"
            )
        lines.append("")

        # Bloque 2.2: Contraste con el consenso web citado
        wc = narrative["web_consensus"]
        lines.append(f"### 2.2 Contraste con el Consenso Externo (`{esc(wc['convergence_grade'])}`)")
        lines.append("")
        lines.append(esc(wc["summary"]))
        lines.append("")
        if wc.get("sources"):
            lines.append("| Fuente | Fecha | Tesis / Niveles Reportados |")
            lines.append("| :--- | :--- | :--- |")
            for src in wc["sources"]:
                s_name = esc(src["source_name"])
                s_link = f"[{s_name}]({src['url']})" if src.get("url") else f"**{s_name}**"
                lines.append(f"| {s_link} | `{src['date']}` | {esc(src['stance'])} |")
            lines.append("")

        # Bloque 2.3: Los 3 Dashboards Técnicos (1000v, 2000v, 500v)
        lines.append("### 2.3 Paneles Técnicos de las 3 Lentes (`1000v` · `2000v` · `500v`)")
        lines.append("")
        lines.append("#### Lente Principal `1000v` (Ámbar)")
        lines.append(f"![Panel Técnico 1000v]({dash_1000_img_ref})")
        lines.append("")
        if dash_2000_img_ref:
            lines.append("#### Lente Contexto `2000v` (Cian)")
            lines.append(f"![Panel Técnico 2000v]({dash_2000_img_ref})")
            lines.append("")
        if dash_500_img_ref:
            lines.append("#### Sensor Táctico `500v` (Violeta)")
            lines.append(f"![Panel Técnico 500v]({dash_500_img_ref})")
            lines.append("")
        lines.append(f"- **Auditoría visual frente a JSON:** {esc(narrative['visual_discrepancies'])}")
        lines.append("")

        # Bloque 2.4: Ecuaciones SINDy de 1000v traducidas
        sv = views["sindy_view"]
        lines.append("### 2.4 Ecuaciones SINDy de `1000v` y Mecánica de Mercado")
        lines.append("")
        lines.append("```text")
        lines.append(f"d{sv['var_name']}/dt = {sv['eq_r']}")
        lines.append(f"dV/dt = {sv['eq_v']}")
        lines.append(f"Régimen activo: {sv['regime_span']} | R² = {sv['r2_fmt']} | Estabilidad: {sv['stability_human']}")
        lines.append("```")
        lines.append("")
        lines.append(esc(narrative["sindy_translation"]))
        lines.append("")

        # Bloque 2.5: Forense CUSUM histórico y catalizadores
        lines.append("### 2.5 Forense CUSUM Histórico y Catalizadores")
        lines.append("")
        lines.append("| Evento Detectado | Fecha Exacta | Precio | Magnitud / Tensión | Catalizador |")
        lines.append("| :--- | :--- | :--- | :--- | :--- |")
        for cev in views["cusum_events_view"]:
            lines.append(
                f"| **{esc(cev['kind'])}** | `{cev['date']}` | {cev['price_fmt']} | {esc(cev['metric_fmt'])} | {esc(cev['catalyst'])} |"
            )
        lines.append("")

        # Bloque 2.6: Límites
        lines.append("### 2.6 Límites de esta Lectura")
        lines.append("")
        for lim in narrative["reading_limits"]:
            lines.append(f"- {esc(lim)}")
        lines.append("")

        return "\n".join(lines)

    # ──────────────────────────────────────────────────────────────────────────
    # 6. Punto de Entrada Público (Usado tanto en Etapa 1 como en Etapa 2)
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def render_from_directory(
        cls,
        report_dir: Path,
        artifact_dir: Optional[Path] = None,
        artifact_slug: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Renderiza `<report_dir>/report.html` y `<report_dir>/analysis.md` leyendo únicamente
        los archivos persistidos del motor (`confluence.json`, `report_bundle.npz`,
        `lens_<W>/telemetry.json`) y, si existe, `<report_dir>/narrative.json`.
        """
        report_dir = Path(report_dir).resolve()
        conf_path = report_dir / "confluence.json"
        bundle_path = report_dir / "report_bundle.npz"
        if not conf_path.is_file():
            raise FileNotFoundError(f"No existe confluence.json en {report_dir}")
        if not bundle_path.is_file():
            raise FileNotFoundError(f"No existe report_bundle.npz en {report_dir}")

        with open(conf_path, "r", encoding="utf-8") as f:
            confluence = json.load(f)

        lenses_ordered = confluence["lenses_ordered"]
        ctx_win = int(lenses_ordered[0]["window_candles"])
        pri_win = int(lenses_ordered[1]["window_candles"])
        sen_win = int(lenses_ordered[2]["window_candles"])
        pri_tel_path = report_dir / f"lens_{pri_win}" / "telemetry.json"

        pri_tel: Optional[Dict[str, Any]] = None
        if pri_tel_path.is_file():
            with open(pri_tel_path, "r", encoding="utf-8") as f:
                pri_tel = json.load(f)

        dash_paths: Dict[int, Path] = {
            pri_win: report_dir / f"lens_{pri_win}" / "dashboard.png",
            ctx_win: report_dir / f"lens_{ctx_win}" / "dashboard.png",
            sen_win: report_dir / f"lens_{sen_win}" / "dashboard.png",
        }
        dash_b64: Dict[str, str] = {}
        for w_val, dp in dash_paths.items():
            if dp.is_file():
                with open(dp, "rb") as f:
                    dash_b64[str(w_val)] = base64.b64encode(f.read()).decode("ascii")

        dashboard_options = [
            {
                "key": str(pri_win),
                "label": f"Dashboard {pri_win}v (Ámbar · Principal)",
                "color": "#f59e0b",
                "b64": dash_b64.get(str(pri_win), ""),
                "available": str(pri_win) in dash_b64,
                "default": True,
            },
            {
                "key": str(ctx_win),
                "label": f"Dashboard {ctx_win}v (Cian · Contexto)",
                "color": "#22d3ee",
                "b64": dash_b64.get(str(ctx_win), ""),
                "available": str(ctx_win) in dash_b64,
                "default": False,
            },
            {
                "key": str(sen_win),
                "label": f"Dashboard {sen_win}v (Violeta · Sensor)",
                "color": "#c084fc",
                "b64": dash_b64.get(str(sen_win), ""),
                "available": str(sen_win) in dash_b64,
                "default": False,
            },
        ]

        narrative_path = report_dir / "narrative.json"
        user_nav: Optional[Dict[str, Any]] = None
        if narrative_path.is_file():
            with open(narrative_path, "r", encoding="utf-8") as f:
                user_nav = json.load(f)

        default_nav = cls._build_default_narrative(confluence, pri_tel)
        narrative, stage_label = cls._merge_narrative(default_nav, user_nav)

        with np.load(bundle_path, allow_pickle=False) as npz_data:
            bundle = {k: npz_data[k] for k in npz_data.files}

        hero_spec, hz_buttons, def_readout = cls._build_interactive_hero_spec(
            bundle=bundle, confluence=confluence, pri_tel=pri_tel
        )
        views_html = cls._build_structured_views(
            confluence=confluence, pri_tel=pri_tel, narrative=narrative, for_markdown=False
        )

        ds = confluence["metadata"]["dataset"]
        meta_ctx = {
            "ticker": ds["ticker"],
            "interval": ds["interval"],
            "calendar_mode": ds.get("calendar_mode", "Diario"),
            "last_close_fmt": cls._fmt_html_price(ds["last_close_price"]),
            "last_date": ds["last_candle_date"],
            "engine": confluence["metadata"]["engine"],
            "generated_at_utc": confluence["metadata"]["generated_at_utc"],
        }

        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(cls.TEMPLATE_DIR)),
            autoescape=jinja2.select_autoescape(["html", "xml"]),
        )
        template = env.get_template("report.html.j2")
        html_out = template.render(
            meta=meta_ctx,
            narrative_stage=stage_label,
            narrative=narrative,
            hierarchy=confluence["hierarchy_verdict"],
            regime_card=views_html["regime_card"],
            horizon_buttons=hz_buttons,
            cone_buttons=hero_spec["nav"]["cone_buttons"],
            default_horizon_readout=def_readout,
            scenarios_view=views_html["scenarios_view"],
            curves_table=views_html["curves_table"],
            levels_table=views_html["levels_table"],
            lenses_table=views_html["lenses_table"],
            dashboard_1000_b64=dash_b64.get(str(pri_win), ""),
            dashboard_options=dashboard_options,
            sindy_view=views_html["sindy_view"],
            cusum_events_view=views_html["cusum_events_view"],
            plotly_js=cls._get_plotly_js(),
            hero_plotly_json=json.dumps(hero_spec, ensure_ascii=False),
        )

        html_path = report_dir / "report.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_out)

        rel_dash_1000 = f"./lens_{pri_win}/dashboard.png"
        rel_dash_2000 = f"./lens_{ctx_win}/dashboard.png" if dash_paths[ctx_win].is_file() else None
        rel_dash_500 = f"./lens_{sen_win}/dashboard.png" if dash_paths[sen_win].is_file() else None
        html_uri = "file:///" + str(html_path).replace("\\", "/")
        md_out = cls._build_markdown_document(
            confluence=confluence,
            pri_tel=pri_tel,
            narrative=narrative,
            hero_img_ref="./hero.png",
            dash_1000_img_ref=rel_dash_1000,
            report_html_ref=html_uri,
            dash_2000_img_ref=rel_dash_2000,
            dash_500_img_ref=rel_dash_500,
        )
        md_path = report_dir / "analysis.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_out)

        result_paths: Dict[str, str] = {
            "narrative_stage": stage_label,
            "report_html": str(html_path),
            "analysis_md": str(md_path),
        }

        if artifact_dir is not None:
            art_dir = Path(artifact_dir).resolve()
            art_dir.mkdir(parents=True, exist_ok=True)
            slug = (
                artifact_slug
                or re.sub(r"[^a-z0-9]+", "_", ds["ticker"].lower()).strip("_")
                or "asset"
            )
            hero_src = report_dir / "hero.png"
            hero_dst = art_dir / f"{slug}_hero.png"
            if hero_src.is_file():
                shutil.copy2(hero_src, hero_dst)

            copied_dashes: Dict[int, Path] = {}
            for w_val, dp in dash_paths.items():
                if dp.is_file():
                    d_dst = art_dir / f"{slug}_dashboard_{w_val}v.png"
                    shutil.copy2(dp, d_dst)
                    copied_dashes[w_val] = d_dst

            html_dst = art_dir / f"{slug}_report.html"
            shutil.copy2(html_path, html_dst)

            hero_abs_str = "/" + str(hero_dst).replace("\\", "/").lstrip("/")
            dash_1000_abs = (
                "/" + str(copied_dashes[pri_win]).replace("\\", "/").lstrip("/")
                if pri_win in copied_dashes
                else rel_dash_1000
            )
            dash_2000_abs = (
                "/" + str(copied_dashes[ctx_win]).replace("\\", "/").lstrip("/")
                if ctx_win in copied_dashes
                else None
            )
            dash_500_abs = (
                "/" + str(copied_dashes[sen_win]).replace("\\", "/").lstrip("/")
                if sen_win in copied_dashes
                else None
            )
            md_art = cls._build_markdown_document(
                confluence=confluence,
                pri_tel=pri_tel,
                narrative=narrative,
                hero_img_ref=hero_abs_str,
                dash_1000_img_ref=dash_1000_abs,
                report_html_ref=html_uri,
                dash_2000_img_ref=dash_2000_abs,
                dash_500_img_ref=dash_500_abs,
            )
            md_art_dst = art_dir / f"{slug}_staged.md"
            with open(md_art_dst, "w", encoding="utf-8") as f:
                f.write(md_art)

            result_paths.update(
                {
                    "artifact_hero_png": str(hero_dst),
                    "artifact_dashboard_1000_png": str(copied_dashes.get(pri_win, "")),
                    "artifact_dashboard_2000_png": str(copied_dashes.get(ctx_win, "")),
                    "artifact_dashboard_500_png": str(copied_dashes.get(sen_win, "")),
                    "artifact_report_html": str(html_dst),
                    "artifact_staged_md": str(md_art_dst),
                }
            )

        return result_paths
