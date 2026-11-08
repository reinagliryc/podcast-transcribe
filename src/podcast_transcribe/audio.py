"""Audio preparation with ffmpeg: downmix, resample, compress, split."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

# Whisper works on 16 kHz mono internally, so this loses nothing useful.
# At 32 kbit/s, one hour is ~14 MB: ~1h40 fits under Groq's 25 MB upload limit.
BITRATE = "32k"
MAX_UPLOAD_BYTES = 24 * 1024 * 1024
CHUNK_SECONDS = 30 * 60


def child_env() -> dict[str, str]:
    """Environment for external tools (ffmpeg, yt-dlp): without the Groq key,
    which they never need. They process untrusted media and web pages."""
    return {k: v for k, v in os.environ.items() if not k.startswith("GROQ_")}


def require(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        raise RuntimeError(f"{tool} not found in PATH; please install it")
    return path


def compress(src: Path, dst: Path) -> Path:
    if dst.exists():
        return dst
    tmp = dst.with_suffix(".part.mp3")
    subprocess.run(
        [require("ffmpeg"), "-nostdin", "-y", "-loglevel", "error", "-i", str(src),
         "-vn", "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", BITRATE, str(tmp)],
        check=True, env=child_env(),
    )
    tmp.rename(dst)
    return dst


def duration(path: Path) -> float:
    out = subprocess.run(
        [require("ffprobe"), "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True, env=child_env(),
    ).stdout.strip()
    return float(out)


def split(path: Path, workdir: Path) -> list[tuple[Path, float]]:
    """Return [(chunk, start_offset_seconds)]. A single chunk if the file is small enough."""
    if path.stat().st_size <= MAX_UPLOAD_BYTES:
        return [(path, 0.0)]
    workdir.mkdir(parents=True, exist_ok=True)
    for old in workdir.glob("chunk_*.mp3"):
        old.unlink()
    subprocess.run(
        [require("ffmpeg"), "-nostdin", "-y", "-loglevel", "error", "-i", str(path),
         "-f", "segment", "-segment_time", str(CHUNK_SECONDS), "-c", "copy",
         str(workdir / "chunk_%03d.mp3")],
        check=True, env=child_env(),
    )
    chunks, offset = [], 0.0
    for chunk in sorted(workdir.glob("chunk_*.mp3")):
        chunks.append((chunk, offset))
        offset += duration(chunk)
    return chunks
