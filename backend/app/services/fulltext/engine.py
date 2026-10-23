"""Strategy registry, bounded fallbacks, and result validation."""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import replace
from urllib.parse import urlsplit, urlunsplit

import httpx

from .base import (MIN_CONTENT_CHARS, FetchAttempt, FetchContext, FetchOptions,
                   FetchResult, FulltextFetcher, FulltextFetchError, validate_public_source)
from .fetchers import (DoiFetcher, FrontiersFetcher, GovernmentHtmlFetcher,
                       HtmlFetcher, JatsXmlFetcher, JinaFetcher, PdfFetcher)

log = logging.getLogger(__name__)


def default_fetchers() -> list[FulltextFetcher]:
    return [DoiFetcher(), PdfFetcher(), JatsXmlFetcher(), FrontiersFetcher(),
            GovernmentHtmlFetcher(), HtmlFetcher(), JinaFetcher()]


def normalize_url(url: str) -> str:
    try:
        parsed = urlsplit(url.strip())
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or any(ord(c) < 32 for c in url)):
            raise ValueError
        _ = parsed.port
        return urlunsplit(parsed._replace(fragment=""))
    except (TypeError, ValueError, AttributeError):
        raise FulltextFetchError("invalid_url") from None


def validate_text(text: str) -> str:
    text = re.sub(r"\n{4,}", "\n\n\n", text.replace("\x00", "")).strip()
    if len(text) < MIN_CONTENT_CHARS:
        raise FulltextFetchError("content_too_short")
    if len(text) < 4000 and re.search(r"^(?:#*\s*)?(?:access denied|just a moment|verify you are human|checking your browser|请完成验证)", text[:500], re.I):
        raise FulltextFetchError("content_access_denied")
    return text


class FulltextEngine:
    """Register fetchers with a priority; unsupported or failed methods fall through."""

    def __init__(self, fetchers=None, *, options: FetchOptions | None = None,
                 transport: httpx.AsyncBaseTransport | None = None, validator=validate_public_source):
        self.fetchers: list[FulltextFetcher] = []
        for fetcher in default_fetchers() if fetchers is None else fetchers:
            self.register(fetcher)
        self.options, self.transport, self.validator = options or FetchOptions(), transport, validator

    def register(self, fetcher: FulltextFetcher) -> None:
        self.fetchers.append(fetcher)
        self.fetchers.sort(key=lambda candidate: candidate.priority)

    async def fetch(self, url: str, *, alternative_urls=()) -> FetchResult:
        candidates, invalid = [], []
        for candidate in (url, *alternative_urls):
            if not candidate:
                continue
            try:
                normalized = normalize_url(candidate)
            except FulltextFetchError:
                invalid.append(FetchAttempt("url", "", "invalid_url"))
                continue
            if normalized not in candidates:
                candidates.append(normalized)
            if len(candidates) >= 8:
                break
        if not candidates:
            raise FulltextFetchError("invalid_url")
        async with httpx.AsyncClient(transport=self.transport, headers={"User-Agent": "AgriHot/1.0 (+https://agrihot.com)"}) as client:
            context = FetchContext(client, self.options, validator=self.validator, attempts=invalid)
            context.follow = lambda target: self._fetch_url(normalize_url(target), context)
            try:
                async with asyncio.timeout(self.options.timeout):
                    for candidate in candidates:
                        try:
                            result = await self._fetch_url(candidate, context)
                            return replace(result, attempts=tuple(context.attempts))
                        except FulltextFetchError:
                            continue
            except TimeoutError:
                error = FulltextFetchError("fetch_timeout")
                error.attempts = tuple(context.attempts)
                raise error from None
            if context.attempts:
                last = context.attempts[-1]
                error = FulltextFetchError(last.reason, last.upstream_status)
            else:
                error = FulltextFetchError("unsupported_content")
            error.attempts = tuple(context.attempts)
            raise error

    async def _fetch_url(self, url: str, context: FetchContext) -> FetchResult:
        if url in context.active_urls or len(context.active_urls) >= 6:
            raise FulltextFetchError("doi_resolution_failed")
        context.active_urls.add(url)
        last_error = FulltextFetchError("unsupported_content")
        try:
            for fetcher in self.fetchers:
                try:
                    if not fetcher.supports(url):
                        continue
                    result = await fetcher.fetch(url, context)
                    text = validate_text(result.text)
                    result = replace(result, text=text[:self.options.max_chars],
                                     truncated=result.truncated or len(text) > self.options.max_chars)
                    log.info("Full text fetched: method=%s chars=%s truncated=%s source=%s",
                             result.fetcher, len(result.text), result.truncated, result.source_url)
                    return result
                except asyncio.CancelledError:
                    raise
                except FulltextFetchError as error:
                    last_error = error
                except Exception as error:
                    log.warning("Full-text parser failed: method=%s error=%s", fetcher.name, type(error).__name__)
                    last_error = FulltextFetchError("fetcher_failed")
                context.attempts.append(FetchAttempt(fetcher.name, url, last_error.reason, last_error.upstream_status))
            raise last_error
        finally:
            context.active_urls.remove(url)
