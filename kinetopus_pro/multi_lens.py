"""
Orquestador Multi-Lente (Estándar Geométrico Puro v0.3.1) — KineTopus-Analyst (`kinetopus_pro`).

Arquitectura jerárquica Multi-Lente v0.3.1:
  1. Descarga única inteligente (`10y` por defecto; escala a `max` cuando es necesario o cuando
     `--audit-oos` exige margen histórico adicional).
  2. Tres lentes cortadas de la misma serie (`2000v` Cian, `1000v` Ámbar, `500v` Violeta),
     calibradas de forma independiente en paralelo (`ProcessPoolExecutor`) con `np.float64` contiguo.
  3. Proyección `t+150` garantizada SIEMPRE en las 3 lentes simultáneamente, con cono EWMA
     calibrado y cuartiles `P25/P75`:
       - `1000v` (Ámbar) = Eje Principal y Escenarios ejecutivos (cono por defecto).
       - `2000v` (Cian) = Marea Estructural de fondo + trayectoria `t+150`.
       - `500v`  (Violeta) = Pulso Táctico + giros/quiebres recientes + trayectoria `t+150`.
  4. Walk-Forward OOS desactivado por defecto (solo informativo bajo `--audit-oos`); sin bloqueo
     por `R²` de SINDy ni banners de fallo OOS.
"""

from __future__ import annotations

import concurrent.futures
import contextlib
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from kinetopus_pro.engine_bridge import MarketLoader
from kinetopus_pro.headless_pipeline import (
    HeadlessRunResult,
    KinetopusAnalysisConfig,
    KinetopusHeadlessPipeline,
)

DEFAULT_MULTI_LENSES: Tuple[int, int, int] = (2000, 1000, 500)

LENS_HIERARCHY_SPECS: Tuple[Tuple[str, str], ...] = (
    ("CONTEXTO_FONDO", "Marea Estructural (2000v · Cian)"),
    ("PRINCIPAL_PREDICTIVA", "Eje Principal y Escenarios (1000v · Ámbar)"),
    ("SENSOR_ALERTA", "Pulso Táctico (500v · Violeta)"),
)

LENS_COLOR_SPECS: Dict[int, Dict[str, str]] = {
    2000: {"color_name": "Cian", "hex_dark": "#22d3ee", "hex_light": "#0891b2"},
    1000: {"color_name": "Ámbar", "hex_dark": "#f59e0b", "hex_light": "#d97706"},
    500: {"color_name": "Violeta", "hex_dark": "#c084fc", "hex_light": "#7c3aed"},
}


@dataclass
class MultiLensConfig:
    """Configuración unificada para una corrida Multi-Lente v0.3.1."""

    ticker: str = "BTC-USD"
    base_period: str = "10y"
    fallback_period: str = "max"
    interval: str = "1d"
    lenses: Tuple[int, ...] = DEFAULT_MULTI_LENSES
    horizon_steps: int = 150
    smooth_tol: float = 0.0050
    cusum_k: Optional[float] = None
    cusum_h: float = 5.0
    poly_degree: int = 1
    disable_norm: bool = False
    disable_returns: bool = False
    auto_tune: bool = True
    auto_rescue: bool = True
    audit_oos: bool = False
    wf_cuts: int = 0
    min_wf_effective_cuts: int = 5
    parallel: bool = True
    random_seed: int = 42


@dataclass
class LensSlotResult:
    """Resultado tipado de una ranura de lente dentro de la jerarquía."""

    window_candles: int
    role_code: str
    role_label: str
    available: bool
    status: str  # "OK" | "N/D"
    unavailable_reason: Optional[str]
    run_result: Optional[HeadlessRunResult]


@dataclass
class MultiLensRunResult:
    """Resultado completo de la corrida Multi-Lente en memoria."""

    confluence: Dict[str, Any]
    lens_slots: List[LensSlotResult]
    dates_full: List[str]
    raw_price_full: np.ndarray
    ohlc_full: Optional[Dict[str, np.ndarray]] = None


def _run_single_lens_worker(
    cfg_dict: Dict[str, Any], df_payload: pd.DataFrame
) -> HeadlessRunResult:
    """Worker top-level serializable para ejecutar una lente en `ProcessPoolExecutor`."""
    lens_cfg = KinetopusAnalysisConfig(**cfg_dict)
    pipeline = KinetopusHeadlessPipeline(lens_cfg)
    with contextlib.redirect_stdout(sys.stderr):
        return pipeline.run(df_override=df_payload)


