"""robots.txt and sitemap.xml."""
from __future__ import annotations

import html
from collections import defaultdict
from datetime import date, datetime, timezone
from urllib.parse import quote

from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Daily, Item, Tag, item_tags
from .topic_service import effective_phrases

CATEGORIES = ("政策", "报道", "论文", "行业")


def site_origin() -> str:
    return (settings.site_url or "https://agrihot.com").rstrip("/")


def abs_url(path: str = "/") -> str:
    origin = site_origin()
    if not path or path == "/":
        return origin + "/"
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if not path.startswith("/"):
        path = "/" + path
    return origin + path


def tag_path(name: str) -> str:
    return "/tags/" + quote(name, safe="")


def _lastmod(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).date().isoformat()
    return value.isoformat()


def robots_txt() -> PlainTextResponse:
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin\n"
        "Disallow: /admin/\n"
        "Disallow: /api/\n"
        "\n"
        f"Sitemap: {abs_url('/sitemap.xml')}\n"
    )
    return PlainTextResponse(body, media_type="text/plain; charset=utf-8")


async def sitemap_xml(session: AsyncSession) -> Response:
    urls: list[tuple[str, str | None, str, str]] = []

    def add(path: str, lastmod: str | None = None, changefreq: str = "weekly", priority: str = "0.6"):
        urls.append((abs_url(path), lastmod, changefreq, priority))

    add("/", changefreq="daily", priority="1.0")
    add("/feed", changefreq="hourly", priority="0.9")
    add("/dailies", changefreq="daily", priority="0.9")
    add("/specials", changefreq="daily", priority="0.9")
    from .special_service import public_specials
    for special, version in await public_specials(session):
        add(f"/specials/{special.id}", _lastmod(version.created_at), "daily", "0.8")
    add("/tags", changefreq="daily", priority="0.7")
    from .taxonomy_service import tree
    taxonomy = await tree(session)
    add("/topic", changefreq="daily", priority="0.8")
    for root in taxonomy["topics"]:
        for node in [root, *root["children"]]:
            if node["count"]:
                add(node["path"], changefreq="daily", priority="0.7")
    add("/about", changefreq="monthly", priority="0.4")
    add("/agent", changefreq="monthly", priority="0.5")
    for cat in CATEGORIES:
        add(f"/feed?category={quote(cat)}", changefreq="daily", priority="0.7")

    dailies = (
        await session.execute(select(Daily.date, Daily.created_at).order_by(Daily.date.desc()))
    ).all()
    for day, created in dailies:
        add(f"/dailies/{day.isoformat()}", _lastmod(created) or day.isoformat(), "weekly", "0.8")

    rows = (
        await session.execute(
            select(Item.id, Item.created_at, Item.published_at, Item.is_selected, Item.search_phrases)
            .order_by(Item.id.desc())
        )
    ).all()
    item_last: dict[int, str | None] = {}
    stored_by_id: dict[int, list | None] = {}
    for iid, created, published, selected, phrases in rows:
        last = _lastmod(published or created)
        item_last[iid] = last
        stored_by_id[iid] = phrases
        add(f"/items/{iid}", last, "weekly", "0.8" if selected else "0.5")

    def newer(current: str | None, candidate: str | None) -> str | None:
        if candidate and (current is None or candidate > current):
            return candidate
        return current

    tag_names: dict[int, list[str]] = defaultdict(list)
    tag_last: dict[str, str | None] = {}
    for iid, tname in (
        await session.execute(
            select(item_tags.c.item_id, Tag.name).join(Tag, Tag.id == item_tags.c.tag_id)
        )
    ).all():
        tag_names[iid].append(tname)
        tag_last[tname] = newer(tag_last.get(tname), item_last.get(iid))
    for name, last in tag_last.items():
        add(tag_path(name), last, "weekly", "0.5")

    phrase_last: dict[str, str | None] = {}
    for iid, stored in stored_by_id.items():
        for phrase in effective_phrases(tag_names.get(iid, []), stored):
            if phrase in tag_last:
                continue
            phrase_last[phrase] = newer(phrase_last.get(phrase), item_last.get(iid))
    for phrase, last in phrase_last.items():
        add(tag_path(phrase), last, "weekly", "0.4")

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for loc, lastmod, changefreq, priority in urls:
        parts.append("<url>")
        parts.append(f"<loc>{html.escape(loc)}</loc>")
        if lastmod:
            parts.append(f"<lastmod>{html.escape(lastmod)}</lastmod>")
        parts.append(f"<changefreq>{changefreq}</changefreq>")
        parts.append(f"<priority>{priority}</priority>")
        parts.append("</url>")
    parts.append("</urlset>\n")
    return Response(content="\n".join(parts), media_type="application/xml; charset=utf-8")
