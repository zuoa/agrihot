"""Auto 精选 scoring: rate each new item via DeepSeek on multiple dimensions.

Dimensions (total 100):
  relevance   0-30  与农业信息化/智慧农业主题的相关度
  importance  0-25  政策级别 / 行业影响力
  quality     0-20  内容质量与信息量
  credibility 0-15  信源权威度
  timeliness  0-10  时效性

Total >= settings.selection_threshold -> is_selected = True.
Scoring failures leave the item unselected (fail-closed) and log a warning.
"""
from __future__ import annotations

import json
import logging
from datetime import date

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import SessionLocal
from ..models import Item

log = logging.getLogger(__name__)

DIMENSION_MAX = {
    "relevance": 30,
    "importance": 25,
    "quality": 20,
    "credibility": 15,
    "timeliness": 10,
}

_SYSTEM_PROMPT = (
    "你是农业信息化资讯平台的资深编辑，负责评估资讯是否值得进入「每日精选」。"
    "按给定维度打分，只输出 JSON，不要输出任何其他内容。"
)


def _build_user_prompt(item: Item) -> str:
    published = item.published_at.date().isoformat() if item.published_at else "未知"
    return f"""请对以下资讯按 5 个维度打分（整数），并给出一句简评。

标题：{item.title}
来源：{item.source_name or "未知"}
分类：{item.category}
发布日期：{published}（今天是 {date.today().isoformat()}）
摘要：{item.summary}

评分维度与分值上限：
- relevance（0-30）：与农业信息化、智慧农业、数字乡村、农业科技主题的相关度
- importance（0-25）：政策级别、行业影响力、受众价值
- quality（0-20）：内容信息量与可读性，空洞或纯宣传稿件给低分
- credibility（0-15）：信源权威度（部委官网、权威媒体、核心期刊给高分）
- timeliness（0-10）：时效性，相对今天越新分越高

输出格式（仅此 JSON）：
{{"relevance": 0, "importance": 0, "quality": 0, "credibility": 0, "timeliness": 0, "comment": "一句话简评"}}"""


def parse_scores(text: str) -> dict[str, int] | None:
    """Parse DeepSeek JSON output; clamp each dimension to [0, max]. None if unparseable."""
    try:
        data = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    scores: dict[str, int] = {}
    for dim, cap in DIMENSION_MAX.items():
        try:
            value = int(data[dim])
        except (KeyError, TypeError, ValueError):
            return None
        scores[dim] = max(0, min(value, cap))
    return scores


async def _call_deepseek(item: Item) -> str | None:
    """POST chat/completions; return raw message content, None on any failure."""
    url = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.deepseek_model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(item)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "max_tokens": 300,
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                url, json=payload,
                headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
    except Exception as exc:  # network / auth / schema — all fail-closed
        log.warning("DeepSeek scoring request failed for item %s: %s", item.id, exc)
        return None


async def score_item(session: AsyncSession, item: Item) -> int | None:
    """Score one item and set is_selected. Returns total score, or None if scoring failed."""
    raw = await _call_deepseek(item)
    if raw is None:
        return None
    scores = parse_scores(raw)
    if scores is None:
        log.warning("DeepSeek scoring unparsable for item %s: %.200s", item.id, raw)
        return None
    total = sum(scores.values())
    item.is_selected = total >= settings.selection_threshold
    log.info(
        "item %s scored %d (threshold %d) -> selected=%s",
        item.id, total, settings.selection_threshold, item.is_selected,
    )
    return total


async def score_and_mark(item_id: int) -> None:
    """Background task entry: open its own session (request session is closed by then)."""
    if not settings.deepseek_api_key:
        return
    async with SessionLocal() as session:
        item = await session.get(Item, item_id)
        if item is None or item.is_selected:
            return
        if await score_item(session, item) is not None:
            await session.commit()
