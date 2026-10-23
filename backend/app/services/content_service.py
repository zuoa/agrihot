"""Full-text backfill via Jina Reader for items pushed without content.

The crawler is the primary source of full text; this is the server-side
fallback: ingest spawns `enrich_and_score`, which fetches the article through
r.jina.ai (returns clean markdown), stores it, then runs scoring so the
substance/depth dimensions see the real body instead of just the summary.

All failures are best-effort: fetch errors leave content empty and scoring
simply falls back to the summary.
"""
from __future__ import annotations

import logging
from urllib.parse import urlsplit, urlunsplit

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import SessionLocal
from ..models import Item
from . import abstract_translate_service, paper_card_service, runtime_settings, scoring_service

log = logging.getLogger(__name__)

# storage cap: keeps pathological pages from bloating the row
MAX_CONTENT_CHARS = 20000
# shorter than this is nav boilerplate / an error page, not an article
MIN_CONTENT_CHARS = 200

_JINA_TITLE_PREFIX = "Title:"
_JINA_BODY_MARKER = "Markdown Content:"
# This public archive serves the same article paths over HTTP, while its
# HTTPS endpoint currently fails certificate validation in Reader.
_HTTP_SOURCE_HOSTS = frozenset({"nynct.gxzf.gov.cn"})


class FulltextFetchError(Exception):
    def __init__(self, reason: str, upstream_status: int | None = None):
        self.reason = reason
        self.upstream_status = upstream_status
        messages = {
            "source_tls_error": "原文网站的 HTTPS 证书或 TLS 连接异常，无法获取正文。请更换有效原文链接，或通过编辑、推送补交正文。",
            "reader_rate_limited": "正文抓取服务暂时限流，请稍后重试。",
            "reader_blocked": "原文域名被正文抓取服务限制访问，请通过编辑、推送补交正文。",
            "reader_auth_error": "正文抓取服务鉴权失败或无访问权限，请检查抓取服务配置。",
            "reader_quota_exhausted": "正文抓取服务额度不足，请检查抓取服务账户。",
            "reader_timeout": "正文抓取超时，请稍后重试。",
            "reader_unavailable": "无法连接正文抓取服务，请稍后重试。",
            "content_too_short": "抓取结果不足 200 个字符，未识别到有效正文。请检查原文链接，或通过编辑、推送补交正文。",
        }
        message = messages.get(reason, f"正文抓取服务返回 HTTP {upstream_status}，请检查原文链接或稍后重试。")
        super().__init__(message)


def _reader_error(response: httpx.Response) -> FulltextFetchError:
    reasons = {401: "reader_auth_error", 402: "reader_quota_exhausted", 403: "reader_auth_error",
               429: "reader_rate_limited", 451: "reader_blocked"}
    reason = reasons.get(response.status_code, "reader_http_error")
    if reason == "reader_http_error":
        detail = response.text[:8192].lower()
        if any(marker in detail for marker in ("err_cert_", "err_ssl_", "certificate_verify_failed")):
            reason = "source_tls_error"
    return FulltextFetchError(reason, response.status_code)


def _http_source_fallback(url: str) -> str | None:
    parsed = urlsplit(url)
    if (parsed.scheme == "https" and parsed.hostname in _HTTP_SOURCE_HOSTS
            and not parsed.username and not parsed.password and parsed.port in (None, 443)):
        return urlunsplit(parsed._replace(scheme="http", netloc=parsed.hostname, fragment=""))
    return None


def _strip_jina_preamble(text: str) -> str:
    """Drop Jina Reader's metadata header (Title: / URL Source: / Markdown Content:).

    Only touches responses that actually start with the Title: line; anything
    else (e.g. a custom reader endpoint) is returned unchanged.
    """
    if not text.startswith(_JINA_TITLE_PREFIX):
        return text
    idx = text.find(_JINA_BODY_MARKER)
    if idx == -1:
        return text
    return text[idx + len(_JINA_BODY_MARKER):].strip()


async def fetch_fulltext(url: str, *, raise_errors: bool = False) -> str | None:
    """Fetch markdown; background callers get None, manual callers can request diagnostics."""
    if not runtime_settings.get("content_fetch_enabled"):
        return None
    headers = {}
    if settings.jina_api_key:
        headers["Authorization"] = f"Bearer {settings.jina_api_key}"
    try:
        async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
            reader_base = settings.jina_reader_base_url.rstrip('/')
            resp = await client.get(
                f"{reader_base}/{url}", headers=headers
            )
            if resp.is_error and _reader_error(resp).reason == "source_tls_error":
                fallback = _http_source_fallback(url)
                if fallback:
                    log.info("Retrying public article over HTTP after source TLS failure: %s", url)
                    resp = await client.get(f"{reader_base}/{fallback}", headers=headers)
            resp.raise_for_status()
            text = _strip_jina_preamble(resp.text.strip())
        if len(text) < MIN_CONTENT_CHARS:
            raise FulltextFetchError("content_too_short")
        return text[:MAX_CONTENT_CHARS]
    except httpx.HTTPStatusError as exc:
        error = _reader_error(exc.response)
    except httpx.TimeoutException:
        error = FulltextFetchError("reader_timeout")
    except FulltextFetchError as exc:
        error = exc
    except Exception:
        error = FulltextFetchError("reader_unavailable")
    log.warning("Full-text fetch failed for %s: %s (reader_http=%s)", url, error.reason, error.upstream_status)
    if raise_errors:
        raise error from None
    return None


async def enrich_item(session: AsyncSession, item: Item) -> bool:
    """Backfill item.content if empty. True if content was added. Caller commits."""
    if item.content and item.content.strip():
        return False
    text = await fetch_fulltext(item.url)
    if text is None:
        return False
    item.content = text
    log.info("item %s backfilled full text (%d chars)", item.id, len(text))
    return True


async def enrich_and_score(item_id: int) -> None:
    """Background task entry: backfill full text (best effort), then score.

    Opens its own session (the request session is closed by then). Enrichment
    runs even when scoring is disabled; scoring failures stay fail-closed.
    """
    async with SessionLocal() as session:
        item = await session.get(Item, item_id)
        if item is None:
            return
        # 论文已有摘要 / DOI 落地页，不跑 Jina（易 403 且无必要）
        is_paper = item.category == "论文" or item.paper is not None
        if not is_paper:
            await enrich_item(session, item)
            # The fetched source must survive scoring errors and cancellation.
            await session.commit()
        if item.is_selected:
            return
        try:
            if settings.deepseek_api_key:
                if await scoring_service.score_item(session, item) is not None:
                    await scoring_service.refresh_day_selection(session, item.created_at)
                if is_paper:
                    await paper_card_service.fill_card(session, item)
                    await abstract_translate_service.fill_summary_zh(session, item)
            await session.commit()
        except Exception as exc:
            await session.rollback()
            log.warning("Item %s enrichment scoring failed: %s", item_id, type(exc).__name__)


async def save_and_score_content(session: AsyncSession, item: Item, text: str) -> None:
    """Persist each fetched body before attempting optional, best-effort scoring."""
    item_id = item.id
    item.content = text
    await session.commit()
    if settings.deepseek_api_key:
        try:
            if await scoring_service.score_item(session, item) is not None:
                await scoring_service.refresh_day_selection(session, item.created_at)
            await session.commit()
        except Exception as exc:
            await session.rollback()
            log.warning("Full text saved for item %s; rescoring failed: %s", item_id, type(exc).__name__)
    await session.refresh(item)
