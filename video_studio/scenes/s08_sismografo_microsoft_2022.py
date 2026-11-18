#!/usr/bin/env python3
"""
S08 — Sismógrafo 2D: Prueba Ciega y el Techo de Microsoft (34.33 s)
100% Real Data Edition:
  - ROC-AUC scale [0.43, 0.63] guarantees 0.473 label stays strictly left of the 0.500 coin-flip dashed line.
  - Uses msft_frames[10:] (2021-10-15 -> 2022-01-06, 58 real cuts) reading 100% real re_lambda_engine
    (zero synthetic formulas) + certified Jan 6 1000b cut (+0.0227).
  - Left 1D panel overlays subtle Amber real MSFT close price curve (292 -> 330 -> 302 USD) alongside sleeping SLATE AR(1).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from manim import (
    Axes,
    Circle,
    DashedLine,
    DOWN,
    FadeIn,
    FadeOut,
    LEFT,
    RIGHT,
    ReplacementTransform,
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
    CYAN,
    EMERALD,
    FONT_MONO,
    FONT_UI,
    SLATE,
    STAGE_CENTER_Y,
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
    build_sharp_polyline,
    enforce_six_words,
    lerp_hex_color,
    load_real_windows,
    load_scene_timing,
    pad_scene_to_exact_audio,
    remaining_until,
    wait_until,
)


def _real_engine_color(re_eng: float) -> str:
    """Color purely from real re_lambda_engine (threshold +0.010 d⁻¹ as in render_visuals_curiosos.py)."""
    if re_eng < 0.0085:
        return EMERALD
    if re_eng < 0.0105:
        return lerp_hex_color(EMERALD, CORAL, (re_eng - 0.0085) / 0.0020)
    return CORAL


class S08SismografoMicrosoft(Scene):
    def construct(self) -> None:
        self.camera.background_color = BG_DARK
        spec = load_scene_timing("s08_sismografo_microsoft_2022")
        a3 = load_real_windows()["anim_03_ilus_03"]
        # Exact real slice used in render_visuals_curiosos.py (2021-10-15 -> 2022-01-06)
        msft_frames = a3["msft_frames"][10:]
        jan6_cut_re1000 = float(a3["msft_jan6_cut"]["re_lambda_1000"])  # +0.022744 real 1000b cut
        n_msft = len(msft_frames)  # 58 real daily cuts

        t_coin = spec.cue("moneda", 11.9)
        t_060 = spec.cue("punto sesenta", 15.95)
        t_msft = spec.cue("Microsoft", 22.98)
        t_sleep = spec.cue("dormía", 26.81)
        t_red = spec.cue("rojo", 30.39)

        header_1 = build_header("Acto 4 · Sismógrafo 2D", spec.on_screen["headline"])
        header_2 = build_header("Caso virgen · Microsoft", "Microsoft · Rumbo a enero 2022")

        # =====================================================================
        # BEATS 1 & 2: ROC-AUC Ranking (15 Virgin Markets) + 6/10 Duel Matrix
        # =====================================================================
        rank_card = build_glass_card(7.85, 5.24, center=(-2.35, STAGE_CENTER_Y, 0.0))
        duel_card = build_glass_card(4.50, 5.24, center=(4.18, STAGE_CENTER_Y, 0.0))

        enforce_six_words("Prueba ciega · 166 grandes caídas")
        rk_title = Text("Prueba ciega · 166 grandes caídas", font=FONT_UI, font_size=19, color=TXT_MAIN, weight="BOLD")
        rk_title.next_to(rank_card.get_top(), DOWN, buff=0.22)

        # Scale [0.445, 0.625] over 4.35 units -> generous gap between 0.473 label and 0.500 dashed line!
        bx0 = float(rank_card.get_left()[0]) + 2.55
        bw_span = 4.35
        auc_min, auc_span = 0.445, 0.180
        x_050 = bx0 + bw_span * ((0.500 - auc_min) / auc_span)
        coin_line = DashedLine(
            [x_050, float(rank_card.get_top()[1]) - 0.78, 0.0],
            [x_050, float(rank_card.get_bottom()[1]) + 0.40, 0.0],
            dash_length=0.07,
            color=TXT_SUB,
            stroke_width=1.5,
        )
        lbl_coin = Text("Azar · 0.500", font=FONT_MONO, font_size=12, color=TXT_SUB).next_to(coin_line, DOWN, buff=0.06)

        auc_specs = [
            ("KineTopus 2D", 0.603, CORAL, 1.15),
            ("Bollinger (20d)", 0.584, CYAN, 0.30),
            ("Lanzar moneda", 0.500, TXT_MUTED, -0.55),
            ("Scheffer AR(1)", 0.473, SLATE, -1.40),
        ]
        auc_rows: list[VGroup] = []
        for name, val, col, y_off in auc_specs:
            enforce_six_words(name)
            ry = STAGE_CENTER_Y + y_off
            nl = Text(name, font=FONT_UI, font_size=15, color=TXT_MAIN, weight="BOLD")
            nl.move_to([bx0 - 0.20 - nl.width / 2.0, ry, 0.0])
            w = bw_span * ((val - auc_min) / auc_span)
            bar = RoundedRectangle(
                corner_radius=0.08,
                width=w,
                height=0.34,
                stroke_color=col,
                stroke_width=1.4,
                fill_color=col,
                fill_opacity=0.82,
            ).move_to([bx0 + w / 2.0, ry, 0.0])
            vl = Text(f"{val:.3f}", font=FONT_MONO, font_size=13, color=col, weight="BOLD").next_to(bar, RIGHT, buff=0.09)
            auc_rows.append(VGroup(nl, bar, vl))

        enforce_six_words("Significado real de 0.60")
        dl_title = Text("Significado real de 0.60", font=FONT_UI, font_size=19, color=TXT_MAIN, weight="BOLD")
        dl_title.next_to(duel_card.get_top(), DOWN, buff=0.22)

        dots_grid = VGroup()
        for k in range(10):
            r_i, c_i = divmod(k, 5)
            lit = k < 6
            c_col = EMERALD if lit else SLATE
            op = 0.90 if lit else 0.25
            circ = Circle(radius=0.23, stroke_color=c_col, stroke_width=2.0, fill_color=c_col, fill_opacity=op)
            circ.move_to(duel_card.get_center() + UP * (0.68 - r_i * 0.72) + RIGHT * ((c_i - 2) * 0.68))
            dots_grid.add(circ)

        pill_610 = build_semantic_pill("6 de cada 10 duelos", EMERALD, font_size=15).move_to(duel_card.get_center() + DOWN * 0.88)
        enforce_six_words("Más tensión antes de caer")
        dl_sub = Text("Más tensión antes de caer", font=FONT_UI, font_size=14, color=TXT_SUB).move_to(duel_card.get_center() + DOWN * 1.55)

        self.play(
            FadeIn(header_1, shift=DOWN * 0.15),
            FadeIn(rank_card),
            FadeIn(duel_card),
            FadeIn(rk_title),
            FadeIn(dl_title),
            FadeIn(coin_line),
            FadeIn(lbl_coin),
            FadeIn(auc_rows[2]),
            run_time=0.90,
        )

        wait_until(self, t_coin - 1.6)
        self.play(FadeIn(auc_rows[3], shift=RIGHT * 0.18), run_time=1.20, rate_func=smooth)

        wait_until(self, t_060 - 0.35)
        self.play(
            FadeIn(auc_rows[1], shift=RIGHT * 0.18),
            FadeIn(auc_rows[0], shift=RIGHT * 0.22),
            FadeIn(dots_grid, lag_ratio=0.07),
            FadeIn(pill_610, scale=0.92),
            FadeIn(dl_sub),
            run_time=1.65,
            rate_func=smooth,
        )

        wait_until(self, t_msft - 0.45)

        # =====================================================================
        # BEATS 3 & 4: Microsoft 100% Real Live Seismograph (msft_frames[10:])
        # =====================================================================
        msft_interp = SmoothOrbitInterpolator(
            msft_frames,
            "orbit_vz",
            "orbit_r_pct",
            scalar_keys=("re_lambda_engine", "scheffer_ar1", "close"),
            alpha=0.24,
        )

        left_m_card = build_glass_card(5.85, 5.24, center=(-3.45, STAGE_CENTER_Y, 0.0))
        right_m_card = build_glass_card(6.45, 5.24, center=(3.15, STAGE_CENTER_Y, 0.0))

        enforce_six_words("Precio MSFT + AR(1) 1D")
        lm_title = Text("Precio MSFT + AR(1) 1D", font=FONT_UI, font_size=19, color=TXT_MAIN, weight="BOLD")
        lm_title.move_to([float(left_m_card.get_left()[0]) + 1.72, float(left_m_card.get_top()[1]) - 0.30, 0.0])

        enforce_six_words("KineTopus 2D · Órbita MSFT")
        rm_title = Text("KineTopus 2D · Órbita MSFT", font=FONT_UI, font_size=19, color=TXT_MAIN, weight="BOLD")
        rm_title.move_to([float(right_m_card.get_left()[0]) + 1.82, float(right_m_card.get_top()[1]) - 0.30, 0.0])

        # Upper mini-axes for real MSFT close price (280..345 USD), lower axes for AR(1) (-0.18..+0.25)
        ax_price = Axes(
            x_range=[0, n_msft - 1, 20],
            y_range=[282.0, 342.0, 20.0],
            x_length=4.75,
            y_length=1.22,
            axis_config={"color": BORDER_SUBTLE, "stroke_width": 1.1, "include_tip": False, "include_ticks": False},
        ).move_to(left_m_card.get_center() + UP * 0.88)

        ax_ar = Axes(
            x_range=[0, n_msft - 1, 20],
            y_range=[-0.16, 0.24, 0.1],
            x_length=4.75,
            y_length=1.55,
            axis_config={"color": BORDER_SUBTLE, "stroke_width": 1.2, "include_tip": False, "include_ticks": False},
        ).move_to(left_m_card.get_center() + DOWN * 0.78)
        ar_zero = DashedLine(ax_ar.c2p(0, 0), ax_ar.c2p(n_msft - 1, 0), dash_length=0.06, color=BORDER_SUBTLE, stroke_width=1.0)

        enforce_six_words("Precio real MSFT (USD)")
        lbl_pr_tag = Text("Precio real MSFT (USD)", font=FONT_UI, font_size=12, color=AMBER, weight="BOLD")
        lbl_pr_tag.next_to(ax_price, UP, buff=0.04).align_to(ax_price, LEFT)

        enforce_six_words("Scheffer AR(1) · 60 días")
        lbl_ar_tag = Text("Scheffer AR(1) · 60 días", font=FONT_UI, font_size=12, color=SLATE, weight="BOLD")
        lbl_ar_tag.next_to(ax_ar, UP, buff=0.04).align_to(ax_ar, LEFT)

        ax_orb = Axes(
            x_range=[-1, 1, 0.5],
            y_range=[-1, 1, 0.5],
            x_length=5.25,
            y_length=3.02,
            axis_config={"color": BORDER_SUBTLE, "stroke_width": 1.2, "include_tip": False, "include_ticks": False},
        ).move_to(right_m_card.get_center() + DOWN * 0.05)

        close_vals = [float(fr["close"]) for fr in msft_frames]
        ar_vals = [float(fr["scheffer_ar1"]) for fr in msft_frames]
        price_pts_all = [ax_price.c2p(float(i), close_vals[i]) for i in range(n_msft)]
        ar_pts_all = [ax_ar.c2p(float(i), ar_vals[i]) for i in range(n_msft)]

        pill_sleep = build_semantic_pill("AR(1) = +0.003 · Dormido", SLATE, font_size=14).move_to(left_m_card.get_bottom() + UP * 0.28)
        pill_drop = build_semantic_pill("Corte +0.0227 · Caída 330→234 USD", CORAL, font_size=14).move_to(right_m_card.get_bottom() + UP * 0.28)

        stage1_all = VGroup(rank_card, duel_card, rk_title, dl_title, coin_line, lbl_coin, *auc_rows, dots_grid, pill_610, dl_sub)
        self.play(
            ReplacementTransform(header_1, header_2),
            FadeOut(stage1_all),
            FadeIn(left_m_card),
            FadeIn(right_m_card),
            FadeIn(lm_title),
            FadeIn(rm_title),
            FadeIn(ax_price),
            FadeIn(lbl_pr_tag),
            FadeIn(ax_ar),
            FadeIn(ar_zero),
            FadeIn(lbl_ar_tag),
            FadeIn(ax_orb),
            run_time=1.05,
            rate_func=smooth,
        )

        u_trk = ValueTracker(0.0)

        def _dyn_left_1d():
            u = u_trk.get_value()
            k = max(2, min(n_msft, int(u) + 2))
            sub_p = price_pts_all[:k]
            sub_a = ar_pts_all[:k]
            pr_now = msft_interp.sample_scalar("close", u)
            pr_rd = Text(f"{pr_now:.0f} USD", font=FONT_MONO, font_size=14, color=AMBER, weight="BOLD")
            pr_rd.move_to([float(left_m_card.get_right()[0]) - 0.78, float(left_m_card.get_top()[1]) - 0.30, 0.0])
            return VGroup(
                build_sharp_polyline(sub_p, AMBER, width=2.4, opacity=0.88),
                build_comet_head(sub_p[-1], AMBER, 0.052),
                build_sharp_polyline(sub_a, SLATE, width=2.5, opacity=0.92),
                build_comet_head(sub_a[-1], SLATE, 0.055),
                pr_rd,
            )

        def _dyn_msft_orb():
            u = u_trk.get_value()
            pts, (ox, oy) = msft_interp.sample_points(ax_orb, u)
            re_eng = msft_interp.sample_scalar("re_lambda_engine", u)
            col = _real_engine_color(re_eng)
            ch_h = DashedLine(ax_orb.c2p(-1, oy), ax_orb.c2p(1, oy), dash_length=0.06, color=BORDER_SUBTLE, stroke_width=1.0)
            ch_v = DashedLine(ax_orb.c2p(ox, -1), ax_orb.c2p(ox, 1), dash_length=0.06, color=BORDER_SUBTLE, stroke_width=1.0)
            # Show live real engine Re(λ), and at final Jan 6 cut show the certified 1000b cut +0.0227
            disp_re = jan6_cut_re1000 if u >= float(n_msft - 1) - 0.15 else re_eng
            rd = Text(f"Re(λ) {disp_re:+.4f}", font=FONT_MONO, font_size=15, color=col, weight="BOLD")
            rd.move_to([float(right_m_card.get_right()[0]) - 1.05, float(right_m_card.get_top()[1]) - 0.30, 0.0])
            dt_lbl = Text(msft_interp.sample_date(u), font=FONT_MONO, font_size=12, color=TXT_MUTED)
            dt_lbl.next_to(ax_orb, DOWN, buff=0.06)
            return VGroup(
                ch_h,
                ch_v,
                build_glow_curve(pts, col, core_width=2.9),
                build_orbit_arrows(pts, col, fracs=(0.45, 0.80)),
                build_comet_head(pts[-1], col, radius=0.066),
                rd,
                dt_lbl,
            )

        dyn_l = always_redraw(_dyn_left_1d)
        dyn_r = always_redraw(_dyn_msft_orb)
        self.add(dyn_l, dyn_r)

        # Beat 3: Sweep Oct -> late Dec (real green calm, price peaks ~330 USD while AR(1) sleeps)
        self.play(u_trk.animate.set_value(38.0), run_time=remaining_until(self, t_sleep - 0.15, floor=1.6), rate_func=linear)
        self.play(
            FadeIn(pill_sleep, shift=UP * 0.08),
            u_trk.animate.set_value(54.5),
            run_time=remaining_until(self, t_red - 0.35, floor=1.4),
            rate_func=linear,
        )

        # Beat 4: Real crossing into >= +0.010 across 2022-01-05..06 right on cue['rojo']!
        self.play(
            u_trk.animate.set_value(float(n_msft - 1)),
            FadeIn(pill_drop, shift=UP * 0.08),
            run_time=1.45,
            rate_func=linear,
        )

        static_l = _dyn_left_1d()
        static_r = _dyn_msft_orb()
        self.remove(dyn_l, dyn_r)
        self.add(static_l, static_r)

        pad_scene_to_exact_audio(self, spec.duration_s)
