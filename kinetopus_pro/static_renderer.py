"""
Renderizador Estático de Estándar Financiero (`Matplotlib Agg`) — Estándar Definitivo v0.3.0.

Implementa la limpieza visual acordada (Decisiones 7, 8, 9 y 17):
  - Paleta unificada tipo terminal financiera (`dark` por defecto + `light`), compartida con `report.html`.
  - `render_hero_chart` (`hero.png`, más alias `render_confluence_chart`): Gráfico Héroe de un solo
    panel con velas japonesas (cuando hay OHLC) o curva limpia de cierre, `1000v` protagonista con
    cono calibrado hasta `t+150`, `2000v` tenue de contexto, alertas puntuales de `500v` y Regla
    Lateral de Niveles a la derecha sin solapamientos.
  - Lentes sin Doble Sello se trazan en gris punteado y sin proyección ni cono.
  - Cortes limpios por régimen en cada quiebre CUSUM (`Nuevo régimen · YYYY-MM-DD`), erradicando los
    escalones verticales artificiales tanto en `hero.png` como en `dashboard.png`.
  - Traducción 100% humana en español (cero `ENUM_STRINGS` internos en títulos, subtítulos o leyendas)
    y eliminación del hueco vacío a la derecha en los Paneles 3 y 4.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import numpy as np

from kinetopus_pro.headless_pipeline import HeadlessRunResult, KinetopusHeadlessPipeline


class KinetopusStaticRenderer:
    """Renderizador financiero unificado para el Gráfico Héroe y el Laboratorio Técnico de 6 paneles."""

    THEME_STYLES: Dict[str, Dict[str, str]] = {
        "dark": {
            "bg_fig": "#090d16",
            "bg_panel": "#0f172a",
            "bg_pill": "#090d16",
            "grid": "#1e293b",
            "spine": "#334155",
            "text_main": "#f8fafc",
            "text_sub": "#cbd5e1",
            "text_muted": "#94a3b8",
            "price_line": "#e2e8f0",
            "candle_up": "#10b981",
            "candle_dn": "#f43f5e",
            "lens_1000": "#f59e0b",
            "lens_1000_proj": "#fbbf24",
            "lens_1000_unsealed": "#f59e0b",
            "lens_2000": "#22d3ee",
            "lens_2000_proj": "#67e8f9",
            "lens_2000_unsealed": "#22d3ee",
            "lens_500": "#c084fc",
            "lens_500_proj": "#d8b4fe",
            "bull": "#10b981",
            "bear": "#f43f5e",
            "alert": "#c084fc",
            "today": "#eab308",
        },
        "light": {
            "bg_fig": "#f8fafc",
            "bg_panel": "#ffffff",
            "bg_pill": "#ffffff",
            "grid": "#e2e8f0",
            "spine": "#cbd5e1",
            "text_main": "#0f172a",
            "text_sub": "#334155",
            "text_muted": "#64748b",
            "price_line": "#1e293b",
            "candle_up": "#059669",
            "candle_dn": "#e11d48",
            "lens_1000": "#d97706",
            "lens_1000_proj": "#b45309",
            "lens_1000_unsealed": "#d97706",
            "lens_2000": "#0891b2",
            "lens_2000_proj": "#0e7490",
            "lens_2000_unsealed": "#0891b2",
            "lens_500": "#7c3aed",
            "lens_500_proj": "#6d28d9",
            "bull": "#059669",
            "bear": "#e11d48",
            "alert": "#7c3aed",
            "today": "#ca8a04",
        },
    }

    BG_FIG = THEME_STYLES["dark"]["bg_fig"]
    BG_PANEL = THEME_STYLES["dark"]["bg_panel"]
    GRID_COL = THEME_STYLES["dark"]["grid"]
    TEXT_MAIN = THEME_STYLES["dark"]["text_main"]
    TEXT_MUTED = THEME_STYLES["dark"]["text_muted"]
    REGIME_COLORS = ["#f59e0b", "#22d3ee", "#c084fc", "#14b8a6", "#eab308", "#f97316"]

    @classmethod
    def get_palette(cls, theme: str = "dark") -> Dict[str, str]:
        return cls.THEME_STYLES.get(theme, cls.THEME_STYLES["dark"])

    @classmethod
    def _lens_palette_for_window(cls, window_candles: int, theme: str = "dark") -> Tuple[str, str, str]:
        """Devuelve `(color_curva, color_proy, nombre_color)` por tamaño de lente."""
        pal = cls.get_palette(theme)
        if window_candles >= 1500:
            return pal["lens_2000"], pal["lens_2000_proj"], "Cian"
        if window_candles >= 750:
            return pal["lens_1000"], pal["lens_1000_proj"], "Ámbar"
        return pal["lens_500"], pal["lens_500_proj"], "Violeta"

    @classmethod
    def _style_axis(cls, ax: Any, theme: str = "dark") -> None:
        pal = cls.get_palette(theme)
        ax.set_facecolor(pal["bg_panel"])
        ax.grid(True, color=pal["grid"], linestyle="--", linewidth=0.55, alpha=0.72)
        ax.tick_params(colors=pal["text_muted"], labelsize=8.5)
        for spine in ax.spines.values():
            spine.set_color(pal["spine"])
            spine.set_linewidth(0.8)

    @classmethod
    def _pill_bbox(
        cls, edge: str = "#334155", alpha: float = 0.88, theme: str = "dark"
    ) -> Dict[str, Any]:
        pal = cls.get_palette(theme)
        return {
            "boxstyle": "round,pad=0.26",
            "facecolor": pal["bg_pill"],
            "edgecolor": edge,
            "linewidth": 0.75,
            "alpha": alpha,
        }

    @staticmethod
    def _format_price(val: float) -> str:
        av = abs(val)
        if av >= 1000.0:
            return f"{val:,.0f}"
        if av >= 10.0:
            return f"{val:,.2f}"
        return f"{val:,.4f}"

    @staticmethod
    def _format_time_ticks(
        ax: Any,
        x_min: float,
        x_max: float,
        t0_val: float,
        dt_step: float,
        dates_active: List[str],
        num_ticks: int = 8,
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

    @staticmethod
    def _deoverlap_vertical_positions(
        items: List[Dict[str, Any]], y_min: float, y_max: float, min_gap_frac: float = 0.068
    ) -> List[Dict[str, Any]]:
        """
        Ajusta la coordenada vertical `y_label` de un conjunto de etiquetas laterales para que
        jamás se solapen entre sí, conservando el orden de precios de mayor a menor.
        """
        if not items:
            return []
        ordered = sorted(items, key=lambda d: float(d["y"]), reverse=True)
        span = max(y_max - y_min, 1e-6)
        min_gap = span * min_gap_frac
        top_cap = y_max - span * 0.045
        bot_cap = y_min + span * 0.045

        placed = [dict(it, y_label=min(top_cap, max(bot_cap, float(it["y"])))) for it in ordered]
        for i in range(1, len(placed)):
            if placed[i - 1]["y_label"] - placed[i]["y_label"] < min_gap:
                placed[i]["y_label"] = placed[i - 1]["y_label"] - min_gap

        if placed[-1]["y_label"] < bot_cap:
            shift = bot_cap - placed[-1]["y_label"]
            for i in range(len(placed)):
                placed[i]["y_label"] += shift
            for i in range(len(placed) - 2, -1, -1):
                if placed[i]["y_label"] - placed[i + 1]["y_label"] < min_gap:
                    placed[i]["y_label"] = placed[i + 1]["y_label"] + min_gap
        return placed

    @classmethod
    def _plot_segmented_series(
        cls,
        ax: Any,
        x_vals: np.ndarray,
        y_vals: np.ndarray,
        triggers: Sequence[int],
        color: Optional[str] = None,
        palette_cycle: Optional[Sequence[str]] = None,
        linestyle: str = "-",
        linewidth: float = 2.0,
        alpha: float = 1.0,
        label: Optional[str] = None,
        zorder: int = 4,
        x_min_visible: Optional[float] = None,
        dates_for_pills: Optional[Sequence[str]] = None,
        draw_break_pills: bool = False,
        theme: str = "dark",
    ) -> None:
        """
        Traza una curva cortando limpiamente en cada quiebre CUSUM `[s_i : e_i]` sin unir
        extremos con escalones verticales artificiales (Decisión 8).
        """
        n = len(x_vals)
        if n == 0:
            return
        pal = cls.get_palette(theme)
        clean_trigs = sorted({int(idx) for idx in triggers if 0 < int(idx) < n})
        seg_bounds = [0] + clean_trigs + [n]

        first_labeled = False
        for i in range(len(seg_bounds) - 1):
            s_i, e_i = seg_bounds[i], seg_bounds[i + 1]
            if e_i <= s_i:
                continue
            seg_x = x_vals[s_i:e_i]
            seg_y = y_vals[s_i:e_i]
            if x_min_visible is not None:
                vis_mask = seg_x >= x_min_visible
                if not np.any(vis_mask):
                    continue
                seg_x = seg_x[vis_mask]
                seg_y = seg_y[vis_mask]
            seg_col = (
                color
                if color is not None
                else (palette_cycle[i % len(palette_cycle)] if palette_cycle else pal["lens_1000"])
            )
            seg_lbl = label if (label and not first_labeled) else None
            if seg_lbl:
                first_labeled = True
            ax.plot(
                seg_x,
                seg_y,
                color=seg_col,
                linestyle=linestyle,
                linewidth=linewidth,
                alpha=alpha,
                label=seg_lbl,
                zorder=zorder,
            )

        if draw_break_pills and clean_trigs:
            vis_trigs = [
                ti
                for ti in clean_trigs
                if x_min_visible is None or float(x_vals[ti]) >= x_min_visible
            ]
            last_x_drawn: Optional[float] = None
            tier = 0
            x_start_vis = float(x_min_visible if x_min_visible is not None else x_vals[0])
            x_span = max(float(x_vals[-1] - x_start_vis), 1.0)
            for ti in vis_trigs[-4:]:
                xv = float(x_vals[ti])
                ax.axvline(
                    xv,
                    color=pal["text_muted"],
                    linestyle="--",
                    linewidth=0.85,
                    alpha=0.52,
                    zorder=2,
                )
                if dates_for_pills is not None and 0 <= ti < len(dates_for_pills):
                    if last_x_drawn is not None and abs(xv - last_x_drawn) < x_span * 0.18:
                        tier = 1 - tier
                    else:
                        tier = 0
                    last_x_drawn = xv
                    x_rel = (xv - x_start_vis) / x_span
                    if x_rel < 0.48:
                        y_frac = 0.775 if tier == 0 else 0.695
                    else:
                        y_frac = 0.945 if tier == 0 else 0.865
                    d_str = str(dates_for_pills[ti])[:10]
                    ax.text(
                        xv,
                        y_frac,
                        f"Nuevo régimen · {d_str}",
                        transform=ax.get_xaxis_transform(),
                        ha="center",
                        va="top",
                        color=pal["text_sub"],
                        fontsize=7.3,
                        bbox=cls._pill_bbox(pal["spine"], 0.86, theme=theme),
                        zorder=8,
                    )

    # ──────────────────────────────────────────────────────────────────────────
    # API Pública 1: Gráfico Héroe de Un Solo Panel (`hero.png`, Decisión 7)
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def render_hero_chart(
        cls,
        multi_result: Any,
        output_path: str,
        theme: str = "dark",
        visible_history_candles: int = 500,
    ) -> str:
        """
        Renderiza el Gráfico Héroe geométrico v0.3.1 (`hero.png`):
          - Vista inicial ~500v + proyección t+150 con auto-escalado limpio.
          - Velas japonesas (cuando hay OHLC) o línea nítida de cierre.
          - Las 3 curvas y proyecciones t+150 simultáneamente: 2000v (Cian), 1000v (Ámbar), 500v (Violeta).
          - Cono calibrado EWMA P5–P95 y P25–P75 de la lente principal (1000v Ámbar).
          - Regla lateral geométrica a la derecha: Hoy, 2000v t+150, 1000v t+150, 500v t+150, P75 y P25.
        """
        pal = cls.get_palette(theme)
        conf = multi_result.confluence
        slots = multi_result.lens_slots
        ds = conf["metadata"]["dataset"]
        hier = conf["hierarchy_verdict"]

        n_full = len(multi_result.raw_price_full)
        vis_hist = max(60, min(int(visible_history_candles), n_full))
        h_start = n_full - vis_hist

        p_vis = np.asarray(multi_result.raw_price_full[h_start:], dtype=np.float64)
        dates_vis = list(multi_result.dates_full[h_start:])
        x_vis = np.arange(vis_hist, dtype=np.float64)
        idx_today = vis_hist - 1
        last_p = float(ds["last_close_price"])

        horizon_max = int(conf["metadata"]["config"].get("horizon_steps", 150))
        x_proj_end = float(idx_today + horizon_max)

        fig, ax = plt.subplots(figsize=(15.8, 8.4), dpi=180, facecolor=pal["bg_fig"])
        fig.subplots_adjust(top=0.845, bottom=0.095, left=0.062, right=0.795)
        cls._style_axis(ax, theme=theme)

        banner_txt = str(hier.get("executive_banner", "Diagnóstico Multi-Lente"))
        conf_lvl = str(hier.get("global_physical_confidence", "MEDIA"))
        conf_col = (
            pal["bull"]
            if conf_lvl == "ALTA"
            else (pal["lens_1000"] if conf_lvl == "MEDIA" else pal["bear"])
        )

        fig.text(
            0.062,
            0.942,
            f"{ds['ticker']}  ·  {banner_txt}",
            color=pal["text_main"],
            fontsize=13.5,
            fontweight="bold",
        )
        fig.text(
            0.795,
            0.944,
            f"Cierre {ds['last_candle_date']}: {cls._format_price(last_p)}   |   Confianza: {conf_lvl}",
            color=conf_col,
            fontsize=10.2,
            fontweight="bold",
            ha="right",
        )
        sub_ctx = (
            f"Marea 2000v (Cian): {hier.get('context_tide_2000v', 'N/D')}    ·    "
            f"Pulso 500v (Violeta): {hier.get('tactical_alert_500v', 'Vigilancia')}"
        )
        fs_sub = min(9.0, max(7.2, 1280.0 / max(len(sub_ctx), 1)))
        fig.text(0.062, 0.902, sub_ctx, color=pal["text_sub"], fontsize=fs_sub)

        y_collect: List[np.ndarray] = [p_vis]

        # 1. Precio: Velas japonesas si hay OHLC, línea nítida en caso contrario
        ohlc = getattr(multi_result, "ohlc_full", None)
        if ohlc is not None and len(ohlc.get("close", [])) == n_full:
            o_v = ohlc["open"][h_start:]
            h_v = ohlc["high"][h_start:]
            l_v = ohlc["low"][h_start:]
            c_v = ohlc["close"][h_start:]
            up_m = c_v >= o_v
            dn_m = ~up_m

            if np.any(up_m):
                ax.vlines(
                    x_vis[up_m],
                    l_v[up_m],
                    h_v[up_m],
                    color=pal["candle_up"],
                    linewidth=0.72,
                    alpha=0.68,
                    zorder=2,
                )
                body_up = np.maximum(c_v[up_m] - o_v[up_m], np.abs(c_v[up_m]) * 0.0006)
                ax.bar(
                    x_vis[up_m],
                    body_up,
                    width=0.64,
                    bottom=o_v[up_m],
                    color=pal["candle_up"],
                    alpha=0.70,
                    zorder=2,
                    label="Precio diario (OHLC)",
                )
            if np.any(dn_m):
                ax.vlines(
                    x_vis[dn_m],
                    l_v[dn_m],
                    h_v[dn_m],
                    color=pal["candle_dn"],
                    linewidth=0.72,
                    alpha=0.68,
                    zorder=2,
                )
                body_dn = np.maximum(o_v[dn_m] - c_v[dn_m], np.abs(c_v[dn_m]) * 0.0006)
                ax.bar(
                    x_vis[dn_m],
                    body_dn,
                    width=0.64,
                    bottom=c_v[dn_m],
                    color=pal["candle_dn"],
                    alpha=0.70,
                    zorder=2,
                    label="Precio diario (OHLC)" if not np.any(up_m) else None,
                )
            y_collect.extend([h_v, l_v])
        else:
            ax.plot(
                x_vis,
                p_vis,
                color=pal["price_line"],
                linewidth=1.35,
                alpha=0.88,
                label="Precio de cierre",
                zorder=2,
            )

        # 2. Dibujar SIEMPRE las 3 lentes (2000v Cian, 1000v Ámbar + cono, 500v Violeta) con t+150
        ruler_items: List[Dict[str, Any]] = [
            {
                "y": last_p,
                "text": f"Hoy · {cls._format_price(last_p)}",
                "color": pal["today"],
                "edge": pal["today"],
            }
        ]
        p25_end_1000: Optional[float] = None
        p75_end_1000: Optional[float] = None

        # Orden de dibujo: 2000v (fondo), 500v (medio), 1000v (protagonista arriba + cono)
        draw_order = [0, 2, 1]
        for s_idx in draw_order:
            if s_idx >= len(slots):
                continue
            slot = slots[s_idx]
            if not slot.available or slot.run_result is None:
                continue
            res_l = slot.run_result
            arr_l = res_l.arrays
            nom_l = cls._get_nominal_smooth(res_l)
            trigs_l = list(arr_l["cusum_triggers"])
            dates_l = list(arr_l["dates_active"])
            offset_l = (n_full - len(nom_l)) - h_start
            x_l = np.arange(len(nom_l), dtype=np.float64) + offset_l
            c_col, p_col, c_name = cls._lens_palette_for_window(slot.window_candles, theme=theme)
            is_pri = s_idx == 1

            cls._plot_segmented_series(
                ax=ax,
                x_vals=x_l,
                y_vals=nom_l,
                triggers=trigs_l,
                color=c_col,
                linestyle="-",
                linewidth=2.55 if is_pri else (1.90 if s_idx == 0 else 1.70),
                alpha=0.96 if is_pri else 0.85,
                label=f"Curva {slot.window_candles}v ({c_name})",
                zorder=5 if is_pri else (3 if s_idx == 0 else 4),
                x_min_visible=0.0,
                dates_for_pills=dates_l if is_pri else None,
                draw_break_pills=is_pri,
                theme=theme,
            )
            vis_mask_l = x_l >= 0.0
            if np.any(vis_mask_l):
                y_collect.append(nom_l[vis_mask_l])

            det_l = np.asarray(arr_l.get("det_price_path", []), dtype=np.float64)
            mc_l = arr_l.get("mc_price_percentiles", [])
            if len(det_l) > 0:
                xf_l = np.arange(idx_today + 1, idx_today + 1 + len(det_l), dtype=np.float64)
                xf_join = np.concatenate(([float(idx_today)], xf_l))
                det_join = np.concatenate(([last_p], det_l))

                if is_pri and len(mc_l) == 5 and len(mc_l[0]) == len(det_l):
                    p5 = np.concatenate(([last_p], np.asarray(mc_l[0], dtype=np.float64)))
                    p25 = np.concatenate(([last_p], np.asarray(mc_l[1], dtype=np.float64)))
                    p75 = np.concatenate(([last_p], np.asarray(mc_l[3], dtype=np.float64)))
                    p95 = np.concatenate(([last_p], np.asarray(mc_l[4], dtype=np.float64)))
                    ax.fill_between(
                        xf_join,
                        p5,
                        p95,
                        color=c_col,
                        alpha=0.10,
                        label="Banda P5–P95 (1000v)",
                        zorder=2,
                    )
                    ax.fill_between(
                        xf_join,
                        p25,
                        p75,
                        color=c_col,
                        alpha=0.22,
                        label="Cuartiles P25–P75 (1000v)",
                        zorder=3,
                    )
                    p25_end_1000 = float(p25[-1])
                    p75_end_1000 = float(p75[-1])
                    y_collect.extend([p5, p25, p75, p95])

                ax.plot(
                    xf_join,
                    det_join,
                    color=p_col,
                    linestyle="--",
                    linewidth=2.25 if is_pri else 1.75,
                    alpha=0.95 if is_pri else 0.90,
                    label=f"Proy. {slot.window_candles}v (t+{len(det_l)})",
                    zorder=6 if is_pri else 5,
                )
                ax.scatter([xf_join[-1]], [float(det_l[-1])], color=p_col, s=30 if is_pri else 22, zorder=7)
                y_collect.append(det_l)

                end_val = float(det_l[-1])
                end_pct = ((end_val - last_p) / last_p) * 100.0 if last_p else 0.0
                ruler_items.append(
                    {
                        "y": end_val,
                        "text": f"{slot.window_candles}v t+{len(det_l)} · {cls._format_price(end_val)} ({end_pct:+.1f}%)",
                        "color": p_col,
                        "edge": c_col,
                    }
                )

        if p75_end_1000 is not None:
            p75_pct = ((p75_end_1000 - last_p) / last_p) * 100.0 if last_p else 0.0
            ruler_items.append(
                {
                    "y": p75_end_1000,
                    "text": f"P75 (1000v) · {cls._format_price(p75_end_1000)} ({p75_pct:+.1f}%)",
                    "color": pal["bull"],
                    "edge": pal["bull"],
                }
            )
        if p25_end_1000 is not None:
            p25_pct = ((p25_end_1000 - last_p) / last_p) * 100.0 if last_p else 0.0
            ruler_items.append(
                {
                    "y": p25_end_1000,
                    "text": f"P25 (1000v) · {cls._format_price(p25_end_1000)} ({p25_pct:+.1f}%)",
                    "color": pal["bear"],
                    "edge": pal["bear"],
                }
            )

        # 3. Marcadores puntuales de alerta táctica de 500v
        tac_detail = hier.get("tactical_sensor_detail", {})
        pins = tac_detail.get("pins", [])
        for p_idx, pin in enumerate(pins[-3:]):
            c_ago = int(pin.get("candles_ago", 0))
            x_pin = float(idx_today - c_ago)
            if 0.0 <= x_pin <= float(idx_today):
                y_pin = float(pin.get("price", last_p))
                is_up_pin = pin.get("direction") == "UP"
                pin_col = pal["bull"] if is_up_pin else pal["alert"]
                ax.scatter(
                    [x_pin],
                    [y_pin],
                    marker="^" if is_up_pin else "v",
                    color=pin_col,
                    edgecolors=pal["bg_fig"],
                    linewidths=0.9,
                    s=72,
                    zorder=8,
                    label="Alerta táctica 500v" if p_idx == 0 else None,
                )
                dy_pin = -18 if is_up_pin else 15
                ax.annotate(
                    str(pin.get("label", "Alerta 500v")),
                    xy=(x_pin, y_pin),
                    xytext=(0, dy_pin),
                    textcoords="offset points",
                    ha="center",
                    va="top" if dy_pin < 0 else "bottom",
                    color=pal["text_main"],
                    fontsize=7.3,
                    bbox=cls._pill_bbox(pin_col, 0.88, theme=theme),
                    zorder=9,
                )

        # 4. Separador Hoy y guías de horizonte (1m / 3m / t+150)
        ax.axvline(float(idx_today), color=pal["today"], linestyle="-.", linewidth=1.0, alpha=0.68, zorder=5)
        ax.scatter(
            [float(idx_today)],
            [last_p],
            color=pal["today"],
            edgecolors="#ffffff",
            linewidths=1.0,
            s=56,
            zorder=9,
        )

        for m_obj in ds.get("horizon_milestones", []):
            st_m = int(m_obj["step"])
            lbl_m = str(m_obj["label"])
            if st_m in (21, 30, 63, 90, horizon_max):
                xm = float(idx_today + st_m)
                ax.axvline(xm, color=pal["spine"], linestyle=":", linewidth=0.75, alpha=0.55, zorder=1)
                ax.text(
                    xm,
                    0.02,
                    lbl_m,
                    transform=ax.get_xaxis_transform(),
                    ha="center",
                    va="bottom",
                    color=pal["text_muted"],
                    fontsize=7.3,
                )

        flat_y = np.concatenate([v[np.isfinite(v)] for v in y_collect if len(v) > 0])
        ymin_raw, ymax_raw = float(np.min(flat_y)), float(np.max(flat_y))
        yrng = ymax_raw - ymin_raw if ymax_raw > ymin_raw else max(abs(last_p) * 0.1, 1.0)
        y_lo = ymin_raw - yrng * 0.10
        y_hi = ymax_raw + yrng * 0.14
        ax.set_ylim(y_lo, y_hi)
        ax.set_xlim(-2.0, x_proj_end + 4.0)

        # 5. Regla Lateral Geométrica en el margen derecho
        placed_ruler = cls._deoverlap_vertical_positions(ruler_items, y_lo, y_hi, min_gap_frac=0.078)
        for r_item in placed_ruler:
            ax.annotate(
                r_item["text"],
                xy=(x_proj_end, float(r_item["y"])),
                xytext=(x_proj_end + 8.0, float(r_item["y_label"])),
                ha="left",
                va="center",
                color=r_item["color"],
                fontsize=8.0,
                fontweight="bold",
                annotation_clip=False,
                arrowprops={
                    "arrowstyle": "-",
                    "color": r_item["edge"],
                    "lw": 0.85,
                    "alpha": 0.70,
                },
                bbox=cls._pill_bbox(r_item["edge"], 0.92, theme=theme),
                zorder=10,
            )

        cls._format_time_ticks(ax, 0.0, x_proj_end, 0.0, 1.0, dates_vis, num_ticks=9)
        ax.set_ylabel("Precio", color=pal["text_main"], fontsize=9.2)
        ax.set_xlabel(f"Últimas {vis_hist} velas y proyección simultánea t+{horizon_max}", color=pal["text_muted"], fontsize=8.6)
        ax.legend(
            loc="upper left",
            ncol=3,
            fontsize=7.7,
            facecolor=pal["bg_fig"],
            edgecolor=pal["spine"],
            labelcolor=pal["text_main"],
        )

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        fig.savefig(output_path, dpi=180, facecolor=pal["bg_fig"])
        plt.close(fig)
        return os.path.abspath(output_path)

    @classmethod
    def render_confluence_chart(cls, multi_result: Any, output_path: str) -> str:
        """Alias compatible hacia `render_hero_chart`."""
        return cls.render_hero_chart(multi_result, output_path, theme="dark")

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers individuales de los 6 paneles de Laboratorio Técnico (100% humanos)
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def _draw_panel_1_price_variety(
        cls, ax: Any, run_result: HeadlessRunResult, show_xticks: bool = True
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
        kin = tel["geometry_and_phase_space"]["kinematics"]
        curve_fit = tel["geometry_and_phase_space"].get("curve_price_fit", {})
        lens_win = int(ds["active_window_candles"])
        lens_col, proj_col, color_lbl = cls._lens_palette_for_window(lens_win)

        ax.plot(
            t,
            raw_price,
            color="#94a3b8",
            linewidth=0.85,
            alpha=0.48,
            label="Precio de cierre",
            zorder=2,
        )

        cls._plot_segmented_series(
            ax=ax,
            x_vals=t,
            y_vals=nominal_smooth,
            triggers=triggers,
            color=lens_col,
            linestyle="-",
            linewidth=2.05,
            alpha=0.95,
            label=f"Curva suave {lens_win}v ({color_lbl})",
            zorder=3,
            dates_for_pills=dates_active,
            draw_break_pills=True,
        )

        last_p = float(ds["last_close_price"])
        gap_pct = float(kin.get("price_vs_spline_gap_pct", 0.0))
        ax.scatter([t[-1]], [last_p], color="#eab308", edgecolors="#ffffff", linewidths=0.9, s=46, zorder=7)
        ax.annotate(
            f"Hoy: {cls._format_price(last_p)} (dist. curva {gap_pct:+.1f}%)",
            xy=(float(t[-1]), last_p),
            xytext=(-10, 12 if gap_pct >= 0 else -14),
            textcoords="offset points",
            ha="right",
            va="bottom" if gap_pct >= 0 else "top",
            color="#fde047",
            fontsize=8.0,
            fontweight="bold",
            bbox=cls._pill_bbox("#ca8a04", 0.88),
            zorder=8,
        )

        has_mc = len(mc_t) > 0 and len(mc_p) == 5 and len(mc_p[0]) == len(mc_t)
        has_det = len(det_t) > 0 and len(det_price) == len(det_t)

        if has_mc:
            p5 = np.asarray(mc_p[0], dtype=np.float64)
            p25 = np.asarray(mc_p[1], dtype=np.float64)
            p75 = np.asarray(mc_p[3], dtype=np.float64)
            p95 = np.asarray(mc_p[4], dtype=np.float64)
            ax.fill_between(mc_t, p5, p95, color=lens_col, alpha=0.11, label="Banda amplia (P5–P95)", zorder=2)
            ax.fill_between(mc_t, p25, p75, color=lens_col, alpha=0.24, label="Cuartiles (P25–P75)", zorder=2)

        if has_det:
            det_end = float(det_price[-1])
            ax.plot(
                det_t,
                det_price,
                color=proj_col,
                linestyle="--",
                linewidth=2.05,
                label=f"Proyección {lens_win}v (t+{len(det_t)})",
                zorder=5,
            )
            ax.scatter([det_t[-1]], [det_end], color=proj_col, s=34, zorder=7)
            ax.annotate(
                f"t+{len(det_t)}: {cls._format_price(det_end)}",
                xy=(float(det_t[-1]), det_end),
                xytext=(6, 0),
                textcoords="offset points",
                ha="left",
                va="center",
                color=proj_col,
                fontsize=8.0,
                fontweight="bold",
                bbox=cls._pill_bbox(lens_col, 0.88),
                zorder=8,
            )

        hist_min = float(np.min(raw_price))
        hist_max = float(np.max(raw_price))
        hist_rng = hist_max - hist_min if hist_max != hist_min else max(abs(hist_max) * 0.1, 1.0)
        safe_max = hist_max + hist_rng * 1.35
        safe_min = max(0.0, hist_min - hist_rng * 1.15) if hist_min > 0 else hist_min - hist_rng * 1.15
        vis_max = hist_max
        vis_min = hist_min

        if has_det:
            fin_det = det_price[np.isfinite(det_price)]
            if len(fin_det) > 0:
                vis_max = max(vis_max, min(safe_max, float(np.max(fin_det))))
                vis_min = min(vis_min, max(safe_min, float(np.min(fin_det))))
        if has_mc:
            for idx_p in (0, 4):
                arr_c = np.asarray(mc_p[idx_p], dtype=np.float64)
                valid_c = arr_c[np.isfinite(arr_c)]
                if len(valid_c) > 0:
                    vis_max = max(vis_max, min(safe_max, float(np.max(valid_c))))
                    vis_min = min(vis_min, max(safe_min, float(np.min(valid_c))))

        buf = (vis_max - vis_min) * 0.12 if vis_max > vis_min else 1.0
        y_lo_p1, y_hi_p1 = vis_min - buf, vis_max + buf
        ax.set_ylim(y_lo_p1, y_hi_p1)

        max_x_plot = float(det_t[-1]) if len(det_t) > 0 else float(t[-1])
        ax.set_xlim(float(t[0]), max_x_plot + max(2.0, (max_x_plot - float(t[0])) * 0.15))

        fit_r2 = float(curve_fit.get("window_price_r2", 0.0))
        fit_mape = float(curve_fit.get("window_price_mape_pct", 0.0))
        ax.set_title(
            f"1. Panorama Completo ({lens_win}v · {color_lbl}), Regímenes CUSUM y Cono t+{len(det_t) if has_det else 150}  —  Ajuste Curva-Precio R²={fit_r2:.3f} (MAPE {fit_mape:.2f}%)",
            color=cls.TEXT_MAIN,
            fontsize=10.0,
            fontweight="bold",
            loc="left",
        )
        ax.set_ylabel("Precio", color=cls.TEXT_MAIN, fontsize=8.8)
        ax.legend(
            loc="upper left",
            ncol=3,
            fontsize=7.6,
            facecolor="#090d16",
            edgecolor="#334155",
            labelcolor=cls.TEXT_MAIN,
        )

        if show_xticks:
            dt_step = float(t[1] - t[0]) if len(t) > 1 else 1.0
            cls._format_time_ticks(ax, float(t[0]), max_x_plot, float(t[0]), dt_step, dates_active)
        else:
            plt.setp(ax.get_xticklabels(), visible=False)

    @classmethod
    def _draw_panel_2_tactical_zoom(
        cls,
        ax: Any,
        run_result: HeadlessRunResult,
        zoom_candles: int = 120,
        zoom_horizon: int = 150,
    ) -> None:
        """Zoom táctico de las últimas ~120 velas + proyección completa t+150 sin líneas de 1 vela."""
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
        lens_win = int(ds["active_window_candles"])
        lens_col, proj_col, color_lbl = cls._lens_palette_for_window(lens_win)
        kin = tel["geometry_and_phase_space"]["kinematics"]

        z_start = max(0, len(t) - zoom_candles)
        t_z = t[z_start:]
        p_z = raw_price[z_start:]
        s_z = nominal_smooth[z_start:]

        ax.plot(t_z, p_z, color="#cbd5e1", linewidth=1.1, alpha=0.76, label="Precio de cierre", zorder=3)
        ax.scatter(t_z, p_z, s=14, color="#e2e8f0", alpha=0.80, zorder=3)

        cls._plot_segmented_series(
            ax=ax,
            x_vals=t,
            y_vals=nominal_smooth,
            triggers=triggers,
            color=lens_col,
            linestyle="-",
            linewidth=2.3,
            alpha=0.95,
            label=f"Curva {lens_win}v ({color_lbl})",
            zorder=4,
            x_min_visible=float(t_z[0]),
            dates_for_pills=dates_active,
            draw_break_pills=True,
        )

        for rev in kin.get("recent_velocity_reversals", []):
            ci = int(rev["candle_idx"])
            if z_start <= ci < len(t):
                is_up = "ALZA" in rev["type"]
                ax.scatter(
                    [t[ci]],
                    [raw_price[ci]],
                    marker="^" if is_up else "v",
                    color="#10b981" if is_up else "#f43f5e",
                    s=58,
                    zorder=6,
                )
                ax.annotate(
                    f"Giro {'alza' if is_up else 'baja'} ({rev['date'][:10]}: {cls._format_price(rev['price'])})",
                    xy=(float(t[ci]), float(raw_price[ci])),
                    xytext=(0, -14 if is_up else 12),
                    textcoords="offset points",
                    ha="center",
                    color="#6ee7b7" if is_up else "#fda4af",
                    fontsize=7.4,
                    bbox=cls._pill_bbox("#059669" if is_up else "#e11d48", 0.86),
                    zorder=7,
                )

        h_cut = min(zoom_horizon, len(det_t))
        has_mc = len(mc_t) >= h_cut > 0 and len(mc_p) == 5 and len(mc_p[0]) >= h_cut
        y_vals = [p_z, s_z]

        if has_mc:
            mt_z = mc_t[:h_cut]
            p5_z = np.asarray(mc_p[0][:h_cut], dtype=np.float64)
            p25_z = np.asarray(mc_p[1][:h_cut], dtype=np.float64)
            p75_z = np.asarray(mc_p[3][:h_cut], dtype=np.float64)
            p95_z = np.asarray(mc_p[4][:h_cut], dtype=np.float64)

            ax.fill_between(mt_z, p5_z, p95_z, color=lens_col, alpha=0.11, zorder=2)
            ax.fill_between(mt_z, p25_z, p75_z, color=lens_col, alpha=0.25, label=f"Cuartiles P25–P75 (t+{h_cut})", zorder=2)
            y_vals.extend([p25_z, p75_z])

        if h_cut > 0 and len(det_price) >= h_cut:
            dt_z = det_t[:h_cut]
            dp_z = det_price[:h_cut]
            det_z_end = float(dp_z[-1])
            ax.plot(dt_z, dp_z, color=proj_col, linestyle="--", linewidth=2.1, label=f"Proyección {lens_win}v (t+{h_cut})", zorder=6)
            ax.scatter([dt_z[-1]], [det_z_end], color=proj_col, s=34, zorder=7)
            y_vals.append(dp_z)
            if has_mc:
                p25_end = float(mc_p[1][h_cut - 1])
                p75_end = float(mc_p[3][h_cut - 1])
                lbl_z = f"t+{h_cut}: {cls._format_price(det_z_end)} [P25–P75: {cls._format_price(p25_end)}–{cls._format_price(p75_end)}]"
            else:
                lbl_z = f"t+{h_cut}: {cls._format_price(det_z_end)}"
            ax.annotate(
                lbl_z,
                xy=(float(dt_z[-1]), det_z_end),
                xytext=(-6, 12),
                textcoords="offset points",
                ha="right",
                color=proj_col,
                fontsize=7.8,
                fontweight="bold",
                bbox=cls._pill_bbox(lens_col, 0.88),
                zorder=9,
            )

        last_p = float(raw_price[-1])
        ax.axvline(float(t[-1]), color="#eab308", linestyle="-.", linewidth=0.95, alpha=0.62)
        ax.scatter([t[-1]], [last_p], color="#eab308", edgecolors="#ffffff", s=50, zorder=8)
        ax.annotate(
            f"Hoy: {cls._format_price(last_p)}",
            xy=(float(t[-1]), last_p),
            xytext=(-8, -14),
            textcoords="offset points",
            ha="right",
            va="top",
            color="#fde047",
            fontsize=8.0,
            fontweight="bold",
            bbox=cls._pill_bbox("#ca8a04", 0.88),
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
            f"2. Zoom Reciente (Últimas {len(t_z)} velas + t+{h_cut})  —  Distancia media 30v a su curva: {gap_30:+.2f}%",
            color=cls.TEXT_MAIN,
            fontsize=9.8,
            fontweight="bold",
            loc="left",
        )
        ax.set_ylabel("Precio Zoom", color=cls.TEXT_MAIN, fontsize=8.8)
        ax.legend(
            loc="upper left",
            ncol=3,
            fontsize=7.4,
            facecolor="#090d16",
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
        triggers: List[int] = list(arr["cusum_triggers"])

        cfg = tel["metadata"]["config"]
        kin = tel["geometry_and_phase_space"]["kinematics"]
        h_reg = tel.get("human_regime", {})
        disable_returns = bool(cfg.get("disable_returns", False))
        scale = 1.0 if disable_returns else 100.0
        vel_scaled = r_dot * scale

        cls._plot_segmented_series(
            ax=ax,
            x_vals=t,
            y_vals=vel_scaled,
            triggers=triggers,
            palette_cycle=cls.REGIME_COLORS,
            linewidth=1.65,
        )
        for trig_i in triggers:
            if 0 < trig_i < len(t):
                ax.axvline(float(t[trig_i]), color="#94a3b8", linestyle="--", linewidth=0.8, alpha=0.45)

        ax.axhline(0.0, color="#94a3b8", linestyle="--", linewidth=0.9, alpha=0.68)

        reversals = kin.get("recent_velocity_reversals", [])[-4:]
        for k_idx, rev in enumerate(reversals):
            ci = int(rev["candle_idx"])
            if 0 <= ci < len(t):
                is_up = "ALZA" in rev["type"]
                ax.scatter(
                    [t[ci]],
                    [0.0],
                    marker="^" if is_up else "v",
                    color="#10b981" if is_up else "#f43f5e",
                    s=50,
                    zorder=6,
                )
                dy = 12 if (k_idx % 2 == 0) else -15
                ax.annotate(
                    f"{rev['date'][:10]} ({cls._format_price(rev['price'])})",
                    xy=(float(t[ci]), 0.0),
                    xytext=(0, dy),
                    textcoords="offset points",
                    ha="center",
                    va="bottom" if dy > 0 else "top",
                    color="#6ee7b7" if is_up else "#fda4af",
                    fontsize=7.3,
                    bbox=cls._pill_bbox("#059669" if is_up else "#e11d48", 0.84),
                    zorder=7,
                )

        v_now = float(vel_scaled[-1])
        ax.scatter([t[-1]], [v_now], color="#eab308", edgecolors="#ffffff", s=40, zorder=7)
        ax.annotate(
            f"Hoy: {v_now:+.4f}",
            xy=(float(t[-1]), v_now),
            xytext=(-8, 10),
            textcoords="offset points",
            ha="right",
            va="bottom",
            color="#fde047",
            fontsize=7.7,
            fontweight="bold",
            bbox=cls._pill_bbox("#ca8a04", 0.86),
            zorder=8,
        )

        vmin, vmax = float(np.min(vel_scaled)), float(np.max(vel_scaled))
        vrng = vmax - vmin if vmax > vmin else 1e-4
        ax.set_ylim(vmin - vrng * 0.24, vmax + vrng * 0.24)

        # Ajustar xlim exactamente hasta Hoy (sin hueco vacío derecho)
        x_span = max(float(t[-1] - t[0]), 1.0)
        ax.set_xlim(float(t[0]), float(t[-1]) + x_span * 0.025)

        state_human = h_reg.get("state_label", "Estado cinemático")
        ax.set_title(
            f"3. Velocidad del Retorno (Impulso Diario)  —  Lectura: {state_human}",
            color=cls.TEXT_MAIN,
            fontsize=9.6,
            fontweight="bold",
            loc="left",
        )
        ax.set_ylabel("% / vela" if not disable_returns else "u / vela", color=cls.TEXT_MAIN, fontsize=8.8)

        if show_xticks:
            dt_step = float(t[1] - t[0]) if len(t) > 1 else 1.0
            cls._format_time_ticks(ax, float(t[0]), float(t[-1]), float(t[0]), dt_step, dates_active)
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
        triggers: List[int] = list(arr["cusum_triggers"])

        cfg = tel["metadata"]["config"]
        kin = tel["geometry_and_phase_space"]["kinematics"]
        disable_returns = bool(cfg.get("disable_returns", False))
        scale = 1.0 if disable_returns else 100.0
        acc_scaled = r_dot2 * scale

        cls._plot_segmented_series(
            ax=ax,
            x_vals=t,
            y_vals=acc_scaled,
            triggers=triggers,
            palette_cycle=cls.REGIME_COLORS,
            linewidth=1.65,
        )
        for trig_i in triggers:
            if 0 < trig_i < len(t):
                ax.axvline(float(t[trig_i]), color="#94a3b8", linestyle="--", linewidth=0.8, alpha=0.45)

        ax.axhline(0.0, color="#94a3b8", linestyle="--", linewidth=0.9, alpha=0.68)

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
                    s=36,
                    zorder=6,
                )
                dy = 12 if (k_idx % 2 == 0) else -15
                ax.annotate(
                    f"{inf['date'][:10]} ({cls._format_price(inf['price'])})",
                    xy=(float(t[ci]), 0.0),
                    xytext=(0, dy),
                    textcoords="offset points",
                    ha="center",
                    va="bottom" if dy > 0 else "top",
                    color="#7dd3fc" if is_pos else "#fdba74",
                    fontsize=7.3,
                    bbox=cls._pill_bbox("#0284c7" if is_pos else "#ea580c", 0.84),
                    zorder=7,
                )

        a_now = float(acc_scaled[-1])
        ax.scatter([t[-1]], [a_now], color="#eab308", edgecolors="#ffffff", s=40, zorder=7)
        ax.annotate(
            f"Hoy: {a_now:+.2e}",
            xy=(float(t[-1]), a_now),
            xytext=(-8, 10),
            textcoords="offset points",
            ha="right",
            va="bottom",
            color="#fde047",
            fontsize=7.6,
            fontweight="bold",
            bbox=cls._pill_bbox("#ca8a04", 0.86),
            zorder=8,
        )

        amin, amax = float(np.min(acc_scaled)), float(np.max(acc_scaled))
        arng = amax - amin if amax > amin else 1e-6
        ax.set_ylim(amin - arng * 0.24, amax + arng * 0.24)

        x_span = max(float(t[-1] - t[0]), 1.0)
        ax.set_xlim(float(t[0]), float(t[-1]) + x_span * 0.025)

        ax.set_title(
            "4. Aceleración del Retorno (Cambio de Ritmo / Inflexiones)",
            color=cls.TEXT_MAIN,
            fontsize=9.6,
            fontweight="bold",
            loc="left",
        )
        ax.set_ylabel("Cambio vel.", color=cls.TEXT_MAIN, fontsize=8.8)

        if show_xticks:
            dt_step = float(t[1] - t[0]) if len(t) > 1 else 1.0
            cls._format_time_ticks(ax, float(t[0]), float(t[-1]), float(t[0]), dt_step, dates_active)
            ax.set_xlabel("Fechas de la ventana analizada", color=cls.TEXT_MAIN, fontsize=8.6)
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
        ds = tel["metadata"]["dataset"]
        lens_col, proj_col, _ = cls._lens_palette_for_window(int(ds["active_window_candles"]))
        phs = tel["geometry_and_phase_space"]["phase_space"]
        cusum_f = tel["cusum_forensics"]
        h_reg = tel.get("human_regime", {})
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
                label="Regímenes anteriores",
            )

        v_act = v_smooth[act_idx0:]
        r_act = r_pct_smooth[act_idx0:]
        ax.plot(v_act, r_act, color=lens_col, linewidth=1.3, alpha=0.68, label="Régimen actual")
        ax.scatter(
            v_act,
            r_act,
            c=np.arange(len(v_act)),
            cmap="viridis",
            s=16,
            alpha=0.88,
            zorder=3,
        )

        if len(v_act) >= 12:
            for frac in (0.25, 0.55, 0.85):
                ai = min(len(v_act) - 2, max(1, int(len(v_act) * frac)))
                dx = float(v_act[ai + 1] - v_act[ai - 1])
                dy = float(r_act[ai + 1] - r_act[ai - 1])
                if abs(dx) + abs(dy) > 1e-9:
                    ax.annotate(
                        "",
                        xy=(float(v_act[ai + 1]), float(r_act[ai + 1])),
                        xytext=(float(v_act[ai - 1]), float(r_act[ai - 1])),
                        arrowprops={"arrowstyle": "-|>", "color": proj_col, "lw": 1.5, "mutation_scale": 12},
                        zorder=5,
                    )

        if len(v_act) > 0:
            ax.scatter(
                [v_act[0]],
                [r_act[0]],
                marker="s",
                color=lens_col,
                edgecolors="#ffffff",
                linewidths=0.8,
                s=44,
                zorder=6,
                label=f"Inicio ({cusum_f['active_regime_start_date'][:10]})",
            )

        if len(det_v) > 0 and len(det_r_pct) == len(det_v):
            ax.plot(
                det_v,
                det_r_pct,
                color=proj_col,
                linestyle="--",
                linewidth=1.8,
                label="Trayectoria proyectada",
                zorder=4,
            )

        v_now = float(v_smooth[-1])
        r_now = float(r_pct_smooth[-1])
        ax.scatter(
            [v_now],
            [r_now],
            color="#eab308",
            edgecolors="#ffffff",
            linewidths=1.0,
            s=80,
            zorder=7,
            label="Estado hoy",
        )
        ax.annotate(
            f"Hoy ({v_now:+.2f}, {r_now:+.3f}%)",
            xy=(v_now, r_now),
            xytext=(8, 8),
            textcoords="offset points",
            color="#fde047",
            fontsize=7.5,
            fontweight="bold",
            bbox=cls._pill_bbox("#ca8a04", 0.86),
            zorder=8,
        )

        ax.axhline(0.0, color="#475569", linestyle=":", linewidth=0.85)
        ax.axvline(0.0, color="#475569", linestyle=":", linewidth=0.85)

        topo_human = h_reg.get(
            "topology_human",
            KinetopusHeadlessPipeline.humanize_code("topology", phs.get("topology_class")),
        )
        rot_raw = str(phs.get("rotation_sense", "")).split(" ")[0].lower()
        rot_human = (
            "giro antihorario"
            if "antihorario" in rot_raw
            else ("giro horario" if "horario" in rot_raw else "lineal")
        )
        ax.set_title(
            f"5. Mapa Retorno-Volumen ({topo_human} · {rot_human})",
            color=cls.TEXT_MAIN,
            fontsize=9.4,
            fontweight="bold",
            loc="left",
        )
        ax.set_xlabel("Volumen normalizado (V_z)", color=cls.TEXT_MAIN, fontsize=8.8)
        ax.set_ylabel(
            f"Retorno suavizado ({'%' if not disable_returns else 'Precio'})",
            color=cls.TEXT_MAIN,
            fontsize=8.8,
        )
        ax.legend(
            loc="upper right",
            fontsize=7.3,
            facecolor="#090d16",
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

        ax.plot(t, s_pos, color="#10b981", linestyle="-", linewidth=1.25, alpha=0.85, label="Presión alcista (S+)")
        ax.plot(t, s_neg, color="#f43f5e", linestyle="-", linewidth=1.25, alpha=0.85, label="Presión bajista (S-)")
        ax.axhline(
            cusum_h,
            color="#f8fafc",
            linestyle="--",
            linewidth=1.15,
            label=f"Umbral de cambio H={cusum_h:.1f}",
        )

        for brk in cusum_f["macro_breaks"]:
            bi = int(brk["candle_idx"])
            if 0 <= bi < len(t):
                ax.axvline(float(t[bi]), color="#eab308", linestyle="--", linewidth=0.85, alpha=0.45)
                ax.scatter([t[bi]], [cusum_h], color="#eab308", marker="x", s=45, zorder=5)

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

        peak_info = cusum_f.get("window_max_tension_peak")
        if peak_info and peak_info.get("peak_score", 0.0) > 0.05:
            pi = int(peak_info["candle_idx"])
            pval = float(peak_info["peak_score"])
            if 0 <= pi < len(t):
                ax.scatter([t[pi]], [pval], marker="D", color="#c084fc", edgecolors="#ffffff", s=44, zorder=7)
                if pi > len(t) * 0.62:
                    ha_pk, dx_pk = "right", -8
                elif pi < len(t) * 0.16:
                    ha_pk, dx_pk = "left", 8
                else:
                    ha_pk, dx_pk = "center", 0
                near_brk = any(abs(pi - int(b["candle_idx"])) < len(t) * 0.22 for b in cusum_f["macro_breaks"])
                dy_pk = -18 if (near_brk or pval >= cusum_h * 0.72 or pi < len(t) * 0.36) else 8
                ax.annotate(
                    f"Pico máx. ({peak_info['date'][:10]}): {pval:.2f}/{cusum_h:.1f}",
                    xy=(float(t[pi]), pval),
                    xytext=(dx_pk, dy_pk),
                    textcoords="offset points",
                    ha=ha_pk,
                    color="#e9d5ff",
                    fontsize=7.4,
                    fontweight="bold",
                    bbox=cls._pill_bbox("#9333ea", 0.86),
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
            f"6. Tensión de Cambio de Régimen CUSUM (k={cusum_f['current_tension']['drift_k']:.2f} · Cambios={len(triggers)} · Hoy={cusum_f['current_tension']['max_tension']:.2f})",
            color=cls.TEXT_MAIN,
            fontsize=9.4,
            fontweight="bold",
            loc="left",
        )
        ax.set_xlabel("Fechas de la ventana analizada", color=cls.TEXT_MAIN, fontsize=8.6)
        ax.set_ylabel("Tensión acumulada", color=cls.TEXT_MAIN, fontsize=8.8)
        has_left_break = any(int(b["candle_idx"]) < len(t) * 0.36 for b in cusum_f["macro_breaks"])
        ax.legend(
            loc="upper right" if has_left_break else "upper left",
            fontsize=7.3,
            facecolor="#090d16",
            edgecolor="#334155",
            framealpha=0.90,
            labelcolor=cls.TEXT_MAIN,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # API Pública 2: Dashboard Compuesto de 6 Paneles por Lente (Decisión 9)
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def render_dashboard(cls, run_result: HeadlessRunResult, output_path: str) -> str:
        """Renderiza los 6 paneles técnicos con etiquetas humanas limpias en `dashboard.png`."""
        tel = run_result.telemetry
        cfg = tel["metadata"]["config"]
        ds = tel["metadata"]["dataset"]
        kpis = tel["executive_kpis"]
        wb = tel["white_box_physics"]
        seal_wf = tel["reliability_seal"]["mini_walk_forward_oos"]
        seal_sum = tel["reliability_seal"].get("double_seal_summary", {})
        cusum_f = tel["cusum_forensics"]
        h_reg = tel.get("human_regime", {})

        disable_returns = bool(cfg.get("disable_returns", False))
        var_name = "P" if disable_returns else "r"

        fig = plt.figure(figsize=(16.5, 17.6), dpi=160, facecolor=cls.BG_FIG)
        gs = gridspec.GridSpec(
            5,
            2,
            figure=fig,
            height_ratios=[2.15, 1.75, 0.95, 0.95, 1.65],
            hspace=0.33,
            wspace=0.16,
            top=0.905,
            bottom=0.048,
            left=0.062,
            right=0.975,
        )

        ax_price = fig.add_subplot(gs[0, :])
        ax_zoom = fig.add_subplot(gs[1, :])
        ax_vel = fig.add_subplot(gs[2, :])
        ax_acc = fig.add_subplot(gs[3, :])
        ax_phase = fig.add_subplot(gs[4, 0])
        ax_cusum = fig.add_subplot(gs[4, 1])

        for ax in (ax_price, ax_zoom, ax_vel, ax_acc, ax_phase, ax_cusum):
            cls._style_axis(ax)

        ticker = ds["ticker"]
        last_p = float(ds["last_close_price"])
        last_d = ds["last_candle_date"]
        eq_r = wb["active_equations"][0] if wb["active_equations"] else "0"
        eq_v = wb["active_equations"][1] if len(wb["active_equations"]) > 1 else "0"
        wf_hr = seal_wf.get("consensus_hit_ratio_pct", "N/D")
        eff_cuts = seal_wf.get("effective_cuts", seal_wf.get("valid_cuts", 0))
        cone_cal = seal_wf.get("cone_calibration", {})
        cov_iqr = cone_cal.get("empirical_p25_p75_coverage_pct")
        cov_txt = f" · Cobertura P25–P75: {cov_iqr:.0f}%" if isinstance(cov_iqr, (int, float)) else ""

        human_full = h_reg.get("full_label", "Diagnóstico de régimen")
        seal_human = h_reg.get(
            "seal_human",
            KinetopusHeadlessPipeline.humanize_code("seal_grade", seal_sum.get("seal_grade")),
        )
        cusum_human = h_reg.get(
            "cusum_human",
            KinetopusHeadlessPipeline.humanize_code("cusum_status", kpis.get("cusum_semaphore")),
        )
        conf_human = KinetopusHeadlessPipeline.humanize_code(
            "confidence", kpis.get("overall_physical_confidence")
        )

        lens_win = int(ds["active_window_candles"])
        lens_col, _, color_lbl = cls._lens_palette_for_window(lens_win)
        curve_fit = tel["geometry_and_phase_space"].get("curve_price_fit", {})
        fit_r2 = float(kpis.get("curve_price_r2", curve_fit.get("window_price_r2", 0.0)))
        fit_mape = float(kpis.get("curve_price_mape_pct", curve_fit.get("window_price_mape_pct", 0.0)))
        fit_lbl = str(kpis.get("curve_price_quality", curve_fit.get("fit_label", "Moderado")))

        oos_str = (
            f"{seal_human} (OOS {wf_hr}% / {eff_cuts} cortes{cov_txt})"
            if seal_wf.get("executed", False)
            else f"{seal_human} · Proyección t+{cfg.get('horizon_steps', 150)} activa"
        )

        title_line = (
            f"LABORATORIO TÉCNICO KINETOPUS v0.3.1  |  {ticker} ({cfg['interval']} · Ventana {lens_win}v · Color {color_lbl} · Cierre {last_d}: {cls._format_price(last_p)})"
        )
        sub_line_1 = (
            f"Estado: {human_full}   |   "
            f"Régimen actual: {kpis['active_regime_duration_candles']}v ({cusum_f['active_regime_start_date']})   |   "
            f"Ajuste Curva-Precio: R²={fit_r2:.3f} (MAPE {fit_mape:.2f}%, {fit_lbl})   |   "
            f"CUSUM: {cusum_human} ({kpis['cusum_tension_vs_h']})"
        )
        sub_line_2 = (
            f"Ecuaciones: d{var_name}/dt = {eq_r}  ;  dV/dt = {eq_v}   |   "
            f"SINDy R²={kpis['sindy_r2_score']:.3f}   |   {oos_str}   |   Confianza: {conf_human}"
        )

        fs_sub1 = min(9.1, max(7.2, 1520.0 / max(len(sub_line_1), 1)))
        fs_sub2 = min(8.4, max(7.0, 1360.0 / max(len(sub_line_2), 1)))
        fig.text(0.062, 0.970, title_line, color="#f8fafc", fontsize=12.6, fontweight="bold")
        fig.text(0.062, 0.946, sub_line_1, color=lens_col, fontsize=fs_sub1, fontweight="semibold")
        fig.text(0.062, 0.924, sub_line_2, color="#cbd5e1", fontsize=fs_sub2, family="monospace")

        cls._draw_panel_1_price_variety(ax_price, run_result, show_xticks=True)
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
    # API Pública 3: Exportación Individual de Paneles en Alta Resolución
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def render_individual_panels(
        cls, run_result: HeadlessRunResult, panels_dir: str, dpi: int = 200
    ) -> Dict[str, str]:
        """Exporta cada uno de los 6 paneles por separado en alta resolución para auditoría."""
        os.makedirs(panels_dir, exist_ok=True)
        ds = run_result.telemetry["metadata"]["dataset"]
        header_tag = f"{ds['ticker']} · Ventana {ds['active_window_candles']} velas ({ds['last_candle_date']})"

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
            fig.suptitle(f"DETALLE TÉCNICO  |  {header_tag}", color="#94a3b8", fontsize=9.5, x=0.08, ha="left")
            out_file = os.path.abspath(os.path.join(panels_dir, filename))
            fig.savefig(out_file, dpi=dpi, facecolor=cls.BG_FIG)
            plt.close(fig)
            exported[filename] = out_file

        return exported
