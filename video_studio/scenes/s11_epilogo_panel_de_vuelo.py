#!/usr/bin/env python3
"""
S11 — Epílogo: Instrumento de Navegación y la Segunda Dimensión (30.1333 s)
  Beat 1 (0-18s): Dual flight-panel navigation rules (Hold serene CCW ellipse vs Cut risk 50% on red CW opening)
                  + subtle legal disclaimer strictly above the 14% bottom subtitle safe zone (y >= -2.84).
  Beat 2 (18-27s): Dissolves into a single luminous microscope lens where a flat 1D shadow unfolds majestically into 2D.
  Beat 3 (27-30.13s): Smooth FadeOut to clean dark obsidian canvas (#090D16) leaving uncluttered air for YouTube End Screen.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from manim import (
    Axes,
    Circle,
    DOWN,
    FadeIn,
    FadeOut,
    LEFT,
    RIGHT,
    ReplacementTransform,
    Scene,
    Text,
    UP,
    VGroup,
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
    CORAL,
    CYAN,
    EMERALD,
    FONT_UI,
    SAFE_BOTTOM_Y,
    SLATE,
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
    wait_until,
)


class S11EpilogoPanelVuelo(Scene):
    def construct(self) -> None:
        self.camera.background_color = BG_DARK
        spec = load_scene_timing("s11_epilogo_panel_de_vuelo")
        guide = load_real_windows()["guide_ilus_00"]

        t_nav = spec.cue("navegación", 4.75)
        t_hold = spec.cue("sostener", 7.34)
        t_half = spec.cue("mitad", 13.44)
        t_mic = spec.cue("microscopio", 19.39)
        t_dim = spec.cue("dimensión", 22.35)

        header_1 = build_header("Acto 6 · Valor real", "Un instrumento de navegación")
        header_2 = build_header("KineTopus · Microscopio físico", spec.on_screen["headline"])
        header_2[1].set_color(AMBER)

        # Subtle legal disclaimer sitting cleanly ABOVE SAFE_BOTTOM_Y (-2.84) at y = -2.68
        disclaimer_txt = Text(
            spec.on_screen["disclaimer"],
            font=FONT_UI,
            font_size=12,
            color=TXT_MUTED,
        )
        disclaimer_txt.move_to([0.0, SAFE_BOTTOM_Y + 0.18, 0.0])

        # =====================================================================
        # BEAT 1: Two Flight-Panel Navigation Rules (y in [-2.35, +2.35])
        # =====================================================================
        left_card = build_glass_card(5.95, 4.45, center=(-3.25, 0.08, 0.0), border_color=EMERALD, fill_color=BG_CARD_ALT)
        right_card = build_glass_card(5.95, 4.45, center=(3.25, 0.08, 0.0), border_color=CORAL, fill_color=BG_CARD_ALT)

        def build_rule_card(card, badge_txt: str, action_txt: str, desc_txt: str, is_ellipse: bool, col: str):
            enforce_six_words(action_txt)
            enforce_six_words(desc_txt)
            pill = build_semantic_pill(badge_txt, col, font_size=15).next_to(card.get_top(), DOWN, buff=0.26)

            # Clean geometric icon in the middle of the card
            if is_ellipse:
                # Counter-clockwise (dtheta > 0) closed ellipse
                th = np.linspace(0.0, 2.0 * np.pi, 80)
                pts = [card.get_center() + UP * 0.18 + np.array([1.22 * np.cos(a), 0.70 * np.sin(a), 0.0]) for a in th]
            else:
                # Genuine clockwise (dphi < 0, Lz < 0 everywhere) outward-opening spiral escape
                u = np.linspace(0.0, 1.0, 75)
                phi = 1.32 * np.pi - u * (1.54 * np.pi)
                rad = 0.22 + 1.02 * (u ** 1.30)
                pts = [
                    card.get_center() + UP * 0.14 + np.array([float(1.08 * r * np.cos(p)), float(0.72 * r * np.sin(p)), 0.0])
                    for r, p in zip(rad, phi)
                ]

            glow = build_glow_curve(pts, col, core_width=2.9)
            arr = build_orbit_arrows(pts, col, fracs=(0.30, 0.72))
            head = build_comet_head(pts[-1], col, radius=0.062)

            act = Text(action_txt, font=FONT_UI, font_size=22, color=TXT_MAIN, weight="BOLD")
            act.move_to(card.get_bottom() + UP * 0.86)
            dsc = Text(desc_txt, font=FONT_UI, font_size=14, color=TXT_SUB)
            dsc.next_to(act, DOWN, buff=0.10)

            return VGroup(pill, glow, arr, head, act, dsc)

        hold_body = build_rule_card(
            left_card,
            spec.on_screen["left_rule"],
            "Sostener con serenidad",
            "Manos pacientes absorben caídas",
            True,
            EMERALD,
        )
        cut_body = build_rule_card(
            right_card,
            spec.on_screen["right_rule"],
            "Reducir exposición al 50%",
            "Proteger capital sin ir a ciegas",
            False,
            CORAL,
        )

        self.play(
            FadeIn(header_1, shift=DOWN * 0.15),
            FadeIn(left_card),
            FadeIn(right_card),
            FadeIn(disclaimer_txt),
            run_time=1.05,
        )

        wait_until(self, t_hold - 0.35)
        self.play(FadeIn(hold_body, shift=UP * 0.12), run_time=1.05, rate_func=smooth)

        wait_until(self, t_half - 0.55)
        self.play(FadeIn(cut_body, shift=UP * 0.12), run_time=1.05, rate_func=smooth)

        # =====================================================================
        # BEAT 2: Microscope Aperture -> 1D Shadow Unfolds Majestically into 2D
        # =====================================================================
        vx = np.asarray(guide["vz"], dtype=float)
        ry = np.asarray(guide["r_smooth_pct"], dtype=float)
        lens_center = [0.0, 0.44, 0.0]
        ax_f = Axes(
            x_range=[float(vx.min() - 0.08), float(vx.max() + 0.08), 0.2],
            y_range=[float(ry.min() - 0.08), float(ry.max() + 0.08), 0.2],
            x_length=3.65,
            y_length=2.55,
            axis_config={"stroke_opacity": 0.0, "include_tip": False, "include_ticks": False},
        ).move_to(lens_center)

        xs_flat = np.linspace(float(vx.min()), float(vx.max()), len(ry))
        pts_1d = [ax_f.c2p(float(xs_flat[i]), 0.0) for i in range(len(ry))]
        pts_2d = [ax_f.c2p(float(vx[i]), float(ry[i])) for i in range(len(ry))]

        lens_outer = Circle(radius=2.08, stroke_color=BORDER_SUBTLE, stroke_width=2.2, fill_color="#0C1322", fill_opacity=0.92).move_to(lens_center)
        lens_inner = Circle(radius=1.93, stroke_color=CYAN, stroke_width=1.2, stroke_opacity=0.45).move_to(lens_center)
        shadow_1d = build_sharp_polyline(pts_1d, SLATE, width=3.0, opacity=0.90)
        orbit_2d = build_glow_curve(pts_2d, CYAN, core_width=3.2)
        orbit_arr = build_orbit_arrows(pts_2d, CYAN, fracs=(0.22, 0.55, 0.84))
        orbit_head = build_comet_head(pts_2d[-1], AMBER, radius=0.075)

        closing_pill = build_semantic_pill(spec.on_screen["closing"], CYAN, font_size=16)
        closing_pill.move_to([0.0, -2.14, 0.0])

        wait_until(self, t_mic - 0.45)
        self.play(
            ReplacementTransform(header_1, header_2),
            FadeOut(VGroup(left_card, hold_body)),
            FadeOut(VGroup(right_card, cut_body)),
            FadeIn(lens_outer, scale=0.90),
            FadeIn(lens_inner, scale=0.90),
            FadeIn(shadow_1d),
            run_time=1.35,
            rate_func=smooth,
        )

        # Unfold flat 1D shadow into luminous 2D phase orbit right on cue['dimensión']!
        wait_until(self, t_dim - 0.35)
        core_copy = orbit_2d[2].copy()
        self.play(
            ReplacementTransform(shadow_1d, core_copy),
            FadeIn(orbit_2d[0]),
            FadeIn(orbit_2d[1]),
            FadeIn(orbit_arr),
            FadeIn(orbit_head),
            FadeIn(closing_pill, shift=UP * 0.10),
            run_time=1.85,
            rate_func=smooth,
        )
        self.remove(core_copy)
        self.add(orbit_2d[2])

        # =====================================================================
        # BEAT 3: Gentle FadeOut after speech ends, leaving clean dark canvas for YouTube End Screen
        # =====================================================================
        wait_until(self, spec.speech_s + 0.35)
        everything = VGroup(header_2, lens_outer, lens_inner, orbit_2d, orbit_arr, orbit_head, closing_pill, disclaimer_txt)
        self.play(FadeOut(everything), run_time=1.35, rate_func=smooth)

        pad_scene_to_exact_audio(self, spec.duration_s)
