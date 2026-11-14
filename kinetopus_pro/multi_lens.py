"""
Orquestador Multi-Lente (Hito 2) — KineTopus-Analyst (`kinetopus_pro`).

Implementa las decisiones de diseño acordadas:
  1. Una sola descarga inteligente (`10y`, escalando automáticamente a `max` cuando `10y` no deja
     margen suficiente para validar la lente larga con Walk-Forward estricto).
  2. Tres lentes cortadas de la misma serie (`2000v` / `1000v` / `500v`), calibradas de forma
     independiente en paralelo (`ProcessPoolExecutor`) con `np.float64` contiguo.
  3. Si un activo no alcanza las velas requeridas para una lente -> estado `N/D` (jamás se inventa).
  4. Jerarquía fija sin votos ni promociones:
       - 2000v = Tendencia de Fondo (`MACRO_FONDO`)
       - 1000v = Confirmación (`MEDIO_CONFIRMACION`)
       - 500v  = Timing (`CORTO_TIMING`)
     Si la lente larga falla el Doble Sello (o es `N/D`), el fondo queda `INDETERMINADO` y la
     confianza física global se topa estrictamente en `BAJA_CAUTELA`.
"""

from __future__ import annotations

import concurrent.futures
import contextlib
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from kinetopus_pro.engine_bridge import MarketLoader
from kinetopus_pro.headless_pipeline import (
    HeadlessRunResult,
    KinetopusAnalysisConfig,
    KinetopusHeadlessPipeline,
)

DEFAULT_MULTI_LENSES: Tuple[int, int, int] = (2000, 1000, 500)

LENS_HIERARCHY_SPECS: Tuple[Tuple[str, str], ...] = (
    ("MACRO_FONDO", "Tendencia de Fondo"),
    ("MEDIO_CONFIRMACION", "Confirmación de Medio Plazo"),
    ("CORTO_TIMING", "Timing Táctico"),
)


@dataclass
class MultiLensConfig:
    """Configuración unificada para una corrida Multi-Lente."""

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
    wf_cuts: int = 10
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
    raw_price_full: Any


def _run_single_lens_worker(
    cfg_dict: Dict[str, Any], df_payload: pd.DataFrame
) -> HeadlessRunResult:
    """Worker top-level serializable para ejecutar una lente en `ProcessPoolExecutor`."""
    lens_cfg = KinetopusAnalysisConfig(**cfg_dict)
    pipeline = KinetopusHeadlessPipeline(lens_cfg)
    with contextlib.redirect_stdout(sys.stderr):
        return pipeline.run(df_override=df_payload)


