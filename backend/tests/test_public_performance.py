"""Compact public reads preserve cards and avoid fetching full-text columns."""
import gzip
import os
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import event, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import ensure_schema, get_session
from app.main import app
from app.models import Base, Daily, Item, ItemClassification, PaperMeta, PaperPdf, PipelineState, SearchJob, Tag
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
    heavy = {"content", "score_detail", "classification", "tag_meta"}
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
async def test_paper_pdf_job_preserves_existing_text_and_serves_saved_file(public_client, public_db, tmp_path, monkeypatch):
    import io
    from pypdf import PdfWriter
    from app.config import settings
    from app.services import paper_pdf, paper_pdf_job

    monkeypatch.setattr(settings, "paper_pdf_dir", str(tmp_path))
    monkeypatch.setattr(paper_pdf_job, "SessionLocal", async_sessionmaker(public_db, expire_on_commit=False))

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    pdf_buffer = io.BytesIO()
    writer.write(pdf_buffer)
    pdf_bytes = pdf_buffer.getvalue()

    async def downloaded(*args, **kwargs):
        return paper_pdf.PdfDownload(pdf_bytes, "https://publisher.example/article.pdf", "example")

    async def no_text(data):
        return None

    monkeypatch.setattr(paper_pdf, "download_pdf", downloaded)
    monkeypatch.setattr(paper_pdf, "extract_pdf_text", no_text)
    assert await paper_pdf_job.fetch_one(1) == "downloaded"
    detail = await public_client.get("/api/v1/items/1")
    assert detail.json()["pdf"]["status"] == "ready"
    assert detail.json()["content"].startswith("水稻遥感")
    response = await public_client.get("/api/v1/items/1/pdf")
    assert response.status_code == 200 and response.content.startswith(b"%PDF-")


