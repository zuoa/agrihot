import os
import sys
from urllib.parse import quote

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_DB = "sqlite+aiosqlite:////tmp/agrihot_test.db"

os.environ["DATABASE_URL"] = TEST_DB
os.environ["CONTENT_FETCH_ENABLED"] = "false"
os.environ["LITERATURE_FETCH_ENABLED"] = "false"

from app.database import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ApiKey, Base, hash_api_key  # noqa: E402
from app.services.topic_service import (  # noqa: E402
    derive_phrases,
    effective_phrases,
    item_slug,
    normalize_phrase,
    parse_item_slug,
    parse_search_phrases,
    parse_tag_query,
)

TEST_KEY = "agri_test_key_topics"

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


def sample_item(**over):
    base = {
        "title": "农业农村部发布智慧农业发展指导意见",
        "url": "https://example.com/news/topics-1",
        "summary": "农业农村部今日发布智慧农业发展指导意见，提出到2030年重点任务。",
        "source_name": "示例新闻网",
        "category": "政策",
        "tags": ["智慧农业", "政策"],
    }
    base.update(over)
    return base


async def create_item(client, **over) -> int:
    r = await client.post(
        "/api/v1/ingest/items",
        json=sample_item(**over),
        headers={"X-API-Key": TEST_KEY},
    )
    assert r.status_code == 200, r.text
    return r.json()["item_id"]


def test_derive_phrases_skips_generic_and_orders_by_specificity():
    assert derive_phrases(["政策", "花生", "大豆", "四川省农科院", "薯花系列"]) == [
        "四川省农科院 薯花系列 大豆 花生",
        "四川省农科院 薯花系列",
    ]
    assert derive_phrases(["政策", "报道"]) == []
    assert derive_phrases(["花生"]) == []


def test_normalize_phrase_drops_generic_and_short():
    assert normalize_phrase("四川省农科院 花生 大豆 政策") == "四川省农科院 花生 大豆"
    assert normalize_phrase("政策") is None
    assert normalize_phrase("花生") is None


def test_effective_phrases_prefers_stored():
    assert effective_phrases(
        ["花生", "大豆"],
        ["四川省农科院 薯花系列 花生"],
    ) == ["四川省农科院 薯花系列 花生", "大豆 花生"]


def test_parse_search_phrases_from_model_json():
    assert parse_search_phrases({
        "search_phrases": ["四川省农科院 薯花系列 花生", "政策", 12],
    }) == ["四川省农科院 薯花系列 花生"]
    assert parse_search_phrases({"search_phrases": "花生 大豆"}) == ["花生 大豆"]
    assert parse_search_phrases({}) == []


def test_item_slug_roundtrip():
    slug = item_slug(12, "一条标题", ["四川省农科院 薯花系列"])
    assert slug.endswith("-12")
    assert " " not in slug
    assert parse_item_slug(slug) == 12
    assert parse_item_slug("nope") is None


def test_parse_tag_query_splits_commas_not_spaces():
    assert parse_tag_query("花生", "大豆，薯花系列") == ["花生", "大豆", "薯花系列"]


@pytest.mark.asyncio
async def test_items_match_all_and_any(client):
    a = await create_item(
        client,
        url="https://example.com/a",
        tags=["四川省农科院", "花生", "大豆", "薯花系列"],
        title="四川省农科院育成薯花系列花生大豆新品种",
        summary="四川省农科院发布薯花系列花生与大豆新品种。",
    )
    b = await create_item(
        client,
        url="https://example.com/b",
        tags=["花生", "智慧农业"],
        title="花生主产区智慧农业观测",
        summary="花生主产区部署物联网监测。",
    )

    r = await client.get(
        "/api/v1/items",
        params={"tags": "四川省农科院,花生,大豆,薯花系列", "match": "all"},
    )
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["id"] == a

    r = await client.get("/api/v1/items", params={"tags": "花生,大豆", "match": "any"})
    assert {it["id"] for it in r.json()["items"]} == {a, b}


