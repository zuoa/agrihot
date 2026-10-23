"""URL-specific retrieval strategies. All implementations share one request context."""
from __future__ import annotations

import asyncio
import re
from dataclasses import replace
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

import httpx

from ..doi import normalize_doi
from .base import MIN_CONTENT_CHARS, FetchAttempt, FetchContext, FetchResult, FulltextFetcher, FulltextFetchError
from .extractors import article_links, extract_html, extract_jats, extract_pdf

DOI_HOSTS = frozenset({"doi.org", "dx.doi.org"})
HTTP_SOURCE_HOSTS = frozenset({"nynct.gxzf.gov.cn"})


def is_doi_url(url: str) -> bool:
    return urlsplit(url).hostname in DOI_HOSTS


def http_source_fallback(url: str) -> str | None:
    parsed = urlsplit(url)
    if (parsed.scheme == "https" and parsed.hostname in HTTP_SOURCE_HOSTS
            and not parsed.username and not parsed.password and parsed.port in (None, 443)):
        return urlunsplit(parsed._replace(scheme="http", netloc=parsed.hostname, fragment=""))
    return None


def reader_error(response: httpx.Response) -> FulltextFetchError:
    reasons = {401: "reader_auth_error", 402: "reader_quota_exhausted", 403: "reader_forbidden",
               429: "reader_rate_limited", 451: "reader_blocked"}
    reason = reasons.get(response.status_code, "reader_http_error")
    if response.status_code == 403:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if isinstance(payload, dict):
            if str(payload.get("status")) == "40305" or payload.get("name") == "AbuseAlleviationError":
                reason = "reader_domain_blocked"
            elif payload.get("name") == "AuthenticationRequiredError":
                reason = "reader_auth_error"
    if reason == "reader_http_error":
        detail = response.text[:8192].lower()
        if any(marker in detail for marker in ("err_cert_", "err_ssl_", "certificate_verify_failed")):
            reason = "source_tls_error"
    return FulltextFetchError(reason, response.status_code)


def strip_jina_preamble(text: str) -> str:
    if text.startswith("Title:") and (position := text.find("Markdown Content:")) != -1:
        return text[position + len("Markdown Content:"):].strip()
    return text


def require_success(response: httpx.Response) -> None:
    if response.is_error:
        raise FulltextFetchError("source_http_error", response.status_code)


async def document_result(response: httpx.Response, name: str) -> FetchResult:
    require_success(response)
    mime = response.headers.get("content-type", "").split(";", 1)[0].lower()
    content, url = response.content, str(response.url)
    if content.lstrip().startswith(b"%PDF"):
        text = await asyncio.to_thread(extract_pdf, content)
        name += "/pdf"
    elif "xml" in mime and "xhtml" not in mime:
        text = await asyncio.to_thread(extract_jats, content)
        name += "/xml"
    elif mime in {"text/plain", "text/markdown"}:
        text = response.text
    elif "html" in mime or content.lstrip().lower().startswith((b"<!doctype html", b"<html")):
        text = await asyncio.to_thread(extract_html, content, url)
    else:
        raise FulltextFetchError("unsupported_content")
    return FetchResult(text, url, name)


async def linked_document_result(response: httpx.Response, context: FetchContext, name: str) -> FetchResult | None:
    """Publisher citation metadata also makes non-specialized journal sites usable."""
    links = article_links(response.content, str(response.url))
    for kind, extract_document in (("xml", extract_jats), ("pdf", extract_pdf)):
        target = links.get(kind)
        if not target:
            continue
        try:
            resource = await context.get(target)
            require_success(resource)
            text = await asyncio.to_thread(extract_document, resource.content)
            if len(text.strip()) < MIN_CONTENT_CHARS:
                raise FulltextFetchError("content_too_short")
            return FetchResult(text, str(resource.url), f"{name}_{kind}")
        except FulltextFetchError as error:
            context.attempts.append(FetchAttempt(f"{name}_{kind}", target, error.reason, error.upstream_status))
    return None


