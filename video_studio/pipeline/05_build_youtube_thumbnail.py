#!/usr/bin/env python3
"""
Fase D — Official 1280x720 YouTube Thumbnail Builder (Supersampled 2560x1440 -> Lanczos 1280x720)
Design rules (Apple Keynote x 3Blue1Brown x Veritasium):
  - #090D16 deep obsidian background
  - Maximum 3 giant bold words: "GIRAN AL REVÉS"
  - Real confronted 2D orbits (Cyan S&P 500 ↺ vs Coral Bitcoin ↻) from real_windows_substack.json#anim_01
  - Dashed projection rays collapsing onto a shared 1D shadow wave at the bottom
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from manim import (
    Axes,
    Circle,
    DashedLine,
    DOWN,
    LEFT,
    Line,
    RIGHT,
    RoundedRectangle,
    Scene,
    Text,
    UP,
    VGroup,
)

STUDIO_DIR = Path(__file__).resolve().parent.parent
if str(STUDIO_DIR) not in sys.path:
    sys.path.insert(0, str(STUDIO_DIR))

from components.theme import (  # noqa: E402
    AMBER,
    BG_CARD,
    BG_DARK,
    BORDER_SUBTLE,
    CORAL,
    CYAN,
    FONT_UI,
    SLATE,
    TXT_MAIN,
    TXT_SUB,
    build_comet_head,
    build_glow_curve,
    build_orbit_arrows,
    build_sharp_polyline,
    enforce_six_words,
    load_real_windows,
)

MANIM_EXE = STUDIO_DIR.parent / ".venv_video" / "Scripts" / "manim.exe"
OUT_PNG = STUDIO_DIR / "output" / "thumbnail_youtube_1280x720.png"


class YouTubeThumbnailScene(Scene):
    def construct(self) -> None:
        self.camera.background_color = BG_DARK
        anim01 = load_real_windows()["anim_01"]
        spy = anim01["spy"]
        btc = anim01["btc"]

        # Subtle ambient radial glow rings behind the two confronted orbits
        aura_l = Circle(radius=2.55, stroke_width=0, fill_color=CYAN, fill_opacity=0.055).move_to([-3.35, -0.05, 0.0])
        aura_r = Circle(radius=2.55, stroke_width=0, fill_color=CORAL, fill_opacity=0.055).move_to([3.35, -0.05, 0.0])
        self.add(aura_l, aura_r)

        # Giant 3-word YouTube Hook Headline (high mobile legibility!)
        enforce_six_words("GIRAN AL REVÉS", max_words=3)
        hero_title = Text("GIRAN AL REVÉS", font=FONT_UI, font_size=68, color=TXT_MAIN, weight="BOLD")
        hero_title.move_to([0.0, 3.12, 0.0])
        self.add(hero_title)

        def build_hero_orbit(asset: dict, center_x: float, color: str, tag_txt: str):
            vx = np.asarray(asset["vz"], dtype=float)
            ry = np.asarray(asset["r_smooth_pct"], dtype=float)
            px = max(0.06, (vx.max() - vx.min()) * 0.12)
            py = max(0.05, (ry.max() - ry.min()) * 0.12)
            ax = Axes(
                x_range=[float(vx.min() - px), float(vx.max() + px), 0.5],
                y_range=[float(ry.min() - py), float(ry.max() + py), 0.5],
                x_length=5.05,
                y_length=2.88,
                axis_config={"stroke_opacity": 0.0, "include_tip": False, "include_ticks": False},
            ).move_to([center_x, -0.10, 0.0])

            ring = RoundedRectangle(
                corner_radius=0.28,
                width=5.85,
                height=4.25,
                stroke_color=color,
                stroke_width=2.2,
                stroke_opacity=0.55,
                fill_color=BG_CARD,
                fill_opacity=0.88,
            ).move_to([center_x, 0.15, 0.0])

            pts = [ax.c2p(float(vx[i]), float(ry[i])) for i in range(len(vx))]
            glow = build_glow_curve(pts, color, core_width=4.6)
            arrs = build_orbit_arrows(pts, color, fracs=(0.24, 0.54, 0.82))
            for a in arrs:
                a.scale(1.55)
            head = build_comet_head(pts[-1], AMBER if color == CYAN else TXT_MAIN, radius=0.105)

            lbl = Text(tag_txt, font=FONT_UI, font_size=30, color=color, weight="BOLD")
            lbl.move_to([center_x, 1.82, 0.0])

            # Vertical projection rays down to the 1D shadow strip
            rays = VGroup(
                DashedLine([center_x - 1.65, -1.98, 0.0], [center_x - 1.15, -2.92, 0.0], dash_length=0.09, color=SLATE, stroke_width=1.8, stroke_opacity=0.55),
                DashedLine([center_x + 1.65, -1.98, 0.0], [center_x + 1.15, -2.92, 0.0], dash_length=0.09, color=SLATE, stroke_width=1.8, stroke_opacity=0.55),
            )
            return VGroup(ring, glow, arrs, head, lbl, rays)

        left_orb = build_hero_orbit(spy, -3.35, CYAN, "S&P 500 ↺")
        right_orb = build_hero_orbit(btc, 3.35, CORAL, "Bitcoin ↻")

        # Bottom 1D Shadow Bar (same upward wave shadow for both)
        sh_bar = RoundedRectangle(
            corner_radius=0.18,
            width=12.55,
            height=0.96,
            stroke_color=BORDER_SUBTLE,
            stroke_width=1.8,
            fill_color="#0C1220",
            fill_opacity=0.95,
        ).move_to([0.0, -3.18, 0.0])

        xs_sh = np.linspace(-5.65, 5.65, 140)
        ys_sh = -3.40 + 0.16 * np.sin((xs_sh + 5.65) * 1.25) + 0.022 * (xs_sh + 5.65)
        pts_sh = [[float(xs_sh[i]), float(ys_sh[i]), 0.0] for i in range(len(xs_sh))]
        sh_curve = build_sharp_polyline(pts_sh, SLATE, width=3.4, opacity=0.92)
        sh_lbl = Text("MISMA SOMBRA 1D", font=FONT_UI, font_size=19, color=TXT_SUB, weight="BOLD")
        sh_lbl.move_to([0.0, -2.92, 0.0])

        self.add(left_orb, right_orb, sh_bar, sh_curve, sh_lbl)


def build_thumbnail() -> Path:
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            str(MANIM_EXE),
            "-s",
            "-r",
            "2560,1440",
            "pipeline/05_build_youtube_thumbnail.py",
            "YouTubeThumbnailScene",
        ],
        cwd=str(STUDIO_DIR),
        check=True,
    )
    rendered_pngs = sorted((STUDIO_DIR / "media" / "images" / "05_build_youtube_thumbnail").glob("YouTubeThumbnailScene*.png"))
    assert rendered_pngs, "Thumbnail render PNG not found!"
    im = Image.open(rendered_pngs[-1]).convert("RGB")
    im_720 = im.resize((1280, 720), Image.Resampling.LANCZOS)
    im_720.save(OUT_PNG, optimize=True)
    print(f"Saved official YouTube thumbnail (1280x720): {OUT_PNG} ({OUT_PNG.stat().st_size:,} bytes)")
    return OUT_PNG


if __name__ == "__main__":
    build_thumbnail()
