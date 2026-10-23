"""Compact public reads preserve cards and avoid fetching full-text columns."""
import gzip
import os
from datetime import date

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import event, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import ensure_schema, get_session
from app.main import app
from app.models import Base, Daily, Item, ItemClassification, PaperMeta, SearchJob, Tag
from app.services import embedding_service
from app.services.taxonomy_service import sync_catalog


BACKENDS = ["sqlite"] + (["postgres"] if os.getenv("AGRIHOT_TEST_POSTGRES_URL") else [])


@pytest_asyncio.fixture(params=BACKENDS)
async def public_db(request, tmp_path):
    url = os.environ["AGRIHOT_TEST_POSTGRES_URL"] if request.param == "postgres" else f"sqlite+aiosqlite:///{tmp_path}/public.db"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await ensure_schema(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await sync_catalog(session)
        tag = Tag(name="水稻")
        for i in range(2):
            item = Item(title=f"水稻农业遥感监测进展 {i}", summary="农业遥感与作物监测研究取得新进展。",
                        url=f"https://example.com/{i}", url_hash=str(i), title_simhash=i,
                        content="水稻遥感监测的完整正文。" * 2000, score=85,
                        score_detail={"reason": "评分依据。" * 500}, is_selected=True,
                        category="论文", tags=[tag])
            item.classification = ItemClassification(status="classified", locked=True,
                                                      evidence={"reason": "人工确认。" * 500})
            item.paper = PaperMeta(openalex_id=f"W{i}", direction="农业遥感",
                                   card={"tldr": "卫星监测提高水稻估产精度。"})
            item.search_job = SearchJob(status="ready", fingerprint=embedding_service.fingerprint())
            session.add(item)
        await session.flush()
        session.add(Daily(date=date(2026, 10, 23), title="农业农村日报", highlights=["水稻新进展"],
                          content="日报内容", item_ids=[2, 999, 1, 2]))
        await session.commit()
        # Content writes enqueue indexing; represent completion after that transaction.
        await session.execute(update(SearchJob).values(status="ready", fingerprint=embedding_service.fingerprint()))
        await session.commit()

    async def dependency():
        async with factory() as session:
            yield session

    previous = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = dependency
    try:
        yield engine
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_session, None)
        else:
            app.dependency_overrides[get_session] = previous
        await engine.dispose()


@pytest_asyncio.fixture
async def public_client(public_db):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
@pytest.mark.parametrize("path,params", [
    ("/api/v1/items", {}),
    ("/api/v1/topics", {"name": "水稻"}),
    ("/api/v1/topics", {"name": "水稻 遥感"}),
    ("/api/v1/items/1/related", {}),
    ("/api/v1/dailies/latest", {}),
    ("/api/v1/dailies/2026-10-23", {}),
])
async def test_compact_reads_match_cards_without_loading_heavy_fields(public_client, public_db, path, params):
    full = await public_client.get(path, params=params)
    assert full.status_code == 200, full.text
    assert full.json()["items"]
    assert all(item["content"] and item["score_detail"] and item["classification"]["locked"]
               for item in full.json()["items"])

    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())

    event.listen(public_db.sync_engine, "before_cursor_execute", capture)
    try:
        compact = await public_client.get(path, params={**params, "compact": True})
    finally:
        event.remove(public_db.sync_engine, "before_cursor_execute", capture)
    assert compact.status_code == 200, compact.text
    heavy = {"content", "score_detail", "classification"}
    expected = [{key: value for key, value in item.items() if key not in heavy}
                for item in full.json()["items"]]
    assert compact.json()["items"] == expected
    assert len(compact.content) < len(full.content) / 10
    assert all("items.content" not in sql and "items.score_detail" not in sql
               and "item_classifications" not in sql for sql in statements)
    if "/dailies/" in path:
        assert len(statements) <= 6
    assert all(item["paper"]["card"]["tldr"] and item["embedding_ready"] for item in expected)


@pytest.mark.asyncio
async def test_compact_pagination_and_full_detail(public_client):
    pages = [await public_client.get("/api/v1/items", params={"compact": True, "mode": "selected",
                                                            "category": "论文", "page_size": 1, "page": page})
             for page in [1, 2]]
    assert [page.json()["total"] for page in pages] == [2, 2]
    assert [page.json()["items"][0]["id"] for page in pages] == [2, 1]
    detail = await public_client.get("/api/v1/items/1")
    assert detail.status_code == 200
    assert detail.json()["content"] == "水稻遥感监测的完整正文。" * 2000
    assert detail.json()["classification"]["locked"] is True


@pytest.mark.asyncio
async def test_daily_batch_read_preserves_order_and_skips_missing(public_client):
    for compact in [False, True]:
        response = await public_client.get("/api/v1/dailies/latest", params={"compact": compact})
        assert response.status_code == 200
        assert response.json()["content"] == "日报内容"
        assert [item["id"] for item in response.json()["items"]] == [2, 1, 2]


@pytest.mark.asyncio
async def test_api_compresses_large_responses_when_supported(public_client):
    plain = await public_client.get("/api/v1/items", headers={"Accept-Encoding": "identity"})
    assert "content-encoding" not in plain.headers
    async with public_client.stream("GET", "/api/v1/items", headers={"Accept-Encoding": "gzip"}) as response:
        assert response.headers["content-encoding"] == "gzip"
        assert "Accept-Encoding" in response.headers["vary"]
        raw = b"".join([chunk async for chunk in response.aiter_raw()])
    assert gzip.decompress(raw) == plain.content
    assert len(raw) < len(plain.content) / 10


@pytest.mark.asyncio
async def test_public_reads_are_edge_cacheable_without_freezing_counts(public_client):
    cached = {
        "/api/v1/items": "public, max-age=60, stale-while-revalidate=600",
        "/api/v1/items?compact=true&mode=selected": "public, max-age=60, stale-while-revalidate=600",
        "/api/v1/dailies": "public, max-age=60, stale-while-revalidate=600",
        "/api/v1/taxonomy": "public, max-age=300, stale-while-revalidate=3600",
        "/api/v1/tags": "public, max-age=300, stale-while-revalidate=3600",
        "/api/v1/stats": "public, max-age=60, stale-while-revalidate=600",
        "/api/v1/items/1/related": "public, max-age=120, stale-while-revalidate=600",
    }
    for path, expected in cached.items():
        response = await public_client.get(path)
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == expected
    detail = await public_client.get("/api/v1/items/1")
    assert "cache-control" not in detail.headers
    posted = await public_client.post("/api/v1/items/1/view")
    assert posted.status_code == 200
    assert "cache-control" not in posted.headers
