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
from app.models import ApiKey, Base, hash_api_key  # noqa: E402

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
