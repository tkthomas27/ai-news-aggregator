# AI News Aggregator

Personal AI-news aggregator: pulls items from a curated set of AI sources (blogs,
Hacker News, optionally X/Twitter) into a DuckDB/parquet store and publishes a
simple static website that displays them in one place.

Read-only public page, no accounts, no personalization. Primary users: Kyle + a
few friends.

## Status

Spec'd, not yet implemented. Full requirements: [docs/spec.md](docs/spec.md).

## Planned architecture

- **Ingest** — `feedparser` pulls RSS/Atom + Hacker News (via hnrss.org) on a
  30–60 min cadence; each source wrapped in its own try/except so one dead feed
  can't fail the run.
- **Store** — DuckDB/parquet (`sources` + `items` tables). Dedup on a hash of the
  canonical link.
- **Publish** — static-generate the page from DuckDB at build time; no live
  backend.
- **Automate** — GitHub Actions on a `schedule` trigger: fetch → update data →
  rebuild → commit → push. Data committed to the repo ("git scraping" pattern).
- **Host** — GitHub Pages via `actions/deploy-pages`.

## Open decisions

See [§9 of the spec](docs/spec.md) — final source list, static vs. backend
(→ static), hosting target (→ GitHub Pages), persistence pattern (→ commit-to-repo),
and whether X/Twitter ships in v1 (→ defer to Phase 2).
