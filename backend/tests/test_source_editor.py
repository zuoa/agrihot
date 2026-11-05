"""Operator-defined feeds and JSONPath/XPath collection, without external requests."""
import json
import os
import sys
from datetime import datetime, timezone

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:////tmp/agrihot_test.db"
os.environ["SOURCES_FETCH_ENABLED"] = "false"

from app.config import settings
from app.database import get_session
from app.main import app
from app.models import Base, Item, PipelineState
from app.schemas import IngestItemIn
from app.security import issue_admin_token
from app.source_schemas import SourceDefinitionIn
from app.services import content_service, source_service, source_registry
from app.services.fulltext import base as fulltext_base
from app.services.ingest_service import ingest_item
from app.services.source_adapters import article_url, get_document, parse_configured, payload_for

NOW = datetime(2026, 11, 4, 8, tzinfo=timezone.utc)
ABSTRACT = "The field study evaluated agricultural robots across multiple crop conditions, measuring accuracy, water savings and limitations."


def definition(**overrides):
    return {"name": "Test research JSON", "kind": "json", "url": "https://news.example/api/list",
            "enabled": True, "parser": {"items": "$.data.items", "title": "$.title", "url": "$.url",
                                       "published_at": "$.date", "summary": "$.summary"}, **overrides}


def row(**overrides):
    return {"title": "Autonomous robots improve rice irrigation efficiency", "url": "/article?id=42",
            "date": "2026-11-03T09:00:00Z", "summary": ABSTRACT, **overrides}


def source(**overrides):
    return source_registry.from_definition("editor-test", SourceDefinitionIn(**definition(**overrides)))


