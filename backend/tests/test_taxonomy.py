"""Topic behavior, manual protection and reversible migrations on real DB engines."""
import hashlib
import os
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.agent_schemas import ItemListIn, SearchIn
from app.config import settings
from app.database import ensure_schema, get_session
from app.main import app
from app.models import (Base, ClassificationChange, Item, ItemClassification,
                        ItemTopic, PipelineState, Tag, Topic)
from app.security import issue_admin_token
from app.services import agent_service, scoring_service, search_index_service
from app.services.taxonomy_catalog import text_matches
from app.services.taxonomy_jobs import backfill, rollback
from app.services.taxonomy_service import classify, set_manual_topics, snapshot, sync_catalog

BACKENDS = ["sqlite"] + (["postgres"] if os.getenv("AGRIHOT_TEST_TAXONOMY_POSTGRES_URL") else [])


@pytest_asyncio.fixture(params=BACKENDS)
async def db(request, tmp_path, monkeypatch):
    url = os.environ["AGRIHOT_TEST_TAXONOMY_POSTGRES_URL"] if request.param == "postgres" else f"sqlite+aiosqlite:///{tmp_path}/taxonomy.db"
    engine = create_async_engine(url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await ensure_schema(engine)
    await ensure_schema(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await sync_catalog(session)
        await session.commit()
        await sync_catalog(session)
        await session.commit()
        assert (await session.execute(select(func.count()).select_from(Topic))).scalar() == 72
    monkeypatch.setattr(settings, "admin_password", "taxonomy-admin")
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    async def dependency():
        async with factory() as session:
            yield session
    previous = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = dependency
    yield factory
    if previous:
        app.dependency_overrides[get_session] = previous
    else:
        app.dependency_overrides.pop(get_session, None)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
        yield client


async def article(db, title="水稻病害识别的农业人工智能应用", tags=None, category="论文"):
    async with db() as session:
        item = Item(title=title, summary="利用深度学习与遥感监测改进农业作物管理。", category=category,
                    url="https://example.com/" + title, url_hash=hashlib.sha256(title.encode()).hexdigest(),
                    title_simhash=0, score=81, is_selected=True)
        tag_names = tags or ["水稻", "农业人工智能", "遥感监测"]
        found = {t.name: t for t in (await session.execute(select(Tag).where(Tag.name.in_(tag_names)))).scalars()}
        item.tags = []
        for name in tag_names:
            tag = found.get(name)
            if tag is None:
                tag = Tag(name=name)
                session.add(tag)
            item.tags.append(tag)
        session.add(item)
        await session.commit()
        return item.id


@pytest.mark.parametrize("title,tags,primary,secondary", [
    ("小麦渍害的无人机多光谱识别", ["智慧农业", "小麦渍害", "农业遥感"], "A2", "I3"),
    ("湖羊行为的农业人工智能目标检测", ["农业人工智能", "智慧养殖", "湖羊"], "C2", "I2"),
    ("水稻病害的深度学习识别", ["水稻", "农业人工智能"], "A1", "I2"),
])
def test_content_evidence_recovers_missing_object_tags(title, tags, primary, secondary):
    item = SimpleNamespace(title=title, summary="农业研究与应用", summary_zh=None, content=None, tags=[SimpleNamespace(name=t) for t in tags])
    result = classify(item)
    assert result["primary"] == primary
    assert secondary in result["secondary"]


def test_generic_technology_does_not_create_agricultural_relevance():
    item = SimpleNamespace(title="AI-driven public building retrofits", summary="Public building energy and cost decisions.",
                           summary_zh=None, content=None, tags=[SimpleNamespace(name="农业人工智能")])
    assert classify(item)["primary"] is None
    assert not text_matches("rice", "food price forecast")
    assert text_matches("rice", "Rice crop monitoring")
    assert not text_matches("葡萄", "硫代葡萄糖苷响应机制")


def test_equal_crop_evidence_stays_at_parent_level():
    item = SimpleNamespace(title="小麦与玉米的农业试验", summary="比较两种作物。", summary_zh=None,
                           content=None, tags=[])
    result = classify(item)
    assert result["primary"] == "A" and result["status"] == "partial"


@pytest.mark.asyncio
async def test_topics_filters_dedup_pagination_and_agent_parity(client, db):
    a = await article(db)
    b = await article(db, "水稻遥感农业生产观测", tags=["水稻", "遥感监测"], category="报道")
    directory = (await client.get("/api/v1/taxonomy")).json()
    assert len(directory["topics"]) == 10
    field = next(n for n in directory["topics"] if n["code"] == "A")
    assert field["count"] == 2
    assert (await client.get("/api/v1/taxonomy/rice")).json()["count"] == 2
    params = [("topic", "field-crops"), ("category", "论文"), ("technologies", "农业人工智能"), ("technologies", "遥感监测")]
    result = (await client.get("/api/v1/items", params=params)).json()
    assert [i["id"] for i in result["items"]] == [a]
    tech = (await client.get("/api/v1/items", params={"topic": "agricultural-ai"})).json()
    assert a in [i["id"] for i in tech["items"]]
    page1 = (await client.get("/api/v1/items", params={"topic": "rice", "page_size": 1})).json()
    page2 = (await client.get("/api/v1/items", params={"topic": "rice", "page_size": 1, "page": 2})).json()
    assert {page1["items"][0]["id"], page2["items"][0]["id"]} == {a, b}
    assert (await client.get("/api/v1/taxonomy/not-a-topic")).status_code == 404
    assert (await client.get("/api/v1/items", params={"topic": "not-a-topic"})).status_code == 422
    assert (await client.get("/api/v1/items", params={"topic": "rice", "category": "行业"})).json()["total"] == 0
    async with db() as session:
        agent = await agent_service.list_items(session, ItemListIn(topic="field-crops", category="论文", technologies=["农业人工智能", "遥感监测"]))
        assert [i["id"] for i in agent["items"]] == [a]


@pytest.mark.asyncio
async def test_manual_primary_swap_and_invalid_assignments(client, db):
    item_id = await article(db)
    headers = {"X-Admin-Token": issue_admin_token()}
    for primary, secondary in [("I2", ["A1"]), ("A1", ["I2"])]:
        response = await client.patch(f"/api/v1/admin/items/{item_id}", headers=headers,
            json={"taxonomy": {"primary_code": primary, "secondary_codes": secondary, "locked": True}})
        assert response.status_code == 200, response.text
        assert response.json()["primary_topic"]["code"] == primary
        assert response.json()["classification"]["locked"]
    for primary, secondary in [("A1", ["A1"]), ("A", ["A1"]), ("bad", [])]:
        response = await client.patch(f"/api/v1/admin/items/{item_id}", headers=headers,
            json={"taxonomy": {"primary_code": primary, "secondary_codes": secondary}})
        assert response.status_code == 422
    assert (await client.post(f"/api/v1/admin/items/{item_id}/classify", headers=headers)).status_code == 409
    # The real database, not just API validation, prevents two primary rows.
    async with db() as session:
        session.add(ItemTopic(item_id=item_id, topic_code="B1", is_primary=True))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_locked_topics_survive_stale_content_writer_and_scoring(db, monkeypatch):
    item_id = await article(db)
    async with db() as stale:
        old = await stale.get(Item, item_id)
        async with db() as session:
            item = (await session.execute(select(Item).where(Item.id == item_id).with_for_update())).scalar_one()
            await set_manual_topics(session, item, "I2", ["A1"], True)
            await session.commit()
        old.content = "后来抓取的水稻全文。"
        await stale.commit()
    async with db() as session:
        item = await session.get(Item, item_id)
        before = snapshot(item)
        async def response(_):
            return '{"relevant":true,"impact":20,"substance":20,"depth":15,"authority":10,"freshness":8,"tags":["畜牧业"]}'
        monkeypatch.setattr(scoring_service, "_call_deepseek", response)
        await scoring_service.score_item(session, item)
        await session.commit()
        assert snapshot(item) == before
        assert "畜牧业" not in [t.name for t in item.tags]


@pytest.mark.asyncio
async def test_content_writer_handles_classification_created_after_read(db):
    item_id = await article(db)
    async with db() as session:
        await session.execute(delete(ItemTopic))
        await session.execute(delete(ItemClassification))
        await session.commit()
    async with db() as stale:
        item = await stale.get(Item, item_id)
        assert item.classification is None
        await backfill(db, batch_id="concurrent")
        item.content = "新的农业水稻全文。"
        await stale.commit()
    async with db() as session:
        item = await session.get(Item, item_id)
        assert item.classification is not None
        assert sum(l.is_primary for l in item.topic_links) == 1


@pytest.mark.asyncio
async def test_aliases_expand_legacy_and_canonical_queries(client, db, monkeypatch):
    monkeypatch.setattr(settings, "embedding_api_key", "")
    a = await article(db, tags=["江苏农科院", "水稻", "农业人工智能"])
    b = await article(db, "江苏水稻遥感农业观测", tags=["江苏省农科院", "水稻", "遥感监测"])
    for name in ["江苏农科院", "江苏省农科院", "江苏省农业科学院"]:
        result = (await client.get("/api/v1/topics", params={"name": name})).json()
        assert {i["id"] for i in result["items"]} == {a, b}
        result = (await client.get("/api/v1/items", params={"q": name})).json()
        assert {i["id"] for i in result["items"]} == {a, b}
        async with db() as session:
            result = await agent_service.search(session, SearchIn(q=name))
            assert {i["id"] for i in result["items"]} == {a, b}
    assert (await client.get("/api/v1/items", params={"q": "%_nonexistent"})).json()["total"] == 0
    # Indexed PostgreSQL retrieval must resolve the same aliases as fresh content.
    for _ in range(2):
        assert await search_index_service.process_one(db)
    async with db() as session:
        for name in ["江苏农科院", "江苏省农科院", "江苏省农业科学院"]:
            result = await agent_service.search(session, SearchIn(q=name))
            assert {i["id"] for i in result["items"]} == {a, b}
    facets = (await client.get("/api/v1/taxonomy/facets", params={"topic": "rice"})).json()
    assert any(t["name"] == "农业人工智能" for t in facets["technologies"])


@pytest.mark.asyncio
async def test_related_content_can_share_topics_without_tags(client, db):
    a = await article(db, "奶牛牧场农业行为观测", tags=["奶牛传感"])
    b = await article(db, "湖羊养殖监测农业技术", tags=["湖羊图像"])
    result = (await client.get(f"/api/v1/items/{a}/related")).json()
    assert b in [item["id"] for item in result["items"]]
    assert a not in [item["id"] for item in result["items"]]


@pytest.mark.asyncio
async def test_preview_resume_idempotence_and_conditional_rollback(db):
    ids = [await article(db, f"水稻农业遥感监测实验{i}") for i in range(3)]
    async with db() as session:
        await session.execute(delete(ItemTopic))
        await session.execute(delete(ItemClassification))
        await session.commit()
    preview = await backfill(db, dry_run=True, batch_id="preview")
    assert preview["processed"] == 3
    async with db() as session:
        assert (await session.execute(select(func.count()).select_from(ItemClassification))).scalar() == 0
        assert await session.get(PipelineState, "taxonomy:preview") is None
    first = await backfill(db, batch_id="resume", limit=1)
    second = await backfill(db, batch_id="resume")
    assert first["processed"] == 1 and second["processed"] == 2
    assert (await backfill(db, batch_id="again"))["unchanged"] == 3
    async with db() as session:
        item = await session.get(Item, ids[0])
        await set_manual_topics(session, item, "I2", ["A1"], True)
        await session.commit()
    result = await rollback(db, "resume")
    assert result == {"batch_id": "resume", "restored": 2, "skipped": 1}
    async with db() as session:
        protected = await session.get(Item, ids[0])
        assert protected.classification.locked
        for item_id in ids[1:]:
            item = await session.get(Item, item_id)
            assert item.classification is None and item.topic_links == []
            assert item.score == 81 and item.is_selected
