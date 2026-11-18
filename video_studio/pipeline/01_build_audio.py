#!/usr/bin/env python3
"""
Fase A — Audio-First Builder for KineTopus Video Studio (v2 Producer Polish)
- Supports per-scene speech rate (e.g. slower contemplative cadence on s10/s11)
- Captures exact WordBoundary timestamps
- Snaps every scene WAV to an exact 1/15 s quantum (= 1 frame @ 15fps -ql, 2 frames @ 30fps -qm, 4 frames @ 60fps -qh, 3200 stereo samples @ 48kHz) -> ZERO drift across all render qualities!
- Exports concatenated master radio cut normalized to -14 LUFS at strict 48 kHz.
"""

from __future__ import annotations

import asyncio
import json
import math
import subprocess
import unicodedata
import wave
from pathlib import Path

import edge_tts

STUDIO_DIR = Path(__file__).resolve().parent.parent
STORYBOARD_PATH = STUDIO_DIR / "storyboard.json"
RAW_DIR = STUDIO_DIR / "audio" / "raw"
WAV48_DIR = STUDIO_DIR / "audio" / "wav48"
RADIO_CUT_RAW = STUDIO_DIR / "audio" / "radio_cut_concat_raw.wav"
RADIO_CUT_MASTER = STUDIO_DIR / "audio" / "radio_cut_master_48k.wav"


def _norm(s: str) -> str:
    s = s.lower().strip(".,;:!?¿¡()[]{}\"'")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