@pytest_asyncio.fixture
async def editor_db(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'editor.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async def session_override():
        async with sessions() as session:
            yield session
    async def enrich(_item_id):
        pass
    monkeypatch.setitem(app.dependency_overrides, get_session, session_override)
    monkeypatch.setattr(source_service, "SessionLocal", sessions)
    monkeypatch.setattr(settings, "admin_password", "source-editor-tests")
    monkeypatch.setattr(content_service, "enrich_and_score", enrich)
    try:
        yield sessions
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def editor_client(editor_db):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, {"X-Admin-Token": issue_admin_token()}


def test_json_mapping_keeps_query_ids_and_rejects_missing_dates():
    configured = source(default_timezone="Asia/Shanghai")
    data = {"data": {"items": [row(url="/article?id=1", date="2026-11-03 14:47"),
                                row(url="/article?id=2"), row(date=""), row(url="")]}}
    candidates, rejected, next_page, total = parse_configured(json.dumps(data).encode(), configured)
    assert total == 4 and rejected == 2 and next_page == ""
    assert candidates[0].published_at.isoformat() == "2026-11-03T06:47:00+00:00"
    assert candidates[0].url.endswith("?id=1") and candidates[1].url.endswith("?id=2")
    assert article_url(configured, "/article?id=1&utm_source=test").endswith("?id=1")


@pytest.mark.parametrize("items_path", ["$.data.items", "$.data.items[*]"])
def test_empty_json_arrays_and_wrong_list_paths_are_distinguished(items_path):
    configured = source(parser={**definition()["parser"], "items": items_path})
    assert parse_configured(b'{"data":{"items":[]}}', configured) == ([], 0, "", 0)
    with pytest.raises(ValueError, match="未匹配"):
        parse_configured(b'{"data":{"other":[]}}', configured)


@pytest.mark.parametrize("timestamp", [1793696400, 1793696400000])
def test_timestamp_mapping_and_link_template(timestamp):
    configured = source(parser={**definition()["parser"], "url": "$.id", "url_template": "/article?id={value}"})
    candidates, *_ = parse_configured(json.dumps({"data": {"items": [row(id="x&y", date=timestamp)]}}).encode(), configured)
    assert candidates[0].url == "https://news.example/article?id=x%26y"
    assert candidates[0].published_at.timestamp() == 1793696400


def test_html_xpath_is_relative_to_each_entry():
    configured = source(kind="html", default_timezone="Asia/Shanghai", parser={
        "items": "//ul/li", "title": "./a", "url": "./a/@href", "published_at": "./time/text()",
        "summary": "./p/text()", "date_format": "%Y年%m月%d日", "next_page": "//a[@rel='next']/@href",
    })
    data = f'<html><ul><li><a href="/news/1">Rice <b>robot</b> research</a><time>2026年11月03日</time><p>{ABSTRACT}</p></li></ul><a rel="next" href="?page=2">Next</a></html>'
    candidates, rejected, next_page, _ = parse_configured(data.encode(), configured)
    assert candidates[0].title == "Rice robot research" and candidates[0].url == "https://news.example/news/1"
    assert candidates[0].published_at.isoformat() == "2026-11-02T16:00:00+00:00"
    assert rejected == 0 and next_page == "?page=2"


@pytest.mark.asyncio
async def test_numbered_json_pagination_stops_at_short_page(monkeypatch):
    configured = source(parser={**definition()["parser"], "page_parameter": "page", "page_size": 2})
    requested = []
    async def document(_client, url, **kwargs):
        assert kwargs["validate_public"] is True
        requested.append(url)
        items = [row(url=f"/news/{i}") for i in range(2 if "page=1" in url else 1)]
        return httpx.Response(200, json={"data": {"items": items}}, request=httpx.Request("GET", url))
    monkeypatch.setattr(source_service, "get_document", document)
    window = {"since": "2026-11-01T00:00:00Z", "cursor": None}
    _, _, next_page = await source_service.fetch_page(None, configured, window)
    assert next_page.endswith("page=2")
    _, _, next_page = await source_service.fetch_page(None, configured, {**window, "cursor": next_page})
    assert next_page is None and len(requested) == 2


@pytest.mark.asyncio
async def test_public_source_redirect_cannot_contact_private_address(monkeypatch):
    original_validator = fulltext_base.validate_public_source
    async def validate(url):
        if "127.0.0.1" in url:
            await original_validator(url)
    monkeypatch.setattr(fulltext_base, "validate_public_source", validate)
    requested = []
    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(fulltext_base.FulltextFetchError, match="公开"):
            await get_document(client, "https://news.example/feed", validate_public=True)
    assert requested == ["https://news.example/feed"]


@pytest.mark.asyncio
async def test_crud_persists_and_deleted_packaged_source_stays_hidden(editor_client, editor_db):
    client, auth = editor_client
    payload = definition(kind="rss", url="https://news.example/feed", parser={})
    assert (await client.post("/api/v1/admin/sources", json=payload)).status_code == 401
    response = await client.post("/api/v1/admin/sources", headers=auth, json=payload)
    assert response.status_code == 201, response.text
    source_id = response.json()["id"]
    sources = {s["id"]: s for s in (await client.get("/api/v1/admin/sources", headers=auth)).json()["sources"]}
    assert sources[source_id]["can_edit"] and sources[source_id]["can_delete"]
    assert sources[source_id]["definition"]["url"] == payload["url"]
    changed = {**payload, "name": "Edited research feed", "interval_minutes": 60}
    assert (await client.put(f"/api/v1/admin/sources/{source_id}", headers=auth, json=changed)).status_code == 200
    async with editor_db() as session:
        saved = next(s for s in await source_service.configured_sources(session) if s.id == source_id)
        assert saved.name == changed["name"] and saved.interval_minutes == 60
        await ingest_item(session, IngestItemIn(title="Independent agricultural field study", url="https://example.org/retained",
                                             summary=ABSTRACT, source_name="AgFunder News"))
        await session.commit()
    assert (await client.delete(f"/api/v1/admin/sources/{source_id}", headers=auth)).status_code == 200
    assert (await client.delete("/api/v1/admin/sources/agfunder", headers=auth)).status_code == 200
    async with editor_db() as session:
        ids = {s.id for s in await source_service.configured_sources(session)}
        assert source_id not in ids and "agfunder" not in ids
        assert await session.scalar(select(func.count(Item.id))) == 1
    assert "agfunder" in {s.id for s in source_service.load_sources()}


@pytest.mark.asyncio
async def test_preview_returns_mapped_samples_without_writing(editor_client, editor_db, monkeypatch):
    client, auth = editor_client
    requested = []
    async def document(_client, url, **kwargs):
        requested.append((url, kwargs["validate_public"]))
        return httpx.Response(200, json={"data": {"items": [row()]}}, request=httpx.Request("GET", url))
    monkeypatch.setattr(source_service, "get_document", document)
    response = await client.post("/api/v1/admin/sources/preview", headers=auth, json=definition())
    assert response.status_code == 200, response.text
    sample = response.json()["samples"][0]
    assert sample["title"] == row()["title"] and sample["summary"] == ABSTRACT
    assert sample["url"].endswith("?id=42") and requested[0][1] is True
    async with editor_db() as session:
        assert await session.scalar(select(func.count(Item.id))) == 0
        assert await session.scalar(select(func.count(PipelineState.key))) == 0


@pytest.mark.asyncio
async def test_preview_keeps_successful_samples_when_an_article_body_fails(editor_client, monkeypatch):
    from app.services import source_adapters
    client, auth = editor_client
    async def listing(_client, url, **kwargs):
        return httpx.Response(200, json={"data": {"items": [row(), row(title="Crop sensors field study results", url="/blocked", summary="")]}},
                              request=httpx.Request("GET", url))
    async def blocked(_client, url, **kwargs):
        raise ValueError("article_body_missing")
    monkeypatch.setattr(source_service, "get_document", listing)
    monkeypatch.setattr(source_adapters, "get_document", blocked)
    response = await client.post("/api/v1/admin/sources/preview", headers=auth, json=definition())
    assert response.status_code == 200
    assert response.json()["failed"] == 1
    assert response.json()["samples"][0]["summary"] == ABSTRACT
    assert response.json()["samples"][1]["error"] == "article_body_missing"


@pytest.mark.asyncio
async def test_edit_stops_old_configuration_and_discards_old_pagination(editor_db, monkeypatch):
    async with editor_db() as session:
        result = await source_service.save_source(session, SourceDefinitionIn(**definition()))
        await session.commit()
        old = next(s for s in await source_service.configured_sources(session) if s.id == result["id"])
    await source_service.write_state(old.id, {"config_hash": source_registry.fingerprint(old),
        "window": {"since": "2026-10-01T00:00:00Z", "until": "2026-11-01T00:00:00Z", "cursor": "https://news.example/obsolete-page"}})
    async with editor_db() as session:
        await source_service.save_source(session, SourceDefinitionIn(**definition(url="https://news.example/new-api")), old.id)
        await session.commit()
        current = next(s for s in await source_service.configured_sources(session) if s.id == old.id)
    assert not await source_service.source_is_enabled(old)
    requested = []
    async def document(_client, url, **kwargs):
        requested.append(url)
        return httpx.Response(200, json={"data": {"items": [row()]}}, request=httpx.Request("GET", url))
    monkeypatch.setattr(source_service, "get_document", document)
    result = await source_service.collect_source(current, None, now=NOW)
    assert result["created"] == 1 and requested == ["https://news.example/new-api"]
    assert (await source_service.read_state(old.id))["watermark"] == NOW.isoformat()
    async with editor_db() as session:
        await source_service.delete_source(session, current.id)
        await session.commit()
    assert not await source_service.source_is_enabled(current)


@pytest.mark.asyncio
async def test_invalid_definitions_duplicates_and_watchlist_sources_are_rejected(editor_client):
    client, auth = editor_client
    payloads = [definition(url="http://127.0.0.1/internal"), definition(parser={**definition()["parser"], "items": "$.broken["}),
                definition(kind="html", parser={**definition()["parser"], "items": "//li["})]
    for payload in payloads:
        response = await client.post("/api/v1/admin/sources", headers=auth, json=payload)
        assert response.status_code == 422
    payload = definition(kind="rss", url="https://agfundernews.com/feed", parser={})
    assert (await client.post("/api/v1/admin/sources", headers=auth, json=payload)).status_code == 422
    assert (await client.put("/api/v1/admin/sources/crossref-0168-1699", headers=auth, json=payload)).status_code == 422
    assert (await client.delete("/api/v1/admin/sources/crossref-0168-1699", headers=auth)).status_code == 422
    assert (await client.delete("/api/v1/admin/sources/missing", headers=auth)).status_code == 404