class DoiFetcher(FulltextFetcher):
    name, priority = "doi", 0

    def supports(self, url: str) -> bool:
        return is_doi_url(url)

    async def fetch(self, url: str, context: FetchContext) -> FetchResult:
        doi = normalize_doi(unquote(url))
        if not doi:
            raise FulltextFetchError("doi_resolution_failed")
        resolver = "https://doi.org/" + quote(doi, safe="/():;._-")
        target = None
        # Only follow DOI-service redirects here; the engine handles the publisher URL.
        for _ in range(3):
            try:
                response = await context.get(resolver, follow_redirects=False)
            except FulltextFetchError:
                break
            if not response.is_redirect or not response.headers.get("location"):
                break
            candidate = urljoin(resolver, response.headers["location"])
            if not is_doi_url(candidate):
                target = candidate
                break
            resolver = candidate
        if not target:
            try:
                response = await context.get("https://api.crossref.org/works/" + quote(doi, safe="/"))
                require_success(response)
                metadata = response.json()["message"]
                target = metadata.get("resource", {}).get("primary", {}).get("URL")
            except FulltextFetchError as error:
                raise FulltextFetchError("doi_resolution_failed", error.upstream_status) from None
            except (ValueError, TypeError, KeyError, AttributeError):
                raise FulltextFetchError("doi_resolution_failed", response.status_code) from None
        if not target or is_doi_url(target) or context.follow is None:
            raise FulltextFetchError("doi_resolution_failed")
        result = await context.follow(target)
        return replace(result, fetcher=f"{self.name}>{result.fetcher}")


class PdfFetcher(FulltextFetcher):
    name, priority = "pdf", 10

    def supports(self, url: str) -> bool:
        path = urlsplit(url).path.lower().rstrip("/")
        return not is_doi_url(url) and (path.endswith(".pdf") or path.endswith("/pdf"))

    async def fetch(self, url: str, context: FetchContext) -> FetchResult:
        response = await context.get(url)
        require_success(response)
        text = await asyncio.to_thread(extract_pdf, response.content)
        return FetchResult(text, str(response.url), self.name)


class JatsXmlFetcher(FulltextFetcher):
    name, priority = "jats_xml", 15

    def supports(self, url: str) -> bool:
        path = urlsplit(url).path.lower().rstrip("/")
        return not is_doi_url(url) and path.endswith((".xml", "/xml", "/xml/nlm", "/fulltextxml"))

    async def fetch(self, url: str, context: FetchContext) -> FetchResult:
        response = await context.get(url)
        require_success(response)
        text = await asyncio.to_thread(extract_jats, response.content)
        return FetchResult(text, str(response.url), self.name)


class FrontiersFetcher(FulltextFetcher):
    name, priority = "frontiers", 20

    def supports(self, url: str) -> bool:
        return urlsplit(url).hostname in {"frontiersin.org", "www.frontiersin.org"}

    async def fetch(self, url: str, context: FetchContext) -> FetchResult:
        response = await context.get(url)
        require_success(response)
        if "xml" in response.headers.get("content-type", "") or response.content.lstrip().startswith(b"%PDF"):
            return await document_result(response, self.name)
        if result := await linked_document_result(response, context, self.name):
            return result
        return await document_result(response, self.name)


class GovernmentHtmlFetcher(FulltextFetcher):
    name, priority = "government_html", 30

    def supports(self, url: str) -> bool:
        return (urlsplit(url).hostname or "").endswith(".gov.cn")

    async def fetch(self, url: str, context: FetchContext) -> FetchResult:
        try:
            response = await context.get(url)
        except FulltextFetchError as error:
            fallback = http_source_fallback(url) if error.reason == "source_tls_error" else None
            if not fallback:
                raise
            response = await context.get(fallback)
        return await document_result(response, self.name)


class HtmlFetcher(FulltextFetcher):
    name, priority = "html", 90

    def supports(self, url: str) -> bool:
        return urlsplit(url).scheme in {"http", "https"} and not is_doi_url(url)

    async def fetch(self, url: str, context: FetchContext) -> FetchResult:
        response = await context.get(url)
        require_success(response)
        if "html" in response.headers.get("content-type", ""):
            if result := await linked_document_result(response, context, self.name):
                return result
        return await document_result(response, self.name)


class JinaFetcher(FulltextFetcher):
    name, priority = "jina", 100

    def supports(self, url: str) -> bool:
        return urlsplit(url).scheme in {"http", "https"} and not is_doi_url(url)

    async def fetch(self, url: str, context: FetchContext) -> FetchResult:
        headers = {"Authorization": f"Bearer {context.options.jina_api_key}"} if context.options.jina_api_key else {}
        base = context.options.jina_base_url.rstrip("/")
        response = await context.get(f"{base}/{url}", headers=headers, trusted=True, timeout=45)
        source_url = url
        if response.is_error and reader_error(response).reason == "source_tls_error":
            fallback = http_source_fallback(url)
            if fallback:
                source_url = fallback
                response = await context.get(f"{base}/{fallback}", headers=headers, trusted=True, timeout=45)
        if response.is_error:
            raise reader_error(response)
        if re.search(r"^Warning:.*(?:returned error [45]\d\d|captcha|verification)", response.text[:2500], re.I | re.M):
            raise FulltextFetchError("content_access_denied")
        return FetchResult(strip_jina_preamble(response.text.strip()), source_url, self.name)
