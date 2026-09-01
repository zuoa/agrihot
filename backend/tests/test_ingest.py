import os
import sys

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_DB = "sqlite+aiosqlite:////tmp/agrihot_test.db"

os.environ["DATABASE_URL"] = TEST_DB
os.environ["CONTENT_FETCH_ENABLED"] = "false"  # no network in tests
os.environ["LITERATURE_FETCH_ENABLED"] = "false"

from app.database import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ApiKey, Base, Item, Tag, hash_api_key  # noqa: E402
from app.services import dedup  # noqa: E402
from app.services.ingest_service import (  # noqa: E402
    normalize_tags,
    retag_all_items,
)

TEST_KEY = "agri_test_key_123"

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
        "url": "https://example.com/news/1001",
        "summary": "农业农村部今日发布智慧农业发展指导意见，提出到2030年重点任务。",
        "source_name": "示例新闻网",
        "category": "政策",
        "tags": ["智慧农业", "政策"],
    }
    base.update(over)
    return base


@pytest.mark.asyncio
async def test_push_requires_api_key(client):
    r = await client.post("/api/v1/ingest/items", json=sample_item())
    assert r.status_code in (401, 403)
    r = await client.post(
        "/api/v1/ingest/items", json=sample_item(),
        headers={"X-API-Key": "wrong-key"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_push_creates_item(client):
    r = await client.post(
        "/api/v1/ingest/items", json=sample_item(),
        headers={"X-API-Key": TEST_KEY},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "created"
    assert body["item_id"]


@pytest.mark.asyncio
async def test_exact_url_dedup_with_tracking_params(client):
    headers = {"X-API-Key": TEST_KEY}
    r1 = await client.post("/api/v1/ingest/items", json=sample_item(), headers=headers)
    assert r1.json()["status"] == "created"

    # same article, different tracking params / fragment
    dup = sample_item(url="https://example.com/news/1001/?utm_source=rss&from=weixin#top")
    r2 = await client.post("/api/v1/ingest/items", json=dup, headers=headers)
    body = r2.json()
    assert body["status"] == "duplicate"
    assert body["dup_reason"] == "exact_url"
    assert body["duplicate_of"] == r1.json()["item_id"]


@pytest.mark.asyncio
async def test_similar_title_dedup_merges_source(client):
    headers = {"X-API-Key": TEST_KEY}
    r1 = await client.post("/api/v1/ingest/items", json=sample_item(), headers=headers)
    item_id = r1.json()["item_id"]

    similar = sample_item(
        title="农业农村部发布智慧农业发展指导意见（全文）",
        url="https://other-site.cn/articles/xyz",
        source_name="另一来源",
    )
    r2 = await client.post("/api/v1/ingest/items", json=similar, headers=headers)
    body = r2.json()
    assert body["status"] == "duplicate"
    assert body["dup_reason"] == "similar_title"

    # source merged into the original item
    detail = await client.get(f"/api/v1/items/{item_id}")
    sources = detail.json()["sources"]
    assert len(sources) == 2
    assert any(s["name"] == "另一来源" for s in sources)


@pytest.mark.asyncio
async def test_doi_dedup_across_different_urls(client):
    headers = {"X-API-Key": TEST_KEY}
    paper = sample_item(
        title="A deep learning approach to smart irrigation scheduling",
        url="https://doi.org/10.1016/j.compag.2026.00001",
        summary="本研究提出一种用于智慧灌溉调度的深度学习方法，在玉米田验证节水效果。",
        source_name="Computers and Electronics in Agriculture",
        category="论文",
        tags=["智慧农业", "灌溉"],
        doi="10.1016/j.compag.2026.00001",
    )
    r1 = await client.post("/api/v1/ingest/items", json=paper, headers=headers)
    assert r1.json()["status"] == "created"
    item_id = r1.json()["item_id"]

    dup = dict(paper)
    dup["url"] = "https://www.sciencedirect.com/science/article/pii/S016816992600001"
    dup["doi"] = "https://doi.org/10.1016/j.compag.2026.00001"
    dup["source_name"] = "ScienceDirect"
    r2 = await client.post("/api/v1/ingest/items", json=dup, headers=headers)
    body = r2.json()
    assert body["status"] == "duplicate"
    assert body["dup_reason"] == "exact_doi"
    assert body["duplicate_of"] == item_id

    detail = await client.get(f"/api/v1/items/{item_id}")
    assert detail.json()["doi"] == "10.1016/j.compag.2026.00001"
    assert len(detail.json()["sources"]) == 2


@pytest.mark.asyncio
async def test_doi_extracted_from_url_when_field_omitted(client):
    headers = {"X-API-Key": TEST_KEY}
    r = await client.post(
        "/api/v1/ingest/items",
        json=sample_item(
            title="Remote sensing of crop phenotyping at field scale",
            url="https://doi.org/10.1007/s11119-026-00001-x",
            summary="田间尺度作物表型遥感监测方法综述，覆盖无人机与卫星数据融合。",
            category="论文",
            source_name="Precision Agriculture",
        ),
        headers=headers,
    )
    assert r.json()["status"] == "created"
    detail = await client.get(f"/api/v1/items/{r.json()['item_id']}")
    assert detail.json()["doi"] == "10.1007/s11119-026-00001-x"
    assert detail.json()["paper"] is not None


@pytest.mark.asyncio
async def test_distinct_items_not_deduped(client):
    headers = {"X-API-Key": TEST_KEY}
    await client.post("/api/v1/ingest/items", json=sample_item(), headers=headers)
    other = sample_item(
        title="基于遥感的冬小麦产量估算研究取得新进展",
        url="https://journal.example.edu.cn/paper/555",
        summary="研究团队利用高分辨率遥感影像实现冬小麦产量精准估算，误差低于百分之五。",
    )
    r = await client.post("/api/v1/ingest/items", json=other, headers=headers)
    assert r.json()["status"] == "created"


@pytest.mark.asyncio
async def test_batch_push(client):
    headers = {"X-API-Key": TEST_KEY}
    payload = {
        "items": [
            sample_item(),
            sample_item(url="https://example.com/news/1001"),  # exact dup
            sample_item(
                title="数字乡村建设试点名单公布",
                url="https://example.com/news/2002",
                summary="多部门联合公布新一批数字乡村建设试点地区名单，覆盖百余个县市区。",
            ),
        ]
    }
    r = await client.post("/api/v1/ingest/items/batch", json=payload, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert body["created"] == 2
    assert body["duplicate"] == 1


@pytest.mark.asyncio
async def test_public_endpoints(client):
    headers = {"X-API-Key": TEST_KEY}
    await client.post("/api/v1/ingest/items", json=sample_item(), headers=headers)

    r = await client.get("/api/v1/items")
    assert r.status_code == 200
    assert r.json()["total"] == 1

    r = await client.get("/api/v1/items?q=智慧农业")
    assert r.json()["total"] == 1

    r = await client.get("/api/v1/tags")
    assert {t["name"] for t in r.json()} >= {"智慧农业", "政策"}


# ---------- tag normalization ----------

def test_normalize_tags_splits_space_separated_keywords():
    assert normalize_tags(["黑龙江农科院 寒地龙果 金秋博览会 成果转化"]) == [
        "黑龙江农科院", "寒地龙果", "金秋博览会", "成果转化",
    ]


def test_normalize_tags_splits_middle_dot_and_backticks():
    assert normalize_tags(["`政策` · `种业振兴` · `知识产权` · `制度创新`"]) == [
        "政策", "种业振兴", "知识产权", "制度创新",
    ]


def test_normalize_tags_keeps_english_phrase_and_mixed_tokens():
    result = normalize_tags(
        ["棉蚜 DNA甲基化 表观遗传 Journal of Advanced Research"]
    )
    assert result == [
        "棉蚜", "DNA甲基化", "表观遗传", "Journal of Advanced Research",
    ]


def test_normalize_tags_drops_dates_numbers_and_dedupes():
    assert normalize_tags(
        ["#智慧农业", "智慧农业", "中国农科院 茶叶所 2026年8月", "2024"]
    ) == ["智慧农业", "中国农科院", "茶叶所"]


def test_normalize_tags_does_not_merge_separate_ascii_tags():
    assert normalize_tags(["IoT", "AI", "NDVI"]) == ["IoT", "AI", "NDVI"]


def test_normalize_tags_splits_chinese_punctuation():
    assert normalize_tags(["智慧农业、数字乡村，遥感"]) == [
        "智慧农业", "数字乡村", "遥感",
    ]


def test_normalize_tags_keeps_already_split():
    assert normalize_tags(["政策", "高标准农田", "粮食安全"]) == [
        "政策", "高标准农田", "粮食安全",
    ]


def test_normalize_tags_drops_overlong_unspaced_blob():
    blob = "黑龙江农科院寒地龙果金秋博览会成果转化专题报道"
    assert normalize_tags([blob]) == []


@pytest.mark.asyncio
async def test_ingest_splits_concatenated_tags(client):
    headers = {"X-API-Key": TEST_KEY}
    r = await client.post(
        "/api/v1/ingest/items",
        json=sample_item(tags=["黑龙江农科院 寒地龙果 成果转化", "智慧农业"]),
        headers=headers,
    )
    assert r.status_code == 200, r.text
    item_id = r.json()["item_id"]

    detail = await client.get(f"/api/v1/items/{item_id}")
    assert set(detail.json()["tags"]) == {
        "黑龙江农科院", "寒地龙果", "成果转化", "智慧农业",
    }

    listed = await client.get("/api/v1/tags")
    names = {t["name"] for t in listed.json()}
    assert "黑龙江农科院 寒地龙果 成果转化" not in names
    assert {"黑龙江农科院", "寒地龙果", "成果转化", "智慧农业"} <= names


@pytest.mark.asyncio
async def test_ingest_accepts_tags_as_single_string(client):
    headers = {"X-API-Key": TEST_KEY}
    payload = sample_item()
    payload["tags"] = "智慧农业 数字乡村 政策"
    r = await client.post("/api/v1/ingest/items", json=payload, headers=headers)
    assert r.status_code == 200, r.text
    item_id = r.json()["item_id"]
    detail = await client.get(f"/api/v1/items/{item_id}")
    assert set(detail.json()["tags"]) == {"智慧农业", "数字乡村", "政策"}


@pytest.mark.asyncio
async def test_retag_all_items_splits_existing_blobs_and_drops_orphans():
    url = "https://example.com/retag-blob"
    async with TestSession() as s:
        blob = Tag(name="黑龙江农科院 寒地龙果 成果转化")
        item = Item(
            title="寒地龙果成果转化",
            url=url,
            url_hash=dedup.url_hash(url),
            title_simhash=dedup.to_signed64(dedup.title_simhash("寒地龙果成果转化")),
            summary="这是用于测试标签重切分的摘要文字。",
            source_name="测试",
            category="报道",
        )
        item.tags = [blob]
        s.add(item)
        await s.commit()
        item_id = item.id

    async with TestSession() as s:
        stats = await retag_all_items(s)
        await s.commit()
        assert stats["changed"] == 1
        assert stats["orphans"] >= 1
        item = await s.get(Item, item_id)
        assert {t.name for t in item.tags} == {"黑龙江农科院", "寒地龙果", "成果转化"}
        leftover = (
            await s.execute(
                select(Tag).where(Tag.name == "黑龙江农科院 寒地龙果 成果转化")
            )
        ).scalar_one_or_none()
        assert leftover is None
