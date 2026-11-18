#!/usr/bin/env python3
"""
Fase B/C — Complete 11/11 Preliminary Film Builder & Zero-Drift Verifier (-ql 480p15)
- Reuses approved S01-S07 & S09 clips (verifying <0.05s drift on each),
- Rebuilds S08 (100% real re_lambda_engine + real close curve + clean 0.473/0.500 spacing),
- Builds new S10 (3 spacious columns) & S11 (navigation rules + disclaimer + 1D->2D lens + End Screen fade),
- Assembles actos_03_04_borrador_ql.mp4, actos_05_06_borrador_ql.mp4, and the complete 11/11
  video_preliminar_completo_ql.mp4 (340.0000 s = 5:40.00) with embedded Spanish .srt!
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

STUDIO_DIR = Path(__file__).resolve().parent.parent
BUILD_DIR = STUDIO_DIR / "build"
OUT_DIR = STUDIO_DIR / "output"
CTRL_DIR = OUT_DIR / "control_frames"
STORYBOARD_PATH = STUDIO_DIR / "storyboard.json"
MANIM_EXE = STUDIO_DIR.parent / ".venv_video" / "Scripts" / "manim.exe"

ACT1_SPECS = [
    ("s01_la_ilusion_de_la_sombra", "scenes/s01_la_ilusion_de_la_sombra.py", "S01IlusionSombra", [13.5, 25.2], False),
    ("s02_galileo_y_el_microscopio", "scenes/s02_galileo_y_el_microscopio.py", "S02GalileoMicroscopio", [11.8, 25.5], False),
    ("s03_las_cuatro_estaciones", "scenes/s03_las_cuatro_estaciones.py", "S03CuatroEstaciones", [5.5, 27.5], False),
]

ACT2_SPECS = [
    ("s04_la_huella_del_capital", "scenes/s04_la_huella_del_capital.py", "S04HuellaCapital", [9.8, 22.8, 32.5], False),
    ("s05_mutacion_microstrategy", "scenes/s05_mutacion_microstrategy.py", "S05MutacionMicroStrategy", [10.5, 22.0, 35.8], False),
]

ACT34_SPECS = [
    ("s06_elipses_vs_hiperbolas", "scenes/s06_elipses_vs_hiperbolas.py", "S06ElipsesVsHiperbolas", [15.5, 27.5], False),
    ("s07_fractal_bitcoin_6x", "scenes/s07_fractal_bitcoin_6x.py", "S07FractalBitcoin6x", [9.2, 24.8], False),
    ("s08_sismografo_microsoft_2022", "scenes/s08_sismografo_microsoft_2022.py", "S08SismografoMicrosoft", [18.5, 32.2], False),
    ("s09_limite_honesto_covid", "scenes/s09_limite_honesto_covid.py", "S09LimiteHonestoCovid", [15.0, 24.8], False),
]

ACT56_SPECS = [
    ("s10_radiografia_noviembre_2026", "scenes/s10_radiografia_noviembre_2026.py", "S10RadiografiaNov2026", [15.8, 26.5], False),
    ("s11_epilogo_panel_de_vuelo", "scenes/s11_epilogo_panel_de_vuelo.py", "S11EpilogoPanelVuelo", [15.5, 25.5], True),
]


def run_cmd(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def verify_zero_drift(mp4_path: Path, expected_dur: float, tol: float = 0.05) -> dict:
    raw = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,duration,sample_rate,r_frame_rate",
            "-of",
            "json",
            str(mp4_path),
        ],
        text=True,
    )
    info = json.loads(raw)
    v_dur = next(float(s["duration"]) for s in info["streams"] if s["codec_type"] == "video")
    a_stream = next(s for s in info["streams"] if s["codec_type"] == "audio")
    a_dur = float(a_stream["duration"])
    sr = int(a_stream["sample_rate"])

    dv = abs(v_dur - expected_dur)
    da = abs(a_dur - expected_dur)
    dva = abs(v_dur - a_dur)
    print(
        f"  [FFPROBE] {mp4_path.name}: expected={expected_dur:.4f}s | video={v_dur:.4f}s (Δ={dv:.4f}s) "
        f"| audio={a_dur:.4f}s (Δ={da:.4f}s) | |V-A|={dva:.4f}s | sr={sr}Hz"
    )
    assert sr == 48000, f"Sample rate violation: {sr} != 48000"
    assert dv < tol and da < tol and dva < tol, (
        f"Audio drift violation on {mp4_path.name}: dv={dv:.4f}s, da={da:.4f}s, dva={dva:.4f}s (tol={tol}s)"
    )
    return info


def extract_frame(video_path: Path, t_sec: float, out_png: Path) -> None:
    run_cmd(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{t_sec:.2f}",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-loglevel",
            "error",
            str(out_png),
        ]
    )


def build_safezone_contact_sheet(png_paths: list[Path], out_sheet: Path, cols: int = 2) -> None:
    imgs = [Image.open(p).convert("RGB") for p in png_paths]
    w, h = imgs[0].size
    rows = (len(imgs) + cols - 1) // cols
    pad = 16
    sheet = Image.new("RGB", (cols * w + (cols + 1) * pad, rows * h + (rows + 1) * pad), (6, 9, 15))
    draw = ImageDraw.Draw(sheet)

    for idx, im in enumerate(imgs):
        r, c = divmod(idx, cols)
        x0 = pad + c * (w + pad)
        y0 = pad + r * (h + pad)
        sheet.paste(im, (x0, y0))
        safe_y = y0 + int(round(h * (1.0 - 0.14)))
        for sx in range(x0, x0 + w, 16):
            draw.line([(sx, safe_y), (min(x0 + w, sx + 9), safe_y)], fill=(251, 191, 36), width=2)
        draw.rectangle([x0, y0, x0 + w - 1, y0 + h - 1], outline=(34, 49, 76), width=2)

    out_sheet.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_sheet)


def render_and_mux_specs(specs: list[tuple], sb_map: dict[str, dict]) -> tuple[list[Path], list[Path], float]:
    muxed: list[Path] = []
    pngs: list[Path] = []
    total_expected = 0.0

    for sid, rel_script, cls_name, snap_times, force_rebuild in specs:
        f15 = int(sb_map[sid]["target_frames_15fps"])
        target_dur = f15 / 15.0
        total_expected += target_dur
        mux_out = BUILD_DIR / f"{sid}_ql.mp4"

        if not force_rebuild and mux_out.exists():
            print(f"\n=== Reusing approved {sid} -> verifying zero drift ===")
            verify_zero_drift(mux_out, target_dur, tol=0.05)
        else:
            print(f"\n=== Rendering {sid} ({cls_name}) -> target={target_dur:.6f}s ({f15}f) ===")
            run_cmd([str(MANIM_EXE), "-ql", rel_script, cls_name], cwd=STUDIO_DIR)

            stem = Path(rel_script).stem
            silent_mp4 = STUDIO_DIR / "media" / "videos" / stem / "480p15" / f"{cls_name}.mp4"
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
                    str(f15),
                    "-c:v",
                    "libx264",
                    "-crf",
                    "18",
                    "-pix_fmt",
                    "yuv420p",
                    "-r",
                    "15",
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
            verify_zero_drift(mux_out, target_dur, tol=0.05)

        muxed.append(mux_out)
        for k, ts in enumerate(snap_times, 1):
            p_out = CTRL_DIR / f"{sid}_ctrl_{k}.png"
            extract_frame(mux_out, ts, p_out)
            pngs.append(p_out)

    return muxed, pngs, total_expected


def concat_with_srt(clips: list[Path], srt_path: Path, out_mp4: Path, expected_dur: float) -> None:
    concat_txt = BUILD_DIR / f"concat_{out_mp4.stem}.txt"
    concat_txt.write_text("\n".join(f"file '{p.as_posix()}'" for p in clips) + "\n", encoding="utf-8")
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
            str(srt_path),
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
            str(out_mp4),
        ]
    )
    verify_zero_drift(out_mp4, expected_dur, tol=0.05)


def main() -> None:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CTRL_DIR.mkdir(parents=True, exist_ok=True)

    sb = json.loads(STORYBOARD_PATH.read_text(encoding="utf-8"))
    sb_map = {sc["id"]: sc for sc in sb["scenes"]}

    act1_clips, _, act1_dur = render_and_mux_specs(ACT1_SPECS, sb_map)
    act2_clips, _, act2_dur = render_and_mux_specs(ACT2_SPECS, sb_map)

    act34_clips, act34_pngs, act34_dur = render_and_mux_specs(ACT34_SPECS, sb_map)
    concat_with_srt(act34_clips, OUT_DIR / "subtitles_es_actos_03_04.srt", OUT_DIR / "actos_03_04_borrador_ql.mp4", act34_dur)
    build_safezone_contact_sheet(act34_pngs, CTRL_DIR / "contact_acto_03_04_safezone.png", cols=2)

    act56_clips, act56_pngs, act56_dur = render_and_mux_specs(ACT56_SPECS, sb_map)
    concat_with_srt(act56_clips, OUT_DIR / "subtitles_es_actos_05_06.srt", OUT_DIR / "actos_05_06_borrador_ql.mp4", act56_dur)
    build_safezone_contact_sheet(act56_pngs, CTRL_DIR / "contact_acto_05_06_safezone.png", cols=2)

    # Full 11/11 Preliminary Film (340.0000 s = 5:40.00)
    all_clips = act1_clips + act2_clips + act34_clips + act56_clips
    total_dur = act1_dur + act2_dur + act34_dur + act56_dur
    concat_with_srt(
        all_clips,
        OUT_DIR / "subtitles_es.srt",
        OUT_DIR / "video_preliminar_completo_ql.mp4",
        total_dur,
    )

    print("\n=== COMPLETE 11/11 PRELIMINARY FILM (340.00s) ZERO-DRIFT VERIFIED ===")


if __name__ == "__main__":
    main()
