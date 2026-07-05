"""Feed autodiscovery.

Given a homepage URL, find its RSS/Atom feed by:
  1. parsing <link rel="alternate" type="application/rss+xml|atom+xml"> tags,
  2. falling back to common paths (/feed, /rss, /feed.xml, /atom.xml, ...),
  3. verifying each candidate actually parses as a feed with entries.

Keeping this out of the config means a blog migrating platforms degrades to
"discovery re-resolves the URL" rather than "someone edits a hardcoded path."
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import feedparser
import requests

from .config import HTTP_TIMEOUT, USER_AGENT

FEED_TYPES = ("application/rss+xml", "application/atom+xml", "application/feed+json")
COMMON_PATHS = ("/feed", "/rss", "/feed.xml", "/rss.xml", "/atom.xml", "/index.xml", "/feed/")


class _FeedLinkParser(HTMLParser):
    """Collect href values from <link rel=alternate type=feed> tags in <head>."""

    def __init__(self) -> None:
        super().__init__()
        self.feeds: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "link":
            return
        a = {k.lower(): (v or "") for k, v in attrs}
        rel = a.get("rel", "").lower()
        typ = a.get("type", "").lower()
        href = a.get("href", "")
        if href and typ in FEED_TYPES and ("alternate" in rel or not rel):
            self.feeds.append(href)


def _get(url: str) -> requests.Response:
    return requests.get(
        url, timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT}, allow_redirects=True
    )


def looks_like_feed(url: str) -> bool:
    """True if the URL parses as a feed that has at least one entry."""
    try:
        parsed = feedparser.parse(url, agent=USER_AGENT)
    except Exception:
        return False
    return bool(parsed.entries) and not (parsed.bozo and not parsed.entries)


def discover_feed(homepage_url: str) -> str | None:
    """Return a working feed URL for a homepage, or None if none found."""
    try:
        resp = _get(homepage_url)
    except requests.RequestException:
        resp = None

    candidates: list[str] = []

    if resp is not None and resp.ok and resp.text:
        parser = _FeedLinkParser()
        try:
            parser.feed(resp.text)
        except Exception:
            pass
        for href in parser.feeds:
            candidates.append(urljoin(resp.url, href))

    # Fallback: common conventional paths off the site root.
    base = f"{urlparse(homepage_url).scheme}://{urlparse(homepage_url).netloc}"
    for path in COMMON_PATHS:
        candidates.append(urljoin(base + "/", path.lstrip("/")))
        candidates.append(urljoin(homepage_url.rstrip("/") + "/", path.lstrip("/")))

    seen: set[str] = set()
    for cand in candidates:
        cand = re.sub(r"#.*$", "", cand)
        if cand in seen:
            continue
        seen.add(cand)
        if looks_like_feed(cand):
            return cand
    return None
