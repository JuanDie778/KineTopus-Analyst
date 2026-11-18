#!/usr/bin/env python3
"""
Phase B — Master Visual Kit (Apple Keynote Minimalism x 3Blue1Brown Geometric Rigor)
Enforces:
  1. Strict semantic color system (#090D16 dark obsidian, Cyan CCW/Spline, Coral CW/Noise/Tension, Emerald Law/Stable, Amber Focus, Slate Blind 1D)
  2. Max 1 idea & <= 6 words per label (automated guardrail)
  3. Bottom 14% YouTube Subtitle Safe Zone (all visual elements stay strictly at y >= SAFE_BOTTOM_Y = -2.84)
  4. Exact audio-first synchronization from storyboard.json
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
from manim import (
     Circle,
    DOWN,
    Dot,
    LEFT,
    Line,
    Polygon,
    RIGHT,
    RoundedRectangle,
    Scene,
    Text,
    UP,
    VGroup,
    VMobject,
)

STUDIO_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = STUDIO_DIR.parent
STORYBOARD_PATH = STUDIO_DIR / "storyboard.json"
REAL_WINDOWS_JSON = (
    REPO_ROOT
    / "reports"
    / "_gran_estudio_v3_ventaja_competitiva"
    / "publicacion_curiosos"
    / "scripts"
    / "real_windows_substack.json"
)

# ---------------------------------------------------------------------------
# Strict Semantic Palette
# ---------------------------------------------------------------------------
BG_DARK = "#090D16"
BG_CARD = "#0F1625"
BG_CARD_ALT = "#131D31"
BORDER_SUBTLE = "#22314C"
GRID_DIM = "#18243A"

TXT_MAIN = "#F4F6FB"
TXT_SUB = "#9FB0CB"
TXT_MUTED = "#687A99"

CYAN = "#38BDF8"      # Lz > 0 (Antihorario) / Causal Spline / Institutional Patience
CORAL = "#FB7185"     # Lz < 0 (Horario) / Raw Noise / Active Tension / Escape
EMERALD = "#34D399"   # Physical Law (9.8 m/s²) / Stable Closed Ellipse
AMBER = "#FBBF24"     # Present Cursor / Focal Highlight
SLATE = "#64748B"     # Blind 1D Shadow (OBV / CMF / AR1)

FONT_UI = "Segoe UI"
FONT_MONO = "Consolas"

# ---------------------------------------------------------------------------
# Layout & Subtitle Safe Zone Constants (Manim frame: 14.222 x 8.0, y in [-4, +4])
# Bottom 14% = 1.12 units -> y in [-4.00, -2.88] reserved for YouTube CC subtitles.
# ---------------------------------------------------------------------------
SAFE_TOP_Y = 3.66
SAFE_BOTTOM_Y = -2.84
STAGE_CENTER_Y = -0.18

DECOR_TOKENS = {"·", "•", "|", "—", "–", "-", "→", "←", "↺", "↻", "+", "×"}


def enforce_six_words(label: str, max_words: int = 6, allow_disclaimer: bool = False) -> str:
    if allow_disclaimer:
        return label
    real_words = [w for w in label.split() if w not in DECOR_TOKENS]
    if len(real_words) > max_words:
        raise ValueError(f"Producer Rule Violation: label '{label}' has {len(real_words)} words (max {max_words}).")
    return label


@dataclass
class SceneTiming:
    scene_id: str
    duration_s: float
    speech_s: float
    cues: dict[str, float]
    on_screen: dict

    def cue(self, key: str, default_s: float) -> float:
        return float(self.cues.get(key, default_s))


def load_scene_timing(scene_id: str) -> SceneTiming:
    sb = json.loads(STORYBOARD_PATH.read_text(encoding="utf-8"))
    for sc in sb["scenes"]:
        if sc["id"] == scene_id:
            return SceneTiming(
                scene_id=scene_id,
                duration_s=float(sc["scene_duration_s"]),
                speech_s=float(sc["speech_duration_s"]),
                cues=dict(sc.get("resolved_cues_s", {})),
                on_screen=dict(sc.get("on_screen_text", {})),
            )
    raise KeyError(f"Scene '{scene_id}' not found in storyboard.json")


def load_real_windows() -> dict:
    return json.loads(REAL_WINDOWS_JSON.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Reusable UI & Geometry Primitives
# ---------------------------------------------------------------------------
def build_header(kicker_txt: str, headline_txt: str) -> VGroup:
    enforce_six_words(kicker_txt, max_words=6)
    enforce_six_words(headline_txt, max_words=6)
    kicker = Text(kicker_txt.upper(), font=FONT_UI, font_size=14, color=TXT_MUTED, weight="BOLD")
    headline = Text(headline_txt, font=FONT_UI, font_size=31, color=TXT_MAIN, weight="BOLD")
    headline.next_to(kicker, DOWN, buff=0.10)
    grp = VGroup(kicker, headline)
    grp.move_to([0.0, SAFE_TOP_Y - grp.height / 2.0, 0.0])
    return grp


def build_glass_card(
    width: float,
    height: float,
    center: Sequence[float] = (0.0, STAGE_CENTER_Y, 0.0),
    border_color: str = BORDER_SUBTLE,
    fill_color: str = BG_CARD,
) -> RoundedRectangle:
    card = RoundedRectangle(
        corner_radius=0.18,
        width=width,
        height=height,
        stroke_color=border_color,
        stroke_width=1.6,
        fill_color=fill_color,
        fill_opacity=0.96,
    )
    card.move_to(center)
    bottom_y = float(card.get_bottom()[1])
    if bottom_y < SAFE_BOTTOM_Y - 0.02:
        raise ValueError(
            f"Subtitle Safe-Zone Violation: card bottom y={bottom_y:.2f} intrudes below SAFE_BOTTOM_Y={SAFE_BOTTOM_Y:.2f}"
        )
    return card


def build_semantic_pill(
    label_txt: str,
    accent: str,
    font_size: int = 17,
    allow_disclaimer: bool = False,
) -> VGroup:
    enforce_six_words(label_txt, max_words=6, allow_disclaimer=allow_disclaimer)
    lbl = Text(label_txt, font=FONT_UI, font_size=font_size, color=accent, weight="BOLD")
    bg = RoundedRectangle(
        corner_radius=0.16,
        width=lbl.width + 0.44,
        height=lbl.height + 0.24,
        stroke_color=accent,
        stroke_width=1.4,
        stroke_opacity=0.75,
        fill_color=accent,
        fill_opacity=0.13,
    )
    lbl.move_to(bg.get_center())
    return VGroup(bg, lbl)


def build_glow_curve(points: Sequence[Sequence[float]], color: str, core_width: float = 2.8) -> VGroup:
    if len(points) < 2:
        return VGroup()
    outer = VMobject(stroke_color=color, stroke_width=core_width * 3.4, stroke_opacity=0.13)
    mid = VMobject(stroke_color=color, stroke_width=core_width * 1.9, stroke_opacity=0.33)
    core = VMobject(stroke_color=color, stroke_width=core_width, stroke_opacity=1.0)
    outer.set_points_smoothly(points) if len(points) >= 4 else outer.set_points_as_corners(points)
    mid.set_points_smoothly(points) if len(points) >= 4 else mid.set_points_as_corners(points)
    core.set_points_smoothly(points) if len(points) >= 4 else core.set_points_as_corners(points)
    return VGroup(outer, mid, core)


def build_sharp_polyline(points: Sequence[Sequence[float]], color: str, width: float = 2.2, opacity: float = 0.9) -> VMobject:
    m = VMobject(stroke_color=color, stroke_width=width, stroke_opacity=opacity)
    if len(points) >= 2:
        m.set_points_as_corners(points)
    return m


def build_comet_head(point: Sequence[float], color: str, radius: float = 0.072) -> VGroup:
    halo = Circle(radius=radius * 2.2, stroke_width=0, fill_color=color, fill_opacity=0.26).move_to(point)
    core = Dot(point=point, radius=radius, color="#FFFFFF").set_stroke(color, width=2.6)
    return VGroup(halo, core)


def build_tangent_arrow(p_prev: Sequence[float], p_curr: Sequence[float], color: str, size: float = 0.13) -> VGroup:
    dx = float(p_curr[0] - p_prev[0])
    dy = float(p_curr[1] - p_prev[1])
    norm = math.hypot(dx, dy)
    if norm < 1e-6:
        return VGroup()
    ux, uy = dx / norm, dy / norm
    px, py = -uy, ux
    tip = np.array([p_curr[0] + ux * size * 0.65, p_curr[1] + uy * size * 0.65, 0.0])
    left = np.array([p_curr[0] - ux * size * 0.55 + px * size * 0.48, p_curr[1] - uy * size * 0.55 + py * size * 0.48, 0.0])
    right = np.array([p_curr[0] - ux * size * 0.55 - px * size * 0.48, p_curr[1] - uy * size * 0.55 - py * size * 0.48, 0.0])
    tri = Polygon(tip, left, right, stroke_width=0, fill_color=color, fill_opacity=0.95)
    return VGroup(tri)


def build_orbit_arrows(points: Sequence[Sequence[float]], color: str, fracs: Sequence[float] = (0.30, 0.68)) -> VGroup:
    n = len(points)
    grp = VGroup()
    if n < 6:
        return grp
    for f in fracs:
        idx = min(n - 1, max(2, int(round(f * (n - 1)))))
        grp.add(build_tangent_arrow(points[idx - 2], points[idx], color=color, size=0.135))
    return grp


def now_s(scene: Scene) -> float:
    return float(scene.renderer.time)


def wait_until(scene: Scene, target_t: float) -> None:
    fps = float(scene.camera.frame_rate)
    dt = float(target_t) - float(scene.renderer.time)
    if dt >= 0.5 / fps:
        scene.wait(dt)


def remaining_until(scene: Scene, target_t: float, floor: float = 0.20) -> float:
    return max(floor, float(target_t) - float(scene.renderer.time))


def pad_scene_to_exact_audio(scene: Scene, target_dur: float) -> None:
    fps = float(scene.camera.frame_rate)
    rem = float(target_dur) - float(scene.renderer.time)
    if rem >= 0.5 / fps:
        scene.wait(rem)


def pad_Scene_to_exact_audio(scene: Scene, target_dur: float, elapsed: float | None = None) -> None:
    pad_scene_to_exact_audio(scene, target_dur)


# ---------------------------------------------------------------------------
# Silky 60 fps Multi-Frame Orbit Interpolator & Geometry Clipping
# ---------------------------------------------------------------------------
def lerp_hex_color(hex_a: str, hex_b: str, t: float) -> str:
    u = max(0.0, min(1.0, float(t)))
    ca = hex_a.lstrip("#")
    cb = hex_b.lstrip("#")
    ra, ga, ba = int(ca[0:2], 16), int(ca[2:4], 16), int(ca[4:6], 16)
    rb, gb, bb = int(cb[0:2], 16), int(cb[2:4], 16), int(cb[4:6], 16)
    r = int(round((1.0 - u) * ra + u * rb))
    g = int(round((1.0 - u) * ga + u * gb))
    b = int(round((1.0 - u) * ba + u * bb))
    return f"#{r:02X}{g:02X}{b:02X}"


class SmoothOrbitInterpolator:
    """
    Precomputes forward-backward smoothed axis envelopes (_smooth_axis_envelope)
    and linearly interpolates both 2D trajectory coordinates and scalar metrics
    between frames[i0] and frames[i1] for silky 60 fps motion without jumps.
    """

    def __init__(
        self,
        frames: Sequence[dict],
        vz_key: str,
        r_key: str,
        scalar_keys: Sequence[str] = (),
        alpha: float = 0.22,
        pad_x: float = 0.20,
        pad_y: float = 0.24,
    ) -> None:
        self.n_frames = len(frames)
        self.dates = [str(fr.get("date", "")) for fr in frames]
        self.vx_arr = np.asarray([fr[vz_key] for fr in frames], dtype=float)
        self.ry_arr = np.asarray([fr[r_key] for fr in frames], dtype=float)
        self.scalars = {
            k: np.asarray([float(fr[k]) for fr in frames], dtype=float) for k in scalar_keys
        }

        raw_bounds = []
        data_ext = []
        for i in range(self.n_frames):
            vx = self.vx_arr[i]
            ry = self.ry_arr[i]
            x_lo, x_hi = min(float(vx.min()), 0.0), max(float(vx.max()), 0.0)
            y_lo, y_hi = min(float(ry.min()), 0.0), max(float(ry.max()), 0.0)
            dx = max(0.08, x_hi - x_lo)
            dy = max(0.08, y_hi - y_lo)
            raw_bounds.append([x_lo - pad_x * dx, x_hi + pad_x * dx, y_lo - pad_y * dy, y_hi + pad_y * dy])
            sx = max(0.06, float(vx.max() - vx.min()))
            sy = max(0.06, float(ry.max() - ry.min()))
            data_ext.append([
                float(vx.min()) - 0.12 * sx,
                float(vx.max()) + 0.12 * sx,
                float(ry.min()) - 0.12 * sy,
                float(ry.max()) + 0.12 * sy,
            ])

        arr = np.asarray(raw_bounds, dtype=float)
        fwd = arr.copy()
        for i in range(1, len(arr)):
            fwd[i] = alpha * arr[i] + (1.0 - alpha) * fwd[i - 1]
        bwd = fwd.copy()
        for i in range(len(arr) - 2, -1, -1):
            bwd[i] = alpha * fwd[i] + (1.0 - alpha) * bwd[i + 1]

        env = np.zeros_like(bwd)
        for i, ext in enumerate(data_ext):
            env[i, 0] = min(float(bwd[i, 0]), ext[0], -0.05)
            env[i, 1] = max(float(bwd[i, 1]), ext[1], +0.05)
            env[i, 2] = min(float(bwd[i, 2]), ext[2], -0.05)
            env[i, 3] = max(float(bwd[i, 3]), ext[3], +0.05)
        self.env = env

    def _split(self, u: float) -> tuple[int, int, float]:
        uc = max(0.0, min(float(self.n_frames - 1), float(u)))
        i0 = int(math.floor(uc))
        i1 = min(self.n_frames - 1, i0 + 1)
        return i0, i1, uc - i0

    def sample_points(self, ax, u: float) -> tuple[list[np.ndarray], tuple[float, float]]:
        """Return interpolated screen points inside ax (assumed [-1, 1]x[-1, 1]) + normalized (0,0) crosshair coords."""
        i0, i1, w = self._split(u)
        vx = (1.0 - w) * self.vx_arr[i0] + w * self.vx_arr[i1]
        ry = (1.0 - w) * self.ry_arr[i0] + w * self.ry_arr[i1]
        b = (1.0 - w) * self.env[i0] + w * self.env[i1]
        xmin, xmax, ymin, ymax = float(b[0]), float(b[1]), float(b[2]), float(b[3])
        span_x = max(1e-6, xmax - xmin)
        span_y = max(1e-6, ymax - ymin)
        nx = np.clip(-1.0 + 2.0 * (vx - xmin) / span_x, -0.97, 0.97)
        ny = np.clip(-1.0 + 2.0 * (ry - ymin) / span_y, -0.97, 0.97)
        ox = float(np.clip(-1.0 + 2.0 * (0.0 - xmin) / span_x, -0.95, 0.95))
        oy = float(np.clip(-1.0 + 2.0 * (0.0 - ymin) / span_y, -0.95, 0.95))
        pts = [ax.c2p(float(nx[k]), float(ny[k])) for k in range(len(nx))]
        return pts, (ox, oy)

    def sample_scalar(self, key: str, u: float) -> float:
        i0, i1, w = self._split(u)
        arr = self.scalars[key]
        return float((1.0 - w) * arr[i0] + w * arr[i1])

    def sample_date(self, u: float) -> str:
        i0, _, _ = self._split(u)
        return self.dates[i0]


def clip_conic_segments_to_box(
    segments: Sequence[Sequence[Sequence[float]]],
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
) -> list[list[tuple[float, float]]]:
    """Clip 2D conic segments strictly inside [xmin, xmax] x [ymin, ymax] with boundary intersections."""

    def _inside(x: float, y: float) -> bool:
        return xmin <= x <= xmax and ymin <= y <= ymax

    def _clip_edge(p0: tuple[float, float], p1: tuple[float, float]) -> tuple[tuple[float, float], tuple[float, float]] | None:
        # Liang-Barsky parametric clipping
        x0, y0 = p0
        dx, dy = p1[0] - x0, p1[1] - y0
        t0, t1 = 0.0, 1.0
        for p, q in ((-dx, x0 - xmin), (dx, xmax - x0), (-dy, y0 - ymin), (dy, ymax - y0)):
            if abs(p) < 1e-12:
                if q < 0:
                    return None
            else:
                r = q / p
                if p < 0:
                    if r > t1:
                        return None
                    if r > t0:
                        t0 = r
                else:
                    if r < t0:
                        return None
                    if r < t1:
                        t1 = r
        return ((x0 + t0 * dx, y0 + t0 * dy), (x0 + t1 * dx, y0 + t1 * dy))

    clipped_polys: list[list[tuple[float, float]]] = []
    for seg in segments:
        cur: list[tuple[float, float]] = []
        for k in range(len(seg) - 1):
            a = (float(seg[k][0]), float(seg[k][1]))
            b = (float(seg[k + 1][0]), float(seg[k + 1][1]))
            res = _clip_edge(a, b)
            if res is None:
                if len(cur) >= 2:
                    clipped_polys.append(cur)
                cur = []
            else:
                ca, cb = res
                if not cur:
                    cur.append(ca)
                cur.append(cb)
                if not _inside(b[0], b[1]):
                    if len(cur) >= 2:
                        clipped_polys.append(cur)
                    cur = []
        if len(cur) >= 2:
            clipped_polys.append(cur)
    return clipped_polys
