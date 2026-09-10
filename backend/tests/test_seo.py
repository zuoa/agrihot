import os
import sys
from datetime import date

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
from app.models import ApiKey, Base, Daily, hash_api_key  # noqa: E402

TEST_KEY = "agri_test_key_seo"

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
        "url": "https://example.com/news/seo-1",
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


@pytest.mark.asyncio
async def test_robots_txt(client):
    r = await client.get("/robots.txt")
    assert r.status_code == 200
    assert "Disallow: /admin" in r.text
    assert "Disallow: /api/" in r.text
    assert "Sitemap: https://agrihot.com/sitemap.xml" in r.text


@pytest.mark.asyncio
async def test_sitemap_includes_pages_and_item(client):
    item_id = await create_item(client)
    r = await client.get("/sitemap.xml")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/xml")
    body = r.text
    assert "https://agrihot.com/" in body
    assert "https://agrihot.com/feed" in body
    assert "https://agrihot.com/dailies" in body
    assert f"https://agrihot.com/items/{item_id}" in body
    assert "智慧农业" in body or "%E6%99%BA%E6%85%A7%E5%86%9C%E4%B8%9A" in body


@pytest.mark.asyncio
async def test_sitemap_includes_daily(client):
    item_id = await create_item(client)
    day = date(2026, 9, 1)
    async with TestSession() as s:
        s.add(Daily(
            date=day,
            title="农业农村日报 · 智慧农业专题",
            highlights=["要点一：智慧农业指导意见发布"],
            content="今日聚焦智慧农业。",
            item_ids=[item_id],
        ))
        await s.commit()
    r = await client.get("/sitemap.xml")
    assert "https://agrihot.com/dailies/2026-09-01" in r.text
