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
# never hit the network in tests; enrichment tests monkeypatch fetch_fulltext
os.environ["CONTENT_FETCH_ENABLED"] = "false"

from app.config import settings  # noqa: E402
from app.database import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ApiKey, Base, hash_api_key  # noqa: E402
from app.services import content_service, scoring_service  # noqa: E402

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


# ---------- prompt builder ----------

def _prompt_item(**over):
    from app.models import Item

    base = {
        "title": "t", "url": "https://x", "url_hash": "h", "title_simhash": 0,
        "summary": "摘要内容", "content": None,
    }
    base.update(over)
    return Item(**base)


def test_prompt_prefers_fulltext_and_truncates():
    body = "正" * (scoring_service.FULLTEXT_MAX_CHARS + 500)
    prompt = scoring_service._build_user_prompt(_prompt_item(content=body))
    assert "正文：" in prompt
    assert "摘要：" not in prompt
    assert "正" * scoring_service.FULLTEXT_MAX_CHARS in prompt
    assert "正" * (scoring_service.FULLTEXT_MAX_CHARS + 1) not in prompt


def test_prompt_falls_back_to_summary():
    prompt = scoring_service._build_user_prompt(_prompt_item())
    assert "摘要：摘要内容" in prompt
    assert "正文：" not in prompt
    # whitespace-only content also falls back
    prompt = scoring_service._build_user_prompt(_prompt_item(content="  \n "))
    assert "摘要：摘要内容" in prompt


def test_prompt_asks_for_topic_tags():
    prompt = scoring_service._build_user_prompt(_prompt_item())
    assert "tags" in prompt
    assert "已有标签" in prompt


# ---------- parse_scores ----------

def test_parse_scores_ok_and_clamp():
    raw = '{"relevant": true, "impact": 99, "substance": 20, "depth": 15, "authority": 10, "freshness": 8}'
    scores = scoring_service.parse_scores(raw)
    assert scores == {
        "impact": 30,  # clamped to cap
        "substance": 20,
        "depth": 15,
        "authority": 10,
        "freshness": 8,
        "relevant": 1,
    }


def test_parse_scores_gate_zeroes_dimensions():
    raw = '{"relevant": false, "impact": 28, "substance": 20, "depth": 15, "authority": 10, "freshness": 8}'
    scores = scoring_service.parse_scores(raw)
    assert scores == {
        "impact": 0, "substance": 0, "depth": 0, "authority": 0, "freshness": 0,
        "relevant": 0,
    }


def test_parse_topic_tags():
    assert scoring_service.parse_topic_tags(
        {"tags": ["智慧农业", " 遥感 ", 12, ""]}
    ) == ["智慧农业", "遥感"]
    assert scoring_service.parse_topic_tags({"tags": "智慧农业 数字乡村"}) == [
        "智慧农业 数字乡村"
    ]
    assert scoring_service.parse_topic_tags({}) == []
    assert scoring_service.parse_topic_tags({"tags": None}) == []


def test_parse_scores_rejects_bad_input():
    assert scoring_service.parse_scores("not json") is None
    assert scoring_service.parse_scores('{"relevant": true, "impact": 10}') is None  # missing dims
    assert scoring_service.parse_scores('["relevant"]') is None
    assert scoring_service.parse_scores(  # gate must be a real bool
        '{"relevant": 1, "impact": 1, "substance": 1, "depth": 1, "authority": 1, "freshness": 1}'
    ) is None
    assert scoring_service.parse_scores(
        '{"relevant": true, "impact": "x", "substance": 1, "depth": 1, "authority": 1, "freshness": 1}'
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
        "relevant": True, "impact": 26, "substance": 22, "depth": 16, "authority": 12, "freshness": 9,
    })  # total 85 >= 75
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
        "relevant": True, "impact": 10, "substance": 5, "depth": 8, "authority": 3, "freshness": 5,
    })  # total 31 < 75
    r = await client.post(
        "/api/v1/ingest/items", json=sample_item(),
        headers={"X-API-Key": TEST_KEY},
    )
    item_id = r.json()["item_id"]
    detail = await client.get(f"/api/v1/items/{item_id}")
    assert detail.json()["is_selected"] is False


