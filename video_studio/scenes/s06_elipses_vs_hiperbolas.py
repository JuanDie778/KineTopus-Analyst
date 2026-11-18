#!/usr/bin/env python3
"""
S06 — Elipses Cerradas vs. Escapes Hiperbólicos (29.67 s)
3 clear visual beats driven by real_windows_substack.json#ilus_02:
  Beat 1 (0-12s): Real 2D phase trajectories of SPY (2024-01-26) and Nvidia (2021-12-16).
  Beat 2 (12-24s): Fitzgibbon algebraic conic fits (strictly clipped inside Axes via clip_conic_segments_to_box).
  Beat 3 (24-29.7s): Universal Law across 25/25 markets (Ellipses 3.0x more stable than Hyperbolas).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from manim import (
    Axes,
    Create,
    DashedLine,
    DashedVMobject,
    DOWN,
    FadeIn,
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
    build_sharp_polyline,
    clip_conic_segments_to_box,
    enforce_six_words,
    load_real_windows,
    load_scene_timing,
    pad_scene_to_exact_audio,
    remaining_until,
    wait_until,
)


class S06ElipsesVsHiperbolas(Scene):
    def construct(self) -> None:
        self.camera.background_color = BG_DARK
        spec = load_scene_timing("s06_elipses_vs_hiperbolas")
        ilus02 = load_real_windows()["ilus_02"]
        el_data = ilus02["ellipse_spy"]
        hy_data = ilus02["hyperbola_nvda"]

        t_el = spec.cue("elipses", 12.7)
        t_hy = spec.cue("hipérbolas", 17.7)
        t_nv = spec.cue("Envidia", 20.3)
        t_3x = spec.cue("tres", 26.7)

        header = build_header("Acto 3 · Geometría cónica", spec.on_screen["headline"])

        # Upper cards: y in [-1.18, +2.48]; Lower law banner: y in [-2.80, -1.36] (>= -2.84)
        left_card = build_glass_card(6.15, 3.66, center=(-3.30, 0.65, 0.0))
        right_card = build_glass_card(6.15, 3.66, center=(3.30, 0.65, 0.0))
        law_card = build_glass_card(12.75, 1.42, center=(0.0, -2.09, 0.0))

        def build_conic_panel(card, item: dict, title_txt: str, disc_txt: str, pill_txt: str, color: str):
            enforce_six_words(title_txt)
            enforce_six_words(disc_txt)
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
                y_length=2.12,
                axis_config={"color": BORDER_SUBTLE, "stroke_width": 1.2, "include_tip": False, "include_ticks": False},
            ).move_to(card.get_center() + DOWN * 0.08)

            cy = 0.0 if ymin <= 0.0 <= ymax else 0.5 * (ymin + ymax)
            cx = 0.0 if xmin <= 0.0 <= xmax else 0.5 * (xmin + xmax)
            grid = VGroup(
                ax,
                DashedLine(ax.c2p(xmin, cy), ax.c2p(xmax, cy), dash_length=0.06, color=BORDER_SUBTLE, stroke_width=1.0),
                DashedLine(ax.c2p(cx, ymin), ax.c2p(cx, ymax), dash_length=0.06, color=BORDER_SUBTLE, stroke_width=1.0),
            )

            hdr = Text(title_txt, font=FONT_UI, font_size=19, color=TXT_MAIN, weight="BOLD")
            hdr.move_to([float(card.get_left()[0]) + 1.55, float(card.get_top()[1]) - 0.30, 0.0])

            disc = Text(disc_txt, font=FONT_MONO, font_size=14, color=color, weight="BOLD")
            disc.move_to([float(card.get_right()[0]) - 1.05, float(card.get_top()[1]) - 0.30, 0.0])

            pts = [ax.c2p(float(vx[i]), float(ry[i])) for i in range(len(vx))]
            glow = build_glow_curve(pts, color, core_width=2.8)
            arrs = build_orbit_arrows(pts, color, fracs=(0.35, 0.75))
            head = build_comet_head(pts[-1], color, radius=0.064)

            # Strictly clip Fitzgibbon algebraic conic segments inside Axes interior!
            mx = 0.03 * (xmax - xmin)
            my = 0.03 * (ymax - ymin)
            clipped_segs = clip_conic_segments_to_box(
                item["conic_fit"]["segments"],
                xmin + mx,
                xmax - mx,
                ymin + my,
                ymax - my,
            )
            conic_mobs = VGroup()
            for cseg in clipped_segs:
                cpts = [ax.c2p(cx_i, cy_i) for (cx_i, cy_i) in cseg]
                raw_vm = build_sharp_polyline(cpts, "#FFFFFF", width=2.2, opacity=0.92)
                dashed_vm = DashedVMobject(raw_vm, num_dashes=max(10, int(len(cpts) * 0.45)))
                dashed_vm.set_stroke(color=color, width=2.1, opacity=0.90)
                conic_mobs.add(dashed_vm)

            pill = build_semantic_pill(pill_txt, color, font_size=14)
            pill.move_to(card.get_bottom() + UP * 0.27)

            return hdr, disc, grid, pts, glow, arrs, head, conic_mobs, pill

        l_hdr, l_disc, l_grid, l_pts, l_glow, l_arr, l_head, l_conic, l_pill = build_conic_panel(
            left_card,
            el_data,
            "S&P 500 · 2024-01",
            "b²−4ac = −0.57",
            spec.on_screen["left_badge"],
            EMERALD,
        )
        r_hdr, r_disc, r_grid, r_pts, r_glow, r_arr, r_head, r_conic, r_pill = build_conic_panel(
            right_card,
            hy_data,
            "Nvidia · 2021-12",
            "b²−4ac = +1.29",
            spec.on_screen["right_badge"],
            CORAL,
        )

        # Bottom Universal Law Card (25/25 markets: Ellipses 3.0x more stable)
        enforce_six_words("Ley universal · 25 de 25 mercados")
        law_title = Text("Ley universal · 25 de 25 mercados", font=FONT_UI, font_size=16, color=TXT_MAIN, weight="BOLD")
        law_title.move_to([float(law_card.get_left()[0]) + 2.15, float(law_card.get_center()[1]) + 0.34, 0.0])

        enforce_six_words("100% activos · Elipses 3x más estables")
        law_sub = Text("100% activos · Elipses 3x más estables", font=FONT_UI, font_size=13, color=EMERALD, weight="BOLD")
        law_sub.move_to([float(law_card.get_left()[0]) + 2.18, float(law_card.get_center()[1]) - 0.28, 0.0])

        bar_x0 = -1.35
        el_bar = RoundedRectangle(corner_radius=0.07, width=1.28, height=0.26, stroke_color=EMERALD, stroke_width=1.3, fill_color=EMERALD, fill_opacity=0.82)
        el_bar.move_to([bar_x0 + 1.28 / 2.0, float(law_card.get_center()[1]) + 0.28, 0.0])
        el_bar_lbl = Text("Elipses · +0.0032 d⁻¹", font=FONT_MONO, font_size=13, color=EMERALD, weight="BOLD").next_to(el_bar, RIGHT, buff=0.16)

        hy_bar = RoundedRectangle(corner_radius=0.07, width=3.84, height=0.26, stroke_color=CORAL, stroke_width=1.3, fill_color=CORAL, fill_opacity=0.82)
        hy_bar.move_to([bar_x0 + 3.84 / 2.0, float(law_card.get_center()[1]) - 0.28, 0.0])
        hy_bar_lbl = Text("Hipérbolas · +0.0096 d⁻¹ (3.0x)", font=FONT_MONO, font_size=13, color=CORAL, weight="BOLD").next_to(hy_bar, RIGHT, buff=0.16)

        law_content = VGroup(law_title, law_sub, el_bar, el_bar_lbl, hy_bar, hy_bar_lbl)

        # --- Audio-First 3-Beat Execution ---
        self.play(
            FadeIn(header, shift=DOWN * 0.15),
            FadeIn(left_card),
            FadeIn(right_card),
            FadeIn(law_card),
            FadeIn(l_hdr),
            FadeIn(r_hdr),
            FadeIn(l_grid),
            FadeIn(r_grid),
            run_time=0.90,
        )

        # Beat 1: Sweep both real trajectories simultaneously
        prog = ValueTracker(0.04)

        def _dyn_l():
            n = max(4, int(prog.get_value() * (len(l_pts) - 1)) + 1)
            sub = l_pts[:n]
            return VGroup(build_glow_curve(sub, EMERALD, 2.8), build_comet_head(sub[-1], EMERALD, 0.064))

        def _dyn_r():
            n = max(4, int(prog.get_value() * (len(r_pts) - 1)) + 1)
            sub = r_pts[:n]
            return VGroup(build_glow_curve(sub, CORAL, 2.8), build_comet_head(sub[-1], CORAL, 0.064))

        dl = always_redraw(_dyn_l)
        dr = always_redraw(_dyn_r)
        self.add(dl, dr)

        self.play(prog.animate.set_value(1.0), run_time=remaining_until(self, t_el - 0.35, floor=2.5), rate_func=linear)
        self.remove(dl, dr)
        self.add(l_glow, l_arr, l_head, r_glow, r_arr, r_head)

        # Beat 2A: Reveal Fitzgibbon closed ellipse on SPY
        wait_until(self, t_el - 0.15)
        self.play(
            Create(l_conic),
            FadeIn(l_disc),
            FadeIn(l_pill, shift=UP * 0.10),
            run_time=1.60,
            rate_func=smooth,
        )

        # Beat 2B: Reveal clipped Fitzgibbon hyperbola branches on Nvidia
        wait_until(self, t_hy - 0.15)
        self.play(
            Create(r_conic),
            FadeIn(r_disc),
            run_time=1.55,
            rate_func=smooth,
        )
        wait_until(self, t_nv - 0.15)
        self.play(FadeIn(r_pill, shift=UP * 0.10), run_time=0.85, rate_func=smooth)

        # Beat 3: Universal 25/25 Law (3x stability)
        wait_until(self, max(23.5, t_3x - 2.2))
        self.play(FadeIn(law_content, lag_ratio=0.14, shift=RIGHT * 0.14), run_time=1.65, rate_func=smooth)

        pad_scene_to_exact_audio(self, spec.duration_s)
