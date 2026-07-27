import os
import sys

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# NOTE: must match test_ingest.py — score_and_mark runs in a background task
# using app.database.SessionLocal (module-level singleton), so all test files
# need to share one DATABASE_URL.
TEST_DB = "sqlite+aiosqlite:////tmp/agrihot_test.db"

os.environ["DATABASE_URL"] = TEST_DB

from app.config import settings  # noqa: E402
from app.database import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ApiKey, Base, hash_api_key  # noqa: E402
from app.services import scoring_service  # noqa: E402

TEST_KEY = "agri_test_key_scoring"

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
        "source_name": "农业农村部官网",
        "category": "政策",
        "tags": ["智慧农业", "政策"],
    }
    base.update(over)
    return base


# ---------- parse_scores ----------

def test_parse_scores_ok_and_clamp():
    raw = '{"relevance": 99, "importance": 20, "quality": 15, "credibility": 10, "timeliness": 8}'
    scores = scoring_service.parse_scores(raw)
    assert scores == {
        "relevance": 30,  # clamped to cap
        "importance": 20,
        "quality": 15,
        "credibility": 10,
        "timeliness": 8,
    }


def test_parse_scores_rejects_bad_input():
    assert scoring_service.parse_scores("not json") is None
    assert scoring_service.parse_scores('{"relevance": 10}') is None  # missing dims
    assert scoring_service.parse_scores('["relevance"]') is None
    assert scoring_service.parse_scores(
        '{"relevance": "x", "importance": 1, "quality": 1, "credibility": 1, "timeliness": 1}'
    ) is None


# ---------- scoring via background task ----------

def mock_deepseek(monkeypatch, scores: dict):
    import json as _json

    async def fake_call(item):
        return _json.dumps(scores)

    monkeypatch.setattr(settings, "deepseek_api_key", "fake-key")
    monkeypatch.setattr(scoring_service, "_call_deepseek", fake_call)


@pytest.mark.asyncio
async def test_high_score_marks_selected(client, monkeypatch):
    mock_deepseek(monkeypatch, {
        "relevance": 28, "importance": 22, "quality": 16, "credibility": 12, "timeliness": 9,
    })  # total 87 >= 70
    r = await client.post(
        "/api/v1/ingest/items", json=sample_item(),
        headers={"X-API-Key": TEST_KEY},
    )
    item_id = r.json()["item_id"]
    detail = await client.get(f"/api/v1/items/{item_id}")
    assert detail.json()["is_selected"] is True


@pytest.mark.asyncio
async def test_low_score_stays_unselected(client, monkeypatch):
    mock_deepseek(monkeypatch, {
        "relevance": 10, "importance": 5, "quality": 8, "credibility": 3, "timeliness": 5,
    })  # total 31 < 70
    r = await client.post(
        "/api/v1/ingest/items", json=sample_item(),
        headers={"X-API-Key": TEST_KEY},
    )
    item_id = r.json()["item_id"]
    detail = await client.get(f"/api/v1/items/{item_id}")
    assert detail.json()["is_selected"] is False


@pytest.mark.asyncio
async def test_scoring_disabled_without_api_key(client, monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    r = await client.post(
        "/api/v1/ingest/items", json=sample_item(),
        headers={"X-API-Key": TEST_KEY},
    )
    assert r.json()["status"] == "created"  # push still works
    detail = await client.get(f"/api/v1/items/{r.json()['item_id']}")
    assert detail.json()["is_selected"] is False


@pytest.mark.asyncio
async def test_scoring_failure_is_fail_closed(client, monkeypatch):
    async def failing_call(item):
        return None

    monkeypatch.setattr(settings, "deepseek_api_key", "fake-key")
    monkeypatch.setattr(scoring_service, "_call_deepseek", failing_call)
    r = await client.post(
        "/api/v1/ingest/items", json=sample_item(),
        headers={"X-API-Key": TEST_KEY},
    )
    detail = await client.get(f"/api/v1/items/{r.json()['item_id']}")
    assert detail.json()["is_selected"] is False


# ---------- delete endpoint ----------

@pytest.mark.asyncio
async def test_delete_requires_api_key(client):
    r = await client.delete("/api/v1/ingest/items/1")
    assert r.status_code in (401, 403)
    r = await client.delete(
        "/api/v1/ingest/items/1", headers={"X-API-Key": "wrong"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_delete_item(client):
    headers = {"X-API-Key": TEST_KEY}
    r = await client.post("/api/v1/ingest/items", json=sample_item(), headers=headers)
    item_id = r.json()["item_id"]

    r = await client.delete(f"/api/v1/ingest/items/{item_id}", headers=headers)
    assert r.status_code == 200
    assert r.json() == {"status": "deleted", "item_id": item_id}

    assert (await client.get(f"/api/v1/items/{item_id}")).status_code == 404
    assert (await client.get("/api/v1/items")).json()["total"] == 0

    # second delete -> 404
    r = await client.delete(f"/api/v1/ingest/items/{item_id}", headers=headers)
    assert r.status_code == 404
