import os
import sys

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# shared with the other test modules — see test_scoring.py NOTE
TEST_DB = "sqlite+aiosqlite:////tmp/agrihot_test.db"

os.environ["DATABASE_URL"] = TEST_DB
os.environ["CONTENT_FETCH_ENABLED"] = "false"  # no network in tests

from app.database import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ApiKey, Base, Daily, hash_api_key  # noqa: E402

TEST_KEY = "agri_test_key_views"

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


async def create_item(client) -> int:
    r = await client.post(
        "/api/v1/ingest/items",
        json=sample_item(),
        headers={"X-API-Key": TEST_KEY},
    )
    assert r.status_code == 200, r.text
    return r.json()["item_id"]


@pytest.mark.asyncio
async def test_detail_view_increments_count(client):
    item_id = await create_item(client)

    # 列表返回初始阅读数 0
    r = await client.get("/api/v1/items")
    assert r.status_code == 200
    assert r.json()["items"][0]["view_count"] == 0

    # 每打开一次详情页 +1
    r = await client.get(f"/api/v1/items/{item_id}")
    assert r.status_code == 200
    assert r.json()["view_count"] == 1

    r = await client.get(f"/api/v1/items/{item_id}")
    assert r.json()["view_count"] == 2

    # 列表同步反映累计值
    r = await client.get("/api/v1/items")
    assert r.json()["items"][0]["view_count"] == 2


@pytest.mark.asyncio
async def test_view_count_404_not_counted(client):
    r = await client.get("/api/v1/items/999")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_stats_empty(client):
    r = await client.get("/api/v1/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["items"] == 0
    assert data["by_category"] == {}
    assert data["selected"] == 0
    assert data["dailies"] == 0
    assert data["tags"] == 0
    assert data["sources"] == 0
    assert data["views"] == 0
    assert data["since"] is None


@pytest.mark.asyncio
async def test_stats_counts_items_categories_and_sources(client):
    from datetime import date

    rows = [
        ("政策一：农业农村部印发数字乡村发展指南若干措施", "https://example.com/s1", "政策", "农业农村部"),
        ("政策二：财政部下达智慧农业专项资金管理办法", "https://example.com/s2", "政策", "财政部"),
        ("论文：基于遥感的作物长势监测方法研究综述", "https://example.com/s3", "论文", "农业工程学报"),
        ("报道：某省数字乡村建设现场见闻与实践", "https://example.com/s4", "报道", "农民日报"),
        ("行业：农业物联网设备出货量持续增长观察", "https://example.com/s5", "行业", "农民日报"),
        ("报道二：地方农技站推广信息化服务纪实", "https://example.com/s6", "报道", ""),
    ]
    for title, url, category, source in rows:
        r = await client.post(
            "/api/v1/ingest/items",
            json=sample_item(title=title, url=url, category=category, source_name=source),
            headers={"X-API-Key": TEST_KEY},
        )
        assert r.status_code == 200, r.text

    async with TestSession() as s:
        s.add(Daily(
            date=date(2026, 7, 15),
            title="农业农村日报 · 测试",
            highlights=["要点"],
            content="",
            item_ids=[],
        ))
        await s.commit()

    item_id = (await client.get("/api/v1/items")).json()["items"][0]["id"]
    await client.get(f"/api/v1/items/{item_id}")

    r = await client.get("/api/v1/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["items"] == 6
    assert data["by_category"] == {"政策": 2, "论文": 1, "报道": 2, "行业": 1}
    assert data["dailies"] == 1
    assert data["tags"] == 2  # sample_item default tags
    assert data["sources"] == 4  # empty source_name excluded; 农民日报 counted once
    assert data["views"] == 1
    assert data["since"] is not None
