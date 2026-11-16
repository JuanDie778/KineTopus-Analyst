"""
Exportador de Indicador Portable B2B, Widget SVG Embebible (`< 35 KB`) y TradingView Pine Script v5 (`v0.4.0` — Hito 4).

Transforma una corrida existente de KineTopus (`confluence.json` + `report_bundle.npz` opcional)
sin recalcular física en tres artefactos ultraligeros para distribución externa:
  1. `indicator_feed.json` (`kinetopus.indicator.v1`, ~5–12 KB)
  2. `widget.html` (`< 35 KB`, SVG puro responsivo Oscuro/Claro sin `plotly.min.js`)
  3. `indicator.pine` (Pine Script v5 `overlay=true` listo para pegar en TradingView)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import jinja2
import numpy as np


ROLE_COLOR_DEFAULTS: Dict[str, Tuple[str, str, str]] = {
    "CONTEXTO_FONDO": ("Cian", "#22d3ee", "#0891b2"),
    "PRINCIPAL_PREDICTIVA": ("Ámbar", "#f59e0b", "#d97706"),
    "SENSOR_ALERTA": ("Violeta", "#c084fc", "#9333ea"),
}


class KinetopusIndicatorExporter:
    """Exportador determinista de feeds JSON B2B, widgets SVG `< 35 KB` y overlays Pine Script v5."""

    SCHEMA_VERSION = "kinetopus.indicator.v1"
    TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

    @staticmethod
    def _safe_float(val: Any, default: Optional[float] = None) -> Optional[float]:
        if val is None:
            return default
        try:
            f = float(val)
            return f if np.isfinite(f) else default
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _fmt_price(val: Optional[float], currency: str = "$") -> str:
        if val is None or not np.isfinite(float(val)):
            return "N/D"
        v = float(val)
        av = abs(v)
        if av >= 1000.0:
            return f"{currency}{v:,.0f}"
        if av >= 10.0:
            return f"{currency}{v:,.2f}"
        return f"{currency}{v:,.4f}"

    @classmethod
    def _extract_t150_from_lens(
        cls,
        lens_obj: Dict[str, Any],
        confluence: Dict[str, Any],
        last_close: float,
    ) -> Dict[str, Optional[float]]:
        """Obtiene el resumen `t+150` de una lente con respaldo limpio para corridas v0.3.0."""
        t150 = lens_obj.get("t150_summary")
        if isinstance(t150, dict) and t150.get("center_price") is not None:
            return {
                "center_price": cls._safe_float(t150.get("center_price")),
                "center_return_pct": cls._safe_float(t150.get("center_return_pct"), 0.0),
                "p25_price": cls._safe_float(t150.get("p25_price")),
                "p50_price": cls._safe_float(t150.get("p50_price")),
                "p75_price": cls._safe_float(t150.get("p75_price")),
                "p5_price": cls._safe_float(t150.get("p5_price")),
                "p95_price": cls._safe_float(t150.get("p95_price")),
            }

        w_str = str(lens_obj.get("window_candles", ""))
        ranges_by_lens = confluence.get("hierarchy_verdict", {}).get("ranges_by_lens", {})
        if isinstance(ranges_by_lens, dict) and isinstance(ranges_by_lens.get(w_str), list) and ranges_by_lens[w_str]:
            last_r = ranges_by_lens[w_str][-1]
            return {
                "center_price": cls._safe_float(last_r.get("center_price")),
                "center_return_pct": cls._safe_float(last_r.get("center_return_pct"), 0.0),
                "p25_price": cls._safe_float(last_r.get("p25_price")),
                "p50_price": cls._safe_float(last_r.get("p50_price")),
                "p75_price": cls._safe_float(last_r.get("p75_price")),
                "p5_price": cls._safe_float(last_r.get("p5_price")),
                "p95_price": cls._safe_float(last_r.get("p95_price")),
            }

        checkpoints = lens_obj.get("horizon_checkpoints")
        if isinstance(checkpoints, list) and checkpoints:
            cp = checkpoints[-1]
            c_price = cls._safe_float(cp.get("deterministic_price", cp.get("center_price")))
            c_ret = cls._safe_float(cp.get("deterministic_return_pct", cp.get("center_return_pct")))
            if c_ret is None and c_price is not None and last_close > 0:
                c_ret = (c_price / last_close - 1.0) * 100.0
            return {
                "center_price": c_price,
                "center_return_pct": c_ret if c_ret is not None else 0.0,
                "p25_price": cls._safe_float(cp.get("mc_p25", cp.get("p25_price"))),
                "p50_price": cls._safe_float(cp.get("mc_p50", cp.get("p50_price"))),
                "p75_price": cls._safe_float(cp.get("mc_p75", cp.get("p75_price"))),
                "p5_price": cls._safe_float(cp.get("mc_p5", cp.get("p5_price"))),
                "p95_price": cls._safe_float(cp.get("mc_p95", cp.get("p95_price"))),
            }

        return {
            "center_price": last_close if last_close > 0 else None,
            "center_return_pct": 0.0,
            "p25_price": None,
            "p50_price": None,
            "p75_price": None,
            "p5_price": None,
            "p95_price": None,
        }

    @classmethod
    def _build_compact_series(
        cls,
        report_dir: Path,
        confluence: Dict[str, Any],
        lenses_list: List[Dict[str, Any]],
        tail_candles: int = 120,
        proj_stride: int = 5,
    ) -> Dict[str, Any]:
        """Extrae series compactas (`tail_candles` + `t+150` muestreado) desde `report_bundle.npz` o JSON."""
        ds = confluence.get("metadata", {}).get("dataset", {})
        cfg = confluence.get("metadata", {}).get("config", {})
        last_close = float(ds.get("last_close_price") or 0.0)
        last_date = str(ds.get("last_candle_date", ""))[:10]
        h_max = max(1, int(cfg.get("horizon_steps", 150)))
        stride = max(1, int(proj_stride))

        bundle_path = report_dir / "report_bundle.npz"
        if bundle_path.is_file():
            with np.load(bundle_path, allow_pickle=False) as npz:
                files = set(npz.files)
                n_full = int(npz["n_full"][0])
                h_start = int(npz["h_start"][0])
                dates_hist = [str(d)[:10] for d in npz["dates_hist"]]
                close_hist = np.asarray(npz["close_hist"], dtype=np.float64)
                n_hist = len(close_hist)
                keep = min(max(10, int(tail_candles)), n_hist)
                t0 = n_hist - keep

                dates_tail = dates_hist[t0:]
                close_tail = [round(float(v), 4) for v in close_hist[t0:]]

                curves_out: Dict[str, Dict[str, Any]] = {}
                proj_steps = sorted({0, *range(stride, h_max, stride), h_max})
                proj_centers: Dict[str, List[float]] = {}
                cone_1000: Dict[str, List[float]] = {}

                for prefix, role_code in (
                    ("ctx", "CONTEXTO_FONDO"),
                    ("pri", "PRINCIPAL_PREDICTIVA"),
                    ("sen", "SENSOR_ALERTA"),
                ):
                    if f"{prefix}_avail" not in files or int(npz[f"{prefix}_avail"][0]) != 1:
                        continue
                    w_val = int(npz[f"{prefix}_win"][0])
                    w_key = str(w_val)
                    nom = np.asarray(npz[f"{prefix}_nom"], dtype=np.float64)
                    trigs = [int(t) for t in npz[f"{prefix}_trigs"].tolist()]
                    det = np.asarray(npz[f"{prefix}_det"], dtype=np.float64)
                    mc = np.asarray(npz[f"{prefix}_mc"], dtype=np.float64)

                    # Alinear curva de longitud len(nom) con la cola close_hist[t0:]
                    off_in_hist = (n_full - len(nom)) - h_start
                    vals_tail: List[Optional[float]] = []
                    for i_tail in range(keep):
                        idx_hist = t0 + i_tail
                        idx_nom = idx_hist - off_in_hist
                        if 0 <= idx_nom < len(nom) and np.isfinite(nom[idx_nom]):
                            vals_tail.append(round(float(nom[idx_nom]), 4))
                        else:
                            vals_tail.append(None)

                    brk_tail: List[int] = []
                    for tr in sorted(set(trigs)):
                        if 0 < tr < len(nom):
                            idx_tail = (tr + off_in_hist) - t0
                            if 0 < idx_tail < keep:
                                brk_tail.append(int(idx_tail))

                    curves_out[w_key] = {
                        "values": vals_tail,
                        "break_indices_tail": brk_tail,
                    }

                    if len(det) > 0:
                        sampled_det: List[float] = []
                        for st in proj_steps:
                            if st == 0:
                                sampled_det.append(round(last_close, 4))
                            else:
                                k = min(st - 1, len(det) - 1)
                                sampled_det.append(round(float(det[k]), 4))
                        proj_centers[w_key] = sampled_det

                        if role_code == "PRINCIPAL_PREDICTIVA" and mc.shape == (5, len(det)):
                            for row_idx, band_key in ((0, "p5"), (1, "p25"), (3, "p75"), (4, "p95")):
                                band_vals: List[float] = []
                                for st in proj_steps:
                                    if st == 0:
                                        band_vals.append(round(last_close, 4))
                                    else:
                                        k = min(st - 1, mc.shape[1] - 1)
                                        band_vals.append(round(float(mc[row_idx, k]), 4))
                                cone_1000[band_key] = band_vals

                # Si alguna lente disponible (p. ej. 500v en corridas v0.3.0) no estaba en el bundle, respaldar su proyección
                for l_item in lenses_list:
                    w_key = str(l_item["window_candles"])
                    if l_item["available"] and w_key not in proj_centers and l_item.get("t150_center_price") is not None:
                        tgt = float(l_item["t150_center_price"])
                        proj_centers[w_key] = [
                            round(last_close + (tgt - last_close) * (st / float(h_max)), 4)
                            for st in proj_steps
                        ]

                return {
                    "tail_candles": keep,
                    "horizon_steps": h_max,
                    "proj_stride": stride,
                    "dates_tail": dates_tail,
                    "close_tail": close_tail,
                    "curves": curves_out,
                    "projections": {
                        "steps": proj_steps,
                        "center": proj_centers,
                        "cone_1000v": cone_1000,
                    },
                }

        # Respaldo determinista si no existe `report_bundle.npz`
        proj_steps = [0, h_max]
        proj_centers_fb: Dict[str, List[float]] = {}
        cone_fb: Dict[str, List[float]] = {}
        curves_fb: Dict[str, Dict[str, Any]] = {}
        for l_item in lenses_list:
            if not l_item["available"]:
                continue
            w_key = str(l_item["window_candles"])
            c_now = float(l_item.get("curve_now_price") or last_close)
            curves_fb[w_key] = {"values": [round(c_now, 4)], "break_indices_tail": []}
            if l_item.get("t150_center_price") is not None:
                proj_centers_fb[w_key] = [round(last_close, 4), round(float(l_item["t150_center_price"]), 4)]
            if l_item["role_code"] == "PRINCIPAL_PREDICTIVA":
                if l_item.get("p25_price") is not None and l_item.get("p75_price") is not None:
                    cone_fb["p25"] = [round(last_close, 4), round(float(l_item["p25_price"]), 4)]
                    cone_fb["p75"] = [round(last_close, 4), round(float(l_item["p75_price"]), 4)]

        return {
            "tail_candles": 1,
            "horizon_steps": h_max,
            "proj_stride": h_max,
            "dates_tail": [last_date],
            "close_tail": [round(last_close, 4)],
            "curves": curves_fb,
            "projections": {
                "steps": proj_steps,
                "center": proj_centers_fb,
                "cone_1000v": cone_fb,
            },
        }

    @classmethod
    def build_indicator_feed(
        cls,
        report_dir: Path,
        include_series: bool = True,
        tail_candles: int = 120,
        proj_stride: int = 5,
    ) -> Dict[str, Any]:
        """Construye el contrato JSON B2B `kinetopus.indicator.v1` a partir de `report_dir`."""
        rep = Path(report_dir).resolve()
        conf_path = rep / "confluence.json"
        if not conf_path.is_file():
            raise FileNotFoundError(f"No existe confluence.json en {rep}")

        with open(conf_path, "r", encoding="utf-8") as f:
            confluence = json.load(f)

        ds = confluence.get("metadata", {}).get("dataset", {})
        cfg = confluence.get("metadata", {}).get("config", {})
        hier = confluence.get("hierarchy_verdict", {})

        ticker = str(ds.get("ticker", "UNKNOWN"))
        interval = str(ds.get("interval", cfg.get("interval", "1d")))
        cal_mode = str(ds.get("calendar_mode", "Diario"))
        last_date = str(ds.get("last_candle_date", ""))[:10]
        last_close = float(ds.get("last_close_price") or 0.0)
        h_steps = int(cfg.get("horizon_steps", 150))

        # Titular cualitativo si existe narrative.json, o titular determinista limpio
        narrative_headline = ""
        nav_path = rep / "narrative.json"
        if nav_path.is_file():
            try:
                with open(nav_path, "r", encoding="utf-8") as f:
                    nav_obj = json.load(f)
                narrative_headline = str(nav_obj.get("headline", "")).strip()
            except Exception:
                narrative_headline = ""

        banner = str(hier.get("executive_banner", "Régimen geométrico activo"))
        confidence = str(hier.get("global_physical_confidence", "MEDIA"))
        if not narrative_headline:
            narrative_headline = (
                f"{ticker} cotiza en {cls._fmt_price(last_close)} bajo lectura '{banner}' "
                f"(confianza física {confidence})."
            )

        # Extraer las 3 lentes en orden jerárquico [2000v, 1000v, 500v]
        raw_lenses: List[Dict[str, Any]] = []
        if isinstance(confluence.get("lenses_ordered"), list) and confluence["lenses_ordered"]:
            raw_lenses = list(confluence["lenses_ordered"])
        elif isinstance(confluence.get("lenses_summary"), dict):
            raw_lenses = sorted(
                confluence["lenses_summary"].values(),
                key=lambda x: int(x.get("window_candles", 0)),
                reverse=True,
            )

        lenses_clean: List[Dict[str, Any]] = []
        for l_raw in raw_lenses:
            win = int(l_raw.get("window_candles", 0))
            role_code = str(l_raw.get("role_code", "PRINCIPAL_PREDICTIVA"))
            def_cname, def_dark, def_light = ROLE_COLOR_DEFAULTS.get(
                role_code, ("Ámbar", "#f59e0b", "#d97706")
            )
            avail = bool(l_raw.get("available", False))
            hr = l_raw.get("human_regime") or {}
            gap_pct = cls._safe_float(l_raw.get("price_vs_spline_gap_pct"), 0.0) or 0.0

            curve_now = cls._safe_float(l_raw.get("curve_now_price"))
            if curve_now is None and avail and last_close > 0 and (1.0 + gap_pct / 100.0) > 1e-6:
                curve_now = last_close / (1.0 + gap_pct / 100.0)

            t150 = cls._extract_t150_from_lens(l_raw, confluence, last_close) if avail else {}

            state_lbl = str(
                hr.get("state_label")
                or l_raw.get("state_label")
                or ("No disponible" if not avail else "Régimen activo")
            )
            full_lbl = str(hr.get("full_label") or state_lbl)

            lenses_clean.append(
                {
                    "window_candles": win,
                    "role_code": role_code,
                    "role_label": str(l_raw.get("role_label", f"Lente {win}v")),
                    "color_name": str(l_raw.get("color_name") or def_cname),
                    "hex_dark": str(l_raw.get("hex_dark") or def_dark),
                    "hex_light": str(l_raw.get("hex_light") or def_light),
                    "available": avail,
                    "state_code": str(hr.get("state_code", "N_D")),
                    "state_label": state_lbl,
                    "position_code": str(hr.get("position_code", "EN_LINEA")),
                    "full_label": full_lbl,
                    "curve_now_price": round(curve_now, 4) if curve_now is not None else None,
                    "gap_now_pct": round(gap_pct, 2),
                    "curve_price_r2": cls._safe_float(l_raw.get("curve_price_r2")),
                    "curve_price_mape_pct": cls._safe_float(l_raw.get("curve_price_mape_pct")),
                    "curve_price_quality": l_raw.get("curve_price_quality"),
                    "t150_center_price": (
                        round(float(t150["center_price"]), 4)
                        if t150.get("center_price") is not None
                        else None
                    ),
                    "t150_return_pct": (
                        round(float(t150["center_return_pct"]), 2)
                        if t150.get("center_return_pct") is not None
                        else None
                    ),
                    "p25_price": (
                        round(float(t150["p25_price"]), 4) if t150.get("p25_price") is not None else None
                    ),
                    "p50_price": (
                        round(float(t150["p50_price"]), 4) if t150.get("p50_price") is not None else None
                    ),
                    "p75_price": (
                        round(float(t150["p75_price"]), 4) if t150.get("p75_price") is not None else None
                    ),
                    "p5_price": (
                        round(float(t150["p5_price"]), 4) if t150.get("p5_price") is not None else None
                    ),
                    "p95_price": (
                        round(float(t150["p95_price"]), 4) if t150.get("p95_price") is not None else None
                    ),
                    "cusum_tension_ratio": round(float(l_raw.get("cusum_tension_ratio") or 0.0), 3),
                    "cusum_tension_vs_h": str(l_raw.get("cusum_tension_vs_h", "0.00 / 5.0")),
                    "active_regime_start_date": l_raw.get("active_regime_start_date"),
                    "sindy_r2_score": cls._safe_float(l_raw.get("sindy_r2_score")),
                }
            )

        exec_sc = hier.get("executive_scenarios") or {}
        base_sc = exec_sc.get("base") or {}
        bull_sc = exec_sc.get("bullish") or {}
        bear_sc = exec_sc.get("bearish") or {}
        iqr_prob = cls._safe_float(
            exec_sc.get("prob_stay_within_iqr_pct", exec_sc.get("prob_stay_within_cusum_channel_pct")),
            50.0,
        )

        scenarios_clean = {
            "horizon_step": str(exec_sc.get("horizon_step", f"t+{h_steps}")),
            "prob_stay_within_iqr_pct": round(float(iqr_prob or 50.0), 1),
            "base": {
                "name": str(base_sc.get("name", "Escenario Central")),
                "trigger_condition": str(base_sc.get("trigger_condition", "")),
                "trigger_low_price": cls._safe_float(base_sc.get("trigger_low_price")),
                "trigger_high_price": cls._safe_float(base_sc.get("trigger_high_price")),
                "target_price": cls._safe_float(base_sc.get("target_price")),
                "target_return_pct": cls._safe_float(base_sc.get("target_return_pct"), 0.0),
                "touch_probability_pct": cls._safe_float(base_sc.get("touch_probability_pct")),
            },
            "bullish": {
                "name": str(bull_sc.get("name", "Expansión Alcista (P75)")),
                "trigger_condition": str(bull_sc.get("trigger_condition", "")),
                "trigger_price": cls._safe_float(bull_sc.get("trigger_price")),
                "target_price": cls._safe_float(bull_sc.get("target_price")),
                "target_return_pct": cls._safe_float(bull_sc.get("target_return_pct"), 0.0),
                "touch_probability_pct": cls._safe_float(bull_sc.get("touch_probability_pct")),
            },
            "bearish": {
                "name": str(bear_sc.get("name", "Soporte Bajista (P25)")),
                "trigger_condition": str(bear_sc.get("trigger_condition", "")),
                "trigger_price": cls._safe_float(bear_sc.get("trigger_price")),
                "target_price": cls._safe_float(bear_sc.get("target_price")),
                "target_return_pct": cls._safe_float(bear_sc.get("target_return_pct"), 0.0),
                "touch_probability_pct": cls._safe_float(bear_sc.get("touch_probability_pct")),
            },
        }

        tac_pins = list((hier.get("tactical_sensor_detail") or {}).get("pins") or [])

        feed: Dict[str, Any] = {
            "schema_version": cls.SCHEMA_VERSION,
            "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "asset": {
                "ticker": ticker,
                "interval": interval,
                "calendar_mode": cal_mode,
                "last_date": last_date,
                "last_close_price": round(last_close, 4),
                "horizon_steps": h_steps,
            },
            "verdict": {
                "human_banner": banner,
                "global_physical_confidence": confidence,
                "alignment_pattern": str(hier.get("alignment_pattern", "GEOMETRICO")),
                "anchor_window_candles": int(hier.get("anchor_window_candles", 1000)),
                "narrative_headline": narrative_headline,
            },
            "lenses": lenses_clean,
            "scenarios": scenarios_clean,
            "tactical_pins_500v": tac_pins,
        }

        if include_series:
            feed["series"] = cls._build_compact_series(
                report_dir=rep,
                confluence=confluence,
                lenses_list=lenses_clean,
                tail_candles=tail_candles,
                proj_stride=proj_stride,
            )

        return feed

    @classmethod
    def build_pine_script_overlay(cls, feed: Dict[str, Any]) -> str:
        """Genera un overlay TradingView Pine Script v5 (`overlay=true`) con las 3 curvas y P25/P75."""
        asset = feed["asset"]
        verdict = feed["verdict"]
        ticker = asset["ticker"]
        interval = asset["interval"]
        last_date = asset["last_date"]
        last_close = float(asset["last_close_price"])
        h_steps = int(asset.get("horizon_steps", 150))
        conf_lbl = verdict["global_physical_confidence"]

        by_role = {l["role_code"]: l for l in feed.get("lenses", []) if l.get("available")}
        l2000 = by_role.get("CONTEXTO_FONDO", {})
        l1000 = by_role.get("PRINCIPAL_PREDICTIVA", {})
        l500 = by_role.get("SENSOR_ALERTA", {})

        c2000 = float(l2000.get("curve_now_price") or last_close)
        c1000 = float(l1000.get("curve_now_price") or last_close)
        c500 = float(l500.get("curve_now_price") or last_close)

        t2000 = float(l2000.get("t150_center_price") or c2000)
        t1000 = float(l1000.get("t150_center_price") or c1000)
        t500 = float(l500.get("t150_center_price") or c500)

        p75 = float(l1000.get("p75_price") or max(t1000, last_close * 1.05))
        p25 = float(l1000.get("p25_price") or min(t1000, last_close * 0.95))

        def _pine_str(txt: Any) -> str:
            return str(txt or "N/D").replace('"', "'")

        def _fmt_r2(val: Any) -> str:
            return f"{float(val):.2f}" if isinstance(val, (int, float)) else "N/D"

        def _fmt_pct(val: Any) -> str:
            return f"{float(val):+.1f}%" if isinstance(val, (int, float)) else "N/D"

        w2000 = int(l2000.get("window_candles", 2000))
        w1000 = int(l1000.get("window_candles", 1000))
        w500 = int(l500.get("window_candles", 500))

        lines = [
            "//@version=5",
            f'// KineTopus-Analyst v0.4.0 — Multi-Lens Regime Overlay para {ticker} ({interval} · Corte {last_date})',
            f'indicator("KineTopus Multi-Lens [{ticker} · {last_date}]", shorttitle="KineTopus 3L", overlay=true, max_lines_count=50, max_labels_count=50)',
            "",
            'show_levels = input.bool(true, "Mostrar niveles de curvas vigentes (2000v / 1000v / 500v)")',
            'show_rays   = input.bool(true, "Proyectar vectores futuros t+' + str(h_steps) + '")',
            'show_cone   = input.bool(true, "Sombrear corredor probable P25-P75 (1000v)")',
            'show_hud    = input.bool(true, "Mostrar panel resumen KineTopus")',
            "",
            "// Niveles geométricos deterministas exportados por KineTopus-Analyst",
            f"float kt_last_close = {last_close:.6f}",
            f"float kt_c{w2000}     = {c2000:.6f}",
            f"float kt_c{w1000}     = {c1000:.6f}",
            f"float kt_c{w500}      = {c500:.6f}",
            f"float kt_t{w2000}     = {t2000:.6f}",
            f"float kt_t{w1000}     = {t1000:.6f}",
            f"float kt_t{w500}      = {t500:.6f}",
            f"float kt_p75        = {p75:.6f}",
            f"float kt_p25        = {p25:.6f}",
            f"int   kt_h_steps    = {h_steps}",
            "",
            f'plot(show_levels ? kt_c{w2000} : na, "Curva {w2000}v (Cian · Marea)", color=color.new(#22d3ee, 15), linewidth=2)',
            f'plot(show_levels ? kt_c{w1000} : na, "Curva {w1000}v (Ámbar · Principal)", color=color.new(#f59e0b, 0), linewidth=2)',
            f'plot(show_levels ? kt_c{w500} : na, "Curva {w500}v (Violeta · Pulso)", color=color.new(#c084fc, 15), linewidth=1)',
            'p_hi = plot(show_cone ? kt_p75 : na, "Cuartil Superior P75 (1000v)", color=color.new(#10b981, 45), style=plot.style_linebr)',
            'p_lo = plot(show_cone ? kt_p25 : na, "Cuartil Inferior P25 (1000v)", color=color.new(#f43f5e, 45), style=plot.style_linebr)',
            'fill(p_hi, p_lo, color=color.new(#f59e0b, 88), title="Corredor Probable P25-P75 (1000v)")',
            "",
            "var line ln_2000 = na",
            "var line ln_1000 = na",
            "var line ln_500  = na",
            "var line ln_p75  = na",
            "var line ln_p25  = na",
            "var linefill lf_iqr = na",
            "",
            "if barstate.islast and show_rays",
            "    line.delete(ln_2000)",
            "    line.delete(ln_1000)",
            "    line.delete(ln_500)",
            "    line.delete(ln_p75)",
            "    line.delete(ln_p25)",
            "    linefill.delete(lf_iqr)",
            f"    ln_2000 := line.new(bar_index, close, bar_index + kt_h_steps, kt_t{w2000}, color=#22d3ee, width=2, style=line.style_dashed)",
            f"    ln_1000 := line.new(bar_index, close, bar_index + kt_h_steps, kt_t{w1000}, color=#f59e0b, width=2, style=line.style_dashed)",
            f"    ln_500  := line.new(bar_index, close, bar_index + kt_h_steps, kt_t{w500}, color=#c084fc, width=2, style=line.style_dotted)",
            "    if show_cone",
            "        ln_p75 := line.new(bar_index, close, bar_index + kt_h_steps, kt_p75, color=color.new(#10b981, 35), width=1, style=line.style_dotted)",
            "        ln_p25 := line.new(bar_index, close, bar_index + kt_h_steps, kt_p25, color=color.new(#f43f5e, 35), width=1, style=line.style_dotted)",
            "        lf_iqr := linefill.new(ln_p75, ln_p25, color.new(#f59e0b, 84))",
            "",
            "var table hud = table.new(position.top_right, 5, 5, bgcolor=color.new(#0f172a, 12), border_color=#334155, border_width=1)",
            "if barstate.islast and show_hud",
            f'    table.cell(hud, 0, 0, "KineTopus · {ticker}", text_color=color.white, text_size=size.small)',
            '    table.cell(hud, 1, 0, "Estado", text_color=#94a3b8, text_size=size.small)',
            '    table.cell(hud, 2, 0, "Brecha", text_color=#94a3b8, text_size=size.small)',
            '    table.cell(hud, 3, 0, "Fit R²", text_color=#94a3b8, text_size=size.small)',
            f'    table.cell(hud, 4, 0, "t+{h_steps}", text_color=#94a3b8, text_size=size.small)',
            f'    table.cell(hud, 0, 1, "{w2000}v Cian", text_color=#22d3ee, text_size=size.tiny)',
            f'    table.cell(hud, 1, 1, "{_pine_str(l2000.get("state_label"))}", text_color=color.white, text_size=size.tiny)',
            f'    table.cell(hud, 2, 1, "{_fmt_pct(l2000.get("gap_now_pct"))}", text_color=color.white, text_size=size.tiny)',
            f'    table.cell(hud, 3, 1, "{_fmt_r2(l2000.get("curve_price_r2"))}", text_color=color.white, text_size=size.tiny)',
            f'    table.cell(hud, 4, 1, "{_fmt_pct(l2000.get("t150_return_pct"))}", text_color=color.white, text_size=size.tiny)',
            f'    table.cell(hud, 0, 2, "{w1000}v Ámbar", text_color=#f59e0b, text_size=size.tiny)',
            f'    table.cell(hud, 1, 2, "{_pine_str(l1000.get("state_label"))}", text_color=color.white, text_size=size.tiny)',
            f'    table.cell(hud, 2, 2, "{_fmt_pct(l1000.get("gap_now_pct"))}", text_color=color.white, text_size=size.tiny)',
            f'    table.cell(hud, 3, 2, "{_fmt_r2(l1000.get("curve_price_r2"))}", text_color=color.white, text_size=size.tiny)',
            f'    table.cell(hud, 4, 2, "{_fmt_pct(l1000.get("t150_return_pct"))}", text_color=color.white, text_size=size.tiny)',
            f'    table.cell(hud, 0, 3, "{w500}v Violeta", text_color=#c084fc, text_size=size.tiny)',
            f'    table.cell(hud, 1, 3, "{_pine_str(l500.get("state_label"))}", text_color=color.white, text_size=size.tiny)',
            f'    table.cell(hud, 2, 3, "{_fmt_pct(l500.get("gap_now_pct"))}", text_color=color.white, text_size=size.tiny)',
            f'    table.cell(hud, 3, 3, "{_fmt_r2(l500.get("curve_price_r2"))}", text_color=color.white, text_size=size.tiny)',
            f'    table.cell(hud, 4, 3, "{_fmt_pct(l500.get("t150_return_pct"))}", text_color=color.white, text_size=size.tiny)',
            f'    table.cell(hud, 0, 4, "Confianza {conf_lbl}", text_color=#fbbf24, text_size=size.tiny)',
            f'    table.cell(hud, 1, 4, "P25: {cls._fmt_price(p25)}", text_color=#f43f5e, text_size=size.tiny)',
            f'    table.cell(hud, 2, 4, "Centro: {cls._fmt_price(t1000)}", text_color=#fbbf24, text_size=size.tiny)',
            f'    table.cell(hud, 3, 4, "P75: {cls._fmt_price(p75)}", text_color=#10b981, text_size=size.tiny)',
            f'    table.cell(hud, 4, 4, "{last_date}", text_color=#94a3b8, text_size=size.tiny)',
            "",
        ]
        return "\n".join(lines)

    @staticmethod
    def _build_svg_segmented_path(
        xs: Sequence[float],
        ys: Sequence[Optional[float]],
        break_indices: Sequence[int],
        map_y: Any,
    ) -> str:
        """Construye un `d` de `<path>` SVG cortando limpiamente en `None` y en `break_indices`."""
        brk_set = set(int(b) for b in break_indices)
        cmds: List[str] = []
        pen_down = False
        for idx, (xv, yv) in enumerate(zip(xs, ys)):
            if yv is None or not np.isfinite(float(yv)):
                pen_down = False
                continue
            if idx in brk_set:
                pen_down = False
            yp = map_y(float(yv))
            cmd = "L" if pen_down else "M"
            cmds.append(f"{cmd}{xv:.1f},{yp:.1f}")
            pen_down = True
        return " ".join(cmds)

    @classmethod
    def render_embed_widget(
        cls,
        feed: Dict[str, Any],
        alerts_payload: Optional[Dict[str, Any]] = None,
        default_theme: str = "dark",
    ) -> str:
        """Renderiza `widget.html` (`< 35 KB`, SVG puro sin JS externo) listo para `<iframe>`."""
        theme_clean = "light" if str(default_theme).lower().strip() == "light" else "dark"
        asset = feed["asset"]
        verdict = feed["verdict"]
        scenarios = feed["scenarios"]
        lenses = feed.get("lenses", [])
        series = feed.get("series") or {}

        dates_tail: List[str] = list(series.get("dates_tail") or [asset["last_date"]])
        close_tail: List[float] = [float(v) for v in (series.get("close_tail") or [asset["last_close_price"]])]
        n_tail = max(1, len(close_tail))
        h_steps = max(1, int(series.get("horizon_steps", asset.get("horizon_steps", 150))))
        curves_map: Dict[str, Dict[str, Any]] = series.get("curves") or {}
        proj_obj: Dict[str, Any] = series.get("projections") or {}
        proj_steps: List[int] = [int(s) for s in (proj_obj.get("steps") or [0, h_steps])]
        proj_centers: Dict[str, List[float]] = proj_obj.get("center") or {}
        cone_1000: Dict[str, List[float]] = proj_obj.get("cone_1000v") or {}

        # Geometría del lienzo SVG
        svg_w, svg_h = 760, 245
        pad_l, pad_r, pad_t, pad_b = 14.0, 92.0, 14.0, 22.0
        plot_w = svg_w - pad_l - pad_r
        plot_h = svg_h - pad_t - pad_b
        hist_share = 0.62
        x_today = pad_l + plot_w * hist_share
        x_end = pad_l + plot_w
        y_bottom = pad_t + plot_h

        if n_tail > 1:
            xs_hist = [pad_l + (i / float(n_tail - 1)) * (x_today - pad_l) for i in range(n_tail)]
        else:
            xs_hist = [x_today]

        xs_proj = [x_today + (st / float(h_steps)) * (x_end - x_today) for st in proj_steps]

        # Recolectar valores Y para escalado limpio sin recortes
        y_pool: List[float] = list(close_tail)
        for c_entry in curves_map.values():
            for v in c_entry.get("values", []):
                if v is not None and np.isfinite(float(v)):
                    y_pool.append(float(v))
        for p_arr in proj_centers.values():
            y_pool.extend(float(v) for v in p_arr if np.isfinite(float(v)))
        for b_key in ("p25", "p75"):
            if b_key in cone_1000:
                y_pool.extend(float(v) for v in cone_1000[b_key] if np.isfinite(float(v)))

        if not y_pool:
            y_pool = [float(asset["last_close_price"])]
        y_min_raw, y_max_raw = min(y_pool), max(y_pool)
        span = y_max_raw - y_min_raw
        pad_y = span * 0.09 if span > 0 else max(abs(y_max_raw) * 0.05, 1.0)
        ylo, yhi = y_min_raw - pad_y, y_max_raw + pad_y

        def _map_y(val: float) -> float:
            clamped = min(max(float(val), ylo), yhi)
            ratio = (clamped - ylo) / max(1e-9, (yhi - ylo))
            return y_bottom - ratio * plot_h

        # Ticks horizontales Y (4 niveles)
        y_ticks = []
        for frac in (0.15, 0.45, 0.75, 0.95):
            yv = ylo + frac * (yhi - ylo)
            y_ticks.append({"y": round(_map_y(yv), 1), "label": cls._fmt_price(yv)})

        price_points = " ".join(f"{x:.1f},{_map_y(y):.1f}" for x, y in zip(xs_hist, close_tail))

        # Identificar claves de ventana por rol
        by_role = {l["role_code"]: l for l in lenses}
        w_ctx = str((by_role.get("CONTEXTO_FONDO") or {}).get("window_candles", 2000))
        w_pri = str((by_role.get("PRINCIPAL_PREDICTIVA") or {}).get("window_candles", 1000))
        w_sen = str((by_role.get("SENSOR_ALERTA") or {}).get("window_candles", 500))

        def _curve_path_for(w_key: str) -> str:
            c_obj = curves_map.get(w_key)
            if not c_obj:
                return ""
            return cls._build_svg_segmented_path(
                xs=xs_hist,
                ys=c_obj.get("values", []),
                break_indices=c_obj.get("break_indices_tail", []),
                map_y=_map_y,
            )

        def _proj_pts_for(w_key: str) -> str:
            arr = proj_centers.get(w_key)
            if not arr or len(arr) != len(xs_proj):
                return ""
            return " ".join(f"{x:.1f},{_map_y(y):.1f}" for x, y in zip(xs_proj, arr))

        def _poly_cone(lo_key: str, hi_key: str) -> str:
            lo_arr = cone_1000.get(lo_key)
            hi_arr = cone_1000.get(hi_key)
            if not lo_arr or not hi_arr or len(lo_arr) != len(xs_proj) or len(hi_arr) != len(xs_proj):
                return ""
            upper = [f"{x:.1f},{_map_y(y):.1f}" for x, y in zip(xs_proj, hi_arr)]
            lower = [f"{x:.1f},{_map_y(y):.1f}" for x, y in reversed(list(zip(xs_proj, lo_arr)))]
            return " ".join(upper + lower)

        # Etiquetas derechas anti-colisión
        raw_tags: List[Dict[str, Any]] = []
        if "p75" in cone_1000 and cone_1000["p75"]:
            raw_tags.append(
                {
                    "y": _map_y(cone_1000["p75"][-1]),
                    "text": f"P75 {cls._fmt_price(cone_1000['p75'][-1])}",
                    "color": "var(--bull)",
                }
            )
        if w_pri in proj_centers and proj_centers[w_pri]:
            raw_tags.append(
                {
                    "y": _map_y(proj_centers[w_pri][-1]),
                    "text": f"{w_pri}v {cls._fmt_price(proj_centers[w_pri][-1])}",
                    "color": "var(--amber)",
                }
            )
        if "p25" in cone_1000 and cone_1000["p25"]:
            raw_tags.append(
                {
                    "y": _map_y(cone_1000["p25"][-1]),
                    "text": f"P25 {cls._fmt_price(cone_1000['p25'][-1])}",
                    "color": "var(--bear)",
                }
            )
        if w_ctx in proj_centers and proj_centers[w_ctx]:
            raw_tags.append(
                {
                    "y": _map_y(proj_centers[w_ctx][-1]),
                    "text": f"{w_ctx}v {cls._fmt_price(proj_centers[w_ctx][-1])}",
                    "color": "var(--cyan)",
                }
            )
        if w_sen in proj_centers and proj_centers[w_sen]:
            raw_tags.append(
                {
                    "y": _map_y(proj_centers[w_sen][-1]),
                    "text": f"{w_sen}v {cls._fmt_price(proj_centers[w_sen][-1])}",
                    "color": "var(--violet)",
                }
            )

        raw_tags.sort(key=lambda item: item["y"])
        min_gap = 11.5
        for idx in range(1, len(raw_tags)):
            if raw_tags[idx]["y"] - raw_tags[idx - 1]["y"] < min_gap:
                raw_tags[idx]["y"] = raw_tags[idx - 1]["y"] + min_gap
        if raw_tags and raw_tags[-1]["y"] > y_bottom + 4:
            shift = raw_tags[-1]["y"] - (y_bottom + 4)
            for item in raw_tags:
                item["y"] = max(pad_t + 6, item["y"] - shift)
        for item in raw_tags:
            item["y"] = round(float(item["y"]) + 3.0, 1)

        svg_ctx = {
            "width": svg_w,
            "height": svg_h,
            "pad_l": round(pad_l, 1),
            "pad_t": round(pad_t, 1),
            "x_today": round(x_today, 1),
            "x_end": round(x_end, 1),
            "y_bottom": round(y_bottom, 1),
            "tail_candles": n_tail,
            "horizon_steps": h_steps,
            "first_tail_date": dates_tail[0] if dates_tail else "",
            "y_ticks": y_ticks,
            "price_points": price_points,
            "curve_2000_path": _curve_path_for(w_ctx),
            "curve_1000_path": _curve_path_for(w_pri),
            "curve_500_path": _curve_path_for(w_sen),
            "proj_2000_points": _proj_pts_for(w_ctx),
            "proj_1000_points": _proj_pts_for(w_pri),
            "proj_500_points": _proj_pts_for(w_sen),
            "cone_iqr_points": _poly_cone("p25", "p75"),
            "cone_outer_points": _poly_cone("p5", "p95"),
            "right_tags": raw_tags,
        }

        win_class_map = {
            "CONTEXTO_FONDO": "2000",
            "PRINCIPAL_PREDICTIVA": "1000",
            "SENSOR_ALERTA": "500",
        }
        lenses_cards = []
        for l_item in lenses:
            r2_v = l_item.get("curve_price_r2")
            ret_v = float(l_item.get("t150_return_pct") or 0.0)
            gap_v = float(l_item.get("gap_now_pct") or 0.0)
            lenses_cards.append(
                {
                    "win_class": win_class_map.get(l_item["role_code"], "1000"),
                    "window_candles": l_item["window_candles"],
                    "color_name": l_item["color_name"],
                    "state_label": l_item["state_label"],
                    "full_label": l_item["full_label"],
                    "r2_fmt": f"{float(r2_v):.2f}" if isinstance(r2_v, (int, float)) else "N/D",
                    "gap_fmt": f"{gap_v:+.1f}%",
                    "t150_ret": ret_v,
                    "t150_ret_fmt": f"{ret_v:+.1f}%" if l_item.get("t150_return_pct") is not None else "N/D",
                }
            )

        base_sc = scenarios["base"]
        bull_sc = scenarios["bullish"]
        bear_sc = scenarios["bearish"]
        fmt_ctx = {
            "last_close": cls._fmt_price(asset["last_close_price"]),
            "iqr_prob": f"{float(scenarios.get('prob_stay_within_iqr_pct') or 50.0):.0f}%",
            "base_target": cls._fmt_price(base_sc.get("target_price")),
            "base_ret": f"{float(base_sc.get('target_return_pct') or 0.0):+.1f}%",
            "bull_target": cls._fmt_price(bull_sc.get("target_price")),
            "bull_ret": f"{float(bull_sc.get('target_return_pct') or 0.0):+.1f}%",
            "bull_prob": (
                f"{float(bull_sc['touch_probability_pct']):.0f}%"
                if bull_sc.get("touch_probability_pct") is not None
                else "N/D"
            ),
            "bear_target": cls._fmt_price(bear_sc.get("target_price")),
            "bear_ret": f"{float(bear_sc.get('target_return_pct') or 0.0):+.1f}%",
            "bear_prob": (
                f"{float(bear_sc['touch_probability_pct']):.0f}%"
                if bear_sc.get("touch_probability_pct") is not None
                else "N/D"
            ),
        }

        alerts_count = 0
        if isinstance(alerts_payload, dict):
            alerts_count = int(alerts_payload.get("total_active_alerts", 0))

        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(cls.TEMPLATE_DIR)),
            autoescape=jinja2.select_autoescape(["html", "xml"]),
        )
        tpl = env.get_template("widget.html.j2")
        return tpl.render(
            default_theme=theme_clean,
            schema_version=cls.SCHEMA_VERSION,
            asset=asset,
            verdict=verdict,
            lenses_cards=lenses_cards,
            fmt=fmt_ctx,
            svg=svg_ctx,
            alerts_count=alerts_count,
        )

    @classmethod
    def export_from_directory(
        cls,
        report_dir: Path,
        alerts_payload: Optional[Dict[str, Any]] = None,
        tail_candles: int = 120,
        proj_stride: int = 5,
    ) -> Dict[str, str]:
        """Genera y guarda `indicator_feed.json`, `indicator.pine` y `widget.html` en `report_dir`."""
        rep = Path(report_dir).resolve()
        if alerts_payload is None and (rep / "alerts.json").is_file():
            try:
                with open(rep / "alerts.json", "r", encoding="utf-8") as f:
                    alerts_payload = json.load(f)
            except Exception:
                alerts_payload = None

        feed = cls.build_indicator_feed(
            report_dir=rep,
            include_series=True,
            tail_candles=tail_candles,
            proj_stride=proj_stride,
        )
        pine_code = cls.build_pine_script_overlay(feed)
        widget_html = cls.render_embed_widget(feed, alerts_payload=alerts_payload, default_theme="dark")

        feed_path = rep / "indicator_feed.json"
        pine_path = rep / "indicator.pine"
        widget_path = rep / "widget.html"

        with open(feed_path, "w", encoding="utf-8") as f:
            json.dump(feed, f, separators=(",", ":"), ensure_ascii=False)
        with open(pine_path, "w", encoding="utf-8") as f:
            f.write(pine_code)
        with open(widget_path, "w", encoding="utf-8") as f:
            f.write(widget_html)

        return {
            "indicator_feed_json": str(feed_path),
            "indicator_pine": str(pine_path),
            "widget_html": str(widget_path),
        }
