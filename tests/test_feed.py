import pytest

from podcast_transcribe.feed import looks_like_feed, parse_feed, select_episode

FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
<channel>
  <title>Test</title>
  <item><title>Episode 3 : La suite</title><pubDate>Wed, 03 Jan 2024</pubDate>
    <itunes:duration>01:02:03</itunes:duration>
    <enclosure url="https://example.com/3.mp3" type="audio/mpeg"/></item>
  <item><title>No audio here</title></item>
  <item><title>Episode 2</title><enclosure url="https://example.com/2.mp3" type="audio/mpeg"/></item>
  <item><title>Episode 1 - Pilot</title><enclosure url="https://example.com/1.mp3" type="audio/mpeg"/></item>
</channel></rss>"""


def test_parse_feed_skips_items_without_audio():
    eps = parse_feed(FEED)
    assert [e.audio_url for e in eps] == [
        "https://example.com/3.mp3", "https://example.com/2.mp3", "https://example.com/1.mp3"]
    assert eps[0].duration == "01:02:03"
    assert eps[0].title == "Episode 3 : La suite"


def test_select_episode():
    eps = parse_feed(FEED)
    assert select_episode(eps, None).title.startswith("Episode 3")
    assert select_episode(eps, "2").title == "Episode 2"
    assert select_episode(eps, "pilot").title == "Episode 1 - Pilot"
    with pytest.raises(ValueError):
        select_episode(eps, "9")
    with pytest.raises(ValueError):
        select_episode(eps, "nope")
    with pytest.raises(ValueError):
        select_episode([], None)


def test_looks_like_feed():
    assert looks_like_feed("application/rss+xml", b"")
    assert looks_like_feed("text/plain", b"  <?xml version='1.0'?><rss>")
    assert not looks_like_feed("text/html", b"<!doctype html><html>")
