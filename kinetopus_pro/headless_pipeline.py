"""
Orquestador Headless del Motor Quant KineTopus (Hito 1 + Hito 2 + v0.3.1 Enfoque Geométrico Puro).

Ejecuta el pipeline físico-matemático completo de 5 capas + Auto-Calibración +
Ajuste Curva-Precio + Cono Calibrado de Integración Simple EWMA + Auditoría OOS
opcional (`--audit-oos`), aislado al 100% de Streamlit (`app.py`) y respetando la
Regla de 16GB RAM (matrices C-contiguous `np.float64`, cero Pandas en hot loops).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from statsmodels.stats.diagnostic import acorr_ljungbox

from kinetopus_pro.engine_bridge import (
    CUSUMAutoTuner,
    ContinuousBlender,
    MarketLoader,
    PhysicsDiscoverer,
    RegimeShiftDetector,
    SpectralAnalyzer,
    SymbolicTranslator,
)

logger = logging.getLogger(__name__)


@dataclass
class KinetopusAnalysisConfig:
    """Configuración tipada para una corrida determinista/estocástica del motor."""

    ticker: str = "BTC-USD"
    period: str = "10y"
    interval: str = "1d"
    context_window: int = 1000
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
    strict_wf_window: bool = True
    min_wf_effective_cuts: int = 5
    in_process_fft: bool = True
    random_seed: int = 42


@dataclass
class HeadlessRunResult:
    """Contenedor en memoria: telemetría serializable + tensores float64 para renderizado."""

    telemetry: Dict[str, Any]
    arrays: Dict[str, Any]


class KinetopusHeadlessPipeline:
    """
    Motor de ejecución sin interfaz gráfica (Headless) para agentes de IA y CLI.
    Garantiza paridad matemática con el pipeline de producción, añadiendo:
      1. Auto-calibración sobre la ventana activa y rescate automático Autopilot 2D.
      2. Doble sello de fiabilidad física estricto (Ljung-Box + Mini Walk-Forward OOS de ventana completa).
      3. Telemetría geométrica, brecha precio-variedad, espacio de fase y calendario CUSUM.
    """

    def __init__(self, config: Optional[KinetopusAnalysisConfig] = None):
        self.cfg = config or KinetopusAnalysisConfig()

    @staticmethod
    def _extract_iso_dates(df: pd.DataFrame) -> List[str]:
        """Extrae etiquetas temporales ISO limpias una única vez fuera de los hot loops."""
        if isinstance(df.index, pd.DatetimeIndex):
            has_time = any(
                (ts.hour != 0 or ts.minute != 0) for ts in df.index[: min(10, len(df))]
            )
            fmt = "%Y-%m-%d %H:%M" if has_time else "%Y-%m-%d"
            return [ts.strftime(fmt) for ts in df.index]

        for col in ("Date", "Datetime", "date", "datetime", "Time", "time"):
            if col in df.columns:
                parsed = pd.to_datetime(df[col], errors="coerce")
                if not parsed.isna().all():
                    has_time = any(
                        (ts.hour != 0 or ts.minute != 0)
                        for ts in parsed.dropna().iloc[:10]
                    )
                    fmt = "%Y-%m-%d %H:%M" if has_time else "%Y-%m-%d"
                    return [
                        ts.strftime(fmt) if pd.notna(ts) else f"t={idx}"
                        for idx, ts in enumerate(parsed)
                    ]

        return [f"t={idx}" for idx in range(len(df))]

    @staticmethod
    def _compute_ewma_sigma(series_diff: np.ndarray, n: int) -> np.ndarray:
        """Replica el estimador EWMA de turbulencia local (30 velas) en float64."""
        sigma_dyn = np.ones(n, dtype=np.float64) * 1e-8
        if len(series_diff) == 0:
            return sigma_dyn

        alpha = 2.0 / (30.0 + 1.0)
        init_w = min(30, len(series_diff))
        var_t = float(np.var(series_diff[:init_w]) / 2.0)
        if var_t < 1e-10:
            var_t = 1e-10
        sigma_dyn[0] = np.sqrt(var_t)

        for i in range(1, n):
            inst_var = float((series_diff[i - 1] ** 2) / 2.0)
            var_t = alpha * inst_var + (1.0 - alpha) * var_t
            val = np.sqrt(var_t)
            sigma_dyn[i] = val if val >= 1e-8 else 1e-8

        return sigma_dyn

    @staticmethod
    def _estimate_ewma_return_sigma(residuals: np.ndarray, span: int = 30) -> float:
        """
        Estima la volatilidad local EWMA (RiskMetrics, span=30 por defecto) sobre los residuos
        de retorno `e_t = log_returns - r_smooth`, acotando outliers extremos a ±3.5 MAD-sigma
        para que un único flash-crash no distorsione meses de difusión estocástica.
        """
        if len(residuals) == 0:
            return 1e-4
        res = np.ascontiguousarray(residuals, dtype=np.float64)
        res = res[np.isfinite(res)]
        if len(res) == 0:
            return 1e-4

        med = float(np.median(res))
        mad_sig = 1.4826 * float(np.median(np.abs(res - med)))
        std_sig = float(np.std(res))
        scale_ref = max(mad_sig, std_sig * 0.5, 1e-8)
        clipped = np.clip(res, med - 3.5 * scale_ref, med + 3.5 * scale_ref)

        alpha = 2.0 / (float(max(span, 2)) + 1.0)
        init_w = min(max(span, 5), len(clipped))
        var_t = max(float(np.mean(clipped[:init_w] ** 2)), 1e-16)
        for val in clipped[1:]:
            var_t = alpha * float(val * val) + (1.0 - alpha) * var_t
        return float(np.sqrt(max(var_t, 1e-16)))

    @classmethod
    def _simulate_calibrated_single_integration_cone(
        cls,
        last_price: float,
        det_prices: np.ndarray,
        precio_raw: np.ndarray,
        log_returns: np.ndarray,
        r_smooth: np.ndarray,
        dt_val: float,
        unstable_flag: bool,
        empty_r_eq: bool,
        disable_returns: bool,
        disable_norm: bool,
        random_seed: int = 42,
        n_paths: int = 2000,
    ) -> Tuple[List[List[float]], np.ndarray, float]:
        """
        Reconstruye el cono Monte Carlo en `kinetopus_pro` aplicando ruido estocástico una
        única vez sobre incrementos de log-precio alrededor de la deriva determinista SINDy F(t),
        eliminando la doble integración de ruido de `KineTopus Engine` sin tocar upstream.
        """
        classic_mode = bool(disable_returns or disable_norm)
        if classic_mode:
            res_base = (
                np.diff(precio_raw - r_smooth)
                if len(precio_raw) > 2
                else (precio_raw - r_smooth)
            )
        else:
            res_base = log_returns - r_smooth

        sigma_ewma = cls._estimate_ewma_return_sigma(res_base, span=30)
        h_steps = len(det_prices)
        if (
            h_steps == 0
            or unstable_flag
            or empty_r_eq
            or not np.all(np.isfinite(det_prices))
        ):
            return [], np.empty((0, 0), dtype=np.float64), sigma_ewma

        rng = np.random.default_rng(int(random_seed))
        dt_scale = float(np.sqrt(max(dt_val, 1e-8)))

        if classic_mode:
            p_seq = np.concatenate(([last_price], np.asarray(det_prices, dtype=np.float64)))
            p_steps = np.diff(p_seq)
            shocks = rng.standard_normal((h_steps, n_paths)) * (sigma_ewma * dt_scale)
            cum_paths = np.cumsum(p_steps[:, None] + shocks, axis=0)
            price_paths = np.ascontiguousarray(last_price + cum_paths, dtype=np.float64)
        else:
            p_seq = np.maximum(
                np.concatenate(([last_price], np.asarray(det_prices, dtype=np.float64))),
                1e-8,
            )
            log_p_steps = np.diff(np.log(p_seq))
            shocks = rng.standard_normal((h_steps, n_paths)) * (sigma_ewma * dt_scale)
            cum_log_paths = np.cumsum(log_p_steps[:, None] + shocks, axis=0)
            price_paths = np.ascontiguousarray(
                max(last_price, 1e-8) * np.exp(np.clip(cum_log_paths, -4.0, 4.0)),
                dtype=np.float64,
            )

        pct_matrix = np.percentile(price_paths, [5, 25, 50, 75, 95], axis=1)
        percentiles_list = [[float(v) for v in row] for row in pct_matrix]
        return percentiles_list, price_paths, sigma_ewma

    @staticmethod
    def humanize_code(category: str, code: Optional[str]) -> str:
        """Traduce códigos enum internos a etiquetas humanas limpias en español."""
        if not code:
            return "No disponible"
        maps: Dict[str, Dict[str, str]] = {
            "seal_grade": {
                "APROBADO_PLENO": "Validado pleno",
                "APROBADO_CONDICIONAL": "Validado condicional",
                "REPROBADO_EXOGENO": "Sin sello (dinámica exógena OOS)",
                "REPROBADO_BAJO_R2": "Sin sello (ajuste interno débil)",
                "INSUFICIENTE": "Sin sello (historial OOS insuficiente)",
                "FALLO_ESTABILIDAD": "Sin sello (inestabilidad numérica)",
                "NO_EVALUADO": "Omitido (--audit-oos)",
                "GEOMETRICO_PURO": "Geometría activa (sin filtro OOS)",
                "N/D": "No disponible",
            },
            "physics_class": {
                "COHERENTE_INERCIAL": "Inercial coherente",
                "TRANSICIONAL_BORDE": "Transicional",
                "EXOGENO_FUNDAMENTALISTA": "Dominado por choques externos",
                "INESTABLE_O_RUIDO_EXTREMO": "Ruido extremo",
                "INSUFICIENTE": "Muestra insuficiente",
                "NO_EVALUADO": "Omitido (usar --audit-oos)",
            },
            "topology": {
                "COMPRESION_EQUILIBRIO_CENTRAL": "Compresión en equilibrio",
                "ESCAPE_RUPTURA_CENTRIFUGA": "Ruptura en expansión",
                "ESPIRAL_AMORTIGUADA_CONVERGENTE": "Espiral amortiguada al equilibrio",
                "CICLO_ORBITAL_ACTIVO": "Ciclo orbital activo",
            },
            "cusum_status": {
                "ESTABLE": "Estable",
                "TENSION_ALTA": "Tensión alta",
                "QUIEBRE_INMINENTE": "Riesgo de quiebre inminente",
            },
            "confidence": {
                "ALTA": "ALTA",
                "MEDIA": "MEDIA",
                "BAJA": "BAJA",
                "BAJA_CAUTELA": "BAJA",
                "NULA_O_DEGRADADA": "BAJA",
            },
        }
        return maps.get(category, {}).get(str(code), str(code).replace("_", " ").capitalize())

    @classmethod
    def classify_human_regime(
        cls,
        last_price: float,
        window_max_price: float,
        gap_now_pct: float,
        vel_now: float,
        acc_now: float,
        det_prices: np.ndarray,
        sigma_ewma: float,
        unstable_flag: bool,
        empty_r_eq: bool,
        disable_returns: bool,
        topology_class: str,
        cusum_status: str,
        seal_grade: str,
    ) -> Dict[str, Any]:
        """
        Clasifica el estado del activo en la taxonomía humana de 5 estados + modificador
        de posición respecto a la variedad suave (Decisión 6).
        """
        if disable_returns:
            sigma_pct = (sigma_ewma / max(abs(last_price), 1e-8)) * 100.0
        else:
            sigma_pct = sigma_ewma * 100.0

        ref_step = min(63, len(det_prices)) if len(det_prices) > 0 else 0
        noise_band_pct = max(0.50, 0.35 * sigma_pct * float(np.sqrt(max(ref_step, 1))))

        if ref_step > 0 and not unstable_flag and not empty_r_eq and abs(last_price) > 1e-8:
            det_ret_ref_pct = ((float(det_prices[ref_step - 1]) - last_price) / last_price) * 100.0
        elif empty_r_eq:
            det_ret_ref_pct = 0.0
        else:
            det_ret_ref_pct = vel_now * float(max(ref_step, 21))

        near_highs = window_max_price > 0 and last_price >= 0.95 * window_max_price

        if abs(det_ret_ref_pct) <= noise_band_pct:
            state_code = "LATERAL_DIGESTION"
            family_label = "Lateral / Digestión"
            state_label = "Lateral en máximos" if near_highs else "Lateral / Digestión"
            state_summary = (
                f"La deriva proyectada a {ref_step or 63} velas ({det_ret_ref_pct:+.2f}%) es menor que la "
                f"banda de ruido normal del activo (±{noise_band_pct:.2f}%): el mercado digiere en rango."
            )
        elif det_ret_ref_pct > noise_band_pct:
            if acc_now >= 0.0:
                state_code = "IMPULSO_ALCISTA"
                family_label = "Impulso alcista"
                state_label = "Impulso alcista"
                state_summary = (
                    f"Avance proyectado ({det_ret_ref_pct:+.2f}% a {ref_step}v) superando el ruido base "
                    "con aceleración sostenida."
                )
            else:
                state_code = "ALCISTA_FRENANDO"
                family_label = "Alcista frenando"
                state_label = "Alcista frenando"
                state_summary = (
                    f"Pendiente aún alcista ({det_ret_ref_pct:+.2f}% a {ref_step}v), pero perdiendo velocidad "
                    "(desaceleración activa)."
                )
        else:
            if acc_now <= 0.0:
                state_code = "CORRECCION_BAJISTA"
                family_label = "Corrección bajista"
                state_label = "Corrección bajista"
                state_summary = (
                    f"Presión vendedora dominante ({det_ret_ref_pct:+.2f}% proyectado a {ref_step}v) "
                    "sin señal de giro todavía."
                )
            else:
                state_code = "CAIDA_FRENANDO_SUELO"
                family_label = "Caída frenando / Suelo en formación"
                state_label = "Caída frenando / Suelo en formación"
                state_summary = (
                    f"Inercia todavía descendente ({det_ret_ref_pct:+.2f}% a {ref_step}v), pero frenando su "
                    "velocidad de caída (posible formación de suelo)."
                )

        ext_thresh_pct = max(2.5, 2.0 * sigma_pct)
        if gap_now_pct >= ext_thresh_pct:
            pos_code = "SOBREEXTENDIDO"
            pos_short = f"sobreextendido {gap_now_pct:+.1f}%"
            pos_detail = f"sobreextendido {gap_now_pct:+.1f}% sobre su curva"
        elif gap_now_pct <= -ext_thresh_pct:
            pos_code = "DESCOLGADO"
            pos_short = f"descolgado {gap_now_pct:+.1f}%"
            pos_detail = f"descolgado {gap_now_pct:+.1f}% bajo su curva"
        else:
            pos_code = "EN_LINEA"
            pos_short = f"cerca de su curva ({gap_now_pct:+.1f}%)"
            pos_detail = f"alineado con su curva ({gap_now_pct:+.1f}%)"

        return {
            "state_code": state_code,
            "family_label": family_label,
            "state_label": state_label,
            "near_window_highs": bool(near_highs),
            "position_code": pos_code,
            "position_short": pos_short,
            "position_modifier": pos_detail,
            "full_label": f"{state_label} · {pos_short}",
            "reference_step_candles": int(ref_step),
            "projected_reference_return_pct": round(float(det_ret_ref_pct), 2),
            "natural_noise_band_pct": round(float(noise_band_pct), 2),
            "daily_ewma_volatility_pct": round(float(sigma_pct), 3),
            "overextension_threshold_pct": round(float(ext_thresh_pct), 2),
            "topology_human": cls.humanize_code("topology", topology_class),
            "cusum_human": cls.humanize_code("cusum_status", cusum_status),
            "seal_human": cls.humanize_code("seal_grade", seal_grade),
            "plain_summary": state_summary,
        }

    @classmethod
    def _compute_probabilistic_scenarios(
        cls,
        last_price: float,
        nominal_smooth_now: float,
        det_prices: np.ndarray,
        mc_percentiles: List[List[float]],
        price_paths: np.ndarray,
        horizon_steps: int,
    ) -> Dict[str, Any]:
        """
        Calcula los 3 escenarios geométricos del motor v0.3.1 (Central, Expansión Alcista P75,
        Reversión Bajista P25) centrados en la curva 1000v y los cuartiles P25/P75 calibrados,
        con probabilidades exactas de primer toque antes de `t+H` sobre las 2000 trayectorias EWMA.
        """
        has_paths = (
            price_paths.ndim == 2
            and price_paths.shape[0] > 0
            and price_paths.shape[1] > 0
            and len(det_prices) > 0
            and len(mc_percentiles) == 5
        )
        h_eff = int(len(det_prices)) if len(det_prices) > 0 else int(horizon_steps)

        if not has_paths:
            return {
                "available": False,
                "validated": False,
                "horizon_step": f"t+{h_eff}",
                "n_simulations": 0,
                "base": None,
                "bullish": None,
                "bearish": None,
            }

        n_sims = int(price_paths.shape[1])
        idx_end = len(det_prices) - 1
        idx_mid = min(20, idx_end)

        base_center = float(det_prices[idx_end])
        p5_end = float(mc_percentiles[0][idx_end])
        p25_end = float(mc_percentiles[1][idx_end])
        p50_end = float(mc_percentiles[2][idx_end])
        p75_end = float(mc_percentiles[3][idx_end])
        p95_end = float(mc_percentiles[4][idx_end])

        p25_mid = float(mc_percentiles[1][idx_mid])
        p75_mid = float(mc_percentiles[3][idx_mid])

        # Garantizar objetivos y gatillos monótonos centrados en cuartiles P25/P75 y curva suave
        bull_target = p75_end if p75_end > last_price * 1.006 else max(p95_end, last_price * 1.010)
        cand_bull_trig = max(
            p75_mid,
            nominal_smooth_now if nominal_smooth_now > last_price else p75_mid,
            last_price * 1.002,
        )
        bull_trigger = min(cand_bull_trig, bull_target * 0.995)
        if bull_trigger <= last_price:
            bull_trigger = last_price + max((bull_target - last_price) * 0.35, last_price * 0.002)
            bull_trigger = min(bull_trigger, bull_target * 0.996)

        bear_target = p25_end if p25_end < last_price * 0.994 else min(p5_end, last_price * 0.990)
        cand_bear_trig = min(
            p25_mid,
            nominal_smooth_now if nominal_smooth_now < last_price else p25_mid,
            last_price * 0.998,
        )
        bear_trigger = max(cand_bear_trig, bear_target * 1.005)
        if bear_trigger >= last_price:
            bear_trigger = last_price - max((last_price - bear_target) * 0.35, last_price * 0.002)
            bear_trigger = max(bear_trigger, bear_target * 1.004)

        if abs(base_center - last_price) / max(abs(last_price), 1e-8) < 0.0025:
            lo_b = min(last_price, base_center) * 0.9975
            hi_b = max(last_price, base_center) * 1.0025
            touch_base_mask = np.any((price_paths >= lo_b) & (price_paths <= hi_b), axis=0)
        elif base_center >= last_price:
            touch_base_mask = np.max(price_paths, axis=0) >= base_center
        else:
            touch_base_mask = np.min(price_paths, axis=0) <= base_center

        touch_bull_trig_mask = np.max(price_paths, axis=0) >= bull_trigger
        touch_bull_tgt_mask = np.max(price_paths, axis=0) >= bull_target
        touch_bear_trig_mask = np.min(price_paths, axis=0) <= bear_trigger
        touch_bear_tgt_mask = np.min(price_paths, axis=0) <= bear_target

        final_prices = price_paths[-1, :]
        stay_iqr_mask = (final_prices >= p25_end) & (final_prices <= p75_end)

        prob_touch_base = float(np.mean(touch_base_mask) * 100.0)
        prob_stay_iqr = float(np.mean(stay_iqr_mask) * 100.0)
        prob_touch_bull = float(np.mean(touch_bull_tgt_mask) * 100.0)
        prob_trig_bull = float(np.mean(touch_bull_trig_mask) * 100.0)
        prob_touch_bear = float(np.mean(touch_bear_tgt_mask) * 100.0)
        prob_trig_bear = float(np.mean(touch_bear_trig_mask) * 100.0)

        up_trig_pct = ((bull_trigger / last_price) - 1.0) * 100.0 if last_price > 0 else 0.0
        dn_trig_pct = ((bear_trigger / last_price) - 1.0) * 100.0 if last_price > 0 else 0.0
        base_ret_pct = ((base_center - last_price) / last_price) * 100.0 if last_price > 0 else 0.0
        bull_ret_pct = ((bull_target - last_price) / last_price) * 100.0 if last_price > 0 else 0.0
        bear_ret_pct = ((bear_target - last_price) / last_price) * 100.0 if last_price > 0 else 0.0
        p95_ret_pct = ((p95_end - last_price) / last_price) * 100.0 if last_price > 0 else 0.0
        p5_ret_pct = ((p5_end - last_price) / last_price) * 100.0 if last_price > 0 else 0.0

        return {
            "available": True,
            "validated": True,
            "horizon_step": f"t+{h_eff}",
            "n_simulations": n_sims,
            "prob_stay_within_iqr_pct": round(prob_stay_iqr, 1),
            "base": {
                "code": "BASE",
                "name": "Escenario Central (Deriva 1000v · P25–P75)",
                "trigger_condition": (
                    f"Sostener deriva dentro del corredor P25–P75 ({p25_end:,.2f} – {p75_end:,.2f})"
                ),
                "trigger_low_price": round(p25_end, 4),
                "trigger_high_price": round(p75_end, 4),
                "target_price": round(base_center, 4),
                "target_return_pct": round(base_ret_pct, 2),
                "band_p25_price": round(p25_end, 4),
                "band_p50_price": round(p50_end, 4),
                "band_p75_price": round(p75_end, 4),
                "touch_probability_pct": round(prob_touch_base, 1),
                "channel_survival_probability_pct": round(prob_stay_iqr, 1),
            },
            "bullish": {
                "code": "ALCISTA",
                "name": "Expansión Alcista (Hacia Cuartil Superior P75)",
                "trigger_condition": f"Tracción sostenida sobre {bull_trigger:,.2f} ({up_trig_pct:+.2f}%)",
                "trigger_price": round(float(bull_trigger), 4),
                "trigger_pct_from_close": round(float(up_trig_pct), 2),
                "trigger_touch_probability_pct": round(prob_trig_bull, 1),
                "target_price": round(float(bull_target), 4),
                "target_return_pct": round(float(bull_ret_pct), 2),
                "stretch_p95_price": round(float(p95_end), 4),
                "stretch_p95_return_pct": round(float(p95_ret_pct), 2),
                "touch_probability_pct": round(prob_touch_bull, 1),
            },
            "bearish": {
                "code": "BAJISTA",
                "name": "Reversión Bajista (Hacia Cuartil Inferior P25)",
                "trigger_condition": f"Debilidad sostenida bajo {bear_trigger:,.2f} ({dn_trig_pct:+.2f}%)",
                "trigger_price": round(float(bear_trigger), 4),
                "trigger_pct_from_close": round(float(dn_trig_pct), 2),
                "trigger_touch_probability_pct": round(prob_trig_bear, 1),
                "target_price": round(float(bear_target), 4),
                "target_return_pct": round(float(bear_ret_pct), 2),
                "stretch_p5_price": round(float(p5_end), 4),
                "stretch_p5_return_pct": round(float(p5_ret_pct), 2),
                "touch_probability_pct": round(prob_touch_bear, 1),
            },
        }

    @staticmethod
    def _compute_curve_price_fit(
        precio_raw: np.ndarray,
        nominal_smooth: np.ndarray,
        act_s: int,
        act_e: int,
    ) -> Dict[str, Any]:
        """Mide qué tan fielmente la curva suave `nominal_smooth` sigue al precio observado."""
        p = np.asarray(precio_raw, dtype=np.float64)
        s = np.asarray(nominal_smooth, dtype=np.float64)

        def _r2_mape_rmse(pa: np.ndarray, sa: np.ndarray) -> Tuple[float, float, float]:
            if len(pa) == 0:
                return 0.0, 0.0, 0.0
            ss_res = float(np.sum((pa - sa) ** 2))
            ss_tot = float(np.sum((pa - np.mean(pa)) ** 2))
            r2 = 1.0 if ss_tot < 1e-12 else float(np.clip(1.0 - (ss_res / ss_tot), -1.0, 1.0))
            mape = float(np.mean(np.abs(pa - sa) / np.maximum(np.abs(pa), 1e-8)) * 100.0)
            rmse = float(np.sqrt(np.mean((pa - sa) ** 2)))
            return r2, mape, rmse

        win_r2, win_mape, win_rmse = _r2_mape_rmse(p, s)
        a_s = max(0, min(int(act_s), max(0, len(p) - 1)))
        a_e = max(a_s + 1, min(int(act_e), len(p)))
        if a_e - a_s >= 3:
            act_r2, act_mape, _ = _r2_mape_rmse(p[a_s:a_e], s[a_s:a_e])
        else:
            act_r2, act_mape = win_r2, win_mape

        if win_r2 >= 0.90:
            quality_lbl = "Fidelidad alta"
        elif win_r2 >= 0.75:
            quality_lbl = "Fidelidad buena"
        elif win_r2 >= 0.50:
            quality_lbl = "Tendencia suavizada"
        else:
            quality_lbl = "Tendencia amplia"

        return {
            "window_price_r2": round(win_r2, 4),
            "active_regime_price_r2": round(act_r2, 4),
            "mape_pct": round(win_mape, 3),
            "window_price_mape_pct": round(win_mape, 3),
            "active_regime_mape_pct": round(act_mape, 3),
            "rmse_price": round(win_rmse, 4),
            "fit_quality_label": quality_lbl,
            "fit_label": quality_lbl,
        }

    @staticmethod
    def _is_projection_numerically_divergent(
        raw_det_prices: Any,
        last_price: float,
        disable_returns: bool,
    ) -> bool:
        """Detecta explosiones exponenciales finitas (ej. 1e200) de EDOs SINDy con λ>0."""
        arr = np.asarray(raw_det_prices if raw_det_prices is not None else [], dtype=np.float64).reshape(-1)
        if len(arr) == 0 or not bool(np.all(np.isfinite(arr))):
            return True
        if disable_returns:
            return bool(np.max(np.abs(arr - float(last_price))) > 1e4 * max(abs(float(last_price)), 1.0))
        if float(last_price) > 0.0:
            return bool(
                np.any(arr <= 0.0)
                or float(np.max(arr)) > float(last_price) * 10.0
                or float(np.min(arr)) < float(last_price) * 1e-4
            )
        return False

    @staticmethod
    def _ensure_geometric_projection(
        last_price: float,
        raw_det_t: np.ndarray,
        raw_det_prices: np.ndarray,
        horizon_steps: int,
        dt_val: float,
        t_end: float,
        r_smooth: np.ndarray,
        r_dot: np.ndarray,
        unstable_flag: bool,
        empty_r_eq: bool,
        disable_returns: bool,
    ) -> Tuple[np.ndarray, np.ndarray, bool]:
        """Garantiza siempre una proyección finita `t+H` aunque la EDO SINDy sea nula o inestable."""
        h_steps = max(1, int(horizon_steps))
        step_dt = float(dt_val) if dt_val > 0 else 1.0
        det_t_fallback = np.ascontiguousarray(
            float(t_end) + np.arange(1, h_steps + 1, dtype=np.float64) * step_dt,
            dtype=np.float64,
        )
        raw_t_arr = np.asarray(raw_det_t if raw_det_t is not None else [], dtype=np.float64).reshape(-1)
        det_prices_arr = np.asarray(raw_det_prices if raw_det_prices is not None else [], dtype=np.float64).reshape(-1)
        det_t_valid = (
            len(raw_t_arr) == h_steps
            and bool(np.all(np.isfinite(raw_t_arr)))
            and float(raw_t_arr[0]) >= float(t_end)
        )
        det_t_out = np.ascontiguousarray(raw_t_arr, dtype=np.float64) if det_t_valid else det_t_fallback

        bad_vals = (
            unstable_flag
            or empty_r_eq
            or len(det_prices_arr) != h_steps
            or KinetopusHeadlessPipeline._is_projection_numerically_divergent(
                det_prices_arr,
                float(last_price),
                disable_returns,
            )
        )
        if not bad_vals:
            return det_t_out, np.ascontiguousarray(det_prices_arr, dtype=np.float64), False

        steps_k = np.arange(1, h_steps + 1, dtype=np.float64)
        if disable_returns:
            v0 = float(r_dot[-1]) if len(r_dot) > 0 and np.isfinite(r_dot[-1]) else 0.0
            fallback_p = float(last_price) + np.cumsum(v0 * (0.975**steps_k))
        else:
            r0_raw = float(r_smooth[-1]) if len(r_smooth) > 0 and np.isfinite(r_smooth[-1]) else 0.0
            r0 = float(np.clip(r0_raw, -0.05, 0.05))
            fallback_p = max(float(last_price), 1e-8) * np.exp(np.cumsum(r0 * (0.975**steps_k)))
        return det_t_fallback, np.ascontiguousarray(fallback_p, dtype=np.float64), True

    @staticmethod
    def compute_nominal_smooth(
        raw_price: np.ndarray,
        r_smooth: np.ndarray,
        triggers: List[int],
        disable_returns: bool = False,
    ) -> np.ndarray:
        """
        Reconstruye la variedad continua de precio nominal P_tilde(t) por régimen CUSUM.
        Integra exactamente r_smooth(t) (preservando al 100% la derivada dr/dt) y fija la
        constante de integración C* por mínimos cuadrados en log-precio sobre cada régimen,
        evitando sesgos verticales cuando el primer o último día del régimen es un pico/valle.
        """
        if disable_returns:
            return np.ascontiguousarray(r_smooth.copy(), dtype=np.float64)

        n = len(raw_price)
        nominal_smooth = np.empty(n, dtype=np.float64)
        seg_bounds = [0] + [int(idx) for idx in triggers if 0 < int(idx) < n] + [n]
        log_p = np.log(np.maximum(raw_price, 1e-8))

        for i in range(len(seg_bounds) - 1):
            s_i, e_i = seg_bounds[i], seg_bounds[i + 1]
            if e_i <= s_i:
                continue
            if e_i - s_i == 1:
                nominal_smooth[s_i] = raw_price[s_i]
                continue
            cum_r = np.zeros(e_i - s_i, dtype=np.float64)
            cum_r[1:] = np.cumsum(r_smooth[s_i + 1 : e_i])
            c_star = float(np.mean(log_p[s_i:e_i] - cum_r))
            nominal_smooth[s_i:e_i] = np.exp(cum_r + c_star)

        return np.ascontiguousarray(nominal_smooth, dtype=np.float64)

    @staticmethod
    def _build_effective_boundaries(
        shift_idx: List[int], total_len: int, min_len: int = 15
    ) -> Tuple[List[int], bool, Optional[int]]:
        """
        Construye fronteras de régimen garantizando que el régimen vigente alcance `total_len`
        con al menos `min_len` velas (evita quedarse anclado en un régimen pasado con h_steps=1
        cuando ocurre un quiebre muy reciente < 15 velas).
        """
        raw_bounds = [0] + list(shift_idx) + [total_len]
        filtered: List[int] = [0]
        for b in raw_bounds[1:-1]:
            if b - filtered[-1] >= min_len:
                filtered.append(b)

        unconsolidated_break = False
        unconsolidated_idx: Optional[int] = None
        if len(shift_idx) > 0 and (total_len - shift_idx[-1]) < min_len:
            unconsolidated_break = True
            unconsolidated_idx = int(shift_idx[-1])

        if len(filtered) > 1 and (total_len - filtered[-1]) < min_len:
            filtered.pop()

        filtered.append(total_len)
        return filtered, unconsolidated_break, unconsolidated_idx

    def _run_fast_cusum_autotune(
        self,
        df_active: pd.DataFrame,
        min_drift: float = 0.1,
        max_drift: float = 5.0,
        steps: float = 0.1,
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Delega en `CUSUMAutoTuner.run_search` de `kinetopus-engine` (>=2.0.0), que ya
        ejecuta FFT en proceso para `n_features <= 4` y cachea segmentos BIC en float64,
        garantizando paridad bit-exacta con upstream sin subprocesos anidados.
        """
        cfg = self.cfg
        tuner = CUSUMAutoTuner(
            df_active.copy(),
            disable_norm=cfg.disable_norm,
            disable_returns=cfg.disable_returns,
        )
        return tuner.run_search(min_drift=min_drift, max_drift=max_drift, steps=steps)

    def _run_core_pass(
        self,
        t: np.ndarray,
        log_returns: np.ndarray,
        volumen_z: np.ndarray,
        precio_raw: np.ndarray,
        dt_val: float,
        periodos_retornos: np.ndarray,
        periodos_volumen: np.ndarray,
        smooth_tol: float,
        cusum_k: float,
    ) -> Dict[str, Any]:
        """Ejecuta Capas 2, 3, 4 y 5 para una combinación dada de (smooth_tol, cusum_k)."""
        cfg = self.cfg

        blender = ContinuousBlender(tolerance=smooth_tol)
        telemetry_r = blender.fit(t, log_returns, periodos_retornos, feature_idx=0)
        telemetry_v = blender.fit(t, volumen_z, periodos_volumen, feature_idx=1)

        r_smooth, r_dot, r_dot2 = blender.compute_continuous(0, t)
        v_smooth, v_dot, v_dot2 = blender.compute_continuous(1, t)

        detector = RegimeShiftDetector(threshold=cfg.cusum_h, drift=cusum_k)
        cusum_report = detector.detect(log_returns, r_smooth)

        x_matrix = np.ascontiguousarray(np.column_stack((r_smooth, v_smooth)), dtype=np.float64)
        x_dot_matrix = np.ascontiguousarray(np.column_stack((r_dot, v_dot)), dtype=np.float64)

        sigma_res_r = float(np.std(log_returns - r_smooth))
        sigma_res_v = float(np.std(volumen_z - v_smooth))

        # 1. Física Global
        disc_global = PhysicsDiscoverer(poly_degree=cfg.poly_degree)
        np.random.seed(cfg.random_seed)
        physics_report_global = disc_global.extract_equations(
            t=t,
            x=x_matrix,
            x_dot=x_dot_matrix,
            dt=dt_val,
            horizon_steps=cfg.horizon_steps,
            sigma_res_r=sigma_res_r,
            sigma_res_v=sigma_res_v,
            last_price=float(precio_raw[-1]),
            disable_norm=cfg.disable_norm,
            disable_returns=cfg.disable_returns,
        )

        # 2. Física por Regímenes (con protección de cola < 15 velas)
        shift_idx = cusum_report["shift_indices"]
        boundaries, unconsolidated_break, unconsolidated_idx = self._build_effective_boundaries(
            shift_idx, len(t), min_len=15
        )

        regime_reports: List[Dict[str, Any]] = []
        active_discoverer: Optional[PhysicsDiscoverer] = None

        for i in range(len(boundaries) - 1):
            start_idx = boundaries[i]
            end_idx = boundaries[i + 1]
            if end_idx - start_idx < 15:
                continue

            is_last = i == (len(boundaries) - 2)
            h_steps = cfg.horizon_steps if is_last else 1

            t_slice = np.ascontiguousarray(t[start_idx:end_idx], dtype=np.float64)
            x_slice = np.ascontiguousarray(x_matrix[start_idx:end_idx], dtype=np.float64)
            x_dot_slice = np.ascontiguousarray(x_dot_matrix[start_idx:end_idx], dtype=np.float64)
            price_slice = precio_raw[start_idx:end_idx]

            local_sigma_r = float(np.std(log_returns[start_idx:end_idx] - r_smooth[start_idx:end_idx]))
            local_sigma_v = float(np.std(volumen_z[start_idx:end_idx] - v_smooth[start_idx:end_idx]))

            disc_reg = PhysicsDiscoverer(poly_degree=cfg.poly_degree)
            np.random.seed(cfg.random_seed)
            rep = disc_reg.extract_equations(
                t=t_slice,
                x=x_slice,
                x_dot=x_dot_slice,
                dt=dt_val,
                horizon_steps=h_steps,
                sigma_res_r=local_sigma_r,
                sigma_res_v=local_sigma_v,
                last_price=float(price_slice[-1]),
                disable_norm=cfg.disable_norm,
                disable_returns=cfg.disable_returns,
            )
            rep["sigma_res_r"] = local_sigma_r
            rep["sigma_res_v"] = local_sigma_v
            rep["start_idx"] = int(start_idx)
            rep["end_idx"] = int(end_idx)
            rep["regime_name"] = f"Régimen {len(regime_reports) + 1} (Velas {start_idx}-{end_idx})"
            rep["is_active"] = bool(is_last)
            regime_reports.append(rep)

            if is_last:
                active_discoverer = disc_reg

        if regime_reports:
            active_report = regime_reports[-1]
        else:
            active_report = physics_report_global
            active_report["start_idx"] = 0
            active_report["end_idx"] = int(len(t))
            active_report["sigma_res_r"] = sigma_res_r
            active_report["sigma_res_v"] = sigma_res_v
            active_report["regime_name"] = f"Régimen Global (Velas 0-{len(t)})"
            active_report["is_active"] = True
            active_discoverer = disc_global

        active_report["blender_mse"] = float(telemetry_r["mse"])
        active_report["blender_mse_v"] = float(telemetry_v["mse"])
        active_report["cusum_runtime"] = float(cusum_report["runtime_ms"])

        return {
            "r_smooth": r_smooth,
            "r_dot": r_dot,
            "r_dot2": r_dot2,
            "v_smooth": v_smooth,
            "v_dot": v_dot,
            "v_dot2": v_dot2,
            "cusum_report": cusum_report,
            "boundaries": boundaries,
            "unconsolidated_break": unconsolidated_break,
            "unconsolidated_idx": unconsolidated_idx,
            "physics_report_global": physics_report_global,
            "regime_reports": regime_reports,
            "active_report": active_report,
            "active_discoverer": active_discoverer,
        }

    def _solve_analytical_fast(
        self,
        symbolic: SymbolicTranslator,
        active_discoverer: PhysicsDiscoverer,
        p0: float,
        v0: float,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Resuelve analíticamente el sistema acoplado sin bloquear el proceso principal:
          - Para `poly_degree == 1`: descompone espectralmente la matriz 2x2 A en <1 ms.
          - Para `poly_degree >= 2`: ejecuta `SymbolicTranslator` en hilo `daemon=True` con corte de 2.0 s.
        """
        var_name = "P" if self.cfg.disable_returns else "r"
        coefs = np.asarray(active_discoverer.model.coefficients(), dtype=np.float64)

        if self.cfg.poly_degree == 1 and coefs.shape == (2, 3):
            b_vec = coefs[:, 0]
            a_mat = coefs[:, 1:3]
            eigvals, eigvecs = np.linalg.eig(a_mat)
            l1, l2 = complex(eigvals[0]), complex(eigvals[1])
            det_a = float(np.linalg.det(a_mat))

            if abs(det_a) > 1e-10:
                x_eq = -np.linalg.solve(a_mat, b_vec)
                eq_r = float(x_eq[0])
                eq_v = float(x_eq[1])
                has_eq = True
            else:
                x_eq = np.zeros(2, dtype=np.float64)
                eq_r, eq_v = 0.0, 0.0
                has_eq = False

            max_real = max(l1.real, l2.real)
            is_complex = abs(l1.imag) > 1e-7

            if is_complex:
                omega = abs(l1.imag)
                period_osc = (2.0 * np.pi / omega) if omega > 1e-8 else None
                if max_real < -1e-6:
                    stab_type = "FOCO_ESPIRAL_ESTABLE_AMORTIGUADO"
                elif max_real > 1e-6:
                    stab_type = "FOCO_ESPIRAL_EXPANSIVO_INESTABLE"
                else:
                    stab_type = "CENTRO_ARMONICO_CONSERVATIVO"

                alpha = l1.real
                x0_shift = np.array([p0, v0], dtype=np.float64) - x_eq
                c_cos = float(x0_shift[0])
                dr0 = float(a_mat[0, 0] * x0_shift[0] + a_mat[0, 1] * x0_shift[1])
                c_sin = (dr0 - alpha * c_cos) / omega if omega > 1e-8 else 0.0

                latex_sol = (
                    f"$${var_name}(t) = {eq_r:+.5f} + e^{{{alpha:+.5f} t}} "
                    f"\\left( {c_cos:+.5f} \\cos({omega:.5f} t) {c_sin:+.5f} \\sin({omega:.5f} t) \\right)$$"
                )
            else:
                period_osc = None
                r1, r2 = float(l1.real), float(l2.real)
                if r1 * r2 < -1e-10:
                    stab_type = "PUNTO_DE_SILLA_HIPERBOLICO"
                elif max_real < -1e-6:
                    stab_type = "NODO_ATRACTOR_ESTABLE"
                elif max_real > 1e-6:
                    stab_type = "NODO_REPULSOR_EXPANSIVO"
                else:
                    stab_type = "DERIVA_MARGINAL_NEUTRA"

                x0_shift = np.array([p0, v0], dtype=np.float64) - x_eq
                try:
                    v_real = np.real(eigvecs)
                    c_vec = np.linalg.solve(v_real, x0_shift)
                    k1 = float(v_real[0, 0] * c_vec[0])
                    k2 = float(v_real[0, 1] * c_vec[1])
                    latex_sol = (
                        f"$${var_name}(t) = {eq_r:+.5f} {k1:+.5f} e^{{{r1:+.5f} t}} {k2:+.5f} e^{{{r2:+.5f} t}}$$"
                    )
                except np.linalg.LinAlgError:
                    latex_sol = f"$${var_name}(t) \\approx {p0:+.5f} e^{{{r1:+.5f} t}}$$"

            spec_diag = {
                "eigenvalues": [
                    {"real": round(float(l1.real), 6), "imag": round(float(l1.imag), 6)},
                    {"real": round(float(l2.real), 6), "imag": round(float(l2.imag), 6)},
                ],
                "lyapunov_max_real_part": round(float(max_real), 6),
                "is_linearly_stable": bool(max_real <= 0.0),
                "stability_regime": stab_type,
                "intrinsic_oscillation_period_candles": round(float(period_osc), 2) if period_osc else None,
                "equilibrium_point": (
                    {"r_pct_eq": round(eq_r, 5), "v_z_eq": round(eq_v, 5)} if has_eq else None
                ),
            }
            return latex_sol, spec_diag

        holder: Dict[str, str] = {}

        def _worker() -> None:
            try:
                holder["sol"] = symbolic.generate_analytical_solution(
                    p0=p0, v0=v0, disable_returns=self.cfg.disable_returns
                )
            except Exception:
                holder["sol"] = (
                    "Sistema No-Lineal Acoplado: sin solución analítica elemental cerrada; usar Cono Numérico."
                )

        th = threading.Thread(target=_worker, daemon=True)
        th.start()
        th.join(timeout=2.0)
        sol_str = holder.get(
            "sol",
            "Sistema No-Lineal Complejo: límite térmico simbólico (2.0 s) alcanzado; rigiendo integración numérica Euler-Maruyama.",
        )
        return sol_str, {"stability_regime": "NO_LINEAL_POLINOMICO", "degree": int(self.cfg.poly_degree)}

    def _compute_ljung_box_seal(
        self,
        log_returns: np.ndarray,
        r_smooth: np.ndarray,
        v_smooth: np.ndarray,
        r_dot: np.ndarray,
        v_dot: np.ndarray,
        active_report: Dict[str, Any],
        active_discoverer: PhysicsDiscoverer,
    ) -> Dict[str, Any]:
        """Evalúa blancura residual (Ljung-Box) sobre residuos del Spline y de la EDO SINDy."""
        start_i = int(active_report.get("start_idx", 0))
        end_i = int(active_report.get("end_idx", len(log_returns)))

        res_spline = log_returns[start_i:end_i] - r_smooth[start_i:end_i]

        x_slice = np.column_stack((r_smooth[start_i:end_i], v_smooth[start_i:end_i])).astype(np.float64)
        xdot_slice = np.column_stack((r_dot[start_i:end_i], v_dot[start_i:end_i])).astype(np.float64)

        if not self.cfg.disable_norm:
            if not self.cfg.disable_returns:
                x_slice[:, 0] *= 100.0
                xdot_slice[:, 0] *= 100.0
            mu_v = float(np.mean(x_slice[:, 1]))
            sig_v = float(np.std(x_slice[:, 1]))
            if sig_v < 1e-8:
                sig_v = 1.0
            x_slice[:, 1] = (x_slice[:, 1] - mu_v) / sig_v
            xdot_slice[:, 1] = xdot_slice[:, 1] / sig_v

        try:
            raw_pred = active_discoverer.model.predict(x_slice)
            pred_xdot = np.array(np.asarray(raw_pred).view(np.ndarray), dtype=np.float64, copy=True)
            res_sindy = np.array(xdot_slice[:, 0] - pred_xdot[:, 0], dtype=np.float64, copy=True)
        except Exception:
            res_sindy = np.zeros_like(res_spline, dtype=np.float64)

        def _eval_lb(series: np.ndarray) -> Dict[str, Any]:
            series = np.array(np.asarray(series).view(np.ndarray), dtype=np.float64, copy=True)
            n_obs = len(series)
            valid_lags = [lag for lag in (5, 10, 20) if lag < max(2, n_obs // 3)]
            if not valid_lags or float(np.std(series)) < 1e-12:
                return {
                    "tested_lags": [],
                    "p_values": {},
                    "is_white_noise_alpha_05": None,
                    "note": "Muestra corta o varianza nula para test asintótico.",
                }
            lb_df = acorr_ljungbox(series, lags=valid_lags, return_df=True)
            p_map = {f"lag_{int(lag)}": round(float(lb_df.loc[lag, "lb_pvalue"]), 5) for lag in valid_lags}
            ref_lag = f"lag_{10 if 10 in valid_lags else valid_lags[-1]}"
            is_wn = bool(p_map[ref_lag] > 0.05)
            return {
                "tested_lags": valid_lags,
                "p_values": p_map,
                "reference_lag": ref_lag,
                "reference_p_value": p_map[ref_lag],
                "is_white_noise_alpha_05": is_wn,
            }

        lb_spline = _eval_lb(res_spline)
        lb_sindy = _eval_lb(res_sindy)

        spline_wn = lb_spline.get("is_white_noise_alpha_05")

        if spline_wn is True:
            verdict = "RUIDO_BLANCO_CERTIFICADO (El suavizado topológico aisló la señal sin dejar autocorrelación lineal fuerte en el residuo)."
        elif spline_wn is False:
            verdict = "ESTRUCTURA_RESIDUAL_PRESENTE (p <= 0.05: existen micro-oscilaciones o choques seriados no absorbidos por el Spline actual)."
        else:
            verdict = "INDETERMINADO_POR_VENTANA_CORTA"

        return {
            "spline_residuals": lb_spline,
            "sindy_ode_residuals": lb_sindy,
            "verdict": verdict,
        }

    def _compute_fast_walk_forward_seal(
        self,
        price_full: np.ndarray,
        vol_raw_full: np.ndarray,
        dt_val: float,
        effective_tol: float,
        effective_k: float,
    ) -> Dict[str, Any]:
        """
        Ejecuta el Mini Walk-Forward sin fuga de datos (Out-of-Sample estricto):
          - En modo estricto (`strict_wf_window=True` y `context_window > 0`), SOLO admite cortes `c`
            con ventana de entrenamiento completa (`len(p_train) == context_window`), sin truncar.
          - Reporta `effective_cuts` y, si es menor que `min_wf_effective_cuts` (por defecto 5),
            el sello queda como `INSUFICIENTE` (`seal_approved = False`).
        """
        cfg = self.cfg
        n_total = len(price_full)
        req_window = int(cfg.context_window) if cfg.context_window > 0 else 0
        min_req_cuts = int(cfg.min_wf_effective_cuts)
        eff_wf_cuts = int(cfg.wf_cuts) if int(cfg.wf_cuts) > 0 else (10 if bool(cfg.audit_oos) else 0)

        empty_cone_cal = {
            "evaluated": False,
            "target_iqr_coverage_pct": 50.0,
            "empirical_p25_p75_coverage_pct": None,
            "empirical_p5_p95_coverage_pct": None,
            "iqr_calibration_bias_pts": None,
            "calibration_label": "No evaluado",
        }

        if eff_wf_cuts <= 0:
            return {
                "executed": False,
                "strict_full_window_enforced": bool(cfg.strict_wf_window and req_window > 0),
                "required_window_candles": req_window,
                "min_required_effective_cuts": min_req_cuts,
                "effective_cuts": 0,
                "seal_approved": False,
                "reason": "Walk-Forward OOS omitido por defecto en v0.3.1 (activar con --audit-oos).",
                "asset_physics_class": "NO_EVALUADO",
                "cone_calibration": empty_cone_cal,
            }

        eval_h = min(cfg.horizon_steps, max(20, min(90, n_total // 6)))
        max_cut = n_total - eval_h

        if cfg.strict_wf_window and req_window > 0:
            # Acotar el inicio a eras de mercado modernas (~15 años / 2x ventana) manteniendo ventana completa W
            modern_span = max(3650, 2 * req_window)
            min_cut = max(req_window, n_total - modern_span - eval_h)
            min_stride = max(5, eval_h // 12)

            if max_cut < req_window:
                return {
                    "executed": True,
                    "strict_full_window_enforced": True,
                    "required_window_candles": req_window,
                    "eval_horizon_candles": int(eval_h),
                    "min_required_effective_cuts": min_req_cuts,
                    "total_cuts": 0,
                    "valid_cuts": 0,
                    "effective_cuts": 0,
                    "validity_rate_pct": 0.0,
                    "seal_approved": False,
                    "asset_physics_class": "INSUFICIENTE",
                    "cone_calibration": empty_cone_cal,
                    "reason": (
                        f"Historial total ({n_total}v) insuficiente para formar al menos 1 corte OOS "
                        f"de ventana completa ({req_window}v + horizonte {eval_h}v)."
                    ),
                    "interpretation": (
                        f"Sello INSUFICIENTE (0/{min_req_cuts} cortes efectivos de ventana completa {req_window}v): "
                        "no aprueba validación OOS."
                    ),
                }

            max_possible_cuts = ((max_cut - min_cut) // min_stride) + 1
            n_place = min(eff_wf_cuts, int(max_possible_cuts))
            if n_place <= 1:
                cut_indices = [int(max_cut)]
            else:
                cut_indices = sorted(
                    list(set(int(c) for c in np.linspace(min_cut, max_cut, num=n_place, dtype=int)))
                )
        else:
            min_train = max(120, min(250, n_total // 3))
            if max_cut <= min_train + 20:
                return {
                    "executed": False,
                    "strict_full_window_enforced": False,
                    "required_window_candles": req_window,
                    "min_required_effective_cuts": min_req_cuts,
                    "effective_cuts": 0,
                    "seal_approved": False,
                    "reason": "Historial insuficiente para validación Walk-Forward Out-of-Sample.",
                    "asset_physics_class": "NO_EVALUADO",
                    "cone_calibration": empty_cone_cal,
                }
            cut_indices = sorted(
                list(set(int(c) for c in np.linspace(min_train, max_cut, num=eff_wf_cuts, dtype=int)))
            )

        short_step = min(10, eval_h)
        mid_step = min(30, eval_h)

        hits_short: List[float] = []
        hits_mid: List[float] = []
        hits_full: List[float] = []
        profits_full: List[float] = []
        mapes_full: List[float] = []
        naive_mapes_full: List[float] = []
        r2_list: List[float] = []
        cov_iqr_cuts: List[float] = []
        cov_90_cuts: List[float] = []
        train_lengths_used: List[int] = []
        valid_count = 0

        eps = 1e-8
        k_steps_arr = np.arange(1, eval_h + 1, dtype=np.float64) * max(dt_val, 1e-8)
        sqrt_k_arr = np.sqrt(k_steps_arr)

        for cut in cut_indices:
            win_start = (cut - req_window) if req_window > 0 else 0
            if cfg.strict_wf_window and req_window > 0 and win_start < 0:
                continue
            win_start = max(0, win_start)

            p_train = np.ascontiguousarray(price_full[win_start:cut], dtype=np.float64)
            v_train_raw = np.ascontiguousarray(vol_raw_full[win_start:cut], dtype=np.float64)
            p_future = np.ascontiguousarray(price_full[cut : cut + eval_h], dtype=np.float64)

            if cfg.strict_wf_window and req_window > 0 and len(p_train) != req_window:
                continue
            if len(p_train) < 60 or len(p_future) < eval_h:
                continue

            # Normalización estrictamente In-Sample (cero data leakage)
            if cfg.disable_returns or cfg.disable_norm:
                r_train = p_train.copy()
            else:
                p_safe = np.maximum(p_train, eps)
                r_train = np.zeros_like(p_safe)
                r_train[1:] = np.log(p_safe[1:] / p_safe[:-1])

            if cfg.disable_norm:
                v_train = v_train_raw.copy()
            else:
                v_m = float(np.mean(v_train_raw))
                v_s = float(np.std(v_train_raw))
                v_train = (v_train_raw - v_m) / v_s if v_s > eps else (v_train_raw - v_m)

            t_sub = np.arange(len(r_train), dtype=np.float64) * dt_val

            try:
                fft_r = SpectralAnalyzer._compute_fft(r_train, dt_val, 2)
                fft_v = SpectralAnalyzer._compute_fft(v_train, dt_val, 2)

                wf_tol = float(effective_tol)
                b_sub = ContinuousBlender(tolerance=wf_tol)
                b_sub.fit(t_sub, r_train, fft_r["periods"], 0)
                b_sub.fit(t_sub, v_train, fft_v["periods"], 1)
                rs, rd, _ = b_sub.compute_continuous(0, t_sub)
                vs, vd, _ = b_sub.compute_continuous(1, t_sub)

                xm_all = np.ascontiguousarray(np.column_stack((rs, vs)), dtype=np.float64)
                xdm_all = np.ascontiguousarray(np.column_stack((rd, vd)), dtype=np.float64)

                # Calibración causal In-Sample de k por corte
                if cfg.cusum_k is not None:
                    best_cut_k = float(cfg.cusum_k)
                else:
                    total_sub = len(t_sub)
                    disc_tune = PhysicsDiscoverer(poly_degree=1)
                    seg_r2_cache: Dict[Tuple[int, int], float] = {}
                    shift_fit_cache: Dict[Tuple[int, ...], float] = {}
                    best_cut_k = 1.0
                    best_cut_fit = -np.inf

                    for k_cand in (0.4, 0.7, 1.0, 1.4, 1.8, 2.2, 2.8, 3.6, 4.5):
                        det_k = RegimeShiftDetector(threshold=cfg.cusum_h, drift=float(k_cand))
                        sh_idx = det_k.detect(r_train, rs)["shift_indices"]
                        sh_key = tuple(sh_idx)

                        if sh_key not in shift_fit_cache:
                            b_cand = [0] + sh_idx + [total_sub]
                            w_r2 = 0.0
                            for bi in range(len(b_cand) - 1):
                                sa, ea = b_cand[bi], b_cand[bi + 1]
                                if ea - sa < 15:
                                    continue
                                if (sa, ea) not in seg_r2_cache:
                                    rep_seg = disc_tune.extract_equations(
                                        t=t_sub[sa:ea],
                                        x=xm_all[sa:ea],
                                        x_dot=xdm_all[sa:ea],
                                        dt=dt_val,
                                        horizon_steps=1,
                                        sigma_res_r=0.0,
                                        sigma_res_v=0.0,
                                        last_price=float(p_train[ea - 1]),
                                        disable_norm=cfg.disable_norm,
                                        disable_returns=cfg.disable_returns,
                                    )
                                    seg_r2_cache[(sa, ea)] = max(0.0, float(rep_seg.get("score", 0.0)))
                                w_r2 += seg_r2_cache[(sa, ea)] * ((ea - sa) / float(total_sub))
                            shift_fit_cache[sh_key] = w_r2 / (1.0 + 0.1 * len(sh_idx))

                        fit_val = shift_fit_cache[sh_key]
                        if fit_val > best_cut_fit:
                            best_cut_fit = fit_val
                            best_cut_k = float(k_cand)

                det_sub = RegimeShiftDetector(threshold=cfg.cusum_h, drift=best_cut_k)
                c_rep = det_sub.detect(r_train, rs)
                bounds, _, _ = self._build_effective_boundaries(
                    c_rep["shift_indices"], len(t_sub), min_len=15
                )
                s_reg = bounds[-2]
                e_reg = bounds[-1]

                disc_sub = PhysicsDiscoverer(poly_degree=cfg.poly_degree)
                xm = np.ascontiguousarray(xm_all[s_reg:e_reg], dtype=np.float64)
                xdm = np.ascontiguousarray(xdm_all[s_reg:e_reg], dtype=np.float64)

                p_rep = disc_sub.extract_equations(
                    t=t_sub[s_reg:e_reg],
                    x=xm,
                    x_dot=xdm,
                    dt=dt_val,
                    horizon_steps=eval_h,
                    sigma_res_r=0.0,
                    sigma_res_v=0.0,
                    last_price=float(p_train[-1]),
                    disable_norm=cfg.disable_norm,
                    disable_returns=cfg.disable_returns,
                )
                det_path = np.asarray(p_rep.get("prediction", {}).get("det_price_path", []), dtype=np.float64)
            except Exception:
                continue

            last_p = float(p_train[-1])
            is_bad = (
                len(det_path) != eval_h
                or p_rep.get("empty_r_eq", False)
                or not np.all(np.isfinite(det_path))
                or float(np.max(np.abs(det_path))) > 1e4 * abs(last_p)
            )
            if is_bad:
                continue

            valid_count += 1
            train_lengths_used.append(int(len(p_train)))
            r2_list.append(float(p_rep.get("score", 0.0)))

            def _dir_hit(pred_end: float, act_end: float) -> float:
                return 1.0 if np.sign(pred_end - last_p) == np.sign(act_end - last_p) else 0.0

            hits_short.append(_dir_hit(float(det_path[short_step - 1]), float(p_future[short_step - 1])))
            hits_mid.append(_dir_hit(float(det_path[mid_step - 1]), float(p_future[mid_step - 1])))
            hits_full.append(_dir_hit(float(det_path[-1]), float(p_future[-1])))

            pred_sign = float(np.sign(det_path[-1] - last_p))
            act_ret_pct = ((float(p_future[-1]) - last_p) / last_p) * 100.0
            profits_full.append(pred_sign * act_ret_pct)

            mape_val = float(np.mean(np.abs((p_future - det_path) / p_future)) * 100.0)
            naive_val = float(np.mean(np.abs((p_future - last_p) / p_future)) * 100.0)
            mapes_full.append(mape_val)
            naive_mapes_full.append(naive_val)

            # Calibración causal OOS del cono de integración simple (Decisión 2, no bloqueante)
            classic_cut = bool(cfg.disable_returns or cfg.disable_norm)
            if classic_cut:
                res_cut = np.diff(p_train - rs) if len(p_train) > 2 else (p_train - rs)
                sigma_cut = self._estimate_ewma_return_sigma(res_cut, span=30)
                err_abs = np.abs(p_future - det_path)
                half_iqr = 0.67448975 * sigma_cut * sqrt_k_arr
                half_90 = 1.64485363 * sigma_cut * sqrt_k_arr
                cov_iqr_cuts.append(float(np.mean(err_abs <= half_iqr) * 100.0))
                cov_90_cuts.append(float(np.mean(err_abs <= half_90) * 100.0))
            else:
                res_cut = r_train - rs
                sigma_cut = self._estimate_ewma_return_sigma(res_cut, span=30)
                det_safe = np.maximum(det_path, eps)
                fut_safe = np.maximum(p_future, eps)
                log_err = np.abs(np.log(fut_safe) - np.log(det_safe))
                half_iqr = 0.67448975 * sigma_cut * sqrt_k_arr
                half_90 = 1.64485363 * sigma_cut * sqrt_k_arr
                cov_iqr_cuts.append(float(np.mean(log_err <= half_iqr) * 100.0))
                cov_90_cuts.append(float(np.mean(log_err <= half_90) * 100.0))

        total_cuts = len(cut_indices)
        if valid_count == 0:
            insufficient_flag = cfg.strict_wf_window and total_cuts < min_req_cuts
            cls_zero = "INSUFICIENTE" if insufficient_flag else "INESTABLE_O_RUIDO_EXTREMO"
            return {
                "executed": True,
                "strict_full_window_enforced": bool(cfg.strict_wf_window and req_window > 0),
                "required_window_candles": req_window,
                "eval_horizon_candles": int(eval_h),
                "min_required_effective_cuts": min_req_cuts,
                "total_cuts": int(total_cuts),
                "valid_cuts": 0,
                "effective_cuts": 0,
                "validity_rate_pct": 0.0,
                "seal_approved": False,
                "asset_physics_class": cls_zero,
                "cone_calibration": empty_cone_cal,
                "warning": "Ningún corte histórico de ventana completa produjo una EDO predictiva válida.",
                "interpretation": (
                    f"Sello {cls_zero} (0/{min_req_cuts} cortes efectivos): no aprueba validación OOS."
                ),
            }

        hr_short = float(np.mean(hits_short) * 100.0)
        hr_mid = float(np.mean(hits_mid) * 100.0)
        hr_full = float(np.mean(hits_full) * 100.0)
        hr_consensus = 0.5 * hr_mid + 0.5 * hr_full
        med_mape = float(np.median(mapes_full))
        med_naive = float(np.median(naive_mapes_full))

        cov_iqr_pct = float(np.mean(cov_iqr_cuts)) if cov_iqr_cuts else 0.0
        cov_90_pct = float(np.mean(cov_90_cuts)) if cov_90_cuts else 0.0
        iqr_bias = cov_iqr_pct - 50.0
        if 38.0 <= cov_iqr_pct <= 62.0:
            cal_label = "Bien calibrado"
        elif cov_iqr_pct > 62.0:
            cal_label = "Banda conservadora (amplia)"
        else:
            cal_label = "Banda estrecha"

        cone_calibration = {
            "evaluated": True,
            "target_iqr_coverage_pct": 50.0,
            "empirical_p25_p75_coverage_pct": round(cov_iqr_pct, 2),
            "empirical_p5_p95_coverage_pct": round(cov_90_pct, 2),
            "iqr_calibration_bias_pts": round(iqr_bias, 2),
            "calibration_label": cal_label,
        }

        if valid_count < min_req_cuts:
            phys_class = "INSUFICIENTE"
            seal_approved = False
            class_note = (
                f"Sello INSUFICIENTE ({valid_count}/{min_req_cuts} cortes efectivos con ventana completa "
                f"de {req_window}v): muestra OOS insuficiente para aprobar el sello."
            )
        elif hr_consensus >= 55.0:
            phys_class = "COHERENTE_INERCIAL"
            seal_approved = True
            class_note = (
                f"El activo exhibe memoria inercial explotable ({hr_consensus:.1f}% HR OOS en "
                f"{valid_count} cortes de ventana completa)."
            )
        elif hr_consensus >= 50.0:
            phys_class = "TRANSICIONAL_BORDE"
            seal_approved = True
            class_note = (
                f"Coherencia física parcial ({hr_consensus:.1f}% HR OOS en {valid_count} cortes); "
                "exigir confirmación de baja tensión CUSUM y catalizadores."
            )
        else:
            phys_class = "EXOGENO_FUNDAMENTALISTA"
            seal_approved = False
            class_note = (
                f"Alerta Caso GLD ({hr_consensus:.1f}% HR OOS < 50% en {valid_count} cortes): "
                "dinámica dominada por choques exógenos/macro fuera del plano (r, V)."
            )

        return {
            "audit_enabled": True,
            "executed": True,
            "strict_full_window_enforced": bool(cfg.strict_wf_window and req_window > 0),
            "required_window_candles": req_window,
            "min_train_candles_used": int(min(train_lengths_used)) if train_lengths_used else 0,
            "max_train_candles_used": int(max(train_lengths_used)) if train_lengths_used else 0,
            "eval_horizon_candles": int(eval_h),
            "min_required_effective_cuts": min_req_cuts,
            "total_cuts": int(total_cuts),
            "valid_cuts": int(valid_count),
            "effective_cuts": int(valid_count),
            "validity_rate_pct": round((valid_count / max(total_cuts, 1)) * 100.0, 2),
            "seal_approved": bool(seal_approved),
            f"hit_ratio_t{short_step}_pct": round(hr_short, 2),
            f"hit_ratio_t{mid_step}_pct": round(hr_mid, 2),
            f"hit_ratio_t{eval_h}_pct": round(hr_full, 2),
            "consensus_hit_ratio_pct": round(hr_consensus, 2),
            "mean_directional_profit_pct": round(float(np.mean(profits_full)), 2),
            "median_mape_pct": round(med_mape, 2),
            "median_naive_mape_pct": round(med_naive, 2),
            "mape_alpha_vs_naive_pct": round(med_naive - med_mape, 2),
            "mean_historical_r2": round(float(np.mean(r2_list)), 4),
            "cone_calibration": cone_calibration,
            "asset_physics_class": phys_class,
            "interpretation": class_note,
        }

    @staticmethod
    def evaluate_double_seal(
        lb_seal: Dict[str, Any],
        wf_seal: Dict[str, Any],
        active_r2: float,
        tension_ratio: float,
        is_unstable: bool,
        empty_eq: bool,
        geometric_fallback_used: bool = False,
    ) -> Dict[str, Any]:
        """
        Consolida diagnóstico geométrico v0.3.1 + Ljung-Box (+ Walk-Forward OOS solo si --audit-oos).
        Elimina bloqueos por SINDy R² < 0.35 o por omisión de Walk-Forward.
        """
        reasons: List[str] = []
        spline_wn = lb_seal.get("spline_residuals", {}).get("is_white_noise_alpha_05")
        wf_cls = wf_seal.get("asset_physics_class", "NO_EVALUADO")
        eff_cuts = int(wf_seal.get("effective_cuts", wf_seal.get("valid_cuts", 0)))
        min_cuts = int(wf_seal.get("min_required_effective_cuts", 5))
        hr_pct = wf_seal.get("consensus_hit_ratio_pct")

        if (is_unstable or empty_eq) and not geometric_fallback_used:
            reasons.append("Fallo de estabilidad SINDy o ecuación de retorno anulada sin respaldo cinemático.")
            return {
                "seal_passed": False,
                "geometric_valid": False,
                "seal_grade": "FALLO_ESTABILIDAD",
                "wf_passed": False,
                "ljung_box_spline_white_noise": spline_wn,
                "effective_oos_cuts": eff_cuts,
                "min_required_oos_cuts": min_cuts,
                "reasons": reasons,
            }

        if geometric_fallback_used:
            reasons.append("Inestabilidad o dr/dt=0 SINDy cubierta con respaldo cinemático amortiguado sobre la variedad.")

        if wf_cls == "NO_EVALUADO":
            reasons.append("Enfoque geométrico puro v0.3.1 (Walk-Forward OOS omitido; activar con --audit-oos).")
            if spline_wn is False:
                reasons.append("Ljung-Box detecta autocorrelación residual en el Spline (p <= 0.05).")
            elif spline_wn is True:
                reasons.append("Ljung-Box certifica ruido blanco en residuos del Spline (p > 0.05).")
            if tension_ratio > 0.85:
                reasons.append(f"Tensión CUSUM elevada ({tension_ratio:.0%} de H).")
            return {
                "seal_passed": True,
                "geometric_valid": True,
                "seal_grade": "GEOMETRICO_PURO",
                "wf_passed": None,
                "ljung_box_spline_white_noise": spline_wn,
                "effective_oos_cuts": eff_cuts,
                "min_required_oos_cuts": min_cuts,
                "reasons": reasons,
            }

        if wf_cls == "INSUFICIENTE" or eff_cuts < min_cuts:
            reasons.append(f"Auditoría --audit-oos: cortes efectivos insuficientes ({eff_cuts}/{min_cuts}).")
            return {
                "seal_passed": False,
                "geometric_valid": True,
                "seal_grade": "INSUFICIENTE",
                "wf_passed": False,
                "ljung_box_spline_white_noise": spline_wn,
                "effective_oos_cuts": eff_cuts,
                "min_required_oos_cuts": min_cuts,
                "reasons": reasons,
            }

        if wf_cls in ("EXOGENO_FUNDAMENTALISTA", "INESTABLE_O_RUIDO_EXTREMO"):
            reasons.append(f"Auditoría --audit-oos reprobada ({wf_cls}, HR={hr_pct}%).")
            return {
                "seal_passed": False,
                "geometric_valid": True,
                "seal_grade": "REPROBADO_EXOGENO",
                "wf_passed": False,
                "ljung_box_spline_white_noise": spline_wn,
                "effective_oos_cuts": eff_cuts,
                "min_required_oos_cuts": min_cuts,
                "reasons": reasons,
            }

        # Walk-Forward aprobado (COHERENTE_INERCIAL o TRANSICIONAL_BORDE)
        reasons.append(f"Auditoría --audit-oos aprobada ({wf_cls}, HR={hr_pct}%, {eff_cuts} cortes). SINDy R² informativo={active_r2:.3f}.")
        conditional = bool(geometric_fallback_used)
        if wf_cls == "TRANSICIONAL_BORDE":
            conditional = True
            reasons.append("Coherencia OOS en franja transicional (50%-55%).")
        if spline_wn is False:
            conditional = True
            reasons.append("Ljung-Box detecta autocorrelación residual en el Spline (p <= 0.05).")
        elif spline_wn is True:
            reasons.append("Ljung-Box certifica ruido blanco en residuos del Spline (p > 0.05).")
        if tension_ratio > 0.85:
            conditional = True
            reasons.append(f"Tensión CUSUM elevada ({tension_ratio:.0%} de H).")

        return {
            "seal_passed": True,
            "geometric_valid": True,
            "seal_grade": "APROBADO_CONDICIONAL" if conditional else "APROBADO_PLENO",
            "wf_passed": True,
            "ljung_box_spline_white_noise": spline_wn,
            "effective_oos_cuts": eff_cuts,
            "min_required_oos_cuts": min_cuts,
            "reasons": reasons,
        }

    def _extract_geometry_and_forensics(
        self,
        dates_active: List[str],
        precio_raw: np.ndarray,
        nominal_smooth: np.ndarray,
        log_returns: np.ndarray,
        r_smooth: np.ndarray,
        r_dot: np.ndarray,
        r_dot2: np.ndarray,
        v_smooth: np.ndarray,
        v_dot: np.ndarray,
        cusum_report: Dict[str, Any],
        boundaries: List[int],
        unconsolidated_break: bool,
        unconsolidated_idx: Optional[int],
        regime_reports: List[Dict[str, Any]],
        active_report: Dict[str, Any],
        effective_k: float,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], np.ndarray, np.ndarray]:
        """
        Traduce las curvas continuas, brecha precio-variedad, espacio de fase, quiebres CUSUM
        y cono Monte Carlo a descriptores geométricos exactos para consumo directo por agentes de IA.
        """
        cfg = self.cfg
        scale = 1.0 if cfg.disable_returns else 100.0

        # 1. Cinemática (Velocidad dr/dt vs Aceleración d²r/dt²) + Brecha Precio-Variedad
        vel_now = float(r_dot[-1] * scale)
        acc_now = float(r_dot2[-1] * scale)
        vol_vel_now = float(v_dot[-1])

        if vel_now > 0 and acc_now > 0:
            quadrant = "Q1_IMPULSO_ALCISTA_ACELERANDO"
            kin_desc = "Velocidad positiva y aceleración positiva: avance alcista ganando fuerza (curvatura convexa)."
        elif vel_now > 0 and acc_now <= 0:
            quadrant = "Q2_AVANCE_ALCISTA_FRENANDO"
            kin_desc = "Velocidad aún positiva pero aceleración negativa: subida perdiendo impulso (posible formación de techo/curvatura cóncava)."
        elif vel_now <= 0 and acc_now < 0:
            quadrant = "Q3_CAIDA_BAJISTA_ACELERANDO"
            kin_desc = "Velocidad negativa y aceleración negativa: presión vendedora en expansión."
        else:
            quadrant = "Q4_CAIDA_BAJISTA_FRENANDO"
            kin_desc = "Velocidad negativa pero aceleración positiva: desaceleración de la caída (absorción / posible suelo cinemático)."

        last_price = float(precio_raw[-1])
        spline_price_now = float(nominal_smooth[-1])
        gap_now_pct = (
            ((last_price - spline_price_now) / spline_price_now) * 100.0
            if abs(spline_price_now) > 1e-8
            else 0.0
        )
        tail_n = min(30, len(precio_raw))
        denom_tail = np.maximum(np.abs(nominal_smooth[-tail_n:]), 1e-8)
        gap_30c_pct = float(np.mean((precio_raw[-tail_n:] - nominal_smooth[-tail_n:]) / denom_tail) * 100.0)

        # Últimos cruces por cero de velocidad (extremos locales) y aceleración (inflexiones)
        vel_signs = np.sign(r_dot)
        vel_cross_idx = np.where(np.diff(vel_signs) != 0)[0] + 1
        recent_extrema = []
        for idx in vel_cross_idx[-4:]:
            idx_i = int(idx)
            kind = "SUELO_LOCAL_GIRO_ALZA" if r_dot[idx_i] > 0 else "TECHO_LOCAL_GIRO_BAJA"
            recent_extrema.append(
                {
                    "candle_idx": idx_i,
                    "candles_ago": int(len(precio_raw) - 1 - idx_i),
                    "date": dates_active[idx_i],
                    "price": round(float(precio_raw[idx_i]), 4),
                    "type": kind,
                }
            )

        acc_signs = np.sign(r_dot2)
        acc_cross_idx = np.where(np.diff(acc_signs) != 0)[0] + 1
        recent_inflections = []
        for idx in acc_cross_idx[-4:]:
            idx_i = int(idx)
            recent_inflections.append(
                {
                    "candle_idx": idx_i,
                    "candles_ago": int(len(precio_raw) - 1 - idx_i),
                    "date": dates_active[idx_i],
                    "price": round(float(precio_raw[idx_i]), 4),
                    "transition": "CONCAVO_A_CONVEXO (+d²r)" if r_dot2[idx_i] > 0 else "CONVEXO_A_CONCAVO (-d²r)",
                }
            )

        # 2. Topología del Atractor de Espacio de Fase (Escalas Homogéneas + Sentido de Giro)
        act_s = int(active_report.get("start_idx", 0))
        act_e = int(active_report.get("end_idx", len(r_smooth)))

        r_pct_series = r_smooth * scale
        r_act = r_pct_series[act_s:act_e]
        v_act = v_smooth[act_s:act_e]

        r_std = float(np.std(r_act)) or 1.0
        v_std = float(np.std(v_act)) or 1.0
        r_norm = (r_act - float(np.mean(r_act))) / r_std
        v_norm = (v_act - float(np.mean(v_act))) / v_std

        radii = np.sqrt(r_norm**2 + v_norm**2)
        r_now_orb = float(radii[-1])
        r_med_orb = float(np.median(radii)) if len(radii) > 0 else 1.0
        if r_med_orb < 1e-8:
            r_med_orb = 1.0
        radius_ratio = r_now_orb / r_med_orb
        radial_slope = float(radii[-1] - np.mean(radii[-min(5, len(radii)) :]))

        # Momento angular medio en el plano (V_norm, r_norm) para identificar giro horario/antihorario
        if len(v_norm) >= 3:
            dv_orb = np.diff(v_norm)
            dr_orb = np.diff(r_norm)
            ang_cross = float(np.mean(v_norm[:-1] * dr_orb - r_norm[:-1] * dv_orb))
            if ang_cross > 1e-4:
                rot_sense = "ANTIHORARIO (Volumen antecede al retorno)"
            elif ang_cross < -1e-4:
                rot_sense = "HORARIO (Retorno antecede al volumen)"
            else:
                rot_sense = "CUASI_COLINEAL"
        else:
            rot_sense = "INDETERMINADO"

        if radius_ratio < 0.60:
            attractor_state = "COMPRESION_EQUILIBRIO_CENTRAL"
            attractor_desc = "Órbita contraída cerca del centro de equilibrio: baja energía cinética, mercado en compresión."
        elif radius_ratio > 1.50 and radial_slope > 0:
            attractor_state = "ESCAPE_RUPTURA_CENTRIFUGA"
            attractor_desc = "Órbita expandiéndose fuera del atractor medio: ruptura inercial activa dominando sobre el ruido."
        elif radial_slope < -0.10:
            attractor_state = "ESPIRAL_AMORTIGUADA_CONVERGENTE"
            attractor_desc = "Trayectoria disipando energía y retornando hacia el punto fijo del régimen."
        else:
            attractor_state = "CICLO_ORBITAL_ACTIVO"
            attractor_desc = "Órbita estacionaria alrededor del atractor del régimen vigente."

        pred = active_report.get("prediction", {})
        det_prices = np.asarray(pred.get("det_price_path", []), dtype=np.float64)

        if len(det_prices) > 0:
            if cfg.disable_returns:
                det_r_pct_path = det_prices.copy()
            else:
                seq_p = np.concatenate(([last_price], det_prices))
                seq_p = np.maximum(seq_p, 1e-8)
                det_r_pct_path = np.log(seq_p[1:] / seq_p[:-1]) * 100.0
            steps_arr = np.arange(1, len(det_prices) + 1, dtype=np.float64)
            det_v_path = float(v_smooth[-1]) * (0.99**steps_arr)
        else:
            det_r_pct_path = np.array([], dtype=np.float64)
            det_v_path = np.array([], dtype=np.float64)

        curve_price_fit = self._compute_curve_price_fit(
            precio_raw=precio_raw,
            nominal_smooth=nominal_smooth,
            act_s=act_s,
            act_e=act_e,
        )

        geometry_dict = {
            "curve_price_fit": curve_price_fit,
            "kinematics": {
                "velocity_dr_dt": round(vel_now, 6),
                "acceleration_d2r_dt2": round(acc_now, 6),
                "volume_flow_dV_dt": round(vol_vel_now, 6),
                "quadrant": quadrant,
                "interpretation": kin_desc,
                "spline_nominal_price_now": round(spline_price_now, 4),
                "price_vs_spline_gap_pct": round(gap_now_pct, 2),
                "last_30c_mean_gap_pct": round(gap_30c_pct, 2),
                "recent_velocity_reversals": recent_extrema,
                "recent_acceleration_inflections": recent_inflections,
            },
            "phase_space": {
                "current_state_r_pct": round(float(r_pct_series[-1]), 5),
                "current_state_v_z": round(float(v_smooth[-1]), 5),
                "orbital_radius_ratio_vs_median": round(radius_ratio, 3),
                "radial_momentum_5c": round(radial_slope, 4),
                "rotation_sense": rot_sense,
                "topology_class": attractor_state,
                "interpretation": attractor_desc,
            },
        }

        # 3. Forense CUSUM con Fechas Reales + Pico Máximo + Nivel Exacto de Invalidación
        s_pos = cusum_report["s_pos"]
        s_neg = cusum_report["s_neg"]
        shift_indices = cusum_report["shift_indices"]

        residuo = log_returns - r_smooth
        sigma_dyn = self._compute_ewma_sigma(np.diff(residuo), len(residuo))
        z_scores = residuo / sigma_dyn

        # Pico máximo acumulado de tensión CUSUM (útil incluso cuando Quiebres = 0)
        combined_s = np.maximum(s_pos, s_neg)
        peak_idx = int(np.argmax(combined_s)) if len(combined_s) > 0 else 0
        peak_val = float(combined_s[peak_idx]) if len(combined_s) > 0 else 0.0
        peak_side = "S+ (Alcista)" if (len(s_pos) > 0 and s_pos[peak_idx] >= s_neg[peak_idx]) else "S- (Bajista)"
        max_cusum_peak = {
            "candle_idx": peak_idx,
            "date": dates_active[peak_idx] if dates_active else None,
            "price": round(float(precio_raw[peak_idx]), 4) if len(precio_raw) > 0 else None,
            "peak_score": round(peak_val, 3),
            "ratio_vs_h": round(peak_val / cfg.cusum_h, 3) if cfg.cusum_h > 0 else 0.0,
            "side": peak_side,
        }

        dated_breaks = []
        for s_idx in shift_indices:
            si = int(s_idx)
            prev_i = max(0, si - 1)
            est_pos = float(s_pos[prev_i] + z_scores[si] - effective_k)
            est_neg = float(s_neg[prev_i] - z_scores[si] - effective_k)
            b_type = "QUIEBRE_ALCISTA (S+ > H)" if est_pos >= est_neg else "QUIEBRE_BAJISTA (S- > H)"
            dated_breaks.append(
                {
                    "candle_idx": si,
                    "date": dates_active[si],
                    "price_at_break": round(float(precio_raw[si]), 4),
                    "candle_return_pct": round(float(log_returns[si] * scale), 3),
                    "break_type": b_type,
                    "peak_cusum_score": round(max(est_pos, est_neg), 2),
                }
            )

        abs_z_act = np.abs(z_scores[act_s:act_e])
        top_k_anom = min(3, len(abs_z_act))
        top_anomalies = []
        if top_k_anom > 0:
            rel_top = np.argsort(-abs_z_act)[:top_k_anom]
            for r_i in rel_top:
                gi = int(act_s + r_i)
                top_anomalies.append(
                    {
                        "candle_idx": gi,
                        "date": dates_active[gi],
                        "price": round(float(precio_raw[gi]), 4),
                        "raw_return_pct": round(float(log_returns[gi] * scale), 3),
                        "expected_spline_pct": round(float(r_smooth[gi] * scale), 3),
                        "residual_z_score": round(float(z_scores[gi]), 2),
                    }
                )

        cur_s_pos = float(s_pos[-1])
        cur_s_neg = float(s_neg[-1])
        cur_tension = max(cur_s_pos, cur_s_neg)
        tension_ratio = cur_tension / cfg.cusum_h if cfg.cusum_h > 0 else 0.0

        z_needed_up = (cfg.cusum_h - cur_s_pos) + effective_k
        z_needed_down = -((cfg.cusum_h - cur_s_neg) + effective_k)
        cur_sig_dyn = float(sigma_dyn[-1])
        expected_next_r = float(r_smooth[-1])

        ret_break_up = expected_next_r + z_needed_up * cur_sig_dyn
        ret_break_down = expected_next_r + z_needed_down * cur_sig_dyn

        if cfg.disable_returns:
            price_break_up = ret_break_up
            price_break_down = ret_break_down
        else:
            price_break_up = last_price * float(np.exp(np.clip(ret_break_up, -1.0, 1.0)))
            price_break_down = last_price * float(np.exp(np.clip(ret_break_down, -1.0, 1.0)))

        regime_catalog = []
        for idx_r, rep in enumerate(regime_reports):
            rs_i = int(rep["start_idx"])
            re_i = int(rep["end_idx"]) - 1
            p_ini = float(precio_raw[rs_i])
            p_fin = float(precio_raw[re_i])
            ret_reg = ((p_fin - p_ini) / p_ini) * 100.0 if p_ini != 0 else 0.0
            regime_catalog.append(
                {
                    "regime_id": idx_r + 1,
                    "is_active": bool(rep.get("is_active", False)),
                    "start_date": dates_active[rs_i],
                    "end_date": dates_active[re_i],
                    "duration_candles": int(rep["end_idx"] - rep["start_idx"]),
                    "start_price": round(p_ini, 4),
                    "end_price": round(p_fin, 4),
                    "cumulative_return_pct": round(ret_reg, 2),
                    "r2_score": round(float(rep.get("score", 0.0)), 4),
                    "complexity_terms": int(rep.get("complexity", 0)),
                    "equations": rep.get("equations", []),
                    "noise_sigma_r": round(float(rep.get("sigma_res_r", 0.0)), 6),
                }
            )

        cusum_forensics = {
            "active_regime_start_date": dates_active[act_s],
            "active_regime_end_date": dates_active[act_e - 1],
            "active_regime_candles": int(act_e - act_s),
            "unconsolidated_recent_break": {
                "detected": unconsolidated_break,
                "break_date": dates_active[unconsolidated_idx] if unconsolidated_idx is not None else None,
                "candles_since_break": int(len(precio_raw) - unconsolidated_idx) if unconsolidated_idx is not None else None,
                "note": (
                    "Se detectó un quiebre hace <15 velas; se fusionó con el régimen previo para estabilidad SINDy, pero vigilar transición."
                    if unconsolidated_break
                    else "Régimen vigente consolidado (>=15 velas)."
                ),
            },
            "current_tension": {
                "s_pos": round(cur_s_pos, 3),
                "s_neg": round(cur_s_neg, 3),
                "max_tension": round(cur_tension, 3),
                "threshold_h": float(cfg.cusum_h),
                "drift_k": float(effective_k),
                "tension_ratio": round(tension_ratio, 3),
                "status": (
                    "QUIEBRE_INMINENTE"
                    if tension_ratio > 0.9
                    else ("TENSION_ALTA" if tension_ratio > 0.6 else "ESTABLE")
                ),
            },
            "window_max_tension_peak": max_cusum_peak,
            "invalidation_levels_1candle": {
                "upside_regime_break_price": round(float(price_break_up), 4),
                "downside_regime_break_price": round(float(price_break_down), 4),
                "upside_shock_pct_needed": round(((price_break_up / last_price) - 1.0) * 100.0, 2) if last_price > 0 else 0.0,
                "downside_shock_pct_needed": round(((price_break_down / last_price) - 1.0) * 100.0, 2) if last_price > 0 else 0.0,
                "explanation": "Precio aproximado que, en una sola vela, superaría el umbral CUSUM H=5.0 invalidando la ecuación SINDy vigente.",
            },
            "macro_breaks": dated_breaks,
            "active_regime_top_anomalies": top_anomalies,
            "regimes_summary": regime_catalog,
        }

        # 4. Silueta del Cono Estocástico y Proyección Determinística (siempre proyecta t+150)
        p_percentiles = pred.get("price_percentiles", [])
        has_mc = (
            len(p_percentiles) == 5
            and len(det_prices) > 0
            and len(p_percentiles[0]) == len(det_prices)
        )

        raw_milestones = [1, 5, 7, 15, 21, 30, 60, 63, 90, 100, cfg.horizon_steps]
        milestones = sorted(list({m for m in raw_milestones if 1 <= m <= cfg.horizon_steps}))

        checkpoints = []
        for step in milestones:
            idx_s = step - 1
            entry: Dict[str, Any] = {"horizon_step": f"t+{step}", "step": int(step)}
            if idx_s < len(det_prices):
                dp = float(det_prices[idx_s])
                entry["deterministic_price"] = round(dp, 4)
                entry["deterministic_return_pct"] = round(((dp - last_price) / last_price) * 100.0, 2) if last_price else 0.0
            if has_mc and idx_s < len(p_percentiles[0]):
                p5 = float(p_percentiles[0][idx_s])
                p25 = float(p_percentiles[1][idx_s])
                p50 = float(p_percentiles[2][idx_s])
                p75 = float(p_percentiles[3][idx_s])
                p95 = float(p_percentiles[4][idx_s])
                up_wing = max(p95 - p50, 0.0)
                dn_wing = max(p50 - p5, 1e-8)
                entry.update(
                    {
                        "mc_p5": round(p5, 4),
                        "mc_p25": round(p25, 4),
                        "mc_p50": round(p50, 4),
                        "mc_p75": round(p75, 4),
                        "mc_p95": round(p95, 4),
                        "mc_p50_return_pct": round(((p50 - last_price) / last_price) * 100.0, 2) if last_price else 0.0,
                        "cone_spread_p5_p95_pct": round(((p95 - p5) / last_price) * 100.0, 2) if last_price else 0.0,
                        "upside_downside_skew": round(up_wing / dn_wing, 3),
                    }
                )
            checkpoints.append(entry)

        traj_shape = "NO_DISPONIBLE"
        peak_info: Dict[str, Any] = {}
        if len(det_prices) >= 3:
            diffs_det = np.diff(np.concatenate(([last_price], det_prices)))
            total_chg_pct = ((float(det_prices[-1]) - last_price) / last_price) * 100.0 if last_price else 0.0
            max_i = int(np.argmax(det_prices))
            min_i = int(np.argmin(det_prices))
            if abs(total_chg_pct) < 0.35 and (float(np.max(det_prices) - np.min(det_prices)) / max(last_price, 1e-8)) < 0.005:
                traj_shape = "EQUILIBRIO_AMORTIGUADO_PLANO"
            elif np.all(diffs_det >= -1e-9):
                traj_shape = "ASCENSO_MONOTONO_AMORTIGUADO"
            elif np.all(diffs_det <= 1e-9):
                traj_shape = "DESCENSO_MONOTONO_AMORTIGUADO"
            elif 0 < max_i < len(det_prices) - 1 and float(det_prices[max_i]) > last_price and float(det_prices[-1]) < float(det_prices[max_i]):
                traj_shape = "CURVATURA_TECHO_Y_REVERSION"
            elif 0 < min_i < len(det_prices) - 1 and float(det_prices[min_i]) < last_price and float(det_prices[-1]) > float(det_prices[min_i]):
                traj_shape = "CURVATURA_SUELO_Y_REBOTE"
            else:
                traj_shape = "OSCILATORIA_ACOPLADA"

            peak_info = {
                "max_projected_price": round(float(det_prices[max_i]), 4),
                "max_at_step": int(max_i + 1),
                "min_projected_price": round(float(det_prices[min_i]), 4),
                "min_at_step": int(min_i + 1),
            }

        forecast_dict = {
            "monte_carlo_valid": bool(has_mc),
            "unstable_flag": bool(pred.get("unstable", False)),
            "empty_return_equation": bool(active_report.get("empty_r_eq", False)),
            "trajectory_geometry": traj_shape,
            "deterministic_extrema": peak_info,
            "horizon_checkpoints": checkpoints,
        }

        return geometry_dict, cusum_forensics, forecast_dict, det_r_pct_path, det_v_path

    def run(self, df_override: Optional[pd.DataFrame] = None) -> HeadlessRunResult:
        """
        Ejecuta el protocolo matemático completo y devuelve `HeadlessRunResult`
        con telemetría JSON enriquecida y arrays float64 listos para el renderizador PNG.
        """
        t0_wall = time.perf_counter()
        cfg = self.cfg

        # 0. Ingesta
        if df_override is not None:
            df = df_override.copy()
        else:
            df = MarketLoader.load_ticker_data(cfg.ticker, period=cfg.period, interval=cfg.interval)

        dates_full = self._extract_iso_dates(df)
        _, _, price_full, dt_full = MarketLoader.prepare_quant_input(
            df.copy(), disable_norm=cfg.disable_norm, disable_returns=cfg.disable_returns
        )

        df_cols_norm = {str(c).title(): c for c in df.columns}
        if "Volume" in df_cols_norm:
            vol_raw_full = np.ascontiguousarray(
                df[df_cols_norm["Volume"]].ffill().bfill().values, dtype=np.float64
            )
            vol_raw_full[vol_raw_full == 0] = 1e-8
        else:
            vol_raw_full = np.ones(len(price_full), dtype=np.float64)

        if cfg.context_window > 0 and len(df) > cfg.context_window:
            df_active = df.iloc[-cfg.context_window :].copy()
            dates_active = dates_full[-cfg.context_window :]
        else:
            df_active = df.copy()
            dates_active = dates_full

        log_returns, volumen_z, precio_raw, dt_val = MarketLoader.prepare_quant_input(
            df_active.copy(), disable_norm=cfg.disable_norm, disable_returns=cfg.disable_returns
        )
        t = np.arange(len(log_returns), dtype=np.float64) * dt_val
        offset_candles = len(price_full) - len(log_returns)
        global_t = (np.arange(len(price_full), dtype=np.float64) - offset_candles) * dt_full

        # 1. Auto-Calibración de Drift CUSUM (k)
        calibration_info: Dict[str, Any] = {
            "auto_tune_executed": False,
            "initial_smooth_tol": float(cfg.smooth_tol),
            "effective_smooth_tol": float(cfg.smooth_tol),
            "autopilot_rescue": {"triggered": False, "applied": False},
        }

        if cfg.cusum_k is not None:
            effective_k = float(cfg.cusum_k)
            calibration_info["drift_k_source"] = "manual_override"
            calibration_info["effective_cusum_k"] = effective_k
        elif cfg.auto_tune:
            best_k, tuner_rep = self._run_fast_cusum_autotune(df_active)
            effective_k = float(best_k)
            calibration_info["auto_tune_executed"] = True
            calibration_info["drift_k_source"] = "CUSUMAutoTuner"
            calibration_info["effective_cusum_k"] = effective_k
            calibration_info["tuner_report"] = {
                k_name: round(float(v_val), 5) if isinstance(v_val, (int, float, np.floating)) else v_val
                for k_name, v_val in tuner_rep.items()
            }
        else:
            effective_k = 1.0
            calibration_info["drift_k_source"] = "default_1.0"
            calibration_info["effective_cusum_k"] = effective_k

        # 2. Sensor Espectral FFT (Capa 1)
        if cfg.in_process_fft:
            fft_results = {
                0: SpectralAnalyzer._compute_fft(log_returns, dt_val, 2),
                1: SpectralAnalyzer._compute_fft(volumen_z, dt_val, 2),
            }
        else:
            sensor = SpectralAnalyzer(top_k=2)
            data_matrix = np.ascontiguousarray(np.column_stack((log_returns, volumen_z)), dtype=np.float64)
            fft_results = sensor.analyze(data_matrix, dt=dt_val)

        periodos_retornos = fft_results[0]["periods"]
        periodos_volumen = fft_results[1]["periods"]

        # 3. Pasada Principal (Capas 2-5)
        effective_tol = float(cfg.smooth_tol)
        core_out = self._run_core_pass(
            t=t,
            log_returns=log_returns,
            volumen_z=volumen_z,
            precio_raw=precio_raw,
            dt_val=dt_val,
            periodos_retornos=periodos_retornos,
            periodos_volumen=periodos_volumen,
            smooth_tol=effective_tol,
            cusum_k=effective_k,
        )

        # 4. Autopilot Quant (Rescate 2D solo ante inestabilidad numérica o dr/dt = 0; nunca por R²)
        active_rep = core_out["active_report"]
        orig_pred = active_rep.get("prediction", {})
        orig_unstable = bool(orig_pred.get("unstable", False)) or self._is_projection_numerically_divergent(
            orig_pred.get("det_price_path", []),
            float(precio_raw[-1]),
            cfg.disable_returns,
        )
        orig_empty = bool(active_rep.get("empty_r_eq", False))
        orig_r2 = float(active_rep.get("score", 0.0))

        if cfg.auto_rescue and (orig_unstable or orig_empty):
            reason = (
                "Ecuación de retorno anulada (dr/dt = 0) por exceso de filtrado."
                if orig_empty
                else "Inestabilidad numérica en la integración SINDy."
            )

            best_rescue_fit = -np.inf
            best_rescue_r2 = -np.inf
            best_rescue_tol: Optional[float] = None
            best_rescue_out: Optional[Dict[str, Any]] = None

            for tol_try in (0.0100, 0.0005, 0.0001, 0.00005):
                if np.isclose(tol_try, effective_tol):
                    continue
                cand_out = self._run_core_pass(
                    t=t,
                    log_returns=log_returns,
                    volumen_z=volumen_z,
                    precio_raw=precio_raw,
                    dt_val=dt_val,
                    periodos_retornos=periodos_retornos,
                    periodos_volumen=periodos_volumen,
                    smooth_tol=tol_try,
                    cusum_k=effective_k,
                )
                cand_rep = cand_out["active_report"]
                cand_score = float(cand_rep.get("score", 0.0))
                cand_pred = cand_rep.get("prediction", {})
                cand_unstable = bool(cand_pred.get("unstable", True)) or self._is_projection_numerically_divergent(
                    cand_pred.get("det_price_path", []),
                    float(precio_raw[-1]),
                    cfg.disable_returns,
                )
                cand_empty = bool(cand_rep.get("empty_r_eq", True))

                if not cand_empty and not cand_unstable:
                    cand_nominal = self.compute_nominal_smooth(
                        raw_price=precio_raw,
                        r_smooth=cand_out["r_smooth"],
                        triggers=cand_out["cusum_report"]["shift_indices"],
                        disable_returns=cfg.disable_returns,
                    )
                    cand_fit = self._compute_curve_price_fit(
                        precio_raw=precio_raw,
                        nominal_smooth=cand_nominal,
                        act_s=int(cand_rep.get("start_idx", 0)),
                        act_e=int(cand_rep.get("end_idx", len(precio_raw))),
                    )
                    cand_fit_r2 = float(cand_fit.get("window_price_r2", 0.0))
                    if cand_fit_r2 > best_rescue_fit:
                        best_rescue_fit = cand_fit_r2
                        best_rescue_r2 = cand_score
                        best_rescue_tol = tol_try
                        best_rescue_out = cand_out

            if best_rescue_out is not None and best_rescue_tol is not None:
                core_out = best_rescue_out
                active_rep = core_out["active_report"]
                effective_tol = float(best_rescue_tol)
                calibration_info["effective_smooth_tol"] = effective_tol
                calibration_info["autopilot_rescue"] = {
                    "triggered": True,
                    "applied": True,
                    "reason": reason,
                    "original_tol": float(cfg.smooth_tol),
                    "rescued_tol": effective_tol,
                    "original_r2": round(orig_r2, 4),
                    "rescued_r2": round(float(best_rescue_r2), 4),
                    "rescued_curve_price_r2": round(float(best_rescue_fit), 4),
                }
            else:
                calibration_info["autopilot_rescue"] = {
                    "triggered": True,
                    "applied": False,
                    "reason": reason,
                    "best_candidate_r2": round(float(best_rescue_r2), 4) if np.isfinite(best_rescue_r2) else None,
                    "note": "Ninguna tolerancia alternativa evitó dr/dt = 0 o inestabilidad; se usará respaldo cinemático geométrico.",
                }

        # Variedad nominal centrada por mínimos cuadrados (compartida entre JSON y gráficos)
        nominal_smooth = self.compute_nominal_smooth(
            raw_price=precio_raw,
            r_smooth=core_out["r_smooth"],
            triggers=core_out["cusum_report"]["shift_indices"],
            disable_returns=cfg.disable_returns,
        )

        # 4b. Proyección geométrica t+H garantizada + Cono Calibrado EWMA de Integración Simple
        pred_raw = active_rep.get("prediction", {})
        raw_det_t = np.asarray(pred_raw.get("det_t_path", []), dtype=np.float64)
        raw_det_prices = np.asarray(pred_raw.get("det_price_path", []), dtype=np.float64)
        raw_unstable = bool(pred_raw.get("unstable", False)) or self._is_projection_numerically_divergent(
            raw_det_prices,
            float(precio_raw[-1]),
            cfg.disable_returns,
        )
        raw_empty = bool(active_rep.get("empty_r_eq", False))

        det_t_arr, det_prices_arr, geometric_fallback_used = self._ensure_geometric_projection(
            last_price=float(precio_raw[-1]),
            raw_det_t=raw_det_t,
            raw_det_prices=raw_det_prices,
            horizon_steps=int(cfg.horizon_steps),
            dt_val=float(dt_val),
            t_end=float(t[-1]),
            r_smooth=core_out["r_smooth"],
            r_dot=core_out["r_dot"],
            unstable_flag=raw_unstable,
            empty_r_eq=raw_empty,
            disable_returns=cfg.disable_returns,
        )
        if isinstance(pred_raw, dict):
            pred_raw["det_t_path"] = det_t_arr
            pred_raw["det_price_path"] = det_prices_arr
            if len(pred_raw.get("t_path", [])) != len(det_t_arr):
                pred_raw["t_path"] = det_t_arr

        cal_percentiles, cal_price_paths, sigma_ewma_now = (
            self._simulate_calibrated_single_integration_cone(
                last_price=float(precio_raw[-1]),
                det_prices=det_prices_arr,
                precio_raw=precio_raw,
                log_returns=log_returns,
                r_smooth=core_out["r_smooth"],
                dt_val=dt_val,
                unstable_flag=False,
                empty_r_eq=False,
                disable_returns=cfg.disable_returns,
                disable_norm=cfg.disable_norm,
                random_seed=cfg.random_seed,
                n_paths=2000,
            )
        )
        if isinstance(pred_raw, dict):
            pred_raw["price_percentiles"] = cal_percentiles

        # 5. Integración Simbólica Rápida
        symbolic = SymbolicTranslator(active_rep)
        p0_sym = float(precio_raw[-1]) if cfg.disable_returns else float(log_returns[-1] * 100.0)
        v0_sym = float(core_out["v_smooth"][-1])
        analytical_solution, eigen_diagnostics = self._solve_analytical_fast(
            symbolic=symbolic,
            active_discoverer=core_out["active_discoverer"],
            p0=p0_sym,
            v0=v0_sym,
        )
        geogebra_script = symbolic.generate_geogebra_commands()

        # 6. Doble Sello de Fiabilidad Física (Ljung-Box + Mini Walk-Forward Estricto)
        lb_seal = self._compute_ljung_box_seal(
            log_returns=log_returns,
            r_smooth=core_out["r_smooth"],
            v_smooth=core_out["v_smooth"],
            r_dot=core_out["r_dot"],
            v_dot=core_out["v_dot"],
            active_report=active_rep,
            active_discoverer=core_out["active_discoverer"],
        )
        wf_seal = self._compute_fast_walk_forward_seal(
            price_full=price_full,
            vol_raw_full=vol_raw_full,
            dt_val=dt_val,
            effective_tol=effective_tol,
            effective_k=effective_k,
        )

        # 7. Geometría, Forense CUSUM y Silueta del Cono
        geometry_dict, cusum_forensics, forecast_dict, det_r_pct_path, det_v_path = (
            self._extract_geometry_and_forensics(
                dates_active=dates_active,
                precio_raw=precio_raw,
                nominal_smooth=nominal_smooth,
                log_returns=log_returns,
                r_smooth=core_out["r_smooth"],
                r_dot=core_out["r_dot"],
                r_dot2=core_out["r_dot2"],
                v_smooth=core_out["v_smooth"],
                v_dot=core_out["v_dot"],
                cusum_report=core_out["cusum_report"],
                boundaries=core_out["boundaries"],
                unconsolidated_break=core_out["unconsolidated_break"],
                unconsolidated_idx=core_out["unconsolidated_idx"],
                regime_reports=core_out["regime_reports"],
                active_report=active_rep,
                effective_k=effective_k,
            )
        )

        forecast_dict["cone_model"] = "SINGLE_INTEGRATION_EWMA_LOGPRICE"
        forecast_dict["ewma_daily_sigma"] = round(float(sigma_ewma_now), 6)
        forecast_dict["geometric_fallback_used"] = bool(geometric_fallback_used)

        # 8. KPIs Ejecutivos, Diagnóstico Geométrico Curva-Precio y Veredicto de Confianza v0.3.1
        r_dot_last = float(core_out["r_dot"][-1])
        vel_pct = r_dot_last * 100.0 if not cfg.disable_returns else r_dot_last
        acc_pct = float(core_out["r_dot2"][-1]) * (100.0 if not cfg.disable_returns else 1.0)
        r2_val = float(active_rep.get("score", 0.0))
        tension_ratio = float(cusum_forensics["current_tension"]["tension_ratio"])
        is_unstable = bool(forecast_dict["unstable_flag"])
        empty_eq = bool(forecast_dict["empty_return_equation"])
        phys_class = wf_seal.get("asset_physics_class", "NO_EVALUADO")
        curve_fit = geometry_dict["curve_price_fit"]
        fit_r2 = float(curve_fit.get("window_price_r2", 0.0))
        fit_mape = float(curve_fit.get("window_price_mape_pct", 0.0))
        fit_label = str(curve_fit.get("fit_label", "Moderado"))

        double_seal = self.evaluate_double_seal(
            lb_seal=lb_seal,
            wf_seal=wf_seal,
            active_r2=r2_val,
            tension_ratio=tension_ratio,
            is_unstable=is_unstable,
            empty_eq=empty_eq,
            geometric_fallback_used=geometric_fallback_used,
        )

        last_price = float(precio_raw[-1])
        win_max_price = float(np.max(precio_raw))
        kin_dict = geometry_dict["kinematics"]
        phs_dict = geometry_dict["phase_space"]

        human_regime = self.classify_human_regime(
            last_price=last_price,
            window_max_price=win_max_price,
            gap_now_pct=float(kin_dict["price_vs_spline_gap_pct"]),
            vel_now=vel_pct,
            acc_now=acc_pct,
            det_prices=det_prices_arr,
            sigma_ewma=sigma_ewma_now,
            unstable_flag=(is_unstable and not geometric_fallback_used),
            empty_r_eq=(empty_eq and not geometric_fallback_used),
            disable_returns=cfg.disable_returns,
            topology_class=str(phs_dict["topology_class"]),
            cusum_status=str(cusum_forensics["current_tension"]["status"]),
            seal_grade=str(double_seal["seal_grade"]),
        )

        scenarios_dict = self._compute_probabilistic_scenarios(
            last_price=last_price,
            nominal_smooth_now=float(nominal_smooth[-1]),
            det_prices=det_prices_arr,
            mc_percentiles=cal_percentiles,
            price_paths=cal_price_paths,
            horizon_steps=int(cfg.horizon_steps),
        )

        confidence_reasons: List[str] = []
        if (is_unstable or empty_eq) and not geometric_fallback_used and len(det_prices_arr) == 0:
            confidence_tier = "NULA_O_DEGRADADA"
            confidence_reasons.append("No se pudo construir trayectoria proyectada estable en esta ventana.")
        else:
            score_pts = 0
            if fit_r2 >= 0.85:
                score_pts += 2
                confidence_reasons.append(
                    f"Ajuste geométrico Curva-Precio fuerte (R²={fit_r2:.3f}, MAPE={fit_mape:.2f}%)."
                )
            elif fit_r2 >= 0.65:
                score_pts += 1
                confidence_reasons.append(
                    f"Ajuste geométrico Curva-Precio moderado (R²={fit_r2:.3f}, MAPE={fit_mape:.2f}%)."
                )
            else:
                confidence_reasons.append(
                    f"Ajuste geométrico Curva-Precio amplio (R²={fit_r2:.3f}, MAPE={fit_mape:.2f}%)."
                )

            if geometric_fallback_used:
                score_pts -= 1
                confidence_reasons.append(
                    "SINDy recurrió a respaldo cinemático amortiguado por inestabilidad o dr/dt=0."
                )

            if phys_class == "NO_EVALUADO":
                confidence_reasons.append(
                    "Enfoque geométrico puro v0.3.1 (Walk-Forward OOS omitido; usar --audit-oos para auditoría retrospectiva)."
                )
            elif phys_class == "COHERENTE_INERCIAL":
                score_pts += 2
                confidence_reasons.append(
                    f"Auditoría --audit-oos coherente ({wf_seal.get('consensus_hit_ratio_pct')}% HR OOS en {wf_seal.get('effective_cuts')} cortes)."
                )
            elif phys_class == "TRANSICIONAL_BORDE":
                score_pts += 1
                confidence_reasons.append(
                    f"Auditoría --audit-oos intermedia ({wf_seal.get('consensus_hit_ratio_pct')}% HR en {wf_seal.get('effective_cuts')} cortes)."
                )
            elif phys_class == "INSUFICIENTE":
                confidence_reasons.append(
                    f"Auditoría --audit-oos con cortes insuficientes ({wf_seal.get('effective_cuts', 0)}/{wf_seal.get('min_required_effective_cuts', 5)})."
                )
            elif phys_class in ("EXOGENO_FUNDAMENTALISTA", "INESTABLE_O_RUIDO_EXTREMO"):
                score_pts -= 1
                confidence_reasons.append(
                    f"Auditoría --audit-oos exógena ({wf_seal.get('consensus_hit_ratio_pct', 0.0)}% HR)."
                )

            if tension_ratio > 0.85:
                score_pts -= 1
                confidence_reasons.append(
                    f"Tensión CUSUM crítica ({tension_ratio:.0%} del umbral H): alto riesgo de giro cercano."
                )
            elif tension_ratio <= 0.50:
                score_pts += 1
                confidence_reasons.append(f"Régimen CUSUM destensado ({tension_ratio:.0%} de H).")

            if score_pts >= 3:
                confidence_tier = "ALTA"
            elif score_pts >= 1:
                confidence_tier = "MEDIA"
            else:
                confidence_tier = "BAJA_CAUTELA"

        total_ms = (time.perf_counter() - t0_wall) * 1000.0

        telemetry: Dict[str, Any] = {
            "metadata": {
                "engine": "KineTopus Headless Engine v3.1",
                "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "total_runtime_ms": round(total_ms, 2),
                "config": asdict(cfg),
                "dataset": {
                    "ticker": cfg.ticker,
                    "total_downloaded_candles": int(len(price_full)),
                    "active_window_candles": int(len(precio_raw)),
                    "first_date_downloaded": dates_full[0] if dates_full else None,
                    "window_start_date": dates_active[0] if dates_active else None,
                    "last_candle_date": dates_active[-1] if dates_active else None,
                    "last_close_price": round(last_price, 4),
                    "window_min_price": round(float(np.min(precio_raw)), 4),
                    "window_max_price": round(win_max_price, 4),
                },
            },
            "calibration": calibration_info,
            "human_regime": human_regime,
            "scenarios": scenarios_dict,
            "executive_kpis": {
                "directional_inertia": "ALCISTA (Long)" if float(det_prices_arr[-1] - last_price) > 0 or (abs(det_prices_arr[-1] - last_price) < 1e-9 and r_dot_last > 0) else "BAJISTA (Short)",
                "instant_velocity_pct_per_candle": round(vel_pct, 4),
                "active_regime_number": int(len(core_out["regime_reports"]) or 1),
                "active_regime_duration_candles": int(cusum_forensics["active_regime_candles"]),
                "curve_price_r2": round(fit_r2, 4),
                "curve_price_mape_pct": round(fit_mape, 3),
                "curve_price_quality": fit_label,
                "sindy_r2_score": round(r2_val, 4),
                "sindy_r2_quality": (
                    "Excelente" if r2_val > 0.8 else ("Aceptable" if r2_val > 0.5 else "Informativo")
                ),
                "cusum_semaphore": cusum_forensics["current_tension"]["status"],
                "cusum_tension_vs_h": f"{cusum_forensics['current_tension']['max_tension']:.2f} / {cfg.cusum_h:.1f}",
                "overall_physical_confidence": confidence_tier,
                "confidence_rationale": confidence_reasons,
            },
            "spectral_layer": {
                "dominant_return_periods_candles": [round(float(p), 2) for p in periodos_retornos],
                "dominant_return_amplitudes": [round(float(a), 5) for a in fft_results[0]["amplitudes"]],
                "dominant_volume_periods_candles": [round(float(p), 2) for p in periodos_volumen],
            },
            "white_box_physics": {
                "state_variable": "P" if cfg.disable_returns else "r",
                "active_equations": active_rep.get("equations", []),
                "global_reference_equations": core_out["physics_report_global"].get("equations", []),
                "global_r2_score": round(float(core_out["physics_report_global"].get("score", 0.0)), 4),
                "active_r2_score": round(r2_val, 4),
                "active_complexity_terms": int(active_rep.get("complexity", 0)),
                "stlsq_threshold_selected": float(active_rep.get("threshold_used", 0.05)),
                "spline_mse_r": round(float(active_rep.get("blender_mse", 0.0)), 7),
                "residual_sigma_r": round(float(active_rep.get("sigma_res_r", 0.0)), 6),
                "residual_sigma_v": round(float(active_rep.get("sigma_res_v", 0.0)), 6),
                "damping_factor_lambda": 0.99,
                "linear_stability_spectrum": eigen_diagnostics,
                "analytical_sympy_solution": analytical_solution.strip(),
                "geogebra_commands": geogebra_script.strip(),
            },
            "reliability_seal": {
                "double_seal_summary": double_seal,
                "ljung_box_whiteness": lb_seal,
                "mini_walk_forward_oos": wf_seal,
            },
            "geometry_and_phase_space": geometry_dict,
            "cusum_forensics": cusum_forensics,
            "forecast_cone": forecast_dict,
        }

        pred_dict = active_rep.get("prediction", {})
        arrays_bundle: Dict[str, Any] = {
            "t": np.ascontiguousarray(t, dtype=np.float64),
            "dates_active": dates_active,
            "full_t": np.ascontiguousarray(global_t, dtype=np.float64),
            "full_raw_price": np.ascontiguousarray(price_full, dtype=np.float64),
            "raw_price": np.ascontiguousarray(precio_raw, dtype=np.float64),
            "nominal_smooth": np.ascontiguousarray(nominal_smooth, dtype=np.float64),
            "log_returns": np.ascontiguousarray(log_returns, dtype=np.float64),
            "r_smooth": np.ascontiguousarray(core_out["r_smooth"], dtype=np.float64),
            "r_dot": np.ascontiguousarray(core_out["r_dot"], dtype=np.float64),
            "r_dot2": np.ascontiguousarray(core_out["r_dot2"], dtype=np.float64),
            "v_smooth": np.ascontiguousarray(core_out["v_smooth"], dtype=np.float64),
            "v_dot": np.ascontiguousarray(core_out["v_dot"], dtype=np.float64),
            "cusum_s_pos": np.ascontiguousarray(core_out["cusum_report"]["s_pos"], dtype=np.float64),
            "cusum_s_neg": np.ascontiguousarray(core_out["cusum_report"]["s_neg"], dtype=np.float64),
            "cusum_triggers": core_out["cusum_report"]["shift_indices"],
            "boundaries": core_out["boundaries"],
            "det_t_path": np.ascontiguousarray(pred_dict.get("det_t_path", []), dtype=np.float64),
            "det_price_path": np.ascontiguousarray(pred_dict.get("det_price_path", []), dtype=np.float64),
            "det_r_pct_path": np.ascontiguousarray(det_r_pct_path, dtype=np.float64),
            "det_v_path": np.ascontiguousarray(det_v_path, dtype=np.float64),
            "mc_t_path": np.ascontiguousarray(pred_dict.get("t_path", []), dtype=np.float64),
            "mc_price_percentiles": pred_dict.get("price_percentiles", []),
        }

        return HeadlessRunResult(telemetry=telemetry, arrays=arrays_bundle)
