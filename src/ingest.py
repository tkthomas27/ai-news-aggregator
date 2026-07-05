"""Ingestion pipeline: fetch feeds -> normalize -> upsert into DuckDB.

Run:  python -m src.ingest
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from time import mktime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import feedparser
import yaml

from .config import SOURCES_FILE, USER_AGENT
from .db import connect
from .discover import discover_feed

# Tracking params stripped before hashing/storing the canonical link.
TRACKING_PREFIXES = ("utm_",)
TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src", "source"}


def canonical_link(url: str) -> str:
    """Strip UTM/tracking params so the same story hashes to one id."""
    if not url:
        return url
    parts = urlparse(url)
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith(TRACKING_PREFIXES) and k.lower() not in TRACKING_KEYS
    ]
    cleaned = parts._replace(query=urlencode(query), fragment="")
    return urlunparse(cleaned)


def item_id(link: str) -> str:
    return hashlib.sha256(canonical_link(link).encode("utf-8")).hexdigest()[:32]


def _entry_published(entry) -> datetime:
    for attr in ("published_parsed", "updated_parsed"):
        t = entry.get(attr)
        if t:
            return datetime.fromtimestamp(mktime(t), tz=timezone.utc)
    return datetime.now(timezone.utc)


def _entry_summary(entry) -> str:
    text = entry.get("summary", "") or ""
    # feedparser gives HTML; strip tags crudely for a plain excerpt.
    import re

    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:600]


def load_sources() -> list[dict]:
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["sources"]


def resolve_feed_url(con, src: dict) -> str | None:
    """Return a feed URL, using the config value, the DB cache, or discovery."""
    if src.get("feed_url"):
        return src["feed_url"]
    cached = con.execute(
        "SELECT feed_url FROM sources WHERE id = ?", [src["id"]]
    ).fetchone()
    if cached and cached[0]:
        return cached[0]
    print(f"  discovering feed for {src['id']} ({src['homepage_url']}) ...")
    found = discover_feed(src["homepage_url"])
    if found:
        print(f"  -> {found}")
    else:
        print(f"  !! no feed found for {src['id']}")
    return found


def upsert_source(con, src: dict, feed_url: str | None, last_fetched: datetime) -> None:
    con.execute(
        """
        INSERT INTO sources (id, name, homepage_url, feed_url, source_type, active, last_fetched)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (id) DO UPDATE SET
            name = excluded.name,
            homepage_url = excluded.homepage_url,
            feed_url = excluded.feed_url,
            source_type = excluded.source_type,
            active = excluded.active,
            last_fetched = excluded.last_fetched
        """,
        [
            src["id"],
            src.get("name", src["id"]),
            src.get("homepage_url"),
            feed_url,
            src.get("type", "rss"),
            bool(src.get("active", True)),
            last_fetched,
        ],
    )


def upsert_items(con, source_id: str, entries) -> int:
    """Insert only new items (by canonical-link hash). Returns # inserted."""
    fetched_at = datetime.now(timezone.utc)
    inserted = 0
    for entry in entries:
        link = entry.get("link") or ""
        if not link:
            continue
        iid = item_id(link)
        row = con.execute("SELECT 1 FROM items WHERE id = ?", [iid]).fetchone()
        if row:
            continue
        con.execute(
            """
            INSERT INTO items
                (id, source_id, title, link, published_at, fetched_at, summary, raw)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                iid,
                source_id,
                (entry.get("title") or "(untitled)").strip(),
                canonical_link(link),
                _entry_published(entry),
                fetched_at,
                _entry_summary(entry),
                json.dumps(
                    {k: entry.get(k) for k in ("title", "link", "author", "id")},
                    default=str,
                ),
            ],
        )
        inserted += 1
    return inserted


def run() -> int:
    sources = load_sources()
    con = connect()
    total_new = 0
    failures = 0

    for src in sources:
        if not src.get("active", True):
            continue
        sid = src["id"]
        try:
            feed_url = resolve_feed_url(con, src)
            now = datetime.now(timezone.utc)
            if not feed_url:
                # Record the source but leave it feed-less; site still works.
                upsert_source(con, src, None, now)
                failures += 1
                continue
            parsed = feedparser.parse(feed_url, agent=USER_AGENT)
            new = upsert_items(con, sid, parsed.entries)
            upsert_source(con, src, feed_url, now)
            total_new += new
            print(f"  {sid:20s} {len(parsed.entries):4d} entries, {new:3d} new")
        except Exception as exc:  # one bad feed must not kill the run
            failures += 1
            print(f"  !! {sid}: {exc}", file=sys.stderr)

    total_items = con.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    con.close()
    print(f"\nDone. {total_new} new items this run, {total_items} total, {failures} source failures.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
