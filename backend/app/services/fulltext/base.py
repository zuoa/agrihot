"""Contracts and shared request handling for full-text fetchers."""
from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Awaitable, Callable
from urllib.parse import urljoin, urlsplit

import httpx

MIN_CONTENT_CHARS = 200
MAX_CONTENT_CHARS = 100_000


class FulltextFetchError(Exception):
    """Safe, actionable failure; provider response bodies never become messages."""

    def __init__(self, reason: str, upstream_status: int | None = None):
        self.reason, self.upstream_status = reason, upstream_status
        self.attempts: tuple[FetchAttempt, ...] = ()
        messages = {
            "source_tls_error": "原文网站的 HTTPS 证书或 TLS 连接异常，请更换有效链接，或通过编辑、推送补交正文。",
            "source_unavailable": "无法连接原文网站，请稍后重试。",
            "source_timeout": "原文网站响应超时，请稍后重试。",
            "source_not_public": "原文地址不是可公开访问的互联网地址，请提供公开链接或补交正文。",
            "invalid_url": "原文链接无效，请提供不含账户信息的 HTTP 或 HTTPS 公开链接。",
            "doi_resolution_failed": "DOI 未能解析到出版社地址，请提供出版社全文链接或开放获取 PDF 链接。",
            "reader_rate_limited": "正文抓取服务暂时限流，请稍后重试。",
            "reader_blocked": "原文域名被正文抓取服务限制访问，请通过编辑、推送补交正文。",
            "reader_domain_blocked": "正文抓取服务暂时限制匿名访问该域名，请稍后重试，或提供出版社、开放获取全文链接。",
            "reader_auth_error": "正文抓取服务鉴权失败，请检查抓取服务配置。",
            "reader_forbidden": "正文抓取服务拒绝访问此页面，请检查原文访问权限或补交正文。",
            "reader_quota_exhausted": "正文抓取服务额度不足，请检查抓取服务账户。",
            "reader_timeout": "正文抓取服务响应超时，请稍后重试。",
            "reader_unavailable": "无法连接正文抓取服务，请稍后重试。",
            "fetch_timeout": "多种正文获取方法均未能在时限内完成，请稍后重试或补交正文。",
            "content_too_short": f"抓取结果不足 {MIN_CONTENT_CHARS} 个字符，未识别到有效正文，请检查链接或补交正文。",
            "content_too_large": "原文文件超过下载大小限制，请提供较小的正文文件或补交文本。",
            "content_access_denied": "原文返回访问验证、登录或错误页面，未保存为正文。",
            "unsupported_content": "未能从此文件类型中提取正文，请提供网页、文本 PDF 或正文文本。",
            "pdf_no_text": "PDF 没有可提取的文字，可能是扫描件，需要 OCR 或补交正文文本。",
            "fetcher_failed": "正文解析失败，其他获取方法也未能取得有效正文。",
        }
        message = messages.get(reason, f"原文获取服务返回 HTTP {upstream_status}，请检查链接或稍后重试。")
        super().__init__(message)


@dataclass(frozen=True)
class FetchAttempt:
    fetcher: str
    url: str
    reason: str
    upstream_status: int | None = None


@dataclass(frozen=True)
class FetchResult:
    text: str
    source_url: str
    fetcher: str
    truncated: bool = False
    attempts: tuple[FetchAttempt, ...] = ()


@dataclass(frozen=True)
class FetchOptions:
    timeout: float = 60
    request_timeout: float = 20
    max_bytes: int = 10 * 1024 * 1024
    max_chars: int = MAX_CONTENT_CHARS
    jina_base_url: str = "https://r.jina.ai"
    jina_api_key: str = ""


async def validate_public_source(url: str) -> None:
    """Check each direct request and redirect before contacting its destination."""
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise FulltextFetchError("invalid_url")
    try:
        async with asyncio.timeout(5):
            addresses = await asyncio.get_running_loop().getaddrinfo(
                parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM,
            )
    except (OSError, TimeoutError):
        raise FulltextFetchError("source_unavailable") from None
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global
                            or ipaddress.ip_address(row[4][0]).is_multicast for row in addresses):
        raise FulltextFetchError("source_not_public")


@dataclass
class FetchContext:
    client: httpx.AsyncClient
    options: FetchOptions
    validator: Callable[[str], Awaitable[None]] = validate_public_source
    follow: Callable[[str], Awaitable[FetchResult]] | None = None
    started_at: float = field(default_factory=time.monotonic)
    cache: dict[tuple, httpx.Response] = field(default_factory=dict)
    failures: dict[tuple, FulltextFetchError] = field(default_factory=dict)
    active_urls: set[str] = field(default_factory=set)
    attempts: list[FetchAttempt] = field(default_factory=list)

    async def get(self, url: str, *, trusted: bool = False, follow_redirects: bool = True,
                  headers: dict | None = None, timeout: float | None = None) -> httpx.Response:
        key = (url, trusted, follow_redirects, tuple(sorted((k.lower(), v) for k, v in (headers or {}).items())))
        if key in self.cache:
            return self.cache[key]
        if key in self.failures:
            raise self.failures[key]
        current = url
        for _ in range(6):
            if not trusted:
                await self.validator(current)
            remaining = self.options.timeout - (time.monotonic() - self.started_at)
            if remaining <= 0:
                raise FulltextFetchError("fetch_timeout")
            try:
                async with self.client.stream("GET", current, headers=headers, follow_redirects=False,
                                              timeout=min(timeout or self.options.request_timeout, remaining)) as raw:
                    declared = raw.headers.get("content-length", "")
                    if declared.isdecimal() and int(declared) > self.options.max_bytes:
                        raise FulltextFetchError("content_too_large")
                    parts, size = [], 0
                    async for part in raw.aiter_bytes():
                        size += len(part)
                        if size > self.options.max_bytes:
                            raise FulltextFetchError("content_too_large")
                        parts.append(part)
                    response = httpx.Response(raw.status_code, request=raw.request, content=b"".join(parts),
                                              headers={k: v for k, v in raw.headers.items()
                                                       if k not in {"content-encoding", "transfer-encoding", "content-length"}})
            except httpx.TimeoutException:
                error = FulltextFetchError("reader_timeout" if trusted else "source_timeout")
                self.failures[key] = error
                raise error from None
            except httpx.HTTPError as exc:
                reason = "reader_unavailable" if trusted else "source_unavailable"
                if not trusted and any(marker in str(exc).lower() for marker in ("certificate", "ssl", "tlsv1")):
                    reason = "source_tls_error"
                error = FulltextFetchError(reason)
                self.failures[key] = error
                raise error from None
            if follow_redirects and response.is_redirect and response.headers.get("location"):
                target = urljoin(current, response.headers["location"])
                if urlsplit(target).netloc != urlsplit(current).netloc or urlsplit(target).scheme != urlsplit(current).scheme:
                    headers = {k: v for k, v in (headers or {}).items() if k.lower() not in {"authorization", "cookie"}}
                current = target
                # A configured Reader endpoint may be private, but redirects from it must be public.
                if trusted:
                    await self.validator(current)
                continue
            self.cache[key] = response
            return response
        raise FulltextFetchError("source_unavailable")


class FulltextFetcher(ABC):
    """Implement supports() and fetch(); register the instance with FulltextEngine."""

    name = "base"
    priority = 100

    @abstractmethod
    def supports(self, url: str) -> bool:
        """Whether this implementation can retrieve the URL's content."""

    @abstractmethod
    async def fetch(self, url: str, context: FetchContext) -> FetchResult:
        """Return extracted Markdown or raise FulltextFetchError."""
