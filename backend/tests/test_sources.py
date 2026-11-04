"""Fixed-source discovery, replay, failure checkpoints and cross-provider DOI merge."""
import gzip
import os
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:////tmp/agrihot_test.db"
os.environ["CONTENT_FETCH_ENABLED"] = "false"
os.environ["LITERATURE_FETCH_ENABLED"] = "false"
os.environ["SOURCES_FETCH_ENABLED"] = "false"

from app.models import Base, Item, PaperMeta, PipelineState
from app.services import content_service, runtime_settings, source_scheduler, source_service
from app.services.ingest_service import ingest_item
from app.services.openalex_service import map_work
from app.services.paper_card_service import has_usable_abstract
from app.services.source_adapters import (
    Source, article_url, get_document, map_crossref, parse_feed, parse_moa, payload_for,
)

NOW = datetime(2026, 11, 4, 8, tzinfo=timezone.utc)
FEED = Source("test-feed", "Test Agtech News", "rss", "https://news.example/feed",
              hosts=["news.example"], article_pattern=r"/news/[a-z0-9-]+")
MOA = Source("test-moa", "农业农村部", "moa", "https://scs.moa.gov.cn/xxhtj/",
             hosts=["scs.moa.gov.cn"], article_pattern=r"/(?:[^/]+/)*\d{6}/t\d{8}_\d+\.htm")
CROSSREF = Source("test-crossref", "Crossref · Precision Agriculture", "crossref",
                  "https://api.crossref.org/journals/1385-2256/works")
TITLES = ["Autonomous field robots reduce herbicide drift in maize",
          "Satellite imagery estimates seasonal rice yield across continents",
          "A new low cost sensor detects greenhouse tomato disease"]


def feed(count=1):
    return ("<rss version='2.0'><channel>" + "".join(
        f"<item><title>{escape(TITLES[i])}</title><link>https://news.example/news/story-{i}</link>"
        f"<pubDate>Tue, 03 Nov 2026 0{i}:00:00 GMT</pubDate>"
        "<description>Researchers tested the agricultural technology in replicated field trials, reporting crop performance and limitations.</description></item>"
        for i in range(count)) + "</channel></rss>").encode()


def moa_list(*, pages=1, link="./202611/t20261103_123.htm", date="2026-11-03"):
    return (f"<html><ul><li><a href='{link}' title='智慧农业发展指导意见发布'>"
            f"<span class='sj_gztzle'>智慧农业发展指导意见发布</span><span class='sj_gztzri'>{date}</span>"
            f"</a></li></ul><script>var countPage = {pages};</script></html>").encode()


def crossref_work(**overrides):
    return {"DOI": "10.1007/s11119-026-01234-5", "type": "journal-article",
            "title": [TITLES[0]], "container-title": ["Precision Agriculture"],
            "published-online": {"date-parts": [[2026, 11, 3]]},
            "author": [{"given": "Jane", "family": "Doe", "ORCID": "https://orcid.org/0000-0001-2345-6789"}],
            **overrides}


