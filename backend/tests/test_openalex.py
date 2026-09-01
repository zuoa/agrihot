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
from app.models import ApiKey, Base, hash_api_key  # noqa: E402
from app.schemas import IngestItemIn  # noqa: E402
from app.services import content_service, paper_card_service, scoring_service  # noqa: E402
from app.services.doi import normalize_doi  # noqa: E402
from app.services.ingest_service import PaperDraft, ingest_item  # noqa: E402
from app.services.openalex_service import (  # noqa: E402
    map_work,
    passes_prescreen,
    reconstruct_abstract,
)

TEST_KEY = "agri_test_key_openalex"

engine = create_async_engine(TEST_DB)
TestSession = async_sessionmaker(engine, expire_on_commit=False)


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


SAMPLE_WORK = {
    "id": "https://openalex.org/W4212345678",
    "doi": "https://doi.org/10.1016/j.compag.2026.00042",
    "display_name": "A deep learning approach to smart irrigation scheduling",
    "publication_date": "2026-08-20",
    "cited_by_count": 3,
    "abstract_inverted_index": {
        "Smart": [0], "irrigation": [1], "reduces": [2], "water": [3],
        "use": [4], "by": [5], "thirty": [6], "percent": [7], "in": [8],
        "maize": [9], "fields": [10], "using": [11], "soil": [12],
        "moisture": [13], "and": [14], "weather": [15], "forecasts": [16],
    },
    "primary_location": {
        "landing_page_url": "https://www.sciencedirect.com/science/article/pii/S016816992600042",
        "pdf_url": None,
        "source": {"display_name": "Computers and Electronics in Agriculture"},
    },
    "authorships": [
        {"author": {"display_name": "Jane Doe", "orcid": "https://orcid.org/0000-0001-2345-6789"}},
        {"author": {"display_name": "李四", "orcid": None}},
    ],
    "open_access": {"oa_url": "https://example.org/oa.pdf"},
}


def test_normalize_doi_variants():
    assert normalize_doi("10.1016/j.compag.2026.00042") == "10.1016/j.compag.2026.00042"
    assert normalize_doi("https://doi.org/10.1016/j.compag.2026.00042") == (
        "10.1016/j.compag.2026.00042"
    )
    assert normalize_doi("https://dx.doi.org/10.1016/j.compag.2026.00042") == (
        "10.1016/j.compag.2026.00042"
    )
    assert normalize_doi("doi:10.1016/j.compag.2026.00042") == "10.1016/j.compag.2026.00042"
    assert normalize_doi("HTTPS://DOI.ORG/10.1016/J.COMPAG.2026.00042") == (
        "10.1016/j.compag.2026.00042"
    )
    assert normalize_doi("https://example.com/news") is None
    assert normalize_doi("") is None
    assert normalize_doi(None) is None


def test_reconstruct_abstract_sorts_by_position():
    inverted = {"percent": [7], "Smart": [0], "irrigation": [1], "reduces": [2]}
    assert reconstruct_abstract(inverted) == "Smart irrigation reduces percent"
    assert reconstruct_abstract(None) is None
    assert reconstruct_abstract({}) is None


def test_map_work_fixture():
    mapped = map_work(SAMPLE_WORK, direction="智慧农业 / 农业物联网")
    assert mapped is not None
    payload, draft = mapped
    assert payload.title.startswith("A deep learning")
    assert payload.doi == "10.1016/j.compag.2026.00042"
    assert payload.url == "https://doi.org/10.1016/j.compag.2026.00042"
    assert payload.category == "论文"
    assert "thirty percent" in payload.summary
    assert draft.openalex_id == "W4212345678"
    assert draft.venue == "Computers and Electronics in Agriculture"
    assert draft.cited_by_count == 3
    assert draft.oa_url == "https://example.org/oa.pdf"
    assert [a["name"] for a in draft.authors] == ["Jane Doe", "李四"]
    assert draft.direction == "智慧农业 / 农业物联网"


