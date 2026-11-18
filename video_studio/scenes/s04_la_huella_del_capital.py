#!/usr/bin/env python3
"""
S04 — 26,294 Instantáneas y la Paradoja de Oro y Tesla (39.13 s)
Structured in 4 distinct visual beats (~8-9 s each) with strict self.renderer.time sync:
  Beat 1 (0-12s): Hero rolling counter 26,294 + 99.9% independence from OBV/CMF.
  Beat 2 (12-20s): Horizontal Chirality Spectrum -> Institutional Cyan block (SPY 79%, QQQ 78%, MSFT 63%).
  Beat 3 (20-28s): Crypto 24/7 Coral block (BTC 33%, ETH 32%, SOL 28%).
  Beat 4 (28-39s): Psychological Amber spotlight on Tesla (39%) and Gold (36%) in regulated markets.
"""

from __future__ import annotations

import sys
from pathlib import Path

from manim import (
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
    EMERALD,
    FONT_MONO,
    FONT_UI,
    SLATE,
    STAGE_CENTER_Y,
    TXT_MAIN,
    TXT_MUTED,
    TXT_SUB,
    build_glass_card,
    build_header,
    build_semantic_pill,
    enforce_six_words,
    load_scene_timing,
    pad_scene_to_exact_audio,
    remaining_until,
    wait_until,
)


