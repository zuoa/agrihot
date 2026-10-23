"""GLM/OpenAI-compatible embedding client. Never log provider bodies or keys."""
import asyncio
import hashlib
import logging
import math
import time
from collections import OrderedDict
from email.utils import parsedate_to_datetime

import httpx

from ..config import settings

_query_cache: OrderedDict = OrderedDict()
log = logging.getLogger(__name__)


class EmbeddingUnavailable(Exception):
    def __init__(self, reason: str, retry_after: float = 0):
        super().__init__(reason)
        self.retry_after = retry_after


def _retry_after(response: httpx.Response) -> float:
    value = response.headers.get("Retry-After", "")
    try:
        delay = float(value)
    except ValueError:
        try:
            delay = parsedate_to_datetime(value).timestamp() - time.time()
        except (TypeError, ValueError, OverflowError):
            return 0
    # Bound untrusted headers to one day, including invalid non-finite values.
    return min(86400, max(0, delay)) if math.isfinite(delay) else 0


def _provider_code(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
        error = payload.get("error") if isinstance(payload, dict) else None
        code = str(error.get("code", "")) if isinstance(error, dict) else ""
    except ValueError:
        return None
    # Only propagate numeric business codes, never provider messages or bodies.
    return code if len(code) == 4 and code.isascii() and code.isdecimal() else None


class _RequestGate:
    """One process shares pacing and provider cooldown across indexing and search."""

    def __init__(self):
        self.lock = asyncio.Lock()
        self.next_request_at = 0.0
        self.cooldown_until = 0.0
        self.failures = 0
        self.reason = "provider_http_429"

    def remaining(self) -> float:
        return max(0, self.cooldown_until - time.monotonic())

    async def wait(self):
        remaining = self.remaining()
        if remaining:
            raise EmbeddingUnavailable(self.reason, retry_after=remaining)
        delay = self.next_request_at - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        self.next_request_at = time.monotonic() + settings.embedding_min_interval

    def throttle(self, response: httpx.Response) -> EmbeddingUnavailable:
        self.failures += 1
        code = _provider_code(response)
        self.reason = f"provider_http_429_{code}" if code else "provider_http_429"
        delay = min(3600, settings.embedding_rate_limit_cooldown * 2 ** min(self.failures - 1, 12))
        if code == "1113":
            self.reason = "provider_insufficient_balance"
            delay = 3600
        delay = max(delay, _retry_after(response))
        self.cooldown_until = time.monotonic() + delay
        log.warning("Embedding provider HTTP 429 (code=%s); pausing requests for %.0fs", code or "unknown", delay)
        return EmbeddingUnavailable(self.reason, retry_after=delay)


_gate = _RequestGate()


def cooldown_remaining() -> float:
    return _gate.remaining()


def fingerprint() -> str:
    return hashlib.sha256(
        f"{settings.embedding_base_url}|{settings.embedding_model}|{settings.embedding_dimensions}".encode()
    ).hexdigest()


async def embed(texts: list[str]) -> list[list[float]]:
    if not settings.embedding_api_key:
        raise EmbeddingUnavailable("not_configured")
    # UTF-8 byte count is a conservative token bound, including for Chinese.
    # GLM's array input has a per-request token budget as well as a batch limit.
    batches, batch, size = [], [], 0
    for text in texts:
        text_size = len(text.encode("utf-8"))
        if text_size > 2800:
            raise EmbeddingUnavailable("input_too_long")
        if batch and (size + text_size > 2800 or len(batch) == 16):
            batches.append(batch)
            batch, size = [], 0
        batch.append(text)
        size += text_size
    if batch:
        batches.append(batch)
    result = []
    for batch in batches:
        try:
            async with _gate.lock:
                await _gate.wait()
                async with httpx.AsyncClient(timeout=settings.embedding_timeout) as client:
                    response = await client.post(
                        f"{settings.embedding_base_url.rstrip('/')}/embeddings",
                        headers={"Authorization": f"Bearer {settings.embedding_api_key}"},
                        json={"model": settings.embedding_model, "dimensions": settings.embedding_dimensions, "input": batch},
                    )
                    if response.status_code == 429:
                        raise _gate.throttle(response)
                    response.raise_for_status()
                    _gate.failures = 0
                    data = sorted(response.json()["data"], key=lambda row: row["index"])
            if len(data) != len(batch) or [row["index"] for row in data] != list(range(len(batch))):
                raise ValueError("invalid batch")
            for row in data:
                vector = [float(v) for v in row["embedding"]]
                if len(vector) != settings.embedding_dimensions or not all(math.isfinite(v) for v in vector) or not any(vector):
                    raise ValueError("invalid vector")
                result.append(vector)
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
            reason = f"provider_http_{exc.response.status_code}" if isinstance(exc, httpx.HTTPStatusError) else "provider_unavailable"
            raise EmbeddingUnavailable(reason) from None
    return result


async def query_vector(query: str) -> list[float]:
    cache_key = (fingerprint(), query)
    cached = _query_cache.get(cache_key)
    if cached and cached[0] > time.monotonic():
        _query_cache.move_to_end(cache_key)
        return cached[1]
    vector = (await embed([query]))[0]
    _query_cache[cache_key] = (time.monotonic() + 300, vector)
    while len(_query_cache) > 256:
        _query_cache.popitem(last=False)
    return vector
