"""LLM-as-function: Chinese translation of a non-Chinese paper abstract.

Independent of scoring and paper cards. Failures leave summary_zh NULL;
ingest is unaffected. Original text stays in item.summary.
"""
from __future__ import annotations

import logging
import re

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Item
from .paper_card_service import has_usable_abstract

log = logging.getLogger(__name__)

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z]")

_SYSTEM_PROMPT = (
    "你是农业与信息科学方向的学术翻译。只输出译文，不要解释、不要加标题。"
)


def is_chinese(text: str) -> bool:
    """True when the text is predominantly CJK (enough to skip translation)."""
    if not text:
        return False
    cjk = len(_CJK_RE.findall(text))
    letters = len(_LATIN_RE.findall(text))
    return cjk >= 10 and cjk >= letters * 0.3


def needs_translation(item: Item) -> bool:
    if (item.summary_zh or "").strip():
        return False
    if not has_usable_abstract(item):
        return False
    if is_chinese(item.summary or ""):
        return False
    return True


def _build_user_prompt(item: Item) -> str:
    return (
        "将下面的学术论文摘要译为流畅的简体中文。"
        "保留专业术语的通行中文译法，必要时在首次出现时括注英文。"
        "只输出译文，不要解释。\n\n"
        f"{(item.summary or '')[:2500]}"
    )


def parse_translation(text: str | None) -> str | None:
    """Strip model chrome; None if empty or still not Chinese."""
    if not text or not str(text).strip():
        return None
    value = str(text).strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:\w+)?\n?", "", value)
        value = re.sub(r"\n?```$", "", value).strip()
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("“") and value.endswith("”")
    ):
        value = value[1:-1].strip()
    if len(value) < 20 or not is_chinese(value):
        return None
    return value


async def _call_deepseek(item: Item) -> str | None:
    url = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.deepseek_model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(item)},
        ],
        "temperature": 0.2,
        "max_tokens": 2000,
    }
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(
                url, json=payload,
                headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        log.warning("abstract-translate request failed for item %s: %s", item.id, exc)
        return None


async def fill_summary_zh(session: AsyncSession, item: Item) -> str | None:
    """Write item.summary_zh when missing. Returns the translation, or None on skip/fail."""
    if item.category != "论文" and item.paper is None:
        return None
    if not needs_translation(item):
        return item.summary_zh
    if not settings.deepseek_api_key:
        return None
    raw = await _call_deepseek(item)
    zh = parse_translation(raw)
    if zh is None:
        log.warning("abstract-translate unusable for item %s: %.200s", item.id, raw)
        return None
    item.summary_zh = zh
    log.info("item %s summary_zh filled (%d chars)", item.id, len(zh))
    return zh
