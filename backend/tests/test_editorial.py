"""Reading aids must stay truthful across API shapes, edits and backfills."""
import json
import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:////tmp/agrihot_test.db")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.database import ensure_schema, get_session
from app.main import app
from app.models import Base, Item, PipelineState
from app.security import issue_admin_token
from app.services import editorial_service as editorial, scoring_service
from app.services.editorial_backfill import backfill


def article(**overrides):
    return Item(**({"title": "农业农村部发布智慧农业行动方案", "summary": "农业农村部印发本行动方案，明确未来三年建设重点及实施责任。",
                   "url": "https://www.moa.gov.cn/gk/tzgg/202610/t20261001_123.htm", "url_hash": "editorial-1",
                   "title_simhash": 1, "source_name": "农业农村部", "category": "政策", "score": 86,
                   "is_selected": True, "tags": []} | overrides))


def answer(**overrides):
    return {"attention_point": "方案明确未来三年建设重点及实施责任，可据此跟踪任务落地。",
            "source_provenance": {"type": "policy", "quote": "农业农村部印发本行动方案，明确未来三年建设重点及实施责任。"}} | overrides


@pytest_asyncio.fixture
async def editorial_db(tmp_path):
    url = os.getenv("AGRIHOT_TEST_EDITORIAL_POSTGRES_URL") or f"sqlite+aiosqlite:///{tmp_path}/editorial.db"
    if url.startswith("postgresql"):
        assert url.rsplit("/", 1)[-1].startswith("agrihot_specials_test_"), "Use a dedicated test database"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await ensure_schema(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def editorial_client(editorial_db, monkeypatch):
    async def dependency():
        async with editorial_db() as session:
            yield session
    old = dict(app.dependency_overrides)
    app.dependency_overrides[get_session] = dependency
    monkeypatch.setattr(settings, "admin_password", "editorial-test-password")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
    app.dependency_overrides.update(old)


@pytest.mark.parametrize("url,kind,quote,primary", [
    ("https://www.moa.gov.cn/news/1", "policy", "农业农村部印发本行动方案，明确未来三年建设重点及实施责任。", True),
    ("https://www.moa.gov.cn/news/1", "unknown", "", False),  # official republication/interpretation
    ("https://moa.gov.cn.evil.example/1", "policy", "农业农村部印发本行动方案，明确未来三年建设重点及实施责任。", False),
    ("https://news.example/1", "policy", "农业农村部印发本行动方案，明确未来三年建设重点及实施责任。", False),
    ("https://www.moa.gov.cn/1", "policy", "模型编造的原始发布证明不在文章中", False),
    ("https://doi.org/10.1234/test", "unknown", "", False),  # DOI is not proof of original research
    ("https://www.nature.com/articles/test", "research", "农业农村部印发本行动方案，明确未来三年建设重点及实施责任。", False),
    ("https://www.deere.com/1", "announcement", "农业农村部印发本行动方案，明确未来三年建设重点及实施责任。", True),
    ("https://www.deere.com/1", "report", "农业农村部印发本行动方案，明确未来三年建设重点及实施责任。", False),
])
def test_primary_requires_both_identity_and_contiguous_content_evidence(url, kind, quote, primary):
    item = article(url=url)
    editorial.apply_model(item, answer(source_provenance={"type": kind, "quote": quote}))
    assert (editorial.public_provenance(item)["status"] == "primary") is primary
    assert "quote" not in editorial.public_provenance(item)


@pytest.mark.asyncio
async def test_compact_and_agent_outputs_keep_aids_private_evidence_stays_admin_only(editorial_db, editorial_client):
    async with editorial_db() as session:
        item = article()
        editorial.apply_model(item, answer())
        session.add(item)
        await session.commit()
        item_id = item.id
    detail = (await editorial_client.get(f"/api/v1/items/{item_id}")).json()
    compact = (await editorial_client.get("/api/v1/items", params={"compact": True})).json()["items"][0]
    assert detail["attention_point"] == compact["attention_point"] == answer()["attention_point"]
    assert compact["source_provenance"]["status"] == "primary"
    assert "editorial_meta" not in detail and "score_detail" not in compact and "content" not in compact
    assert "provenance_evidence" not in json.dumps(detail)
    from app.services.agent_service import item_out
    async with editorial_db() as session:
        result = item_out(await session.get(Item, item_id))
        assert result["attention_point"] == detail["attention_point"]
        assert result["source_provenance"] == detail["source_provenance"]
    assert (await editorial_client.get(f"/api/v1/admin/items/{item_id}/editorial")).status_code == 401


@pytest.mark.asyncio
async def test_manual_lock_clear_and_content_invalidation(editorial_db, editorial_client):
    async with editorial_db() as session:
        item = article()
        session.add(item)
        await session.commit()
        item_id = item.id
    headers = {"X-Admin-Token": issue_admin_token()}
    url = f"/api/v1/admin/items/{item_id}"
    point = "人工核对了任务责任及实施期限，可持续跟踪后续落实。"
    changed = await editorial_client.patch(url, headers=headers, json={"editorial": {"attention_point": point, "source_provenance": {"type": "policy"}}})
    assert changed.status_code == 200, changed.text
    async with editorial_db() as session:
        item = await session.get(Item, item_id)
        editorial.apply_model(item, answer())
        await session.commit()
        assert item.attention_point == point
        item.content = "补抓的全文给出了新的实施期限和适用范围。"
        await session.commit()
        assert item.attention_point is None
        assert editorial.public_provenance(item)["status"] == "unknown"
        assert item.editorial_meta["stale_attention"] == point
    cleared = await editorial_client.patch(url, headers=headers, json={"editorial": {"attention_point": None, "source_provenance": {"type": None}}})
    assert cleared.status_code == 200 and cleared.json()["attention_point"] is None
    assert cleared.json()["source_provenance"]["status"] == "unknown"
    internal = (await editorial_client.get(url + "/editorial", headers=headers)).json()
    assert internal["meta"]["attention_locked"] and internal["meta"]["provenance_locked"]


@pytest.mark.asyncio
async def test_model_result_does_not_replace_a_concurrent_edit(editorial_db, monkeypatch):
    async with editorial_db() as session:
        item = article()
        session.add(item)
        await session.commit()
        item_id = item.id
        async def response(snapshot):
            async with editorial_db() as other:
                current = await other.get(Item, item_id)
                editorial.apply_manual(current, {"attention_point": "人工最新核对的关注点，应保留而不被过期模型结果覆盖。"})
                await other.commit()
            return json.dumps(answer() | {"relevant": True, "impact": 30, "substance": 20, "depth": 15, "authority": 10, "freshness": 8})
        monkeypatch.setattr(scoring_service, "_call_deepseek", response)
        await scoring_service.score_item(session, item)
        await session.commit()
        assert item.attention_point.startswith("人工最新")


@pytest.mark.asyncio
async def test_backfill_preview_resume_and_failure_retry_preserve_selection(editorial_db, monkeypatch):
    async with editorial_db() as session:
        for index in range(3):
            session.add(article(url_hash=f"backfill-{index}", title_simhash=index))
        await session.commit()
    preview = await backfill(editorial_db, dry_run=True, limit=2)
    assert preview["total"] == 2 and preview["generated"] == 0
    async with editorial_db() as session:
        assert (await session.scalars(select(PipelineState).where(PipelineState.key.like("editorial_backfill:%")))).all() == []
    monkeypatch.setattr(settings, "deepseek_api_key", "local-test-only")
    calls = []
    async def response(item):
        calls.append(item.id)
        return None if len(calls) == 1 else json.dumps(answer())
    monkeypatch.setattr(scoring_service, "_call_deepseek", response)
    first = await backfill(editorial_db, limit=2)
    second = await backfill(editorial_db, limit=2)
    assert first["failed"] == 1 and first["generated"] == 1
    assert second["generated"] == 2 and calls == [1, 2, 3, 1]
    assert (await backfill(editorial_db, limit=2))["total"] == 0
    async with editorial_db() as session:
        items = (await session.scalars(select(Item))).all()
        assert all(item.score == 86 and item.is_selected and item.attention_point for item in items)


def test_malformed_optional_fields_do_not_leak_comment_or_create_primary():
    item = article()
    editorial.apply_model(item, {"attention_point": ["错误类型"], "comment": "不能拿评分简评代替关注点", "source_provenance": "bad"})
    assert item.attention_point is None and editorial.public_provenance(item)["status"] == "unknown"


@pytest.mark.asyncio
async def test_upgrade_adds_nullable_columns_without_changing_existing_scores(editorial_db):
    async with editorial_db() as session:
        session.add(article())
        await session.commit()
    engine = editorial_db.kw['bind']
    async with engine.begin() as connection:
        for name in ('attention_point', 'source_provenance', 'editorial_meta'):
            await connection.execute(text(f'ALTER TABLE items DROP COLUMN {name}'))
    await ensure_schema(engine)
    async with editorial_db() as session:
        item = await session.get(Item, 1)
        assert item.score == 86 and item.is_selected
        assert item.attention_point is item.source_provenance is item.editorial_meta is None