@pytest.mark.asyncio
async def test_irrelevant_gate_blocks_selection(client, monkeypatch):
    # high-quality but off-topic: gate zeroes all dimensions -> not selected
    mock_deepseek(monkeypatch, {
        "relevant": False, "impact": 28, "substance": 24, "depth": 18, "authority": 14, "freshness": 10,
    })
    r = await client.post(
        "/api/v1/ingest/items", json=sample_item(),
        headers={"X-API-Key": TEST_KEY},
    )
    item_id = r.json()["item_id"]
    detail = await client.get(f"/api/v1/items/{item_id}")
    assert detail.json()["is_selected"] is False


@pytest.mark.asyncio
async def test_scoring_replaces_tags_from_model(client, monkeypatch):
    mock_deepseek(monkeypatch, {
        "relevant": True, "impact": 26, "substance": 22, "depth": 16,
        "authority": 12, "freshness": 9,
        "tags": ["智慧农业", "农业人工智能", "行业标准"],
        "comment": "标准落地",
    })
    r = await client.post(
        "/api/v1/ingest/items",
        json=sample_item(tags=["黑龙江农科院 寒地龙果 金秋博览会"]),
        headers={"X-API-Key": TEST_KEY},
    )
    detail = (await client.get(f"/api/v1/items/{r.json()['item_id']}")).json()
    assert set(detail["tags"]) == {"智慧农业", "农业人工智能", "行业标准"}


@pytest.mark.asyncio
async def test_scoring_keeps_tags_when_model_omits_them(client, monkeypatch):
    mock_deepseek(monkeypatch, {
        "relevant": True, "impact": 26, "substance": 22, "depth": 16,
        "authority": 12, "freshness": 9,
    })
    r = await client.post(
        "/api/v1/ingest/items", json=sample_item(),
        headers={"X-API-Key": TEST_KEY},
    )
    detail = (await client.get(f"/api/v1/items/{r.json()['item_id']}")).json()
    assert set(detail["tags"]) == {"智慧农业", "政策"}


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


@pytest.mark.asyncio
async def test_daily_top_n_caps_selection(client, monkeypatch):
    """7 items all above threshold -> only the top 5 (DAILY_TOP_N) are selected."""
    import json as _json

    def mk(total_dims):
        return {"relevant": True, **total_dims}

    # totals: 100, 95, 90, 85, 80, 78, 76 — all >= 75
    queue = [
        mk({"impact": 30, "substance": 25, "depth": 20, "authority": 15, "freshness": 10}),
        mk({"impact": 29, "substance": 24, "depth": 19, "authority": 14, "freshness": 9}),
        mk({"impact": 27, "substance": 23, "depth": 18, "authority": 13, "freshness": 9}),
        mk({"impact": 26, "substance": 21, "depth": 17, "authority": 12, "freshness": 9}),
        mk({"impact": 24, "substance": 20, "depth": 16, "authority": 11, "freshness": 9}),
        mk({"impact": 23, "substance": 20, "depth": 15, "authority": 11, "freshness": 9}),
        mk({"impact": 22, "substance": 20, "depth": 15, "authority": 10, "freshness": 9}),
    ]

    async def fake_call(item):
        return _json.dumps(queue.pop(0))

    monkeypatch.setattr(settings, "deepseek_api_key", "fake-key")
    monkeypatch.setattr(scoring_service, "_call_deepseek", fake_call)
    monkeypatch.setattr(settings, "daily_top_n", 5)

    ids = []
    titles = [
        "农业农村部发布智慧农业发展指导意见",
        "河南夏粮总产量再创新高 科技赋能成效显著",
        "农业人工智能行业标准集中立项 覆盖大模型多领域",
        "数字乡村建设试点经验在全国范围推广落地",
        "高标准农田建设突出问题整治推进会召开",
        "遥感技术助力农业灾害预警能力持续提升",
        "种业振兴行动方案明确下一阶段重点任务",
    ]
    for n in range(7):
        r = await client.post(
            "/api/v1/ingest/items",
            json=sample_item(title=titles[n], url=f"https://example.com/news/top{n}"),
            headers={"X-API-Key": TEST_KEY},
        )
        ids.append(r.json()["item_id"])

    flags = [(await client.get(f"/api/v1/items/{i}")).json()["is_selected"] for i in ids]
    assert flags == [True, True, True, True, True, False, False]

    selected = await client.get("/api/v1/items?mode=selected&page_size=100")
    assert selected.json()["total"] == 5


