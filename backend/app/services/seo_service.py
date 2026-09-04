"""robots.txt, sitemap.xml, and crawler-facing HTML snapshots."""
from __future__ import annotations

import html
import json
import re
from datetime import date, datetime, timezone
from urllib.parse import quote

from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Daily, Item, PaperMeta, Tag

SITE_NAME = "AgriHot"
DEFAULT_TITLE = "AgriHot · 农业信息化动态聚合"
DEFAULT_DESC = (
    "农业信息化资讯聚合：政策、报道、学术论文每日精选与农业农村日报。"
    "覆盖智慧农业、数字乡村与农业农村政策。"
)
OG_IMAGE_PATH = "/og-image.png"
CATEGORIES = ("政策", "报道", "论文", "行业")
NAV = (
    ("/", "精选"),
    ("/feed", "全部动态"),
    ("/dailies", "农业日报"),
    ("/tags", "主题"),
    ("/about", "关于"),
)

_CSS = """
:root { color-scheme: light; }
body { margin:0; font-family:"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  background:#f2f9f0; color:#1c1917; line-height:1.65; }
a { color:#327a2d; }
header.site { background:#fff; border-bottom:1px solid #e0f1db; }
header.site nav { max-width:720px; margin:0 auto; padding:14px 20px;
  display:flex; gap:14px; flex-wrap:wrap; align-items:center; }
header.site a.brand { font-weight:700; color:#296026; text-decoration:none; font-size:18px; }
header.site nav a { color:#44403c; text-decoration:none; font-size:14px; }
main { max-width:720px; margin:0 auto; padding:28px 20px 48px; }
h1 { font-size:1.55rem; line-height:1.35; margin:0 0 12px; color:#1c1917; }
h2 { font-size:1.12rem; color:#296026; margin:1.4em 0 .5em; }
.lede { color:#57534e; margin:0 0 20px; }
.muted { color:#78716c; font-size:14px; }
.card { background:#fff; border:1px solid #e0f1db; border-radius:14px; padding:16px 18px; margin:12px 0; }
.card h2 { margin:0 0 6px; font-size:1.05rem; }
.card h2 a { color:#1c1917; text-decoration:none; }
.card h2 a:hover { color:#327a2d; }
.summary { font-size:15px; color:#44403c; margin:8px 0 0; }
.tags { margin-top:12px; }
.tags a { display:inline-block; margin:4px 10px 0 0; font-size:13px; }
article.body p { margin:0 0 12px; }
footer.site { max-width:720px; margin:0 auto; padding:0 20px 40px; color:#a8a29e; font-size:12px; }
.crumb { font-size:13px; color:#78716c; margin-bottom:12px; }
.crumb a { color:#57534e; text-decoration:none; }
"""


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


def clip(text: str | None, n: int = 160) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if len(t) <= n:
        return t
    return t[: n - 1] + "…"


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


def _iso(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime) and value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _clean(obj):
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return obj


