import os
import sys

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_DB = "sqlite+aiosqlite:////tmp/agrihot_test.db"

os.environ["DATABASE_URL"] = TEST_DB
os.environ["CONTENT_FETCH_ENABLED"] = "false"  # no network in tests

from app.database import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ApiKey, Base, hash_api_key  # noqa: E402

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
