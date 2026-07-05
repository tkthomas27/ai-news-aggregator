# AI News Aggregator — Requirements Spec

**Owner:** Kyle
**Purpose:** Personal AI-news aggregator, published to a public (but unpromoted) website. Primary users: Kyle + a few friends. Hand-off target: Claude Code.

---

## 1. Goal

Pull items from a curated set of AI-relevant sources (blogs, Hacker News, optionally X/Twitter) into a single store, and publish a simple website that displays them in one place. No accounts, no personalization engine — this is a read-only public page, not a product.

---

## 2. Content sources

### 2a. RSS/Atom-native sources (Phase 1)

Build the ingester against a `sources` config (see §3) so adding/removing a blog is a one-line change, not a code change. Suggested starting list:

| Source | Feed | Confidence |
|---|---|---|
| Anthropic News | discover via `<link rel="alternate">` on anthropic.com/news | verify at build time |
| OpenAI News | discover via autodiscovery on openai.com/news | verify at build time |
| Google DeepMind Blog | discover via autodiscovery on deepmind.google/discover/blog | verify at build time |
| Hugging Face Blog | `https://huggingface.co/blog/feed.xml` | verify |
| BAIR Blog | discover via autodiscovery on bair.berkeley.edu/blog | verify |
| Simon Willison's Weblog | discover via autodiscovery on simonwillison.net (he runs multiple feed variants — "everything" feed is what you want, not just blogmarks) | verify |
| Interconnects (Nathan Lambert) | `https://www.interconnects.ai/feed` (standard Substack pattern) | verify |
| Ahead of AI (Sebastian Raschka) | `https://magazine.sebastianraschka.com/feed` (standard Substack pattern) | verify |
| Marginal Revolution | discover via autodiscovery on marginalrevolution.com — site has changed CMS/URL structure over the years, don't hardcode a guessed path | verify |
| Don't Worry About the Vase (Zvi Mowshowitz) | `https://thezvi.substack.com/feed` (standard Substack pattern) | verify |
| Import AI (Jack Clark, Anthropic co-founder) | `https://importai.substack.com/feed` (standard Substack pattern; also mirrors at jack-clark.net) | verify |
| Epoch AI | `https://epochai.substack.com/feed` (standard Substack pattern) | verify |
| AI as Normal Technology (Arvind Narayanan & Sayash Kapoor) | discover via autodiscovery on normaltech.ai — note this is the rebrand of what was previously "AI Snake Oil"; if you find the old name/URL elsewhere it may be stale | verify |
| The Batch (DeepLearning.AI / Andrew Ng) | discover via autodiscovery on deeplearning.ai/the-batch — lower confidence this has a clean native feed; some readers use a mail-to-RSS bridge (e.g. kill-the-newsletter.com) on the email version instead. Verify before committing to this one, substitute if it's not worth the friction | lower confidence |

**Implementation note:** don't hand-code feed URLs from this table into production without a discovery step first. Write a small `discover_feed(url)` helper that fetches the page and looks for `<link type="application/rss+xml">` / `application/atom+xml`, falls back to common paths (`/feed`, `/rss`, `/feed.xml`, `/atom.xml`), and caches the resolved URL in the `sources` table. This makes the pipeline resilient if a blog migrates platforms.

### 2b. Hacker News (Phase 1)

Use **hnrss.org** (third-party RSS bridge over the Algolia HN Search API — well-established, has been running since 2014). Don't use the official `news.ycombinator.com/rss` — it's front-page-only with no filtering.

Recommended: run two feeds and merge/dedupe them —
- `https://hnrss.org/frontpage` — catches anything that reaches the HN front page regardless of topic match
- `https://hnrss.org/newest?q=AI+OR+LLM+OR+"machine+learning"&points=50` — catches AI-specific stories that don't make the front page but still get meaningful engagement

hnrss asks that you keep polling frequency reasonable (it scrapes HN + Algolia under the hood) — every 30–60 min is plenty for a personal feed.

### 2c. X/Twitter accounts (Phase 2 — decision needed before building)

As of Feb 2026, X removed the free API tier for new developers; the default is now pay-per-use ($0.005/post read, $0.010/user read, no monthly minimum). For a handful of accounts checked a few times a day, the actual metered cost is genuinely low — reading ~10 recent posts × 5 accounts × 4x/day ≈ 200 reads/day ≈ 6,000/month ≈ **$30/month**, or less if you poll less often. The friction isn't cost, it's setup: you need a developer account, a payment method on file, and apps flagged as automated/bot-like reportedly get an extra review step.

Third-party resale APIs (TwitterAPI.io, GetXAPI, etc.) are cheaper and skip the review step, but they're unofficial scrapers reselling access — a ToS and reliability gray area I'd avoid for something you're putting a public URL on.

**Recommendation:** ship Phase 1 without X, then decide if it's worth ~$10–30/month + developer account setup for "a few accounts." If yes, treat it as its own `source_type` in the schema below so it slots into the same pipeline rather than becoming a special case.

---

## 3. Data model

Given your existing stack, this stays in DuckDB/parquet.

```
sources
  id            text primary key
  name          text
  homepage_url  text
  feed_url      text          -- resolved via discovery, cached here
  source_type   text          -- 'rss' | 'hn' | 'twitter'
  active        boolean
  last_fetched  timestamp

items
  id            text primary key   -- hash of canonical link
  source_id     text references sources(id)
  title         text
  link          text
  published_at  timestamp
  fetched_at    timestamp
  summary       text          -- excerpt/description from feed, not full content
  raw           json          -- optional, original feed entry for debugging
```

