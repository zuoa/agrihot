"""Auto 精选 scoring: rate each new item via DeepSeek on multiple dimensions.

Design borrows from industry practice:
  - relevance as a GATE, not a scored dimension (recommender-system convention):
    off-topic items are rejected outright instead of recouping points elsewhere
  - news-value theory: impact / freshness as core axes
  - Google E-E-A-T: source authority is independent of content quality
  - feed-platform quality scores: information gain penalizes rewrites/PR fluff
  - scholarly curation: papers anchored on method novelty & venue tier

Dimensions (total 100):
  impact    0-30  影响范围与层级（全国/产业级 > 省级 > 地市/企业）
  substance 0-25  信息增量（新数据/新政策/新结论 vs 转载汇编宣传稿）
  depth     0-20  专业深度（条款细节 / 方法与数据 / 分析背景）
  authority 0-15  信源权威度（部委央媒核心期刊 > 地方媒体自媒体）
  freshness 0-10  时效性，相对今天越新分越高

Gate `relevant` = false -> not selected regardless of score.
精选名额：每天（按入库日）达 SELECTION_THRESHOLD 的条目中，评分最高的前
DAILY_TOP_N 篇进入精选，每次评分后重算当天名单。
Scoring failures leave the item unselected (fail-closed) and log a warning.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import SessionLocal
from ..models import Item
from .ingest_service import _get_or_create_tags

log = logging.getLogger(__name__)

# 评分送入正文的最大字符数：控制 token 成本，4000 字已覆盖绝大多数资讯主体
FULLTEXT_MAX_CHARS = 4000

DIMENSION_MAX = {
    "impact": 30,
    "substance": 25,
    "depth": 20,
    "authority": 15,
    "freshness": 10,
}

_SYSTEM_PROMPT = (
    "你是农业信息化资讯平台的资深编辑，负责评估资讯是否值得进入「每日精选」，"
    "并提炼可在「主题」页聚合的短标签。只输出 JSON，不要输出任何其他内容。"
)


def _existing_tag_line(item: Item) -> str:
    """Best-effort tag names for the prompt; unsaved items have no collection."""
    try:
        names = [t.name for t in (item.tags or [])]
    except Exception:
        names = []
    return "、".join(names) or "无"


def _build_user_prompt(item: Item) -> str:
    published = item.published_at.date().isoformat() if item.published_at else "未知"
    # substance/depth 维度依赖正文证据：优先用全文（截断），无正文时回退摘要
    if item.content and item.content.strip():
        body_label = "正文"
        body = item.content.strip()[:FULLTEXT_MAX_CHARS]
    else:
        body_label = "摘要"
        body = item.summary
    existing = _existing_tag_line(item)
    return f"""请评估以下资讯能否进入「每日精选」，并重新提炼主题标签。

标题：{item.title}
来源：{item.source_name or "未知"}
分类：{item.category}
发布日期：{published}（今天是 {date.today().isoformat()}）
已有标签（可能未切开或过碎，请重写，不要照抄）：{existing}
{body_label}：{body}

第一步——相关性门槛：
relevant：主题是否属于三农、农业信息化、智慧农业、数字乡村、农业科技？false 则后续维度全部给 0。

第二步——按锚点打分（整数）：
- impact（0-30）影响范围与层级：全国性政策/产业级事件/重大突破 25-30；省级政策、细分行业进展 15-24；地市级动态、企业宣传 5-14；无公共价值 0-4
- substance（0-25）信息增量：含新政策条款/新数据/新结论/独家信息 20-25；有实质内容的综合报道 12-19；转载汇编、空洞宣传、老生常谈 0-11
- depth（0-20）专业深度，按分类锚定：政策看条款与数字细节；论文看方法新颖性、数据规模与结论可靠性；报道看背景分析与多方信源；流水账通稿 0-7
- authority（0-15）信源权威度：部委官网/央媒/核心期刊/国家级科研机构 12-15；省级官媒/主流行业媒体 8-11；地方媒体/商业门户 4-7；自媒体或来源不明 0-3
- freshness（0-10）时效性：24小时内 9-10；3天内 7-8；一周内 5-6；更早 0-4

