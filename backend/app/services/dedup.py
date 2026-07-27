"""Deduplication primitives: URL normalization, URL hash, title SimHash.

Level 1  — exact URL duplicate: normalize URL (strip tracking params, unify
           scheme/host case, drop fragment/trailing slash) then sha256.
Level 2  — near duplicate title: normalize title (NFKC, drop punctuation /
           whitespace) then 64-bit SimHash over char-bigrams; hamming
           distance <= SIMHASH_THRESHOLD counts as the same story.
Level 3  — merge, don't drop: duplicates fold their source into the existing
           item's `sources` list instead of being rejected (handled in
           ingest_service).
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SIMHASH_THRESHOLD = 6

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "spm", "from", "ref", "ref_src", "source", "fbclid", "gclid",
    "dclid", "msclkid", "_t", "timestamp", "share_token", "track_id",
}


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = "https" if parts.scheme.lower() in ("http", "https") else parts.scheme.lower()
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/") or "/"
    query = urlencode(
        sorted(
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k.lower() not in _TRACKING_PARAMS
        )
    )
    return urlunsplit((scheme, netloc, path, query, ""))


def url_hash(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode()).hexdigest()


_PUNCT = re.compile(
    r"[\s　，。！？；：、「」『』（）()【】《》〈〉—\-–_|·…,.!?;:'\"()\[\]<>/@#&*+=~^%$]+"
)


def normalize_title(title: str) -> str:
    t = unicodedata.normalize("NFKC", title).lower()
    return _PUNCT.sub("", t)


def _tokens(text: str) -> list[str]:
    # char bigrams — works for CJK without a segmenter
    if len(text) <= 2:
        return [text] if text else []
    return [text[i : i + 2] for i in range(len(text) - 1)]


def simhash64(text: str) -> int:
    """Unsigned 64-bit SimHash of normalized text."""
    weights = [0] * 64
    for tok in _tokens(text):
        h = int.from_bytes(hashlib.md5(tok.encode()).digest()[:8], "big")
        for i in range(64):
            weights[i] += 1 if (h >> i) & 1 else -1
    out = 0
    for i in range(64):
        if weights[i] > 0:
            out |= 1 << i
    return out


def title_simhash(title: str) -> int:
    return simhash64(normalize_title(title))


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def to_signed64(h: int) -> int:
    """Store unsigned 64-bit hash in a signed BIGINT column."""
    return h if h < 2**63 else h - 2**64


def from_signed64(v: int) -> int:
    return v if v >= 0 else v + 2**64
