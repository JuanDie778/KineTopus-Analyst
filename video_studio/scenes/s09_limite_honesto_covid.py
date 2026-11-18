#!/usr/bin/env python3
"""
S09 — El Límite Honesto: S&P 500 antes del COVID (26.33 s)
3 clear visual beats driven by real_windows_substack.json#anim_03_ilus_03.spy_precovid:
  Beat 1 (0-12.5s): Real S&P 500 trajectory on 2020-02-12 closing into a calm Emerald ellipse (Re(λ) = +0.0063).
  Beat 2 (12.5-22s): Healthy internal order book -> '✓ Fracturas internas' scope box lights up.
  Beat 3 (22-26.3s): External shockwave arcs enter from outside the frame on cue['virus'] -> '✕ Choques exógenos'.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from manim import (
    Arc,
    Axes,
    DashedLine,
    DOWN,
    FadeIn,
    LEFT,
    PI,
    RIGHT,
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
    BG_CARD_ALT,
    BG_DARK,
    BORDER_SUBTLE,
    EMERALD,
    FONT_MONO,
    FONT_UI,
    STAGE_CENTER_Y,
    TXT_MAIN,
    TXT_MUTED,
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


class S09LimiteHonestoCovid(Scene):
    def construct(self) -> None:
        self.camera.background_color = BG_DARK
        spec = load_scene_timing("s09_limite_honesto_covid")
        cov = load_real_windows()["anim_03_ilus_03"]["spy_precovid"]

        t_feb = spec.cue("febrero", 7.4)
        t_ser = spec.cue("serena", 13.1)
        t_vir = spec.cue("virus", 23.8)

        vx = np.asarray(cov["vz"], dtype=float)
        ry = np.asarray(cov["r_smooth_pct"], dtype=float)

        header = build_header("Acto 4 · Rigor científico", spec.on_screen["headline"])

        left_card = build_glass_card(7.55, 5.24, center=(-2.52, STAGE_CENTER_Y, 0.0))
        right_card = build_glass_card(4.80, 5.24, center=(4.02, STAGE_CENTER_Y, 0.0))

        enforce_six_words("S&P 500 · 12 febrero 2020")
        l_title = Text("S&P 500 · 12 febrero 2020", font=FONT_UI, font_size=20, color=TXT_MAIN, weight="BOLD")
        l_title.move_to([float(left_card.get_left()[0]) + 1.85, float(left_card.get_top()[1]) - 0.30, 0.0])

        re_tag = Text("Re(λ) = +0.0063", font=FONT_MONO, font_size=14, color=EMERALD, weight="BOLD")
        re_tag.move_to([float(left_card.get_right()[0]) - 1.15, float(left_card.get_top()[1]) - 0.30, 0.0])

        px = max(0.03, (vx.max() - vx.min()) * 0.22)
        py = max(0.02, (ry.max() - ry.min()) * 0.24)
        xmin, xmax = float(vx.min() - px), float(vx.max() + px)
        ymin, ymax = float(ry.min() - py), float(ry.max() + py)

        ax = Axes(
            x_range=[xmin, xmax, (xmax - xmin) / 4],
            y_range=[ymin, ymax, (ymax - ymin) / 4],
            x_length=6.10,
            y_length=3.25,
            axis_config={"color": BORDER_SUBTLE, "stroke_width": 1.3, "include_tip": False, "include_ticks": False},
        ).move_to(left_card.get_center() + DOWN * 0.05)

        cx = 0.5 * (xmin + xmax)
        cy = 0.5 * (ymin + ymax)
        grid = VGroup(
            ax,
            DashedLine(ax.c2p(xmin, cy), ax.c2p(xmax, cy), dash_length=0.07, color=BORDER_SUBTLE, stroke_width=1.1),
            DashedLine(ax.c2p(cx, ymin), ax.c2p(cx, ymax), dash_length=0.07, color=BORDER_SUBTLE, stroke_width=1.1),
        )
        enforce_six_words("Volumen Vz  ×  Velocidad r %")
        ax_lbl = Text("Volumen Vz  ×  Velocidad r %", font=FONT_UI, font_size=13, color=TXT_MUTED).next_to(ax, DOWN, buff=0.10)

        pts = [ax.c2p(float(vx[i]), float(ry[i])) for i in range(len(vx))]
        glow = build_glow_curve(pts, EMERALD, core_width=3.0)
        arrs = build_orbit_arrows(pts, EMERALD, fracs=(0.35, 0.72))
        head = build_comet_head(pts[-1], EMERALD, radius=0.068)

        pill_calm = build_semantic_pill("Elipse verde · Orden interno sano", EMERALD, font_size=14)
        pill_calm.move_to(left_card.get_bottom() + UP * 0.28)

        # External shockwave arcs entering from upper-left corner of ax (strictly below title & clear of pill!)
        wave_origin = left_card.get_corner(UP + LEFT) + RIGHT * 0.48 + DOWN * 0.88
        shock_arcs = VGroup(
            *[
                Arc(radius=0.38 + i * 0.28, start_angle=-0.38 * PI, angle=0.32 * PI, arc_center=wave_origin, stroke_color=AMBER, stroke_width=2.6 - i * 0.4, stroke_opacity=0.88 - i * 0.20)
                for i in range(3)
            ]
        )
        shock_pill = build_semantic_pill("Impacto externo · COVID-19", AMBER, font_size=13)
        shock_pill.move_to(ax.get_top() + RIGHT * 0.55 + DOWN * 0.20)

        # Right Scope Card
        enforce_six_words("Alcance real del instrumento")
        r_hdr = Text("Alcance real del instrumento", font=FONT_UI, font_size=19, color=TXT_MAIN, weight="BOLD")
        r_hdr.next_to(right_card.get_top(), DOWN, buff=0.22)

        def make_scope_box(y_off: float, t1_s: str, t2_s: str, col: str) -> VGroup:
            enforce_six_words(t1_s)
            enforce_six_words(t2_s)
            box = build_glass_card(4.24, 1.90, center=right_card.get_center() + UP * y_off, border_color=col, fill_color=BG_CARD_ALT)
            t1 = Text(t1_s, font=FONT_UI, font_size=19, color=col, weight="BOLD")
            t2 = Text(t2_s, font=FONT_UI, font_size=14, color=TXT_MAIN)
            vg = VGroup(t1, t2).arrange(DOWN, buff=0.14).move_to(box.get_center())
            return VGroup(box, vg)

        box_in = make_scope_box(0.95, "✓ Fractura interna", "Lee fragilidad del capital", EMERALD)
        box_ex = make_scope_box(-1.25, "✕ Choque exógeno", "No adivina virus externos", AMBER)
        box_in.set_opacity(0.18)
        box_ex.set_opacity(0.18)

        # --- Audio-First 3-Beat Execution ---
        self.play(
            FadeIn(header, shift=DOWN * 0.15),
            FadeIn(left_card),
            FadeIn(right_card),
            FadeIn(l_title),
            FadeIn(r_hdr),
            FadeIn(box_in),
            FadeIn(box_ex),
            FadeIn(grid),
            FadeIn(ax_lbl),
            run_time=0.90,
        )

        wait_until(self, max(1.2, t_feb - 1.5))

        # Beat 1: Trace serene pre-COVID SPY ellipse
        prog = ValueTracker(0.05)

        def _dyn_cov():
            n = max(4, int(prog.get_value() * (len(pts) - 1)) + 1)
            sub = pts[:n]
            return VGroup(build_glow_curve(sub, EMERALD, 3.0), build_comet_head(sub[-1], EMERALD, 0.068))

        dc = always_redraw(_dyn_cov)
        self.add(dc)
        self.play(prog.animate.set_value(1.0), run_time=remaining_until(self, t_ser - 0.25, floor=2.2), rate_func=linear)
        self.remove(dc)
        self.add(glow, arrs, head)

        # Beat 2: Serene ellipse confirmed + Internal order-book scope box
        self.play(
            FadeIn(re_tag),
            FadeIn(pill_calm, shift=UP * 0.10),
            box_in.animate.set_opacity(1.0),
            run_time=1.20,
            rate_func=smooth,
        )

        # Beat 3: Exogenous virus shockwave + External limit box
        wait_until(self, t_vir - 1.6)
        self.play(
            FadeIn(shock_arcs, lag_ratio=0.22),
            FadeIn(shock_pill, scale=0.92),
            box_ex.animate.set_opacity(1.0),
            run_time=1.35,
            rate_func=smooth,
        )

        pad_scene_to_exact_audio(self, spec.duration_s)
