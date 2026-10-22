"""GLM/OpenAI-compatible embedding client. Never log provider bodies or keys."""
import asyncio
import hashlib
import math
import time
from collections import OrderedDict

import httpx

from ..config import settings

_query_cache: OrderedDict = OrderedDict()
_semaphore = asyncio.Semaphore(2)


class EmbeddingUnavailable(Exception):
    pass


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
            async with _semaphore, httpx.AsyncClient(timeout=settings.embedding_timeout) as client:
                response = await client.post(
                    f"{settings.embedding_base_url.rstrip('/')}/embeddings",
                    headers={"Authorization": f"Bearer {settings.embedding_api_key}"},
                    json={"model": settings.embedding_model, "dimensions": settings.embedding_dimensions, "input": batch},
                )
                response.raise_for_status()
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
