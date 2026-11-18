#!/usr/bin/env python3
"""
S05 — La Mutación en Vivo de MicroStrategy (2018–2026) (37.40 s)
Polished Producer Edition:
  1. Silky 60 fps linear frame + envelope interpolation via SmoothOrbitInterpolator (zero stepping/jumps).
  2. Live top-right rolling % antihorario counters (mstr_ccw_smooth_pct & btc_ccw_smooth_pct) with dynamic color shift.
  3. Zero typography collisions in Beat 4 (CMF pill cleanly separated above 53%/27%/42% bars) and extra timeline vertical clearance.
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
    FadeOut,
    LEFT,
    Line,
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
    BG_CARD_ALT,
    BG_DARK,
    BORDER_SUBTLE,
    CORAL,
    CYAN,
    FONT_MONO,
    FONT_UI,
    SLATE,
    SmoothOrbitInterpolator,
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
    lerp_hex_color,
    load_real_windows,
    load_scene_timing,
    pad_scene_to_exact_audio,
    remaining_until,
)


def _pct_to_color(pct: float) -> str:
    if pct >= 50.0:
        return lerp_hex_color(AMBER, CYAN, min(1.0, (pct - 50.0) / 16.0))
    if pct >= 38.0:
        return lerp_hex_color(CORAL, AMBER, (pct - 38.0) / 12.0)
    return CORAL


class S05MutacionMicroStrategy(Scene):
    def construct(self) -> None:
        self.camera.background_color = BG_DARK
        spec = load_scene_timing("s05_mutacion_microstrategy")
        frames = load_real_windows()["anim_02"]["sync_frames"]
        n_fr = len(frames)  # 115 synchronized real windows (2018 -> 2026)

        mstr_interp = SmoothOrbitInterpolator(
            frames,
            "mstr_orbit_vz",
            "mstr_orbit_r_pct",
            scalar_keys=("mstr_ccw_smooth_pct",),
            alpha=0.22,
        )
        btc_interp = SmoothOrbitInterpolator(
            frames,
            "btc_orbit_vz",
            "btc_orbit_r_pct",
            scalar_keys=("btc_ccw_smooth_pct",),
            alpha=0.22,
        )

        t_53 = spec.cue("cincuenta", 8.9)
        t_aug = spec.cue("agosto", 12.1)
        t_42 = spec.cue("cuarenta", 29.2)
        t_blind = spec.cue("ciegos", 33.9)

        header = build_header("Acto 2 · Experimento vivo", spec.on_screen["headline"])

        # Upper cards: y in [-1.18, +2.48]; Lower timeline card: y in [-2.80, -1.36] (>= SAFE_BOTTOM_Y -2.84)
        mstr_card = build_glass_card(6.15, 3.66, center=(-3.30, 0.65, 0.0))
        btc_card = build_glass_card(6.15, 3.66, center=(3.30, 0.65, 0.0))
        time_card = build_glass_card(12.75, 1.44, center=(0.0, -2.08, 0.0))

        enforce_six_words("MicroStrategy (MSTR)")
        m_title = Text("MicroStrategy (MSTR)", font=FONT_UI, font_size=20, color=TXT_MAIN, weight="BOLD")
        m_title.move_to([float(mstr_card.get_left()[0]) + 1.48, float(mstr_card.get_top()[1]) - 0.30, 0.0])

        enforce_six_words("Bitcoin (BTC) · Referencia")
        b_title = Text("Bitcoin (BTC) · Referencia", font=FONT_UI, font_size=20, color=TXT_MAIN, weight="BOLD")
        b_title.move_to([float(btc_card.get_left()[0]) + 1.65, float(btc_card.get_top()[1]) - 0.30, 0.0])

        ax_m = Axes(
            x_range=[-1, 1, 0.5],
            y_range=[-1, 1, 0.5],
            x_length=4.95,
            y_length=2.18,
            axis_config={"color": BORDER_SUBTLE, "stroke_width": 1.2, "include_tip": False, "include_ticks": False},
        ).move_to(mstr_card.get_center() + DOWN * 0.12)

        ax_b = Axes(
            x_range=[-1, 1, 0.5],
            y_range=[-1, 1, 0.5],
            x_length=4.95,
            y_length=2.18,
            axis_config={"color": BORDER_SUBTLE, "stroke_width": 1.2, "include_tip": False, "include_ticks": False},
        ).move_to(btc_card.get_center() + DOWN * 0.12)

        pill_era1 = build_semantic_pill("Software · 53% global ↺", CYAN, font_size=14).move_to(mstr_card.get_bottom() + UP * 0.27)
        pill_era2 = build_semantic_pill("Tesorería BTC · 27% ↻", CORAL, font_size=14).move_to(mstr_card.get_bottom() + UP * 0.27)
        pill_era3 = build_semantic_pill("Post-ETF · 42%", AMBER, font_size=14).move_to(mstr_card.get_bottom() + UP * 0.27)
        pill_btc = build_semantic_pill("Pulso horario · 33% ↻", CORAL, font_size=14).move_to(btc_card.get_bottom() + UP * 0.27)

        # Timeline with generous vertical separation between top milestone ticks and bottom moving date
        tl_x0 = -5.55
        tl_x1 = 5.55
        tl_y = -2.06
        tl_track = Line([tl_x0, tl_y, 0.0], [tl_x1, tl_y, 0.0], color=BORDER_SUBTLE, stroke_width=3.0)

        x_aug20 = tl_x0 + (34.0 / (n_fr - 1)) * (tl_x1 - tl_x0)
        x_etf24 = tl_x0 + (78.0 / (n_fr - 1)) * (tl_x1 - tl_x0)

        lbl_2018 = Text("2018 · Software", font=FONT_UI, font_size=13, color=CYAN, weight="BOLD").move_to([tl_x0 + 0.72, tl_y + 0.42, 0.0])
        mark_aug = Line([x_aug20, tl_y - 0.08, 0.0], [x_aug20, tl_y + 0.24, 0.0], color=CORAL, stroke_width=2.6)
        lbl_aug = Text("Ago 2020 · Compra BTC", font=FONT_UI, font_size=13, color=CORAL, weight="BOLD").move_to([x_aug20, tl_y + 0.44, 0.0])
        mark_etf = Line([x_etf24, tl_y - 0.08, 0.0], [x_etf24, tl_y + 0.24, 0.0], color=AMBER, stroke_width=2.6)
        lbl_etf = Text("2024 · ETFs Wall St", font=FONT_UI, font_size=13, color=AMBER, weight="BOLD").move_to([x_etf24, tl_y + 0.44, 0.0])
        lbl_2026 = Text("2026", font=FONT_MONO, font_size=13, color=TXT_SUB).move_to([tl_x1 - 0.25, tl_y + 0.42, 0.0])

        idx_tracker = ValueTracker(0.0)

        def _era_blend_color(u: float) -> str:
            if u <= 32.0:
                return CYAN
            if u < 37.0:
                return lerp_hex_color(CYAN, CORAL, (u - 32.0) / 5.0)
            if u <= 76.0:
                return CORAL
            if u < 82.0:
                return lerp_hex_color(CORAL, AMBER, (u - 76.0) / 6.0)
            return AMBER

        def _dyn_mstr_panel():
            u = idx_tracker.get_value()
            pts, (ox, oy) = mstr_interp.sample_points(ax_m, u)
            pct = mstr_interp.sample_scalar("mstr_ccw_smooth_pct", u)
            col = _era_blend_color(u)
            cnt_col = _pct_to_color(pct)
            spin_sym = "↺" if pct >= 50.0 else "↻"
            ch_h = DashedLine(ax_m.c2p(-1, oy), ax_m.c2p(1, oy), dash_length=0.06, color=BORDER_SUBTLE, stroke_width=1.0)
            ch_v = DashedLine(ax_m.c2p(ox, -1), ax_m.c2p(ox, 1), dash_length=0.06, color=BORDER_SUBTLE, stroke_width=1.0)
            cnt_lbl = Text(f"{pct:3.0f}% {spin_sym}", font=FONT_UI, font_size=18, color=cnt_col, weight="BOLD")
            cnt_lbl.move_to([float(mstr_card.get_right()[0]) - 0.85, float(mstr_card.get_top()[1]) - 0.30, 0.0])
            return VGroup(
                ch_h,
                ch_v,
                build_glow_curve(pts, col, core_width=2.7),
                build_orbit_arrows(pts, col, fracs=(0.45, 0.82)),
                build_comet_head(pts[-1], col, radius=0.064),
                cnt_lbl,
            )

        def _dyn_btc_panel():
            u = idx_tracker.get_value()
            pts, (ox, oy) = btc_interp.sample_points(ax_b, u)
            pct = btc_interp.sample_scalar("btc_ccw_smooth_pct", u)
            cnt_col = _pct_to_color(pct)
            spin_sym = "↺" if pct >= 50.0 else "↻"
            ch_h = DashedLine(ax_b.c2p(-1, oy), ax_b.c2p(1, oy), dash_length=0.06, color=BORDER_SUBTLE, stroke_width=1.0)
            ch_v = DashedLine(ax_b.c2p(ox, -1), ax_b.c2p(ox, 1), dash_length=0.06, color=BORDER_SUBTLE, stroke_width=1.0)
            cnt_lbl = Text(f"{pct:3.0f}% {spin_sym}", font=FONT_UI, font_size=18, color=cnt_col, weight="BOLD")
            cnt_lbl.move_to([float(btc_card.get_right()[0]) - 0.85, float(btc_card.get_top()[1]) - 0.30, 0.0])
            return VGroup(
                ch_h,
                ch_v,
                build_glow_curve(pts, CORAL, core_width=2.7),
                build_orbit_arrows(pts, CORAL, fracs=(0.45, 0.82)),
                build_comet_head(pts[-1], CORAL, radius=0.064),
                cnt_lbl,
            )

        def _dyn_playhead():
            u = idx_tracker.get_value()
            frac = np.clip(u / float(n_fr - 1), 0.0, 1.0)
            px = tl_x0 + frac * (tl_x1 - tl_x0)
            col = _era_blend_color(u)
            prog_line = Line([tl_x0, tl_y, 0.0], [px, tl_y, 0.0], color=col, stroke_width=4.2)
            head = build_comet_head([px, tl_y, 0.0], col, radius=0.064)
            dt_txt = Text(mstr_interp.sample_date(u)[:7], font=FONT_MONO, font_size=12, color=TXT_MAIN)
            dt_txt.move_to([px, tl_y - 0.40, 0.0])
            return VGroup(prog_line, head, dt_txt)

        dyn_m = always_redraw(_dyn_mstr_panel)
        dyn_b = always_redraw(_dyn_btc_panel)
        dyn_tl = always_redraw(_dyn_playhead)

        # Beat 4 Blindness Comparison Card — clean vertical hierarchy with zero text collisions
        blind_card = build_glass_card(6.15, 3.66, center=(3.30, 0.65, 0.0), border_color=SLATE, fill_color=BG_CARD_ALT)
        enforce_six_words("Mutación 2D vs. Ceguera 1D")
        bl_title = Text("Mutación 2D vs. Ceguera 1D", font=FONT_UI, font_size=20, color=TXT_MAIN, weight="BOLD")
        bl_title.next_to(blind_card.get_top(), DOWN, buff=0.18)

        # Dedicated CMF badge cleanly below card title, completely above all bar percentages
        cmf_pill = build_semantic_pill("CMF(20) plano · ~50% ciego", SLATE, font_size=13)
        cmf_pill.next_to(bl_title, DOWN, buff=0.12)

        bar_specs = [
            ("Software", 52.8, CYAN, -1.65),
            ("Caja BTC", 27.3, CORAL, 0.05),
            ("Post-ETF", 42.0, AMBER, 1.75),
        ]
        base_y = float(blind_card.get_bottom()[1]) + 0.56
        max_h = 1.58  # represents 70% -> 52.8% bar top sits well below cmf_pill
        bars_grp = VGroup()
        for b_lbl, val, b_col, x_off in bar_specs:
            bh = max_h * (val / 70.0)
            bx = float(blind_card.get_center()[0]) + x_off
            rect = RoundedRectangle(
                corner_radius=0.08,
                width=1.02,
                height=bh,
                stroke_color=b_col,
                stroke_width=1.5,
                fill_color=b_col,
                fill_opacity=0.82,
            ).move_to([bx, base_y + bh / 2.0, 0.0])
            vl = Text(f"{val:.0f}%", font=FONT_MONO, font_size=15, color=b_col, weight="BOLD").next_to(rect, UP, buff=0.07)
            nl = Text(b_lbl, font=FONT_UI, font_size=13, color=TXT_SUB).move_to([bx, base_y - 0.22, 0.0])
            bars_grp.add(VGroup(rect, vl, nl))

        y_cmf50 = base_y + max_h * (50.0 / 70.0)
        cmf_line = DashedLine(
            [float(blind_card.get_left()[0]) + 0.72, y_cmf50, 0.0],
            [float(blind_card.get_right()[0]) - 0.36, y_cmf50, 0.0],
            dash_length=0.08,
            color=SLATE,
            stroke_width=2.0,
        )
        lbl_50_axis = Text("50%", font=FONT_MONO, font_size=12, color=SLATE, weight="BOLD")
        lbl_50_axis.next_to(cmf_line, LEFT, buff=0.08)
        blind_group = VGroup(blind_card, bl_title, cmf_pill, cmf_line, lbl_50_axis, bars_grp)

        # --- Audio-First 4-Beat Execution ---
        self.play(
            FadeIn(header, shift=DOWN * 0.15),
            FadeIn(mstr_card),
            FadeIn(btc_card),
            FadeIn(time_card),
            FadeIn(m_title),
            FadeIn(b_title),
            FadeIn(ax_m),
            FadeIn(ax_b),
            FadeIn(tl_track),
            FadeIn(lbl_2018),
            FadeIn(lbl_2026),
            FadeIn(pill_btc),
            run_time=0.90,
        )
        self.add(dyn_m, dyn_b, dyn_tl)

        # Beat 1: Software Era (frames 0 -> 33) + 53% pill
        self.play(idx_tracker.animate.set_value(22.0), run_time=remaining_until(self, t_53 - 0.25, floor=1.5), rate_func=linear)
        self.play(
            FadeIn(pill_era1, scale=0.92),
            idx_tracker.animate.set_value(33.5),
            run_time=remaining_until(self, t_aug - 0.10, floor=0.8),
            rate_func=linear,
        )

        # Beat 2: Aug 2020 Bitcoin Treasury Shock (frames 33.5 -> 77.5)
        self.play(
            FadeIn(mark_aug),
            FadeIn(lbl_aug, shift=DOWN * 0.08),
            FadeOut(pill_era1),
            FadeIn(pill_era2, scale=0.92),
            idx_tracker.animate.set_value(45.0),
            run_time=1.35,
            rate_func=smooth,
        )
        self.play(
            idx_tracker.animate.set_value(77.5),
            run_time=remaining_until(self, t_42 - 1.60, floor=2.0),
            rate_func=linear,
        )

        # Beat 3: 2024 Post-ETF Rebound (frames 77.5 -> 104.0, holding representative Post-ETF window)
        self.play(
            FadeIn(mark_etf),
            FadeIn(lbl_etf, shift=DOWN * 0.08),
            FadeOut(pill_era2),
            FadeIn(pill_era3, scale=0.92),
            idx_tracker.animate.set_value(92.0),
            run_time=1.40,
            rate_func=smooth,
        )
        self.play(
            idx_tracker.animate.set_value(104.0),
            run_time=remaining_until(self, t_blind - 0.35, floor=1.0),
            rate_func=linear,
        )

        # Freeze left MSTR panel & timeline cleanly, transition right card to Beat 4 Blindness summary
        static_m = _dyn_mstr_panel()
        static_tl = _dyn_playhead()
        self.remove(dyn_m, dyn_b, dyn_tl)
        self.add(static_m, static_tl)

        self.play(
            FadeOut(VGroup(btc_card, b_title, ax_b, pill_btc)),
            FadeIn(blind_group, scale=0.96),
            run_time=1.15,
            rate_func=smooth,
        )

        pad_scene_to_exact_audio(self, spec.duration_s)
