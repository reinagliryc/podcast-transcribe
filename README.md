# podcast-transcribe

Transcribe a podcast episode with Whisper (`whisper-large-v3-turbo`) on [Groq](https://console.groq.com/docs/speech-to-text),
and print the text to stdout so it can be piped into a summarizer or any other script.

```sh
podcast-transcribe https://feeds.example.com/show.xml -l fr | llm "Summarize this podcast episode"
```

## Features

- **Any source**: a local audio file, a direct audio URL, an RSS feed (latest episode by default),
  or any page [yt-dlp](https://github.com/yt-dlp/yt-dlp) understands (Apple Podcasts, YouTube, …).
- **Long episodes**: audio is re-encoded to 16 kHz mono at 32 kbit/s (Whisper's native rate, so no
  accuracy loss). About 1h40 fits under Groq's 25 MB upload limit; longer audio is split into
  30-minute chunks and timestamps are stitched back together.
- **Output formats**: plain text, JSON (with timestamped segments), SRT, WebVTT.
- **Cache**: transcripts are cached in `~/.cache/podcast-transcribe`, so re-running costs nothing.
- **Cheap**: `whisper-large-v3-turbo` costs about $0.04 per hour of audio on Groq.

## Install

Requires Python ≥ 3.10 and `ffmpeg` (plus `yt-dlp` for web pages).

```sh
uv tool install git+https://github.com/reinagliryc/podcast-transcribe
# or: pipx install git+https://github.com/reinagliryc/podcast-transcribe
```

## API key

Get a key at <https://console.groq.com/keys>. The first match wins:

1. `--api-key KEY` (avoid it: command lines are visible to other users via `ps`)
2. `--api-key-file PATH`
3. the `GROQ_API_KEY` environment variable
4. the `GROQ_API_KEY_FILE` environment variable (path to a file holding the key)
5. `$CREDENTIALS_DIRECTORY/groq`, i.e. systemd's `LoadCredential=groq:/path/to/key`
6. the key store of Simon Willison's [`llm`](https://llm.datasette.io/) (`llm keys set groq`)

Prefer a file (`chmod 600`) to an environment variable. In any case the key is removed from the
environment of `ffmpeg` and `yt-dlp`, which never need it.

## Usage

```sh
# Latest episode of a feed, in French
podcast-transcribe https://feeds.example.com/show.xml -l fr > episode.txt

# List a feed's episodes, then pick one by number (1 = latest) or title substring
podcast-transcribe https://feeds.example.com/show.xml --list
podcast-transcribe https://feeds.example.com/show.xml -e 3
podcast-transcribe https://feeds.example.com/show.xml -e "interview"

# Local file to subtitles
podcast-transcribe interview.m4a -f srt -o interview.srt

# Help Whisper with names and jargon
podcast-transcribe episode.mp3 -l fr -p "Anthony Berthou, micronutrition, oméga-3"
```

Progress messages go to stderr (`-q` silences them); the exit status is non-zero on error.
Run `podcast-transcribe --help` for every option.

### From Python

```python
import subprocess
text = subprocess.run(["podcast-transcribe", url, "-l", "fr", "-q"],
                      capture_output=True, text=True, check=True).stdout
```

### As a hardened systemd service

The tool downloads and decodes untrusted media (ffmpeg) and visits arbitrary web pages (yt-dlp).
For unattended jobs, run it sandboxed and hand it the key as a systemd credential, so it never
appears in the environment, the process list or the Nix store. NixOS example:

```nix
systemd.services.podcast-digest = {
  path = [ podcast-transcribe ];
  script = ''
    podcast-transcribe https://feeds.example.com/show.xml -l fr -q -o "$STATE_DIRECTORY/latest.txt"
  '';
  environment.XDG_CACHE_HOME = "/var/cache/podcast-digest";
  serviceConfig = {
    LoadCredential = "groq:/var/lib/secrets/groq.key";  # root-only file, read by systemd
    DynamicUser = true;
    StateDirectory = "podcast-digest";
    CacheDirectory = "podcast-digest";
    ProtectSystem = "strict";
    ProtectHome = true;
    PrivateTmp = true;
    PrivateDevices = true;
    NoNewPrivileges = true;
  };
};
```

## Security notes

- The key is sent only to `https://api.groq.com` and is never logged or cached.
- Cached files under `~/.cache/podcast-transcribe` contain transcripts, never the key.
- Audio from untrusted sources is parsed by ffmpeg, which has a history of vulnerabilities on
  crafted files: sandbox unattended runs as shown above.

## Speaker diarization

Not supported: Groq's Whisper API does not identify speakers. For summaries this rarely matters, since an LLM
infers host and guest from context. If you need speaker labels, look at
[WhisperX](https://github.com/m-bain/whisperX) (local, pyannote) or a hosted service such as AssemblyAI or Deepgram.

## Development

```sh
uv run --group dev pytest
```

## License

MIT
