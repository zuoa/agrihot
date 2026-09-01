"""Chinese translation of non-Chinese paper abstracts."""
import os
import sys

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_DB = "sqlite+aiosqlite:////tmp/agrihot_test.db"

os.environ["DATABASE_URL"] = TEST_DB
os.environ["CONTENT_FETCH_ENABLED"] = "false"
os.environ["LITERATURE_FETCH_ENABLED"] = "false"

from app.config import settings  # noqa: E402
from app.database import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ApiKey, Base, Item, hash_api_key  # noqa: E402
from app.schemas import IngestItemIn  # noqa: E402
from app.services import (  # noqa: E402
    abstract_translate_service,
    job_runner,
    paper_card_service,
    scoring_service,
)
from app.services.ingest_service import ingest_item  # noqa: E402

TEST_KEY = "agri_test_key_translate"

engine = create_async_engine(TEST_DB)
TestSession = async_sessionmaker(engine, expire_on_commit=False)

EN_SUMMARY = (
    "Smart irrigation reduces water use by thirty percent in maize fields "
    "using soil moisture sensors and weather forecasts for daily scheduling."
)
ZH_SUMMARY = "本研究提出一种用于智慧灌溉调度的深度学习方法，结合土壤墒情与气象预报在玉米田验证。"
ZH_TRANSLATION = "智慧灌溉结合土壤墒情与气象预报，可使玉米田用水减少约三成。"


async def override_session():
    async with TestSession() as s:
        yield s


app.dependency_overrides[get_session] = override_session


@pytest_asyncio.fixture(autouse=True)
async def fresh_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with TestSession() as s:
        s.add(ApiKey(key_hash=hash_api_key(TEST_KEY), name="test-bot"))
        await s.commit()
    yield


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def paper_payload(**over):
    base = {
        "title": "A deep learning approach to smart irrigation scheduling",
        "url": "https://doi.org/10.1016/j.compag.2026.00200",
        "summary": EN_SUMMARY,
        "source_name": "Computers and Electronics in Agriculture",
        "category": "论文",
        "tags": ["智慧农业"],
        "doi": "10.1016/j.compag.2026.00200",
    }
    base.update(over)
    return IngestItemIn(**base)


def test_is_chinese_pure_and_mixed():
    assert abstract_translate_service.is_chinese(ZH_SUMMARY) is True
    assert abstract_translate_service.is_chinese(EN_SUMMARY) is False
    mixed = (
        "原文标题：Digital Agricultural Technology Innovation。"
        "摘要（译）：数字农业技术创新是农业现代化与绿色转型的重要驱动力。"
        "研究基于县域面板数据实证检验其对绿色全要素生产率的影响。"
    )
    assert abstract_translate_service.is_chinese(mixed) is True
    assert abstract_translate_service.is_chinese("") is False
    assert abstract_translate_service.is_chinese("short 中文") is False


def test_parse_translation_strips_fences_and_rejects_english():
    assert abstract_translate_service.parse_translation(ZH_TRANSLATION) == ZH_TRANSLATION
    fenced = f"```\n{ZH_TRANSLATION}\n```"
    assert abstract_translate_service.parse_translation(fenced) == ZH_TRANSLATION
    assert abstract_translate_service.parse_translation(EN_SUMMARY) is None
    assert abstract_translate_service.parse_translation("太短") is None
    assert abstract_translate_service.parse_translation(None) is None


@pytest.mark.asyncio
async def test_skips_chinese_abstract(monkeypatch):
    async def boom(item):
        raise AssertionError("must not call the model for Chinese abstracts")

    monkeypatch.setattr(settings, "deepseek_api_key", "fake-key")
    monkeypatch.setattr(abstract_translate_service, "_call_deepseek", boom)

    async with TestSession() as s:
        result = await ingest_item(s, paper_payload(summary=ZH_SUMMARY))
        await s.commit()
        item = await s.get(Item, result.item_id)
        assert abstract_translate_service.needs_translation(item) is False
        assert await abstract_translate_service.fill_summary_zh(s, item) is None
        assert item.summary_zh is None


@pytest.mark.asyncio
async def test_skips_padded_title_venue_abstract(monkeypatch):
    async def boom(item):
        raise AssertionError("must not call the model for padded abstracts")

    monkeypatch.setattr(settings, "deepseek_api_key", "fake-key")
    monkeypatch.setattr(abstract_translate_service, "_call_deepseek", boom)
    title = "A deep learning approach to smart irrigation scheduling"
    padded = f"{title}。OpenAlex"

    async with TestSession() as s:
        result = await ingest_item(s, paper_payload(summary=padded))
        await s.commit()
        item = await s.get(Item, result.item_id)
        assert abstract_translate_service.needs_translation(item) is False
        assert await abstract_translate_service.fill_summary_zh(s, item) is None


@pytest.mark.asyncio
async def test_skips_news_even_if_english(monkeypatch):
    async def boom(item):
        raise AssertionError("must not translate news items")

    monkeypatch.setattr(settings, "deepseek_api_key", "fake-key")
    monkeypatch.setattr(abstract_translate_service, "_call_deepseek", boom)

    async with TestSession() as s:
        result = await ingest_item(
            s,
            IngestItemIn(
                title="Ministry issues smart agriculture guidance",
                url="https://example.com/news/en-1",
                summary=EN_SUMMARY,
                source_name="Example News",
                category="政策",
            ),
        )
        await s.commit()
        item = await s.get(Item, result.item_id)
        assert await abstract_translate_service.fill_summary_zh(s, item) is None
        assert item.summary_zh is None