第三步——主题标签 tags（3–6 个独立短词）：
- 每个 2–8 个汉字，或短英文缩写（AI、NDVI）；必须是数组里的多个元素，禁止用空格/顿号把若干词拼成一条
- 要能跨文章复用，供主题页聚合：领域（智慧农业/数字乡村/种业振兴/农业人工智能/遥感）、作物或对象、政策行动
- 不要：分类名（政策/报道/论文/行业）、论文方法词（作用机理、门槛特征）、日期、期刊名、把标题或机构全称整段塞进一个标签
- 好：["智慧农业","农业人工智能","行业标准"]  坏：["黑龙江农科院 寒地龙果 金秋博览会"]

输出格式（仅此 JSON）：
{{"relevant": true, "impact": 0, "substance": 0, "depth": 0, "authority": 0, "freshness": 0, "tags": ["智慧农业"], "comment": "一句话简评"}}"""


def parse_scores(text: str) -> dict[str, int] | None:
    """Parse DeepSeek JSON output; clamp each dimension to [0, max]. None if unparseable.

    The returned dict includes the `relevant` gate as 0/1 alongside the dimensions.
    """
    try:
        data = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    relevant = data.get("relevant")
    if not isinstance(relevant, bool):
        return None
    scores: dict[str, int] = {}
    for dim, cap in DIMENSION_MAX.items():
        try:
            value = int(data[dim])
        except (KeyError, TypeError, ValueError):
            return None
        scores[dim] = max(0, min(value, cap))
    if not relevant:
        scores = dict.fromkeys(scores, 0)
    scores["relevant"] = int(relevant)
    return scores


def parse_topic_tags(data: dict) -> list[str]:
    """Pull tags from model JSON; missing / malformed -> empty (caller keeps old tags)."""
    raw = data.get("tags")
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [t.strip() for t in raw if isinstance(t, str) and t.strip()]


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
        "max_tokens": 450,
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
    total = sum(v for k, v in scores.items() if k in DIMENSION_MAX)
    item.score = total
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        data = {}
    comment = str(data.get("comment") or "")[:200]
    item.score_detail = {k: scores[k] for k in DIMENSION_MAX} | {
        "relevant": scores["relevant"], "comment": comment,
    }
    topic_names = parse_topic_tags(data) if isinstance(data, dict) else []
    if topic_names:
        new_tags = await _get_or_create_tags(session, topic_names)
        if new_tags:
            item.tags = new_tags
    log.info("item %s scored %d tags=%s", item.id, total, [t.name for t in item.tags])
    return total


async def refresh_day_selection(session: AsyncSession, created_at) -> None:
    """Recompute 精选 for one ingest day: top DAILY_TOP_N items meeting the threshold.

    Admin edits made after a scoring event are kept until the next event re-ranks
    the day; unscored items (score IS NULL) never enter the ranking.
    """
    start = created_at.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    items = (
        await session.execute(
            select(Item).where(
                Item.created_at >= start,
                Item.created_at < end,
                Item.score.is_not(None),
            )
        )
    ).scalars().all()
    ranked = sorted(items, key=lambda i: (-i.score, i.id))
    for rank, it in enumerate(ranked):
        it.is_selected = (
            rank < settings.daily_top_n and it.score >= settings.selection_threshold
        )


async def score_and_mark(item_id: int) -> None:
    """Background task entry: open its own session (request session is closed by then)."""
    if not settings.deepseek_api_key:
        return
    async with SessionLocal() as session:
        item = await session.get(Item, item_id)
        if item is None or item.is_selected:
            return
        if await score_item(session, item) is not None:
            await refresh_day_selection(session, item.created_at)
            await session.commit()
