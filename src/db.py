"""DuckDB access layer + schema.

The DB file is committed to the repo ("git scraping" pattern) so dedup state
survives across ephemeral CI runs.
"""
from __future__ import annotations

import duckdb

from .config import DATA_DIR, DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id            TEXT PRIMARY KEY,
    name          TEXT,
    homepage_url  TEXT,
    feed_url      TEXT,
    source_type   TEXT,
    active        BOOLEAN,
    last_fetched  TIMESTAMP
);

CREATE TABLE IF NOT EXISTS items (
    id            TEXT PRIMARY KEY,   -- hash of canonical link
    source_id     TEXT,
    title         TEXT,
    link          TEXT,
    published_at  TIMESTAMP,
    fetched_at    TIMESTAMP,
    summary       TEXT,
    raw           JSON
);
"""


def connect() -> duckdb.DuckDBPyConnection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    con.execute(SCHEMA)
    return con