class KinetopusMultiLensRunner:
    """Orquestador Multi-Lente con jerarquía fija y sello estricto por nivel."""

    def __init__(self, config: Optional[MultiLensConfig] = None):
        self.cfg = config or MultiLensConfig()
        # Garantizar orden descendente (larga -> media -> corta) para la jerarquía fija
        ordered = tuple(sorted((int(w) for w in self.cfg.lenses), reverse=True))
        if len(ordered) != 3:
            raise ValueError(
                f"La arquitectura jerárquica requiere exactamente 3 lentes (larga, media, corta); recibido: {ordered}"
            )
        self.cfg.lenses = ordered

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
        # Margen mínimo deseado para espaciar cortes OOS genuinos sobre la lente larga
        min_desired_candles = (
            max_lens + eval_h_est + max(500, cfg.wf_cuts * 60)
            if cfg.wf_cuts > 0
            else max_lens
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
                fallback_reason = f"Intento de respaldo '{cfg.fallback_period}' falló ({exc}); se conserva '{cfg.base_period}'."

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
    def _extract_lens_summary(slot: LensSlotResult) -> Dict[str, Any]:
        """Extrae el resumen estructurado de una lente para `confluence.json`."""
        if not slot.available or slot.run_result is None:
            return {
                "window_candles": slot.window_candles,
                "role_code": slot.role_code,
                "role_label": slot.role_label,
                "status": "N/D",
                "available": False,
                "seal_passed": False,
                "seal_grade": "N/D",
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
        cus = tel["cusum_forensics"]
        cone = tel["forecast_cone"]

        raw_dir = "ALCISTA" if kpis["directional_inertia"].startswith("ALCISTA") else "BAJISTA"

        return {
            "window_candles": slot.window_candles,
            "role_code": slot.role_code,
            "role_label": slot.role_label,
            "status": "OK",
            "available": True,
            "window_start_date": ds["window_start_date"],
            "window_end_date": ds["last_candle_date"],
            "calibrated_k": cal["effective_cusum_k"],
            "effective_smooth_tol": cal["effective_smooth_tol"],
            "autopilot_rescued": cal["autopilot_rescue"]["applied"],
            "raw_direction": raw_dir,
            "directional_inertia": kpis["directional_inertia"],
            "instant_velocity_pct_per_candle": kpis["instant_velocity_pct_per_candle"],
            "quadrant": kin["quadrant"],
            "price_vs_spline_gap_pct": kin["price_vs_spline_gap_pct"],
            "last_30c_mean_gap_pct": kin["last_30c_mean_gap_pct"],
            "phase_topology": phs["topology_class"],
            "phase_rotation_sense": phs["rotation_sense"],
            "sindy_r2_score": kpis["sindy_r2_score"],
            "active_equations": wb["active_equations"],
            "cusum_semaphore": kpis["cusum_semaphore"],
            "cusum_tension_vs_h": kpis["cusum_tension_vs_h"],
            "cusum_window_max_peak": cus["window_max_tension_peak"],
            "active_regime_start_date": cus["active_regime_start_date"],
            "active_regime_candles": cus["active_regime_candles"],
            "invalidation_levels_1candle": cus["invalidation_levels_1candle"],
            "seal_passed": bool(seal_sum["seal_passed"]),
            "seal_grade": seal_sum["seal_grade"],
            "seal_reasons": seal_sum["reasons"],
            "oos_physics_class": wf.get("asset_physics_class"),
            "oos_consensus_hr_pct": wf.get("consensus_hit_ratio_pct"),
            "oos_effective_cuts": wf.get("effective_cuts", 0),
            "oos_min_required_cuts": wf.get("min_required_effective_cuts", 5),
            "ljung_box_verdict": lb.get("verdict"),
            "ljung_box_spline_p": lb.get("spline_residuals", {}).get("reference_p_value"),
            "lens_confidence": kpis["overall_physical_confidence"],
            "trajectory_geometry": cone["trajectory_geometry"],
            "horizon_checkpoints": cone["horizon_checkpoints"],
        }

    @staticmethod
    def _synthesize_fixed_hierarchy(
        summaries: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Aplica estrictamente la Jerarquía Fija sin votos ni promociones:
          - Lente 0 (2000v): Tendencia de Fondo. Si es N/D o falla Doble Sello -> INDETERMINADA y
            confianza global <= BAJA_CAUTELA. La lente media jamás la sustituye.
          - Lente 1 (1000v): Confirmación de Medio Plazo.
          - Lente 2 (500v) : Timing Táctico.
        """
        macro = summaries[0]
        medio = summaries[1]
        corto = summaries[2]

        notes: List[str] = []

        # 1. Nivel Fondo (2000v)
        if not macro["available"]:
            bg_state = "N/D (sin historial suficiente para 2000v)"
            bg_dir_clean = "N/D"
            notes.append(
                f"La lente de fondo ({macro['window_candles']}v) no está disponible; la lente media no la sustituye."
            )
        elif not macro["seal_passed"]:
            cls_m = macro.get("oos_physics_class", "EXOGENO")
            if cls_m == "INSUFICIENTE":
                bg_state = "INDETERMINADA (historial OOS insuficiente)"
            else:
                bg_state = "INDETERMINADA (exógena)"
            bg_dir_clean = "INDETERMINADA"
            notes.append(
                f"La lente larga ({macro['window_candles']}v) no aprobó el Doble Sello "
                f"({macro['seal_grade']}: {cls_m}, HR={macro.get('oos_consensus_hr_pct')}%). "
                f"Su inercia interna bruta es {macro['raw_direction']}, pero el fondo oficial queda {bg_state}."
            )
        else:
            bg_dir_clean = macro["raw_direction"]
            bg_state = f"{bg_dir_clean} ({macro['seal_grade']})"
            notes.append(
                f"Tendencia de fondo ({macro['window_candles']}v) validada como {bg_dir_clean} "
                f"(HR OOS={macro['oos_consensus_hr_pct']}% en {macro['oos_effective_cuts']} cortes, R²={macro['sindy_r2_score']:.3f})."
            )

        # 2. Nivel Confirmación (1000v)
        if not medio["available"]:
            conf_state = "N/D (sin historial de 1000v)"
        elif not medio["seal_passed"]:
            cls_md = medio.get("oos_physics_class", "EXOGENO")
            conf_state = (
                "SIN_CONFIRMACION (OOS insuficiente)"
                if cls_md == "INSUFICIENTE"
                else f"SIN_CONFIRMACION_EXOGENA (inercia bruta {medio['raw_direction']})"
            )
            notes.append(
                f"La lente media ({medio['window_candles']}v) no superó el Doble Sello ({cls_md}, HR={medio.get('oos_consensus_hr_pct')}%)."
            )
        else:
            if bg_dir_clean in ("ALCISTA", "BAJISTA"):
                if medio["raw_direction"] == bg_dir_clean:
                    conf_state = f"CONFIRMADA_{medio['raw_direction']}"
                    notes.append(
                        f"La lente media ({medio['window_candles']}v) confirma la dirección {bg_dir_clean} del fondo."
                    )
                else:
                    conf_state = f"DIVERGENCIA_MEDIA_{medio['raw_direction']} (corrección contra fondo)"
                    notes.append(
                        f"La lente media ({medio['window_candles']}v) apunta {medio['raw_direction']}, contradiciendo al fondo {bg_dir_clean}."
                    )
            else:
                conf_state = f"ACTIVA_AISLADA_{medio['raw_direction']} (sin fondo validado)"
                notes.append(
                    f"La lente media ({medio['window_candles']}v) sí aprueba su sello ({medio['raw_direction']}, HR={medio['oos_consensus_hr_pct']}%), "
                    "pero por jerarquía fija no reemplaza a la tendencia de fondo."
                )

        # 3. Nivel Timing (500v)
        if not corto["available"]:
            tim_state = "N/D (sin historial de 500v)"
        elif not corto["seal_passed"]:
            cls_c = corto.get("oos_physics_class", "EXOGENO")
            tim_state = (
                f"TIMING_NO_VALIDADO_OOS ({cls_c} · inercia bruta {corto['raw_direction']} en {corto['quadrant']})"
            )
            notes.append(
                f"El timing ({corto['window_candles']}v) marca {corto['quadrant']}, pero falla su sello OOS ({cls_c}, HR={corto.get('oos_consensus_hr_pct')}%)."
            )
        else:
            if bg_dir_clean in ("ALCISTA", "BAJISTA"):
                if corto["raw_direction"] == bg_dir_clean:
                    tim_state = f"TIMING_ALINEADO_{corto['raw_direction']} ({corto['quadrant']})"
                else:
                    tim_state = f"TIMING_CONTRATENDENCIA_{corto['raw_direction']} ({corto['quadrant']})"
            else:
                tim_state = f"TIMING_TACTICO_{corto['raw_direction']} ({corto['quadrant']})"
            notes.append(
                f"La lente corta ({corto['window_candles']}v) valida timing {corto['raw_direction']} en {corto['quadrant']} "
                f"(HR={corto['oos_consensus_hr_pct']}%)."
            )

        # 4. Patrón de Confluencia y Tope Estricto de Confianza Global
        if not macro["available"] or not macro["seal_passed"]:
            # Regla inquebrantable (Decisión 3): si la lente larga falla o falta, confianza <= BAJA_CAUTELA
            any_unstable = any(
                s.get("available") and s.get("lens_confidence") == "NULA_O_DEGRADADA"
                for s in summaries
            )
            global_confidence = "NULA_O_DEGRADADA" if any_unstable and not any(s.get("seal_passed") for s in summaries) else "BAJA_CAUTELA"
            pattern = "FONDO_INDETERMINADO_POR_SELLO_LARGO"
        else:
            # Lente larga aprobada
            if medio["seal_passed"] and corto["seal_passed"]:
                if medio["raw_direction"] == bg_dir_clean == corto["raw_direction"]:
                    pattern = f"ALINEACION_JERARQUICA_PLENA_{bg_dir_clean}"
                    all_pleno = all(s["seal_grade"] == "APROBADO_PLENO" for s in summaries)
                    global_confidence = "ALTA" if all_pleno else "MEDIA"
                elif medio["raw_direction"] == bg_dir_clean and corto["raw_direction"] != bg_dir_clean:
                    pattern = f"FONDO_Y_MEDIO_{bg_dir_clean}_CON_REPLIEGUE_CORTO"
                    global_confidence = "MEDIA"
                else:
                    pattern = f"FONDO_{bg_dir_clean}_EN_TRANSICION_INTERMEDIA"
                    global_confidence = "MEDIA"
            elif medio["seal_passed"] or corto["seal_passed"]:
                pattern = f"FONDO_{bg_dir_clean}_CON_CONFIRMACION_PARCIAL"
                global_confidence = "MEDIA"
            else:
                pattern = f"SOLO_FONDO_{bg_dir_clean}_CORTO_Y_MEDIO_RUIDOSOS"
                global_confidence = "BAJA_CAUTELA"

        raw_dirs_str = " / ".join(
            f"{s['window_candles']}v: {s['raw_direction']} ({'Sello OK' if s['seal_passed'] else s['seal_grade']})"
            if s["available"]
            else f"{s['window_candles']}v: N/D"
            for s in summaries
        )

        return {
            "hierarchy_rule": "JERARQUIA_FIJA_SIN_PROMOCIONES (2000v=Fondo, 1000v=Confirmación, 500v=Timing)",
            "background_trend_2000v": bg_state,
            "medium_confirmation_1000v": conf_state,
            "short_timing_500v": tim_state,
            "alignment_pattern": pattern,
            "global_physical_confidence": global_confidence,
            "raw_lenses_snapshot": raw_dirs_str,
            "rationale": notes,
        }

    def run(self, df_override: Optional[pd.DataFrame] = None) -> MultiLensRunResult:
        """Ejecuta las 3 lentes sobre una sola descarga y sintetiza `MultiLensRunResult`."""
        t0 = time.perf_counter()
        cfg = self.cfg

        df_full, download_meta = self._load_smart_dataset(df_override=df_override)
        dates_full = KinetopusHeadlessPipeline._extract_iso_dates(df_full)
        _, _, raw_price_full, _ = MarketLoader.prepare_quant_input(
            df_full.copy(), disable_norm=cfg.disable_norm, disable_returns=cfg.disable_returns
        )
        n_total = len(df_full)

        # Preparar ranuras jerárquicas
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

        # Ejecutar lentes disponibles en paralelo (o secuencial si solo hay 1 o parallel=False)
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
        hierarchy = self._synthesize_fixed_hierarchy(summaries)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        last_price = float(raw_price_full[-1]) if len(raw_price_full) > 0 else 0.0
        confluence: Dict[str, Any] = {
            "metadata": {
                "engine": "KineTopus Multi-Lens Engine v2.2 (Hito 2)",
                "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "total_runtime_ms": round(elapsed_ms, 2),
                "config": asdict(cfg),
                "download": download_meta,
                "dataset": {
                    "ticker": cfg.ticker,
                    "interval": cfg.interval,
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
            raw_price_full=raw_price_full,
        )
