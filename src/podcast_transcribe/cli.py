"""Command-line entry point."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import httpx

from . import __version__, audio, formats, groq
from .feed import looks_like_feed, parse_feed, select_episode

USER_AGENT = f"podcast-transcribe/{__version__}"
AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac", ".mp4", ".webm", ".mpga"}

quiet = False


def log(msg: str) -> None:
    if not quiet:
        print(msg, file=sys.stderr)


def default_cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "podcast-transcribe"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(1 << 20):
            h.update(block)
    return h.hexdigest()[:16]


def is_audio_response(content_type: str, url: str) -> bool:
    ct = content_type.split(";")[0].strip().lower()
    if ct.startswith(("audio/", "video/")):
        return True
    return Path(urlparse(url).path).suffix.lower() in AUDIO_EXTS and ct in ("", "application/octet-stream", "binary/octet-stream")


def download(url: str, dest_dir: Path) -> Path:
    existing = [p for p in dest_dir.glob("source.*") if not p.name.endswith(".part")]
    if existing:
        log(f"Using cached download: {existing[0]}")
        return existing[0]
    dest_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(urlparse(url).path).suffix.lower()
    dest = dest_dir / f"source{ext if ext in AUDIO_EXTS else '.audio'}"
    part = dest.with_name(dest.name + ".part")
    log(f"Downloading {url}")
    with httpx.stream("GET", url, follow_redirects=True, timeout=60,
                      headers={"User-Agent": USER_AGENT}) as r:
        r.raise_for_status()
        with part.open("wb") as f:
            for block in r.iter_bytes(1 << 16):
                f.write(block)
    part.rename(dest)
    log(f"  {dest.stat().st_size / 1e6:.1f} MB")
    return dest


def ytdlp_download(url: str, dest_dir: Path) -> Path:
    existing = [p for p in dest_dir.glob("source.*") if not p.name.endswith(".part")]
    if existing:
        log(f"Using cached download: {existing[0]}")
        return existing[0]
    exe = shutil.which("yt-dlp")
    if not exe:
        raise RuntimeError(f"{url} is not an audio file or RSS feed; install yt-dlp to handle web pages")
    dest_dir.mkdir(parents=True, exist_ok=True)
    log(f"Fetching audio with yt-dlp: {url}")
    subprocess.run(
        [exe, "--no-playlist", "-f", "bestaudio/best", "-q", "--no-warnings",
         "-o", str(dest_dir / "source.%(ext)s"), url],
        check=True,
    )
    found = [p for p in dest_dir.glob("source.*") if not p.name.endswith(".part")]
    if not found:
        raise RuntimeError("yt-dlp did not produce an audio file")
    return found[0]


def resolve(args: argparse.Namespace, cache: Path) -> tuple[Callable[[], Path], Path, str] | None:
    """Return (fetch audio callable, cache entry dir, title). None when only listing.
    Downloading is deferred so a cached transcript avoids it entirely."""
    src = args.source
    local = Path(src).expanduser()
    if local.exists():
        if args.list:
            raise RuntimeError("--list needs an RSS feed URL")
        return (lambda: local), cache / file_sha(local), local.stem

    if urlparse(src).scheme not in ("http", "https"):
        raise RuntimeError(f"{src}: no such file, and not an http(s) URL")

    with httpx.stream("GET", src, follow_redirects=True, timeout=60,
                      headers={"User-Agent": USER_AGENT}) as r:
        r.raise_for_status()
        content_type = r.headers.get("content-type", "")
        final_url = str(r.url)
        if is_audio_response(content_type, final_url):
            body = None
        else:
            body = r.read()

    if body is not None and looks_like_feed(content_type, body[:512]):
        episodes = parse_feed(body)
        if args.list:
            for i, ep in enumerate(episodes, 1):
                print(f"{i}\t{ep.pub_date}\t{ep.duration}\t{ep.title}")
            return None
        ep = select_episode(episodes, args.episode)
        log(f"Episode: {ep.title} ({ep.pub_date})")
        entry = cache / sha(ep.audio_url)
        return (lambda: download(ep.audio_url, entry)), entry, ep.title

    if args.list or args.episode:
        raise RuntimeError("--list/--episode need an RSS feed URL")
    entry = cache / sha(src)
    if body is None:
        return (lambda: download(final_url, entry)), entry, Path(urlparse(final_url).path).stem
    return (lambda: ytdlp_download(src, entry)), entry, src


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="podcast-transcribe",
        description="Transcribe a podcast episode with Whisper on Groq. "
                    "SOURCE can be a local audio file, a direct audio URL, an RSS feed "
                    "(latest episode by default) or any page yt-dlp understands.",
    )
    p.add_argument("source", help="audio file, audio URL, RSS feed URL or web page")
    p.add_argument("-e", "--episode", help="feed episode: N = Nth most recent (1 = latest), or a title substring")
    p.add_argument("--list", action="store_true", help="list feed episodes and exit")
    p.add_argument("-l", "--language", help="ISO-639-1 code, e.g. fr or en (default: auto-detect)")
    p.add_argument("-f", "--format", choices=sorted(formats.RENDERERS), default="text", help="output format (default: text)")
    p.add_argument("-o", "--output", type=Path, help="write to this file instead of stdout")
    p.add_argument("-m", "--model", default=groq.DEFAULT_MODEL, help=f"Groq model (default: {groq.DEFAULT_MODEL})")
    p.add_argument("-p", "--prompt", help="context or spellings to guide Whisper (names, jargon)")
    p.add_argument("--api-key", help="Groq API key (default: $GROQ_API_KEY, then `llm keys get groq`)")
    p.add_argument("--cache-dir", type=Path, default=default_cache_dir(), help="where downloads and transcripts are cached")
    p.add_argument("--no-cache", action="store_true", help="ignore any cached transcript")
    p.add_argument("--keep-audio", action="store_true", help="keep downloaded audio in the cache after transcribing")
    p.add_argument("-q", "--quiet", action="store_true", help="no progress messages on stderr")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def run(args: argparse.Namespace) -> int:
    global quiet
    quiet = args.quiet
    resolved = resolve(args, args.cache_dir)
    if resolved is None:
        return 0
    fetch, entry, title = resolved
    entry.mkdir(parents=True, exist_ok=True)

    cached = entry / f"transcript-{args.model}-{args.language or 'auto'}.json"
    if cached.exists() and not args.no_cache:
        log(f"Using cached transcript: {cached}")
        transcript = json.loads(cached.read_text())
    else:
        api_key = groq.find_api_key(args.api_key)
        source = fetch()
        log("Compressing audio (16 kHz mono)...")
        small = audio.compress(source, entry / "audio.mp3")
        chunks = audio.split(small, entry / "chunks")
        parts = []
        for i, (chunk, offset) in enumerate(chunks, 1):
            label = f" chunk {i}/{len(chunks)}" if len(chunks) > 1 else ""
            log(f"Transcribing{label} with {args.model}...")
            parts.append((groq.transcribe(chunk, api_key=api_key, model=args.model,
                                          language=args.language, prompt=args.prompt), offset))
        transcript = formats.merge(parts)
        transcript["title"] = title
        transcript["model"] = args.model
        cached.write_text(json.dumps(transcript, ensure_ascii=False))
        shutil.rmtree(entry / "chunks", ignore_errors=True)
        if not args.keep_audio:
            for f in entry.glob("source.*"):
                if f.resolve() != Path(args.source).expanduser().resolve():
                    f.unlink()
            (entry / "audio.mp3").unlink(missing_ok=True)

    out = formats.RENDERERS[args.format](transcript)
    if args.output:
        args.output.write_text(out, encoding="utf-8")
        log(f"Wrote {args.output}")
    else:
        sys.stdout.write(out)
        sys.stdout.flush()  # surface BrokenPipeError here, not at interpreter exit
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        # Downstream closed early (e.g. `| head`): exit quietly, as Unix tools do.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 141
    except (RuntimeError, ValueError, httpx.HTTPError, subprocess.CalledProcessError) as e:
        print(f"podcast-transcribe: error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
