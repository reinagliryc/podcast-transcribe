"""Merge chunk transcriptions and render them as text, JSON, SRT or WebVTT."""

from __future__ import annotations

import json


def merge(parts: list[tuple[dict, float]]) -> dict:
    """Combine verbose_json responses from consecutive chunks, shifting timestamps."""
    segments, texts, language, total = [], [], None, 0.0
    for resp, offset in parts:
        language = language or resp.get("language")
        texts.append((resp.get("text") or "").strip())
        for seg in resp.get("segments") or []:
            segments.append({
                "start": round(seg["start"] + offset, 3),
                "end": round(seg["end"] + offset, 3),
                "text": seg["text"].strip(),
            })
        total = max(total, offset + float(resp.get("duration") or 0))
    return {
        "language": language,
        "duration": round(total, 3),
        "text": "\n".join(t for t in texts if t),
        "segments": segments,
    }


def _ts(seconds: float, sep: str) -> str:
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def to_text(t: dict) -> str:
    return t["text"] + "\n"


def to_json(t: dict) -> str:
    return json.dumps(t, ensure_ascii=False, indent=2) + "\n"


def to_srt(t: dict) -> str:
    blocks = [
        f"{i}\n{_ts(s['start'], ',')} --> {_ts(s['end'], ',')}\n{s['text']}\n"
        for i, s in enumerate(t["segments"], 1)
    ]
    return "\n".join(blocks)


def to_vtt(t: dict) -> str:
    blocks = [
        f"{_ts(s['start'], '.')} --> {_ts(s['end'], '.')}\n{s['text']}\n"
        for s in t["segments"]
    ]
    return "WEBVTT\n\n" + "\n".join(blocks)


RENDERERS = {"text": to_text, "json": to_json, "srt": to_srt, "vtt": to_vtt}
