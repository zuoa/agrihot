"""Per-source collection, durable progress and health, using the shared ingest path."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import yaml
from sqlalchemy import select

from ..config import settings
from ..database import SessionLocal
from ..models import Item, PipelineState, utcnow
from . import content_service, job_runner, runtime_settings, watchlist_service
from .dedup import url_hash
from .ingest_service import ingest_item
from .openalex_service import passes_prescreen
from .source_adapters import (
    Candidate, Source, get_document, map_crossref, moa_page_count, parse_date,
    parse_feed, parse_moa, payload_for,
)

log = logging.getLogger(__name__)
STATE_PREFIX = "source:"
MAX_PAGES = 5
CROSSREF_ROWS = 50
EXCLUDED_TITLES = re.compile(r"党支部|党建|理论学习|廉政|工会活动|招聘|招聘会|nominations? (?:open|close)", re.I)
JOURNAL_FRONT_MATTER = re.compile(r"^(?:editorial board|contents|table of contents|author index|front matter|back matter|cover image|masthead)$", re.I)


def load_sources() -> list[Source]:
    path = Path(settings.sources_path) if settings.sources_path else Path(__file__).parents[1] / "sources.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    sources = [Source(**raw) for raw in data["sources"]]
    for journal in watchlist_service.get_watchlist().get("journals") or []:
        issn = str(journal.get("issn", "")).strip()
        if not re.fullmatch(r"\d{4}-\d{3}[\dXx]", issn):
            raise ValueError(f"invalid journal ISSN: {issn}")
        sources.append(Source(id=f"crossref-{issn.lower()}", name=f"Crossref · {journal['name']}", kind="crossref",
                              url=f"https://api.crossref.org/journals/{issn}/works"))
    seen = set()
    for source in sources:
        if not re.fullmatch(r"[a-z0-9-]{1,70}", source.id) or source.id in seen:
            raise ValueError(f"invalid or duplicate source id: {source.id}")
        seen.add(source.id)
        if source.enabled and source.kind not in {"rss", "moa", "crossref"}:
            raise ValueError(f"source adapter not implemented: {source.id}")
        if source.interval_minutes < 1:
            raise ValueError(f"invalid source interval: {source.id}")
        if source.category not in {"报道", "论文"}:
            raise ValueError(f"invalid source category: {source.id}")
        ZoneInfo(source.default_timezone)
    return sources


async def read_state(source_id: str) -> dict:
    async with SessionLocal() as session:
        row = await session.get(PipelineState, STATE_PREFIX + source_id)
        if row and row.value:
            return json.loads(row.value)
    return {}


async def write_state(source_id: str, state: dict) -> None:
    async with SessionLocal() as session:
        row = await session.get(PipelineState, STATE_PREFIX + source_id)
        if row is None:
            row = PipelineState(key=STATE_PREFIX + source_id, value="")
            session.add(row)
        row.value, row.updated_at = json.dumps(state, ensure_ascii=False), utcnow()
        await session.commit()


async def list_sources() -> list[dict]:
    async with SessionLocal() as session:
        rows = (await session.scalars(select(PipelineState).where(PipelineState.key.like("source:%")))).all()
        states = {row.key[len(STATE_PREFIX):]: json.loads(row.value) for row in rows}
    return [{"id": s.id, "name": s.name, "kind": s.kind, "url": s.url, "enabled": s.enabled,
             "interval_minutes": s.interval_minutes, "note": s.note, "state": states.get(s.id, {})}
            for s in load_sources()]


def window_start(state: dict, now: datetime) -> datetime:
    last = parse_date(state.get("watermark", ""))
    if last:
        return last - timedelta(days=int(runtime_settings.get("sources_lookback_days")))
    return now - timedelta(days=int(runtime_settings.get("sources_bootstrap_days")))


def eligible(candidate: Candidate, now: datetime) -> bool:
    return ((candidate.paper is not None or candidate.published_at <= now + timedelta(days=1))
            and not EXCLUDED_TITLES.search(candidate.title)
            and not JOURNAL_FRONT_MATTER.fullmatch(candidate.title.strip()))


async def fetch_page(client: httpx.AsyncClient, source: Source, window: dict) -> tuple[list[Candidate], int, str | None]:
    """Return a page and its next cursor. None means the window is complete."""
    if source.kind == "crossref":
        cursor = window.get("cursor") or "*"
        since = parse_date(window["since"]).strftime("%Y-%m-%dT%H:%M:%S")
        until = parse_date(window["until"]).strftime("%Y-%m-%dT%H:%M:%S")
        params = {"filter": f"type:journal-article,from-created-date:{since},until-created-date:{until}",
                  "rows": CROSSREF_ROWS, "cursor": cursor, "mailto": settings.openalex_mailto}
        response = await get_document(client, source.url, params=params)
        message = response.json()["message"]
        works = message["items"]
        if not isinstance(works, list):
            raise ValueError("invalid_crossref_page")
        mapped = [map_crossref(work, source) for work in works]
        next_cursor = message.get("next-cursor") if len(works) == CROSSREF_ROWS else None
        if len(works) == CROSSREF_ROWS and (not next_cursor or next_cursor == cursor):
            raise ValueError("crossref_cursor_stalled")
        return [c for c in mapped if c], sum(c is None for c in mapped), next_cursor
    page = int(window.get("cursor") or 0)
    url = source.url if not page else source.url.rstrip("/") + f"/index_{page}.htm"
    response = await get_document(client, url)
    if response.url.host not in source.hosts:
        raise ValueError("unexpected_source_redirect")
    if source.kind == "rss":
        candidates, rejected = parse_feed(response.content, source)
        if not candidates:
            raise ValueError("no_valid_feed_articles")
        return candidates, rejected, None
    candidates, rejected = parse_moa(response.content, source)
    if not candidates:
        raise ValueError("no_valid_moa_articles")
    since = parse_date(window["since"])
    older_page = bool(candidates) and max(c.published_at for c in candidates) < since
    more = page + 1 < moa_page_count(response.content) and not older_page
    return candidates, rejected, str(page + 1) if more else None


async def collect_source(source: Source, client: httpx.AsyncClient, *, now: datetime,
                         dry_run: bool = False, preview_limit: int = 5) -> dict:
    state = {} if dry_run else await read_state(source.id)
    stats = {"id": source.id, "fetched": 0, "created": 0, "duplicate": 0,
             "screened_out": 0, "rejected": 0, "errors": 0, "truncated": False}
    previews = []
    # Reuse the bounded window until every page has been committed. A new
    # window uses overlap, so late discoveries and list shifts can be replayed.
    window = state.get("window") or {"since": window_start(state, now).isoformat(), "until": now.isoformat(), "cursor": None}
    created_ids = []
    limit = int(runtime_settings.get("sources_max_new_per_source"))
    complete = False
    try:
        for _ in range(MAX_PAGES):
            try:
                candidates, rejected, next_cursor = await fetch_page(client, source, window)
            except httpx.HTTPStatusError as exc:
                # Expired Crossref cursors must replay this same time window.
                if source.kind == "crossref" and window.get("cursor") and exc.response.status_code in (400, 404):
                    window["cursor"] = None
                raise
            stats["fetched"] += len(candidates)
            stats["rejected"] += rejected
            since = parse_date(window["since"])
            for candidate in sorted(candidates, key=lambda c: c.published_at):
                if (not eligible(candidate, now)
                        or (source.kind != "crossref" and candidate.published_at < since)
                        or (source.keywords and not passes_prescreen(candidate.title, candidate.summary, extra=source.keywords))):
                    stats["screened_out"] += 1
                    continue
                if dry_run:
                    payload = await payload_for(candidate, source, client)
                    previews.append({"title": payload.title, "url": payload.url,
                                     "published_at": payload.published_at.isoformat(),
                                     "summary_chars": len(payload.summary), "content_chars": len(payload.content or "")})
                    if len(previews) >= preview_limit:
                        break
                    continue
                # Check before network I/O; replays should not refetch MOA bodies.
                async with SessionLocal() as session:
                    existing = await session.scalar(select(Item.id).where(Item.url_hash == url_hash(candidate.url)))
                if existing is not None and source.kind != "crossref":
                    stats["duplicate"] += 1
                    continue
                # At the cap, replay this page next run. Existing records are
                # still processed above, allowing a finite feed to drain.
                if stats["created"] >= limit:
                    stats["truncated"] = True
                    break
                try:
                    payload = await payload_for(candidate, source, client)
                    async with SessionLocal() as session:
                        result = await ingest_item(session, payload, pushed_by=f"source:{source.id}", paper_draft=candidate.paper)
                        await session.commit()
                    if result.status == "created":
                        stats["created"] += 1
                        created_ids.append(result.item_id)
                    elif result.status == "duplicate":
                        stats["duplicate"] += 1
                    else:
                        raise ValueError("source_ingest_invalid")
                except Exception as exc:
                    stats["errors"] += 1
                    stats["error"] = f"HTTP {exc.response.status_code}" if isinstance(exc, httpx.HTTPStatusError) else f"{type(exc).__name__}: {str(exc)[:200]}"
                    stats["failed_urls"] = [*(stats.get("failed_urls") or []), candidate.url][-10:]
                    log.warning("source %s article failed: %s", source.id, stats["error"])
            if dry_run and len(previews) >= preview_limit:
                break
            if stats["truncated"] or stats["errors"]:
                break
            if next_cursor is None:
                complete = True
                break
            window = {**window, "cursor": next_cursor}
            if not dry_run:
                state["window"] = window
                await write_state(source.id, state)
            await asyncio.sleep(0.2)
        if not complete and not dry_run:
            stats["truncated"] = True
    except Exception as exc:
        stats["errors"] += 1
        stats["error"] = f"HTTP {exc.response.status_code}" if isinstance(exc, httpx.HTTPStatusError) else type(exc).__name__ + ": " + str(exc)[:200]
        log.warning("source %s failed: %s", source.id, stats["error"])

    if dry_run:
        return {**stats, "previews": previews}
    if complete:
        state["watermark"] = window["until"]
        state["last_success_at"] = now.isoformat()
        state.pop("window", None)
    else:
        state["window"] = window
    totals = dict(state.get("totals") or {})
    totals["runs"] = totals.get("runs", 0) + 1
    totals["failed_runs"] = totals.get("failed_runs", 0) + bool(stats["errors"])
    for key in ("created", "duplicate", "screened_out", "rejected"):
        totals[key] = totals.get(key, 0) + stats[key]
    state["totals"] = totals
    state.update(last_checked_at=now.isoformat(), status="error" if stats["errors"] else "partial" if stats["truncated"] else "ok", stats=stats)
    await write_state(source.id, state)
    # Enrichment cannot undo ingested records or collection checkpoints. On a
    # restart the existing unscored/content backfill jobs handle saved records.
    for item_id in created_ids:
        try:
            await content_service.enrich_and_score(item_id)
        except Exception:
            log.exception("source enrichment failed item=%s", item_id)
    return stats


async def run_once(*, force: bool = True, dry_run: bool = False, source_id: str | None = None,
                   preview_limit: int = 5, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if not dry_run:
        async with SessionLocal() as session:
            await runtime_settings.load(session)
            await watchlist_service.load_from_db(session)
    sources = [s for s in load_sources() if s.enabled and (source_id is None or s.id == source_id)]
    if source_id is not None and not sources:
        raise ValueError(f"unknown or disabled source: {source_id}")
    results = []
    async with httpx.AsyncClient(timeout=30, follow_redirects=True,
                                 headers={"User-Agent": f"AgriHot/1.0 (mailto:{settings.openalex_mailto})"}) as client:
        for source in sources:
            state = {} if dry_run else await read_state(source.id)
            checked = parse_date(state.get("last_checked_at", ""))
            if not force and checked and now < checked + timedelta(minutes=source.interval_minutes):
                continue
            result = await collect_source(source, client, now=now, dry_run=dry_run, preview_limit=preview_limit)
            results.append(result)
            if not dry_run:
                await job_runner.append_log("sources_fetch", stage="sources", message=f"{source.name}：新增 {result['created']}，重复 {result['duplicate']}，错误 {result['errors']}",
                                            level="warning" if result["errors"] else "info", details=result)
    return {"sources": results, **{key: sum(r[key] for r in results) for key in
            ("fetched", "created", "duplicate", "screened_out", "rejected", "errors")},
            "truncated": any(r["truncated"] for r in results)}