@pytest.mark.asyncio
async def test_topic_atomic_tag_vs_phrase(client):
    item_id = await create_item(
        client,
        tags=["四川省农科院", "花生", "大豆", "薯花系列"],
        title="四川省农科院育成薯花系列花生大豆新品种",
        summary="四川省农科院发布薯花系列花生与大豆新品种。",
    )

    tag = (await client.get("/api/v1/topics", params={"name": "花生"})).json()
    assert tag["kind"] == "tag"
    assert tag["total"] == 1
    assert tag["items"][0]["id"] == item_id

    phrase = (
        await client.get(
            "/api/v1/topics",
            params={"name": "四川省农科院 花生 大豆 薯花系列"},
        )
    ).json()
    assert phrase["kind"] == "phrase"
    assert phrase["tokens"] == ["四川省农科院", "花生", "大豆", "薯花系列"]
    assert phrase["total"] == 1
    assert phrase["items"][0]["id"] == item_id

    listed = await client.get("/api/v1/tags")
    names = {t["name"] for t in listed.json()}
    assert "四川省农科院 花生 大豆 薯花系列" not in names
    assert {"四川省农科院", "花生", "大豆", "薯花系列"} <= names


@pytest.mark.asyncio
async def test_topic_english_phrase_tag_is_atomic(client):
    await create_item(
        client,
        url="https://example.com/journal",
        tags=["Journal of Advanced Research", "棉蚜"],
        title="棉蚜表观遗传研究",
        summary="棉蚜 DNA 甲基化研究发表于 Journal of Advanced Research。",
    )
    r = (await client.get(
        "/api/v1/topics",
        params={"name": "Journal of Advanced Research"},
    )).json()
    assert r["kind"] == "tag"
    assert r["total"] == 1


@pytest.mark.asyncio
async def test_topic_phrase_falls_back_to_title(client):
    item_id = await create_item(
        client,
        tags=["智慧农业"],
        title="四川省农科院育成薯花系列花生新品种",
        summary="新品种已进入示范推广。",
    )
    r = (await client.get(
        "/api/v1/topics",
        params={"name": "四川省农科院 薯花系列 花生"},
    )).json()
    assert r["kind"] == "phrase"
    assert r["total"] == 1
    assert r["items"][0]["id"] == item_id


@pytest.mark.asyncio
async def test_item_exposes_derived_phrases_and_slug(client):
    item_id = await create_item(
        client,
        tags=["四川省农科院", "花生", "大豆", "薯花系列", "政策"],
    )
    detail = (await client.get(f"/api/v1/items/{item_id}")).json()
    assert detail["search_phrases"][0] == "四川省农科院 薯花系列 大豆 花生"
    assert detail["slug"].endswith(f"-{item_id}")
    assert " " not in detail["slug"]


@pytest.mark.asyncio
async def test_related_items_by_tag_overlap(client):
    a = await create_item(
        client,
        url="https://example.com/rel-a",
        tags=["花生", "大豆"],
        title="花生大豆轮作试验",
        summary="花生与大豆轮作提高地力。",
    )
    b = await create_item(
        client,
        url="https://example.com/rel-b",
        tags=["花生", "智慧农业"],
        title="花生田物联网监测",
        summary="花生田部署土壤墒情传感器。",
    )
    await create_item(
        client,
        url="https://example.com/rel-c",
        tags=["遥感"],
        title="遥感估产进展",
        summary="遥感估产方法综述若干进展。",
    )
    r = (await client.get(f"/api/v1/items/{a}/related")).json()
    ids = [it["id"] for it in r["items"]]
    assert b in ids
    assert a not in ids


@pytest.mark.asyncio
async def test_sitemap_includes_phrase_not_as_tag(client):
    await create_item(
        client,
        tags=["四川省农科院", "花生", "大豆", "薯花系列"],
    )
    body = (await client.get("/sitemap.xml")).text
    phrase = "四川省农科院 薯花系列 大豆 花生"
    assert quote(phrase, safe="") in body
    listed = await client.get("/api/v1/tags")
    assert phrase not in {t["name"] for t in listed.json()}
