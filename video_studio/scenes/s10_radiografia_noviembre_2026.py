#!/usr/bin/env python3
"""
S10 — Instantánea Real de Noviembre de 2026 (28.20 s, Evergreen Framing)
Uses 3 spacious, highly legible architectural columns (instead of 6 tiny boxes) driven by real_windows_substack.json#ilus_04_now:
  Col 1 (Cyan): S&P 500 + Nasdaq-100 -> Calma orbital ↺ (Re(λ) +0.002 d⁻¹)
  Col 2 (Emerald): Oro (GOLD) -> Equilibrio amortiguado (Re(λ) −0.002 d⁻¹)
  Col 3 (Coral): Nvidia + Bitcoin -> Tensión interna activa (Re(λ) > +0.010 d⁻¹)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from manim import (
    Axes,
    DashedLine,
    DOWN,
    FadeIn,
    Scene,
    Text,
    UP,
    ValueTracker,
    VGroup,
    always_redraw,
    linear,
    smooth,
)

STUDIO_DIR = Path(__file__).resolve().parent.parent
if str(STUDIO_DIR) not in sys.path:
    sys.path.insert(0, str(STUDIO_DIR))

from components.theme import (  # noqa: E402
    BG_DARK,
    BORDER_SUBTLE,
    CORAL,
    CYAN,
    EMERALD,
    FONT_MONO,
    FONT_UI,
    STAGE_CENTER_Y,
    TXT_MAIN,
    TXT_MUTED,
    TXT_SUB,
    build_comet_head,
    build_glass_card,
    build_glow_curve,
    build_header,
    build_orbit_arrows,
    build_semantic_pill,
    build_sharp_polyline,
    enforce_six_words,
    load_real_windows,
    load_scene_timing,
    pad_scene_to_exact_audio,
    remaining_until,
    wait_until,
)


def _norm_pts(ax: Axes, vz_list: list[float], r_list: list[float]) -> tuple[list[np.ndarray], tuple[float, float]]:
    vx = np.asarray(vz_list, dtype=float)
    ry = np.asarray(r_list, dtype=float)
    px = max(0.05, (vx.max() - vx.min()) * 0.16)
    py = max(0.04, (ry.max() - ry.min()) * 0.18)
    xmin, xmax = min(float(vx.min() - px), -0.05), max(float(vx.max() + px), 0.05)
    ymin, ymax = min(float(ry.min() - py), -0.05), max(float(ry.max() + py), 0.05)
    sx = max(1e-6, xmax - xmin)
    sy = max(1e-6, ymax - ymin)
    nx = np.clip(-1.0 + 2.0 * (vx - xmin) / sx, -0.96, 0.96)
    ny = np.clip(-1.0 + 2.0 * (ry - ymin) / sy, -0.96, 0.96)
    ox = float(np.clip(-1.0 + 2.0 * (0.0 - xmin) / sx, -0.94, 0.94))
    oy = float(np.clip(-1.0 + 2.0 * (0.0 - ymin) / sy, -0.94, 0.94))
    return [ax.c2p(float(nx[i]), float(ny[i])) for i in range(len(nx))], (ox, oy)


class S10RadiografiaNov2026(Scene):
    def construct(self) -> None:
        self.camera.background_color = BG_DARK
        spec = load_scene_timing("s10_radiografia_noviembre_2026")
        now_data = load_real_windows()["ilus_04_now"]

        t_nov = spec.cue("noviembre", 4.33)
        t_calm = spec.cue("calma", 15.01)
        t_gold = spec.cue("oro", 17.75)
        t_tens = spec.cue("tensión", 23.55)

        header = build_header("Acto 5 · Mundo real", spec.on_screen["headline"])

        col_xs = [-4.32, 0.00, 4.32]
        cards = [build_glass_card(4.02, 5.24, center=(cx, STAGE_CENTER_Y, 0.0)) for cx in col_xs]

        def build_state_column(
            card,
            title_txt: str,
            sub_txt: str,
            metric_txt: str,
            pill_txt: str,
            main_vz: list[float],
            main_r: list[float],
            comp_vz: list[float] | None,
            comp_r: list[float] | None,
            color: str,
        ):
            enforce_six_words(title_txt)
            enforce_six_words(sub_txt)
            enforce_six_words(metric_txt)

            t1 = Text(title_txt, font=FONT_UI, font_size=20, color=TXT_MAIN, weight="BOLD")
            t1.next_to(card.get_top(), DOWN, buff=0.22)
            t2 = Text(sub_txt, font=FONT_UI, font_size=13, color=TXT_MUTED)
            t2.next_to(t1, DOWN, buff=0.06)

            ax = Axes(
                x_range=[-1, 1, 0.5],
                y_range=[-1, 1, 0.5],
                x_length=3.30,
                y_length=2.55,
                axis_config={"color": BORDER_SUBTLE, "stroke_width": 1.2, "include_tip": False, "include_ticks": False},
            ).move_to(card.get_center() + DOWN * 0.02)

            pts_main, (ox, oy) = _norm_pts(ax, main_vz, main_r)
            grid = VGroup(
                ax,
                DashedLine(ax.c2p(-1, oy), ax.c2p(1, oy), dash_length=0.06, color=BORDER_SUBTLE, stroke_width=1.0),
                DashedLine(ax.c2p(ox, -1), ax.c2p(ox, 1), dash_length=0.06, color=BORDER_SUBTLE, stroke_width=1.0),
            )

            comp_mob = VGroup()
            if comp_vz is not None and comp_r is not None:
                pts_comp, _ = _norm_pts(ax, comp_vz, comp_r)
                comp_mob = build_sharp_polyline(pts_comp, color, width=1.6, opacity=0.30)

            glow = build_glow_curve(pts_main, color, core_width=2.8)
            arrs = build_orbit_arrows(pts_main, color, fracs=(0.38, 0.76))
            head = build_comet_head(pts_main[-1], color, radius=0.064)

            met = Text(metric_txt, font=FONT_MONO, font_size=13, color=TXT_SUB)
            met.next_to(ax, DOWN, buff=0.14)

            pill = build_semantic_pill(pill_txt, color, font_size=14)
            pill.move_to(card.get_bottom() + UP * 0.28)

            shell = VGroup(t1, t2, grid)
            return card, shell, pts_main, comp_mob, glow, arrs, head, met, pill

        spy_d, qqq_d = now_data["SPY"], now_data["QQQ"]
        gold_d = now_data["GOLD"]
        btc_d, nvda_d = now_data["BTC"], now_data["NVDA"]

        c1_card, c1_shell, c1_pts, c1_comp, c1_glow, c1_arr, c1_head, c1_met, c1_pill = build_state_column(
            cards[0],
            "S&P 500 · Nasdaq",
            "Índices · Nov 2026",
            "Re(λ) +0.002 d⁻¹",
            "↺ Calma orbital",
            spy_d["active_vz"][::3],
            spy_d["active_r_pct"][::3],
            qqq_d["active_vz"][::3],
            qqq_d["active_r_pct"][::3],
            CYAN,
        )
        c2_card, c2_shell, c2_pts, c2_comp, c2_glow, c2_arr, c2_head, c2_met, c2_pill = build_state_column(
            cards[1],
            "Oro (GOLD)",
            "Refugio · 3,886 USD",
            "Re(λ) −0.002 d⁻¹",
            "Equilibrio amortiguado",
            gold_d["active_vz"][::3],
            gold_d["active_r_pct"][::3],
            None,
            None,
            EMERALD,
        )
        c3_card, c3_shell, c3_pts, c3_comp, c3_glow, c3_arr, c3_head, c3_met, c3_pill = build_state_column(
            cards[2],
            "Nvidia · Bitcoin",
            "Alerta · Re(λ) > +0.010",
            "BTC +0.027 · NVDA +0.013",
            "↻ Tensión activa",
            btc_d["active_vz"],
            btc_d["active_r_pct"],
            nvda_d["active_vz"][::3],
            nvda_d["active_r_pct"][::3],
            CORAL,
        )

        # --- Audio-First 4-Beat Execution (FadeIn preserves card fill_opacity=0.96!) ---
        self.play(
            FadeIn(header, shift=DOWN * 0.15),
            FadeIn(c1_card),
            FadeIn(c2_card),
            FadeIn(c3_card),
            run_time=1.00,
        )

        wait_until(self, max(1.2, t_nov - 0.5))
        self.play(
            FadeIn(c1_shell[0]),
            FadeIn(c1_shell[1]),
            FadeIn(c2_shell[0]),
            FadeIn(c2_shell[1]),
            FadeIn(c3_shell[0]),
            FadeIn(c3_shell[1]),
            run_time=1.05,
            rate_func=smooth,
        )

        # Column 1: SPY + QQQ Calma Orbital
        wait_until(self, max(8.8, t_calm - 3.6))
        p1 = ValueTracker(0.05)

        def _d1():
            n = max(4, int(p1.get_value() * (len(c1_pts) - 1)) + 1)
            sub = c1_pts[:n]
            return VGroup(build_glow_curve(sub, CYAN, 2.8), build_comet_head(sub[-1], CYAN, 0.064))

        dyn1 = always_redraw(_d1)
        self.play(FadeIn(c1_shell[2]), FadeIn(c1_comp), run_time=0.55)
        self.add(dyn1)
        self.play(p1.animate.set_value(1.0), run_time=remaining_until(self, t_calm - 0.15, floor=1.4), rate_func=linear)
        self.remove(dyn1)
        self.add(c1_glow, c1_arr, c1_head)
        self.play(FadeIn(c1_met), FadeIn(c1_pill, scale=0.92), run_time=0.75, rate_func=smooth)

        # Column 2: Gold Damped Equilibrium
        p2 = ValueTracker(0.05)

        def _d2():
            n = max(4, int(p2.get_value() * (len(c2_pts) - 1)) + 1)
            sub = c2_pts[:n]
            return VGroup(build_glow_curve(sub, EMERALD, 2.8), build_comet_head(sub[-1], EMERALD, 0.064))

        dyn2 = always_redraw(_d2)
        self.play(FadeIn(c2_shell[2]), run_time=0.45)
        self.add(dyn2)
        self.play(p2.animate.set_value(1.0), run_time=remaining_until(self, t_gold + 1.15, floor=1.5), rate_func=linear)
        self.remove(dyn2)
        self.add(c2_glow, c2_arr, c2_head)
        self.play(FadeIn(c2_met), FadeIn(c2_pill, scale=0.92), run_time=0.75, rate_func=smooth)

        # Column 3: Nvidia + Bitcoin Active Tension
        p3 = ValueTracker(0.05)

        def _d3():
            n = max(4, int(p3.get_value() * (len(c3_pts) - 1)) + 1)
            sub = c3_pts[:n]
            return VGroup(build_glow_curve(sub, CORAL, 2.8), build_comet_head(sub[-1], CORAL, 0.064))

        dyn3 = always_redraw(_d3)
        self.play(FadeIn(c3_shell[2]), FadeIn(c3_comp), run_time=0.50)
        self.add(dyn3)
        self.play(p3.animate.set_value(1.0), run_time=remaining_until(self, t_tens - 0.10, floor=1.4), rate_func=linear)
        self.remove(dyn3)
        self.add(c3_glow, c3_arr, c3_head)
        self.play(FadeIn(c3_met), FadeIn(c3_pill, scale=0.92), run_time=0.85, rate_func=smooth)

        pad_scene_to_exact_audio(self, spec.duration_s)
