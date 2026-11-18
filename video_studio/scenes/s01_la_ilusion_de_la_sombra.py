#!/usr/bin/env python3
"""
S01 — La Ilusión de la Sombra 1D (Cold Open)
- Uses self.renderer.time (zero audio drift).
- Includes subtle diagonal dashed trend chords (start -> +25% / +29%) reinforcing the 1D illusion.
- Morphs 1D shadows into 2D phase planes at cue['giramos'], revealing opposite spins (Cyan CCW vs Coral CW).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from manim import (
    Axes,
    Create,
    DashedLine,
    DOWN,
    Dot,
    FadeIn,
    FadeOut,
    LEFT,
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

STUDIO_DIR = Path(__file__).resolve().parent.parent
if str(STUDIO_DIR) not in sys.path:
    sys.path.insert(0, str(STUDIO_DIR))

from components.theme import (  # noqa: E402
    BG_DARK,
    BORDER_SUBTLE,
    CORAL,
    CYAN,
    FONT_UI,
    SLATE,
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


class S01IlusionSombra(Scene):
    def construct(self) -> None:
        self.camera.background_color = BG_DARK
        spec = load_scene_timing("s01_la_ilusion_de_la_sombra")
        anim01 = load_real_windows()["anim_01"]
        spy = anim01["spy"]
        btc = anim01["btc"]

        t_25 = spec.cue("veinticinco", 3.9)
        t_29 = spec.cue("veintinueve", 6.8)
        t_obv = spec.cue("acumulado", 10.0)
        t_turn = spec.cue("giramos", 18.0)
        t_opp = spec.cue("opuestos", 23.5)

        header = build_header("Acto 1 · KineTopus", spec.on_screen["headline"])

        left_card = build_glass_card(6.15, 5.24, center=(-3.30, STAGE_CENTER_Y, 0.0))
        right_card = build_glass_card(6.15, 5.24, center=(3.30, STAGE_CENTER_Y, 0.0))

        def make_title_pair(card, name_txt: str, sub_txt: str) -> VGroup:
            enforce_six_words(name_txt)
            enforce_six_words(sub_txt)
            t1 = Text(name_txt, font=FONT_UI, font_size=24, color=TXT_MAIN, weight="BOLD")
            t2 = Text(sub_txt, font=FONT_UI, font_size=14, color=TXT_MUTED)
            t1.next_to(card.get_top(), DOWN, buff=0.22)
            t2.next_to(t1, DOWN, buff=0.06)
            return VGroup(t1, t2)

        spy_hdr = make_title_pair(left_card, "S&P 500", "2023-03  →  2024-01")
        btc_hdr = make_title_pair(right_card, "Bitcoin", "2024-07  →  2025-03")

        def build_1d_curves(card, asset: dict, gain_txt: str):
            close = np.asarray(asset["close"], dtype=float)
            pct = (close / close[0] - 1.0) * 100.0
            obv = np.asarray(asset["obv_minmax"], dtype=float)
            xs = np.linspace(0.0, 1.0, len(pct))

            ax_p = Axes(
                x_range=[0, 1, 0.5],
                y_range=[float(pct.min() - 3), float(pct.max() + 4), 10],
                x_length=5.1,
                y_length=1.65,
                axis_config={"color": BORDER_SUBTLE, "stroke_width": 1.2, "include_tip": False, "include_ticks": False},
            ).move_to(card.get_center() + UP * 0.58)

            ax_o = Axes(
                x_range=[0, 1, 0.5],
                y_range=[-0.08, 1.08, 0.5],
                x_length=5.1,
                y_length=1.25,
                axis_config={"color": BORDER_SUBTLE, "stroke_width": 1.2, "include_tip": False, "include_ticks": False},
            ).move_to(card.get_center() + DOWN * 1.18)

            pts_p = [ax_p.c2p(float(xs[i]), float(pct[i])) for i in range(len(xs))]
            pts_o = [ax_o.c2p(float(xs[i]), float(obv[i])) for i in range(len(xs))]

            curve_p = build_sharp_polyline(pts_p, TXT_MAIN, width=2.8, opacity=0.95)
            curve_o = build_sharp_polyline(pts_o, SLATE, width=2.4, opacity=0.90)

            # Subtle diagonal dashed trend chord from start (0%) to end (+25% / +29%)
            chord_line = DashedLine(
                pts_p[0],
                pts_p[-1],
                dash_length=0.09,
                color=TXT_SUB,
                stroke_width=1.7,
                stroke_opacity=0.62,
            )
            chord_dots = VGroup(
                Dot(pts_p[0], radius=0.045, color=TXT_SUB),
                Dot(pts_p[-1], radius=0.052, color=TXT_MAIN),
            )
            chord_grp = VGroup(chord_line, chord_dots)

            lbl_p = build_semantic_pill(gain_txt, TXT_SUB, font_size=14)
            lbl_p.move_to(ax_p.get_corner(UP + LEFT) + RIGHT * 0.92 + DOWN * 0.14)

            enforce_six_words("OBV acumulado · Casi idéntico")
            lbl_o = Text("OBV acumulado · Casi idéntico", font=FONT_UI, font_size=14, color=SLATE, weight="BOLD")
            lbl_o.next_to(ax_o, UP, buff=0.08).align_to(ax_o, LEFT)

            return ax_p, ax_o, curve_p, curve_o, chord_grp, lbl_p, lbl_o

        spy_axp, spy_axo, spy_cp, spy_co, spy_chord, spy_gain, spy_obvlbl = build_1d_curves(left_card, spy, "Precio · +25%")
        btc_axp, btc_axo, btc_cp, btc_co, btc_chord, btc_gain, btc_obvlbl = build_1d_curves(right_card, btc, "Precio · +29%")

        def build_2d_stage(card, asset: dict, color: str, pill_txt: str):
            vx = np.asarray(asset["vz"], dtype=float)
            ry = np.asarray(asset["r_smooth_pct"], dtype=float)
            px = max(0.08, (vx.max() - vx.min()) * 0.14)
            py = max(0.06, (ry.max() - ry.min()) * 0.14)
            xmin, xmax = float(vx.min() - px), float(vx.max() + px)
            ymin, ymax = float(ry.min() - py), float(ry.max() + py)

            ax2 = Axes(
                x_range=[xmin, xmax, (xmax - xmin) / 4],
                y_range=[ymin, ymax, (ymax - ymin) / 4],
                x_length=5.0,
                y_length=3.15,
                axis_config={"color": BORDER_SUBTLE, "stroke_width": 1.3, "include_tip": False, "include_ticks": False},
            ).move_to(card.get_center() + DOWN * 0.08)

            cx = float(vx.mean())
            cy = 0.0 if ymin <= 0.0 <= ymax else float(ry.mean())
            ch_h = DashedLine(ax2.c2p(xmin, cy), ax2.c2p(xmax, cy), dash_length=0.07, color=BORDER_SUBTLE, stroke_width=1.1)
            ch_v = DashedLine(ax2.c2p(cx, ymin), ax2.c2p(cx, ymax), dash_length=0.07, color=BORDER_SUBTLE, stroke_width=1.1)

            enforce_six_words("Volumen Vz  ×  Velocidad r %")
            ax_lbl = Text("Volumen Vz  ×  Velocidad r %", font=FONT_UI, font_size=13, color=TXT_MUTED)
            ax_lbl.next_to(ax2, DOWN, buff=0.10)

            pts2 = [ax2.c2p(float(vx[i]), float(ry[i])) for i in range(len(vx))]
            glow_full = build_glow_curve(pts2, color, core_width=3.0)
            arrows = build_orbit_arrows(pts2, color, fracs=(0.25, 0.55, 0.82))
            head = build_comet_head(pts2[-1], color)

            pill = build_semantic_pill(pill_txt, color, font_size=16)
            pill.next_to(card.get_bottom(), UP, buff=0.18)

            return VGroup(ax2, ch_h, ch_v, ax_lbl), pts2, glow_full, arrows, head, pill

        spy_2d_grid, spy_pts2, spy_glow, spy_arr, spy_head, spy_pill = build_2d_stage(
            left_card, spy, CYAN, spec.on_screen["left_badge"]
        )
        btc_2d_grid, btc_pts2, btc_glow, btc_arr, btc_head, btc_pill = build_2d_stage(
            right_card, btc, CORAL, spec.on_screen["right_badge"]
        )

        # --- Audio-First Timeline driven by self.renderer.time ---
        self.play(
            FadeIn(header, shift=DOWN * 0.15),
            FadeIn(left_card),
            FadeIn(right_card),
            FadeIn(spy_hdr),
            FadeIn(btc_hdr),
            FadeIn(spy_axp),
            FadeIn(btc_axp),
            run_time=0.85,
        )

        wait_until(self, t_25 - 0.90)
        self.play(
            Create(spy_cp),
            FadeIn(spy_chord),
            FadeIn(spy_gain, scale=0.92),
            run_time=1.35,
            rate_func=smooth,
        )

        wait_until(self, t_29 - 0.80)
        self.play(
            Create(btc_cp),
            FadeIn(btc_chord),
            FadeIn(btc_gain, scale=0.92),
            run_time=1.35,
            rate_func=smooth,
        )

        wait_until(self, t_obv - 0.40)
        self.play(
            FadeIn(spy_axo),
            FadeIn(btc_axo),
            FadeIn(spy_obvlbl),
            FadeIn(btc_obvlbl),
            Create(spy_co),
            Create(btc_co),
            run_time=1.80,
            rate_func=smooth,
        )

        wait_until(self, t_turn)

        spy_morph_target = spy_glow[2].copy()
        btc_morph_target = btc_glow[2].copy()
        self.play(
            FadeOut(VGroup(spy_axp, spy_axo, spy_chord, spy_gain, spy_obvlbl, spy_co)),
            FadeOut(VGroup(btc_axp, btc_axo, btc_chord, btc_gain, btc_obvlbl, btc_co)),
            FadeIn(spy_2d_grid),
            FadeIn(btc_2d_grid),
            ReplacementTransform(spy_cp, spy_morph_target),
            ReplacementTransform(btc_cp, btc_morph_target),
            run_time=1.70,
            rate_func=smooth,
        )
        self.remove(spy_morph_target, btc_morph_target)

        prog = ValueTracker(0.22)

        def _dyn_spy():
            n = max(4, int(prog.get_value() * (len(spy_pts2) - 1)) + 1)
            sub = spy_pts2[:n]
            return VGroup(build_glow_curve(sub, CYAN, 3.0), build_comet_head(sub[-1], CYAN))

        def _dyn_btc():
            n = max(4, int(prog.get_value() * (len(btc_pts2) - 1)) + 1)
            sub = btc_pts2[:n]
            return VGroup(build_glow_curve(sub, CORAL, 3.0), build_comet_head(sub[-1], CORAL))

        dyn_s = always_redraw(_dyn_spy)
        dyn_b = always_redraw(_dyn_btc)
        self.add(dyn_s, dyn_b)

        d_sweep1 = remaining_until(self, t_opp, floor=0.60)
        self.play(prog.animate.set_value(0.84), run_time=d_sweep1, rate_func=linear)

        self.play(
            prog.animate.set_value(1.0),
            FadeIn(spy_arr),
            FadeIn(btc_arr),
            FadeIn(spy_pill, shift=UP * 0.12),
            FadeIn(btc_pill, shift=UP * 0.12),
            run_time=1.10,
            rate_func=smooth,
        )

        self.remove(dyn_s, dyn_b)
        self.add(spy_glow, spy_arr, spy_head, btc_glow, btc_arr, btc_head)

        pad_scene_to_exact_audio(self, spec.duration_s)