def test_map_work_without_abstract_still_ingestable():
    work = {
        "id": "https://openalex.org/W9",
        "doi": None,
        "display_name": "Something about digital agriculture platforms",
        "primary_location": {
            "landing_page_url": "https://example.org/paper/9",
            "source": {"display_name": "Agricultural Systems"},
        },
        "authorships": [],
        "open_access": {},
    }
    mapped = map_work(work)
    assert mapped is not None
    payload, draft = mapped
    assert payload.url == "https://example.org/paper/9"
    assert "Agricultural Systems" in payload.summary
    assert draft.openalex_id == "W9"


def test_map_work_rejects_empty_title():
    assert map_work({"display_name": "ab", "id": "https://openalex.org/W1"}) is None


def test_passes_prescreen_uses_watchlist_terms():
    assert passes_prescreen("Smart irrigation for maize", "using IoT soil sensors")
    assert passes_prescreen("数字乡村建设评价", "基于县域面板数据")
    assert not passes_prescreen("A history of medieval pottery", "kiln temperatures in France")


def test_parse_card_ok_and_unknown_direction():
    raw = (
        '{"tldr": "提出智慧灌溉调度模型", "method": "LSTM + 土壤墒情", '
        '"finding": "玉米田节水约三成", "direction": "不存在的方向", '
        '"opportunity": "可扩展到其他大田作物"}'
    )
    card = paper_card_service.parse_card(raw)
    assert card is not None
    assert card["tldr"] == "提出智慧灌溉调度模型"
    assert card["direction"] == "其他"


def test_parse_card_rejects_incomplete():
    assert paper_card_service.parse_card("not json") is None
    assert paper_card_service.parse_card('{"tldr": "只有一句"}') is None


def test_has_usable_abstract():
    from app.models import Item

    fat = Item(
        title="t", url="https://x", url_hash="h", title_simhash=0,
        summary="Smart irrigation reduces water use by thirty percent in maize fields.",
    )
    assert paper_card_service.has_usable_abstract(fat) is True
    thin = Item(
        title="Something about digital agriculture platforms",
        url="https://x", url_hash="h", title_simhash=0,
        summary="Something about digital agriculture platforms。Agricultural Systems",
    )
    assert paper_card_service.has_usable_abstract(thin) is False


@pytest.mark.asyncio
async def test_openalex_ingest_creates_paper_meta(client):
    payload, draft = map_work(SAMPLE_WORK, direction="智慧农业 / 农业物联网")
    async with TestSession() as s:
        result = await ingest_item(s, payload, paper_draft=draft)
        await s.commit()
        assert result.status == "created"
        item_id = result.item_id

    detail = (await client.get(f"/api/v1/items/{item_id}")).json()
    assert detail["category"] == "论文"
    assert detail["doi"] == "10.1016/j.compag.2026.00042"
    assert detail["paper"]["openalex_id"] == "W4212345678"
    assert detail["paper"]["venue"] == "Computers and Electronics in Agriculture"
    assert detail["paper"]["direction"] == "智慧农业 / 农业物联网"
    assert detail["paper"]["authors"][0]["name"] == "Jane Doe"


@pytest.mark.asyncio
async def test_openalex_id_dedup(client):
    payload, draft = map_work(SAMPLE_WORK)
    async with TestSession() as s:
        first = await ingest_item(s, payload, paper_draft=draft)
        await s.commit()

    # same work, no DOI, different landing URL
    work = dict(SAMPLE_WORK)
    work["doi"] = None
    work["primary_location"] = {
        "landing_page_url": "https://openalex.org/W4212345678",
        "source": {"display_name": "Computers and Electronics in Agriculture"},
    }
    payload2, draft2 = map_work(work)
    async with TestSession() as s:
        second = await ingest_item(s, payload2, paper_draft=draft2)
        await s.commit()
    assert second.status == "duplicate"
    assert second.dup_reason == "openalex_id"
    assert second.duplicate_of == first.item_id


