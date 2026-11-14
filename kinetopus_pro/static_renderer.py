"""
Renderizador Estático Multi-Escala de Alta Legibilidad (`Matplotlib Agg`) — Hito 2.

Incorpora todos los refuerzos visuales acordados (A–E) manteniendo la Regla de 16GB RAM:
  - A: Anotaciones sin solapamiento (fechas y precios de cruces dr/dt=0 y d²r/dt²=0, bandas
       horizontales de invalidación CUSUM a 1v, último cierre, pico CUSUM máximo y flechas
       direccionales en el atractor).
  - B: Panel dedicado de Zoom Táctico (últimas ~120 velas + proyección t+60).
  - C: Gráfico maestro de Confluencia Multi-Lente (`confluence.png`: 3 splines superpuestos +
       zoom de divergencia reciente + 3 curvas de velocidad).
  - E: Exportación individual de los 6 paneles de cada lente en alta resolución (`dpi=200`).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import numpy as np

from kinetopus_pro.headless_pipeline import HeadlessRunResult, KinetopusHeadlessPipeline


class KinetopusStaticRenderer:
    """Renderizador oscuro 'Data Sci-Fi' de alta legibilidad para humanos y agentes multimodales."""

    BG_FIG = "#0b0f17"
    BG_PANEL = "#111827"
    GRID_COL = "#263248"
    TEXT_MAIN = "#e5e7eb"
    TEXT_MUTED = "#9ca3af"
    REGIME_COLORS = ["#00ffcc", "#ff9900", "#cc33ff", "#ff3366", "#33ccff", "#eab308"]

    LENS_PALETTE: Dict[int, Tuple[str, str]] = {
        0: ("#38bdf8", "Fondo"),         # Lente Larga (ej. 2000v) - Azul Cian
        1: ("#f59e0b", "Confirmación"),  # Lente Media (ej. 1000v) - Ámbar
        2: ("#10b981", "Timing"),        # Lente Corta (ej. 500v)  - Esmeralda
    }

    @classmethod
    def _style_axis(cls, ax: Any) -> None:
        ax.set_facecolor(cls.BG_PANEL)
        ax.grid(True, color=cls.GRID_COL, linestyle="--", linewidth=0.55, alpha=0.65)
        ax.tick_params(colors=cls.TEXT_MUTED, labelsize=8.5)
        for spine in ax.spines.values():
            spine.set_color("#334155")
            spine.set_linewidth(0.8)

    @staticmethod
    def _pill_bbox(edge: str = "#334155", alpha: float = 0.86) -> Dict[str, Any]:
        return {
            "boxstyle": "round,pad=0.22",
            "facecolor": "#0b0f17",
            "edgecolor": edge,
            "linewidth": 0.65,
            "alpha": alpha,
        }

    @staticmethod
    def _format_time_ticks(
        ax: Any,
        x_min: float,
        x_max: float,
        t0_val: float,
        dt_step: float,
        dates_active: List[str],
        num_ticks: int = 9,
    ) -> None:
        tick_positions = np.linspace(x_min, x_max, num=num_ticks)
        tick_labels: List[str] = []
        for tp in tick_positions:
            rel_idx = int(round((tp - t0_val) / max(dt_step, 1e-8)))
            if 0 <= rel_idx < len(dates_active):
                tick_labels.append(dates_active[rel_idx][:10])
            elif rel_idx < 0:
                tick_labels.append(f"{rel_idx}v")
            else:
                ahead = rel_idx - (len(dates_active) - 1)
                tick_labels.append(f"t+{ahead}")
        ax.set_xticks(tick_positions)
        ax.set_xticklabels(tick_labels)

    @staticmethod
    def _get_nominal_smooth(run_result: HeadlessRunResult) -> np.ndarray:
        arr = run_result.arrays
        if "nominal_smooth" in arr and isinstance(arr["nominal_smooth"], np.ndarray):
            return arr["nominal_smooth"]
        cfg = run_result.telemetry["metadata"]["config"]
        return KinetopusHeadlessPipeline.compute_nominal_smooth(
            raw_price=arr["raw_price"],
            r_smooth=arr["r_smooth"],
            triggers=list(arr["cusum_triggers"]),
            disable_returns=bool(cfg.get("disable_returns", False)),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers individuales de los 6 paneles (reutilizados en dashboard y panels/)
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def _draw_panel_1_price_variety(
        cls, ax: Any, run_result: HeadlessRunResult, show_xticks: bool = False
    ) -> None:
        tel = run_result.telemetry
        arr = run_result.arrays
        t: np.ndarray = arr["t"]
        dates_active: List[str] = arr["dates_active"]
        raw_price: np.ndarray = arr["raw_price"]
        nominal_smooth = cls._get_nominal_smooth(run_result)
        triggers: List[int] = list(arr["cusum_triggers"])
        det_t: np.ndarray = arr["det_t_path"]
        det_price: np.ndarray = arr["det_price_path"]
        mc_t: np.ndarray = arr["mc_t_path"]
        mc_p: List[List[float]] = arr["mc_price_percentiles"]

        ds = tel["metadata"]["dataset"]
        cusum_f = tel["cusum_forensics"]
        kin = tel["geometry_and_phase_space"]["kinematics"]
        inv = cusum_f["invalidation_levels_1candle"]

        seg_bounds = [0] + [int(idx) for idx in triggers if 0 < int(idx) < len(t)] + [len(t)]

        ax.scatter(
            t,
            raw_price,
            s=8,
            color="#94a3b8",
            alpha=0.40,
            label="Precio Crudo (Velas)",
            zorder=2,
        )

        for i in range(len(seg_bounds) - 1):
            s_i, e_i = seg_bounds[i], seg_bounds[i + 1]
            col = cls.REGIME_COLORS[i % len(cls.REGIME_COLORS)]
            lbl = "Variedad Spline C² (Centrada por Régimen)" if i == 0 else None
            ax.plot(t[s_i:e_i], nominal_smooth[s_i:e_i], color=col, linewidth=1.9, label=lbl, zorder=3)

        for trig_i in triggers:
            if 0 <= trig_i < len(t):
                ax.axvline(float(t[trig_i]), color="#facc15", linestyle="--", linewidth=0.85, alpha=0.42)

        # Líneas horizontales de invalidación CUSUM a 1 vela (Refuerzo A)
        up_brk = float(inv["upside_regime_break_price"])
        dn_brk = float(inv["downside_regime_break_price"])
        up_pct = float(inv["upside_shock_pct_needed"])
        dn_pct = float(inv["downside_shock_pct_needed"])

        ax.axhline(up_brk, color="#38bdf8", linestyle=":", linewidth=1.15, alpha=0.75, zorder=2)
        ax.axhline(dn_brk, color="#fb7185", linestyle=":", linewidth=1.15, alpha=0.78, zorder=2)

        x_lbl_left = float(t[0]) + (float(t[-1]) - float(t[0])) * 0.015
        ax.annotate(
            f"Ruptura Alza CUSUM (1v): {up_brk:,.2f} ({up_pct:+.1f}%)",
            xy=(x_lbl_left, up_brk),
            xytext=(0, 4),
            textcoords="offset points",
            ha="left",
            va="bottom",
            color="#7dd3fc",
            fontsize=7.6,
            bbox=cls._pill_bbox("#0284c7", 0.78),
            zorder=6,
        )
        ax.annotate(
            f"Invalidación Baja CUSUM (1v): {dn_brk:,.2f} ({dn_pct:+.1f}%)",
            xy=(x_lbl_left, dn_brk),
            xytext=(0, -5),
            textcoords="offset points",
            ha="left",
            va="top",
            color="#fda4af",
            fontsize=7.6,
            bbox=cls._pill_bbox("#e11d48", 0.78),
            zorder=6,
        )

        # Marcador del último cierre y brecha vs Spline
        last_p = float(ds["last_close_price"])
        gap_pct = float(kin.get("price_vs_spline_gap_pct", 0.0))
        ax.scatter([t[-1]], [last_p], color="#facc15", edgecolors="#ffffff", linewidths=0.9, s=46, zorder=7)
        ax.annotate(
            f"Cierre: {last_p:,.2f} (Gap Spline {gap_pct:+.1f}%)",
            xy=(float(t[-1]), last_p),
            xytext=(-10, 12 if gap_pct >= 0 else -14),
            textcoords="offset points",
            ha="right",
            va="bottom" if gap_pct >= 0 else "top",
            color="#fde047",
            fontsize=8.0,
            fontweight="bold",
            bbox=cls._pill_bbox("#ca8a04", 0.86),
            zorder=8,
        )

        has_mc = (
            len(mc_t) > 0
            and len(mc_p) == 5
            and len(mc_p[0]) == len(mc_t)
            and not tel["forecast_cone"]["empty_return_equation"]
            and not tel["forecast_cone"]["unstable_flag"]
        )
        has_det = len(det_t) > 0 and len(det_price) == len(det_t)

        p50_end: Optional[float] = None
        det_end: Optional[float] = None

        if has_mc:
            p5 = np.asarray(mc_p[0], dtype=np.float64)
            p25 = np.asarray(mc_p[1], dtype=np.float64)
            p50 = np.asarray(mc_p[2], dtype=np.float64)
            p75 = np.asarray(mc_p[3], dtype=np.float64)
            p95 = np.asarray(mc_p[4], dtype=np.float64)
            p50_end = float(p50[-1])

            ax.fill_between(
                mc_t, p5, p95, color="#ec4899", alpha=0.14, label="Cono Monte Carlo (P5-P95)", zorder=2
            )
            ax.fill_between(
                mc_t, p25, p75, color="#ec4899", alpha=0.26, label="Núcleo Estocástico (P25-P75)", zorder=2
            )
            ax.plot(mc_t, p50, color="#f472b6", linewidth=2.0, label="Mediana Estocástica (P50)", zorder=4)
            ax.scatter([mc_t[-1]], [p50_end], color="#ffffff", s=45, marker="*", zorder=7)

        if has_det:
            det_end = float(det_price[-1])
            ax.plot(
                det_t,
                det_price,
                color="#00ffcc",
                linestyle="--",
                linewidth=1.9,
                label="Proyección Determinista F(t+N)",
                zorder=5,
            )
            ax.scatter([det_t[-1]], [det_end], color="#00ffcc", s=30, zorder=7)

        # Anti-solapamiento dinámico entre P50(t+N) y F(t+N)
        if p50_end is not None and det_end is not None:
            p50_higher = p50_end >= det_end
            p50_dy = 13 if p50_higher else -15
            det_dy = -15 if p50_higher else 13
        else:
            p50_dy = 12
            det_dy = -14

        if p50_end is not None:
            ax.annotate(
                f"P50(t+{len(mc_t)}): {p50_end:,.2f}",
                xy=(float(mc_t[-1]), p50_end),
                xytext=(6, p50_dy),
                textcoords="offset points",
                ha="left",
                va="center",
                color="#f472b6",
                fontsize=8.0,
                fontweight="bold",
                bbox=cls._pill_bbox("#db2777", 0.85),
                zorder=8,
            )
        if det_end is not None:
            ax.annotate(
                f"F(t+{len(det_t)}): {det_end:,.2f}",
                xy=(float(det_t[-1]), det_end),
                xytext=(6, det_dy),
                textcoords="offset points",
                ha="left",
                va="center",
                color="#00ffcc",
                fontsize=8.0,
                fontweight="bold",
                bbox=cls._pill_bbox("#0d9488", 0.85),
                zorder=8,
            )

        hist_min = float(np.min(raw_price))
        hist_max = float(np.max(raw_price))
        hist_rng = hist_max - hist_min if hist_max != hist_min else max(abs(hist_max) * 0.1, 1.0)
        safe_max = hist_max + hist_rng * 1.45
        safe_min = max(0.0, hist_min - hist_rng * 1.25) if hist_min > 0 else hist_min - hist_rng * 1.25
        vis_max = max(hist_max, min(safe_max, up_brk))
        vis_min = min(hist_min, max(safe_min, dn_brk))

        if has_det:
            fin_det = det_price[np.isfinite(det_price)]
            if len(fin_det) > 0:
                vis_max = max(vis_max, min(safe_max, float(np.max(fin_det))))
                vis_min = min(vis_min, max(safe_min, float(np.min(fin_det))))
        if has_mc:
            for idx_p in (0, 2, 4):
                arr_c = np.asarray(mc_p[idx_p], dtype=np.float64)
                valid_c = arr_c[np.isfinite(arr_c)]
                if len(valid_c) > 0:
                    vis_max = max(vis_max, min(safe_max, float(np.max(valid_c))))
                    vis_min = min(vis_min, max(safe_min, float(np.min(valid_c))))

        buf = (vis_max - vis_min) * 0.11 if vis_max > vis_min else 1.0
        ax.set_ylim(vis_min - buf, vis_max + buf)

        max_x_plot = float(det_t[-1]) if len(det_t) > 0 else float(t[-1])
        ax.set_xlim(float(t[0]), max_x_plot + max(2.0, (max_x_plot - float(t[0])) * 0.165))

        ax.set_title(
            f"1. Variedad de Precio Nominal ({ds['active_window_candles']}v), Bandas CUSUM y Cono Euler-Maruyama",
            color=cls.TEXT_MAIN,
            fontsize=10.0,
            fontweight="bold",
            loc="left",
        )
        ax.set_ylabel("Precio Nominal", color=cls.TEXT_MAIN, fontsize=8.8)
        ax.legend(
            loc="upper left",
            ncol=3,
            fontsize=7.7,
            facecolor="#0f172a",
            edgecolor="#334155",
            labelcolor=cls.TEXT_MAIN,
        )

        if show_xticks:
            dt_step = float(t[1] - t[0]) if len(t) > 1 else 1.0
            cls._format_time_ticks(ax, float(t[0]), max_x_plot, float(t[0]), dt_step, dates_active)
            ax.set_xlabel("Tiempo Calendario / Horizonte Proyectado", color=cls.TEXT_MAIN, fontsize=8.8)
        else:
            plt.setp(ax.get_xticklabels(), visible=False)

    @classmethod
    def _draw_panel_2_tactical_zoom(
        cls,
        ax: Any,
        run_result: HeadlessRunResult,
        zoom_candles: int = 120,
        zoom_horizon: int = 60,
    ) -> None:
        """Refuerzo B: Zoom táctico legible de las últimas ~120 velas + proyección t+60."""
        tel = run_result.telemetry
        arr = run_result.arrays
        t: np.ndarray = arr["t"]
        dates_active: List[str] = arr["dates_active"]
        raw_price: np.ndarray = arr["raw_price"]
        nominal_smooth = cls._get_nominal_smooth(run_result)
        det_t: np.ndarray = arr["det_t_path"]
        det_price: np.ndarray = arr["det_price_path"]
        mc_t: np.ndarray = arr["mc_t_path"]
        mc_p: List[List[float]] = arr["mc_price_percentiles"]

        cusum_f = tel["cusum_forensics"]
        kin = tel["geometry_and_phase_space"]["kinematics"]
        inv = cusum_f["invalidation_levels_1candle"]

        z_start = max(0, len(t) - zoom_candles)
        t_z = t[z_start:]
        p_z = raw_price[z_start:]
        s_z = nominal_smooth[z_start:]

        ax.plot(t_z, p_z, color="#cbd5e1", linewidth=1.05, alpha=0.72, label="Precio Cierre Diario", zorder=3)
        ax.scatter(t_z, p_z, s=16, color="#e2e8f0", alpha=0.80, zorder=3)
        ax.plot(t_z, s_z, color="#00ffcc", linewidth=2.25, label="Variedad Spline C² (Reciente)", zorder=4)

        # Sombrear brecha entre precio crudo y variedad Spline en el tramo reciente
        ax.fill_between(t_z, p_z, s_z, color="#38bdf8", alpha=0.09, zorder=2)

        # Marcar giros dr/dt=0 que caigan dentro de la ventana de zoom
        for rev in kin.get("recent_velocity_reversals", []):
            ci = int(rev["candle_idx"])
            if z_start <= ci < len(t):
                is_up = "ALZA" in rev["type"]
                ax.scatter(
                    [t[ci]],
                    [raw_price[ci]],
                    marker="^" if is_up else "v",
                    color="#22c55e" if is_up else "#ef4444",
                    s=62,
                    zorder=6,
                )
                ax.annotate(
                    f"dr/dt=0 ({rev['date'][:10]}: {rev['price']:,.2f})",
                    xy=(float(t[ci]), float(raw_price[ci])),
                    xytext=(0, -14 if is_up else 12),
                    textcoords="offset points",
                    ha="center",
                    color="#86efac" if is_up else "#fca5a5",
                    fontsize=7.5,
                    bbox=cls._pill_bbox("#16a34a" if is_up else "#dc2626", 0.84),
                    zorder=7,
                )

        # Bandas CUSUM de invalidación a 1 vela
        up_brk = float(inv["upside_regime_break_price"])
        dn_brk = float(inv["downside_regime_break_price"])
        ax.axhline(up_brk, color="#38bdf8", linestyle=":", linewidth=1.2, alpha=0.82, label=f"Ruptura Alza CUSUM ({up_brk:,.2f})")
        ax.axhline(dn_brk, color="#fb7185", linestyle=":", linewidth=1.2, alpha=0.85, label=f"Invalidación Baja CUSUM ({dn_brk:,.2f})")

        h_cut = min(zoom_horizon, len(det_t))
        has_mc = (
            len(mc_t) >= h_cut > 0
            and len(mc_p) == 5
            and len(mc_p[0]) >= h_cut
            and not tel["forecast_cone"]["empty_return_equation"]
            and not tel["forecast_cone"]["unstable_flag"]
        )

        y_vals = [p_z, s_z, np.array([up_brk, dn_brk], dtype=np.float64)]

        p50_z_end: Optional[float] = None
        det_z_end: Optional[float] = None

        if has_mc:
            mt_z = mc_t[:h_cut]
            p5_z = np.asarray(mc_p[0][:h_cut], dtype=np.float64)
            p25_z = np.asarray(mc_p[1][:h_cut], dtype=np.float64)
            p50_z = np.asarray(mc_p[2][:h_cut], dtype=np.float64)
            p75_z = np.asarray(mc_p[3][:h_cut], dtype=np.float64)
            p95_z = np.asarray(mc_p[4][:h_cut], dtype=np.float64)
            p50_z_end = float(p50_z[-1])

            ax.fill_between(mt_z, p5_z, p95_z, color="#ec4899", alpha=0.14, zorder=2)
            ax.fill_between(mt_z, p25_z, p75_z, color="#ec4899", alpha=0.28, label="Núcleo P25-P75 (t+60)", zorder=2)
            ax.plot(mt_z, p50_z, color="#f472b6", linewidth=2.1, label="Mediana P50", zorder=5)
            ax.scatter([mt_z[-1]], [p50_z_end], color="#ffffff", marker="*", s=48, zorder=7)
            y_vals.extend([p25_z, p75_z, p50_z])

            # Guías verticales sutiles en t+15 y t+30
            for step_m in (15, 30):
                if step_m <= h_cut:
                    xm = float(mt_z[step_m - 1])
                    ax.axvline(xm, color="#64748b", linestyle=":", linewidth=0.75, alpha=0.55)

        if h_cut > 0 and len(det_price) >= h_cut:
            dt_z = det_t[:h_cut]
            dp_z = det_price[:h_cut]
            det_z_end = float(dp_z[-1])
            ax.plot(dt_z, dp_z, color="#00ffcc", linestyle="--", linewidth=2.0, label=f"F(t+{h_cut})", zorder=6)
            ax.scatter([dt_z[-1]], [det_z_end], color="#00ffcc", s=32, zorder=7)
            y_vals.append(dp_z)

        # Etiqueta del cierre actual en la frontera hoy | futuro
        last_p = float(raw_price[-1])
        ax.axvline(float(t[-1]), color="#94a3b8", linestyle="-.", linewidth=0.9, alpha=0.55)
        ax.scatter([t[-1]], [last_p], color="#facc15", edgecolors="#ffffff", s=52, zorder=8)
        ax.annotate(
            f"Hoy: {last_p:,.2f}",
            xy=(float(t[-1]), last_p),
            xytext=(-8, 11),
            textcoords="offset points",
            ha="right",
            color="#fde047",
            fontsize=8.0,
            fontweight="bold",
            bbox=cls._pill_bbox("#ca8a04", 0.86),
            zorder=9,
        )

        # Etiquetas separadas en t+60 sin solapamiento
        if p50_z_end is not None and det_z_end is not None:
            p50_top = p50_z_end >= det_z_end
            dy_p50 = 13 if p50_top else -15
            dy_det = -15 if p50_top else 13
        else:
            dy_p50 = 12
            dy_det = -14

        if p50_z_end is not None and has_mc:
            p25_end = float(mc_p[1][h_cut - 1])
            p75_end = float(mc_p[3][h_cut - 1])
            ax.annotate(
                f"P50(t+{h_cut}): {p50_z_end:,.2f} [P25-P75: {p25_end:,.0f}–{p75_end:,.0f}]",
                xy=(float(mc_t[h_cut - 1]), p50_z_end),
                xytext=(-6, dy_p50),
                textcoords="offset points",
                ha="right",
                va="bottom" if dy_p50 > 0 else "top",
                color="#f472b6",
                fontsize=7.9,
                fontweight="bold",
                bbox=cls._pill_bbox("#db2777", 0.86),
                zorder=9,
            )
        if det_z_end is not None and h_cut > 0:
            ax.annotate(
                f"F(t+{h_cut}): {det_z_end:,.2f}",
                xy=(float(det_t[h_cut - 1]), det_z_end),
                xytext=(-6, dy_det),
                textcoords="offset points",
                ha="right",
                va="bottom" if dy_det > 0 else "top",
                color="#00ffcc",
                fontsize=7.9,
                fontweight="bold",
                bbox=cls._pill_bbox("#0d9488", 0.86),
                zorder=9,
            )

        flat_y = np.concatenate([v[np.isfinite(v)] for v in y_vals if len(v) > 0])
        ymin, ymax = float(np.min(flat_y)), float(np.max(flat_y))
        pad = (ymax - ymin) * 0.14 if ymax > ymin else 1.0
        ax.set_ylim(ymin - pad, ymax + pad)

        x_end = float(det_t[h_cut - 1]) if h_cut > 0 else float(t[-1])
        ax.set_xlim(float(t_z[0]), x_end + max(1.5, (x_end - float(t_z[0])) * 0.03))

        dt_step = float(t[1] - t[0]) if len(t) > 1 else 1.0
        cls._format_time_ticks(ax, float(t_z[0]), x_end, float(t[0]), dt_step, dates_active, num_ticks=9)

        gap_30 = float(kin.get("last_30c_mean_gap_pct", 0.0))
        ax.set_title(
            f"2. Zoom Táctico (Últimas {len(t_z)}v + Proyección t+{h_cut})  —  Brecha Media 30v Precio vs Spline: {gap_30:+.2f}%",
            color=cls.TEXT_MAIN,
            fontsize=9.8,
            fontweight="bold",
            loc="left",
        )
        ax.set_ylabel("Precio Zoom", color=cls.TEXT_MAIN, fontsize=8.8)
        ax.legend(
            loc="upper left",
            ncol=3,
            fontsize=7.5,
            facecolor="#0f172a",
            edgecolor="#334155",
            labelcolor=cls.TEXT_MAIN,
        )

    @classmethod
    def _draw_panel_3_velocity(
        cls, ax: Any, run_result: HeadlessRunResult, show_xticks: bool = False
    ) -> None:
        tel = run_result.telemetry
        arr = run_result.arrays
        t: np.ndarray = arr["t"]
        dates_active: List[str] = arr["dates_active"]
        r_dot: np.ndarray = arr["r_dot"]
        det_t: np.ndarray = arr["det_t_path"]
        triggers: List[int] = list(arr["cusum_triggers"])

        cfg = tel["metadata"]["config"]
        kin = tel["geometry_and_phase_space"]["kinematics"]
        disable_returns = bool(cfg.get("disable_returns", False))
        var_name = "P" if disable_returns else "r"
        scale = 1.0 if disable_returns else 100.0

        seg_bounds = [0] + [int(idx) for idx in triggers if 0 < int(idx) < len(t)] + [len(t)]
        vel_scaled = r_dot * scale

        for i in range(len(seg_bounds) - 1):
            s_i, e_i = seg_bounds[i], seg_bounds[i + 1]
            s_plot = max(0, s_i - 1) if i > 0 else s_i
            col = cls.REGIME_COLORS[i % len(cls.REGIME_COLORS)]
            ax.plot(t[s_plot:e_i], vel_scaled[s_plot:e_i], color=col, linewidth=1.6)

        for trig_i in triggers:
            if 0 <= trig_i < len(t):
                ax.axvline(float(t[trig_i]), color="#facc15", linestyle="--", linewidth=0.85, alpha=0.40)

        ax.axhline(0.0, color="#94a3b8", linestyle="--", linewidth=0.9, alpha=0.68)

        # Anotar cruces dr/dt = 0 con fechas y precios (Refuerzo A)
        reversals = kin.get("recent_velocity_reversals", [])[-4:]
        for k_idx, rev in enumerate(reversals):
            ci = int(rev["candle_idx"])
            if 0 <= ci < len(t):
                is_up = "ALZA" in rev["type"]
                ax.scatter(
                    [t[ci]],
                    [0.0],
                    marker="^" if is_up else "v",
                    color="#22c55e" if is_up else "#ef4444",
                    s=54,
                    zorder=6,
                )
                dy = 12 if (k_idx % 2 == 0) else -15
                ax.annotate(
                    f"{rev['date'][:10]} ({rev['price']:,.0f})",
                    xy=(float(t[ci]), 0.0),
                    xytext=(0, dy),
                    textcoords="offset points",
                    ha="center",
                    va="bottom" if dy > 0 else "top",
                    color="#86efac" if is_up else "#fca5a5",
                    fontsize=7.4,
                    bbox=cls._pill_bbox("#15803d" if is_up else "#b91c1c", 0.84),
                    zorder=7,
                )

        v_now = float(vel_scaled[-1])
        ax.scatter([t[-1]], [v_now], color="#facc15", edgecolors="#ffffff", s=40, zorder=7)
        ax.annotate(
            f"Hoy: {v_now:+.4f}",
            xy=(float(t[-1]), v_now),
            xytext=(8, 0),
            textcoords="offset points",
            ha="left",
            va="center",
            color="#fde047",
            fontsize=7.7,
            fontweight="bold",
            bbox=cls._pill_bbox("#ca8a04", 0.85),
            zorder=8,
        )

        vmin, vmax = float(np.min(vel_scaled)), float(np.max(vel_scaled))
        vrng = vmax - vmin if vmax > vmin else 1e-4
        ax.set_ylim(vmin - vrng * 0.24, vmax + vrng * 0.24)

        max_x_plot = float(det_t[-1]) if len(det_t) > 0 else float(t[-1])
        ax.set_xlim(float(t[0]), max_x_plot + max(2.0, (max_x_plot - float(t[0])) * 0.165))

        ax.set_title(
            f"3. Primera Derivada (Velocidad / Momentum d{var_name}/dt)  —  Cuadrante: {kin['quadrant']}",
            color=cls.TEXT_MAIN,
            fontsize=9.6,
            fontweight="bold",
            loc="left",
        )
        ax.set_ylabel(
            f"d{var_name}/dt ({'%/v' if not disable_returns else 'u/v'})", color=cls.TEXT_MAIN, fontsize=8.8
        )

        if show_xticks:
            dt_step = float(t[1] - t[0]) if len(t) > 1 else 1.0
            cls._format_time_ticks(ax, float(t[0]), max_x_plot, float(t[0]), dt_step, dates_active)
            ax.set_xlabel("Tiempo Calendario / Horizonte Proyectado", color=cls.TEXT_MAIN, fontsize=8.8)
        else:
            plt.setp(ax.get_xticklabels(), visible=False)

    @classmethod
    def _draw_panel_4_acceleration(
        cls, ax: Any, run_result: HeadlessRunResult, show_xticks: bool = True
    ) -> None:
        tel = run_result.telemetry
        arr = run_result.arrays
        t: np.ndarray = arr["t"]
        dates_active: List[str] = arr["dates_active"]
        r_dot2: np.ndarray = arr["r_dot2"]
        det_t: np.ndarray = arr["det_t_path"]
        triggers: List[int] = list(arr["cusum_triggers"])

        cfg = tel["metadata"]["config"]
        kin = tel["geometry_and_phase_space"]["kinematics"]
        disable_returns = bool(cfg.get("disable_returns", False))
        var_name = "P" if disable_returns else "r"
        scale = 1.0 if disable_returns else 100.0

        seg_bounds = [0] + [int(idx) for idx in triggers if 0 < int(idx) < len(t)] + [len(t)]
        acc_scaled = r_dot2 * scale

        for i in range(len(seg_bounds) - 1):
            s_i, e_i = seg_bounds[i], seg_bounds[i + 1]
            s_plot = max(0, s_i - 1) if i > 0 else s_i
            col = cls.REGIME_COLORS[i % len(cls.REGIME_COLORS)]
            ax.plot(t[s_plot:e_i], acc_scaled[s_plot:e_i], color=col, linewidth=1.6)

        for trig_i in triggers:
            if 0 <= trig_i < len(t):
                ax.axvline(float(t[trig_i]), color="#facc15", linestyle="--", linewidth=0.85, alpha=0.40)

        ax.axhline(0.0, color="#94a3b8", linestyle="--", linewidth=0.9, alpha=0.68)

        # Anotar inflexiones d²r/dt² = 0 con fechas y precios (Refuerzo A)
        inflections = kin.get("recent_acceleration_inflections", [])[-4:]
        for k_idx, inf in enumerate(inflections):
            ci = int(inf["candle_idx"])
            if 0 <= ci < len(t):
                is_pos = "+d²r" in inf["transition"]
                ax.scatter(
                    [t[ci]],
                    [0.0],
                    marker="D",
                    color="#38bdf8" if is_pos else "#fb923c",
                    s=38,
                    zorder=6,
                )
                dy = 12 if (k_idx % 2 == 0) else -15
                ax.annotate(
                    f"{inf['date'][:10]} ({inf['price']:,.0f})",
                    xy=(float(t[ci]), 0.0),
                    xytext=(0, dy),
                    textcoords="offset points",
                    ha="center",
                    va="bottom" if dy > 0 else "top",
                    color="#7dd3fc" if is_pos else "#fdba74",
                    fontsize=7.4,
                    bbox=cls._pill_bbox("#0284c7" if is_pos else "#ea580c", 0.84),
                    zorder=7,
                )

        a_now = float(acc_scaled[-1])
        ax.scatter([t[-1]], [a_now], color="#facc15", edgecolors="#ffffff", s=40, zorder=7)
        ax.annotate(
            f"Hoy: {a_now:+.2e}",
            xy=(float(t[-1]), a_now),
            xytext=(8, 0),
            textcoords="offset points",
            ha="left",
            va="center",
            color="#fde047",
            fontsize=7.6,
            fontweight="bold",
            bbox=cls._pill_bbox("#ca8a04", 0.85),
            zorder=8,
        )

        amin, amax = float(np.min(acc_scaled)), float(np.max(acc_scaled))
        arng = amax - amin if amax > amin else 1e-6
        ax.set_ylim(amin - arng * 0.24, amax + arng * 0.24)

        max_x_plot = float(det_t[-1]) if len(det_t) > 0 else float(t[-1])
        ax.set_xlim(float(t[0]), max_x_plot + max(2.0, (max_x_plot - float(t[0])) * 0.165))

        ax.set_title(
            f"4. Segunda Derivada (Aceleración / Fuerza Neta d²{var_name}/dt²)",
            color=cls.TEXT_MAIN,
            fontsize=9.6,
            fontweight="bold",
            loc="left",
        )
        ax.set_ylabel(f"d²{var_name}/dt²", color=cls.TEXT_MAIN, fontsize=8.8)

        if show_xticks:
            dt_step = float(t[1] - t[0]) if len(t) > 1 else 1.0
            cls._format_time_ticks(ax, float(t[0]), max_x_plot, float(t[0]), dt_step, dates_active)
            ax.set_xlabel("Tiempo Calendario / Horizonte Proyectado", color=cls.TEXT_MAIN, fontsize=8.8)
        else:
            plt.setp(ax.get_xticklabels(), visible=False)

    @classmethod
    def _draw_panel_5_phase_attractor(cls, ax: Any, run_result: HeadlessRunResult) -> None:
        tel = run_result.telemetry
        arr = run_result.arrays
        t: np.ndarray = arr["t"]
        r_smooth: np.ndarray = arr["r_smooth"]
        v_smooth: np.ndarray = arr["v_smooth"]
        det_r_pct: np.ndarray = arr["det_r_pct_path"]
        det_v: np.ndarray = arr["det_v_path"]

        cfg = tel["metadata"]["config"]
        phs = tel["geometry_and_phase_space"]["phase_space"]
        cusum_f = tel["cusum_forensics"]
        disable_returns = bool(cfg.get("disable_returns", False))
        scale = 1.0 if disable_returns else 100.0

        r_pct_smooth = r_smooth * scale
        act_start = int(cusum_f["regimes_summary"][-1]["duration_candles"])
        act_idx0 = max(0, len(t) - act_start)

        if act_idx0 > 1:
            ax.plot(
                v_smooth[:act_idx0],
                r_pct_smooth[:act_idx0],
                color="#64748b",
                linewidth=0.85,
                alpha=0.28,
                label="Órbitas Pasadas",
            )

        v_act = v_smooth[act_idx0:]
        r_act = r_pct_smooth[act_idx0:]
        ax.plot(v_act, r_act, color="#00ffcc", linewidth=1.25, alpha=0.60, label="Órbita Régimen Vigente")
        ax.scatter(
            v_act,
            r_act,
            c=np.arange(len(v_act)),
            cmap="viridis",
            s=16,
            alpha=0.88,
            zorder=3,
        )

        # Flechas de dirección orbital (Refuerzo A)
        if len(v_act) >= 12:
            arrow_fracs = (0.22, 0.50, 0.78, 0.94)
            for frac in arrow_fracs:
                ai = min(len(v_act) - 2, max(1, int(len(v_act) * frac)))
                dx = float(v_act[ai + 1] - v_act[ai - 1])
                dy = float(r_act[ai + 1] - r_act[ai - 1])
                if abs(dx) + abs(dy) > 1e-9:
                    ax.annotate(
                        "",
                        xy=(float(v_act[ai + 1]), float(r_act[ai + 1])),
                        xytext=(float(v_act[ai - 1]), float(r_act[ai - 1])),
                        arrowprops={
                            "arrowstyle": "-|>",
                            "color": "#38bdf8",
                            "lw": 1.6,
                            "mutation_scale": 13,
                        },
                        zorder=5,
                    )

        # Marcador de inicio del régimen vigente
        if len(v_act) > 0:
            ax.scatter(
                [v_act[0]],
                [r_act[0]],
                marker="s",
                color="#38bdf8",
                edgecolors="#ffffff",
                linewidths=0.8,
                s=46,
                zorder=6,
                label=f"Inicio ({cusum_f['active_regime_start_date'][:10]})",
            )

        # Proyección en espacio homogéneo + flecha direccional
        if len(det_v) > 0 and len(det_r_pct) == len(det_v):
            ax.plot(
                det_v,
                det_r_pct,
                color="#f472b6",
                linestyle="--",
                linewidth=1.8,
                label="Atractor Proyectado (t+N)",
                zorder=4,
            )
            if len(det_v) >= 6:
                mi = len(det_v) // 2
                ax.annotate(
                    "",
                    xy=(float(det_v[mi + 1]), float(det_r_pct[mi + 1])),
                    xytext=(float(det_v[mi - 1]), float(det_r_pct[mi - 1])),
                    arrowprops={
                        "arrowstyle": "-|>",
                        "color": "#f472b6",
                        "lw": 1.6,
                        "mutation_scale": 12,
                    },
                    zorder=5,
                )

        v_now = float(v_smooth[-1])
        r_now = float(r_pct_smooth[-1])
        ax.scatter(
            [v_now],
            [r_now],
            color="#facc15",
            edgecolors="#ffffff",
            linewidths=1.0,
            s=82,
            zorder=7,
            label="Estado Presente",
        )
        ax.annotate(
            f"Hoy ({v_now:+.2f}, {r_now:+.3f}%)",
            xy=(v_now, r_now),
            xytext=(8, 8),
            textcoords="offset points",
            color="#fde047",
            fontsize=7.6,
            fontweight="bold",
            bbox=cls._pill_bbox("#ca8a04", 0.85),
            zorder=8,
        )

        ax.axhline(0.0, color="#475569", linestyle=":", linewidth=0.85)
        ax.axvline(0.0, color="#475569", linestyle=":", linewidth=0.85)

        rot_short = str(phs.get("rotation_sense", "")).split(" ")[0]
        ax.set_title(
            f"5. Atractor de Fase ({phs['topology_class']} · Giro {rot_short})",
            color=cls.TEXT_MAIN,
            fontsize=9.4,
            fontweight="bold",
            loc="left",
        )
        ax.set_xlabel("Volumen Suavizado Normalizado (V_z)", color=cls.TEXT_MAIN, fontsize=8.8)
        ax.set_ylabel(
            f"Inercia {'Retorno (%)' if not disable_returns else 'Precio'}", color=cls.TEXT_MAIN, fontsize=8.8
        )
        ax.legend(
            loc="upper right",
            fontsize=7.4,
            facecolor="#0f172a",
            edgecolor="#334155",
            framealpha=0.90,
            labelcolor=cls.TEXT_MAIN,
        )

    @classmethod
    def _draw_panel_6_cusum_tension(cls, ax: Any, run_result: HeadlessRunResult) -> None:
        tel = run_result.telemetry
        arr = run_result.arrays
        t: np.ndarray = arr["t"]
        dates_active: List[str] = arr["dates_active"]
        s_pos: np.ndarray = arr["cusum_s_pos"]
        s_neg: np.ndarray = arr["cusum_s_neg"]
        triggers: List[int] = list(arr["cusum_triggers"])

        cfg = tel["metadata"]["config"]
        cusum_f = tel["cusum_forensics"]
        cusum_h = float(cfg.get("cusum_h", 5.0))

        ax.plot(t, s_pos, color="#ef4444", linestyle=":", linewidth=1.3, label="S+ (Tensión Alcista)")
        ax.plot(t, s_neg, color="#22c55e", linestyle=":", linewidth=1.3, label="S- (Tensión Bajista)")
        ax.axhline(
            cusum_h,
            color="#f8fafc",
            linestyle="--",
            linewidth=1.15,
            label=f"Umbral Crítico H={cusum_h:.1f}",
        )

        for brk in cusum_f["macro_breaks"]:
            bi = int(brk["candle_idx"])
            if 0 <= bi < len(t):
                ax.axvline(float(t[bi]), color="#facc15", linestyle="--", linewidth=0.85, alpha=0.45)
                ax.scatter([t[bi]], [cusum_h], color="#facc15", marker="x", s=45, zorder=5)

        prev_bi: Optional[int] = None
        prev_tier = 0
        for brk in cusum_f["macro_breaks"][-3:]:
            bi = int(brk["candle_idx"])
            if 0 <= bi < len(t):
                if prev_bi is not None and abs(bi - prev_bi) < len(t) * 0.24:
                    tier = 1 - prev_tier
                else:
                    tier = 0
                dy_brk = 7 if tier == 0 else 21
                prev_bi = bi
                prev_tier = tier
                ax.annotate(
                    brk["date"][:10],
                    xy=(float(t[bi]), cusum_h),
                    xytext=(0, dy_brk),
                    textcoords="offset points",
                    ha="center",
                    color="#fde047",
                    fontsize=7.3,
                    bbox=cls._pill_bbox("#ca8a04", 0.84),
                    zorder=7,
                )

        # Señalar siempre el pico máximo de tensión CUSUM (Refuerzo A)
        peak_info = cusum_f.get("window_max_tension_peak")
        if peak_info and peak_info.get("peak_score", 0.0) > 0.05:
            pi = int(peak_info["candle_idx"])
            pval = float(peak_info["peak_score"])
            if 0 <= pi < len(t):
                ax.scatter([t[pi]], [pval], marker="D", color="#f472b6", edgecolors="#ffffff", s=46, zorder=7)
                if pi > len(t) * 0.62:
                    ha_pk, dx_pk = "right", -8
                elif pi < len(t) * 0.16:
                    ha_pk, dx_pk = "left", 8
                else:
                    ha_pk, dx_pk = "center", 0
                near_brk = any(abs(pi - int(b["candle_idx"])) < len(t) * 0.22 for b in cusum_f["macro_breaks"])
                dy_pk = -18 if (near_brk or pval >= cusum_h * 0.72 or pi < len(t) * 0.36) else 8
                ax.annotate(
                    f"Pico Máx ({peak_info['date'][:10]}): {pval:.2f}/{cusum_h:.1f}",
                    xy=(float(t[pi]), pval),
                    xytext=(dx_pk, dy_pk),
                    textcoords="offset points",
                    ha=ha_pk,
                    color="#f9a8d4",
                    fontsize=7.5,
                    fontweight="bold",
                    bbox=cls._pill_bbox("#db2777", 0.86),
                    zorder=8,
                )

        dt_step = float(t[1] - t[0]) if len(t) > 1 else 1.0
        t0_val = float(t[0])
        c_ticks = np.linspace(float(t[0]), float(t[-1]), num=5)
        c_labels = [
            dates_active[min(len(dates_active) - 1, max(0, int(round((cp - t0_val) / max(dt_step, 1e-8)))))][:10]
            for cp in c_ticks
        ]
        ax.set_xticks(c_ticks)
        ax.set_xticklabels(c_labels)
        max_s = max(float(np.max(s_pos)) if len(s_pos) else 0.0, float(np.max(s_neg)) if len(s_neg) else 0.0)
        ax.set_ylim(-0.35, max(cusum_h * 1.42, max_s * 1.22))
        ax.set_title(
            f"6. Tensión CUSUM (Drift k={cusum_f['current_tension']['drift_k']:.2f} | Quiebres={len(triggers)} | Hoy={cusum_f['current_tension']['max_tension']:.2f})",
            color=cls.TEXT_MAIN,
            fontsize=9.4,
            fontweight="bold",
            loc="left",
        )
        ax.set_xlabel("Tiempo Calendario (Ventana Activa)", color=cls.TEXT_MAIN, fontsize=8.8)
        ax.set_ylabel("Acumulador Z-Score", color=cls.TEXT_MAIN, fontsize=8.8)
        ax.legend(
            loc="upper left",
            fontsize=7.4,
            facecolor="#0f172a",
            edgecolor="#334155",
            framealpha=0.90,
            labelcolor=cls.TEXT_MAIN,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # API Pública 1: Dashboard Compuesto de 6 Paneles por Lente
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def render_dashboard(cls, run_result: HeadlessRunResult, output_path: str) -> str:
        """Renderiza los 6 paneles anotados (incluyendo Zoom Táctico) en `dashboard.png`."""
        tel = run_result.telemetry
        cfg = tel["metadata"]["config"]
        ds = tel["metadata"]["dataset"]
        kpis = tel["executive_kpis"]
        wb = tel["white_box_physics"]
        seal_wf = tel["reliability_seal"]["mini_walk_forward_oos"]
        seal_sum = tel["reliability_seal"].get("double_seal_summary", {})
        cusum_f = tel["cusum_forensics"]

        disable_returns = bool(cfg.get("disable_returns", False))
        var_name = "P" if disable_returns else "r"

        fig = plt.figure(figsize=(16.5, 17.6), dpi=160, facecolor=cls.BG_FIG)
        gs = gridspec.GridSpec(
            5,
            2,
            figure=fig,
            height_ratios=[2.15, 1.75, 0.95, 0.95, 1.65],
            hspace=0.32,
            wspace=0.16,
            top=0.905,
            bottom=0.048,
            left=0.062,
            right=0.975,
        )

        ax_price = fig.add_subplot(gs[0, :])
        ax_zoom = fig.add_subplot(gs[1, :])
        ax_vel = fig.add_subplot(gs[2, :], sharex=ax_price)
        ax_acc = fig.add_subplot(gs[3, :], sharex=ax_price)
        ax_phase = fig.add_subplot(gs[4, 0])
        ax_cusum = fig.add_subplot(gs[4, 1])

        for ax in (ax_price, ax_zoom, ax_vel, ax_acc, ax_phase, ax_cusum):
            cls._style_axis(ax)

        # Encabezado Ejecutivo
        ticker = ds["ticker"]
        last_p = ds["last_close_price"]
        last_d = ds["last_candle_date"]
        eq_r = wb["active_equations"][0] if wb["active_equations"] else "0"
        eq_v = wb["active_equations"][1] if len(wb["active_equations"]) > 1 else "0"
        wf_hr = seal_wf.get("consensus_hit_ratio_pct", "N/A")
        wf_cls = seal_wf.get("asset_physics_class", "N/A")
        eff_cuts = seal_wf.get("effective_cuts", seal_wf.get("valid_cuts", 0))
        seal_grade = seal_sum.get("seal_grade", wf_cls)

        title_line = (
            f"KINETOPUS ENGINE  |  {ticker} ({cfg['interval']} · Lente {ds['active_window_candles']}v · Últ. cierre {last_d}: {last_p:,.4f})"
        )
        sub_line_1 = (
            f"Inercia: {kpis['directional_inertia']} ({kpis['instant_velocity_pct_per_candle']:+.3f}%/v)   |   "
            f"Régimen #{kpis['active_regime_number']} ({kpis['active_regime_duration_candles']}v desde {cusum_f['active_regime_start_date']})   |   "
            f"SINDy R²: {kpis['sindy_r2_score']:.4f} ({kpis['sindy_r2_quality']})   |   "
            f"CUSUM: {kpis['cusum_semaphore']} ({kpis['cusum_tension_vs_h']})"
        )
        sub_line_2 = (
            f"EDO Activa: d{var_name}/dt = {eq_r}  ;  dV/dt = {eq_v}   |   "
            f"Doble Sello: {seal_grade} (OOS={wf_cls}, HR={wf_hr}%, Cortes={eff_cuts})   |   Confianza: {kpis['overall_physical_confidence']}"
        )

        fs_sub1 = min(9.3, max(7.4, 1520.0 / max(len(sub_line_1), 1)))
        fs_sub2 = min(8.6, max(7.2, 1340.0 / max(len(sub_line_2), 1)))
        fig.text(0.062, 0.970, title_line, color="#f8fafc", fontsize=13.0, fontweight="bold")
        fig.text(0.062, 0.946, sub_line_1, color="#38bdf8", fontsize=fs_sub1, fontweight="semibold")
        fig.text(0.062, 0.924, sub_line_2, color="#cbd5e1", fontsize=fs_sub2, family="monospace")

        cls._draw_panel_1_price_variety(ax_price, run_result, show_xticks=False)
        cls._draw_panel_2_tactical_zoom(ax_zoom, run_result)
        cls._draw_panel_3_velocity(ax_vel, run_result, show_xticks=False)
        cls._draw_panel_4_acceleration(ax_acc, run_result, show_xticks=True)
        cls._draw_panel_5_phase_attractor(ax_phase, run_result)
        cls._draw_panel_6_cusum_tension(ax_cusum, run_result)

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        fig.savefig(output_path, dpi=160, facecolor=cls.BG_FIG)
        plt.close(fig)
        return os.path.abspath(output_path)

    # ──────────────────────────────────────────────────────────────────────────
    # API Pública 2: Exportación Individual de Paneles en Alta Resolución (Refuerzo E)
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def render_individual_panels(
        cls, run_result: HeadlessRunResult, panels_dir: str, dpi: int = 200
    ) -> Dict[str, str]:
        """Exporta cada uno de los 6 paneles por separado en alta resolución para lectura escalonada."""
        os.makedirs(panels_dir, exist_ok=True)
        ds = run_result.telemetry["metadata"]["dataset"]
        header_tag = f"{ds['ticker']} · Lente {ds['active_window_candles']}v ({ds['last_candle_date']})"

        specs = [
            ("01_price_variety_cone.png", (14.0, 5.6), lambda ax: cls._draw_panel_1_price_variety(ax, run_result, show_xticks=True)),
            ("02_tactical_zoom_120v_t60.png", (14.0, 5.6), lambda ax: cls._draw_panel_2_tactical_zoom(ax, run_result)),
            ("03_velocity_dr_dt.png", (14.0, 4.6), lambda ax: cls._draw_panel_3_velocity(ax, run_result, show_xticks=True)),
            ("04_acceleration_d2r_dt2.png", (14.0, 4.6), lambda ax: cls._draw_panel_4_acceleration(ax, run_result, show_xticks=True)),
            ("05_phase_space_attractor.png", (9.2, 6.8), lambda ax: cls._draw_panel_5_phase_attractor(ax, run_result)),
            ("06_cusum_tension.png", (10.5, 5.6), lambda ax: cls._draw_panel_6_cusum_tension(ax, run_result)),
        ]

        exported: Dict[str, str] = {}
        for filename, fsize, drawer in specs:
            fig, ax = plt.subplots(figsize=fsize, dpi=dpi, facecolor=cls.BG_FIG)
            fig.subplots_adjust(top=0.86, bottom=0.13, left=0.08, right=0.96)
            cls._style_axis(ax)
            drawer(ax)
            fig.suptitle(f"KINETOPUS DETAIL  |  {header_tag}", color="#94a3b8", fontsize=9.5, x=0.08, ha="left")
            out_file = os.path.abspath(os.path.join(panels_dir, filename))
            fig.savefig(out_file, dpi=dpi, facecolor=cls.BG_FIG)
            plt.close(fig)
            exported[filename] = out_file

        return exported

    # ──────────────────────────────────────────────────────────────────────────
    # API Pública 3: Gráfico Maestro de Confluencia Multi-Lente (Refuerzo C)
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def render_confluence_chart(cls, multi_result: Any, output_path: str) -> str:
        """
        Renderiza `confluence.png`: imagen principal de la Parte 1 Ejecutiva.
          - Panel Superior: Serie histórica + 3 Variedades Spline C² superpuestas (2000v / 1000v / 500v).
          - Panel Central : Zoom de Confluencia Táctica (~220 velas recientes + Proyección t+60).
          - Panel Inferior: Curvas de Velocidad Inercial dr/dt (%/vela) superpuestas de las 3 lentes.
        """
        conf = multi_result.confluence
        slots = multi_result.lens_slots
        meta = conf["metadata"]
        ds = meta["dataset"]
        dl = meta["download"]
        hier = conf["hierarchy_verdict"]

        # Determinar extensión histórica máxima entre las lentes activas (o últimos 2000 puntos del dataset)
        avail_lengths = [
            len(sl.run_result.arrays["raw_price"])
            for sl in slots
            if sl.available and sl.run_result is not None
        ]
        max_hist = max(avail_lengths) if avail_lengths else min(2000, len(multi_result.raw_price_full))
        max_hist = max(10, min(max_hist, len(multi_result.raw_price_full)))

        p_base = np.asarray(multi_result.raw_price_full[-max_hist:], dtype=np.float64)
        dates_base = list(multi_result.dates_full[-max_hist:])
        x_base = np.arange(max_hist, dtype=np.float64)
        idx_today = max_hist - 1

        fig = plt.figure(figsize=(16.5, 13.4), dpi=180, facecolor=cls.BG_FIG)
        gs = gridspec.GridSpec(
            3,
            1,
            figure=fig,
            height_ratios=[1.55, 1.55, 1.15],
            hspace=0.30,
            top=0.875,
            bottom=0.055,
            left=0.065,
            right=0.975,
        )

        ax_macro = fig.add_subplot(gs[0, 0])
        ax_zoom = fig.add_subplot(gs[1, 0])
        ax_vel = fig.add_subplot(gs[2, 0])
        for ax in (ax_macro, ax_zoom, ax_vel):
            cls._style_axis(ax)

        # Cinta Ejecutiva Superior
        last_p = float(ds["last_close_price"])
        title_str = (
            f"KINETOPUS MULTI-LENS CONFLUENCE  |  {ds['ticker']} ({ds['interval']} · "
            f"Descarga '{dl['effective_period_used']}': {ds['total_downloaded_candles']}v · "
            f"Últ. cierre {ds['last_candle_date']}: {last_p:,.4f})"
        )
        hier_str = (
            f"FONDO ({slots[0].window_candles}v): {hier['background_trend_2000v']}   |   "
            f"CONFIRMACIÓN ({slots[1].window_candles}v): {hier['medium_confirmation_1000v']}   |   "
            f"TIMING ({slots[2].window_candles}v): {hier['short_timing_500v']}"
        )
        conf_str = (
            f"Patrón Jerárquico: {hier['alignment_pattern']}   |   "
            f"Confianza Física Global: {hier['global_physical_confidence']}"
        )

        fs_hier = min(9.1, max(7.3, 1480.0 / max(len(hier_str), 1)))
        fs_conf = min(9.0, max(7.5, 1480.0 / max(len(conf_str), 1)))
        fig.text(0.065, 0.960, title_str, color="#f8fafc", fontsize=12.8, fontweight="bold")
        fig.text(0.065, 0.931, hier_str, color="#38bdf8", fontsize=fs_hier, fontweight="semibold")
        fig.text(0.065, 0.904, conf_str, color="#fde047", fontsize=fs_conf, family="monospace")

        # ── PANEL 1: Panorama Multi-Lente (Precio + 3 Splines Superpuestos) ──
        ax_macro.scatter(x_base, p_base, s=7, color="#94a3b8", alpha=0.32, label="Precio Cierre Diario", zorder=1)

        horizon_max = int(meta["config"].get("horizon_steps", 150))
        zoom_len = min(220, max_hist)
        z_idx0 = max_hist - zoom_len
        zoom_h = min(60, horizon_max)

        ax_zoom.plot(
            x_base[z_idx0:],
            p_base[z_idx0:],
            color="#cbd5e1",
            linewidth=1.05,
            alpha=0.68,
            label="Precio Cierre Diario",
            zorder=2,
        )
        ax_zoom.scatter(x_base[z_idx0:], p_base[z_idx0:], s=14, color="#e2e8f0", alpha=0.72, zorder=2)

        zoom_y_collect: List[np.ndarray] = [p_base[z_idx0:]]
        endpoint_tags: List[Tuple[float, str, str]] = []

        for rank_idx, slot in enumerate(slots):
            col, short_role = cls.LENS_PALETTE.get(rank_idx, ("#e5e7eb", slot.role_label))
            lw = 2.4 - rank_idx * 0.22

            if not slot.available or slot.run_result is None:
                lbl_nd = f"{slot.window_candles}v ({short_role}): N/D — sin historial"
                ax_macro.plot([], [], color=col, linestyle=":", label=lbl_nd)
                ax_zoom.plot([], [], color=col, linestyle=":", label=lbl_nd)
                ax_vel.plot([], [], color=col, linestyle=":", label=lbl_nd)
                continue

            res = slot.run_result
            tel_l = res.telemetry
            arr_l = res.arrays
            nom_l = cls._get_nominal_smooth(res)
            n_l = len(nom_l)
            start_pos = max_hist - n_l
            if start_pos < 0:
                nom_l = nom_l[-max_hist:]
                vel_l = arr_l["r_dot"][-max_hist:]
                start_pos = 0
                n_l = len(nom_l)
            else:
                vel_l = arr_l["r_dot"]

            x_lens = np.arange(start_pos, start_pos + n_l, dtype=np.float64)
            disable_ret = bool(tel_l["metadata"]["config"].get("disable_returns", False))
            scale_l = 1.0 if disable_ret else 100.0
            vel_pct_l = vel_l * scale_l

            seal_ok = tel_l["reliability_seal"]["double_seal_summary"]["seal_passed"]
            wf_hr = tel_l["reliability_seal"]["mini_walk_forward_oos"].get("consensus_hit_ratio_pct", "N/A")
            seal_tag = f"Sello OK ({wf_hr}%)" if seal_ok else f"Sin Sello ({wf_hr}%)"
            lbl_full = (
                f"{slot.window_candles}v ({short_role}) · {tel_l['executive_kpis']['directional_inertia'].split(' ')[0]} · {seal_tag}"
            )

            # Curvas en Panel 1 (Macro)
            ax_macro.plot(x_lens, nom_l, color=col, linewidth=lw, label=lbl_full, zorder=3 + rank_idx)

            det_p = arr_l["det_price_path"]
            if len(det_p) > 0:
                x_fut = np.arange(idx_today + 1, idx_today + 1 + len(det_p), dtype=np.float64)
                ax_macro.plot(x_fut, det_p, color=col, linestyle="--", linewidth=1.5, alpha=0.88, zorder=4 + rank_idx)

            # Curvas en Panel 2 (Zoom Confluencia ~220v + t+60)
            mask_z = x_lens >= z_idx0
            if np.any(mask_z):
                ax_zoom.plot(x_lens[mask_z], nom_l[mask_z], color=col, linewidth=lw + 0.2, label=lbl_full, zorder=3 + rank_idx)
                zoom_y_collect.append(nom_l[mask_z])

            if len(det_p) >= zoom_h > 0:
                xf_z = np.arange(idx_today + 1, idx_today + 1 + zoom_h, dtype=np.float64)
                dp_z = det_p[:zoom_h]
                ax_zoom.plot(xf_z, dp_z, color=col, linestyle="--", linewidth=1.85, zorder=5 + rank_idx)
                ax_zoom.scatter([xf_z[-1]], [dp_z[-1]], color=col, s=28, zorder=7)
                endpoint_tags.append((float(dp_z[-1]), f"F_{slot.window_candles}v(t+{zoom_h}): {dp_z[-1]:,.2f}", col))
                zoom_y_collect.append(dp_z)

            # Sombrear suavemente el núcleo P25-P75 de la lente de Timing (o Confirmación si Timing no tiene MC)
            mc_p = arr_l["mc_price_percentiles"]
            if rank_idx == 2 and len(mc_p) == 5 and len(mc_p[1]) >= zoom_h > 0 and not tel_l["forecast_cone"]["unstable_flag"]:
                xf_z = np.arange(idx_today + 1, idx_today + 1 + zoom_h, dtype=np.float64)
                p25_t = np.asarray(mc_p[1][:zoom_h], dtype=np.float64)
                p75_t = np.asarray(mc_p[3][:zoom_h], dtype=np.float64)
                ax_zoom.fill_between(
                    xf_z, p25_t, p75_t, color=col, alpha=0.14, label=f"Núcleo P25-P75 ({slot.window_candles}v)", zorder=2
                )
                zoom_y_collect.extend([p25_t, p75_t])

                # Bandas CUSUM de la lente corta en el zoom
                inv_c = tel_l["cusum_forensics"]["invalidation_levels_1candle"]
                up_c = float(inv_c["upside_regime_break_price"])
                dn_c = float(inv_c["downside_regime_break_price"])
                ax_zoom.axhline(up_c, color="#38bdf8", linestyle=":", linewidth=1.1, alpha=0.75)
                ax_zoom.axhline(dn_c, color="#fb7185", linestyle=":", linewidth=1.1, alpha=0.75)
                zoom_y_collect.append(np.array([up_c, dn_c], dtype=np.float64))

            # Curvas en Panel 3 (Velocidades Superpuestas)
            ax_vel.plot(
                x_lens,
                vel_pct_l,
                color=col,
                linewidth=1.85,
                label=f"{slot.window_candles}v ({short_role}): hoy {vel_pct_l[-1]:+.4f}%/v ({tel_l['geometry_and_phase_space']['kinematics']['quadrant'].split('_')[0]})",
                zorder=3 + rank_idx,
            )
            ax_vel.scatter([x_lens[-1]], [vel_pct_l[-1]], color=col, edgecolors="#ffffff", linewidths=0.7, s=38, zorder=7)

        # Anotar endpoints de F(t+60) en Panel 2 ordenados verticalmente sin solaparse
        if endpoint_tags and zoom_h > 0:
            endpoint_tags.sort(key=lambda item: item[0], reverse=True)
            offsets_y = [14, 0, -14] if len(endpoint_tags) == 3 else ([10, -10] if len(endpoint_tags) == 2 else [0])
            x_tag = float(idx_today + zoom_h)
            for (y_val, txt, col_t), dy_off in zip(endpoint_tags, offsets_y):
                ax_zoom.annotate(
                    txt,
                    xy=(x_tag, y_val),
                    xytext=(-6, dy_off),
                    textcoords="offset points",
                    ha="right",
                    va="center",
                    color=col_t,
                    fontsize=7.8,
                    fontweight="bold",
                    bbox=cls._pill_bbox(col_t, 0.85),
                    zorder=9,
                )

        # Marcar frontera 'Hoy' en los 3 paneles
        for ax_i in (ax_macro, ax_zoom, ax_vel):
            ax_i.axvline(float(idx_today), color="#facc15", linestyle="-.", linewidth=0.95, alpha=0.60)

        ax_zoom.scatter([idx_today], [last_p], color="#facc15", edgecolors="#ffffff", s=52, zorder=8)
        ax_zoom.annotate(
            f"Hoy: {last_p:,.2f}",
            xy=(float(idx_today), last_p),
            xytext=(-8, 11),
            textcoords="offset points",
            ha="right",
            color="#fde047",
            fontsize=8.0,
            fontweight="bold",
            bbox=cls._pill_bbox("#ca8a04", 0.86),
            zorder=9,
        )

        # Ajustar escalas y etiquetas X de cada panel
        x_macro_end = float(idx_today + horizon_max)
        ax_macro.set_xlim(0.0, x_macro_end + max(3.0, x_macro_end * 0.02))
        cls._format_time_ticks(ax_macro, 0.0, x_macro_end, 0.0, 1.0, dates_base, num_ticks=9)
        ax_macro.set_title(
            "1. Panorama Estructural Multi-Lente — Precio Crudo + 3 Variedades Spline C² Superpuestas y Proyecciones F(t+150)",
            color=cls.TEXT_MAIN,
            fontsize=9.9,
            fontweight="bold",
            loc="left",
        )
        ax_macro.set_ylabel("Precio Nominal", color=cls.TEXT_MAIN, fontsize=8.8)
        ax_macro.legend(
            loc="upper left",
            ncol=2,
            fontsize=7.7,
            facecolor="#0f172a",
            edgecolor="#334155",
            labelcolor=cls.TEXT_MAIN,
        )

        flat_zy = np.concatenate([arr_y[np.isfinite(arr_y)] for arr_y in zoom_y_collect if len(arr_y) > 0])
        zy_min, zy_max = float(np.min(flat_zy)), float(np.max(flat_zy))
        zy_pad = (zy_max - zy_min) * 0.14 if zy_max > zy_min else 1.0
        ax_zoom.set_ylim(zy_min - zy_pad, zy_max + zy_pad)
        x_zoom_end = float(idx_today + zoom_h)
        ax_zoom.set_xlim(float(z_idx0), x_zoom_end + max(2.0, (x_zoom_end - z_idx0) * 0.03))
        cls._format_time_ticks(ax_zoom, float(z_idx0), x_zoom_end, 0.0, 1.0, dates_base, num_ticks=9)
        ax_zoom.set_title(
            f"2. Zoom de Confluencia y Divergencia Reciente (Últimas {zoom_len}v + Proyección t+{zoom_h} + Bandas CUSUM Timing)",
            color=cls.TEXT_MAIN,
            fontsize=9.9,
            fontweight="bold",
            loc="left",
        )
        ax_zoom.set_ylabel("Precio Zoom", color=cls.TEXT_MAIN, fontsize=8.8)
        ax_zoom.legend(
            loc="upper left",
            ncol=2,
            fontsize=7.5,
            facecolor="#0f172a",
            edgecolor="#334155",
            labelcolor=cls.TEXT_MAIN,
        )

        ax_vel.axhline(0.0, color="#94a3b8", linestyle="--", linewidth=0.95, alpha=0.72)
        ax_vel.set_xlim(0.0, float(idx_today) + max(5.0, max_hist * 0.02))
        cls._format_time_ticks(ax_vel, 0.0, float(idx_today), 0.0, 1.0, dates_base, num_ticks=9)
        ax_vel.set_title(
            "3. Confluencia de Velocidades Inerciales Superpuestas dr/dt (%/vela) — Giro de Timing vs. Fondo",
            color=cls.TEXT_MAIN,
            fontsize=9.9,
            fontweight="bold",
            loc="left",
        )
        ax_vel.set_ylabel("dr/dt (%/v)", color=cls.TEXT_MAIN, fontsize=8.8)
        ax_vel.set_xlabel("Tiempo Calendario / Horizonte Proyectado", color=cls.TEXT_MAIN, fontsize=8.8)
        ax_vel.legend(
            loc="upper left",
            ncol=2,
            fontsize=7.7,
            facecolor="#0f172a",
            edgecolor="#334155",
            labelcolor=cls.TEXT_MAIN,
        )

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        fig.savefig(output_path, dpi=180, facecolor=cls.BG_FIG)
        plt.close(fig)
        return os.path.abspath(output_path)