Dedup key: hash of the canonical link (strip UTM/tracking params first). Don't dedupe across sources in Phase 1 (e.g. same story on HN + the original blog) — that's a nice-to-have, not a blocker.

---

## 4. Ingestion pipeline

- **Cadence:** every 30–60 min is fine for a personal project; no need for real-time.
- **Fetch:** `feedparser` (Python) handles RSS/Atom/HN feeds uniformly — no need for separate parsing logic per source type.
- **Normalize:** map each feed entry to the `items` schema above.
- **Upsert:** insert only new items (by dedup key); update `last_fetched` on the source row.
- **Resilience:** one dead/slow feed should not fail the whole run — wrap each source fetch in its own try/except, log failures, continue. A blog changing its feed URL should degrade to "stops showing new items" not "breaks the site."
- **Retention:** keep full history in parquet; no need to prune — volume here is tiny (a few hundred items/week at most).

---

## 5. Website

- Single page, reverse-chronological list of items, newest first.
- Group-by-source toggle vs. unified timeline — pick one as default (unified is simpler to start).
- Filter by source (checkboxes) — cheap to add, meaningfully improves usability with 10+ sources.
- Each item: title (links out to original), source name/logo, published date, excerpt.
- Search box: nice-to-have, not required for v1.
- Mobile-friendly, minimal styling — this is explicitly meant to be simple, resist the urge to over-design it.

**Rendering approach:** static-generate the page from the DuckDB/parquet data at build time (e.g., a Python script that queries DuckDB and renders a template) rather than standing up a live backend. At this scale (few users, low update frequency) a static site regenerated every fetch cycle is simpler to host and has nothing to go down.

---

## 6. Hosting/deployment & scheduling

Two moving pieces: (1) a scheduled job that fetches new items and rebuilds the site, (2) something that serves the resulting static files.

**How the automation actually works, end to end:**
1. A GitHub Actions workflow runs on a `schedule` trigger (cron syntax — e.g. hourly), plus `workflow_dispatch` so it can be triggered manually while testing.
2. The workflow checks out the repo, runs the Python ingestion script (fetch feeds → update DuckDB/parquet → run the static site generator).
3. The workflow commits the updated data + rebuilt HTML and pushes.
4. That push is what triggers the redeploy — GitHub Pages redeploys automatically on push to the configured branch, or (if using Azure Static Web Apps) the Azure-generated workflow fires on push and deploys.

So "GitHub updates it and pushes to the site automatically" is accurate — but the push happens because the *scheduled workflow itself* commits and pushes, not because GitHub does anything on its own initiative. Worth being explicit about this for whoever/whatever builds it.

**Persisting fetched data across runs:** GitHub Actions runners are ephemeral — nothing survives between runs unless it's committed or fetched from somewhere persistent. Two options:

- **Commit data to the repo each run** ("git scraping" — a pattern Simon Willison, already on your source list, popularized for exactly this kind of scheduled-scrape project). Each run appends new items and commits the diff. At this volume (a few hundred items/week) the diffs are trivial and you get a free audit trail of what appeared when. **Recommended** — simplest option, no extra infrastructure.
- **Stateless build**: fetch → build → deploy → discard, nothing committed to git. Cleaner history, but dedup state needs to live somewhere else (a Gist, a small storage bucket) since the runner won't remember what it already saw. More moving parts for no real benefit at this scale.

**Hosting:** since everything's already living in GitHub for the Actions workflow, **GitHub Pages** is probably the lowest-friction choice — no separate account, no cross-service auth, just `actions/deploy-pages` in the same workflow. Azure Static Web Apps and Posit Connect both still work if you'd rather this live next to your other infra, but neither buys you anything over Pages for a single static site like this.

**Caveat:** GitHub's `schedule` trigger only fires on the default branch, and cron jobs can be delayed by several minutes during periods of high platform load — irrelevant for a personal news feed, but worth knowing so a late run doesn't look like a bug.

---

## 7. Non-functional requirements

- No authentication — public URL, not indexed/promoted.
- Free-tier-friendly hosting (see §6).
- Should degrade gracefully with zero maintenance for weeks at a time — a side project that breaks silently and stays broken is worse than one that just quietly keeps working with a stale feed or two.

---

## 8. Explicitly out of scope for v1 (stretch goals)

- Cross-source relevance ranking ("N sources mentioned this today" style surfacing)
- Your own RSS output of the curated aggregate, so you can subscribe to it elsewhere
- Tagging/categorization (research / product / policy / etc.)
- X/Twitter ingestion (§2c — explicit Phase 2 decision)

---

## 9. Open decisions before handing this to Claude Code

1. Final source list — trim/add to the table in §2a.
2. Static site vs. lightweight backend (recommendation: static, per §5).
3. Hosting target: GitHub Pages vs. Azure Static Web Apps vs. Posit Connect (recommendation: GitHub Pages, per §6).
4. Data persistence pattern: commit-to-repo ("git scraping") vs. stateless build (recommendation: commit-to-repo, per §6).
5. Whether X/Twitter ships in v1 or is deferred (recommendation: defer, §2c).