@pytest.mark.asyncio
async def test_paper_pdf_job_saves_text_layer_containing_nul(public_client, public_db, tmp_path, monkeypatch):
    import io
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    from app.config import settings
    from app.services import paper_pdf, paper_pdf_job

    monkeypatch.setattr(settings, "paper_pdf_dir", str(tmp_path))
    monkeypatch.setattr(paper_pdf_job, "SessionLocal", async_sessionmaker(public_db, expire_on_commit=False))
    async with async_sessionmaker(public_db, expire_on_commit=False)() as session:
        await session.execute(update(Item).where(Item.id == 2).values(content=None))
        await session.commit()

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                             NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({
        NameObject("/F1"): writer._add_object(font),
    })})
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 36 750 Td (" + b"Agricultural research on groundwater " * 10
                    + b"\x00 continues after this character." + b") Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)

    async def downloaded(*args, **kwargs):
        return paper_pdf.PdfDownload(output.getvalue(), "https://publisher.example/article.pdf", "example")

    monkeypatch.setattr(paper_pdf, "download_pdf", downloaded)
    assert await paper_pdf_job.fetch_one(2) == "downloaded"
    detail = (await public_client.get("/api/v1/items/2")).json()
    assert detail["pdf"]["status"] == "ready"
    assert "\x00" not in detail["content"]
    assert "continues after this character" in detail["content"]
    assert (await public_client.get("/api/v1/items/2/pdf")).status_code == 200


@pytest.mark.asyncio
async def test_paper_pdf_job_replaces_invalid_unicode_text(public_db, tmp_path, monkeypatch):
    import io
    from pypdf import PdfWriter
    from app.config import settings
    from app.services import paper_pdf, paper_pdf_job

    monkeypatch.setattr(settings, "paper_pdf_dir", str(tmp_path))
    monkeypatch.setattr(paper_pdf_job, "SessionLocal", async_sessionmaker(public_db, expire_on_commit=False))
    async with async_sessionmaker(public_db, expire_on_commit=False)() as session:
        await session.execute(update(Item).where(Item.id == 1).values(content=None))
        await session.commit()

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    output = io.BytesIO()
    writer.write(output)

    async def downloaded(*args, **kwargs):
        return paper_pdf.PdfDownload(output.getvalue(), "https://publisher.example/paper.pdf", "direct")

    async def extracted(*args, **kwargs):
        return "Agricultural research " * 20 + "\ud800"

    monkeypatch.setattr(paper_pdf, "download_pdf", downloaded)
    monkeypatch.setattr(paper_pdf, "extract_pdf_text", extracted)
    assert await paper_pdf_job.fetch_one(1) == "downloaded"
    async with async_sessionmaker(public_db, expire_on_commit=False)() as session:
        item = await session.get(Item, 1)
        assert item.pdf.status == "ready" and "\ud800" not in item.content


@pytest.mark.asyncio
async def test_paper_pdf_is_kept_when_text_classification_fails(public_db, tmp_path, monkeypatch):
    import io
    from pypdf import PdfWriter
    from app.config import settings
    from app.services import paper_pdf, paper_pdf_job, taxonomy_service

    monkeypatch.setattr(settings, "paper_pdf_dir", str(tmp_path))
    monkeypatch.setattr(paper_pdf_job, "SessionLocal", async_sessionmaker(public_db, expire_on_commit=False))
    async with async_sessionmaker(public_db, expire_on_commit=False)() as session:
        await session.execute(update(Item).where(Item.id == 1).values(content=None))
        await session.execute(update(ItemClassification).where(ItemClassification.item_id == 1).values(locked=False))
        await session.commit()

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    output = io.BytesIO()
    writer.write(output)

    async def downloaded(*args, **kwargs):
        return paper_pdf.PdfDownload(output.getvalue(), "https://publisher.example/paper.pdf", "direct")

    async def extracted(*args, **kwargs):
        return "Agricultural research " * 20

    def broken_hash(*args, **kwargs):
        raise ValueError("classification failed")

    monkeypatch.setattr(paper_pdf, "download_pdf", downloaded)
    monkeypatch.setattr(paper_pdf, "extract_pdf_text", extracted)
    monkeypatch.setattr(taxonomy_service, "input_hash", broken_hash)
    assert await paper_pdf_job.fetch_one(1) == "downloaded"
    async with async_sessionmaker(public_db, expire_on_commit=False)() as session:
        item = await session.get(Item, 1)
        assert item.pdf.status == "ready" and item.content is None


@pytest.mark.asyncio
async def test_missing_pdfs_precede_cursor_scan_without_advancing_it(public_db, monkeypatch):
    from app.services import paper_pdf_job

    monkeypatch.setattr(paper_pdf_job, "SessionLocal", async_sessionmaker(public_db, expire_on_commit=False))
    async with async_sessionmaker(public_db, expire_on_commit=False)() as session:
        session.add(PaperPdf(item_id=1, status="pending", error="pdf_file_missing", attempts=0))
        session.add(PipelineState(key=paper_pdf_job.CURSOR, value="1"))
        await session.commit()

    monkeypatch.setattr(paper_pdf_job, "BATCH", 1)
    assert await paper_pdf_job._batch_ids() == ([1], None)
    monkeypatch.setattr(paper_pdf_job, "BATCH", 2)
    assert await paper_pdf_job._batch_ids() == ([1, 2], 2)


@pytest.mark.asyncio
async def test_unexpected_pdf_fetch_error_records_failure(public_db, monkeypatch):
    from app.services import paper_pdf, paper_pdf_job

    monkeypatch.setattr(paper_pdf_job, "SessionLocal", async_sessionmaker(public_db, expire_on_commit=False))

    async def broken(*args, **kwargs):
        raise ValueError("malformed upstream header")

    monkeypatch.setattr(paper_pdf, "download_pdf", broken)
    assert await paper_pdf_job.fetch_one(1) == "failed"
    async with async_sessionmaker(public_db, expire_on_commit=False)() as session:
        record = await session.get(PaperPdf, 1)
        assert record.status == "failed" and record.error == "fetcher_failed"


@pytest.mark.asyncio
async def test_interrupted_pdf_at_retry_limit_is_not_selected(public_db, monkeypatch):
    from app.services import paper_pdf_job

    monkeypatch.setattr(paper_pdf_job, "SessionLocal", async_sessionmaker(public_db, expire_on_commit=False))
    async with async_sessionmaker(public_db, expire_on_commit=False)() as session:
        session.add(PaperPdf(item_id=1, status="running", attempts=3,
                             updated_at=datetime.now(timezone.utc) - timedelta(hours=1)))
        await session.commit()
    ids, _ = await paper_pdf_job._batch_ids()
    assert ids == [2]


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
    assert detail.json()["tags"] == ["水稻"]
    assert detail.json()["tag_meta"] == [{"name": "水稻", "kind": "keyword"}]


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
