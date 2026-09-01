"""Admin console: settings, jobs, watchlist, keys, overview, item list."""
import asyncio
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
from app.services import job_runner  # noqa: E402

TEST_KEY = "agri_test_key_console"
ADMIN_PW = "test-admin-password"

engine = create_async_engine(TEST_DB)
TestSession = async_sessionmaker(engine, expire_on_commit=False)


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


async def login(client) -> dict:
    r = await client.post("/api/v1/admin/login", json={"password": ADMIN_PW})
    assert r.status_code == 200, r.text
    return {"X-Admin-Token": r.json()["token"]}


def sample_item(**over):
    base = {
        "title": "农业农村部发布智慧农业发展指导意见",
        "url": "https://example.com/news/console-1",
        "summary": "农业农村部今日发布智慧农业发展指导意见，提出到2030年重点任务。",
        "source_name": "示例新闻网",
        "category": "政策",
        "tags": ["智慧农业"],
    }
    base.update(over)
    return base


# ---------- overview / settings ----------

@pytest.mark.asyncio
async def test_overview_counts(client):
    auth = await login(client)
    headers = {"X-API-Key": TEST_KEY}
    await client.post("/api/v1/ingest/items", json=sample_item(), headers=headers)
    r = await client.get("/api/v1/admin/overview", headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["items"] >= 1
    assert "missing_content" in body
    assert "unscored" in body
    assert "daily_generate" in body["schedulers"]
    assert len(body["jobs"]) >= 4


@pytest.mark.asyncio
async def test_settings_patch_and_hide_secrets(client):
    auth = await login(client)
    r = await client.get("/api/v1/admin/settings", headers=auth)
    assert r.status_code == 200
    text = r.text
    assert "deepseek_api_key" not in text
    assert "admin_password" not in text
    assert "database_url" not in text
    assert r.json()["readonly"]["deepseek_configured"] in (True, False)

    r = await client.patch(
        "/api/v1/admin/settings",
        json={"selection_threshold": 88, "daily_top_n": 3},
        headers=auth,
    )
    assert r.status_code == 200, r.text
    writable = r.json()["writable"]
    assert writable["selection_threshold"]["value"] == 88
    assert writable["selection_threshold"]["source"] == "override"
    assert writable["daily_top_n"]["value"] == 3

    r = await client.patch(
        "/api/v1/admin/settings",
        json={"admin_password": "nope"},
        headers=auth,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_settings_invalid_time(client):
    auth = await login(client)
    r = await client.patch(
        "/api/v1/admin/settings",
        json={"daily_generate_time": "25:99"},
        headers=auth,
    )
    assert r.status_code == 422


# ---------- items list / batch ----------

@pytest.mark.asyncio
async def test_admin_item_list_filters(client):
    headers = {"X-API-Key": TEST_KEY}
    await client.post("/api/v1/ingest/items", json=sample_item(), headers=headers)
    await client.post(
        "/api/v1/ingest/items",
        json=sample_item(
            title="另一篇数字乡村报道内容标题足够长",
            url="https://example.com/news/console-2",
            summary="数字乡村建设进展综述，介绍若干试点县的做法与成效。",
            category="报道",
        ),
        headers=headers,
    )
    auth = await login(client)
    r = await client.get("/api/v1/admin/items", headers=auth, params={"has_content": "false"})
    assert r.status_code == 200, r.text
    assert r.json()["total"] >= 2
    r = await client.get("/api/v1/admin/items", headers=auth, params={"category": "政策"})
    assert all(it["category"] == "政策" for it in r.json()["items"])
    r = await client.get("/api/v1/admin/items", headers=auth, params={"scored": "false"})
    assert r.json()["total"] >= 2


@pytest.mark.asyncio
async def test_batch_delete(client):
    headers = {"X-API-Key": TEST_KEY}
    a = (await client.post("/api/v1/ingest/items", json=sample_item(), headers=headers)).json()["item_id"]
    b = (await client.post(
        "/api/v1/ingest/items",
        json=sample_item(title="第二条足够长的标题用于批量删除测试", url="https://example.com/news/console-3",
                         summary="第二条摘要也要超过十个字才能通过校验。"),
        headers=headers,
    )).json()["item_id"]
    auth = await login(client)
    r = await client.post(
        "/api/v1/admin/items/batch-delete",
        json={"ids": [a, b, 99999]},
        headers=auth,
    )
    assert r.status_code == 200, r.text
    assert set(r.json()["deleted"]) == {a, b}
    assert 99999 in r.json()["missing"]
    assert (await client.get(f"/api/v1/items/{a}")).status_code == 404


# ---------- jobs ----------

@pytest.mark.asyncio
async def test_job_unknown_name(client):
    auth = await login(client)
    r = await client.post("/api/v1/admin/jobs/not-a-job/run", json={}, headers=auth)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_job_overlap_and_status(client, monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow(_params):
        started.set()
        await release.wait()
        return {"ok": True}

    monkeypatch.setitem(job_runner.HANDLERS, "retag", slow)
    auth = await login(client)
    r = await client.post("/api/v1/admin/jobs/retag/run", json={}, headers=auth)
    assert r.status_code == 202, r.text
    await asyncio.wait_for(started.wait(), timeout=2)
    r2 = await client.post("/api/v1/admin/jobs/retag/run", json={}, headers=auth)
    assert r2.status_code == 409
    release.set()
    status = None
    for _ in range(40):
        jobs = (await client.get("/api/v1/admin/jobs", headers=auth)).json()["jobs"]
        status = next(j for j in jobs if j["name"] == "retag")
        if status["status"] == "ok":
            break
        await asyncio.sleep(0.05)
    assert status is not None and status["status"] == "ok"
    assert status["stats"]["ok"] is True


# ---------- watchlist ----------

@pytest.mark.asyncio
async def test_watchlist_get_and_put(client):
    auth = await login(client)
    r = await client.get("/api/v1/admin/watchlist", headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "directions" in body
    assert "prescreen" in body
    body["directions"] = [{"name": "测试方向", "queries": ["smart agriculture"]}]
    r = await client.put("/api/v1/admin/watchlist", json=body, headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["directions"][0]["name"] == "测试方向"

    r = await client.put(
        "/api/v1/admin/watchlist",
        json={"directions": [{"name": "", "queries": []}], "journals": [], "authors": [], "prescreen": []},
        headers=auth,
    )
    assert r.status_code == 422


# ---------- api keys ----------

@pytest.mark.asyncio
async def test_api_key_create_and_disable(client):
    auth = await login(client)
    r = await client.post("/api/v1/admin/api-keys", json={"name": "new-bot"}, headers=auth)
    assert r.status_code == 200, r.text
    created = r.json()
    assert created["key"].startswith("agri_")
    key_id = created["id"]
    raw = created["key"]

    r = await client.get("/api/v1/admin/api-keys", headers=auth)
    names = [k["name"] for k in r.json()]
    assert "new-bot" in names
    assert all("key" not in k or k.get("key") is None for k in r.json() if k["id"] == key_id)

    ingest = await client.post(
        "/api/v1/ingest/items",
        json=sample_item(url="https://example.com/news/console-key"),
        headers={"X-API-Key": raw},
    )
    assert ingest.status_code == 200, ingest.text

    r = await client.patch(
        f"/api/v1/admin/api-keys/{key_id}",
        json={"is_active": False},
        headers=auth,
    )
    assert r.json()["is_active"] is False
    ingest = await client.post(
        "/api/v1/ingest/items",
        json=sample_item(url="https://example.com/news/console-key-2"),
        headers={"X-API-Key": raw},
    )
    assert ingest.status_code == 401
