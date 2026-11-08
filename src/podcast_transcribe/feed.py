"""Minimal RSS podcast feed parsing."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"


@dataclass
class Episode:
    title: str
    audio_url: str
    pub_date: str = ""
    duration: str = ""


def looks_like_feed(content_type: str, head: bytes) -> bool:
    if any(t in content_type for t in ("rss", "xml", "atom")):
        return True
    start = head.lstrip()[:200].lower()
    return start.startswith(b"<?xml") or start.startswith(b"<rss")


def parse_feed(xml_bytes: bytes) -> list[Episode]:
    """Return episodes with an audio enclosure, in feed order (usually newest first)."""
    root = ET.fromstring(xml_bytes)
    episodes = []
    for item in root.iter("item"):
        enc = item.find("enclosure")
        url = enc.get("url", "") if enc is not None else ""
        if not url:
            continue
        episodes.append(
            Episode(
                title=(item.findtext("title") or "").strip(),
                audio_url=url,
                pub_date=(item.findtext("pubDate") or "").strip(),
                duration=(item.findtext(f"{ITUNES}duration") or "").strip(),
            )
        )
    return episodes


def select_episode(episodes: list[Episode], selector: str | None) -> Episode:
    """Pick an episode: None -> latest, an integer N -> Nth most recent (1-based),
    anything else -> first episode whose title contains it (case-insensitive)."""
    if not episodes:
        raise ValueError("feed contains no episode with an audio enclosure")
    if selector is None:
        return episodes[0]
    if selector.isdigit():
        n = int(selector)
        if not 1 <= n <= len(episodes):
            raise ValueError(f"episode {n} out of range (feed has {len(episodes)})")
        return episodes[n - 1]
    needle = selector.casefold()
    for ep in episodes:
        if needle in ep.title.casefold():
            return ep
    raise ValueError(f"no episode title matches {selector!r}")
