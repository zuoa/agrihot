import os
import sys
from datetime import date

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# shared with the other test modules — see test_scoring.py NOTE
TEST_DB = "sqlite+aiosqlite:////tmp/agrihot_test.db"

os.environ["DATABASE_URL"] = TEST_DB
os.environ["CONTENT_FETCH_ENABLED"] = "false"  # no network in tests

from app.config import settings  # noqa: E402
from app.database import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ApiKey, Base, hash_api_key  # noqa: E402
from app.services import daily_scheduler, daily_service  # noqa: E402

TEST_KEY = "agri_test_key_daily"
ADMIN_PW = "test-admin-password"

engine = create_async_engine(TEST_DB)
TestSession = async_sessionmaker(engine, expire_on_commit=False)

# 日报按收录日期的本地日历日归集（与 daily_service._day_items 口径一致）
TODAY = date.today().isoformat()


async def override_session():
    async with TestSession() as s:
        yield s


app.dependency_overrides[get_session] = override_session


@pytest_asyncio.fixture(autouse=True)
async def fresh_db(monkeypatch):
    monkeypatch.setattr(settings, "admin_password", ADMIN_PW)
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


def sample_item(n: int, **over):
    base = {
        "title": f"农业农村部发布智慧农业发展指导意见（第{n}号）",
        "url": f"https://example.com/news/{n}",
        "summary": "农业农村部今日发布智慧农业发展指导意见，提出到2030年重点任务。",
        "source_name": "示例新闻网",
        "category": "政策",
    }
    base.update(over)
    return base


# login 接口限流 10/minute（全量跑时其他测试文件也会登录），
# admin token 是无状态 HMAC、不落库，整个模块登录一次复用即可。
_auth_cache: dict = {}


async def login(client) -> dict:
    if "headers" not in _auth_cache:
        r = await client.post("/api/v1/admin/login", json={"password": ADMIN_PW})
        assert r.status_code == 200, r.text
        _auth_cache["headers"] = {"X-Admin-Token": r.json()["token"]}
    return _auth_cache["headers"]


async def push_items(client, n: int, start: int = 1) -> list[int]:
    ids = []
    for i in range(start, start + n):
        r = await client.post(
            "/api/v1/ingest/items", json=sample_item(i),
            headers={"X-API-Key": TEST_KEY},
        )
        assert r.status_code == 200, r.text
        ids.append(r.json()["item_id"])
    return ids


# ---------- parse_daily_compose ----------

def test_parse_compose_ok():
    raw = '{"title": "农业农村日报 · 测试", "highlights": ["要点一", "要点二"], "overview": "概述"}'
    out = daily_service.parse_daily_compose(raw)
    assert out == {"title": "农业农村日报 · 测试", "highlights": ["要点一", "要点二"], "overview": "概述"}


def test_parse_compose_truncates_and_filters():
    highlights = ["  " + "长" * 200 + "  ", "", None, "正常要点"] + ["x"] * 10
    raw = __import__("json").dumps({"highlights": highlights})
    out = daily_service.parse_daily_compose(raw)
    assert len(out["highlights"]) <= daily_service.HIGHLIGHT_COUNT_MAX
    assert all(len(h) <= daily_service.HIGHLIGHT_CHARS_MAX for h in out["highlights"])
    assert "正常要点" in out["highlights"]


def test_parse_compose_rejects_garbage():
    assert daily_service.parse_daily_compose("not json") is None
    assert daily_service.parse_daily_compose('{"title": "没有要点"}') is None
    assert daily_service.parse_daily_compose('{"highlights": []}') is None
    assert daily_service.parse_daily_compose('["不是对象"]') is None


# ---------- scheduler helpers ----------