class S04HuellaCapital(Scene):
    def construct(self) -> None:
        self.camera.background_color = BG_DARK
        spec = load_scene_timing("s04_la_huella_del_capital")

        t_26k = spec.cue("veintiséis", 1.1)
        t_indep = spec.cue("independiente", 8.8)
        t_80 = spec.cue("ochenta", 16.3)
        t_30 = spec.cue("treinta", 22.3)
        t_gold = spec.cue("oro", 29.5)

        header = build_header("Acto 2 · Quién empuja", spec.on_screen["headline"])

        # =====================================================================
        # BEAT 1: Hero Counter 26,294 + 99.9% Orthogonality vs OBV / CMF
        # =====================================================================
        hero_card = build_glass_card(9.40, 4.55, center=(0.0, -0.10, 0.0))
        counter_val = ValueTracker(0.0)

        def _counter_mob():
            n_val = int(round(counter_val.get_value()))
            txt = f"{n_val:,}"
            return Text(txt, font=FONT_MONO, font_size=64, color=CYAN, weight="BOLD").move_to(hero_card.get_center() + UP * 0.72)

        dyn_counter = always_redraw(_counter_mob)
        enforce_six_words("Instantáneas causales sin mirar futuro")
        hero_sub = Text("Instantáneas causales sin mirar futuro", font=FONT_UI, font_size=20, color=TXT_SUB)
        hero_sub.move_to(hero_card.get_center() + DOWN * 0.12)

        pill_99 = build_semantic_pill("99.9% independiente de OBV", EMERALD, font_size=17)
        pill_blind = build_semantic_pill("OBV y CMF · Ciegos", SLATE, font_size=17)
        hero_pills = VGroup(pill_99, pill_blind).arrange(RIGHT, buff=0.35).move_to(hero_card.get_center() + DOWN * 1.18)

        self.play(FadeIn(header, shift=DOWN * 0.15), FadeIn(hero_card), FadeIn(hero_sub), run_time=0.80)
        self.add(dyn_counter)
        wait_until(self, max(0.85, t_26k - 0.15))
        self.play(counter_val.animate.set_value(26294), run_time=2.40, rate_func=smooth)

        static_counter = Text("26,294", font=FONT_MONO, font_size=64, color=CYAN, weight="BOLD").move_to(hero_card.get_center() + UP * 0.72)
        self.remove(dyn_counter)
        self.add(static_counter)

        wait_until(self, t_indep - 0.35)
        self.play(FadeIn(pill_99, shift=UP * 0.12), FadeIn(pill_blind, shift=UP * 0.12), run_time=1.05, rate_func=smooth)
        wait_until(self, 12.20)

        # =====================================================================
        # BEAT 2 -> 4: Horizontal Chirality Spectrum + 3 Insight Cards
        # =====================================================================
        spec_card = build_glass_card(8.15, 5.24, center=(-2.22, STAGE_CENTER_Y, 0.0))
        side_card = build_glass_card(4.20, 5.24, center=(4.32, STAGE_CENTER_Y, 0.0))

        enforce_six_words("% tiempo en giro antihorario")
        sp_title = Text("% tiempo en giro antihorario", font=FONT_UI, font_size=19, color=TXT_MAIN, weight="BOLD")
        sp_title.next_to(spec_card.get_top(), DOWN, buff=0.20)

        bar_x0 = float(spec_card.get_left()[0]) + 2.35
        bar_max_w = 4.65  # represents 100%
        x_50 = bar_x0 + bar_max_w * 0.50
        y_top_line = float(spec_card.get_top()[1]) - 0.72
        y_bot_line = float(spec_card.get_bottom()[1]) + 0.36
        mid_50_line = DashedLine([x_50, y_top_line, 0.0], [x_50, y_bot_line, 0.0], dash_length=0.07, color=BORDER_SUBTLE, stroke_width=1.4)
        lbl_50 = Text("50%", font=FONT_MONO, font_size=12, color=TXT_MUTED).next_to(mid_50_line, DOWN, buff=0.05)

        rows_spec = [
            ("S&P 500", 79.1, CYAN),
            ("Nasdaq-100", 78.4, CYAN),
            ("Microsoft", 62.6, CYAN),
            ("Tesla", 39.2, AMBER),
            ("Oro", 35.6, AMBER),
            ("Bitcoin", 33.0, CORAL),
            ("Solana", 27.8, CORAL),
        ]

        row_ys = [1.46 - i * 0.62 for i in range(len(rows_spec))]
        row_groups: list[VGroup] = []
        for (name, pct, col), ry in zip(rows_spec, row_ys):
            enforce_six_words(name)
            nlbl = Text(name, font=FONT_UI, font_size=16, color=TXT_MAIN, weight="BOLD")
            nlbl.move_to([bar_x0 - 0.22 - nlbl.width / 2.0, ry, 0.0])

            track = RoundedRectangle(
                corner_radius=0.08,
                width=bar_max_w,
                height=0.28,
                stroke_width=0,
                fill_color="#152036",
                fill_opacity=0.85,
            ).move_to([bar_x0 + bar_max_w / 2.0, ry, 0.0])

            bw = bar_max_w * (pct / 100.0)
            bar = RoundedRectangle(
                corner_radius=0.08,
                width=bw,
                height=0.28,
                stroke_color=col,
                stroke_width=1.2,
                fill_color=col,
                fill_opacity=0.82,
            ).move_to([bar_x0 + bw / 2.0, ry, 0.0])

            plbl = Text(f"{pct:.0f}%", font=FONT_MONO, font_size=15, color=col, weight="BOLD")
            plbl.next_to(bar, RIGHT, buff=0.14)
            row_groups.append(VGroup(nlbl, track, bar, plbl))

        def make_insight_box(y_off: float, t1_txt: str, t2_txt: str, col: str) -> VGroup:
            enforce_six_words(t1_txt)
            enforce_six_words(t2_txt)
            box = build_glass_card(3.76, 1.42, center=side_card.get_center() + UP * y_off, border_color=col, fill_color=BG_CARD_ALT)
            t1 = Text(t1_txt, font=FONT_UI, font_size=17, color=col, weight="BOLD")
            t2 = Text(t2_txt, font=FONT_UI, font_size=13, color=TXT_MAIN)
            vg = VGroup(t1, t2).arrange(DOWN, buff=0.10).move_to(box.get_center())
            return VGroup(box, vg)

        box_inst = make_insight_box(1.62, "↺ Ahorro programado", "Casi 80% · Entra antes", CYAN)
        box_cryp = make_insight_box(0.00, "↻ Pura persecución", "Ronda 30% · Corre detrás", CORAL)
        box_psyc = make_insight_box(-1.62, "Psicología · No horarios", "Oro reactivo · Tesla minorista", AMBER)

        self.play(
            FadeOut(VGroup(hero_card, static_counter, hero_sub, hero_pills)),
            FadeIn(spec_card),
            FadeIn(side_card),
            FadeIn(sp_title),
            FadeIn(mid_50_line),
            FadeIn(lbl_50),
            run_time=1.05,
            rate_func=smooth,
        )

        # Beat 2: Institutional Cyan rows (0, 1, 2)
        inst_rows = VGroup(row_groups[0], row_groups[1], row_groups[2])
        wait_until(self, max(13.4, t_80 - 1.6))
        self.play(
            FadeIn(inst_rows, lag_ratio=0.18, shift=RIGHT * 0.18),
            FadeIn(box_inst, shift=LEFT * 0.12),
            run_time=1.55,
            rate_func=smooth,
        )

        # Beat 3: Crypto Coral rows (5, 6)
        cryp_rows = VGroup(row_groups[5], row_groups[6])
        wait_until(self, max(19.8, t_30 - 1.2))
        self.play(
            FadeIn(cryp_rows, lag_ratio=0.20, shift=RIGHT * 0.18),
            FadeIn(box_cryp, shift=LEFT * 0.12),
            run_time=1.45,
            rate_func=smooth,
        )

        # Beat 4: Gold & Tesla Psychological Spotlight in Regulated Markets (rows 3, 4)
        psyc_rows = VGroup(row_groups[3], row_groups[4])
        wait_until(self, t_gold - 0.35)
        self.play(
            inst_rows.animate.set_opacity(0.42),
            cryp_rows.animate.set_opacity(0.42),
            box_inst.animate.set_opacity(0.45),
            box_cryp.animate.set_opacity(0.45),
            FadeIn(psyc_rows, lag_ratio=0.22, shift=RIGHT * 0.22),
            FadeIn(box_psyc, scale=0.94),
            run_time=1.50,
            rate_func=smooth,
        )

        # Restore subtle balance near the end so the full 7-asset map shines cleanly
        wait_until(self, spec.speech_s - 1.4)
        self.play(
            inst_rows.animate.set_opacity(0.88),
            cryp_rows.animate.set_opacity(0.88),
            box_inst.animate.set_opacity(0.88),
            box_cryp.animate.set_opacity(0.88),
            run_time=0.95,
            rate_func=smooth,
        )

        pad_scene_to_exact_audio(self, spec.duration_s)
