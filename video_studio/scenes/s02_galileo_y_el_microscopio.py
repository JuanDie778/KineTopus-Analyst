#!/usr/bin/env python3
"""
S02 — De la Piedra de Galileo a KineTopus
- Uses self.renderer.time (zero audio drift).
- Includes a physical vertical drop guide (20 m -> 0 m) alongside the (t, h) plot so the stone drops vertically in real space.
- Marks 19.6 m/s (2 s) cleanly on the Emerald derivative line.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from manim import (
    Axes,
    Circle,
    Create,
    DashedLine,
    DOWN,
    Dot,
    FadeIn,
    LEFT,
    Line,
    RIGHT,
    ReplacementTransform,
    Scene,
    Text,
    UP,
    ValueTracker,
    VGroup,
    always_redraw,
    linear,
    smooth,
)
from scipy.interpolate import UnivariateSpline

STUDIO_DIR = Path(__file__).resolve().parent.parent
if str(STUDIO_DIR) not in sys.path:
    sys.path.insert(0, str(STUDIO_DIR))

from components.theme import (  # noqa: E402
    AMBER,
    BG_DARK,
    BORDER_SUBTLE,
    CORAL,
    CYAN,
    EMERALD,
    FONT_UI,
    STAGE_CENTER_Y,
    TXT_MAIN,
    TXT_MUTED,
    TXT_SUB,
    build_comet_head,
    build_glass_card,
    build_glow_curve,
    build_header,
    build_semantic_pill,
    build_sharp_polyline,
    enforce_six_words,
    load_scene_timing,
    pad_scene_to_exact_audio,
    remaining_until,
    wait_until,
)


class S02GalileoMicroscopio(Scene):
    def construct(self) -> None:
        self.camera.background_color = BG_DARK
        spec = load_scene_timing("s02_galileo_y_el_microscopio")

        t_stone = spec.cue("piedra", 3.5)
        t_teeth = spec.cue("dientes", 9.8)
        t_curve = spec.cue("curva", 12.8)
        t_nine = spec.cue("nueve", 18.2)
        t_kt = spec.cue("KineTopus", 22.8)

        rng = np.random.default_rng(42)
        n_pts = 48
        t = np.linspace(0.0, 2.0, n_pts)
        h_true = 20.0 - 0.5 * 9.8 * (t ** 2)
        sigma = 0.34
        h_obs = h_true + rng.normal(0.0, sigma, size=n_pts)

        v_raw = np.zeros(n_pts, dtype=float)
        v_raw[1:] = -(h_obs[1:] - h_obs[:-1]) / (t[1:] - t[:-1])

        sp = UnivariateSpline(t, h_obs, k=3, s=n_pts * (sigma ** 2) * 1.15)
        h_sp = sp(t)
        v_sp = -sp.derivative(1)(t)

        header = build_header("De Galileo al mercado", spec.on_screen["headline"])
        kt_header = build_header("KineTopus · Motor cinemático", "Un microscopio físico para mercados")
        kt_header[1].set_color(AMBER)

        left_card = build_glass_card(6.05, 5.24, center=(-3.35, STAGE_CENTER_Y, 0.0))
        right_card = build_glass_card(6.25, 5.24, center=(3.25, STAGE_CENTER_Y, 0.0))

        enforce_six_words("Caída vertical  +  Pulso (t, h)")
        l_title = Text("Caída vertical  +  Pulso (t, h)", font=FONT_UI, font_size=21, color=TXT_MAIN, weight="BOLD")
        l_title.next_to(left_card.get_top(), DOWN, buff=0.22)

        enforce_six_words("Velocidad deducida (m/s)")
        r_title = Text("Velocidad deducida (m/s)", font=FONT_UI, font_size=21, color=TXT_MAIN, weight="BOLD")
        r_title.next_to(right_card.get_top(), DOWN, buff=0.22)

        # Shift ax_h slightly right inside left_card to leave clean vertical drop shaft on the left
        ax_h = Axes(
            x_range=[0, 2.05, 0.5],
            y_range=[-1.5, 22.0, 5.0],
            x_length=3.95,
            y_length=3.15,
            axis_config={"color": BORDER_SUBTLE, "stroke_width": 1.3, "include_tip": False, "include_ticks": False},
        ).move_to(left_card.get_center() + RIGHT * 0.58 + DOWN * 0.05)

        # Physical vertical drop guide 20 m -> 0 m aligned to ax_h's exact y-coordinates
        shaft_x = float(left_card.get_left()[0]) + 0.78
        y_20m = float(ax_h.c2p(0, 20.0)[1])
        y_0m = float(ax_h.c2p(0, 0.0)[1])
        shaft_line = Line([shaft_x, y_20m, 0.0], [shaft_x, y_0m, 0.0], color=BORDER_SUBTLE, stroke_width=2.2)
        tick_top = Line([shaft_x - 0.14, y_20m, 0.0], [shaft_x + 0.14, y_20m, 0.0], color=TXT_SUB, stroke_width=2.0)
        tick_bot = Line([shaft_x - 0.18, y_0m, 0.0], [shaft_x + 0.18, y_0m, 0.0], color=TXT_SUB, stroke_width=2.4)
        lbl_20m = Text("20 m", font=FONT_UI, font_size=12, color=TXT_SUB, weight="BOLD").next_to(tick_top, UP, buff=0.10)
        lbl_0m = Text("0 m", font=FONT_UI, font_size=12, color=TXT_SUB, weight="BOLD").next_to(tick_bot, DOWN, buff=0.16)
        drop_guide = VGroup(shaft_line, tick_top, tick_bot, lbl_20m, lbl_0m)

        ax_v = Axes(
            x_range=[0, 2.08, 0.5],
            y_range=[-9.0, 34.0, 10.0],
            x_length=5.15,
            y_length=3.15,
            axis_config={"color": BORDER_SUBTLE, "stroke_width": 1.3, "include_tip": False, "include_ticks": False},
        ).move_to(right_card.get_center() + DOWN * 0.05)

        zero_v = DashedLine(ax_v.c2p(0, 0), ax_v.c2p(2.08, 0), dash_length=0.07, color=BORDER_SUBTLE, stroke_width=1.1)

        enforce_six_words("Tiempo (0 → 2 s)")
        lbl_xh = Text("Tiempo (0 → 2 s)", font=FONT_UI, font_size=13, color=TXT_MUTED).next_to(ax_h, DOWN, buff=0.10)
        enforce_six_words("Tiempo (0 → 2 s)")
        lbl_xv = Text("Tiempo (0 → 2 s)", font=FONT_UI, font_size=13, color=TXT_MUTED).next_to(ax_v, DOWN, buff=0.10)

        dots_obs = VGroup(
            *[
                Dot(ax_h.c2p(float(t[i]), float(h_obs[i])), radius=0.040, color="#E2E8F0").set_opacity(0.85)
                for i in range(n_pts)
            ]
        )

        pts_h_sp = [ax_h.c2p(float(t[i]), float(h_sp[i])) for i in range(n_pts)]
        pts_v_raw = [ax_v.c2p(float(t[i]), float(v_raw[i])) for i in range(1, n_pts)]
        pts_v_sp = [ax_v.c2p(float(t[i]), float(v_sp[i])) for i in range(n_pts)]

        spline_glow = build_glow_curve(pts_h_sp, CYAN, core_width=2.9)
        sawtooth_curve = build_sharp_polyline(pts_v_raw, CORAL, width=2.2, opacity=0.92)
        emerald_law = build_glow_curve(pts_v_sp, EMERALD, core_width=3.1)

        # Callout for exact 19.6 m/s at t = 2 s
        enforce_six_words("19.6 m/s (2 s)")
        end_v_pt = pts_v_sp[-1]
        v_end_lbl = build_semantic_pill("19.6 m/s (2 s)", EMERALD, font_size=13)
        v_end_lbl.move_to([end_v_pt[0] - 0.88, end_v_pt[1] + 0.42, 0.0])

        pill_noise = build_semantic_pill(spec.on_screen["left_badge"], CORAL, font_size=15)
        pill_noise.next_to(right_card.get_bottom(), UP, buff=0.18)

        pill_spline = build_semantic_pill("Spline causal · Sin ruido", CYAN, font_size=15)
        pill_spline.next_to(left_card.get_bottom(), UP, buff=0.18)

        pill_law = build_semantic_pill(spec.on_screen["right_badge"], EMERALD, font_size=16)
        pill_law.next_to(right_card.get_bottom(), UP, buff=0.18)

        # --- Timeline driven by self.renderer.time ---
        self.play(
            FadeIn(header, shift=DOWN * 0.15),
            FadeIn(left_card),
            FadeIn(right_card),
            FadeIn(l_title),
            FadeIn(r_title),
            FadeIn(drop_guide),
            FadeIn(ax_h),
            FadeIn(ax_v),
            FadeIn(zero_v),
            FadeIn(lbl_xh),
            FadeIn(lbl_xv),
            run_time=0.85,
        )

        wait_until(self, t_stone - 0.30)

        fall_prog = ValueTracker(0.0)

        def _falling_stone():
            idx = min(n_pts - 1, int(fall_prog.get_value() * (n_pts - 1)))
            y_phys = float(ax_h.c2p(0, float(h_true[idx]))[1])
            stone_pos = [shaft_x, y_phys, 0.0]
            plot_pos = ax_h.c2p(float(t[idx]), float(h_obs[idx]))
            proj_ray = DashedLine(stone_pos, plot_pos, dash_length=0.06, color=AMBER, stroke_width=1.2, stroke_opacity=0.55)
            shown = VGroup(*[dots_obs[j].copy() for j in range(idx + 1)])
            stone = Circle(radius=0.105, stroke_color=TXT_MAIN, stroke_width=2.0, fill_color=AMBER, fill_opacity=0.95).move_to(stone_pos)
            return VGroup(proj_ray, shown, stone)

        dyn_stone = always_redraw(_falling_stone)
        self.add(dyn_stone)

        d_fall = min(3.4, remaining_until(self, t_teeth - 0.25, floor=1.8))
        self.play(fall_prog.animate.set_value(1.0), run_time=d_fall, rate_func=linear)

        rested_stone = Circle(radius=0.105, stroke_color=TXT_MAIN, stroke_width=2.0, fill_color=AMBER, fill_opacity=0.85).move_to([shaft_x, y_0m, 0.0])
        self.remove(dyn_stone)
        self.add(dots_obs, rested_stone)

        wait_until(self, t_teeth)
        self.play(Create(sawtooth_curve), FadeIn(pill_noise, shift=UP * 0.10), run_time=1.60, rate_func=linear)

        wait_until(self, t_curve)
        self.play(
            dots_obs.animate.set_opacity(0.32),
            Create(spline_glow[2]),
            FadeIn(spline_glow[0]),
            FadeIn(spline_glow[1]),
            FadeIn(pill_spline, shift=UP * 0.10),
            run_time=1.80,
            rate_func=smooth,
        )

        wait_until(self, t_nine - 0.35)
        law_head = build_comet_head(end_v_pt, EMERALD)
        self.play(
            sawtooth_curve.animate.set_stroke(opacity=0.18),
            pill_noise.animate.set_opacity(0.0),
            Create(emerald_law[2]),
            FadeIn(emerald_law[0]),
            FadeIn(emerald_law[1]),
            FadeIn(law_head),
            FadeIn(v_end_lbl, scale=0.92),
            FadeIn(pill_law, shift=UP * 0.10),
            run_time=1.75,
            rate_func=smooth,
        )

        wait_until(self, t_kt)
        self.play(ReplacementTransform(header, kt_header), run_time=1.00, rate_func=smooth)

        pad_scene_to_exact_audio(self, spec.duration_s)
