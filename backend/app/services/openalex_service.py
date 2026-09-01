"""OpenAlex literature poll: fetch works, map to ingest payloads, no LLM.

OpenAlex is the only first-party scholarly source in P0. Fetch is pure
bookkeeping — scoring and paper cards run after ingest, in enrich_and_score.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import PipelineState
from ..schemas import IngestItemIn
from .doi import normalize_doi
from .ingest_service import PaperDraft, ingest_item

log = logging.getLogger(__name__)

OPENALEX_BASE = "https://api.openalex.org"
STATE_KEY = "openalex.from_date"
# per-query page cap so a runaway search cannot loop forever
MAX_PAGES_PER_QUERY = 4
PER_PAGE = 50
WORK_SELECT = (
    "id,doi,display_name,publication_date,type,cited_by_count,"
    "abstract_inverted_index,primary_location,authorships,open_access"
)


def reconstruct_abstract(inverted_index: dict | None) -> str | None:
    """Rebuild a space-joined abstract from OpenAlex's inverted index."""
    if not inverted_index or not isinstance(inverted_index, dict):
        return None
    placed: list[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        if not word or not isinstance(positions, list):
            continue
        for pos in positions:
            try:
                placed.append((int(pos), str(word)))
            except (TypeError, ValueError):
                continue
    if not placed:
        return None
    placed.sort()
    return " ".join(word for _, word in placed)


def _default_watchlist_path() -> Path:
    return Path(__file__).resolve().parent.parent / "watchlist.yaml"


@lru_cache(maxsize=1)
def load_watchlist() -> dict:
    path = Path(settings.watchlist_path) if settings.watchlist_path else _default_watchlist_path()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        log.warning("watchlist not found at %s", path)
        return {}
    except Exception:
        log.exception("failed to load watchlist %s", path)
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def direction_names() -> list[str]:
    names = [d.get("name") for d in load_watchlist().get("directions") or [] if d.get("name")]
    if "其他" not in names:
        names.append("其他")
    return names


def passes_prescreen(title: str, abstract: str, extra: list[str] | None = None) -> bool:
    """Cheap keyword gate: any watchlist term in title+abstract (casefold)."""
    terms = list(load_watchlist().get("prescreen") or [])
    if extra:
        terms.extend(extra)
    hay = f"{title}\n{abstract}".casefold()
    return any(str(t).casefold() in hay for t in terms if t)


def map_work(
    work: dict,
    *,
    direction: str | None = None,
    ingested_from: str = "openalex",
) -> tuple[IngestItemIn, PaperDraft] | None:
    """OpenAlex work JSON -> ingest payload + paper draft. None if unusable."""
    title = (work.get("display_name") or "").strip()
    if len(title) < 4:
        return None
    doi = normalize_doi(work.get("doi"))
    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
    loc = work.get("primary_location") or {}
    source = loc.get("source") or {} if isinstance(loc, dict) else {}
    venue = (source.get("display_name") or "").strip() or None
    landing = (loc.get("landing_page_url") or "").strip() if isinstance(loc, dict) else ""
    oa = work.get("open_access") or {}
    oa_url = (oa.get("oa_url") or loc.get("pdf_url") or "") or None
    if doi:
        url = f"https://doi.org/{doi}"
    else:
        url = landing or (work.get("id") or "")
    if not url:
        return None

    summary = (abstract or "").strip()
    if len(summary) < 10:
        # schema requires ≥10 chars; no-abstract papers still ingest
        summary = f"{title}。{venue or 'OpenAlex'}"[:500]

    authors: list[dict] = []
    for authorship in (work.get("authorships") or [])[:20]:
        author = (authorship or {}).get("author") or {}
        name = (author.get("display_name") or "").strip()
        if not name:
            continue
        orcid = author.get("orcid")
        authors.append({"name": name, "orcid": orcid})

    published_at = None
    pub = work.get("publication_date")
    if pub:
        try:
            published_at = datetime.strptime(pub, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            published_at = None

    openalex_id = _short_id(work.get("id"))
    cited = work.get("cited_by_count") or 0
    try:
        cited = int(cited)
    except (TypeError, ValueError):
        cited = 0

    payload = IngestItemIn(
        title=title[:500],
        url=url[:2000],
        summary=summary,
        source_name=(venue or "OpenAlex")[:200],
        source_url=landing or url,
        published_at=published_at,
        category="论文",
        tags=["论文"],
        doi=doi,
    )
    draft = PaperDraft(
        openalex_id=openalex_id,
        authors=authors,
        venue=venue,
        cited_by_count=cited,
        oa_url=oa_url,
        direction=direction,
        ingested_from=ingested_from,
    )
    return payload, draft


def _short_id(openalex_url: str | None) -> str | None:
    if not openalex_url:
        return None
    ident = str(openalex_url).rstrip("/").rsplit("/", 1)[-1]
    return ident or None


def _client_params(extra: dict | None = None) -> dict:
    params: dict[str, Any] = {"mailto": settings.openalex_mailto}
    if settings.openalex_api_key:
        params["api_key"] = settings.openalex_api_key
    if extra:
        params.update(extra)
    return params


def _headers() -> dict[str, str]:
    return {"User-Agent": f"AgriHot (mailto:{settings.openalex_mailto})"}


async def _get_json(client: httpx.AsyncClient, path: str, params: dict) -> dict:
    url = f"{OPENALEX_BASE}{path}"
    resp = await client.get(url, params=_client_params(params), headers=_headers())
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, dict) else {}


async def resolve_source_id(client: httpx.AsyncClient, issn: str) -> str | None:
    data = await _get_json(client, "/sources", {"filter": f"issn:{issn}", "per_page": 1})
    results = data.get("results") or []
    if not results:
        return None
    return _short_id(results[0].get("id"))


async def iter_works(
    client: httpx.AsyncClient,
    filter_expr: str,
    *,
    search: str | None = None,
) -> AsyncIterator[dict]:
    cursor = "*"
    pages = 0
    while cursor and pages < MAX_PAGES_PER_QUERY:
        params: dict[str, Any] = {
            "filter": filter_expr,
            "per_page": PER_PAGE,
            "cursor": cursor,
            "select": WORK_SELECT,
            "sort": "publication_date:desc",
        }
        if search:
            params["search"] = search
        try:
            data = await _get_json(client, "/works", params)
        except Exception as exc:
            log.warning("OpenAlex works request failed filter=%s search=%s: %s", filter_expr, search, exc)
            return
        for work in data.get("results") or []:
            if isinstance(work, dict):
                yield work
        cursor = (data.get("meta") or {}).get("next_cursor")
        pages += 1
        if cursor:
            await asyncio.sleep(0.12)


def _date_filter(from_date: date) -> str:
    return (
        f"from_publication_date:{from_date.isoformat()},"
        "type:article|preprint,is_retracted:false"
    )


async def _from_date(session: AsyncSession, today: date) -> date:
    row = await session.get(PipelineState, STATE_KEY)
    if row is None or not row.value:
        return today - timedelta(days=settings.literature_bootstrap_days)
    try:
        last = date.fromisoformat(row.value)
    except ValueError:
        last = today
    return last - timedelta(days=settings.literature_lookback_days)


async def _save_from_date(session: AsyncSession, today: date) -> None:
    row = await session.get(PipelineState, STATE_KEY)
    if row is None:
        row = PipelineState(key=STATE_KEY, value=today.isoformat())
        session.add(row)
    else:
        row.value = today.isoformat()
        row.updated_at = datetime.now(timezone.utc)


async def poll_and_ingest(session: AsyncSession, *, today: date | None = None) -> dict:
    """Pull OpenAlex works in the watch window and ingest. Caller commits.

    Returns counts plus created item ids under ``created_ids``.
    """
    today = today or datetime.now(timezone.utc).date()
    from_date = await _from_date(session, today)
    watch = load_watchlist()
    stats = {
        "fetched": 0,
        "screened_out": 0,
        "created": 0,
        "duplicate": 0,
        "errors": 0,
        "from_date": from_date.isoformat(),
        "truncated": False,
        "created_ids": [],
    }
    date_filter = _date_filter(from_date)
    timeout = httpx.Timeout(30.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        # journals: trusted venues, skip keyword prescreen
        for journal in watch.get("journals") or []:
            issn = str(journal.get("issn") or "").strip()
            if not issn:
                continue
            try:
                source_id = await resolve_source_id(client, issn)
            except Exception as exc:
                log.warning("OpenAlex source lookup failed issn=%s: %s", issn, exc)
                continue
            if not source_id:
                log.info("OpenAlex has no source for issn=%s (%s)", issn, journal.get("name"))
                continue
            filt = f"{date_filter},primary_location.source.id:{source_id}"
            await _ingest_stream(session, client, filt, stats, direction=None, prescreen=False)

        for author in watch.get("authors") or []:
            aid = str(author.get("openalex_id") or author.get("id") or "").strip()
            if not aid:
                continue
            aid = aid.rsplit("/", 1)[-1]
            filt = f"{date_filter},authorships.author.id:{aid}"
            await _ingest_stream(session, client, filt, stats, direction=None, prescreen=True)

        for direction in watch.get("directions") or []:
            name = direction.get("name")
            for query in direction.get("queries") or []:
                q = str(query).strip()
                if not q:
                    continue
                await _ingest_stream(
                    session, client, date_filter, stats,
                    direction=name, prescreen=True, search=q,
                )
                if stats["truncated"]:
                    break
            if stats["truncated"]:
                break

    await _save_from_date(session, today)
    log.info(
        "OpenAlex poll %s→%s fetched=%s created=%s dup=%s screened=%s errors=%s truncated=%s",
        from_date, today, stats["fetched"], stats["created"], stats["duplicate"],
        stats["screened_out"], stats["errors"], stats["truncated"],
    )
    return stats


async def _ingest_stream(
    session: AsyncSession,
    client: httpx.AsyncClient,
    filter_expr: str,
    stats: dict,
    *,
    direction: str | None,
    prescreen: bool,
    search: str | None = None,
) -> None:
    if stats["truncated"]:
        return
    async for work in iter_works(client, filter_expr, search=search):
        stats["fetched"] += 1
        mapped = map_work(work, direction=direction)
        if mapped is None:
            stats["errors"] += 1
            continue
        payload, draft = mapped
        if prescreen and not passes_prescreen(payload.title, payload.summary):
            stats["screened_out"] += 1
            continue
        if stats["created"] >= settings.literature_max_new_per_run:
            stats["truncated"] = True
            return
        try:
            async with session.begin_nested():
                result = await ingest_item(session, payload, paper_draft=draft)
        except Exception:
            stats["errors"] += 1
            log.exception("ingest OpenAlex work failed id=%s", work.get("id"))
            continue
        if result.status == "created" and result.item_id is not None:
            stats["created"] += 1
            stats["created_ids"].append(result.item_id)
        elif result.status == "duplicate":
            stats["duplicate"] += 1
        else:
            stats["errors"] += 1
