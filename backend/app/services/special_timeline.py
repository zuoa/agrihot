"""Stable, cited progress nodes stored inside existing publication versions."""
import copy
import hashlib
import re
from datetime import datetime, timezone


def node_key(row):
    return row["date"], re.sub(r"\s+", "", row["claim"]["text"])


def evidence_key(row, sources):
    by_id = {source["id"]: source for source in sources}
    return row["date"], tuple(sorted({(by_id.get(c["source_id"], {}).get("evidence_group", c["source_id"]),
                                       re.sub(r"\s+", "", c["quote"])) for c in row["claim"]["citations"]}))


def previous_nodes(document):
    rows = copy.deepcopy((document or {}).get("timeline", []))
    for row in rows:
        row.setdefault("title", "")
        row.setdefault("date_basis", "unknown")
        if not row.get("id"):
            row["id"] = "legacy-" + hashlib.sha256(repr(node_key(row)).encode()).hexdigest()[:24]
    return rows


def prepare(document, previous, sources, *, preserve=True):
    """Only the server mints IDs. Old nodes survive while their evidence is valid."""
    from .special_service import EvidenceValidationError, validate_evidence

    result = copy.deepcopy(document)
    old = previous_nodes(previous)
    by_id = {row["id"]: row for row in old}
    by_key = {node_key(row): row for row in old}
    by_evidence = {evidence_key(row, sources): row for row in old}
    rows, seen_ids, seen_keys, errors = [], set(), set(), []
    for index, row in enumerate(result.get("timeline", [])):
        identity = row.get("id")
        minted = "p-" + hashlib.sha256(repr(node_key(row)).encode()).hexdigest()[:32]
        if identity and identity not in by_id and identity != minted:
            errors.append({"path": f"timeline[{index}].id", "code": "timeline_id", "reason": "只能沿用 previous_timeline 的 ID，新进展 id 必须为 null"})
        existing = by_id.get(identity) or by_key.get(node_key(row)) or by_evidence.get(evidence_key(row, sources))
        if row.get("date_basis", "unknown") == "unknown" and not existing:
            cited_ids = {citation["source_id"] for citation in row["claim"]["citations"]}
            if any(source_day(source) == row["date"] for source in sources if source["id"] in cited_ids):
                row["date_basis"] = "published"
            elif any(date_in_quote(row["date"], citation["quote"]) for citation in row["claim"]["citations"]):
                row["date_basis"] = "event"
            else:
                errors.append({"path": f"timeline[{index}].date_basis", "code": "timeline_evidence", "reason": "新进展须有明确发生日期摘录或匹配来源的报道日期"})
        row["id"] = existing["id"] if existing else minted
        if row["id"] in seen_ids and not any(node_key(r) == node_key(row) for r in rows):
            errors.append({"path": f"timeline[{index}].id", "code": "timeline_id", "reason": "不同进展不能重复使用同一个节点ID"})
            continue
        if row["id"] in seen_ids or node_key(row) in seen_keys:
            # Exact duplicate reports add citations rather than extra progress nodes.
            match = next(r for r in rows if r["id"] == row["id"] or node_key(r) == node_key(row))
            citations = {c["source_id"]: c for c in [*match["claim"]["citations"], *row["claim"]["citations"]]}
            match["claim"]["citations"] = list(citations.values())[:8]
            continue
        rows.append(row)
        seen_ids.add(row["id"])
        seen_keys.add(node_key(row))
    if errors:
        raise EvidenceValidationError(errors)
    if preserve:
        for row in old:
            if row["id"] in seen_ids or node_key(row) in seen_keys:
                continue
            # Run the same evidence/date checks before retaining a historical node.
            check = {**result, "timeline": [row]}
            try:
                validate_evidence(check, sources, kind="event")
            except EvidenceValidationError:
                continue
            rows.append(row)
            seen_ids.add(row["id"])
            seen_keys.add(node_key(row))
    old_order = {row["id"]: index for index, row in enumerate(old)}
    draft_order = {row["id"]: index for index, row in enumerate(rows)}
    result["timeline"] = sorted(rows, key=lambda row: (
        row["date"], row["id"] not in by_id, -old_order.get(row["id"], draft_order[row["id"]]),
    ), reverse=True)[:15]
    return result


def date_in_quote(day, quote):
    year, month, date = map(int, day.split("-"))
    return bool(re.search(rf"{year}(?:年0?{month}月0?{date}日|[-/]0?{month}[-/]0?{date}(?!\d))", quote))


def source_day(source):
    from .daily_service import business_tz
    value = source.get("published_at")
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(business_tz()).date().isoformat()
    except (ValueError, TypeError):
        return None


def latest(document):
    rows = (document or {}).get("timeline", [])
    if not rows:
        return None
    row = max(rows, key=lambda r: r["date"])
    return {key: row.get(key) for key in ("id", "title", "date", "date_basis", "claim")}


def new_ids(document, previous):
    if not previous:
        return []
    existing = {row["id"] for row in previous_nodes(previous)}
    return [row["id"] for row in document.get("timeline", []) if row.get("id") and row["id"] not in existing]
