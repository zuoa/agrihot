"""Publisher PDF discovery, bounded download and durable file storage."""
from __future__ import annotations

import asyncio
import hashlib
import io
import os
import re
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit

import httpx
from lxml import html
from pypdf import PdfReader

from ..config import settings
from .doi import normalize_doi
from .fulltext.base import FetchContext, FetchOptions, FulltextFetchError
from .fulltext.extractors import article_links, extract_pdf
from .fulltext.fetchers import require_success


@dataclass(frozen=True)
class PdfDownload:
    data: bytes
    url: str
    plugin: str


class PdfPlugin:
    name = "generic"

    def supports(self, url: str) -> bool:
        return True

    def candidates(self, url: str, page: bytes) -> list[str]:
        """Return links advertised by the publisher page."""
        links = article_links(page, url)
        candidates = [links["pdf"]] if links.get("pdf") else []
        try:
            root = html.fromstring(page)
        except (ValueError, html.etree.ParserError):
            return candidates
        for href in root.xpath("//a/@href"):
            target = urljoin(url, href.strip())
            path = urlsplit(target).path.lower()
            if path.endswith(".pdf") or path.endswith("/pdf") or "/article/pdf/" in path:
                candidates.append(target)
        return list(dict.fromkeys(candidates))[:12]


class ArxivPlugin(PdfPlugin):
    name = "arxiv"

    def supports(self, url: str) -> bool:
        return urlsplit(url).hostname == "arxiv.org"

    def candidates(self, url: str, page: bytes) -> list[str]:
        path = urlsplit(url).path
        direct = ["https://arxiv.org/pdf/" + path.removeprefix("/abs/")]
        return list(dict.fromkeys([*direct, *super().candidates(url, page)])) if path.startswith("/abs/") else super().candidates(url, page)


class NaturePlugin(PdfPlugin):
    name = "nature"

    def supports(self, url: str) -> bool:
        return urlsplit(url).hostname in {"nature.com", "www.nature.com"}

    def candidates(self, url: str, page: bytes) -> list[str]:
        paths = super().candidates(url, page)
        article_path = urlsplit(url).path
        if article_path.startswith("/articles/") and not article_path.endswith(".pdf"):
            article_url = url.split("?", 1)[0].rstrip("/")
            paths.extend((article_url + ".pdf", article_url + "_reference.pdf"))
        return list(dict.fromkeys(paths))


class MdpiPlugin(PdfPlugin):
    name = "mdpi"

    def supports(self, url: str) -> bool:
        return urlsplit(url).hostname in {"mdpi.com", "www.mdpi.com"}

    def candidates(self, url: str, page: bytes) -> list[str]:
        paths = super().candidates(url, page)
        if not urlsplit(url).path.endswith("/pdf"):
            paths.append(url.split("?", 1)[0].rstrip("/") + "/pdf")
        return list(dict.fromkeys(paths))


class FrontiersPlugin(PdfPlugin):
    name = "frontiers"

    def supports(self, url: str) -> bool:
        return urlsplit(url).hostname in {"frontiersin.org", "www.frontiersin.org"}

    def candidates(self, url: str, page: bytes) -> list[str]:
        paths = super().candidates(url, page)
        path = urlsplit(url).path
        if path.endswith(("/full", "/abstract")):
            paths.append(url.rsplit("/", 1)[0] + "/pdf")
        return list(dict.fromkeys(paths))


class AeeispPlugin(PdfPlugin):
    name = "aeeisp"

    def supports(self, url: str) -> bool:
        return urlsplit(url).hostname in {"aeeisp.com", "www.aeeisp.com", "tcsae.org", "www.tcsae.org"}

    def candidates(self, url: str, page: bytes) -> list[str]:
        paths = super().candidates(url, page)
        parsed = urlsplit(url)
        if parsed.hostname == "www.aeeisp.com" and "/article/doi/" in parsed.path:
            journal, doi = parsed.path.split("/article/doi/", 1)
            paths.append(f"https://www.aeeisp.com{journal}/cn/article/pdf/preview/{doi}.pdf")
        return list(dict.fromkeys(paths))


PLUGINS = (ArxivPlugin(), NaturePlugin(), MdpiPlugin(), FrontiersPlugin(), AeeispPlugin(), PdfPlugin())
MDPI_SLUGS = {"applied sciences": "applsci"}


def plugin_for(url: str) -> PdfPlugin:
    return next(plugin for plugin in PLUGINS if plugin.supports(url))


def is_pdf(data: bytes) -> bool:
    return data.lstrip().startswith(b"%PDF-") and b"%%EOF" in data[-2048:]


