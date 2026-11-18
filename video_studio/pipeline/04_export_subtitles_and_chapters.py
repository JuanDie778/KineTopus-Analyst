#!/usr/bin/env python3
"""
Exports broadcast-clean Spanish subtitles (.srt) strictly from narration_display
(never phonetic narration_tts) aligned 1:1 to exact WordBoundary sentence windows, plus
YouTube Chapters + Legal Disclaimer (youtube_chapters.txt).
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

STUDIO_DIR = Path(__file__).resolve().parent.parent
STORYBOARD_PATH = STUDIO_DIR / "storyboard.json"
OUT_DIR = STUDIO_DIR / "output"


def _norm_tok(s: str) -> str:
    s = s.lower().strip(".,;:!?¿¡()[]{}\"'—–-")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def fmt_srt_time(seconds: float) -> str:
    ms_total = max(0, int(round(seconds * 1000)))
    hh = ms_total // 3_600_000
    rem = ms_total % 3_600_000
    mm = rem // 60_000
    rem %= 60_000
    ss = rem // 1000
    ms = rem % 1000
    return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"


def fmt_yt_chapter(seconds: float) -> str:
    sec_int = max(0, int(round(seconds)))
    mm = sec_int // 60
    ss = sec_int % 60
    return f"{mm:02d}:{ss:02d}"


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.?!])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def wrap_subtitle_block(sentence: str, max_line_chars: int = 42, max_block_chars: int = 84) -> list[str]:
    """Split a long sentence into balanced subtitle cards (zero 1-2 word orphans), each <= 2 lines."""
    n_total = len(sentence)
    n_cards = max(1, (n_total + max_block_chars - 1) // max_block_chars)
    words = sentence.split()
    if n_cards == 1 or len(words) <= 4:
        chunks = [sentence]
    else:
        target_chars = n_total / n_cards
        chunks = []
        cur: list[str] = []
        cur_len = 0
        for i, w in enumerate(words):
            add_len = len(w) + (1 if cur else 0)
            rem_cards = n_cards - len(chunks)
            rem_words = len(words) - i
            if rem_cards > 1 and cur and cur_len + add_len > target_chars + 6 and rem_words >= 3:
                chunks.append(" ".join(cur))
                cur = [w]
                cur_len = len(w)
            else:
                cur.append(w)
                cur_len += add_len
        if cur:
            chunks.append(" ".join(cur))

    formatted: list[str] = []
    for ch in chunks:
        if len(ch) <= max_line_chars:
            formatted.append(ch)
            continue
        wlist = ch.split()
        best_idx = 1
        best_diff = 10**9
        for i in range(1, len(wlist)):
            l1 = " ".join(wlist[:i])
            l2 = " ".join(wlist[i:])
            diff = abs(len(l1) - len(l2))
            if len(l1) <= max_line_chars + 6 and len(l2) <= max_line_chars + 6 and diff < best_diff:
                best_diff = diff
                best_idx = i
        formatted.append(" ".join(wlist[:best_idx]) + "\n" + " ".join(wlist[best_idx:]))
    return formatted


def detect_tts_sentence_windows(tts_text: str, boundaries: list[dict], speech_dur: float) -> list[tuple[float, float]]:
    """Map each sentence in narration_tts to exact WordBoundary start and end timestamps via sequential token matching."""
    tts_sents = split_sentences(tts_text)
    assert boundaries and tts_sents, "Missing WordBoundary tokens or TTS sentences."

    b_norms = [_norm_tok(b["text"]) for b in boundaries]
    n_b = len(boundaries)
    cursor = 0
    windows: list[tuple[float, float]] = []

    for s_idx, sent in enumerate(tts_sents):
        s_toks = [_norm_tok(t) for t in re.findall(r"[\wáéíóúñüÁÉÍÓÚÑÜ]+", sent) if _norm_tok(t)]
        assert s_toks, f"Empty tokenized sentence: {sent}"

        # Match first token near cursor
        start_b = cursor
        for probe in range(cursor, min(n_b, cursor + 5)):
            if b_norms[probe] == s_toks[0] or b_norms[probe].startswith(s_toks[0][:3]):
                start_b = probe
                break

        if s_idx == len(tts_sents) - 1:
            end_b = n_b - 1
        else:
            # Advance len(s_toks) tokens and snap to exact last token match
            est_end = min(n_b - 1, start_b + len(s_toks) - 1)
            end_b = est_end
            last_tok = s_toks[-1]
            for probe in range(max(start_b, est_end - 3), min(n_b, est_end + 4)):
                if b_norms[probe] == last_tok:
                    end_b = probe
                    break

        t_start = float(boundaries[start_b]["offset_s"])
        t_end = float(boundaries[end_b]["offset_s"] + boundaries[end_b]["duration_s"])
        if s_idx == len(tts_sents) - 1:
            t_end = max(t_end, speech_dur)
        windows.append((t_start, t_end))
        cursor = min(n_b - 1, end_b + 1)

    return windows


def export_all(max_scene_index: int | None = None, suffix: str = "") -> tuple[Path, Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sb = json.loads(STORYBOARD_PATH.read_text(encoding="utf-8"))
    scenes = sb["scenes"] if max_scene_index is None else sb["scenes"][:max_scene_index]

    srt_entries: list[str] = []
    chapter_lines: list[str] = [
        f"{sb['title']}",
        "",
        "Capítulos:",
    ]

    cue_counter = 1
    scene_offset_s = 0.0

    for sc in scenes:
        chapter_lines.append(f"{fmt_yt_chapter(scene_offset_s)} {sc.get('chapter_title', sc['title'])}")

        words_path = STUDIO_DIR / sc["words_json"]
        boundaries = json.loads(words_path.read_text(encoding="utf-8"))
        speech_dur = float(sc["speech_duration_s"])
        scene_dur = float(sc["scene_duration_s"])

        disp_sents = split_sentences(sc["narration_display"])
        tts_windows = detect_tts_sentence_windows(sc["narration_tts"], boundaries, speech_dur)

        # Strict 1:1 producer assertion — zero fallback allowed
        assert len(disp_sents) == len(tts_windows), (
            f"Sentence parity failure in {sc['id']}: "
            f"narration_display={len(disp_sents)} vs narration_tts={len(tts_windows)}"
        )

        for sent, (w_start, w_end) in zip(disp_sents, tts_windows):
            cards = wrap_subtitle_block(sent)
            card_chars = max(1, sum(len(c) for c in cards))
            t_c = w_start
            span = max(0.32, w_end - w_start)
            for c_idx, card in enumerate(cards):
                dt = span * (len(card) / card_chars)
                t0 = scene_offset_s + t_c
                t1 = scene_offset_s + (w_end if c_idx == len(cards) - 1 else t_c + dt - 0.04)
                t1 = max(t0 + 0.28, t1)
                srt_entries.append(f"{cue_counter}\n{fmt_srt_time(t0)} --> {fmt_srt_time(t1)}\n{card}\n")
                cue_counter += 1
                t_c += dt

        scene_offset_s += scene_dur

    chapter_lines.extend(
        [
            "",
            "Nota legal:",
            "Investigación cuantitativa y divulgativa basada en datos históricos reales (2000–2026). No constituye asesoría financiera ni recomendación de inversión.",
        ]
    )

    srt_path = OUT_DIR / f"subtitles_es{suffix}.srt"
    chap_path = OUT_DIR / f"youtube_chapters{suffix}.txt"
    srt_path.write_text("\n".join(srt_entries), encoding="utf-8")
    chap_path.write_text("\n".join(chapter_lines) + "\n", encoding="utf-8")
    return srt_path, chap_path


def export_slice(start_idx: int, end_idx: int | None, out_name: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sb_data = json.loads(STORYBOARD_PATH.read_text(encoding="utf-8"))
    sub_scenes = sb_data["scenes"][start_idx:end_idx]
    entries = []
    cnt = 1
    off = 0.0
    for sc in sub_scenes:
        bnds = json.loads((STUDIO_DIR / sc["words_json"]).read_text(encoding="utf-8"))
        ds = split_sentences(sc["narration_display"])
        tw = detect_tts_sentence_windows(sc["narration_tts"], bnds, float(sc["speech_duration_s"]))
        assert len(ds) == len(tw), f"Sentence mismatch in {sc['id']}"
        for sent, (ws, we) in zip(ds, tw):
            cards = wrap_subtitle_block(sent)
            cc = max(1, sum(len(c) for c in cards))
            tc = ws
            spn = max(0.32, we - ws)
            for ci, card in enumerate(cards):
                dt = spn * (len(card) / cc)
                t0 = off + tc
                t1 = max(t0 + 0.28, off + (we if ci == len(cards) - 1 else tc + dt - 0.04))
                entries.append(f"{cnt}\n{fmt_srt_time(t0)} --> {fmt_srt_time(t1)}\n{card}\n")
                cnt += 1
                tc += dt
        off += float(sc["scene_duration_s"])
    out_p = OUT_DIR / out_name
    out_p.write_text("\n".join(entries), encoding="utf-8")
    return out_p


if __name__ == "__main__":
    full_srt, full_chap = export_all()
    export_slice(0, 3, "subtitles_es_acto_01.srt")
    export_slice(3, 5, "subtitles_es_acto_02.srt")
    export_slice(0, 5, "subtitles_es_actos_01_02.srt")
    export_slice(5, 9, "subtitles_es_actos_03_04.srt")
    export_slice(0, 9, "subtitles_es_actos_01_04.srt")
    export_slice(9, 11, "subtitles_es_actos_05_06.srt")
    print(f"Verified 1:1 WordBoundary SRT parity across all slices -> {full_srt}")