# ---------- full-text backfill (content_service) ----------

def test_strip_jina_preamble():
    raw = (
        "Title: 我国种业知产保护大保护格局基本形成_中国经济网\n\n"
        "URL Source: https://www.ce.cn/xwzx/gnsz/gdxw/202607/t20260728_3112127.shtml\n\n"
        "Markdown Content:\n\n正文第一段。\n\n正文第二段。"
    )
    assert content_service._strip_jina_preamble(raw) == "正文第一段。\n\n正文第二段。"


def test_strip_jina_preamble_passthrough():
    # no Title: header -> untouched
    assert content_service._strip_jina_preamble("直接就是正文") == "直接就是正文"
    # header-like but no body marker -> untouched (don't eat real content)
    raw = "Title: 标题\n\n但没有标记的正文"
    assert content_service._strip_jina_preamble(raw) == raw


FAKE_FULLTEXT = "# 指导意见全文\n\n" + "正文段落。" * 100  # > MIN_CONTENT_CHARS


@pytest.mark.asyncio
async def test_enrich_backfills_fulltext_before_scoring(client, monkeypatch):
    """No content pushed -> Jina fetch fills it in, and scoring sees the body."""
    async def fake_fetch(url):
        return FAKE_FULLTEXT

    seen_prompts = []

    async def fake_deepseek(item):
        seen_prompts.append(scoring_service._build_user_prompt(item))
        return '{"relevant": true, "impact": 26, "substance": 22, "depth": 16, "authority": 12, "freshness": 9}'

    monkeypatch.setattr(content_service, "fetch_fulltext", fake_fetch)
    monkeypatch.setattr(settings, "deepseek_api_key", "fake-key")
    monkeypatch.setattr(scoring_service, "_call_deepseek", fake_deepseek)

    r = await client.post(
        "/api/v1/ingest/items", json=sample_item(),
        headers={"X-API-Key": TEST_KEY},
    )
    detail = (await client.get(f"/api/v1/items/{r.json()['item_id']}")).json()
    assert detail["content"] == FAKE_FULLTEXT
    assert detail["is_selected"] is True
    assert seen_prompts and "正文：" in seen_prompts[0]


@pytest.mark.asyncio
async def test_enrich_skipped_when_content_present(client, monkeypatch):
    """Content pushed by the crawler is never overwritten by the backfill."""
    async def fail_fetch(url):
        raise AssertionError("fetch_fulltext must not be called")

    monkeypatch.setattr(content_service, "fetch_fulltext", fail_fetch)
    monkeypatch.setattr(settings, "deepseek_api_key", "")  # isolate: no scoring

    r = await client.post(
        "/api/v1/ingest/items", json=sample_item(content="爬虫给的正文"),
        headers={"X-API-Key": TEST_KEY},
    )
    detail = (await client.get(f"/api/v1/items/{r.json()['item_id']}")).json()
    assert detail["content"] == "爬虫给的正文"


@pytest.mark.asyncio
async def test_enrich_failure_still_scores_with_summary(client, monkeypatch):
    """Fetch failure is best-effort: content stays empty, scoring uses summary."""
    async def fake_fetch(url):
        return None

    seen_prompts = []

    async def fake_deepseek(item):
        seen_prompts.append(scoring_service._build_user_prompt(item))
        return '{"relevant": true, "impact": 26, "substance": 22, "depth": 16, "authority": 12, "freshness": 9}'

    monkeypatch.setattr(content_service, "fetch_fulltext", fake_fetch)
    monkeypatch.setattr(settings, "deepseek_api_key", "fake-key")
    monkeypatch.setattr(scoring_service, "_call_deepseek", fake_deepseek)

    r = await client.post(
        "/api/v1/ingest/items", json=sample_item(),
        headers={"X-API-Key": TEST_KEY},
    )
    detail = (await client.get(f"/api/v1/items/{r.json()['item_id']}")).json()
    assert detail["content"] is None
    assert detail["is_selected"] is True
    assert seen_prompts and "摘要：" in seen_prompts[0]


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
