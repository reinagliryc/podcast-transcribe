"""End-to-end CLI tests with the Groq API mocked out (no network, no cost)."""

import os
import shutil
import subprocess

import pytest

from podcast_transcribe import audio, cli, groq

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")


@pytest.fixture
def sample(tmp_path):
    path = tmp_path / "sample.wav"
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi",
                    "-i", "sine=frequency=440:duration=9", str(path)], check=True)
    return path


@pytest.fixture
def fake_groq(monkeypatch):
    calls = []

    def fake(path, **kwargs):
        calls.append(path.name)
        return {"text": f"part {len(calls)}", "language": "english", "duration": 3.0,
                "segments": [{"start": 0.5, "end": 1.0, "text": f" part {len(calls)}"}]}

    monkeypatch.setattr(groq, "transcribe", fake)
    monkeypatch.setenv("GROQ_API_KEY", "dummy")
    return calls


def test_chunked_transcription_and_cache(sample, tmp_path, fake_groq, monkeypatch, capsys):
    monkeypatch.setattr(audio, "MAX_UPLOAD_BYTES", 1)  # force splitting
    monkeypatch.setattr(audio, "CHUNK_SECONDS", 3)
    args = [str(sample), "-q", "-f", "srt", "--cache-dir", str(tmp_path / "cache")]

    assert cli.main(args) == 0
    out = capsys.readouterr().out
    assert len(fake_groq) >= 3
    # second chunk's segment is shifted by the first chunk's real duration (~3 s)
    assert "00:00:03," in out and "part 2" in out
    assert sample.exists(), "the user's own file must never be deleted"

    n = len(fake_groq)
    assert cli.main(args) == 0
    assert len(fake_groq) == n, "second run must come from the cache"


def test_missing_file_is_an_error(tmp_path, capsys):
    assert cli.main([str(tmp_path / "nope.mp3")]) == 1
    assert "error" in capsys.readouterr().err


def test_child_env_has_no_groq_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "secret")
    monkeypatch.setenv("GROQ_API_KEY_FILE", "/x")
    env = audio.child_env()
    assert not any(k.startswith("GROQ_") for k in env)
    assert "PATH" in env


FAKE_YTDLP = """#!/bin/sh
# Fake yt-dlp: write a file at the -o template, print the title, dump env.
while [ $# -gt 0 ]; do
  case "$1" in -o) out="$2"; shift;; esac; shift
done
f=$(echo "$out" | sed 's/%(ext)s/webm/')
echo fake > "$f"
env > "$(dirname "$f")/env.txt"
echo "Ma vidéo : épisode 1"
"""


def test_ytdlp_title_and_env(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "yt-dlp").write_text(FAKE_YTDLP)
    (bindir / "yt-dlp").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")
    monkeypatch.setenv("GROQ_API_KEY", "secret")

    entry = tmp_path / "entry"
    path = cli.ytdlp_download("https://example.com/watch?v=x", entry)
    assert path.name == "source.webm"
    assert (entry / "title.txt").read_text(encoding="utf-8") == "Ma vidéo : épisode 1"
    assert "secret" not in (entry / "env.txt").read_text(), "yt-dlp must not see the key"
