"""Shared paths and constants."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SOURCES_FILE = ROOT / "sources.yaml"
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "news.duckdb"
SITE_DIR = ROOT / "site"
TEMPLATES_DIR = ROOT / "templates"

# Polite HTTP defaults. hnrss + most blogs are happy with a real UA and a
# reasonable timeout; we never hammer them (30-60 min cadence).
USER_AGENT = "ai-news-aggregator/0.1 (+https://github.com/tkthomas27/ai-news-aggregator)"
HTTP_TIMEOUT = 20  # seconds

# How many items to render on the site (keeps the page snappy; full history
# still lives in the DB).
SITE_MAX_ITEMS = 400