def is_access_challenge(data: bytes) -> bool:
    sample = data[:4096].lower()
    return b"<title>client challenge" in sample or b"_fs-ch-" in sample


def validate_pdf(data: bytes) -> None:
    if not is_pdf(data):
        raise FulltextFetchError("unsupported_content")
    try:
        if len(PdfReader(io.BytesIO(data), strict=False).pages) < 1:
            raise FulltextFetchError("unsupported_content")
    except FulltextFetchError:
        raise
    except Exception:
        raise FulltextFetchError("unsupported_content") from None


def _mdpi_record_urls(record: dict) -> list[str]:
    doi = normalize_doi(record.get("DOI"))
    if not doi or not doi.startswith("10.3390/"):
        return []
    volume = str(record.get("volume") or "")
    number = str(record.get("article-number") or record.get("page") or "").split("-", 1)[0]
    if not volume.isdecimal() or not number.isdecimal():
        return []
    title = str((record.get("container-title") or [""])[0]).lower()
    doi_code = re.match(r"10\.3390/([a-z]+)\d", doi)
    slugs = dict.fromkeys(filter(None, (
        MDPI_SLUGS.get(title), re.sub(r"[^a-z0-9]", "", title),
        doi_code.group(1) if doi_code else None,
    )))
    return [
        f"https://mdpi-res.com/d_attachment/{slug}/{slug}-{int(volume):02d}-{int(number):05d}"
        f"/article_deploy/{slug}-{int(volume):02d}-{int(number):05d}.pdf"
        for slug in slugs
    ]


async def _mdpi_cdn_candidates(context: FetchContext, doi: str) -> list[str]:
    """Find MDPI's public PDF CDN path when its article host blocks this server."""
    if not doi.startswith("10.3390/"):
        return []
    try:
        response = await context.get("https://api.crossref.org/works/" + quote(doi, safe="/"),
                                     headers={"User-Agent": f"AgriHot/1.0 (mailto:{settings.openalex_mailto})"})
        if response.status_code != 200:
            return []
        record = response.json()["message"]
        if normalize_doi(record.get("DOI")) != doi:
            return []
        return _mdpi_record_urls(record)
    except (FulltextFetchError, ValueError, KeyError, TypeError, AttributeError):
        return []


async def _mdpi_url_cdn_candidates(context: FetchContext, urls: list[str]) -> list[str]:
    """Resolve an MDPI article without a stored DOI using exact Crossref metadata."""
    for url in urls:
        if not MdpiPlugin().supports(url):
            continue
        match = re.fullmatch(r"/(\d{4}-\d{3}[\dXx])/(\d+)/(\d+)/(\d+)(?:/pdf)?/?", urlsplit(url).path)
        if not match:
            continue
        issn, volume, issue, number = match.groups()
        try:
            query = quote(f"{volume} {issue} {number}")
            response = await context.get(
                f"https://api.crossref.org/journals/{issn}/works?query.bibliographic={query}&rows=5",
                headers={"User-Agent": f"AgriHot/1.0 (mailto:{settings.openalex_mailto})"},
            )
            if response.status_code != 200:
                continue
            for record in response.json()["message"]["items"]:
                candidate_number = str(record.get("article-number") or record.get("page") or "").split("-", 1)[0]
                if ("mdpi" in str(record.get("publisher") or "").lower()
                        and issn.upper() in [str(value).upper() for value in record.get("ISSN") or []]
                        and str(record.get("volume") or "").isdecimal()
                        and str(record.get("issue") or "").isdecimal()
                        and candidate_number.isdecimal()
                        and int(record["volume"]) == int(volume)
                        and int(record["issue"]) == int(issue)
                        and int(candidate_number) == int(number)):
                    return _mdpi_record_urls(record)
        except (FulltextFetchError, ValueError, KeyError, TypeError, AttributeError):
            continue
    return []


def _aeeisp_standard_download(url: str, max_bytes: int) -> bytes:
    """aeeisp currently serves its public PDF to urllib but redirects httpx to CAPTCHA."""
    class SameHostRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            target = urljoin(request.full_url, newurl)
            if "/captcha/" in urlsplit(target).path:
                raise FulltextFetchError("content_access_denied")
            if urlsplit(target).scheme != "https" or urlsplit(target).hostname != "www.aeeisp.com":
                raise FulltextFetchError("source_not_public")
            return super().redirect_request(request, fp, code, msg, headers, target)

    if urlsplit(url).scheme != "https" or urlsplit(url).hostname != "www.aeeisp.com":
        raise FulltextFetchError("invalid_url")
    opener = urllib.request.build_opener(SameHostRedirect())
    try:
        with opener.open(url, timeout=settings.paper_pdf_timeout) as response:
            declared = response.headers.get("Content-Length", "")
            if declared.isdecimal() and int(declared) > max_bytes:
                raise FulltextFetchError("content_too_large")
            data = response.read(max_bytes + 1)
    except FulltextFetchError as exc:
        if exc.reason != "content_access_denied":
            raise
        data = _aeeisp_curl_download(url, max_bytes)
    except (urllib.error.URLError, TimeoutError, OSError):
        data = _aeeisp_curl_download(url, max_bytes)
    if len(data) > max_bytes:
        raise FulltextFetchError("content_too_large")
    if not is_pdf(data) and b"captcha" in data[:4096].lower():
        data = _aeeisp_curl_download(url, max_bytes)
    if not is_pdf(data):
        raise FulltextFetchError("content_access_denied" if b"captcha" in data[:4096].lower() else "unsupported_content")
    return data


