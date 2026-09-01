"""DOI normalization. Used by ingest dedup and OpenAlex mapping."""
from __future__ import annotations

import re

# Crossref-style DOI: 10.<registrant>/<suffix>. Optional doi: / doi.org prefix.
_DOI_RE = re.compile(
    r"(?:doi:\s*)?(?:https?://(?:dx\.)?doi\.org/)?(10\.\d{4,9}/[-._;()/:A-Z0-9]+)",
    re.IGNORECASE,
)


def normalize_doi(value: str | None) -> str | None:
    """Return lowercase DOI without resolver prefix, or None if not a DOI."""
    if not value:
        return None
    match = _DOI_RE.search(value.strip())
    if not match:
        return None
    doi = match.group(1).rstrip(").,;]")
    return doi.lower() or None