@pytest.mark.asyncio
async def test_paper_skips_jina_fetch(client, monkeypatch):
    async def fail_fetch(url):
        raise AssertionError("fetch_fulltext must not be called for papers")

    monkeypatch.setattr(content_service, "fetch_fulltext", fail_fetch)
    monkeypatch.setattr(settings, "deepseek_api_key", "")

    r = await client.post(
        "/api/v1/ingest/items",
        json={
            "title": "A deep learning approach to smart irrigation scheduling",
            "url": "https://doi.org/10.1016/j.compag.2026.00099",
            "summary": "本研究提出一种用于智慧灌溉调度的深度学习方法，在玉米田验证节水效果显著。",
            "source_name": "Computers and Electronics in Agriculture",
            "category": "论文",
            "tags": ["智慧农业"],
        },
        headers={"X-API-Key": TEST_KEY},
    )
    assert r.json()["status"] == "created"
    detail = (await client.get(f"/api/v1/items/{r.json()['item_id']}")).json()
    assert detail["content"] is None
    assert detail["paper"] is not None


@pytest.mark.asyncio
async def test_paper_card_written_after_ingest(client, monkeypatch):
    async def fake_score_call(item):
        return (
            '{"relevant": true, "impact": 20, "substance": 18, "depth": 16,'
            ' "authority": 12, "freshness": 8, "tags": ["智慧农业", "灌溉"]}'
        )

    async def fake_card_call(item):
        return (
            '{"tldr": "提出智慧灌溉调度模型", "method": "LSTM + 墒情", '
            '"finding": "玉米田节水约三成", "direction": "智慧农业 / 农业物联网", '
            '"opportunity": "可扩展到其他大田作物"}'
        )

    monkeypatch.setattr(settings, "deepseek_api_key", "fake-key")
    monkeypatch.setattr(scoring_service, "_call_deepseek", fake_score_call)
    monkeypatch.setattr(paper_card_service, "_call_deepseek", fake_card_call)

    r = await client.post(
        "/api/v1/ingest/items",
        json={
            "title": "A deep learning approach to smart irrigation scheduling",
            "url": "https://doi.org/10.1016/j.compag.2026.00100",
            "summary": "本研究提出一种用于智慧灌溉调度的深度学习方法，结合土壤墒情与气象预报在玉米田验证。",
            "source_name": "Computers and Electronics in Agriculture",
            "category": "论文",
            "tags": ["智慧农业"],
        },
        headers={"X-API-Key": TEST_KEY},
    )
    detail = (await client.get(f"/api/v1/items/{r.json()['item_id']}")).json()
    assert detail["paper"]["card"]["tldr"] == "提出智慧灌溉调度模型"
    assert detail["paper"]["direction"] == "智慧农业 / 农业物联网"


@pytest.mark.asyncio
async def test_list_filter_by_direction(client):
    payload, draft = map_work(SAMPLE_WORK, direction="智慧农业 / 农业物联网")
    other = IngestItemIn(
        title="Satellite phenotyping of wheat canopies under drought",
        url="https://doi.org/10.1007/s11119-026-00999-x",
        summary="利用卫星遥感提取小麦冠层表型，评估干旱胁迫下的形态变化与产量关系。",
        source_name="Precision Agriculture",
        category="论文",
        doi="10.1007/s11119-026-00999-x",
    )
    other_draft = PaperDraft(direction="农业遥感与作物表型", ingested_from="openalex")
    async with TestSession() as s:
        await ingest_item(s, payload, paper_draft=draft)
        await ingest_item(s, other, paper_draft=other_draft)
        await s.commit()

    listed = await client.get(
        "/api/v1/items", params={"category": "论文", "direction": "农业遥感与作物表型"}
    )
    body = listed.json()
    assert body["total"] == 1
    assert body["items"][0]["paper"]["direction"] == "农业遥感与作物表型"

    dirs = (await client.get("/api/v1/paper-directions")).json()
    names = {d["name"] for d in dirs}
    assert "智慧农业 / 农业物联网" in names
    assert "农业遥感与作物表型" in names