def _aeeisp_curl_download(url: str, max_bytes: int) -> bytes:
    """The public aeeisp endpoint currently serves curl while Python clients get CAPTCHA."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as output:
        name = output.name
    try:
        completed = subprocess.run(
            ["curl", "--silent", "--show-error", "--fail", "--proto", "=https",
             "--max-time", str(int(settings.paper_pdf_timeout)), "--max-filesize", str(max_bytes),
             "--output", name, url], capture_output=True, timeout=settings.paper_pdf_timeout + 5,
        )
        if completed.returncode != 0:
            reason = {22: "content_access_denied", 63: "content_too_large", 28: "source_timeout"}.get(completed.returncode, "source_unavailable")
            raise FulltextFetchError(reason)
        if os.path.getsize(name) > max_bytes:
            raise FulltextFetchError("content_too_large")
        with open(name, "rb") as file:
            data = file.read(max_bytes + 1)
        if not is_pdf(data):
            raise FulltextFetchError("content_access_denied" if b"captcha" in data[:4096].lower() else "unsupported_content")
        return data
    except (OSError, subprocess.TimeoutExpired):
        raise FulltextFetchError("source_unavailable") from None
    finally:
        os.unlink(name)


def _nature_standard_download(url: str, max_bytes: int) -> bytes:
    """Nature serves its public reference manuscript to urllib while challenging httpx."""
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != "www.nature.com"
            or parsed.username or parsed.password or parsed.port is not None
            or not re.fullmatch(r"/articles/[a-zA-Z0-9-]+_reference\.pdf", parsed.path)):
        raise FulltextFetchError("invalid_url")

    class SameHostRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            target = urlsplit(urljoin(request.full_url, newurl))
            if (target.scheme != "https" or target.hostname != "www.nature.com"
                    or target.username or target.password or target.port is not None):
                raise FulltextFetchError("source_not_public")
            return super().redirect_request(request, fp, code, msg, headers, newurl)

    opener = urllib.request.build_opener(SameHostRedirect())
    try:
        with opener.open(url, timeout=settings.paper_pdf_timeout) as response:
            declared = response.headers.get("Content-Length", "")
            if declared.isdecimal() and int(declared) > max_bytes:
                raise FulltextFetchError("content_too_large")
            data = response.read(max_bytes + 1)
    except FulltextFetchError:
        raise
    except urllib.error.HTTPError as exc:
        raise FulltextFetchError("source_http_error", exc.code) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise FulltextFetchError("source_unavailable") from None
    if len(data) > max_bytes:
        raise FulltextFetchError("content_too_large")
    if not is_pdf(data):
        raise FulltextFetchError("content_access_denied" if is_access_challenge(data) else "unsupported_content")
    return data


async def download_pdf(urls: list[str], *, doi: str | None = None, transport: httpx.AsyncBaseTransport | None = None,
                       validator=None) -> PdfDownload:
    """Try known OA links and publisher pages without trusting URL suffixes."""
    from .fulltext.base import validate_public_source
    options = FetchOptions(timeout=settings.paper_pdf_timeout, max_bytes=settings.paper_pdf_max_bytes)
    async with httpx.AsyncClient(transport=transport, headers={"User-Agent": "AgriHot/1.0 (+https://agrihot.com)"}) as client:
        context = FetchContext(client, options, validator=validator or validate_public_source)
        async with asyncio.timeout(options.timeout):
            last = FulltextFetchError("unsupported_content")

            def remember(error: FulltextFetchError) -> None:
                nonlocal last
                if last.reason != "content_too_large" or error.reason == "content_too_large":
                    last = error

            seen: set[str] = set()
            normalized = normalize_doi(doi)
            candidates = [*(await _mdpi_cdn_candidates(context, normalized) if normalized else []),
                          *(await _mdpi_url_cdn_candidates(context, urls) if not normalized else []), *urls]
            checked_openalex = False
            index = 0
            while index < len(candidates) or (doi and not checked_openalex):
                if index >= len(candidates):
                    checked_openalex = True
                    if normalized:
                        try:
                            metadata = await context.get("https://api.openalex.org/works/https://doi.org/" + quote(normalized, safe="/"))
                            if metadata.status_code == 200:
                                work = metadata.json()
                                locations = [work.get("best_oa_location") or {}, work.get("primary_location") or {}, *(work.get("locations") or [])]
                                candidates.extend(location.get("pdf_url") for location in locations if location and location.get("is_oa") and location.get("pdf_url"))
                        except (FulltextFetchError, ValueError, AttributeError):
                            pass
                    continue
                source = candidates[index]
                index += 1
                if not source or source in seen:
                    continue
                seen.add(source)
                candidates.extend(target for target in plugin_for(source).candidates(source, b"") if target not in seen)
                if transport is None and urlsplit(source).hostname == "www.nature.com" and urlsplit(source).path.endswith("_reference.pdf"):
                    try:
                        data = await asyncio.to_thread(_nature_standard_download, source, options.max_bytes)
                        return PdfDownload(data, source, "nature")
                    except FulltextFetchError as exc:
                        remember(exc)
                if transport is None and urlsplit(source).hostname == "www.aeeisp.com" and urlsplit(source).path.lower().endswith(".pdf"):
                    try:
                        data = await asyncio.to_thread(_aeeisp_standard_download, source, options.max_bytes)
                        return PdfDownload(data, source, "aeeisp")
                    except FulltextFetchError as exc:
                        remember(exc)
                try:
                    page = await context.get(source)
                    require_success(page)
                    resolved = str(page.url)
                    if is_pdf(page.content):
                        return PdfDownload(page.content, resolved, "direct")
                    if is_access_challenge(page.content):
                        remember(FulltextFetchError("content_access_denied"))
                        continue
                    if "html" not in page.headers.get("content-type", "").lower() and not page.content.lstrip().lower().startswith((b"<!doctype", b"<html")):
                        continue
                    plugin = plugin_for(resolved)
                    for target in plugin.candidates(resolved, page.content):
                        try:
                            if transport is None and plugin.name == "nature" and urlsplit(target).path.endswith("_reference.pdf"):
                                data = await asyncio.to_thread(_nature_standard_download, target, options.max_bytes)
                                return PdfDownload(data, target, "nature")
                            headers = ({"Referer": resolved, "User-Agent": "Mozilla/5.0"}
                                       if plugin.name == "aeeisp" else None)
                            response = await context.get(target, headers=headers)
                            require_success(response)
                            if is_pdf(response.content):
                                return PdfDownload(response.content, str(response.url), plugin.name)
                            if is_access_challenge(response.content):
                                remember(FulltextFetchError("content_access_denied"))
                                continue
                            if transport is None and plugin.name == "aeeisp" and urlsplit(target).hostname == "www.aeeisp.com":
                                try:
                                    data = await asyncio.to_thread(_aeeisp_standard_download, target, options.max_bytes)
                                    return PdfDownload(data, target, plugin.name)
                                except FulltextFetchError as exc:
                                    remember(exc)
                            else:
                                remember(FulltextFetchError("unsupported_content"))
                        except FulltextFetchError as exc:
                            remember(exc)
                            if transport is None and plugin.name == "aeeisp" and urlsplit(target).hostname == "www.aeeisp.com":
                                try:
                                    data = await asyncio.to_thread(_aeeisp_standard_download, target, options.max_bytes)
                                    return PdfDownload(data, target, plugin.name)
                                except FulltextFetchError as fallback_error:
                                    remember(fallback_error)
                except FulltextFetchError as exc:
                    remember(exc)
            raise last


def store_pdf(data: bytes) -> tuple[str, int]:
    digest = hashlib.sha256(data).hexdigest()
    root = Path(settings.paper_pdf_dir)
    if os.environ.get("AGRIHOT_PROCESS") == "worker" and not root.is_mount():
        raise OSError("paper PDF volume is not mounted")
    destination = root / digest[:2] / f"{digest}.pdf"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        temporary = destination.with_name(f".{digest}.{os.getpid()}.tmp")
        try:
            with temporary.open("xb") as file:
                file.write(data)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
    return digest, len(data)


def pdf_path(digest: str) -> Path | None:
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        return None
    path = Path(settings.paper_pdf_dir) / digest[:2] / f"{digest}.pdf"
    return path if path.is_file() else None


async def extract_pdf_text(data: bytes) -> str | None:
    try:
        return await asyncio.to_thread(extract_pdf, data)
    except FulltextFetchError:
        return None
