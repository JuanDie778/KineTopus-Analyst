#!/usr/bin/env python3
"""
S07 — Invariancia Fractal 6x en Bitcoin (26.53 s)
3 clear visual beats driven by real_windows_substack.json#ilus_02 & b04_btc_1d_vs_4h_fractal_invariance.csv:
  Beat 1 (0-8s): Scientific skepticism on Bitcoin Daily (1D, 788 cuts) phase spiral.
  Beat 2 (8-14s): Optical 6x zoom ring (zero retuning) revealing Bitcoin 4-Hour (4H, 3,543 bars) spiral.
  Beat 3 (14-26.5s): Twin structural bars locking onto 47.34% (1D) vs 47.20% (4H) spiral focus.
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
    FadeIn,
    FadeOut,
    LEFT,
    RIGHT,
    RoundedRectangle,
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
    AMBER,
    BG_DARK,
    BORDER_SUBTLE,
    CORAL,
    EMERALD,
    FONT_MONO,
    FONT_UI,
    TXT_MAIN,
    TXT_MUTED,
    TXT_SUB,
    build_comet_head,
    build_glass_card,
    build_glow_curve,
    build_header,
    build_orbit_arrows,
    build_semantic_pill,
    enforce_six_words,
    load_real_windows,
    load_scene_timing,
    pad_scene_to_exact_audio,
    remaining_until,
    wait_until,
)


class S07FractalBitcoin6x(Scene):
    def construct(self) -> None:
        self.camera.background_color = BG_DARK
        spec = load_scene_timing("s07_fractal_bitcoin_6x")
        ilus02 = load_real_windows()["ilus_02"]
        b1d = ilus02["fractal_btc_1d"]
        b4h = ilus02["fractal_btc_4h"]

        t_6x = spec.cue("seis", 8.36)
        t_4h = spec.cue("cuatro", 10.24)
        t_lock = spec.cue("clavada", 13.95)
        t_mkt = spec.cue("pertenecía", 23.68)

        header = build_header("Acto 3 · Invariancia fractal", spec.on_screen["headline"])

        left_card = build_glass_card(6.15, 3.66, center=(-3.30, 0.65, 0.0))
        right_card = build_glass_card(6.15, 3.66, center=(3.30, 0.65, 0.0))
        bot_card = build_glass_card(12.75, 1.42, center=(0.0, -2.09, 0.0))

        def build_btc_panel(card, item: dict, title_txt: str, sub_txt: str, color: str):
            enforce_six_words(title_txt)
            enforce_six_words(sub_txt)
            vx = np.asarray(item["vz"], dtype=float)
            ry = np.asarray(item["r_smooth_pct"], dtype=float)
            px = max(0.06, (vx.max() - vx.min()) * 0.16)
            py = max(0.05, (ry.max() - ry.min()) * 0.18)
            xmin, xmax = float(vx.min() - px), float(vx.max() + px)
            ymin, ymax = float(ry.min() - py), float(ry.max() + py)

            ax = Axes(
                x_range=[xmin, xmax, (xmax - xmin) / 4],
                y_range=[ymin, ymax, (ymax - ymin) / 4],
                x_length=4.95,
                y_length=2.10,
                axis_config={"color": BORDER_SUBTLE, "stroke_width": 1.2, "include_tip": False, "include_ticks": False},
            ).move_to(card.get_center() + DOWN * 0.08)

            cy = 0.0 if ymin <= 0.0 <= ymax else 0.5 * (ymin + ymax)
            cx = 0.0 if xmin <= 0.0 <= xmax else 0.5 * (xmin + xmax)
            grid = VGroup(
                ax,
                DashedLine(ax.c2p(xmin, cy), ax.c2p(xmax, cy), dash_length=0.06, color=BORDER_SUBTLE, stroke_width=1.0),
                DashedLine(ax.c2p(cx, ymin), ax.c2p(cx, ymax), dash_length=0.06, color=BORDER_SUBTLE, stroke_width=1.0),
            )

            t1 = Text(title_txt, font=FONT_UI, font_size=20, color=TXT_MAIN, weight="BOLD")
            t1.move_to([float(card.get_left()[0]) + 1.55, float(card.get_top()[1]) - 0.28, 0.0])
            t2 = Text(sub_txt, font=FONT_UI, font_size=13, color=TXT_MUTED)
            t2.move_to([float(card.get_right()[0]) - 1.28, float(card.get_top()[1]) - 0.28, 0.0])

            pts = [ax.c2p(float(vx[i]), float(ry[i])) for i in range(len(vx))]
            glow = build_glow_curve(pts, color, core_width=2.8)
            arrs = build_orbit_arrows(pts, color, fracs=(0.35, 0.72))
            head = build_comet_head(pts[-1], color, radius=0.064)
            return VGroup(t1, t2), grid, pts, glow, arrs, head

        l_hdr, l_grid, l_pts, l_glow, l_arr, l_head = build_btc_panel(
            left_card, b1d, "Bitcoin Diario (1D)", "788 cortes · 1D", CORAL
        )
        r_hdr, r_grid, r_pts, r_glow, r_arr, r_head = build_btc_panel(
            right_card, b4h, "Bitcoin 4 Horas (4H)", "Zoom 6x · 3,543 velas", AMBER
        )

        pill_doubt = build_semantic_pill("¿Espejismo del cierre diario?", TXT_SUB, font_size=14).move_to(left_card.get_bottom() + UP * 0.27)
        pill_1d = build_semantic_pill(spec.on_screen["left_badge"], CORAL, font_size=14).move_to(left_card.get_bottom() + UP * 0.27)
        pill_4h = build_semantic_pill(spec.on_screen["right_badge"], AMBER, font_size=14).move_to(right_card.get_bottom() + UP * 0.27)

        # Optical Zoom Ring
        zoom_lens = VGroup(
            Circle(radius=0.52, stroke_color=AMBER, stroke_width=2.6, fill_color=AMBER, fill_opacity=0.10),
            Text("6x", font=FONT_MONO, font_size=20, color=AMBER, weight="BOLD"),
        ).move_to(left_card.get_center())

        # Bottom Twin Comparison Strip (47.34% vs 47.20%)
        enforce_six_words("Proporción de foco espiral")
        b_lbl = Text("Proporción de foco espiral", font=FONT_UI, font_size=16, color=TXT_MAIN, weight="BOLD")
        b_lbl.move_to([float(bot_card.get_left()[0]) + 1.85, float(bot_card.get_center()[1]) + 0.30, 0.0])

        seal_pill = build_semantic_pill("Geometría propia del mercado", EMERALD, font_size=13)
        seal_pill.move_to([float(bot_card.get_left()[0]) + 1.92, float(bot_card.get_center()[1]) - 0.30, 0.0])

        bx0 = -1.65
        w_max = 5.40  # represents 60%
        w_1d = w_max * (47.34 / 60.0)
        w_4h = w_max * (47.20 / 60.0)

        bar_1d = RoundedRectangle(corner_radius=0.07, width=w_1d, height=0.26, stroke_color=CORAL, stroke_width=1.3, fill_color=CORAL, fill_opacity=0.84)
        bar_1d.move_to([bx0 + w_1d / 2.0, float(bot_card.get_center()[1]) + 0.28, 0.0])
        txt_1d = Text("1D Diario · 47.34%", font=FONT_MONO, font_size=14, color=CORAL, weight="BOLD").next_to(bar_1d, RIGHT, buff=0.16)

        bar_4h = RoundedRectangle(corner_radius=0.07, width=w_4h, height=0.26, stroke_color=AMBER, stroke_width=1.3, fill_color=AMBER, fill_opacity=0.84)
        bar_4h.move_to([bx0 + w_4h / 2.0, float(bot_card.get_center()[1]) - 0.28, 0.0])
        txt_4h = Text("4H Zoom 6x · 47.20%", font=FONT_MONO, font_size=14, color=AMBER, weight="BOLD").next_to(bar_4h, RIGHT, buff=0.16)

        lock_line = DashedLine(
            [bx0 + w_1d, float(bot_card.get_top()[1]) - 0.16, 0.0],
            [bx0 + w_1d, float(bot_card.get_bottom()[1]) + 0.16, 0.0],
            dash_length=0.06,
            color=EMERALD,
            stroke_width=1.8,
        )

        # --- Audio-First 3-Beat Execution ---
        self.play(
            FadeIn(header, shift=DOWN * 0.15),
            FadeIn(left_card),
            FadeIn(right_card),
            FadeIn(bot_card),
            FadeIn(l_hdr),
            FadeIn(l_grid),
            run_time=0.85,
        )

        # Beat 1: Draw Bitcoin 1D orbit + doubt badge
        p1 = ValueTracker(0.04)

        def _dyn_1d():
            n = max(4, int(p1.get_value() * (len(l_pts) - 1)) + 1)
            sub = l_pts[:n]
            return VGroup(build_glow_curve(sub, CORAL, 2.8), build_comet_head(sub[-1], CORAL, 0.064))

        d1 = always_redraw(_dyn_1d)
        self.add(d1)
        self.play(p1.animate.set_value(1.0), FadeIn(pill_doubt, shift=UP * 0.08), run_time=3.20, rate_func=linear)
        self.remove(d1)
        self.add(l_glow, l_arr, l_head)

        # Beat 2: Optical 6x Lens glides to Right Card -> Draws Bitcoin 4H spiral
        wait_until(self, t_6x - 0.35)
        self.play(FadeIn(zoom_lens, scale=0.65), run_time=0.55, rate_func=smooth)
        self.play(
            zoom_lens.animate.move_to(right_card.get_center()),
            FadeIn(r_hdr),
            FadeIn(r_grid),
            run_time=1.15,
            rate_func=smooth,
        )
        self.play(FadeOut(zoom_lens, scale=1.35), run_time=0.45)

        p4 = ValueTracker(0.04)

        def _dyn_4h():
            n = max(4, int(p4.get_value() * (len(r_pts) - 1)) + 1)
            sub = r_pts[:n]
            return VGroup(build_glow_curve(sub, AMBER, 2.8), build_comet_head(sub[-1], AMBER, 0.064))

        d4 = always_redraw(_dyn_4h)
        self.add(d4)
        self.play(
            p4.animate.set_value(1.0),
            run_time=remaining_until(self, t_lock - 0.20, floor=1.8),
            rate_func=linear,
        )
        self.remove(d4)
        self.add(r_glow, r_arr, r_head)

        # Beat 3: Twin bars lock at 47.34% vs 47.20%
        self.play(
            FadeOut(pill_doubt),
            FadeIn(pill_1d, scale=0.92),
            FadeIn(pill_4h, scale=0.92),
            FadeIn(b_lbl),
            FadeIn(VGroup(bar_1d, txt_1d), shift=RIGHT * 0.20),
            FadeIn(VGroup(bar_4h, txt_4h), shift=RIGHT * 0.20),
            Create(lock_line),
            run_time=1.65,
            rate_func=smooth,
        )

        wait_until(self, t_mkt - 0.35)
        self.play(FadeIn(seal_pill, scale=0.92), run_time=0.95, rate_func=smooth)

        pad_scene_to_exact_audio(self, spec.duration_s)