async def synth_scene_edge(voice: str, rate: str, text: str, raw_mp3: Path, words_json: Path) -> list[dict]:
    comm = edge_tts.Communicate(text, voice=voice, rate=rate, boundary="WordBoundary")
    boundaries: list[dict] = []
    with open(raw_mp3, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                boundaries.append(
                    {
                        "text": chunk["text"],
                        "offset_s": round(chunk["offset"] / 10_000_000, 4),
                        "duration_s": round(chunk["duration"] / 10_000_000, 4),
                    }
                )
    words_json.write_text(json.dumps(boundaries, ensure_ascii=False, indent=2), encoding="utf-8")
    return boundaries


def convert_and_pad_exact_quantum_wav(
    raw_mp3: Path,
    dst_wav: Path,
    pause_after_s: float,
    sample_rate: int = 48000,
) -> tuple[float, float, int, int]:
    """
    Convert MP3 -> 48kHz stereo 16-bit PCM WAV, then pad trailing silence to exact 1/15 s quantum:
    1 quantum = 1 frame @ 15fps (-ql) = 4 frames @ 60fps (-qh) = 3200 stereo samples @ 48kHz.
    """
    tmp_wav = dst_wav.with_suffix(".tmp.wav")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(raw_mp3),
            "-ar",
            str(sample_rate),
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(tmp_wav),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    with wave.open(str(tmp_wav), "rb") as rf:
        n_speech_samples = rf.getnframes()
        pcm_bytes = rf.readframes(n_speech_samples)

    tmp_wav.unlink(missing_ok=True)

    speech_dur_s = n_speech_samples / float(sample_rate)
    frames_15 = math.ceil((speech_dur_s + pause_after_s) * 15.0)
    frames_60 = frames_15 * 4
    scene_dur_s = frames_60 / 60.0

    samples_per_quantum = sample_rate // 15  # 3200 exact
    target_total_samples = frames_15 * samples_per_quantum
    pad_samples = max(0, target_total_samples - n_speech_samples)
    silence_bytes = b"\x00\x00\x00\x00" * pad_samples

    with wave.open(str(dst_wav), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes + silence_bytes)

    return round(speech_dur_s, 4), round(scene_dur_s, 4), frames_60, frames_15


def resolve_cues(cues: list[str], boundaries: list[dict]) -> dict[str, float]:
    resolved: dict[str, float] = {}
    norm_tokens = [_norm(b["text"]) for b in boundaries]
    for cue in cues:
        parts = [_norm(p) for p in cue.split() if _norm(p)]
        if not parts:
            continue
        k = len(parts)
        matched_t = None
        for i in range(len(norm_tokens) - k + 1):
            if norm_tokens[i : i + k] == parts:
                matched_t = float(boundaries[i]["offset_s"])
                break
        if matched_t is None and k == 1:
            for i, tok in enumerate(norm_tokens):
                if tok.startswith(parts[0]):
                    matched_t = float(boundaries[i]["offset_s"])
                    break
        if matched_t is not None:
            resolved[cue] = matched_t
    return resolved


def build_radio_cut_master(wav_paths: list[Path], concat_raw: Path, master_out: Path, sample_rate: int = 48000) -> float:
    with wave.open(str(concat_raw), "wb") as out_wf:
        out_wf.setnchannels(2)
        out_wf.setsampwidth(2)
        out_wf.setframerate(sample_rate)
        for p in wav_paths:
            with wave.open(str(p), "rb") as in_wf:
                out_wf.writeframes(in_wf.readframes(in_wf.getnframes()))

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(concat_raw),
            "-af",
            "loudnorm=I=-14:TP=-1.0:LRA=11",
            "-ar",
            str(sample_rate),
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(master_out),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    concat_raw.unlink(missing_ok=True)

    with wave.open(str(master_out), "rb") as mf:
        return round(mf.getnframes() / float(sample_rate), 3)


async def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    WAV48_DIR.mkdir(parents=True, exist_ok=True)

    sb = json.loads(STORYBOARD_PATH.read_text(encoding="utf-8"))
    voice = sb["voice"]
    default_rate = sb.get("rate", "+0%")
    sr = int(sb.get("sample_rate_hz", 48000))

    total_speech = 0.0
    total_dur = 0.0
    total_frames_60 = 0
    wav_list: list[Path] = []

    print(f"Synthesizing {len(sb['scenes'])} scenes with {voice}...")
    for sc in sb["scenes"]:
        sid = sc["id"]
        rate = sc.get("rate", default_rate)
        raw_mp3 = RAW_DIR / f"{sid}.mp3"
        words_json = RAW_DIR / f"{sid}_words.json"
        dst_wav = WAV48_DIR / f"{sid}.wav"

        boundaries = await synth_scene_edge(voice, rate, sc["narration_tts"], raw_mp3, words_json)
        speech_s, scene_s, f60, f15 = convert_and_pad_exact_quantum_wav(
            raw_mp3, dst_wav, float(sc.get("pause_after_s", 0.7)), sample_rate=sr
        )
        cues_map = resolve_cues(sc.get("sync_cues", []), boundaries)

        sc["audio_wav"] = f"audio/wav48/{sid}.wav"
        sc["words_json"] = f"audio/raw/{sid}_words.json"
        sc["speech_duration_s"] = speech_s
        sc["scene_duration_s"] = scene_s
        sc["target_frames_60fps"] = f60
        sc["target_frames_15fps"] = f15
        sc["resolved_cues_s"] = cues_map

        total_speech += speech_s
        total_dur += scene_s
        total_frames_60 += f60
        wav_list.append(dst_wav)

        print(
            f"  [{sid}] rate={rate:>4s} | speech={speech_s:5.2f}s | total={scene_s:5.2f}s "
            f"({f60:4d}f@60 / {f15:3d}f@15) | cues={len(cues_map)}/{len(sc.get('sync_cues', []))}"
        )

    master_dur = build_radio_cut_master(wav_list, RADIO_CUT_RAW, RADIO_CUT_MASTER, sample_rate=sr)

    sb["total_speech_s"] = round(total_speech, 3)
    sb["total_duration_s"] = round(total_dur, 3)
    sb["total_frames_60fps"] = total_frames_60
    STORYBOARD_PATH.write_text(json.dumps(sb, ensure_ascii=False, indent=2), encoding="utf-8")

    mins = int(total_dur // 60)
    secs = total_dur - mins * 60
    print("-" * 78)
    print(f"TOTAL SPEECH: {total_speech:.2f}s | TOTAL VIDEO: {total_dur:.2f}s ({mins}:{secs:05.2f}) | FRAMES @60fps: {total_frames_60}")
    print(f"MASTER RADIO CUT (48kHz, -14 LUFS): {RADIO_CUT_MASTER} ({master_dur:.2f}s)")


if __name__ == "__main__":
    asyncio.run(main())