@pytest_asyncio.fixture
async def db(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'sources.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(source_service, "SessionLocal", sessions)
    enriched = []

    async def enrich(item_id):
        enriched.append(item_id)

    monkeypatch.setattr(content_service, "enrich_and_score", enrich)
    try:
        yield sessions, enriched
    finally:
        await engine.dispose()


def test_registry_keeps_pilots_disabled_and_uses_watchlist_journals():
    sources = source_service.load_sources()
    assert len([s for s in sources if s.enabled and s.kind == "rss"]) == 14
    assert len([s for s in sources if s.enabled and s.kind == "moa"]) == 2
    assert len([s for s in sources if s.enabled and s.kind == "crossref"]) == 6
    assert all(not s.enabled for s in sources if s.kind == "candidate")
    assert "crossref-0308-521x" in {s.id for s in sources}


def test_feed_rejects_search_links_missing_dates_and_title_only():
    good = feed().decode()
    bad = good.replace("https://news.example/news/story-0", "https://news.google.com/rss/articles/123")
    assert parse_feed(bad.encode(), FEED) == ([], 1)
    assert parse_feed(good.replace("Tue, 03 Nov 2026 00:00:00 GMT", "invalid").encode(), FEED) == ([], 1)
    assert parse_feed(good.replace("Researchers tested the agricultural technology in replicated field trials, reporting crop performance and limitations.", "Headline only").encode(), FEED) == ([], 1)
    candidates, rejected = parse_feed(feed(), FEED)
    assert rejected == 0 and candidates[0].published_at == NOW.replace(day=3, hour=0)


def test_atom_feed_and_external_entity_are_not_treated_as_article_content():
    atom = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>New agricultural robot field trial</title>
    <link href="https://news.example/news/robot" rel="alternate"/><published>2026-11-03T01:00:00Z</published>
    <summary>Replicated field trials demonstrate performance across multiple crops and identify limitations.</summary></entry></feed>'''
    candidates, rejected = parse_feed(atom, FEED)
    assert len(candidates) == 1 and rejected == 0
    for content in [b"<html>Access denied</html>", b"<rss><channel></channel></rss>"]:
        with pytest.raises(ValueError):
            parse_feed(content, FEED)


def test_chinese_feed_dates_use_source_timezone_and_content_can_fill_empty_description():
    source = Source(**{**FEED.__dict__, "default_timezone": "Asia/Shanghai"})
    content = feed().replace(b"Tue, 03 Nov 2026 00:00:00 GMT", b"2026-11-03 14:47")
    content = content.replace(b"<description>", b"<description/><content>").replace(b"</description>", b"</content>")
    candidates, rejected = parse_feed(content, source)
    assert rejected == 0
    assert candidates[0].published_at.isoformat() == "2026-11-03T06:47:00+00:00"
    assert "replicated field trials" in candidates[0].summary


def test_irri_feed_only_accepts_formal_news_paths():
    source = next(s for s in source_service.load_sources() if s.id == "irri-news")
    assert source.enabled and source.kind == "rss"
    for path in ("/home-test", "/about-us/our-people/researcher", "/projects/palai"):
        assert article_url(source, path) is None
    assert article_url(source, "/news-and-events/news/rice-field-research")


def journal_feed():
    return b'''<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
      xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/"
      xmlns:prism="http://prismstandard.org/namespaces/basic/2.0/"
      xmlns:content="http://purl.org/rss/1.0/modules/content/">
      <item><title>Optimizing rice irrigation under climate stress</title>
      <link>https://www.nature.com/articles/s43016-026-01234-5</link>
      <dc:date>2026-11-03</dc:date><dc:creator>Jane Doe</dc:creator><dc:creator>John Doe</dc:creator>
      <prism:doi>10.1038/s43016-026-01234-5</prism:doi><prism:publicationName>Nature Food</prism:publicationName>
      <content:encoded><![CDATA[<p>Nature Food, Published online: 03 November 2026;
      <a href="https://www.nature.com/articles/s43016-026-01234-5">doi:10.1038/s43016-026-01234-5</a></p>
      Replicated rice field trials measure water savings, yield response and limitations of automated irrigation across soil types.
      ]]></content:encoded></item></rdf:RDF>'''


@pytest.mark.asyncio
async def test_journal_rdf_preserves_doi_authors_abstract_and_merges_crossref(db):
    source = next(s for s in source_service.load_sources() if s.id == "nature-food-rss")
    candidates, rejected = parse_feed(journal_feed(), source)
    assert rejected == 0 and len(candidates) == 1
    candidate = candidates[0]
    assert candidate.doi == "10.1038/s43016-026-01234-5"
    assert candidate.paper.ingested_from == "rss"
    assert candidate.paper.authors == [{"name": "Jane Doe"}, {"name": "John Doe"}]
    assert candidate.summary.startswith("Replicated rice field trials")
    assert "Published online" not in candidate.summary
    async with httpx.AsyncClient() as client:
        payload = await payload_for(candidate, source, client)
        assert payload.category == "论文" and payload.source_name == "Nature Food"
        work = crossref_work(DOI=candidate.doi, title=[candidate.title], **{"container-title": ["Nature Food"]})
        other = map_crossref(work, CROSSREF)
        other_payload = await payload_for(other, CROSSREF, client)
    async with db[0]() as session:
        first = await ingest_item(session, payload, paper_draft=candidate.paper)
        duplicate = await ingest_item(session, other_payload, paper_draft=other.paper)
        await session.commit()
        assert duplicate.status == "duplicate" and duplicate.dup_reason == "exact_doi"
        item = await session.get(Item, first.item_id)
        assert item.paper.ingested_from == "rss" and item.summary == candidate.summary
        assert await session.scalar(select(func.count(Item.id))) == 1


def test_journal_feed_without_explicit_doi_is_rejected():
    source = next(s for s in source_service.load_sources() if s.id == "nature-food-rss")
    content = journal_feed().replace(b"<prism:doi>10.1038/s43016-026-01234-5</prism:doi>", b"")
    assert parse_feed(content, source) == ([], 1)


def test_moa_uses_displayed_date_and_rejects_non_article_urls():
    candidates, rejected = parse_moa(moa_list(date="2026-10-28"), MOA)
    assert rejected == 0
    assert candidates[0].published_at.isoformat() == "2026-10-27T16:00:00+00:00"
    for value in ["https://scs.moa.gov.cn.evil.test/202611/t20261103_123.htm", "/home-test", "/xxhtj/"]:
        assert article_url(MOA, value) is None
    assert parse_moa(moa_list(link="/home-test"), MOA) == ([], 1)


def test_journal_front_matter_is_filtered_but_future_issue_dates_are_preserved():
    candidate = map_crossref(crossref_work(title=["Editorial Board"]), CROSSREF)
    assert not source_service.eligible(candidate, NOW)
    candidate = map_crossref(crossref_work(**{"published-online": {"date-parts": [[2027, 1]]}}), CROSSREF)
    assert candidate.published_at.year == 2027
    assert source_service.eligible(candidate, NOW)


@pytest.mark.asyncio
async def test_rss_technology_prescreen_skips_general_trade_news(db):
    scoped = Source(**{**FEED.__dict__, "keywords": ["agricultural robot"]})
    content = feed().replace(TITLES[0].encode(), b"Wholesale vegetable trade volumes increase in southern Europe")
    content = content.replace(b"Researchers tested the agricultural technology in replicated field trials, reporting crop performance and limitations.",
                              b"Wholesalers report higher imports and trading volumes at several distribution centers this week.")
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=content))) as client:
        result = await source_service.collect_source(scoped, client, now=NOW)
    assert result["created"] == 0 and result["screened_out"] == 1


@pytest.mark.asyncio
async def test_bad_article_does_not_block_other_articles_on_same_page(db):
    body = "田间精准灌溉试验已完成，研究人员公开了农业机器人技术参数和节水率。" * 20
    listing = moa_list().replace(b"</ul>",
        "<li><a href='./202611/t20261103_456.htm' title='温室番茄智能灌溉系统完成田间验证'><span class='sj_gztzri'>2026-11-03</span></a></li></ul>".encode())
    def handler(request):
        if request.url.path.endswith("/"):
            return httpx.Response(200, content=listing)
        if request.url.path.endswith("123.htm"):
            return httpx.Response(403)
        return httpx.Response(200, content=f"<html><article><p>{body}</p></article></html>".encode())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await source_service.collect_source(MOA, client, now=NOW)
    assert result["created"] == 1 and result["errors"] == 1
    assert "watermark" not in await source_service.read_state(MOA.id)


@pytest.mark.asyncio
async def test_compressed_feed_is_decoded_once():
    def handler(request):
        return httpx.Response(200, headers={"content-encoding": "gzip"}, content=gzip.compress(feed()))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await get_document(client, FEED.url)
    assert len(parse_feed(response.content, FEED)[0]) == 1


@pytest.mark.asyncio
async def test_feed_replay_is_idempotent_and_only_new_items_are_enriched(db):
    sessions, enriched = db
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=feed(2)))) as client:
        first = await source_service.collect_source(FEED, client, now=NOW)
        second = await source_service.collect_source(FEED, client, now=NOW + timedelta(hours=1))
    assert first["created"] == 2 and second["created"] == 0 and second["duplicate"] == 2
    assert len(enriched) == 2
    async with sessions() as session:
        assert await session.scalar(select(func.count(Item.id))) == 2
    state = await source_service.read_state(FEED.id)
    assert state["status"] == "ok" and "window" not in state
    assert state["totals"]["runs"] == 2 and state["totals"]["created"] == 2


@pytest.mark.asyncio
async def test_new_item_cap_drains_on_next_run_instead_of_skipping(db):
    runtime_settings._overrides["sources_max_new_per_source"] = 1
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=feed(2)))) as client:
        first = await source_service.collect_source(FEED, client, now=NOW)
        state = await source_service.read_state(FEED.id)
        assert first["truncated"] and "watermark" not in state
        second = await source_service.collect_source(FEED, client, now=NOW + timedelta(minutes=1))
    assert second["created"] == 1 and second["duplicate"] == 1 and not second["truncated"]
    assert (await source_service.read_state(FEED.id))["watermark"] == NOW.isoformat()


@pytest.mark.asyncio
async def test_http_failure_keeps_checkpoint_and_retries_same_window(db):
    watermark = (NOW - timedelta(days=1)).isoformat()
    await source_service.write_state(FEED.id, {"watermark": watermark})
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(503))) as client:
        failed = await source_service.collect_source(FEED, client, now=NOW)
    state = await source_service.read_state(FEED.id)
    assert failed["errors"] == 1 and state["watermark"] == watermark
    assert state["stats"]["error"] == "HTTP 503"
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=feed()))) as client:
        recovered = await source_service.collect_source(FEED, client, now=NOW + timedelta(hours=1))
    assert recovered["created"] == 1
    assert (await source_service.read_state(FEED.id))["watermark"] == NOW.isoformat()


@pytest.mark.asyncio
async def test_moa_body_failure_does_not_publish_title_only_or_advance(db):
    def handler(request):
        return httpx.Response(200, content=moa_list() if request.url.path.endswith("/") else b"<html>Access denied</html>")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await source_service.collect_source(MOA, client, now=NOW)
    assert result["created"] == 0 and result["errors"] == 1
    assert "watermark" not in await source_service.read_state(MOA.id)


@pytest.mark.asyncio
async def test_moa_pagination_dry_run_is_read_only_and_validates_body(db):
    sessions, enriched = db
    requests = []
    body = "智慧农业建设推进精准灌溉与农业机器人应用，组织开展田间验证并公开技术指标。" * 15

    def handler(request):
        requests.append(request.url.path)
        if request.url.path.endswith(".htm") and "/202611/" in request.url.path:
            return httpx.Response(200, content=f"<html><article><h1>智慧农业技术</h1><p>{body}</p></article></html>".encode())
        return httpx.Response(200, content=moa_list(pages=2, date="2026-10-01" if "index_1" in request.url.path else "2026-11-03"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await source_service.collect_source(MOA, client, now=NOW, dry_run=True)
    assert len(result["previews"]) == 1 and result["previews"][0]["content_chars"] > 200
    assert "/xxhtj/index_1.htm" in requests
    async with sessions() as session:
        assert await session.scalar(select(func.count(Item.id))) == 0
        assert await session.scalar(select(func.count(PipelineState.key))) == 0
    assert enriched == []


@pytest.mark.asyncio
async def test_crossref_page_failure_resumes_without_advancing_watermark(db, monkeypatch):
    monkeypatch.setattr(source_service, "CROSSREF_ROWS", 1)
    requests = []
    fail = True

    def handler(request):
        nonlocal fail
        cursor = request.url.params["cursor"]
        requests.append(cursor)
        assert "from-created-date:" in request.url.params["filter"]
        if cursor == "*":
            return httpx.Response(200, json={"message": {"items": [crossref_work()], "next-cursor": "page-two"}})
        if fail:
            return httpx.Response(503)
        return httpx.Response(200, json={"message": {"items": []}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        first = await source_service.collect_source(CROSSREF, client, now=NOW)
        state = await source_service.read_state(CROSSREF.id)
        assert first["created"] == 1 and first["errors"] == 1
        assert state["window"]["cursor"] == "page-two" and "watermark" not in state
        fail = False
        await source_service.collect_source(CROSSREF, client, now=NOW + timedelta(minutes=5))
    assert requests == ["*", "page-two", "page-two"]
    assert (await source_service.read_state(CROSSREF.id))["watermark"] == NOW.isoformat()


@pytest.mark.asyncio
async def test_expired_crossref_cursor_replays_same_window(db):
    window = {"since": (NOW - timedelta(days=3)).isoformat(), "until": NOW.isoformat(), "cursor": "expired"}
    await source_service.write_state(CROSSREF.id, {"window": window})
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(400))) as client:
        result = await source_service.collect_source(CROSSREF, client, now=NOW)
    state = await source_service.read_state(CROSSREF.id)
    assert result["errors"] == 1 and state["window"]["cursor"] is None
    assert state["window"]["since"] == window["since"] and "watermark" not in state


@pytest.mark.asyncio
async def test_crossref_then_openalex_merges_doi_and_fills_real_abstract(db):
    sessions, _ = db
    candidate = map_crossref(crossref_work(), CROSSREF)
    async with httpx.AsyncClient() as client:
        payload = await payload_for(candidate, CROSSREF, client)
    thin_payload = payload
    async with sessions() as session:
        first = await ingest_item(session, payload, paper_draft=candidate.paper)
        await session.commit()
        item = await session.get(Item, first.item_id)
        assert not has_usable_abstract(item)
    abstract = "Replicated field trials show agricultural robots reduce pesticide drift and quantify the limitations of autonomous navigation across crop conditions."
    work = {"id": "https://openalex.org/W123456", "doi": candidate.doi, "display_name": TITLES[0],
            "publication_date": "2026-11-03", "abstract_inverted_index": {abstract: [0]},
            "primary_location": {"source": {"display_name": "Precision Agriculture"}}}
    payload, draft = map_work(work)
    async with sessions() as session:
        second = await ingest_item(session, payload, paper_draft=draft)
        await session.commit()
        item = await session.get(Item, first.item_id)
        assert second.status == "duplicate" and second.dup_reason == "exact_doi"
        assert item.summary == abstract and has_usable_abstract(item)
        assert item.paper.openalex_id == "W123456" and item.paper.authors[0]["name"] == "Jane Doe"
        assert await session.scalar(select(func.count(Item.id))) == 1
        assert await session.scalar(select(func.count(PaperMeta.item_id))) == 1
        # A repeat of thin Crossref metadata must not replace the real abstract.
        await ingest_item(session, thin_payload, paper_draft=candidate.paper)
        assert item.summary == abstract


@pytest.mark.asyncio
async def test_scheduler_respects_disable_and_source_intervals(db, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "sources_fetch_enabled", True)
    called = []
    async def spawn(*args):
        called.append(args)
    async def sources():
        return [{"enabled": True, "interval_minutes": 1440,
                 "state": {"last_checked_at": datetime.now(timezone.utc).isoformat()}}]

    monkeypatch.setattr(source_scheduler, "SessionLocal", db[0])
    monkeypatch.setattr(source_service, "list_sources", sources)
    monkeypatch.setattr(source_scheduler.job_runner, "spawn", spawn)
    await source_scheduler.tick()
    assert not called
    async def due():
        return [{"enabled": True, "interval_minutes": 120, "state": {}}]
    monkeypatch.setattr(source_service, "list_sources", due)
    await source_scheduler.tick()
    assert called == [("sources_fetch", {"force": False})]
    async with db[0]() as session:
        await runtime_settings.patch(session, {"sources_fetch_enabled": False})
        await session.commit()
    await source_scheduler.tick()
    assert len(called) == 1


@pytest.mark.asyncio
async def test_disabled_sources_are_skipped_by_manual_collection(db, monkeypatch):
    monkeypatch.setattr(source_service, "load_sources", lambda: [FEED])
    async with db[0]() as session:
        await source_service.set_source_enabled(session, FEED.id, False)
        await session.commit()
    async def unexpected(*args, **kwargs):
        pytest.fail("disabled source was collected")
    monkeypatch.setattr(source_service, "collect_source", unexpected)
    result = await source_service.run_once(force=True, now=NOW)
    assert result["sources"] == [] and result["created"] == 0
    with pytest.raises(ValueError, match="disabled source"):
        await source_service.run_once(source_id=FEED.id)


@pytest.mark.asyncio
async def test_enabling_a_source_overrides_default_and_schedules_without_waiting_for_interval(db, monkeypatch):
    from app.config import settings
    source = replace(FEED, enabled=False)
    monkeypatch.setattr(source_service, "load_sources", lambda: [source])
    monkeypatch.setattr(source_service, "utcnow", lambda: NOW + timedelta(minutes=1))
    monkeypatch.setattr(source_scheduler, "SessionLocal", db[0])
    monkeypatch.setattr(source_service.job_runner, "SessionLocal", db[0])
    monkeypatch.setattr(settings, "sources_fetch_enabled", True)
    await source_service.write_state(source.id, {"last_checked_at": NOW.isoformat(), "watermark": NOW.isoformat()})
    async with db[0]() as session:
        await source_service.set_source_enabled(session, source.id, True)
        await session.commit()
    scheduled = []
    async def spawn(*args):
        scheduled.append(args)
    monkeypatch.setattr(source_scheduler.job_runner, "spawn", spawn)
    await source_scheduler.tick()
    assert scheduled == [("sources_fetch", {"force": False})]
    async_client = httpx.AsyncClient
    requests = []
    def handler(request):
        requests.append(str(request.url))
        return httpx.Response(200, content=feed())
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: async_client(
        transport=httpx.MockTransport(handler), **kwargs,
    ))
    result = await source_service.run_once(force=False, now=NOW + timedelta(minutes=2))
    assert result["created"] == 1 and requests == [FEED.url]


@pytest.mark.asyncio
async def test_disabling_during_collection_stops_next_page_and_preserves_resume_cursor(db, monkeypatch):
    monkeypatch.setattr(source_service, "load_sources", lambda: [CROSSREF])
    monkeypatch.setattr(source_service, "CROSSREF_ROWS", 1)
    requests = []
    async def handler(request):
        cursor = request.url.params["cursor"]
        requests.append(cursor)
        if cursor == "*":
            async with db[0]() as session:
                await source_service.set_source_enabled(session, CROSSREF.id, False)
                await session.commit()
            return httpx.Response(200, json={"message": {"items": [crossref_work()], "next-cursor": "next-page"}})
        return httpx.Response(200, json={"message": {"items": []}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await source_service.collect_source(CROSSREF, client, now=NOW)
        assert result["created"] == 1 and result["paused"] is True
        state = await source_service.read_state(CROSSREF.id)
        assert state["status"] == "paused" and state["window"]["cursor"] == "next-page"
        assert "watermark" not in state and requests == ["*"]
        assert await source_service.source_is_enabled(CROSSREF) is False
        async with db[0]() as session:
            await source_service.set_source_enabled(session, CROSSREF.id, True)
            await session.commit()
        await source_service.collect_source(CROSSREF, client, now=NOW + timedelta(hours=1))
    assert requests == ["*", "next-page"]
    assert (await source_service.read_state(CROSSREF.id))["watermark"] == NOW.isoformat()
