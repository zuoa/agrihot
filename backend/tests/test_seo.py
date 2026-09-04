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
async def test_crawler_item_html(client):
    item_id = await create_item(client)
    r = await client.get(f"/seo/items/{item_id}")
    assert r.status_code == 200
    html = r.text
    assert "农业农村部发布智慧农业发展指导意见" in html
    assert 'rel="canonical" href="https://agrihot.com/items/' in html
    assert "application/ld+json" in html
    assert "NewsArticle" in html
    assert "智慧农业发展指导意见" in html
    assert f"/tags/" in html


@pytest.mark.asyncio
async def test_crawler_item_404(client):
    r = await client.get("/seo/items/99999")
    assert r.status_code == 404
    assert "noindex" in r.text
    assert r.headers.get("x-robots-tag", "").startswith("noindex")


@pytest.mark.asyncio
async def test_crawler_escapes_html_in_title(client):
    item_id = await create_item(
        client,
        title="测试<script>alert(1)</script>标题足够长",
        url="https://example.com/news/xss",
        summary="摘要里也有<script>alert(2)</script>应被转义。",
    )
    html = (await client.get(f"/seo/items/{item_id}")).text
    assert "<script>alert(1)</script>" not in html
    assert "<script>alert(2)</script>" not in html
    assert "&lt;script&gt;" in html


@pytest.mark.asyncio
async def test_crawler_home_and_about(client):
    home = await client.get("/seo/")
    assert home.status_code == 200
    assert "农业信息化每日精选" in home.text
    assert "WebSite" in home.text
    about = await client.get("/seo/about")
    assert about.status_code == 200
    assert "关于 AgriHot" in about.text
    assert 'rel="canonical" href="https://agrihot.com/about"' in about.text


@pytest.mark.asyncio
async def test_crawler_daily(client):
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
    r = await client.get("/seo/dailies/2026-09-01")
    assert r.status_code == 200
    assert "智慧农业专题" in r.text
    assert "要点一" in r.text
    assert f"/items/{item_id}" in r.text
    missing = await client.get("/seo/dailies/2010-01-01")
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_crawler_tag_and_feed(client):
    await create_item(client)
    tag = await client.get("/seo/tags/智慧农业")
    assert tag.status_code == 200
    assert "智慧农业" in tag.text
    feed = await client.get("/seo/feed", params={"category": "政策"})
    assert feed.status_code == 200
    assert "全部动态 · 政策" in feed.text
    unknown = await client.get("/seo/tags/不存在的主题xyz")
    assert unknown.status_code == 404


@pytest.mark.asyncio
async def test_crawler_unknown_path_404(client):
    r = await client.get("/seo/admin")
    assert r.status_code == 404
    assert "noindex" in r.text
