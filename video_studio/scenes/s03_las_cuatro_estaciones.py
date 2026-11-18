#!/usr/bin/env python3
"""
S03 — Las Cuatro Estaciones del Plano 2D
- Uses self.renderer.time (zero audio drift).
- Numbers stations in narrative order 1 -> 2 -> 3 -> 4 (instead of Roman numerals) + subtle 'Inicio' marker.
- Unfolds real S&P 500 trajectory (guide_ilus_00: 2023-03 -> 2024-01) from 1D into 2D Chronograph Phase Plane.
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
    LEFT,
    RIGHT,
    ReplacementTransform,
    Scene,
    Square,
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
    CORAL,
    CYAN,
    EMERALD,
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


class S03CuatroEstaciones(Scene):
    def construct(self) -> None:
        self.camera.background_color = BG_DARK
        spec = load_scene_timing("s03_las_cuatro_estaciones")
        guide = load_real_windows()["guide_ilus_00"]

        t_open = spec.cue("abre", 7.6)
        t_s1 = spec.cue("silencioso", 11.6)
        t_s2 = spec.cue("acelera", 14.0)
        t_s3 = spec.cue("retira", 16.4)
        t_s4 = spec.cue("descansa", 19.0)
        t_ccw = spec.cue("antihorario", 21.6)
        t_cw = spec.cue("sentido horario", 26.8)

        vx = np.asarray(guide["vz"], dtype=float)
        ry = np.asarray(guide["r_smooth_pct"], dtype=float)
        cx = float(guide["center_vz"])
        cy = float(guide["center_r_pct"])

        header = build_header("Espacio de fases 2D", spec.on_screen["headline"])

        chrono_card = build_glass_card(7.75, 5.24, center=(-2.42, STAGE_CENTER_Y, 0.0))
        compass_card = build_glass_card(4.60, 5.24, center=(4.12, STAGE_CENTER_Y, 0.0))

        enforce_six_words("S&P 500 · Órbita real (2023–2024)")
        c_title = Text("S&P 500 · Órbita real (2023–2024)", font=FONT_UI, font_size=20, color=TXT_MAIN, weight="BOLD")
        c_title.next_to(chrono_card.get_top(), DOWN, buff=0.20)

        px = max(0.08, (vx.max() - vx.min()) * 0.22)
        py = max(0.07, (ry.max() - ry.min()) * 0.24)
        xmin, xmax = float(vx.min() - px), float(vx.max() + px)
        ymin, ymax = float(ry.min() - py), float(ry.max() + py)

        ax2 = Axes(
            x_range=[xmin, xmax, (xmax - xmin) / 4],
            y_range=[ymin, ymax, (ymax - ymin) / 4],
            x_length=6.55,
            y_length=3.55,
            axis_config={"color": BORDER_SUBTLE, "stroke_width": 1.3, "include_tip": False, "include_ticks": False},
        ).move_to(chrono_card.get_center() + DOWN * 0.08)

        ch_h = DashedLine(ax2.c2p(xmin, cy), ax2.c2p(xmax, cy), dash_length=0.07, color=BORDER_SUBTLE, stroke_width=1.2)
        ch_v = DashedLine(ax2.c2p(cx, ymin), ax2.c2p(cx, ymax), dash_length=0.07, color=BORDER_SUBTLE, stroke_width=1.2)

        enforce_six_words("Volumen Vz  ×  Velocidad r %")
        ax_lbl = Text("Volumen Vz  ×  Velocidad r %", font=FONT_UI, font_size=13, color=TXT_MUTED)
        ax_lbl.next_to(ax2, DOWN, buff=0.14)

        xs_1d = np.linspace(xmin + 0.04, xmax - 0.04, len(ry))
        pts_1d = [ax2.c2p(float(xs_1d[i]), float(ry[i])) for i in range(len(ry))]
        pts_2d = [ax2.c2p(float(vx[i]), float(ry[i])) for i in range(len(ry))]

        line_1d = build_sharp_polyline(pts_1d, SLATE, width=2.8, opacity=0.95)
        pill_1d = build_semantic_pill("Vista plana · Contra el reloj", SLATE, font_size=14)
        pill_1d.move_to(chrono_card.get_bottom() + UP * 0.35)

        # Subtle 'Inicio' square marker at pts_2d[0]
        start_sq = Square(side_length=0.13, stroke_color=TXT_MAIN, stroke_width=1.8, fill_color=EMERALD, fill_opacity=0.95).move_to(pts_2d[0])
        enforce_six_words("Inicio")
        start_txt = Text("Inicio", font=FONT_UI, font_size=12, color=EMERALD, weight="BOLD").next_to(start_sq, RIGHT, buff=0.10)
        inicio_marker = VGroup(start_sq, start_txt)

        # 4 Stations numbered 1 -> 2 -> 3 -> 4 in narrative order
        q_texts = spec.on_screen["quadrants"]
        s1_pill = build_semantic_pill(q_texts[0], CYAN, font_size=13).move_to(ax2.get_corner(DOWN + RIGHT) + LEFT * 1.15 + UP * 0.26)
        s2_pill = build_semantic_pill(q_texts[1], EMERALD, font_size=13).move_to(ax2.get_corner(UP + RIGHT) + LEFT * 1.05 + DOWN * 0.26)
        s3_pill = build_semantic_pill(q_texts[2], AMBER, font_size=13).move_to(ax2.get_corner(UP + LEFT) + RIGHT * 0.98 + DOWN * 0.26)
        s4_pill = build_semantic_pill(q_texts[3], TXT_SUB, font_size=13).move_to(ax2.get_corner(DOWN + LEFT) + RIGHT * 1.12 + UP * 0.26)

        enforce_six_words("Lectura física del giro")
        r_hdr = Text("Lectura física del giro", font=FONT_UI, font_size=20, color=TXT_MAIN, weight="BOLD")
        r_hdr.next_to(compass_card.get_top(), DOWN, buff=0.20)

        def make_spin_box(center_pos, title_txt: str, sub_txt: str, accent: str) -> VGroup:
            enforce_six_words(title_txt)
            enforce_six_words(sub_txt)
            box = build_glass_card(4.10, 1.92, center=center_pos, border_color=accent, fill_color=BG_CARD_ALT)
            t1 = Text(title_txt, font=FONT_UI, font_size=20, color=accent, weight="BOLD")
            t2 = Text(sub_txt, font=FONT_UI, font_size=14, color=TXT_MAIN)
            vg = VGroup(t1, t2).arrange(DOWN, buff=0.14).move_to(box.get_center())
            return VGroup(box, vg)

        ccw_box = make_spin_box(
            compass_card.get_center() + UP * 0.96,
            "↺ Giro antihorario",
            "Capital paciente compra antes",
            CYAN,
        )
        cw_box = make_spin_box(
            compass_card.get_center() + DOWN * 1.24,
            "↻ Giro horario",
            "Precio salta · Multitud persigue",
            CORAL,
        )
        ccw_box.set_opacity(0.18)
        cw_box.set_opacity(0.18)

        # --- Timeline driven strictly by self.renderer.time ---
        self.play(
            FadeIn(header, shift=DOWN * 0.15),
            FadeIn(chrono_card),
            FadeIn(compass_card),
            FadeIn(c_title),
            FadeIn(r_hdr),
            FadeIn(ccw_box),
            FadeIn(cw_box),
            FadeIn(ax2),
            FadeIn(line_1d),
            FadeIn(pill_1d),
            run_time=0.90,
        )

        wait_until(self, t_open - 0.30)

        faint_2d = build_sharp_polyline(pts_2d, CYAN, width=1.6, opacity=0.28)
        self.play(
            pill_1d.animate.set_opacity(0.0),
            FadeIn(ch_h),
            FadeIn(ch_v),
            FadeIn(ax_lbl),
            FadeIn(inicio_marker, scale=0.90),
            ReplacementTransform(line_1d, faint_2d),
            run_time=1.35,
            rate_func=smooth,
        )

        prog = ValueTracker(0.03)

        def _dyn_orbit():
            n = max(4, int(prog.get_value() * (len(pts_2d) - 1)) + 1)
            sub = pts_2d[:n]
            return VGroup(build_glow_curve(sub, CYAN, 3.0), build_comet_head(sub[-1], AMBER))

        dyn_orb = always_redraw(_dyn_orbit)
        self.add(dyn_orb)

        # Station 1 (Bottom-Right)
        self.play(prog.animate.set_value(0.14), run_time=remaining_until(self, t_s1, floor=0.35), rate_func=linear)
        self.play(FadeIn(s1_pill, scale=0.92), prog.animate.set_value(0.22), run_time=0.60, rate_func=linear)

        # Station 2 (Top-Right)
        self.play(prog.animate.set_value(0.36), run_time=remaining_until(self, t_s2, floor=0.35), rate_func=linear)
        self.play(FadeIn(s2_pill, scale=0.92), prog.animate.set_value(0.45), run_time=0.60, rate_func=linear)

        # Station 3 (Top-Left)
        self.play(prog.animate.set_value(0.58), run_time=remaining_until(self, t_s3, floor=0.35), rate_func=linear)
        self.play(FadeIn(s3_pill, scale=0.92), prog.animate.set_value(0.67), run_time=0.60, rate_func=linear)

        # Station 4 (Bottom-Left)
        self.play(prog.animate.set_value(0.80), run_time=remaining_until(self, t_s4, floor=0.35), rate_func=linear)
        self.play(FadeIn(s4_pill, scale=0.92), prog.animate.set_value(0.90), run_time=0.60, rate_func=linear)

        # Complete loop right onto cue['antihorario']
        self.play(prog.animate.set_value(1.0), run_time=remaining_until(self, t_ccw, floor=0.30), rate_func=linear)

        full_glow = build_glow_curve(pts_2d, CYAN, 3.0)
        orb_arrows = build_orbit_arrows(pts_2d, CYAN, fracs=(0.18, 0.45, 0.75))
        end_head = build_comet_head(pts_2d[-1], AMBER)
        self.remove(dyn_orb, faint_2d)
        self.add(full_glow, orb_arrows, end_head)

        self.play(ccw_box.animate.set_opacity(1.0), run_time=0.80, rate_func=smooth)

        wait_until(self, t_cw)
        self.play(cw_box.animate.set_opacity(1.0), run_time=0.80, rate_func=smooth)

        pad_scene_to_exact_audio(self, spec.duration_s)