def _dumps_ld(obj) -> str:
    return json.dumps(_clean(obj), ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def _inline(text: str) -> str:
    parts: list[str] = []
    last = 0
    for m in re.finditer(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", text):
        parts.append(html.escape(text[last:m.start()]))
        parts.append(
            f'<a href="{html.escape(m.group(2), quote=True)}" rel="noopener">'
            f"{html.escape(m.group(1))}</a>"
        )
        last = m.end()
    parts.append(html.escape(text[last:]))
    return "".join(parts).replace("\n", "<br>\n")


def _text_to_html(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    blocks = []
    for raw in re.split(r"\n{2,}", text[:50000]):
        block = raw.strip()
        if not block:
            continue
        if block.startswith("### "):
            blocks.append(f"<h3>{_inline(block[4:].strip())}</h3>")
        elif block.startswith("## "):
            blocks.append(f"<h2>{_inline(block[3:].strip())}</h2>")
        elif block.startswith("# "):
            blocks.append(f"<h2>{_inline(block[2:].strip())}</h2>")
        else:
            blocks.append(f"<p>{_inline(block)}</p>")
    return "\n".join(blocks)


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
    add("/tags", changefreq="daily", priority="0.7")
    add("/about", changefreq="monthly", priority="0.4")
    for cat in CATEGORIES:
        add(f"/feed?category={quote(cat)}", changefreq="daily", priority="0.7")

    dailies = (
        await session.execute(select(Daily.date, Daily.created_at).order_by(Daily.date.desc()))
    ).all()
    for day, created in dailies:
        add(f"/dailies/{day.isoformat()}", _lastmod(created) or day.isoformat(), "weekly", "0.8")

    items = (
        await session.execute(
            select(Item.id, Item.created_at, Item.published_at, Item.is_selected).order_by(Item.id.desc())
        )
    ).all()
    for iid, created, published, selected in items:
        add(
            f"/items/{iid}",
            _lastmod(published or created),
            "weekly",
            "0.8" if selected else "0.5",
        )

    tags = (
        await session.execute(
            select(Tag.name)
            .join(Tag.items)
            .group_by(Tag.name)
            .having(func.count(Item.id) > 0)
        )
    ).all()
    for (name,) in tags:
        add(tag_path(name), None, "weekly", "0.5")

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


def render_html(
    *,
    title: str,
    description: str,
    path: str,
    body: str,
    json_ld: dict | list | None = None,
    status: int = 200,
    noindex: bool = False,
    og_type: str = "website",
) -> HTMLResponse:
    canonical = abs_url(path)
    image = abs_url(OG_IMAGE_PATH)
    robots = "noindex, nofollow" if noindex else "index, follow"
    ld = f'<script type="application/ld+json">{_dumps_ld(json_ld)}</script>' if json_ld else ""
    nav = "".join(
        f'<a href="{html.escape(href)}">{html.escape(label)}</a>' for href, label in NAV
    )
    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(description)}">
<meta name="robots" content="{robots}">
<link rel="canonical" href="{html.escape(canonical)}">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta property="og:type" content="{html.escape(og_type)}">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:locale" content="zh_CN">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(description)}">
<meta property="og:url" content="{html.escape(canonical)}">
<meta property="og:image" content="{html.escape(image)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{html.escape(title)}">
<meta name="twitter:description" content="{html.escape(description)}">
<meta name="twitter:image" content="{html.escape(image)}">
<style>{_CSS}</style>
{ld}
</head>
<body>
<header class="site"><nav><a class="brand" href="/">AgriHot</a>{nav}</nav></header>
<main>{body}</main>
<footer class="site">AgriHot · 农业信息化动态聚合 — 内容整理自公开来源，摘要由 AI 生成，引用请以官方原文为准</footer>
</body>
</html>
"""
    headers = {"X-Robots-Tag": robots}
    return HTMLResponse(page, status_code=status, headers=headers)


def page_not_found(path: str = "/") -> HTMLResponse:
    body = (
        " <h1>页面不存在</h1>"
        '<p class="lede">这条内容可能已下线。返回 <a href="/">首页</a> 或查看 '
        '<a href="/dailies">农业日报</a>。</p>'
    )
    return render_html(
        title="页面不存在 · AgriHot",
        description=DEFAULT_DESC,
        path=path,
        body=body,
        status=404,
        noindex=True,
    )


def website_json_ld() -> dict:
    origin = abs_url("/")
    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Organization",
                "@id": origin + "#org",
                "name": SITE_NAME,
                "url": origin,
                "logo": abs_url("/apple-touch-icon.png"),
            },
            {
                "@type": "WebSite",
                "@id": origin + "#website",
                "url": origin,
                "name": SITE_NAME,
                "description": DEFAULT_DESC,
                "inLanguage": "zh-CN",
                "publisher": {"@id": origin + "#org"},
                "potentialAction": {
                    "@type": "SearchAction",
                    "target": abs_url("/feed") + "?q={search_term_string}",
                    "query-input": "required name=search_term_string",
                },
            },
        ],
    }


def item_json_ld(item: Item) -> dict:
    path = f"/items/{item.id}"
    summary = item.summary_zh or item.summary
    is_paper = item.category == "论文" or item.paper is not None
    authors: list[dict] = []
    if item.paper and item.paper.authors:
        for raw in item.paper.authors:
            if isinstance(raw, dict) and raw.get("name"):
                authors.append({"@type": "Person", "name": str(raw["name"])})
    article = {
        "@type": "ScholarlyArticle" if is_paper else "NewsArticle",
        "headline": item.title,
        "description": clip(summary, 300),
        "url": abs_url(path),
        "mainEntityOfPage": abs_url(path),
        "image": item.cover_url or abs_url(OG_IMAGE_PATH),
        "datePublished": _iso(item.published_at or item.created_at),
        "dateModified": _iso(item.created_at),
        "inLanguage": "zh-CN",
        "isAccessibleForFree": True,
        "publisher": {
            "@type": "Organization",
            "name": SITE_NAME,
            "url": abs_url("/"),
            "logo": {"@type": "ImageObject", "url": abs_url("/apple-touch-icon.png")},
        },
        "author": authors or {"@type": "Organization", "name": item.source_name or SITE_NAME},
    }
    if item.doi:
        article["identifier"] = f"https://doi.org/{item.doi}"
        article["sameAs"] = f"https://doi.org/{item.doi}"
    if item.paper and item.paper.venue:
        article["isPartOf"] = {"@type": "Periodical", "name": item.paper.venue}
    crumbs = [
        {"@type": "ListItem", "position": 1, "name": "首页", "item": abs_url("/")},
        {
            "@type": "ListItem",
            "position": 2,
            "name": item.category or "资讯",
            "item": abs_url("/feed") + (f"?category={quote(item.category)}" if item.category else ""),
        },
        {"@type": "ListItem", "position": 3, "name": item.title, "item": abs_url(path)},
    ]
    return {
        "@context": "https://schema.org",
        "@graph": [article, {"@type": "BreadcrumbList", "itemListElement": crumbs}],
    }


def _item_card(item: Item) -> str:
    summary = clip(item.summary_zh or item.summary, 140)
    meta = " · ".join(x for x in (item.source_name, item.category) if x)
    return (
        f'<article class="card"><h2><a href="/items/{item.id}">{html.escape(item.title)}</a></h2>'
        f'<p class="muted">{html.escape(meta)}</p>'
        f'<p class="summary">{html.escape(summary)}</p></article>'
    )


def _crumb(*parts: str) -> str:
    bits = []
    for i in range(0, len(parts), 2):
        href, label = parts[i], parts[i + 1]
        bits.append(f'<a href="{html.escape(href)}">{html.escape(label)}</a>')
    return '<p class="crumb">' + " / ".join(bits) + "</p>"


async def page_home(session: AsyncSession, category: str | None) -> HTMLResponse:
    cat = category if category in CATEGORIES else None
    stmt = (
        select(Item)
        .where(Item.is_selected.is_(True))
        .order_by(Item.created_at.desc(), Item.id.desc())
        .limit(50)
    )
    if cat:
        stmt = stmt.where(Item.category == cat)
    items = (await session.execute(stmt)).scalars().all()
    heading = f"{cat}精选" if cat else "农业信息化每日精选"
    title = f"{heading} · AgriHot" if cat else DEFAULT_TITLE
    desc = (
        f"AgriHot 首页精选中的{cat}资讯。"
        if cat
        else DEFAULT_DESC
    )
    path = f"/?category={quote(cat)}" if cat else "/"
    cards = "".join(_item_card(i) for i in items) or '<p class="lede">暂无内容</p>'
    filters = " ".join(
        f'<a href="{"/" if c == "全部" else "/?category=" + quote(c)}">{html.escape(c)}</a>'
        for c in ("全部", *CATEGORIES)
    )
    body = (
        f"{_crumb('/', '首页')}"
        f"<h1>{html.escape(heading)}</h1>"
        f'<p class="lede">{html.escape(desc)}</p>'
        f'<p class="muted">分类：{filters}</p>'
        f"{cards}"
    )
    return render_html(
        title=title,
        description=clip(desc),
        path=path,
        body=body,
        json_ld=website_json_ld(),
    )


async def page_feed(
    session: AsyncSession,
    *,
    category: str | None,
    direction: str | None,
    q: str | None,
    page: int,
) -> HTMLResponse:
    cat = category if category in CATEGORIES else None
    query = (q or "").strip()
    page = max(1, page)
    page_size = 20
    stmt = select(Item)
    count_stmt = select(func.count(Item.id))
    if cat:
        stmt = stmt.where(Item.category == cat)
        count_stmt = count_stmt.where(Item.category == cat)
    if cat == "论文" and direction:
        stmt = stmt.join(Item.paper).where(PaperMeta.direction == direction)
        count_stmt = count_stmt.join(Item.paper).where(PaperMeta.direction == direction)
    if query:
        like = f"%{query}%"
        cond = Item.title.ilike(like)
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    total = (await session.execute(count_stmt)).scalar_one()
    rows = (
        await session.execute(
            stmt.order_by(Item.created_at.desc(), Item.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    heading_bits = ["全部动态"]
    if cat:
        heading_bits.append(cat)
    if cat == "论文" and direction:
        heading_bits.append(direction)
    heading = " · ".join(heading_bits)
    title = f"{heading} · AgriHot"
    desc = clip(query or f"农业信息化{cat or '资讯'}列表：政策、报道、学术论文与行业动态。")

    def feed_path(p: int = 1) -> str:
        parts: list[str] = []
        if cat:
            parts.append(f"category={quote(cat)}")
        if cat == "论文" and direction:
            parts.append(f"direction={quote(direction)}")
        if query:
            parts.append(f"q={quote(query)}")
        if p > 1:
            parts.append(f"page={p}")
        return "/feed" + (("?" + "&".join(parts)) if parts else "")

    path = feed_path(page)
    filters = " ".join(
        f'<a href="{html.escape("/feed" if c == "全部" else "/feed?category=" + quote(c))}">{html.escape(c)}</a>'
        for c in ("全部", *CATEGORIES)
    )
    cards = "".join(_item_card(i) for i in rows) or '<p class="lede">暂无内容</p>'
    pages = max(1, (total + page_size - 1) // page_size)
    pager = ""
    if pages > 1:
        bits = []
        if page > 1:
            bits.append(f'<a href="{html.escape(feed_path(page - 1))}">上一页</a>')
        bits.append(f"{page} / {pages}")
        if page < pages:
            bits.append(f'<a href="{html.escape(feed_path(page + 1))}">下一页</a>')
        pager = f'<p class="muted">{" · ".join(bits)}</p>'
    hidden_cat = (
        f'<input type="hidden" name="category" value="{html.escape(cat)}">' if cat else ""
    )
    body = (
        f"{_crumb('/', '首页')}"
        f"<h1>{html.escape(heading)}</h1>"
        f'<form action="/feed" method="get"><input type="search" name="q" value="{html.escape(query)}" placeholder="搜索标题">'
        f"{hidden_cat}"
        f'<button type="submit">搜索</button></form>'
        f'<p class="muted">分类：{filters}</p>'
        f"{cards}{pager}"
    )
    return render_html(
        title=title,
        description=desc,
        path=path,
        body=body,
        noindex=bool(query),
    )


async def page_item(session: AsyncSession, item_id: int) -> HTMLResponse:
    item = await session.get(Item, item_id)
    if item is None:
        return page_not_found(f"/items/{item_id}")
    path = f"/items/{item_id}"
    summary = item.summary_zh or item.summary
    desc = clip(summary)
    title = f"{item.title} · AgriHot"
    meta_bits = [item.source_name or "未知来源", item.category]
    if item.published_at or item.created_at:
        meta_bits.append(_lastmod(item.published_at or item.created_at) or "")
    tags_html = ""
    if item.tags:
        tags_html = '<p class="tags">' + "".join(
            f'<a href="{html.escape(tag_path(t.name))}">#{html.escape(t.name)}</a>'
            for t in item.tags
        ) + "</p>"
    card_html = ""
    paper = item.paper
    if paper and isinstance(paper.card, dict) and paper.card.get("tldr"):
        fields = (
            ("速览", "tldr"),
            ("方法", "method"),
            ("发现", "finding"),
            ("方向", "direction"),
            ("机会点", "opportunity"),
        )
        rows = "".join(
            f"<p><strong>{label}：</strong>{html.escape(str(paper.card.get(key) or ''))}</p>"
            for label, key in fields
            if paper.card.get(key)
        )
        card_html = f"<section><h2>论文卡片</h2>{rows}</section>"
    authors = ""
    if paper and paper.authors:
        names = [str(a.get("name")) for a in paper.authors if isinstance(a, dict) and a.get("name")]
        if names:
            authors = f'<p class="muted">{html.escape(" · ".join(names[:8]))}</p>'
    extra = ""
    if item.doi:
        extra += f'<p class="muted">DOI <a href="https://doi.org/{html.escape(item.doi)}" rel="noopener">{html.escape(item.doi)}</a></p>'
    if paper and paper.venue:
        extra += f'<p class="muted">{html.escape(paper.venue)}</p>'
    sources = item.sources or [{"name": item.source_name, "url": item.url}]
    source_html = "<h2>信源</h2><ul>" + "".join(
        f'<li><a href="{html.escape(str(s.get("url") or item.url), quote=True)}" rel="noopener">'
        f'{html.escape(str(s.get("name") or "原文"))}</a></li>'
        for s in sources
        if isinstance(s, dict)
    ) + "</ul>"
    body = (
        f"{_crumb('/', '首页')}"
        f'<p class="muted">{html.escape(" · ".join(x for x in meta_bits if x))}</p>'
        f"<h1>{html.escape(item.title)}</h1>"
        f"{authors}{extra}{card_html}"
        f"<section><h2>摘要</h2><div class=\"body\">{_text_to_html(summary)}</div></section>"
        + (f"<section><h2>全文</h2><div class=\"body\">{_text_to_html(item.content or '')}</div></section>" if item.content else "")
        + tags_html
        + source_html
    )
    return render_html(
        title=title,
        description=desc,
        path=path,
        body=body,
        json_ld=item_json_ld(item),
        og_type="article",
    )


async def page_dailies(session: AsyncSession) -> HTMLResponse:
    rows = (
        await session.execute(select(Daily).order_by(Daily.date.desc()).limit(60))
    ).scalars().all()
    cards = "".join(
        f'<article class="card"><h2><a href="/dailies/{d.date.isoformat()}">{html.escape(d.title)}</a></h2>'
        f'<p class="muted">{d.date.isoformat()} · {len(d.highlights or [])} 条要点 · {len(d.item_ids or [])} 条资讯</p>'
        f"</article>"
        for d in rows
    ) or '<p class="lede">暂无日报</p>'
    body = (
        f"{_crumb('/', '首页')}"
        "<h1>农业日报</h1>"
        '<p class="lede">每日《农业农村日报》：政策、报道、学术论文与行业动态精选。</p>'
        f"{cards}"
    )
    return render_html(
        title="农业日报 · AgriHot",
        description="每日《农业农村日报》：农业信息化政策、报道、论文与行业动态精选。",
        path="/dailies",
        body=body,
    )


async def page_daily(session: AsyncSession, day: date) -> HTMLResponse:
    d = (
        await session.execute(select(Daily).where(Daily.date == day))
    ).scalar_one_or_none()
    if d is None:
        return page_not_found(f"/dailies/{day.isoformat()}")
    items: list[Item] = []
    for iid in d.item_ids or []:
        item = await session.get(Item, iid)
        if item is not None:
            items.append(item)
    highlights = "".join(f"<li>{html.escape(h)}</li>" for h in (d.highlights or []))
    cards = "".join(_item_card(i) for i in items)
    desc = clip(" ".join(d.highlights or []) or d.content or d.title)
    path = f"/dailies/{day.isoformat()}"
    body = (
        f"{_crumb('/', '首页', '/dailies', '农业日报')}"
        f'<p class="muted">{day.isoformat()}</p>'
        f"<h1>{html.escape(d.title)}</h1>"
        + (f"<section><h2>今日要点</h2><ol>{highlights}</ol></section>" if highlights else "")
        + (f"<section><h2>收录条目</h2>{cards}</section>" if cards else "")
    )
    json_ld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": d.title,
        "description": desc,
        "url": abs_url(path),
        "datePublished": day.isoformat(),
        "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": abs_url("/")},
        "hasPart": [
            {"@type": "Article", "name": it.title, "url": abs_url(f"/items/{it.id}")}
            for it in items[:20]
        ],
    }
    return render_html(
        title=f"{d.title}（{day.isoformat()}）｜农业农村日报",
        description=desc,
        path=path,
        body=body,
        json_ld=json_ld,
        og_type="article",
    )


async def page_tags(session: AsyncSession) -> HTMLResponse:
    rows = (
        await session.execute(
            select(Tag.name, func.count(Item.id))
            .join(Tag.items)
            .group_by(Tag.name)
            .having(func.count(Item.id) > 0)
            .order_by(func.count(Item.id).desc())
        )
    ).all()
    links = "".join(
        f'<a href="{html.escape(tag_path(name))}">#{html.escape(name)} ({count})</a> '
        for name, count in rows
    ) or '<p class="lede">暂无主题</p>'
    body = (
        f"{_crumb('/', '首页')}"
        "<h1>主题</h1>"
        '<p class="lede">按主题浏览农业信息化资讯与论文。</p>'
        f'<p class="tags">{links}</p>'
    )
    return render_html(
        title="主题 · AgriHot",
        description="按主题浏览农业信息化资讯：智慧农业、数字乡村、遥感、政策等。",
        path="/tags",
        body=body,
    )


async def page_tag(session: AsyncSession, name: str) -> HTMLResponse:
    rows = (
        await session.execute(
            select(Item)
            .where(Item.tags.any(Tag.name == name))
            .order_by(Item.created_at.desc(), Item.id.desc())
            .limit(100)
        )
    ).scalars().all()
    if not rows:
        # still 200 if tag exists historically empty; 404 only when nothing to show
        exists = (
            await session.execute(select(Tag.id).where(Tag.name == name))
        ).scalar_one_or_none()
        if exists is None:
            return page_not_found(tag_path(name))
    cards = "".join(_item_card(i) for i in rows) or '<p class="lede">该主题下暂无内容</p>'
    path = tag_path(name)
    desc = f"农业信息化主题「{name}」相关资讯与论文，共 {len(rows)} 条。"
    body = (
        f"{_crumb('/', '首页', '/tags', '主题')}"
        f"<h1>#{html.escape(name)}</h1>"
        f'<p class="lede">{html.escape(desc)}</p>'
        f"{cards}"
    )
    return render_html(
        title=f"#{name} · AgriHot",
        description=clip(desc),
        path=path,
        body=body,
    )


def page_about() -> HTMLResponse:
    body = (
        f"{_crumb('/', '首页')}"
        "<h1>关于 AgriHot</h1>"
        '<p class="lede">AgriHot 是一个农业信息化资讯聚合站：聚合农业农村政策、行业报道与'
        "农业信息化学术论文，每日生成《农业农村日报》。内容主要由爬虫 Agent 通过开放推送接口提交，"
        "服务层自动去重后上线。</p>"
        "<ul>"
        "<li>政策与报道：部委文件、地方实践、行业动态</li>"
        "<li>学术论文：OpenAlex 日更订阅核心期刊与方向；外文摘要译为中文卡片</li>"
        "<li>Agent 友好：开放推送 API，去重后自动上线</li>"
        "</ul>"
        '<p>联系：<a href="mailto:ijedyu@gmail.com">ijedyu@gmail.com</a></p>'
    )
    return render_html(
        title="关于 · AgriHot",
        description="关于 AgriHot：农业信息化资讯聚合、农业农村日报与学术论文雷达。",
        path="/about",
        body=body,
    )


def page_agent() -> HTMLResponse:
    body = (
        f"{_crumb('/', '首页')}"
        "<h1>Agent 接入说明</h1>"
        '<p class="lede">AgriHot 面向爬虫 / 资讯聚合 Agent 开放推送接口。'
        "推送的内容经服务层自动去重后直接上线，并由 AI 做相关性判断与多维评分。</p>"
        '<p>完整接口说明见站点 <a href="/agent">/agent</a> 与 <a href="/docs">OpenAPI</a>。</p>'
    )
    return render_html(
        title="Agent 接入 · AgriHot",
        description="AgriHot 开放推送 API：农业信息化资讯接入、自动去重与精选评分。",
        path="/agent",
        body=body,
    )
