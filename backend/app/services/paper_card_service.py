"""LLM-as-function: freeze a 5-field Chinese paper card from title+abstract.

Independent of news scoring. Failures leave card NULL; ingest is unaffected.
"""
from __future__ import annotations

import json
import logging

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Item, PaperMeta
from .ingest_service import PaperDraft, _apply_paper_meta
from .openalex_service import direction_names

log = logging.getLogger(__name__)

CARD_KEYS = ("tldr", "method", "finding", "direction", "opportunity")
LIMITS = {
    "tldr": 50,
    "method": 40,
    "finding": 50,
    "opportunity": 60,
}

_SYSTEM_PROMPT = (
    "你是农业信息化方向的科研助理。只输出 JSON，不要输出任何其他内容。"
)


def _build_user_prompt(item: Item) -> str:
    choices = direction_names()
    quoted = ", ".join(f'"{n}"' for n in choices)
    return f"""下面是一篇论文的标题与摘要。

请用简体中文输出严格的 JSON，字段如下：
- tldr: 一句话讲清这篇论文做了什么（不超过 50 字）
- method: 用了什么关键方法 / 数据 / 技术（不超过 40 字）
- finding: 最关键的发现或结论（不超过 50 字）
- direction: 从 [{quoted}] 中选最贴切的 1 个
- opportunity: 对寻找研究方向有价值的一句话 —— 可延伸的研究空白 / 机会点（不超过 60 字）
只输出 JSON 对象，不要多余文字。

标题：{item.title}

摘要：{(item.summary or "")[:2500]}
"""


def parse_card(text: str) -> dict | None:
    """Parse model JSON into a 5-field card; None if unusable."""
    try:
        data = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    choices = direction_names()
    card: dict[str, str] = {}
    for key in CARD_KEYS:
        raw = data.get(key)
        if not isinstance(raw, str) or not raw.strip():
            return None
        value = raw.strip()
        if key in LIMITS:
            value = value[: LIMITS[key]]
        card[key] = value
    if card["direction"] not in choices:
        card["direction"] = "其他"
    return card


def has_usable_abstract(item: Item) -> bool:
    summary = (item.summary or "").strip()
    if len(summary) < 40:
        return False
    title = item.title.strip()
    if summary.rstrip("。") == title.rstrip("。"):
        return False
    # map_work pads missing abstracts as "{title}。{venue}"
    if summary.startswith(title) and len(summary) - len(title) < 40:
        return False
    return True


async def _call_deepseek(item: Item) -> str | None:
    url = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.deepseek_model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(item)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "max_tokens": 400,
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                url, json=payload,
                headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        log.warning("paper-card request failed for item %s: %s", item.id, exc)
        return None


async def fill_card(session: AsyncSession, item: Item) -> dict | None:
    """Write paper_meta.card when missing. Returns the card, or None on skip/fail."""
    if item.category != "论文":
        return None
    if item.paper and item.paper.card:
        return item.paper.card
    if not has_usable_abstract(item):
        return None
    if not settings.deepseek_api_key:
        return None
    raw = await _call_deepseek(item)
    if raw is None:
        return None
    card = parse_card(raw)
    if card is None:
        log.warning("paper-card unparsable for item %s: %.200s", item.id, raw)
        return None
    if item.paper is None:
        _apply_paper_meta(item, PaperDraft(ingested_from="agent"), item.doi)
        await session.flush()
    meta: PaperMeta = item.paper
    meta.card = card
    if not meta.direction:
        meta.direction = card["direction"]
    log.info("item %s paper card direction=%s", item.id, meta.direction)
    return card
