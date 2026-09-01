"""日报生成：汇总当天收录的高分资讯，DeepSeek 生成今日要点，upsert Daily。

日报按「收录日期」归集（Item.created_at 入库时刻），与资讯原始发布日期无关；
日界按 settings.daily_timezone（业务时区，默认 Asia/Shanghai）的日历日切分，
与容器系统时区解耦——生产容器默认 UTC，若按 UTC 切，国内早上收录的资讯
会被算进前一天的日报。

取当天评分最高的前 DAILY_ITEM_COUNT 条进入日报。

DeepSeek 不可用（无 key / 请求失败 / 输出不可解析）时降级：
标题用日期、要点取前几条资讯标题——保证定时任务 fail-closed 也能出日报。
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Daily, Item

log = logging.getLogger(__name__)

# 每期日报收录的条目数上限（按评分降序）
DAILY_ITEM_COUNT = 15
# 送入 DeepSeek 的条目数与单条摘要长度：控制 token 成本
PROMPT_ITEM_COUNT = 12
PROMPT_SUMMARY_CHARS = 200
# 要点条数与单条长度上限（超出截断，保证分享图/详情页不会过长）
HIGHLIGHT_COUNT_MAX = 6
HIGHLIGHT_CHARS_MAX = 120

DISCLAIMER = (
    "\n\n---\n*本日报内容整理自公开来源，学术论文元数据来自 OpenAlex 等开放接口；"
    "外文资料已译为中文，翻译与摘要仅供参考；引用与决策请以官方原文与正式出版物为准。*"
)

_SYSTEM_PROMPT = (
    "你是农业信息化资讯平台的资深编辑，负责把当天收录的资讯汇编成「农业农村日报」。"
    "只输出 JSON，不要输出任何其他内容。"
)


def business_tz() -> timezone | ZoneInfo:
    """日报业务时区；配置非法时回退 UTC 并告警（不阻断生成）。"""
    try:
        return ZoneInfo(settings.daily_timezone)
    except Exception:
        log.warning("invalid daily_timezone %r, falling back to UTC", settings.daily_timezone)
        return timezone.utc


def day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    """`day`（业务时区日历日）对应的 UTC 区间 [start, end)。"""
    start = datetime.combine(day, time.min, tzinfo=business_tz()).astimezone(timezone.utc)
    return start, start + timedelta(days=1)


async def _day_items(session: AsyncSession, day: date) -> list[Item]:
    """收录日期（created_at）落在 `day` 的条目，按评分降序（未评分排后）。

    日界按业务时区（daily_timezone）取 `[day 00:00, day+1 00:00)`，换算成
    UTC 与 created_at（timestamptz）比较——「某日的日报」就是该日历日当天
    收录的资讯。
    """
    start, end = day_bounds_utc(day)
    rows = (
        await session.execute(
            select(Item)
            .where(Item.created_at >= start, Item.created_at < end)
            .order_by(Item.score.desc().nulls_last(), Item.id.desc())
            .limit(DAILY_ITEM_COUNT)
        )
    ).scalars().all()
    return list(rows)


def _build_user_prompt(items: list[Item], day: date) -> str:
    lines = []
    for i, it in enumerate(items[:PROMPT_ITEM_COUNT], 1):
        summary = (it.summary or "").strip().replace("\n", " ")[:PROMPT_SUMMARY_CHARS]
        lines.append(f"{i}. 【{it.category}】{it.title}\n   {summary}")
    return f"""以下是 {day.isoformat()} 收录的农业资讯，请汇编成当日「农业农村日报」。

资讯列表：
{chr(10).join(lines)}

要求：
- title：日报标题，30 字以内，可点出当天最重要的主题
- highlights：今日要点，3-6 条，每条 80 字以内，聚焦政策动向、产业事件与前沿研究中最有价值的信息，多条资讯可合并为一条要点
- overview：本期概述，120 字以内，一段话说明本期覆盖面

输出格式（仅此 JSON）：
{{"title": "...", "highlights": ["...", "..."], "overview": "..."}}"""


def parse_daily_compose(text: str) -> dict | None:
    """Parse DeepSeek JSON output -> {title, highlights, overview}; None if unusable."""
    try:
        data = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    raw_highlights = data.get("highlights")
    if not isinstance(raw_highlights, list):
        return None
    highlights = [
        h.strip()[:HIGHLIGHT_CHARS_MAX]
        for h in raw_highlights
        if isinstance(h, str) and h.strip()
    ][:HIGHLIGHT_COUNT_MAX]
    if not highlights:
        return None
    title = str(data.get("title") or "").strip()[:300]
    overview = str(data.get("overview") or "").strip()[:500]
    return {"title": title, "highlights": highlights, "overview": overview}


async def _compose_with_deepseek(items: list[Item], day: date) -> dict | None:
    """Generate title/highlights/overview via DeepSeek; None on any failure."""
    if not settings.deepseek_api_key:
        return None
    url = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.deepseek_model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(items, day)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.3,
        "max_tokens": 1200,
    }
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                url, json=payload,
                headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]
    except Exception as exc:  # network / auth / schema — all fail-closed
        log.warning("DeepSeek daily-compose request failed for %s: %s", day, exc)
        return None
    composed = parse_daily_compose(raw)
    if composed is None:
        log.warning("DeepSeek daily-compose unparsable for %s: %.200s", day, raw)
    return composed


async def generate_daily(session: AsyncSession, day: date) -> Daily | None:
    """Generate (or regenerate) the Daily for `day`. None if no items that day.

    Does not commit — the caller owns the transaction.
    """
    items = await _day_items(session, day)
    if not items:
        return None

    composed = await _compose_with_deepseek(items, day)
    if composed:
        title = composed["title"] or f"农业农村日报 · {day.isoformat()}"
        highlights = composed["highlights"]
        content = (composed["overview"] + DISCLAIMER) if composed["overview"] else DISCLAIMER.strip()
    else:
        title = f"农业农村日报 · {day.isoformat()}"
        highlights = [it.title for it in items[:5]]
        content = DISCLAIMER.strip()

    daily = (
        await session.execute(select(Daily).where(Daily.date == day))
    ).scalar_one_or_none()
    if daily is None:
        daily = Daily(date=day, title=title)
        session.add(daily)
    daily.title = title
    daily.highlights = highlights
    daily.content = content
    daily.item_ids = [it.id for it in items]
    log.info(
        "daily %s generated: %d items, %d highlights (%s)",
        day, len(items), len(highlights), "llm" if composed else "fallback",
    )
    return daily
