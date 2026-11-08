from podcast_transcribe.formats import merge, to_srt, to_text, to_vtt


def resp(text, segs, duration):
    return {"text": text, "language": "french", "duration": duration,
            "segments": [{"start": a, "end": b, "text": t} for a, b, t in segs]}


def test_merge_shifts_timestamps():
    t = merge([
        (resp(" Bonjour.", [(0.0, 1.5, " Bonjour.")], 1800.2), 0.0),
        (resp(" Au revoir.", [(0.5, 2.0, " Au revoir.")], 600.0), 1800.2),
    ])
    assert t["text"] == "Bonjour.\nAu revoir."
    assert t["segments"][1] == {"start": 1800.7, "end": 1802.2, "text": "Au revoir."}
    assert t["duration"] == 2400.2
    assert t["language"] == "french"


def test_srt_and_vtt():
    t = merge([(resp("Hi", [(3661.5, 3662.25, " Hi")], 3663), 0.0)])
    assert to_srt(t) == "1\n01:01:01,500 --> 01:01:02,250\nHi\n"
    assert to_vtt(t) == "WEBVTT\n\n01:01:01.500 --> 01:01:02.250\nHi\n"
    assert to_text(t) == "Hi\n"