@pytest.mark.asyncio
async def test_writes_summary_zh_and_is_idempotent(monkeypatch):
    calls = []

    async def fake(item):
        calls.append(item.id)
        return ZH_TRANSLATION

    monkeypatch.setattr(settings, "deepseek_api_key", "fake-key")
    monkeypatch.setattr(abstract_translate_service, "_call_deepseek", fake)

    async with TestSession() as s:
        result = await ingest_item(s, paper_payload())
        await s.commit()
        item = await s.get(Item, result.item_id)
        assert abstract_translate_service.needs_translation(item) is True
        zh = await abstract_translate_service.fill_summary_zh(s, item)
        await s.commit()
        assert zh == ZH_TRANSLATION
        assert item.summary_zh == ZH_TRANSLATION
        assert item.summary == EN_SUMMARY

        again = await abstract_translate_service.fill_summary_zh(s, item)
        assert again == ZH_TRANSLATION
    assert calls == [result.item_id]


@pytest.mark.asyncio
async def test_model_failure_leaves_null(monkeypatch):
    async def fake(item):
        return "not chinese at all, still english abstract text here"

    monkeypatch.setattr(settings, "deepseek_api_key", "fake-key")
    monkeypatch.setattr(abstract_translate_service, "_call_deepseek", fake)

    async with TestSession() as s:
        result = await ingest_item(s, paper_payload())
        await s.commit()
        item = await s.get(Item, result.item_id)
        assert await abstract_translate_service.fill_summary_zh(s, item) is None
        assert item.summary_zh is None


@pytest.mark.asyncio
async def test_no_api_key_skips(monkeypatch):
    async def boom(item):
        raise AssertionError("must not call without a key")

    monkeypatch.setattr(settings, "deepseek_api_key", "")
    monkeypatch.setattr(abstract_translate_service, "_call_deepseek", boom)

    async with TestSession() as s:
        result = await ingest_item(s, paper_payload())
        await s.commit()
        item = await s.get(Item, result.item_id)
        assert await abstract_translate_service.fill_summary_zh(s, item) is None


@pytest.mark.asyncio
async def test_enrich_and_score_writes_summary_zh(client, monkeypatch):
    async def fake_score(item):
        return (
            '{"relevant": true, "impact": 20, "substance": 18, "depth": 16,'
            ' "authority": 12, "freshness": 8, "tags": ["智慧农业", "灌溉"]}'
        )

    async def fake_card(item):
        return (
            '{"tldr": "提出智慧灌溉调度模型", "method": "LSTM + 墒情", '
            '"finding": "玉米田节水约三成", "direction": "智慧农业 / 农业物联网", '
            '"opportunity": "可扩展到其他大田作物"}'
        )

    async def fake_zh(item):
        return ZH_TRANSLATION

    monkeypatch.setattr(settings, "deepseek_api_key", "fake-key")
    monkeypatch.setattr(scoring_service, "_call_deepseek", fake_score)
    monkeypatch.setattr(paper_card_service, "_call_deepseek", fake_card)
    monkeypatch.setattr(abstract_translate_service, "_call_deepseek", fake_zh)

    r = await client.post(
        "/api/v1/ingest/items",
        json={
            "title": "A deep learning approach to smart irrigation scheduling",
            "url": "https://doi.org/10.1016/j.compag.2026.00201",
            "summary": EN_SUMMARY,
            "source_name": "Computers and Electronics in Agriculture",
            "category": "论文",
            "tags": ["智慧农业"],
        },
        headers={"X-API-Key": TEST_KEY},
    )
    assert r.json()["status"] == "created"
    detail = (await client.get(f"/api/v1/items/{r.json()['item_id']}")).json()
    assert detail["summary"] == EN_SUMMARY
    assert detail["summary_zh"] == ZH_TRANSLATION
    assert detail["paper"]["card"]["tldr"] == "提出智慧灌溉调度模型"


@pytest.mark.asyncio
async def test_translate_abstracts_job(monkeypatch):
    calls = []

    async def fake(item):
        calls.append(item.id)
        return ZH_TRANSLATION

    monkeypatch.setattr(settings, "deepseek_api_key", "fake-key")
    monkeypatch.setattr(abstract_translate_service, "_call_deepseek", fake)

    async with TestSession() as s:
        en = await ingest_item(s, paper_payload())
        zh = await ingest_item(
            s,
            paper_payload(
                title="数字乡村建设对农业绿色全要素生产率的影响机制",
                url="https://doi.org/10.1016/j.compag.2026.00202",
                doi="10.1016/j.compag.2026.00202",
                summary=ZH_SUMMARY,
            ),
        )
        await s.commit()
        en_id, zh_id = en.item_id, zh.item_id

    stats = await job_runner.run("translate_abstracts")
    assert stats["status"] == "ok"
    assert stats["stats"]["translated"] == 1
    assert stats["stats"]["skipped"] == 1
    assert stats["stats"]["failed"] == 0
    assert calls == [en_id]

    async with TestSession() as s:
        assert (await s.get(Item, en_id)).summary_zh == ZH_TRANSLATION
        assert (await s.get(Item, zh_id)).summary_zh is None
