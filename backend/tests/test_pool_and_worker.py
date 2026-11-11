"""Connection checkout stays off the network, and a busy pool returns 503."""
import time
import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.main import app, pool_timeout_handler
from app.models import Base, Item
from app.services import content_service, ingest_service, job_runner, read_cache


class _Request:
    method = "GET"
    url = type("U", (), {"path": "/api/v1/items"})()


@pytest.mark.asyncio
async def test_repeated_catalog_reads_share_one_database_session(monkeypatch):
    opened = []

    class Session:
        async def __aenter__(self):
            opened.append(time.monotonic())
            return self

        async def __aexit__(self, *args):
            return None

    async def load(session):
        assert isinstance(session, Session)
        return {"topics": 1}

    monkeypatch.setattr(read_cache, "SessionLocal", Session)
    monkeypatch.setattr(read_cache, "_session_factory", lambda: Session)
    read_cache.reset()
    assert await read_cache.get(("taxonomy",), load) == {"topics": 1}
    assert await read_cache.get(("taxonomy",), load) == {"topics": 1}
    assert len(opened) == 1


@pytest.mark.asyncio
async def test_pool_timeout_is_503_without_traceback():
    response = await pool_timeout_handler(_Request(), PoolTimeoutError("pool"))
    assert response.status_code == 503
    assert "繁忙" in response.body.decode()


@pytest.mark.asyncio
async def test_health_reports_backend_duration():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.headers["server-timing"].startswith("api;dur=")


@pytest.mark.asyncio
async def test_startup_doi_backfill_reads_only_needed_columns():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(Item(title="DOI paper", url="https://doi.org/10.1234/example",
                         url_hash="doi-backfill", title_simhash=1, summary="abstract",
                         content="large body " * 1000))
        await session.commit()
    queries = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement.lower())

    event.listen(engine.sync_engine, "before_cursor_execute", capture)
    try:
        async with factory() as session:
            assert await ingest_service.maybe_backfill_doi(session) == 1
            await session.commit()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture)
    async with factory() as session:
        assert (await session.scalar(select(Item.doi))) == "10.1234/example"
        assert await ingest_service.maybe_backfill_doi(session) == 0
    assert all("items.content" not in sql and "paper_pdfs" not in sql for sql in queries)
    await engine.dispose()


@pytest.mark.asyncio
async def test_fetch_content_drops_the_connection_before_http(monkeypatch):
    checked_out = []

    class Session:
        async def __aenter__(self):
            checked_out.append("open")
            return self

        async def __aexit__(self, *args):
            checked_out.append("close")

        async def get(self, model, key):
            return type("Row", (), {"value": "0"})()

        async def commit(self):
            checked_out.append("commit")

    async def missing(session, **kwargs):
        return []

    monkeypatch.setattr(job_runner, "SessionLocal", Session)
    monkeypatch.setattr(job_runner, "missing_content_ids", missing)
    from app.services import runtime_settings
    monkeypatch.setattr(runtime_settings, "get", lambda key: True)

    stats = await job_runner._fetch_content({})
    assert stats["requested"] == 0
    assert "http" not in checked_out
    assert checked_out[0] == "open" and checked_out[-1] == "close"


@pytest.mark.asyncio
@pytest.mark.parametrize("job_name", sorted(job_runner.WORKER_JOBS))
async def test_api_process_queues_fetch_instead_of_running_it(monkeypatch, job_name):
    written = {}

    async def write(name, payload):
        written.update(payload)

    async def read(name):
        return {"status": "idle"}

    monkeypatch.setattr(job_runner, "RUNS_JOBS", False)
    monkeypatch.setattr(job_runner, "_write_status", write)
    monkeypatch.setattr(job_runner, "_read_status", read)
    assert await job_runner.spawn(job_name, {"item_ids": [3]}) is True
    assert written["status"] == "queued"
    assert written["params"]["item_ids"] == [3]
    await asyncio.sleep(0)
    assert job_name not in job_runner._running


@pytest.mark.asyncio
async def test_enrich_fetches_after_the_read_session_closes(monkeypatch):
    order = []

    class Item:
        id = 7
        url = "https://example.org/a"
        source_url = None
        paper = None
        category = "报道"
        content = None
        is_selected = True

    class Session:
        async def __aenter__(self):
            order.append("open")
            return self

        async def __aexit__(self, *args):
            order.append("close")

        async def get(self, model, item_id):
            return Item()

        async def commit(self):
            order.append("commit")

    async def fetch(url, **kwargs):
        order.append("http")
        assert order[-2] == "close"
        return "正文" * 40

    monkeypatch.setattr(content_service, "SessionLocal", Session)
    monkeypatch.setattr(content_service, "fetch_fulltext", fetch)
    await content_service.enrich_and_score(7)
    assert order.index("http") < order.index("commit")
