"""
Orquestador Headless del Motor Quant KineTopus (Hito 1 + Hito 2 Multi-Lente).

Ejecuta el pipeline físico-matemático completo de 5 capas + Auto-Calibración +
Doble Sello de Fiabilidad Estricto (Ljung-Box y Mini Walk-Forward con ventana completa) +
Geometría Cinemática y Variedad Nominal centrada por mínimos cuadrados,
aislado al 100% de Streamlit (`app.py`) y respetando la Regla de 16GB RAM
(matrices C-contiguous `np.float64`, cero Pandas en hot loops).
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
    wf_cuts: int = 10
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
        Paridad matemática exacta con `CUSUMAutoTuner.run_search` (k en [0.1..5.0] paso 0.1,
        tolerancia base 0.0050, H=5.0, poly_degree=1), ejecutando FFT en proceso y cacheando
        segmentos (start, end) idénticos para evitar crear subprocesos anidados en Windows.
        """
        cfg = self.cfg
        if not cfg.in_process_fft:
            tuner = CUSUMAutoTuner(
                df_active.copy(),
                disable_norm=cfg.disable_norm,
                disable_returns=cfg.disable_returns,
            )
            return tuner.run_search(min_drift=min_drift, max_drift=max_drift, steps=steps)

        log_returns, volumen_z, precio_raw, dt_val = MarketLoader.prepare_quant_input(
            df_active.copy(), disable_norm=cfg.disable_norm, disable_returns=cfg.disable_returns
        )
        t = np.arange(len(log_returns), dtype=np.float64) * dt_val
        total_velas = len(t)

        fft_r = SpectralAnalyzer._compute_fft(log_returns, dt_val, 2)
        fft_v = SpectralAnalyzer._compute_fft(volumen_z, dt_val, 2)

        blender = ContinuousBlender(tolerance=0.0050)
        blender.fit(t, log_returns, fft_r["periods"], feature_idx=0)
        blender.fit(t, volumen_z, fft_v["periods"], feature_idx=1)

        r_smooth, r_dot, _ = blender.compute_continuous(0, t)
        v_smooth, v_dot, _ = blender.compute_continuous(1, t)

        x_matrix = np.ascontiguousarray(np.column_stack((r_smooth, v_smooth)), dtype=np.float64)
        x_dot_matrix = np.ascontiguousarray(np.column_stack((r_dot, v_dot)), dtype=np.float64)
        discoverer = PhysicsDiscoverer(poly_degree=1)

        seg_r2_cache: Dict[Tuple[int, int], float] = {}
        shift_eval_cache: Dict[Tuple[int, ...], Tuple[float, float, int]] = {}

        best_drift = min_drift
        best_score = -float("inf")
        best_report: Dict[str, Any] = {}

        drift_values = np.arange(min_drift, max_drift + steps, steps)
        for k in drift_values:
            detector = RegimeShiftDetector(threshold=5.0, drift=float(k))
            cusum_report = detector.detect(log_returns, r_smooth)
            shift_idx = cusum_report["shift_indices"]
            sh_key = tuple(shift_idx)

            if sh_key not in shift_eval_cache:
                boundaries = [0] + shift_idx + [total_velas]
                weighted_r2_sum = 0.0
                for i in range(len(boundaries) - 1):
                    start = boundaries[i]
                    end = boundaries[i + 1]
                    length = end - start
                    if length < 15:
                        continue
                    if (start, end) not in seg_r2_cache:
                        p_rep = discoverer.extract_equations(
                            t=t[start:end],
                            x=x_matrix[start:end],
                            x_dot=x_dot_matrix[start:end],
                            dt=dt_val,
                            horizon_steps=1,
                            sigma_res_r=0.0,
                            sigma_res_v=0.0,
                            last_price=float(precio_raw[end - 1]),
                            disable_norm=cfg.disable_norm,
                            disable_returns=cfg.disable_returns,
                        )
                        seg_r2_cache[(start, end)] = max(0.0, float(p_rep["score"]))
                    peso = length / float(total_velas)
                    weighted_r2_sum += seg_r2_cache[(start, end)] * peso

                num_quiebres = len(shift_idx)
                fitness = weighted_r2_sum / (1.0 + 0.1 * num_quiebres)
                shift_eval_cache[sh_key] = (fitness, weighted_r2_sum, num_quiebres)

            fitness, weighted_r2_sum, num_quiebres = shift_eval_cache[sh_key]
            if fitness > best_score:
                best_score = fitness
                best_drift = float(k)
                best_report = {
                    "fitness": fitness,
                    "weighted_r2": weighted_r2_sum,
                    "num_quiebres": num_quiebres,
                }

        return round(best_drift, 2), best_report

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

        if cfg.wf_cuts <= 0:
            return {
                "executed": False,
                "strict_full_window_enforced": bool(cfg.strict_wf_window and req_window > 0),
                "required_window_candles": req_window,
                "min_required_effective_cuts": min_req_cuts,
                "effective_cuts": 0,
                "seal_approved": False,
                "reason": "Walk-Forward desactivado por configuración (wf_cuts <= 0).",
                "asset_physics_class": "NO_EVALUADO",
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
            n_place = min(int(cfg.wf_cuts), int(max_possible_cuts))
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
                }
            cut_indices = sorted(
                list(set(int(c) for c in np.linspace(min_train, max_cut, num=cfg.wf_cuts, dtype=int)))
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
        train_lengths_used: List[int] = []
        valid_count = 0

        eps = 1e-8

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
    ) -> Dict[str, Any]:
        """Consolida Ljung-Box + Mini Walk-Forward Estricto en un veredicto unificado de Doble Sello."""
        reasons: List[str] = []
        spline_wn = lb_seal.get("spline_residuals", {}).get("is_white_noise_alpha_05")
        wf_cls = wf_seal.get("asset_physics_class", "NO_EVALUADO")
        eff_cuts = int(wf_seal.get("effective_cuts", wf_seal.get("valid_cuts", 0)))
        min_cuts = int(wf_seal.get("min_required_effective_cuts", 5))
        hr_pct = wf_seal.get("consensus_hit_ratio_pct")

        if is_unstable or empty_eq:
            reasons.append("Fallo de estabilidad SINDy o ecuación de retorno anulada.")
            return {
                "seal_passed": False,
                "seal_grade": "FALLO_ESTABILIDAD",
                "wf_passed": False,
                "ljung_box_spline_white_noise": spline_wn,
                "effective_oos_cuts": eff_cuts,
                "min_required_oos_cuts": min_cuts,
                "reasons": reasons,
            }

        if wf_cls == "NO_EVALUADO":
            reasons.append("Walk-Forward OOS no ejecutado.")
            return {
                "seal_passed": False,
                "seal_grade": "NO_EVALUADO",
                "wf_passed": False,
                "ljung_box_spline_white_noise": spline_wn,
                "effective_oos_cuts": eff_cuts,
                "min_required_oos_cuts": min_cuts,
                "reasons": reasons,
            }

        if wf_cls == "INSUFICIENTE" or eff_cuts < min_cuts:
            reasons.append(f"Cortes OOS efectivos insuficientes ({eff_cuts}/{min_cuts}).")
            return {
                "seal_passed": False,
                "seal_grade": "INSUFICIENTE",
                "wf_passed": False,
                "ljung_box_spline_white_noise": spline_wn,
                "effective_oos_cuts": eff_cuts,
                "min_required_oos_cuts": min_cuts,
                "reasons": reasons,
            }

        if wf_cls in ("EXOGENO_FUNDAMENTALISTA", "INESTABLE_O_RUIDO_EXTREMO"):
            reasons.append(f"Walk-Forward OOS reprobado ({wf_cls}, HR={hr_pct}%).")
            return {
                "seal_passed": False,
                "seal_grade": "REPROBADO_EXOGENO",
                "wf_passed": False,
                "ljung_box_spline_white_noise": spline_wn,
                "effective_oos_cuts": eff_cuts,
                "min_required_oos_cuts": min_cuts,
                "reasons": reasons,
            }

        if active_r2 < 0.35:
            reasons.append(f"Pureza interna SINDy demasiado débil (R²={active_r2:.3f} < 0.35).")
            return {
                "seal_passed": False,
                "seal_grade": "REPROBADO_BAJO_R2",
                "wf_passed": True,
                "ljung_box_spline_white_noise": spline_wn,
                "effective_oos_cuts": eff_cuts,
                "min_required_oos_cuts": min_cuts,
                "reasons": reasons,
            }

        # Walk-Forward aprobado (COHERENTE_INERCIAL o TRANSICIONAL_BORDE)
        reasons.append(f"Walk-Forward OOS aprobado ({wf_cls}, HR={hr_pct}%, {eff_cuts} cortes).")
        conditional = False
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

        geometry_dict = {
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

        # 4. Silueta del Cono Estocástico y Proyección Determinística (incluye hitos 1s/1m/3m para cripto y bolsa)
        p_percentiles = pred.get("price_percentiles", [])
        has_mc = len(p_percentiles) == 5 and len(p_percentiles[0]) > 0 and not active_report.get("empty_r_eq", False)

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

        # 4. Autopilot Quant (Rescate 2D aplicado automáticamente si el régimen es inestable)
        active_rep = core_out["active_report"]
        if cfg.auto_rescue and active_rep.get("prediction", {}).get("unstable", False):
            orig_r2 = float(active_rep.get("score", 0.0))
            orig_empty = bool(active_rep.get("empty_r_eq", False))
            reason = (
                "Ecuación de retorno anulada (dr/dt = 0) por exceso de filtrado."
                if orig_empty
                else f"Inestabilidad o R² insuficiente ({orig_r2:.4f})."
            )

            best_rescue_r2 = -np.inf
            best_rescue_tol: Optional[float] = None
            best_rescue_out: Optional[Dict[str, Any]] = None

            for tol_try in (0.0005, 0.0001, 0.00005):
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
                cand_unstable = bool(cand_rep.get("prediction", {}).get("unstable", True))
                cand_empty = bool(cand_rep.get("empty_r_eq", True))

                if not cand_empty and not cand_unstable and cand_score > best_rescue_r2:
                    best_rescue_r2 = cand_score
                    best_rescue_tol = tol_try
                    best_rescue_out = cand_out

            if best_rescue_out is not None and best_rescue_tol is not None and best_rescue_r2 >= 0.40:
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
                }
            else:
                calibration_info["autopilot_rescue"] = {
                    "triggered": True,
                    "applied": False,
                    "reason": reason,
                    "best_candidate_r2": round(float(best_rescue_r2), 4) if np.isfinite(best_rescue_r2) else None,
                    "note": "Ninguna tolerancia de rescate alcanzó R² >= 0.40 con física estable; proyección Monte Carlo degradada por seguridad.",
                }

        # Variedad nominal centrada por mínimos cuadrados (compartida entre JSON y gráficos)
        nominal_smooth = self.compute_nominal_smooth(
            raw_price=precio_raw,
            r_smooth=core_out["r_smooth"],
            triggers=core_out["cusum_report"]["shift_indices"],
            disable_returns=cfg.disable_returns,
        )

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

        # 8. KPIs Ejecutivos, Resumen del Doble Sello y Veredicto de Confianza
        r_dot_last = float(core_out["r_dot"][-1])
        vel_pct = r_dot_last * 100.0 if not cfg.disable_returns else r_dot_last
        r2_val = float(active_rep.get("score", 0.0))
        tension_ratio = float(cusum_forensics["current_tension"]["tension_ratio"])
        is_unstable = bool(forecast_dict["unstable_flag"])
        empty_eq = bool(forecast_dict["empty_return_equation"])
        phys_class = wf_seal.get("asset_physics_class", "NO_EVALUADO")

        double_seal = self.evaluate_double_seal(
            lb_seal=lb_seal,
            wf_seal=wf_seal,
            active_r2=r2_val,
            tension_ratio=tension_ratio,
            is_unstable=is_unstable,
            empty_eq=empty_eq,
        )

        confidence_reasons: List[str] = []
        if is_unstable:
            confidence_tier = "NULA_O_DEGRADADA"
            confidence_reasons.append("El régimen vigente activó el Kill-Switch de estabilidad física.")
        else:
            score_pts = 0
            if r2_val >= 0.70:
                score_pts += 2
                confidence_reasons.append(f"Ajuste SINDy fuerte (R²={r2_val:.3f}).")
            elif r2_val >= 0.45:
                score_pts += 1
                confidence_reasons.append(f"Ajuste SINDy moderado (R²={r2_val:.3f}).")
            else:
                confidence_reasons.append(f"Ajuste SINDy ruidoso (R²={r2_val:.3f}).")

            if phys_class == "COHERENTE_INERCIAL":
                score_pts += 2
                confidence_reasons.append(
                    f"Activo físicamente coherente en Walk-Forward ({wf_seal.get('consensus_hit_ratio_pct')}% HR OOS en {wf_seal.get('effective_cuts')} cortes)."
                )
            elif phys_class == "TRANSICIONAL_BORDE":
                score_pts += 1
                confidence_reasons.append(
                    f"Coherencia OOS intermedia ({wf_seal.get('consensus_hit_ratio_pct')}% HR en {wf_seal.get('effective_cuts')} cortes)."
                )
            elif phys_class == "INSUFICIENTE":
                score_pts -= 2
                confidence_reasons.append(
                    f"Sello OOS INSUFICIENTE ({wf_seal.get('effective_cuts', 0)}/{wf_seal.get('min_required_effective_cuts', 5)} cortes efectivos de ventana completa)."
                )
            elif phys_class in ("EXOGENO_FUNDAMENTALISTA", "INESTABLE_O_RUIDO_EXTREMO"):
                score_pts -= 2
                confidence_reasons.append(
                    f"Alerta Caso GLD / Exógeno: Walk-Forward OOS reprobado ({wf_seal.get('consensus_hit_ratio_pct', 0.0)}% HR)."
                )

            if tension_ratio > 0.85:
                score_pts -= 1
                confidence_reasons.append(
                    f"Tensión CUSUM crítica ({tension_ratio:.0%} del umbral H): alto riesgo de cambio inminente de régimen."
                )
            elif tension_ratio <= 0.50:
                score_pts += 1
                confidence_reasons.append(f"Régimen CUSUM destensado ({tension_ratio:.0%} de H).")

            if not double_seal["seal_passed"]:
                confidence_tier = "BAJA_CAUTELA"
            elif double_seal["seal_grade"] == "APROBADO_CONDICIONAL":
                confidence_tier = "MEDIA" if score_pts >= 2 else "BAJA_CAUTELA"
            elif score_pts >= 4:
                confidence_tier = "ALTA"
            elif score_pts >= 2:
                confidence_tier = "MEDIA"
            else:
                confidence_tier = "BAJA_CAUTELA"

        total_ms = (time.perf_counter() - t0_wall) * 1000.0
        last_price = float(precio_raw[-1])

        telemetry: Dict[str, Any] = {
            "metadata": {
                "engine": "KineTopus Headless Engine v2.2",
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
                    "window_max_price": round(float(np.max(precio_raw)), 4),
                },
            },
            "calibration": calibration_info,
            "executive_kpis": {
                "directional_inertia": "ALCISTA (Long)" if r_dot_last > 0 else "BAJISTA (Short)",
                "instant_velocity_pct_per_candle": round(vel_pct, 4),
                "active_regime_number": int(len(core_out["regime_reports"]) or 1),
                "active_regime_duration_candles": int(cusum_forensics["active_regime_candles"]),
                "sindy_r2_score": round(r2_val, 4),
                "sindy_r2_quality": (
                    "Excelente" if r2_val > 0.8 else ("Aceptable" if r2_val > 0.5 else "Ruidoso")
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
