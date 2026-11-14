"""
Renderizador Estático de 5 Paneles para KineTopus Engine (`Matplotlib Agg`).

Genera `dashboard.png` sin levantar navegador ni procesos pesados en RAM (16GB Rule),
replicando los 5 paneles del Dashboard interactivo de Hugging Face con:
  - Fechas calendario reales mapeadas sobre el eje temporal.
  - Escalas homogéneas corregidas en el Atractor de Espacio de Fase (V_z vs r_%).
  - Cinta superior con KPIs ejecutivos, ecuación SINDy vigente y Sello de Fiabilidad.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import numpy as np

from kinetopus_pro.headless_pipeline import HeadlessRunResult


class KinetopusStaticRenderer:
    """Renderizador oscuro 'Data Sci-Fi' de alta legibilidad para humanos y agentes multimodales."""

    BG_FIG = "#0b0f17"
    BG_PANEL = "#111827"
    GRID_COL = "#263248"
    TEXT_MAIN = "#e5e7eb"
    TEXT_MUTED = "#9ca3af"
    REGIME_COLORS = ["#00ffcc", "#ff9900", "#cc33ff", "#ff3366", "#33ccff", "#eab308"]

    @classmethod
    def render_dashboard(cls, run_result: HeadlessRunResult, output_path: str) -> str:
        """
        Renderiza los 5 paneles de telemetría físico-predictiva en un archivo PNG.

        Returns:
            str: Ruta absoluta del archivo PNG generado.
        """
        tel: Dict[str, Any] = run_result.telemetry
        arr: Dict[str, Any] = run_result.arrays

        t: np.ndarray = arr["t"]
        dates_active: List[str] = arr["dates_active"]
        raw_price: np.ndarray = arr["raw_price"]
        r_smooth: np.ndarray = arr["r_smooth"]
        r_dot: np.ndarray = arr["r_dot"]
        r_dot2: np.ndarray = arr["r_dot2"]
        v_smooth: np.ndarray = arr["v_smooth"]
        s_pos: np.ndarray = arr["cusum_s_pos"]
        s_neg: np.ndarray = arr["cusum_s_neg"]
        triggers: List[int] = list(arr["cusum_triggers"])
        det_t: np.ndarray = arr["det_t_path"]
        det_price: np.ndarray = arr["det_price_path"]
        det_r_pct: np.ndarray = arr["det_r_pct_path"]
        det_v: np.ndarray = arr["det_v_path"]
        mc_t: np.ndarray = arr["mc_t_path"]
        mc_p: List[List[float]] = arr["mc_price_percentiles"]

        cfg = tel["metadata"]["config"]
        ds = tel["metadata"]["dataset"]
        kpis = tel["executive_kpis"]
        wb = tel["white_box_physics"]
        seal_wf = tel["reliability_seal"]["mini_walk_forward_oos"]
        cusum_f = tel["cusum_forensics"]
        geom = tel["geometry_and_phase_space"]

        disable_returns = bool(cfg.get("disable_returns", False))
        var_name = "P" if disable_returns else "r"
        scale = 1.0 if disable_returns else 100.0
        cusum_h = float(cfg.get("cusum_h", 5.0))

        # Segmentos de regímenes para colorear curvas temporales y anclar la variedad de precio
        seg_bounds = [0] + [idx for idx in triggers if 0 < idx < len(t)] + [len(t)]

        # Reconstrucción de inercia nominal sobre el precio (anclada por régimen sin deriva espuria)
        if disable_returns:
            nominal_smooth = r_smooth.copy()
        else:
            nominal_smooth = np.empty_like(raw_price, dtype=np.float64)
            eps_p = 1e-8
            log_p = np.log(np.maximum(raw_price, eps_p))
            for i in range(len(seg_bounds) - 1):
                s_i, e_i = seg_bounds[i], seg_bounds[i + 1]
                if e_i <= s_i:
                    continue
                if e_i - s_i == 1:
                    nominal_smooth[s_i] = raw_price[s_i]
                    continue
                step_true = np.diff(log_p[s_i:e_i])
                step_smooth = r_smooth[s_i + 1 : e_i]
                mean_corr = float(np.mean(step_true - step_smooth))
                seg_log_p = np.empty(e_i - s_i, dtype=np.float64)
                seg_log_p[0] = log_p[s_i]
                seg_log_p[1:] = log_p[s_i] + np.cumsum(step_smooth + mean_corr)
                nominal_smooth[s_i:e_i] = np.exp(seg_log_p)

        fig = plt.figure(figsize=(15.5, 13.0), dpi=160, facecolor=cls.BG_FIG)
        gs = gridspec.GridSpec(
            4,
            2,
            figure=fig,
            height_ratios=[2.35, 0.95, 0.95, 1.65],
            hspace=0.30,
            wspace=0.16,
            top=0.88,
            bottom=0.06,
            left=0.065,
            right=0.975,
        )

        ax_price = fig.add_subplot(gs[0, :])
        ax_vel = fig.add_subplot(gs[1, :], sharex=ax_price)
        ax_acc = fig.add_subplot(gs[2, :], sharex=ax_price)
        ax_phase = fig.add_subplot(gs[3, 0])
        ax_cusum = fig.add_subplot(gs[3, 1])

        all_axes = [ax_price, ax_vel, ax_acc, ax_phase, ax_cusum]
        for ax in all_axes:
            ax.set_facecolor(cls.BG_PANEL)
            ax.grid(True, color=cls.GRID_COL, linestyle="--", linewidth=0.55, alpha=0.65)
            ax.tick_params(colors=cls.TEXT_MUTED, labelsize=8.5)
            for spine in ax.spines.values():
                spine.set_color("#334155")
                spine.set_linewidth(0.8)

        # ── Encabezado Ejecutivo ──────────────────────────────────────────────
        ticker = ds["ticker"]
        last_p = ds["last_close_price"]
        last_d = ds["last_candle_date"]
        eq_r = wb["active_equations"][0] if wb["active_equations"] else "0"
        eq_v = wb["active_equations"][1] if len(wb["active_equations"]) > 1 else "0"
        wf_hr = seal_wf.get("consensus_hit_ratio_pct", "N/A")
        wf_cls = seal_wf.get("asset_physics_class", "N/A")

        title_line = (
            f"KINETOPUS ENGINE  |  {ticker} ({cfg['interval']} · Ventana {ds['active_window_candles']}v · Últ. cierre {last_d}: {last_p:,.4f})"
        )
        sub_line_1 = (
            f"Inercia: {kpis['directional_inertia']} ({kpis['instant_velocity_pct_per_candle']:+.3f}%/v)   |   "
            f"Régimen #{kpis['active_regime_number']} ({kpis['active_regime_duration_candles']}v desde {cusum_f['active_regime_start_date']})   |   "
            f"SINDy R²: {kpis['sindy_r2_score']:.4f} ({kpis['sindy_r2_quality']})   |   "
            f"CUSUM: {kpis['cusum_semaphore']} ({kpis['cusum_tension_vs_h']})"
        )
        sub_line_2 = (
            f"EDO Activa: d{var_name}/dt = {eq_r}   ;   dV/dt = {eq_v}   |   "
            f"Sello OOS: {wf_cls} (HR={wf_hr}%)   |   Confianza: {kpis['overall_physical_confidence']}"
        )

        fig.text(0.065, 0.962, title_line, color="#f8fafc", fontsize=13.0, fontweight="bold")
        fig.text(0.065, 0.934, sub_line_1, color="#38bdf8", fontsize=9.3, fontweight="semibold")
        fig.text(0.065, 0.908, sub_line_2, color="#cbd5e1", fontsize=8.8, family="monospace")

        # ── PANEL 1: Precio Crudo + Spline por Regímenes + Cono Monte Carlo ──
        ax_price.scatter(
            t,
            raw_price,
            s=8,
            color="#94a3b8",
            alpha=0.38,
            label="Precio Crudo (Velas)",
            zorder=2,
        )

        for i in range(len(seg_bounds) - 1):
            s_i, e_i = seg_bounds[i], seg_bounds[i + 1]
            # Solapar 1 punto para continuidad visual entre tramos
            s_plot = max(0, s_i - 1) if i > 0 else s_i
            col = cls.REGIME_COLORS[i % len(cls.REGIME_COLORS)]
            lbl = "Inercia Spline C² (Por Régimen)" if i == 0 else None
            ax_price.plot(t[s_plot:e_i], nominal_smooth[s_plot:e_i], color=col, linewidth=1.8, label=lbl, zorder=3)

        has_mc = (
            len(mc_t) > 0
            and len(mc_p) == 5
            and len(mc_p[0]) == len(mc_t)
            and not tel["forecast_cone"]["empty_return_equation"]
            and not tel["forecast_cone"]["unstable_flag"]
        )

        if has_mc:
            p5 = np.asarray(mc_p[0], dtype=np.float64)
            p25 = np.asarray(mc_p[1], dtype=np.float64)
            p50 = np.asarray(mc_p[2], dtype=np.float64)
            p75 = np.asarray(mc_p[3], dtype=np.float64)
            p95 = np.asarray(mc_p[4], dtype=np.float64)

            ax_price.fill_between(
                mc_t, p5, p95, color="#ec4899", alpha=0.14, label="Cono Monte Carlo (P5-P95)", zorder=2
            )
            ax_price.fill_between(
                mc_t, p25, p75, color="#ec4899", alpha=0.26, label="Núcleo Estocástico (P25-P75)", zorder=2
            )
            ax_price.plot(mc_t, p50, color="#f472b6", linewidth=2.0, label="Mediana Estocástica (P50)", zorder=4)
            ax_price.scatter([mc_t[-1]], [p50[-1]], color="#ffffff", s=45, marker="*", zorder=6)
            ax_price.annotate(
                f"P50(t+{len(mc_t)}): {p50[-1]:,.2f}",
                xy=(mc_t[-1], p50[-1]),
                xytext=(-8, 8),
                textcoords="offset points",
                ha="right",
                color="#f472b6",
                fontsize=8.5,
                fontweight="bold",
            )

        if len(det_t) > 0 and len(det_price) == len(det_t):
            ax_price.plot(
                det_t,
                det_price,
                color="#00ffcc",
                linestyle="--",
                linewidth=1.9,
                label="Proyección Determinista F(t+N)",
                zorder=5,
            )
            ax_price.scatter([det_t[-1]], [det_price[-1]], color="#00ffcc", s=30, zorder=6)
            ax_price.annotate(
                f"F(t+{len(det_t)}): {det_price[-1]:,.2f}",
                xy=(det_t[-1], det_price[-1]),
                xytext=(-8, -13),
                textcoords="offset points",
                ha="right",
                color="#00ffcc",
                fontsize=8.5,
                fontweight="bold",
            )

        # Escala Y segura (evita que colas extremas aplasten el historial)
        hist_min = float(np.min(raw_price))
        hist_max = float(np.max(raw_price))
        hist_rng = hist_max - hist_min if hist_max != hist_min else max(abs(hist_max) * 0.1, 1.0)
        safe_max = hist_max + hist_rng * 1.5
        safe_min = hist_min - hist_rng * 1.5
        vis_max, vis_min = hist_max, hist_min

        if len(det_price) > 0:
            fin_det = det_price[np.isfinite(det_price)]
            if len(fin_det) > 0:
                vis_max = max(vis_max, min(safe_max, float(np.max(fin_det))))
                vis_min = min(vis_min, max(safe_min, float(np.min(fin_det))))
        if has_mc:
            fin_p50 = np.asarray(mc_p[2], dtype=np.float64)
            fin_p95 = np.asarray(mc_p[4], dtype=np.float64)
            fin_p5 = np.asarray(mc_p[0], dtype=np.float64)
            for arr_c in (fin_p50, fin_p95, fin_p5):
                valid_c = arr_c[np.isfinite(arr_c)]
                if len(valid_c) > 0:
                    vis_max = max(vis_max, min(safe_max, float(np.max(valid_c))))
                    vis_min = min(vis_min, max(safe_min, float(np.min(valid_c))))

        buf = hist_rng * 0.12
        ax_price.set_ylim(vis_min - buf, vis_max + buf)
        ax_price.set_title(
            "1. Variedad de Precio Nominal, Regímenes CUSUM y Cono Estocástico Euler-Maruyama",
            color=cls.TEXT_MAIN,
            fontsize=10.2,
            fontweight="bold",
            loc="left",
        )
        ax_price.set_ylabel("Precio Nominal", color=cls.TEXT_MAIN, fontsize=9.0)
        ax_price.legend(
            loc="upper left",
            ncol=3,
            fontsize=8.0,
            facecolor="#0f172a",
            edgecolor="#334155",
            labelcolor=cls.TEXT_MAIN,
        )

        # ── PANEL 2: Primera Derivada (Velocidad) ────────────────────────────
        vel_scaled = r_dot * scale
        for i in range(len(seg_bounds) - 1):
            s_i, e_i = seg_bounds[i], seg_bounds[i + 1]
            s_plot = max(0, s_i - 1) if i > 0 else s_i
            col = cls.REGIME_COLORS[i % len(cls.REGIME_COLORS)]
            ax_vel.plot(t[s_plot:e_i], vel_scaled[s_plot:e_i], color=col, linewidth=1.5)
        ax_vel.axhline(0.0, color="#94a3b8", linestyle="--", linewidth=0.8, alpha=0.6)
        ax_vel.scatter([t[-1]], [vel_scaled[-1]], color="#facc15", s=32, zorder=5)
        ax_vel.set_title(
            f"2. Primera Derivada (Velocidad / Momentum d{var_name}/dt)  —  Cuadrante Actual: {geom['kinematics']['quadrant']}",
            color=cls.TEXT_MAIN,
            fontsize=9.6,
            fontweight="bold",
            loc="left",
        )
        ax_vel.set_ylabel(f"d{var_name}/dt ({'%/v' if not disable_returns else 'u/v'})", color=cls.TEXT_MAIN, fontsize=8.8)

        # ── PANEL 3: Segunda Derivada (Aceleración) ──────────────────────────
        acc_scaled = r_dot2 * scale
        for i in range(len(seg_bounds) - 1):
            s_i, e_i = seg_bounds[i], seg_bounds[i + 1]
            s_plot = max(0, s_i - 1) if i > 0 else s_i
            col = cls.REGIME_COLORS[i % len(cls.REGIME_COLORS)]
            ax_acc.plot(t[s_plot:e_i], acc_scaled[s_plot:e_i], color=col, linewidth=1.5)
        ax_acc.axhline(0.0, color="#94a3b8", linestyle="--", linewidth=0.8, alpha=0.6)
        ax_acc.scatter([t[-1]], [acc_scaled[-1]], color="#facc15", s=32, zorder=5)
        ax_acc.set_title(
            f"3. Segunda Derivada (Aceleración / Fuerza Neta d²{var_name}/dt²)",
            color=cls.TEXT_MAIN,
            fontsize=9.6,
            fontweight="bold",
            loc="left",
        )
        ax_acc.set_ylabel(f"d²{var_name}/dt²", color=cls.TEXT_MAIN, fontsize=8.8)

        # Muros verticales de quiebres CUSUM en los paneles temporales
        for trig_i in triggers:
            if 0 <= trig_i < len(t):
                tx = float(t[trig_i])
                for ax_t in (ax_price, ax_vel, ax_acc):
                    ax_t.axvline(tx, color="#facc15", linestyle="--", linewidth=0.85, alpha=0.42)

        # Formateo de etiquetas temporales con fechas reales en el eje X compartido
        max_x_plot = float(det_t[-1]) if len(det_t) > 0 else float(t[-1])
        ax_price.set_xlim(float(t[0]), max_x_plot + max(2.0, (max_x_plot - float(t[0])) * 0.03))
        plt.setp(ax_price.get_xticklabels(), visible=False)
        plt.setp(ax_vel.get_xticklabels(), visible=False)

        dt_step = float(t[1] - t[0]) if len(t) > 1 else 1.0
        t0_val = float(t[0])
        tick_positions = np.linspace(float(t[0]), max_x_plot, num=9)
        tick_labels: List[str] = []
        for tp in tick_positions:
            rel_idx = int(round((tp - t0_val) / max(dt_step, 1e-8)))
            if 0 <= rel_idx < len(dates_active):
                tick_labels.append(dates_active[rel_idx][:10])
            else:
                ahead = rel_idx - (len(dates_active) - 1)
                tick_labels.append(f"t+{ahead}")
        ax_acc.set_xticks(tick_positions)
        ax_acc.set_xticklabels(tick_labels)
        ax_acc.set_xlabel("Tiempo Calendario / Horizonte Proyectado", color=cls.TEXT_MAIN, fontsize=8.8)

        # ── PANEL 4: Atractor de Espacio de Fase Homogéneo (V_z vs r_%) ──────
        r_pct_smooth = r_smooth * scale
        act_start = int(tel["cusum_forensics"]["regimes_summary"][-1]["duration_candles"])
        act_idx0 = max(0, len(t) - act_start)

        # Fondo tenue de regímenes anteriores
        if act_idx0 > 1:
            ax_phase.plot(
                v_smooth[:act_idx0],
                r_pct_smooth[:act_idx0],
                color="#64748b",
                linewidth=0.8,
                alpha=0.28,
                label="Órbitas Pasadas",
            )

        # Régimen activo coloreado por evolución temporal
        v_act = v_smooth[act_idx0:]
        r_act = r_pct_smooth[act_idx0:]
        ax_phase.plot(v_act, r_act, color="#00ffcc", linewidth=1.2, alpha=0.55, label="Órbita Régimen Vigente")
        sc = ax_phase.scatter(
            v_act,
            r_act,
            c=np.arange(len(v_act)),
            cmap="viridis",
            s=16,
            alpha=0.90,
            zorder=3,
        )

        # Proyección en el mismo espacio homogéneo (sin mezcla de escalas)
        if len(det_v) > 0 and len(det_r_pct) == len(det_v):
            ax_phase.plot(
                det_v,
                det_r_pct,
                color="#f472b6",
                linestyle="--",
                linewidth=1.7,
                label="Atractor Proyectado (t+N)",
                zorder=4,
            )

        ax_phase.scatter(
            [v_smooth[-1]],
            [r_pct_smooth[-1]],
            color="#facc15",
            edgecolors="#ffffff",
            linewidths=1.0,
            s=75,
            zorder=6,
            label="Estado Presente",
        )
        ax_phase.axhline(0.0, color="#475569", linestyle=":", linewidth=0.8)
        ax_phase.axvline(0.0, color="#475569", linestyle=":", linewidth=0.8)
        ax_phase.set_title(
            f"4. Atractor de Espacio de Fase ({geom['phase_space']['topology_class']})",
            color=cls.TEXT_MAIN,
            fontsize=9.6,
            fontweight="bold",
            loc="left",
        )
        ax_phase.set_xlabel("Volumen Suavizado Normalizado (V_z)", color=cls.TEXT_MAIN, fontsize=8.8)
        ax_phase.set_ylabel(
            f"Inercia {'Retorno (%)' if not disable_returns else 'Precio'}", color=cls.TEXT_MAIN, fontsize=8.8
        )
        ax_phase.legend(
            loc="upper right",
            fontsize=7.6,
            facecolor="#0f172a",
            edgecolor="#334155",
            labelcolor=cls.TEXT_MAIN,
        )

        # ── PANEL 5: Sistema Nervioso CUSUM y Quiebres Estructurales ─────────
        ax_cusum.plot(t, s_pos, color="#ef4444", linestyle=":", linewidth=1.25, label="S+ (Tensión Alcista)")
        ax_cusum.plot(t, s_neg, color="#22c55e", linestyle=":", linewidth=1.25, label="S- (Tensión Bajista)")
        ax_cusum.axhline(
            cusum_h,
            color="#f8fafc",
            linestyle="--",
            linewidth=1.1,
            label=f"Umbral Crítico H={cusum_h:.1f}",
        )

        for brk in cusum_f["macro_breaks"]:
            bi = int(brk["candle_idx"])
            if 0 <= bi < len(t):
                ax_cusum.axvline(float(t[bi]), color="#facc15", linestyle="--", linewidth=0.85, alpha=0.45)
                ax_cusum.scatter([t[bi]], [cusum_h], color="#facc15", marker="x", s=45, zorder=5)

        # Anotar hasta los últimos 3 quiebres con fecha corta
        for brk in cusum_f["macro_breaks"][-3:]:
            bi = int(brk["candle_idx"])
            if 0 <= bi < len(t):
                ax_cusum.annotate(
                    brk["date"][:10],
                    xy=(t[bi], cusum_h),
                    xytext=(0, 6),
                    textcoords="offset points",
                    ha="center",
                    color="#fde047",
                    fontsize=7.3,
                    rotation=15,
                )

        c_ticks = np.linspace(float(t[0]), float(t[-1]), num=5)
        c_labels = [
            dates_active[min(len(dates_active) - 1, max(0, int(round((cp - t0_val) / max(dt_step, 1e-8)))))][:10]
            for cp in c_ticks
        ]
        ax_cusum.set_xticks(c_ticks)
        ax_cusum.set_xticklabels(c_labels)
        ax_cusum.set_ylim(-0.25, max(cusum_h * 1.28, float(np.max(s_pos)) * 1.15, float(np.max(s_neg)) * 1.15))
        ax_cusum.set_title(
            f"5. Tensión CUSUM (Drift k={cusum_f['current_tension']['drift_k']:.2f} | Quiebres={len(triggers)})",
            color=cls.TEXT_MAIN,
            fontsize=9.6,
            fontweight="bold",
            loc="left",
        )
        ax_cusum.set_xlabel("Tiempo Calendario (Ventana Activa)", color=cls.TEXT_MAIN, fontsize=8.8)
        ax_cusum.set_ylabel("Acumulador Z-Score", color=cls.TEXT_MAIN, fontsize=8.8)
        ax_cusum.legend(
            loc="upper left",
            fontsize=7.6,
            facecolor="#0f172a",
            edgecolor="#334155",
            labelcolor=cls.TEXT_MAIN,
        )

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        fig.savefig(output_path, dpi=160, facecolor=cls.BG_FIG)
        plt.close(fig)
        return os.path.abspath(output_path)
