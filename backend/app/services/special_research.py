"""Bounded external research. Search snippets are never publication evidence."""
from __future__ import annotations

from urllib.parse import urlsplit

import httpx

from ..config import settings
from ..models import utcnow
from .content_service import create_fulltext_engine
from .fulltext.base import FulltextFetchError
from .openalex_service import reconstruct_abstract


async def supplement(queries: list[str]) -> tuple[list[dict], str]:
    sources, seen = [], set()
    if not queries:
        return [], "no_results"
    failures = 0
    search_requests = 0
    engine = create_fulltext_engine()
    async with httpx.AsyncClient(timeout=20) as client:
        for query in queries[:3]:
            if search_requests >= 3 or len(sources) >= 5:
                break
            # OpenAlex provides primary academic metadata/abstracts, never fake full text.
            try:
                search_requests += 1
                params = {"search": query[:300], "per-page": 2, "mailto": settings.openalex_mailto}
                if settings.openalex_api_key:
                    params["api_key"] = settings.openalex_api_key
                response = await client.get("https://api.openalex.org/works", params=params)
                response.raise_for_status()
                for work in response.json().get("results", []):
                    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
                    url = work.get("doi") or work.get("id")
                    if not url or url in seen or len(abstract) < 150 or len(sources) >= 5:
                        continue
                    seen.add(url)
                    if sum(s.get("publisher") == "OpenAlex · 原始论文摘要" for s in sources) >= 3:
                        continue
                    sources.append({"id": f"e{len(sources) + 1}", "kind": "external", "title": work.get("display_name", ""),
                                    "url": url, "publisher": "OpenAlex · 原始论文摘要", "basis": "abstract",
                                    "published_at": work.get("publication_date"), "retrieved_at": utcnow().isoformat(),
                                    "text": abstract[:4000]})
            except (httpx.HTTPError, ValueError, TypeError):
                failures += 1
            if not settings.tavily_api_key or len(sources) >= 5 or search_requests >= 3:
                continue
            try:
                search_requests += 1
                response = await client.post("https://api.tavily.com/search", headers={"Authorization": f"Bearer {settings.tavily_api_key}"},
                                             json={"query": query[:300], "search_depth": "basic", "max_results": 3,
                                                   "include_answer": False, "include_raw_content": False})
                response.raise_for_status()
                for hit in response.json().get("results", []):
                    url = hit.get("url", "")
                    if not url or url in seen or len(sources) >= 5:
                        continue
                    seen.add(url)
                    try:
                        fetched = await engine.fetch(url)
                    except FulltextFetchError:
                        failures += 1
                        continue
                    # Trustworthiness and relevance are checked by the evidence verifier.
                    sources.append({"id": f"e{len(sources) + 1}", "kind": "external", "title": str(hit.get("title") or url)[:500],
                                    "url": url, "publisher": urlsplit(url).hostname or "", "basis": "fulltext",
                                    "published_at": None, "retrieved_at": utcnow().isoformat(), "text": fetched.text[:4000]})
            except (httpx.HTTPError, ValueError, TypeError):
                failures += 1
    status = "partial" if failures else "ok"
    if not settings.tavily_api_key:
        status = "academic_only" if not failures else "academic_partial"
    return sources, status if sources else ("unavailable" if failures else "no_results")
