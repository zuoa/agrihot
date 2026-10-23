"""Extensible full-text retrieval. Add a FulltextFetcher and register it with the engine."""
from .base import (MAX_CONTENT_CHARS, MIN_CONTENT_CHARS, FetchAttempt, FetchContext,
                   FetchOptions, FetchResult, FulltextFetcher, FulltextFetchError)
from .engine import FulltextEngine
from .fetchers import (DoiFetcher, FrontiersFetcher, GovernmentHtmlFetcher,
                       HtmlFetcher, JatsXmlFetcher, JinaFetcher, PdfFetcher)

__all__ = ["FulltextFetcher", "FulltextEngine", "FulltextFetchError", "FetchContext", "FetchOptions",
           "FetchResult", "FetchAttempt", "DoiFetcher", "PdfFetcher", "JatsXmlFetcher", "FrontiersFetcher",
           "GovernmentHtmlFetcher", "HtmlFetcher", "JinaFetcher", "MIN_CONTENT_CHARS", "MAX_CONTENT_CHARS"]
