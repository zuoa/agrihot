"""Fixed RSS, MOA columns and Crossref journals; discovery never uses search."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import httpx
from lxml import etree, html

from ..schemas import IngestItemIn
from .doi import normalize_doi
from .fulltext.extractors import extract_html
from .ingest_service import PaperDraft


@dataclass
class Source:
    id: str
    name: str
    kind: str
    url: str
    enabled: bool = True
    hosts: list[str] = field(default_factory=list)
    article_pattern: str = ""
    interval_minutes: int = 1440
    note: str = ""
    keywords: list[str] = field(default_factory=list)
    category: str = "报道"
    default_timezone: str = "UTC"


@dataclass
class Candidate:
    title: str
    url: str
    published_at: datetime
    summary: str = ""
    paper: PaperDraft | None = None
    doi: str | None = None


def parse_date(value: str, *, local: bool = False, default_timezone: str | None = None) -> datetime | None:
    try:
        result = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        try:
            result = parsedate_to_datetime(value)
        except (ValueError, TypeError, AttributeError):
            return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=ZoneInfo(default_timezone or ("Asia/Shanghai" if local else "UTC")))
    return result.astimezone(timezone.utc)


def plain_text(value: str) -> str:
    if not value.strip():
        return ""
    return re.sub(r"\s+", " ", html.fromstring(value).text_content()).strip()


def article_url(source: Source, value: str) -> str | None:
    parts = urlsplit(urljoin(source.url, value))
    if (parts.scheme not in {"http", "https"} or parts.hostname not in source.hosts
            or parts.username or parts.password or parts.port not in (None, 80, 443)):
        return None
    if not source.article_pattern or not re.fullmatch(source.article_pattern, parts.path):
        return None
    # Feeds often append tracking queries. Article identity comes from its path.
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


MAX_RESPONSE_BYTES = 8_000_000


async def get_document(client: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
    async with client.stream("GET", url, **kwargs) as response:
        response.raise_for_status()
        body = bytearray()
        async for chunk in response.aiter_bytes():
            body.extend(chunk)
            if len(body) > MAX_RESPONSE_BYTES:
                raise ValueError("source_response_too_large")
        headers = {k: v for k, v in response.headers.items() if k not in {"content-encoding", "content-length"}}
        return httpx.Response(response.status_code, headers=headers, content=bytes(body),
                              request=response.request)


def parse_feed(content: bytes, source: Source) -> tuple[list[Candidate], int]:
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    root = etree.fromstring(content, parser=parser)
    if etree.QName(root).localname not in {"rss", "RDF", "feed"}:
        raise ValueError("invalid_feed")
    entries = root.xpath('//*[local-name()="item" or local-name()="entry"]')
    if not entries:
        raise ValueError("empty_feed")
    candidates, rejected = [], 0
    for entry in entries:
        def text(*names):
            for name in names:
                nodes = entry.xpath(f'./*[local-name()="{name}"]')
                if nodes:
                    value = "".join(nodes[0].itertext()).strip()
                    if value:
                        return value
            return ""

        links = entry.xpath('./*[local-name()="link" and (not(@rel) or @rel="alternate")]/@href')
        url = article_url(source, links[0] if links else text("link"))
        published = parse_date(text("pubDate", "published", "date"), default_timezone=source.default_timezone)
        title = plain_text(text("title"))
        raw_summary = text("description", "summary", "encoded", "content")
        if source.category == "论文":
            # Nature RDF feeds prepend a citation paragraph, which is metadata
            # rather than an abstract and must not become a paper card's evidence.
            raw_summary = re.sub(r'^\s*<p>[^<]*Published online:.*?</p>', "", raw_summary, count=1, flags=re.S)
        summary = plain_text(raw_summary)
        if not url or not published or len(title) < 4 or len(summary) < 40 or summary == title:
            rejected += 1
            continue
        doi, paper = None, None
        if source.category == "论文":
            doi = normalize_doi(text("doi", "identifier"))
            if not doi:
                rejected += 1
                continue
            authors = [{"name": "".join(node.itertext()).strip()} for node in entry.xpath('./*[local-name()="creator"]')]
            paper = PaperDraft(venue=text("publicationName") or source.name,
                               authors=[author for author in authors if author["name"]][:20], ingested_from="rss")
        candidates.append(Candidate(title[:500], url, published, summary[:6000], paper, doi))
    return candidates, rejected


def parse_moa(content: bytes, source: Source) -> tuple[list[Candidate], int]:
    root = html.fromstring(content)
    candidates, rejected = [], 0
    # MOA's dated list anchors, not navigation/footer links. Dates in URL paths
    # can be upload dates: always use the date actually displayed in the list.
    anchors = root.xpath('//a[.//span[contains(@class,"sj_gztzri")]]')
    if not anchors:
        raise ValueError("moa_list_not_found")
    for anchor in anchors:
        title = anchor.get("title") or "".join(anchor.xpath('.//span[contains(@class,"sj_gztzle")]/text()'))
        date_text = "".join(anchor.xpath('.//span[contains(@class,"sj_gztzri")]/text()')).strip()
        published = parse_date(date_text, local=True)
        url = article_url(source, anchor.get("href", ""))
        if not url or not published or len(title.strip()) < 4:
            rejected += 1
            continue
        candidates.append(Candidate(title.strip()[:500], url, published))
    return candidates, rejected


def moa_page_count(content: bytes) -> int:
    found = re.search(rb"(?:var\s+)?countPage\s*=\s*(\d+)", content)
    return max(1, int(found[1])) if found else 1


def map_crossref(work: dict, source: Source) -> Candidate | None:
    if work.get("type") != "journal-article":
        return None
    doi = normalize_doi(work.get("DOI"))
    titles = work.get("title") or []
    title = plain_text(titles[0]) if titles else ""
    # Discovery uses created date; publication date is preserved separately.
    parts = next((work.get(key, {}).get("date-parts", [[]])[0]
                  for key in ("published-online", "published-print", "published", "issued")
                  if work.get(key, {}).get("date-parts", [[]])[0]), [])
    try:
        published = datetime(*parts[:3], *([1] * (3 - len(parts[:3]))), tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None
    if not doi or len(title) < 4:
        return None
    abstract = plain_text(work.get("abstract") or "")
    venue = (work.get("container-title") or [source.name.removeprefix("Crossref · ")])[0]
    authors = [{"name": " ".join(filter(None, [a.get("given"), a.get("family")])),
                "orcid": a.get("ORCID")} for a in (work.get("author") or [])[:20]]
    draft = PaperDraft(authors=[a for a in authors if a["name"]], venue=venue,
                       ingested_from="crossref")
    return Candidate(title[:500], f"https://doi.org/{doi}", published,
                     abstract or f"{title}。{venue}", draft, doi)


async def payload_for(candidate: Candidate, source: Source, client: httpx.AsyncClient) -> IngestItemIn:
    content = None
    category = "论文" if candidate.paper else "报道"
    summary = candidate.summary
    if source.kind == "moa":
        response = await get_document(client, candidate.url)
        if not article_url(source, str(response.url)):
            raise ValueError("unexpected_article_redirect")
        content = extract_html(response.content, candidate.url)
        if len(content) < 200:
            raise ValueError("article_body_missing")
        summary = plain_text(content)[:1500]
        if re.search(r"通知|办法|指导意见|规划|公告|实施方案", candidate.title):
            category = "政策"
    return IngestItemIn(title=candidate.title, url=candidate.url, summary=summary,
                        content=content, source_name=candidate.paper.venue if candidate.paper else source.name,
                        source_url=candidate.url, published_at=candidate.published_at,
                        category=category, tags=["论文"] if candidate.paper else [], doi=candidate.doi)