class KinetopusMultiLensRunner:
    """Orquestador Multi-Lente v0.3.1 geométrico con proyección t+150 simultánea en las 3 lentes."""

    def __init__(self, config: Optional[MultiLensConfig] = None):
        self.cfg = config or MultiLensConfig()
        ordered = tuple(sorted((int(w) for w in self.cfg.lenses), reverse=True))
        if len(ordered) != 3:
            raise ValueError(
                f"La arquitectura jerárquica requiere exactamente 3 lentes (contexto, principal, alerta); recibido: {ordered}"
            )
        self.cfg.lenses = ordered

    @staticmethod
    def _extract_ohlc_contiguous(df: pd.DataFrame) -> Optional[Dict[str, np.ndarray]]:
        """Extrae arreglos OHLC `np.float64` `C_CONTIGUOUS` si existen las 4 columnas en `df`."""
        col_map = {str(c).strip().lower(): c for c in df.columns}
        required = ("open", "high", "low", "close")
        if not all(k in col_map for k in required):
            return None
        clean_df = df[[col_map[k] for k in required]].ffill().bfill()
        return {
            k: np.ascontiguousarray(clean_df[col_map[k]].values, dtype=np.float64)
            for k in required
        }

    @staticmethod
    def _detect_24_7_calendar(df: pd.DataFrame, ticker: str) -> bool:
        """Detecta si la serie opera en calendario continuo 24/7 (ej. cripto) o sesiones bursátiles."""
        sample_ts = None
        if isinstance(df.index, pd.DatetimeIndex):
            sample_ts = df.index[-min(90, len(df)) :]
        else:
            for col in ("Date", "Datetime", "date", "datetime"):
                if col in df.columns:
                    parsed = pd.to_datetime(df[col].iloc[-min(90, len(df)) :], errors="coerce").dropna()
                    if len(parsed) >= 10:
                        sample_ts = pd.DatetimeIndex(parsed)
                        break
        if sample_ts is not None and len(sample_ts) >= 14:
            weekend_bars = sum(1 for ts in sample_ts if ts.weekday() >= 5)
            return weekend_bars >= max(3, len(sample_ts) // 10)
        t_up = ticker.upper()
        return any(tag in t_up for tag in ("-USD", "-EUR", "USDT", "BTC", "ETH", "SOL"))

    @staticmethod
    def _standard_horizon_milestones(
        is_24_7: bool, horizon_steps: int
    ) -> List[Tuple[str, int]]:
        """Hitos estándar de la tabla ejecutiva: 1 semana, 1 mes, 3 meses y horizonte final `t+H`."""
        base = (
            [("1 semana", 7), ("1 mes", 30), ("3 meses", 90)]
            if is_24_7
            else [("1 semana", 5), ("1 mes", 21), ("3 meses", 63)]
        )
        filtered: List[Tuple[str, int]] = [
            (lbl, st) for lbl, st in base if 1 <= st < horizon_steps
        ]
        if horizon_steps >= 1:
            filtered.append((f"t+{horizon_steps}", int(horizon_steps)))
        return filtered

    def _load_smart_dataset(
        self, df_override: Optional[pd.DataFrame] = None
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Descarga una sola vez en `base_period` (`10y` por defecto) y escala automáticamente a
        `fallback_period` (`max`) cuando `10y` no ofrece margen suficiente para validar la lente
        mayor con Walk-Forward estricto de ventana completa.
        """
        cfg = self.cfg
        max_lens = max(cfg.lenses)
        eval_h_est = min(cfg.horizon_steps, 90)
        eff_wf_cuts = int(cfg.wf_cuts) if int(cfg.wf_cuts) > 0 else (10 if bool(cfg.audit_oos) else 0)
        min_desired_candles = max(
            max_lens + 690,
            max_lens + eval_h_est + max(600, eff_wf_cuts * 60),
        )

        if df_override is not None:
            df = df_override.copy()
            return df, {
                "source": "dataframe_override",
                "requested_period": "override",
                "effective_period_used": "override",
                "fallback_to_max_triggered": False,
                "min_desired_candles_for_full_wf": int(min_desired_candles),
                "downloaded_candles": int(len(df)),
            }

        df_base = MarketLoader.load_ticker_data(
            cfg.ticker, period=cfg.base_period, interval=cfg.interval
        )
        base_len = int(len(df_base))
        used_period = cfg.base_period
        fallback_triggered = False
        fallback_reason: Optional[str] = None

        if (
            cfg.fallback_period
            and cfg.fallback_period != cfg.base_period
            and base_len < min_desired_candles
        ):
            try:
                df_max = MarketLoader.load_ticker_data(
                    cfg.ticker, period=cfg.fallback_period, interval=cfg.interval
                )
                if len(df_max) > base_len:
                    df_base = df_max
                    used_period = cfg.fallback_period
                    fallback_triggered = True
                    fallback_reason = (
                        f"Periodo '{cfg.base_period}' entregó {base_len} velas (< {min_desired_candles} "
                        f"óptimas para lente {max_lens}v + Walk-Forward estricto); ampliado a '{cfg.fallback_period}' "
                        f"({len(df_max)} velas)."
                    )
            except Exception as exc:
                fallback_reason = (
                    f"Intento de respaldo '{cfg.fallback_period}' falló ({exc}); se conserva '{cfg.base_period}'."
                )

        return df_base, {
            "source": "yfinance",
            "requested_period": cfg.base_period,
            "effective_period_used": used_period,
            "initial_base_candles": base_len,
            "downloaded_candles": int(len(df_base)),
            "min_desired_candles_for_full_wf": int(min_desired_candles),
            "fallback_to_max_triggered": fallback_triggered,
            "fallback_note": fallback_reason,
        }

    @staticmethod
    def _lens_color_spec(window_candles: int) -> Dict[str, str]:
        """Devuelve color nominal por lente (>=1500v Cian, 750-1499v Ámbar, <750v Violeta)."""
        if window_candles in LENS_COLOR_SPECS:
            return LENS_COLOR_SPECS[window_candles]
        if window_candles >= 1500:
            return LENS_COLOR_SPECS[2000]
        if window_candles >= 750:
            return LENS_COLOR_SPECS[1000]
        return LENS_COLOR_SPECS[500]

    @classmethod
    def _extract_lens_summary(cls, slot: LensSlotResult) -> Dict[str, Any]:
        """Extrae el resumen geométrico de una lente para `confluence.json` (t+150 en las 3 lentes)."""
        color_spec = cls._lens_color_spec(slot.window_candles)
        if not slot.available or slot.run_result is None:
            return {
                "window_candles": slot.window_candles,
                "role_code": slot.role_code,
                "role_label": slot.role_label,
                "color_name": color_spec["color_name"],
                "hex_dark": color_spec["hex_dark"],
                "hex_light": color_spec["hex_light"],
                "status": "N/D",
                "available": False,
                "seal_passed": False,
                "seal_grade": "N/D",
                "seal_human": "No disponible",
                "emits_ranges_or_scenarios": False,
                "emits_t150_projection": False,
                "unavailable_reason": slot.unavailable_reason,
            }

        tel = slot.run_result.telemetry
        ds = tel["metadata"]["dataset"]
        cal = tel["calibration"]
        kpis = tel["executive_kpis"]
        wb = tel["white_box_physics"]
        seal_sum = tel["reliability_seal"]["double_seal_summary"]
        wf = tel["reliability_seal"]["mini_walk_forward_oos"]
        lb = tel["reliability_seal"]["ljung_box_whiteness"]
        kin = tel["geometry_and_phase_space"]["kinematics"]
        phs = tel["geometry_and_phase_space"]["phase_space"]
        curve_fit = tel["geometry_and_phase_space"].get("curve_price_fit", {})
        cus = tel["cusum_forensics"]
        cone = tel["forecast_cone"]
        h_reg = tel.get("human_regime", {})
        scen = tel.get("scenarios", {})

        checkpoints = cone.get("horizon_checkpoints", [])
        last_ckpt = checkpoints[-1] if checkpoints else {}
        t150_summary = {
            "step": int(last_ckpt.get("step", 150)),
            "horizon_step": str(last_ckpt.get("horizon_step", "t+150")),
            "center_price": last_ckpt.get("deterministic_price"),
            "center_return_pct": last_ckpt.get("deterministic_return_pct"),
            "p25_price": last_ckpt.get("mc_p25"),
            "p50_price": last_ckpt.get("mc_p50"),
            "p75_price": last_ckpt.get("mc_p75"),
            "p5_price": last_ckpt.get("mc_p5"),
            "p95_price": last_ckpt.get("mc_p95"),
            "cone_spread_p5_p95_pct": last_ckpt.get("cone_spread_p5_p95_pct"),
        }

        if t150_summary.get("center_return_pct") is not None:
            raw_dir = "ALCISTA" if float(t150_summary["center_return_pct"]) >= 0.0 else "BAJISTA"
        else:
            raw_dir = "ALCISTA" if kpis["directional_inertia"].startswith("ALCISTA") else "BAJISTA"

        seal_ok = bool(seal_sum["seal_passed"])

        summary_obj: Dict[str, Any] = {
            "window_candles": slot.window_candles,
            "role_code": slot.role_code,
            "role_label": slot.role_label,
            "color_name": color_spec["color_name"],
            "hex_dark": color_spec["hex_dark"],
            "hex_light": color_spec["hex_light"],
            "status": "OK",
            "available": True,
            "emits_ranges_or_scenarios": True,
            "emits_t150_projection": True,
            "window_start_date": ds["window_start_date"],
            "window_end_date": ds["last_candle_date"],
            "last_close_price": ds.get("last_close_price"),
            "calibrated_k": cal["effective_cusum_k"],
            "effective_smooth_tol": cal["effective_smooth_tol"],
            "autopilot_rescued": cal["autopilot_rescue"]["applied"],
            "geometric_fallback_used": bool(cone.get("geometric_fallback_used", False)),
            "raw_direction": raw_dir,
            "directional_inertia": kpis["directional_inertia"],
            "instant_velocity_pct_per_candle": kpis["instant_velocity_pct_per_candle"],
            "human_regime": h_reg,
            "quadrant": kin["quadrant"],
            "curve_now_price": kin.get("spline_nominal_price_now"),
            "price_vs_spline_gap_pct": kin["price_vs_spline_gap_pct"],
            "last_30c_mean_gap_pct": kin["last_30c_mean_gap_pct"],
            "curve_price_fit": curve_fit,
            "curve_price_r2": kpis.get("curve_price_r2", curve_fit.get("window_price_r2")),
            "curve_price_mape_pct": kpis.get("curve_price_mape_pct", curve_fit.get("window_price_mape_pct")),
            "curve_price_quality": kpis.get("curve_price_quality", curve_fit.get("fit_label")),
            "recent_velocity_reversals": kin.get("recent_velocity_reversals", []),
            "phase_topology": phs["topology_class"],
            "phase_rotation_sense": phs["rotation_sense"],
            "sindy_r2_score": kpis["sindy_r2_score"],
            "active_equations": wb["active_equations"],
            "cusum_semaphore": kpis["cusum_semaphore"],
            "cusum_tension_vs_h": kpis["cusum_tension_vs_h"],
            "cusum_tension_ratio": cus["current_tension"]["tension_ratio"],
            "cusum_window_max_peak": cus["window_max_tension_peak"],
            "active_regime_start_date": cus["active_regime_start_date"],
            "active_regime_candles": cus["active_regime_candles"],
            "macro_breaks": cus.get("macro_breaks", []),
            "invalidation_levels_1candle": cus["invalidation_levels_1candle"],
            "seal_passed": seal_ok,
            "geometric_valid": bool(seal_sum.get("geometric_valid", True)),
            "seal_grade": seal_sum["seal_grade"],
            "seal_human": h_reg.get(
                "seal_human",
                KinetopusHeadlessPipeline.humanize_code("seal_grade", seal_sum["seal_grade"]),
            ),
            "seal_reasons": seal_sum["reasons"],
            "oos_physics_class": wf.get("asset_physics_class"),
            "oos_consensus_hr_pct": wf.get("consensus_hit_ratio_pct"),
            "oos_effective_cuts": wf.get("effective_cuts", 0),
            "oos_min_required_cuts": wf.get("min_required_effective_cuts", 5),
            "oos_eval_horizon_candles": wf.get("eval_horizon_candles", 90),
            "cone_calibration": wf.get("cone_calibration"),
            "ljung_box_verdict": lb.get("verdict"),
            "ljung_box_spline_p": lb.get("spline_residuals", {}).get("reference_p_value"),
            "lens_confidence": kpis["overall_physical_confidence"],
            "trajectory_geometry": cone["trajectory_geometry"],
            "t150_summary": t150_summary,
            "horizon_checkpoints": checkpoints,
            "scenarios": scen,
        }
        return summary_obj

    @staticmethod
    def _build_tactical_sensor_alert(
        sensor: Dict[str, Any], primary: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Sintetiza alertas tácticas y pines visuales de `500v` sin emitir rangos ni objetivos."""
        if not sensor.get("available"):
            return {
                "status": "N/D",
                "has_active_alert": False,
                "summary": "Sensor táctico (500v) no disponible por historial corto.",
                "items": [],
                "pins": [],
            }

        alerts: List[str] = []
        pins: List[Dict[str, Any]] = []
        win_c = int(sensor.get("window_candles", 500))

        # 1. Quiebres CUSUM recientes dentro de las últimas 120 velas
        macro_breaks = sensor.get("macro_breaks", [])
        for brk in macro_breaks[-2:]:
            c_idx = int(brk.get("candle_idx", 0))
            candles_ago = max(0, (win_c - 1) - c_idx)
            if candles_ago <= 120:
                is_up_brk = "ALCISTA" in str(brk.get("break_type", ""))
                dir_word = "alcista" if is_up_brk else "bajista"
                b_date = str(brk.get("date", ""))[:10]
                b_price = float(brk.get("price_at_break", 0.0))
                alerts.append(
                    f"Quiebre CUSUM {dir_word} reciente el {b_date} (hace {candles_ago}v en {b_price:,.2f})"
                )
                pins.append(
                    {
                        "kind": "CUSUM_BREAK",
                        "direction": "UP" if is_up_brk else "DOWN",
                        "candles_ago": candles_ago,
                        "date": b_date,
                        "price": round(b_price, 4),
                        "label": f"Alerta 500v · Quiebre {dir_word} ({b_date})",
                    }
                )

        # 2. Giros recientes de velocidad (dr/dt = 0 en últimas 50 velas)
        revs = sensor.get("recent_velocity_reversals", [])
        if revs:
            last_rev = revs[-1]
            c_ago = int(last_rev.get("candles_ago", 999))
            if c_ago <= 50:
                is_up_turn = "ALZA" in str(last_rev.get("type", ""))
                turn_word = "giro táctico al alza" if is_up_turn else "techo táctico / giro a la baja"
                r_date = str(last_rev.get("date", ""))[:10]
                r_price = float(last_rev.get("price", 0.0))
                alerts.append(f"Detectado {turn_word} el {r_date} ({r_price:,.2f})")
                pins.append(
                    {
                        "kind": "VELOCITY_TURN",
                        "direction": "UP" if is_up_turn else "DOWN",
                        "candles_ago": c_ago,
                        "date": r_date,
                        "price": round(r_price, 4),
                        "label": f"Alerta 500v · {'Giro alza' if is_up_turn else 'Giro baja'} ({r_date})",
                    }
                )

        # 3. Tensión CUSUM acumulada en corto plazo
        t_ratio = float(sensor.get("cusum_tension_ratio", 0.0) or 0.0)
        t_vs_h = str(sensor.get("cusum_tension_vs_h", "0.00 / 5.0"))
        if t_ratio >= 0.60:
            alerts.append(f"Tensión CUSUM táctica elevada ({t_vs_h}, {t_ratio:.0%} del umbral)")

        # 4. Divergencia direccional frente a 1000v
        sen_hr = sensor.get("human_regime", {})
        pri_hr = primary.get("human_regime", {}) if primary.get("available") else {}
        sen_state = sen_hr.get("state_label") or str(sensor.get("raw_direction", "")).capitalize()
        pri_code = pri_hr.get("state_code", "")
        sen_code = sen_hr.get("state_code", "")

        if primary.get("available"):
            bull_codes = {"IMPULSO_ALCISTA", "ALCISTA_FRENANDO"}
            bear_codes = {"CORRECCION_BAJISTA", "CAIDA_FRENANDO_SUELO"}
            if (pri_code in bull_codes and sen_code in bear_codes) or (
                pri_code in bear_codes and sen_code in bull_codes
            ):
                alerts.append(
                    f"Divergencia táctica frente a 1000v: corto plazo en {sen_state.lower()}"
                )
            elif not pri_code and sensor.get("raw_direction") != primary.get("raw_direction"):
                alerts.append(
                    f"Divergencia de corto plazo ({sensor.get('raw_direction')}) frente a 1000v ({primary.get('raw_direction')})"
                )

        has_alert = len(alerts) > 0
        if has_alert:
            summary_txt = " · ".join(alerts[:2])
        else:
            summary_txt = (
                f"Sin alertas de ruptura ni giros bruscos recientes "
                f"({sen_state.lower()}, tensión CUSUM {t_vs_h})"
            )

        return {
            "status": "ALERTA_ACTIVA" if has_alert else "VIGILANCIA_TRANQUILA",
            "has_active_alert": has_alert,
            "sensor_state_label": sen_state,
            "seal_passed": bool(sensor.get("seal_passed", False)),
            "summary": summary_txt,
            "items": alerts,
            "pins": pins,
        }

    @classmethod
    def _synthesize_fixed_hierarchy(
        cls,
        summaries: Sequence[Dict[str, Any]],
        horizon_milestones: Optional[Sequence[Tuple[str, int]]] = None,
    ) -> Dict[str, Any]:
        """
        Sintetiza la Arquitectura Geométrica Multi-Lente v0.3.1:
          - Las 3 lentes (`2000v` Cian, `1000v` Ámbar, `500v` Violeta) proyectan siempre `t+150`
            con cono EWMA calibrado y cuartiles `P25/P75`.
          - `1000v` (Ámbar) actúa como eje principal de rangos ejecutivos y escenarios (solo cede al
            pulso `500v` en activos ultra-jóvenes < 1000 velas).
          - Sin bloqueo `"Sin escenario predictivo validado hoy"` ni vetos por SINDy R².
        """
        contexto = summaries[0]
        principal = summaries[1]
        sensor = summaries[2]
        milestones = list(
            horizon_milestones
            or [("1 semana", 5), ("1 mes", 21), ("3 meses", 63), ("t+150", 150)]
        )

        notes: List[str] = []

        # 1. Lectura de Contexto de Fondo (2000v · Cian)
        ctx_hr = contexto.get("human_regime", {})
        if not contexto.get("available"):
            context_2000v = f"No disponible (historial < {contexto['window_candles']} velas)"
            bg_legacy = f"N/D (< {contexto['window_candles']}v)"
            notes.append(
                f"Marea estructural ({contexto['window_candles']}v · Cian) no disponible por edad del activo."
            )
        else:
            full_c = ctx_hr.get("full_label") or str(contexto.get("raw_direction", "Estable"))
            c_r2 = float(contexto.get("curve_price_r2") or 0.0)
            c_t150 = contexto.get("t150_summary", {})
            ret_c = c_t150.get("center_return_pct")
            ret_c_str = f", t+150 {float(ret_c):+.1f}%" if isinstance(ret_c, (int, float)) else ""
            hr_c = contexto.get("oos_consensus_hr_pct")
            oos_note = f", OOS {hr_c:.0f}%" if isinstance(hr_c, (int, float)) else ""
            context_2000v = f"{full_c} (Curva-Precio R²={c_r2:.2f}{ret_c_str}{oos_note})"
            bg_legacy = f"{contexto.get('raw_direction')} ({contexto.get('seal_grade')})"
            notes.append(
                f"Marea estructural ({contexto['window_candles']}v · Cian): {full_c} | "
                f"Ajuste Curva-Precio R²={c_r2:.3f}, MAPE={float(contexto.get('curve_price_mape_pct') or 0.0):.2f}%{ret_c_str}."
            )

        # 2. Sensor de Pulso Táctico (500v · Violeta)
        tactical_alert = cls._build_tactical_sensor_alert(sensor, principal if principal.get("available") else sensor)
        if sensor.get("available"):
            s_t150 = sensor.get("t150_summary", {})
            s_ret = s_t150.get("center_return_pct")
            s_ret_str = f" · t+150 {float(s_ret):+.1f}%" if isinstance(s_ret, (int, float)) else ""
            notes.append(
                f"Pulso táctico ({sensor['window_candles']}v · Violeta): {tactical_alert['summary']}{s_ret_str}."
            )
        else:
            notes.append(f"Pulso táctico ({sensor['window_candles']}v · Violeta): {tactical_alert['summary']}.")

        # 3. Eje Principal (1000v · Ámbar, con respaldo en 500v solo si el activo tiene <1000v)
        anchor = principal if principal.get("available") else (sensor if sensor.get("available") else contexto)
        anchor_ok = bool(anchor.get("available"))
        anchor_hr = anchor.get("human_regime", {})

        # Rangos por lente (para selector interactivo de cono y comparativa multipunto)
        ranges_by_lens: Dict[str, List[Dict[str, Any]]] = {}
        curves_comparison: List[Dict[str, Any]] = []
        for s_item in summaries:
            w_key = str(s_item["window_candles"])
            t150_s = s_item.get("t150_summary", {})
            c_fit = s_item.get("curve_price_fit", {})
            s_hr = s_item.get("human_regime", {})
            curves_comparison.append(
                {
                    "window_candles": int(s_item["window_candles"]),
                    "color_name": s_item.get("color_name", ""),
                    "role_code": s_item.get("role_code", ""),
                    "role_label": s_item.get("role_label", ""),
                    "available": bool(s_item.get("available")),
                    "curve_now_price": s_item.get("curve_now_price"),
                    "gap_now_pct": s_item.get("price_vs_spline_gap_pct"),
                    "last_30c_mean_gap_pct": s_item.get("last_30c_mean_gap_pct"),
                    "curve_price_r2": c_fit.get("window_price_r2", s_item.get("curve_price_r2")),
                    "curve_price_mape_pct": c_fit.get("window_price_mape_pct", s_item.get("curve_price_mape_pct")),
                    "curve_price_quality": c_fit.get("fit_label", s_item.get("curve_price_quality")),
                    "state_label": s_hr.get("state_label", s_item.get("raw_direction", "N/D")),
                    "full_label": s_hr.get("full_label", s_item.get("raw_direction", "N/D")),
                    "t150_center_price": t150_s.get("center_price"),
                    "t150_center_return_pct": t150_s.get("center_return_pct"),
                    "t150_p25_price": t150_s.get("p25_price"),
                    "t150_p50_price": t150_s.get("p50_price"),
                    "t150_p75_price": t150_s.get("p75_price"),
                    "t150_p5_price": t150_s.get("p5_price"),
                    "t150_p95_price": t150_s.get("p95_price"),
                    "cusum_tension_vs_h": s_item.get("cusum_tension_vs_h"),
                    "geometric_fallback_used": bool(s_item.get("geometric_fallback_used", False)),
                }
            )
            if not s_item.get("available"):
                ranges_by_lens[w_key] = []
                continue
            chk_map = {
                int(c["step"]): c
                for c in s_item.get("horizon_checkpoints", [])
                if "step" in c
            }
            lens_rows: List[Dict[str, Any]] = []
            for lbl_h, st_h in milestones:
                c_row = chk_map.get(int(st_h))
                if c_row and "mc_p25" in c_row:
                    lens_rows.append(
                        {
                            "horizon_label": lbl_h,
                            "horizon_step": f"t+{st_h}",
                            "step": int(st_h),
                            "center_price": c_row.get("deterministic_price"),
                            "center_return_pct": c_row.get("deterministic_return_pct"),
                            "p25_price": c_row.get("mc_p25"),
                            "p50_price": c_row.get("mc_p50"),
                            "p75_price": c_row.get("mc_p75"),
                            "p5_price": c_row.get("mc_p5"),
                            "p95_price": c_row.get("mc_p95"),
                        }
                    )
            ranges_by_lens[w_key] = lens_rows

        executive_ranges: List[Dict[str, Any]] = []
        if anchor_ok:
            predictive_validated = True
            primary_label = anchor_hr.get("full_label") or (
                f"Tendencia {str(anchor.get('raw_direction', '')).lower()}"
            )
            executive_banner = primary_label
            unvalidated_reason: Optional[str] = None
            executive_ranges = list(ranges_by_lens.get(str(anchor["window_candles"]), []))
            executive_scenarios = anchor.get("scenarios") or {
                "available": False,
                "validated": True,
            }

            # Confianza física global basada en geometría Curva-Precio, armonía 3 lentes y tensión CUSUM
            anchor_fit = anchor.get("curve_price_fit", {})
            fit_r2 = float(anchor_fit.get("window_price_r2", anchor.get("curve_price_r2") or 0.0) or 0.0)
            fit_mape = float(anchor_fit.get("window_price_mape_pct", anchor.get("curve_price_mape_pct") or 0.0) or 0.0)
            t_pri = float(anchor.get("cusum_tension_ratio", 0.0) or 0.0)

            avail_dirs = [s.get("raw_direction") for s in summaries if s.get("available")]
            all_aligned = len(avail_dirs) >= 2 and len(set(avail_dirs)) == 1
            ctx_contradicts = (
                bool(contexto.get("available"))
                and contexto.get("raw_direction") != anchor.get("raw_direction")
                and anchor_hr.get("state_code") != "LATERAL_DIGESTION"
            )

            score_pts = 0
            if fit_r2 >= 0.85:
                score_pts += 2
            elif fit_r2 >= 0.65:
                score_pts += 1

            if all_aligned:
                score_pts += 1
            elif ctx_contradicts:
                score_pts -= 1

            if t_pri <= 0.60:
                score_pts += 1
            elif t_pri > 0.85:
                score_pts -= 1

            if anchor.get("geometric_fallback_used"):
                score_pts -= 1

            oos_cls = anchor.get("oos_physics_class")
            if oos_cls == "COHERENTE_INERCIAL":
                score_pts += 1
            elif oos_cls in ("EXOGENO_FUNDAMENTALISTA", "INESTABLE_O_RUIDO_EXTREMO"):
                score_pts -= 1

            if t_pri > 0.85:
                global_confidence = "BAJA"
                pattern = "GEOMETRIA_CON_TENSION_CRITICA"
            elif score_pts >= 3 and not ctx_contradicts:
                global_confidence = "ALTA"
                pattern = "ARMONIA_3_LENTES_Y_AJUSTE_ALTO"
            elif score_pts >= 1:
                global_confidence = "MEDIA"
                pattern = (
                    "EJE_1000V_CONTRA_MAREA_2000V"
                    if ctx_contradicts
                    else "ENFOQUE_GEOMETRICO_MODERADO"
                )
            else:
                global_confidence = "BAJA"
                pattern = "DIVERGENCIA_Y_RUIDO_ELEVADO"

            a_t150 = anchor.get("t150_summary", {})
            ret_a = a_t150.get("center_return_pct")
            ret_a_str = f"{float(ret_a):+.1f}%" if isinstance(ret_a, (int, float)) else "N/D"
            notes.append(
                f"Eje principal ({anchor['window_candles']}v · Ámbar): {primary_label} | "
                f"Curva-Precio R²={fit_r2:.3f}, MAPE={fit_mape:.2f}%, centro t+150={ret_a_str}."
            )
        else:
            predictive_validated = False
            executive_banner = "Historial insuficiente para lectura multi-lente"
            unvalidated_reason = "No hay velas suficientes en ninguna lente del activo."
            primary_label = executive_banner
            executive_scenarios = {"available": False, "validated": False, "base": None, "bullish": None, "bearish": None}
            global_confidence = "BAJA"
            pattern = "HISTORIAL_INSUFICIENTE"

        raw_dirs_str = " / ".join(
            f"{s['window_candles']}v ({s.get('color_name', '')}): "
            f"{s.get('human_regime', {}).get('state_label', s.get('raw_direction'))} "
            f"(Fit R²={float(s.get('curve_price_r2') or 0.0):.2f})"
            if s.get("available")
            else f"{s['window_candles']}v: N/D"
            for s in summaries
        )

        return {
            "hierarchy_rule": (
                "ARQUITECTURA_GEOMETRICA_3_LENTES_V31 "
                "(3 lentes t+150: 1000v Ámbar=Eje Principal y Escenarios, 2000v Cian=Marea, 500v Violeta=Pulso Táctico)"
            ),
            "anchor_window_candles": int(anchor["window_candles"]) if anchor_ok else 1000,
            "predictive_scenario_validated": predictive_validated,
            "executive_banner": executive_banner,
            "unvalidated_reason": unvalidated_reason,
            "primary_lens_1000v": primary_label,
            "context_tide_2000v": context_2000v,
            "tactical_alert_500v": tactical_alert["summary"],
            "tactical_sensor_detail": tactical_alert,
            "background_trend_2000v": bg_legacy,
            "alignment_pattern": pattern,
            "global_physical_confidence": global_confidence,
            "executive_ranges": executive_ranges,
            "ranges_by_lens": ranges_by_lens,
            "curves_comparison": curves_comparison,
            "executive_scenarios": executive_scenarios,
            "raw_lenses_snapshot": raw_dirs_str,
            "rationale": notes,
        }

    def run(self, df_override: Optional[pd.DataFrame] = None) -> MultiLensRunResult:
        """Ejecuta las 3 lentes sobre una sola descarga y sintetiza `MultiLensRunResult`."""
        t0 = time.perf_counter()
        cfg = self.cfg

        df_full, download_meta = self._load_smart_dataset(df_override=df_override)
        dates_full = KinetopusHeadlessPipeline._extract_iso_dates(df_full)
        ohlc_full = self._extract_ohlc_contiguous(df_full)
        is_24_7 = self._detect_24_7_calendar(df_full, cfg.ticker)
        milestones = self._standard_horizon_milestones(is_24_7, cfg.horizon_steps)

        _, _, raw_price_full, _ = MarketLoader.prepare_quant_input(
            df_full.copy(), disable_norm=cfg.disable_norm, disable_returns=cfg.disable_returns
        )
        n_total = len(df_full)

        pending_tasks: List[Tuple[int, Dict[str, Any]]] = []
        slots: List[LensSlotResult] = []

        for idx, win in enumerate(cfg.lenses):
            role_code, role_label = LENS_HIERARCHY_SPECS[idx]
            if n_total < win:
                slots.append(
                    LensSlotResult(
                        window_candles=win,
                        role_code=role_code,
                        role_label=role_label,
                        available=False,
                        status="N/D",
                        unavailable_reason=(
                            f"Historial disponible ({n_total} velas) menor que las {win} velas requeridas por la lente."
                        ),
                        run_result=None,
                    )
                )
            else:
                lens_cfg = KinetopusAnalysisConfig(
                    ticker=cfg.ticker,
                    period=download_meta["effective_period_used"],
                    interval=cfg.interval,
                    context_window=win,
                    horizon_steps=cfg.horizon_steps,
                    smooth_tol=cfg.smooth_tol,
                    cusum_k=cfg.cusum_k,
                    cusum_h=cfg.cusum_h,
                    poly_degree=cfg.poly_degree,
                    disable_norm=cfg.disable_norm,
                    disable_returns=cfg.disable_returns,
                    auto_tune=cfg.auto_tune,
                    auto_rescue=cfg.auto_rescue,
                    audit_oos=cfg.audit_oos,
                    wf_cuts=cfg.wf_cuts,
                    strict_wf_window=True,
                    min_wf_effective_cuts=cfg.min_wf_effective_cuts,
                    in_process_fft=True,
                    random_seed=cfg.random_seed,
                )
                slots.append(
                    LensSlotResult(
                        window_candles=win,
                        role_code=role_code,
                        role_label=role_label,
                        available=True,
                        status="OK",
                        unavailable_reason=None,
                        run_result=None,
                    )
                )
                pending_tasks.append((idx, asdict(lens_cfg)))

        if len(pending_tasks) > 1 and cfg.parallel:
            max_w = min(3, len(pending_tasks))
            with concurrent.futures.ProcessPoolExecutor(max_workers=max_w) as pool:
                fut_map = {
                    pool.submit(_run_single_lens_worker, c_dict, df_full): slot_idx
                    for slot_idx, c_dict in pending_tasks
                }
                for fut in concurrent.futures.as_completed(fut_map):
                    s_idx = fut_map[fut]
                    slots[s_idx].run_result = fut.result()
        else:
            for slot_idx, c_dict in pending_tasks:
                slots[slot_idx].run_result = _run_single_lens_worker(c_dict, df_full)

        summaries = [self._extract_lens_summary(sl) for sl in slots]
        hierarchy = self._synthesize_fixed_hierarchy(summaries, horizon_milestones=milestones)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        last_price = float(raw_price_full[-1]) if len(raw_price_full) > 0 else 0.0
        confluence: Dict[str, Any] = {
            "metadata": {
                "engine": "KineTopus Multi-Lens Engine v3.1",
                "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "total_runtime_ms": round(elapsed_ms, 2),
                "config": asdict(cfg),
                "download": download_meta,
                "dataset": {
                    "ticker": cfg.ticker,
                    "interval": cfg.interval,
                    "calendar_mode": "24/7 (continuo)" if is_24_7 else "Bursátil (~252 sesiones/año)",
                    "is_24_7_calendar": bool(is_24_7),
                    "has_ohlc": bool(ohlc_full is not None),
                    "horizon_milestones": [
                        {"label": lbl, "step": int(st)} for lbl, st in milestones
                    ],
                    "total_downloaded_candles": n_total,
                    "first_date_downloaded": dates_full[0] if dates_full else None,
                    "last_candle_date": dates_full[-1] if dates_full else None,
                    "last_close_price": round(last_price, 4),
                },
            },
            "hierarchy_verdict": hierarchy,
            "lenses_summary": {str(s["window_candles"]): s for s in summaries},
            "lenses_ordered": summaries,
        }

        return MultiLensRunResult(
            confluence=confluence,
            lens_slots=slots,
            dates_full=dates_full,
            raw_price_full=np.ascontiguousarray(raw_price_full, dtype=np.float64),
            ohlc_full=ohlc_full,
        )
