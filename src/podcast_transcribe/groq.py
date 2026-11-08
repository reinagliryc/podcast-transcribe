"""Groq Whisper API client and API key lookup."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx

API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
DEFAULT_MODEL = "whisper-large-v3-turbo"


def llm_keys_path() -> Path:
    """Where Simon Willison's `llm` CLI stores its keys."""
    if base := os.environ.get("LLM_USER_PATH"):
        return Path(base) / "keys.json"
    config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    if sys.platform == "darwin":
        config = Path.home() / "Library" / "Application Support"
    return config / "io.datasette.llm" / "keys.json"


def find_api_key(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    if key := os.environ.get("GROQ_API_KEY"):
        return key
    path = llm_keys_path()
    try:
        if key := json.loads(path.read_text()).get("groq"):
            return key
    except (OSError, ValueError):
        pass
    raise RuntimeError(
        "no Groq API key: set GROQ_API_KEY, pass --api-key, or run `llm keys set groq`"
    )


def transcribe(
    path: Path,
    *,
    api_key: str,
    model: str = DEFAULT_MODEL,
    language: str | None = None,
    prompt: str | None = None,
    retries: int = 5,
) -> dict:
    """Transcribe one file (<= 25 MB) and return Groq's verbose_json response."""
    data = {"model": model, "response_format": "verbose_json", "temperature": "0"}
    if language:
        data["language"] = language
    if prompt:
        data["prompt"] = prompt
    headers = {"Authorization": f"Bearer {api_key}"}

    for attempt in range(retries + 1):
        with path.open("rb") as f:
            files = {"file": (path.name, f, "audio/mpeg")}
            try:
                r = httpx.post(API_URL, headers=headers, data=data, files=files, timeout=600)
            except httpx.TransportError as e:
                if attempt == retries:
                    raise
                wait = 2**attempt
                print(f"  network error ({e}), retrying in {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
        if r.status_code == 429 or r.status_code >= 500:
            if attempt == retries:
                break
            wait = float(r.headers.get("retry-after") or 2**attempt)
            print(f"  Groq returned {r.status_code}, retrying in {wait:.0f}s", file=sys.stderr)
            time.sleep(wait)
            continue
        break
    if r.status_code != 200:
        try:
            msg = r.json()["error"]["message"]
        except (ValueError, KeyError, TypeError):
            msg = r.text[:500]
        raise RuntimeError(f"Groq API error {r.status_code}: {msg}")
    return r.json()
