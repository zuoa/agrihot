"""Connection checkout stays off the network, and a busy pool returns 503."""
import asyncio

import pytest
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app.main import pool_timeout_handler
from app.services import content_service, job_runner


class _Request:
    method = "GET"
    url = type("U", (), {"path": "/api/v1/items"})()


@pytest.mark.asyncio
async def test_pool_timeout_is_503_without_traceback():
    response = await pool_timeout_handler(_Request(), PoolTimeoutError("pool"))
    assert response.status_code == 503
    assert "繁忙" in response.body.decode()


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
async def test_api_process_queues_fetch_instead_of_running_it(monkeypatch):
    written = {}

    async def write(name, payload):
        written.update(payload)

    async def read(name):
        return {"status": "idle"}

    monkeypatch.setattr(job_runner, "RUNS_JOBS", False)
    monkeypatch.setattr(job_runner, "_write_status", write)
    monkeypatch.setattr(job_runner, "_read_status", read)
    assert await job_runner.spawn("fetch_content", {"item_ids": [3]}) is True
    assert written["status"] == "queued"
    assert written["params"]["item_ids"] == [3]
    await asyncio.sleep(0)
    assert "fetch_content" not in job_runner._running


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
