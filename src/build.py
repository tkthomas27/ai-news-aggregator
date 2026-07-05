"""Static site generator: query DuckDB -> render templates/index.html.j2 -> site/.

Run:  python -m src.build
"""
from __future__ import annotations

from datetime import datetime, timezone

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import SITE_DIR, SITE_MAX_ITEMS, TEMPLATES_DIR
from .db import connect


def _fmt_date(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return value.strftime("%Y-%m-%d %H:%M")


def gather():
    con = connect()
    rows = con.execute(
        """
        SELECT i.title, i.link, i.published_at, i.summary,
               s.id AS source_id, s.name AS source_name, s.homepage_url
        FROM items i
        JOIN sources s ON s.id = i.source_id
        WHERE s.active
        ORDER BY i.published_at DESC
        LIMIT ?
        """,
        [SITE_MAX_ITEMS],
    ).fetchall()
    cols = [c[0] for c in con.description]
    items = [dict(zip(cols, r)) for r in rows]

    sources = con.execute(
        """
        SELECT s.id, s.name, COUNT(i.id) AS n
        FROM sources s
        LEFT JOIN items i ON i.source_id = s.id
        WHERE s.active
        GROUP BY s.id, s.name
        ORDER BY s.name
        """
    ).fetchall()
    scols = [c[0] for c in con.description]
    source_list = [dict(zip(scols, r)) for r in sources]
    con.close()
    return items, source_list


def build() -> int:
    items, sources = gather()
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.filters["fmt_date"] = _fmt_date
    template = env.get_template("index.html.j2")
    html = template.render(
        items=items,
        sources=sources,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        item_count=len(items),
    )
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    (SITE_DIR / "index.html").write_text(html, encoding="utf-8")
    # GitHub Pages: skip Jekyll processing.
    (SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Wrote {SITE_DIR / 'index.html'} ({len(items)} items, {len(sources)} sources).")
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
