#!/usr/bin/env python3
"""
Fase D — Final Broadcast Master Renderer (1920x1080 @ 60 fps, H.264 CRF 17, 48 kHz -14 LUFS)
- Resumable per-scene build (reuses any scene_1080p60.mp4 that already passes zero-drift verification).
- Enforces exact target_frames_60fps (-frames:v) + atrim + -ar 48000 on all 11 scenes.
- Concatenates into video_studio/output/kinetopus_segunda_dimension_MASTER_1080p60.mp4 with soft .srt.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

STUDIO_DIR = Path(__file__).resolve().parent.parent
BUILD_DIR = STUDIO_DIR / "build" / "1080p60"
OUT_DIR = STUDIO_DIR / "output"
STORYBOARD_PATH = STUDIO_DIR / "storyboard.json"
MANIM_EXE = STUDIO_DIR.parent / ".venv_video" / "Scripts" / "manim.exe"

ALL_SCENES = [
    ("s01_la_ilusion_de_la_sombra", "scenes/s01_la_ilusion_de_la_sombra.py", "S01IlusionSombra"),
    ("s02_galileo_y_el_microscopio", "scenes/s02_galileo_y_el_microscopio.py", "S02GalileoMicroscopio"),
    ("s03_las_cuatro_estaciones", "scenes/s03_las_cuatro_estaciones.py", "S03CuatroEstaciones"),
    ("s04_la_huella_del_capital", "scenes/s04_la_huella_del_capital.py", "S04HuellaCapital"),
    ("s05_mutacion_microstrategy", "scenes/s05_mutacion_microstrategy.py", "S05MutacionMicroStrategy"),
    ("s06_elipses_vs_hiperbolas", "scenes/s06_elipses_vs_hiperbolas.py", "S06ElipsesVsHiperbolas"),
    ("s07_fractal_bitcoin_6x", "scenes/s07_fractal_bitcoin_6x.py", "S07FractalBitcoin6x"),
    ("s08_sismografo_microsoft_2022", "scenes/s08_sismografo_microsoft_2022.py", "S08SismografoMicrosoft"),
    ("s09_limite_honesto_covid", "scenes/s09_limite_honesto_covid.py", "S09LimiteHonestoCovid"),
    ("s10_radiografia_noviembre_2026", "scenes/s10_radiografia_noviembre_2026.py", "S10RadiografiaNov2026"),
    ("s11_epilogo_panel_de_vuelo", "scenes/s11_epilogo_panel_de_vuelo.py", "S11EpilogoPanelVuelo"),
]


def run_cmd(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def verify_master_clip(mp4_path: Path, expected_dur: float, tol: float = 0.05) -> None:
    raw = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,duration,width,height,r_frame_rate,sample_rate",
            "-of",
            "json",
            str(mp4_path),
        ],
        text=True,
    )
    info = json.loads(raw)
    v_st = next(s for s in info["streams"] if s["codec_type"] == "video")
    a_st = next(s for s in info["streams"] if s["codec_type"] == "audio")
    v_dur = float(v_st["duration"])
    a_dur = float(a_st["duration"])
    w, h = int(v_st["width"]), int(v_st["height"])
    fps_str = v_st["r_frame_rate"]
    sr = int(a_st["sample_rate"])

    dv = abs(v_dur - expected_dur)
    da = abs(a_dur - expected_dur)
    dva = abs(v_dur - a_dur)
    print(
        f"  [1080p60 QA] {mp4_path.name}: {w}x{h} @{fps_str} | V={v_dur:.4f}s | A={a_dur:.4f}s "
        f"| |V-A|={dva:.4f}s | {sr}Hz"
    )
    assert (w, h) == (1920, 1080) and fps_str == "60/1" and sr == 48000
    assert dv < tol and da < tol and dva < tol


def main() -> None:
    force_ids = set(sys.argv[1:])
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    sb = json.loads(STORYBOARD_PATH.read_text(encoding="utf-8"))
    sb_map = {sc["id"]: sc for sc in sb["scenes"]}

    clips: list[Path] = []
    total_expected = 0.0

    for sid, rel_script, cls_name in ALL_SCENES:
        f60 = int(sb_map[sid]["target_frames_60fps"])
        target_dur = f60 / 60.0
        total_expected += target_dur
        mux_out = BUILD_DIR / f"{sid}_1080p60.mp4"

        if mux_out.exists() and sid not in force_ids and "all" not in force_ids:
            print(f"\n=== Reusing verified 1080p60 {sid} ===")
            verify_master_clip(mux_out, target_dur)
            clips.append(mux_out)
            continue

        print(f"\n=== Rendering MASTER 1080p60 {sid} ({f60} frames, {target_dur:.4f}s) ===")
        run_cmd([str(MANIM_EXE), "-qh", rel_script, cls_name], cwd=STUDIO_DIR)

        stem = Path(rel_script).stem
        silent_mp4 = STUDIO_DIR / "media" / "videos" / stem / "1080p60" / f"{cls_name}.mp4"
        wav_in = STUDIO_DIR / "audio" / "wav48" / f"{sid}.wav"

        run_cmd(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(silent_mp4),
                "-i",
                str(wav_in),
                "-vf",
                "tpad=stop_mode=clone:stop_duration=2",
                "-frames:v",
                str(f60),
                "-c:v",
                "libx264",
                "-crf",
                "17",
                "-preset",
                "medium",
                "-pix_fmt",
                "yuv420p",
                "-r",
                "60",
                "-af",
                f"loudnorm=I=-14:TP=-1.0:LRA=11,apad,atrim=0:{target_dur:.6f}",
                "-ar",
                "48000",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-loglevel",
                "error",
                str(mux_out),
            ]
        )
        verify_master_clip(mux_out, target_dur)
        clips.append(mux_out)

    concat_txt = BUILD_DIR / "concat_master_1080p60.txt"
    concat_txt.write_text("\n".join(f"file '{p.as_posix()}'" for p in clips) + "\n", encoding="utf-8")
    master_out = OUT_DIR / "kinetopus_segunda_dimension_MASTER_1080p60.mp4"

    run_cmd(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_txt),
            "-i",
            str(OUT_DIR / "subtitles_es.srt"),
            "-c:v",
            "copy",
            "-c:a",
            "copy",
            "-c:s",
            "mov_text",
            "-metadata:s:s:0",
            "language=spa",
            "-movflags",
            "+faststart",
            "-loglevel",
            "error",
            str(master_out),
        ]
    )
    verify_master_clip(master_out, total_expected)
    print(f"\n=== YOUTUBE 1080p60 MASTER READY: {master_out} ===")


if __name__ == "__main__":
    main()