def test_parse_generate_time(monkeypatch):
    monkeypatch.setattr(settings, "daily_generate_time", "07:30")
    assert daily_scheduler._parse_generate_time() == (7, 30)
    monkeypatch.setattr(settings, "daily_generate_time", "垃圾")
    assert daily_scheduler._parse_generate_time() == (20, 0)
    monkeypatch.setattr(settings, "daily_generate_time", "25:00")
    assert daily_scheduler._parse_generate_time() == (20, 0)


# ---------- admin generate endpoint ----------

@pytest.mark.asyncio
async def test_generate_requires_token(client):
    r = await client.post(f"/api/v1/admin/dailies/{TODAY}/generate")
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_generate_404_when_no_items(client):
    auth = await login(client)
    r = await client.post(f"/api/v1/admin/dailies/{TODAY}/generate", headers=auth)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_generate_fallback_without_deepseek(client, monkeypatch):
    """无 DeepSeek key 时降级：标题用日期、要点取资讯标题。"""
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    item_ids = await push_items(client, 3)

    auth = await login(client)
    r = await client.post(f"/api/v1/admin/dailies/{TODAY}/generate", headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["item_count"] == 3
    assert body["highlight_count"] == 3

    r = await client.get(f"/api/v1/dailies/{TODAY}")
    assert r.status_code == 200, r.text
    daily = r.json()
    assert TODAY in daily["title"]
    # 未评分时按 id 倒序（最新入库在前）
    assert daily["highlights"] == [sample_item(i)["title"] for i in (3, 2, 1)]
    assert {it["id"] for it in daily["items"]} == set(item_ids)


@pytest.mark.asyncio
async def test_generate_with_deepseek_compose(client, monkeypatch):
    await push_items(client, 2)

    async def fake_compose(items, day):
        return {
            "title": "农业农村日报 · 智慧农业集中发力",
            "highlights": ["要点甲", "要点乙"],
            "overview": "本期覆盖政策与报道。",
        }

    monkeypatch.setattr(daily_service, "_compose_with_deepseek", fake_compose)
    auth = await login(client)
    r = await client.post(f"/api/v1/admin/dailies/{TODAY}/generate", headers=auth)
    assert r.status_code == 200, r.text

    daily = (await client.get(f"/api/v1/dailies/{TODAY}")).json()
    assert daily["title"] == "农业农村日报 · 智慧农业集中发力"
    assert daily["highlights"] == ["要点甲", "要点乙"]
    assert "本期覆盖政策与报道。" in daily["content"]


@pytest.mark.asyncio
async def test_daily_groups_by_ingest_date_not_publish_date(client, monkeypatch):
    """归集看收录日期而非发布日期：今天收录的旧资讯进今天的日报。"""
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    r = await client.post(
        "/api/v1/ingest/items",
        json=sample_item(200, published_at="2020-01-01T00:00:00+00:00"),
        headers={"X-API-Key": TEST_KEY},
    )
    assert r.status_code == 200, r.text
    item_id = r.json()["item_id"]

    auth = await login(client)
    r = await client.post(f"/api/v1/admin/dailies/{TODAY}/generate", headers=auth)
    assert r.status_code == 200, r.text

    daily = (await client.get(f"/api/v1/dailies/{TODAY}")).json()
    assert [it["id"] for it in daily["items"]] == [item_id]


@pytest.mark.asyncio
async def test_regenerate_overwrites_existing_daily(client, monkeypatch):
    """重复生成是 upsert：同一天只有一条日报，内容被覆盖。"""
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    await push_items(client, 2)

    auth = await login(client)
    r1 = await client.post(f"/api/v1/admin/dailies/{TODAY}/generate", headers=auth)
    assert r1.status_code == 200

    await push_items(client, 1, start=100)  # 再入库一条后重新生成（新 URL 避免去重）
    r2 = await client.post(f"/api/v1/admin/dailies/{TODAY}/generate", headers=auth)
    assert r2.status_code == 200
    assert r2.json()["item_count"] == 3

    r = await client.get("/api/v1/dailies")
    dates = [d["date"] for d in r.json()["dailies"]]
    assert dates.count(TODAY) == 1
