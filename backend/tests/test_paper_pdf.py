"""PDF discovery validates downloaded bytes and keeps publisher URLs explicit."""
import httpx
import pytest

from app.services.paper_pdf import download_pdf, plugin_for, is_pdf, store_pdf, validate_pdf
from app.services.fulltext.base import FulltextFetchError


PDF = b"%PDF-1.4\n1 0 obj\nendobj\n%%EOF\n"
PAGE = b'<html><head><meta name="citation_pdf_url" content="/cn/article/pdf/preview/sample.pdf"></head></html>'


@pytest.mark.asyncio
async def test_aeeisp_metadata_downloads_real_pdf():
    visited = []

    def handler(request):
        visited.append(str(request.url))
        if request.url.path.endswith("sample.pdf"):
            return httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"})
        return httpx.Response(200, content=PAGE, headers={"content-type": "text/html"})

    result = await download_pdf(
        ["https://www.aeeisp.com/nygcxb/article/doi/10.11975/sample"],
        transport=httpx.MockTransport(handler), validator=lambda _: _valid(),
    )
    assert result.plugin == "aeeisp" and result.data == PDF
    assert visited[-1] == "https://www.aeeisp.com/cn/article/pdf/preview/sample.pdf"


async def _valid():
    return None


@pytest.mark.asyncio
async def test_pdf_labeled_html_is_rejected():
    def handler(request):
        if request.url.path.endswith(".pdf"):
            return httpx.Response(200, content=b"<html>access denied</html>", headers={"content-type": "application/pdf"})
        return httpx.Response(200, content=PAGE, headers={"content-type": "text/html"})

    with pytest.raises(FulltextFetchError):
        await download_pdf(["https://www.aeeisp.com/article/123"],
                           transport=httpx.MockTransport(handler), validator=lambda _: _valid())
    assert not is_pdf(b"<html>access denied</html>")


def test_pdf_with_fake_header_and_eof_is_rejected_before_storage():
    with pytest.raises(FulltextFetchError):
        validate_pdf(PDF)


def test_worker_refuses_to_store_pdf_without_shared_volume(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setenv("AGRIHOT_PROCESS", "worker")
    monkeypatch.setattr(settings, "paper_pdf_dir", str(tmp_path))
    with pytest.raises(OSError, match="volume is not mounted"):
        store_pdf(PDF)
    assert list(tmp_path.iterdir()) == []


def test_site_plugins_are_selected_by_publisher_host():
    assert plugin_for("https://arxiv.org/abs/2611.02862").name == "arxiv"
    assert plugin_for("https://www.nature.com/articles/example").name == "nature"
    assert plugin_for("https://www.mdpi.com/2077-0472/16/8/846").name == "mdpi"
    assert plugin_for("https://www.frontiersin.org/articles/example/full").name == "frontiers"


@pytest.mark.asyncio
async def test_nature_reference_manuscript_follows_html_pdf_route():
    def handler(request):
        if request.url.path.endswith("_reference.pdf"):
            return httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"})
        return httpx.Response(200, content=b"<html>Article page</html>",
                              headers={"content-type": "text/html"})

    result = await download_pdf(["https://www.nature.com/articles/s41598-026-66501-5"],
                                transport=httpx.MockTransport(handler), validator=lambda _: _valid())
    assert result.url == "https://www.nature.com/articles/s41598-026-66501-5_reference.pdf"


@pytest.mark.asyncio
async def test_automatic_pdf_job_pauses_before_reserving_items_on_low_disk(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from app.config import settings
    from app.services import paper_pdf_job, runtime_settings

    monkeypatch.setattr(settings, "paper_pdf_dir", str(tmp_path))
    monkeypatch.setattr(runtime_settings, "get", lambda _: True)
    monkeypatch.setattr(paper_pdf_job.shutil, "disk_usage", lambda _: SimpleNamespace(free=1))

    async def unexpected_batch():
        raise AssertionError("Low disk space must leave the queue untouched")

    async def logged(*args, **kwargs):
        return None

    monkeypatch.setattr(paper_pdf_job, "_batch_ids", unexpected_batch)
    monkeypatch.setattr(paper_pdf_job.job_runner, "append_log", logged)
    stats = await paper_pdf_job.run({})
    assert stats["storage_paused"] and stats["requested"] == 0


@pytest.mark.asyncio
async def test_openalex_open_pdf_fallback():
    def handler(request):
        if request.url.host == "api.openalex.org":
            return httpx.Response(200, json={"best_oa_location": {
                "is_oa": True, "pdf_url": "https://repository.example/paper.pdf"}})
        if request.url.path.endswith("paper.pdf"):
            return httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"})
        return httpx.Response(200, content=b"<html>Abstract only</html>", headers={"content-type": "text/html"})

    result = await download_pdf(["https://publisher.example/article"], doi="10.1234/example",
                                transport=httpx.MockTransport(handler), validator=lambda _: _valid())
    assert result.url == "https://repository.example/paper.pdf"


@pytest.mark.asyncio
async def test_known_pdf_route_survives_blocked_landing_page():
    def handler(request):
        if request.url.path.endswith("/pdf"):
            return httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"})
        return httpx.Response(403)

    result = await download_pdf(["https://www.mdpi.com/2077-0472/16/8/846"],
                                transport=httpx.MockTransport(handler), validator=lambda _: _valid())
    assert result.url.endswith("/pdf")


@pytest.mark.asyncio
@pytest.mark.parametrize("doi,journal,slug,number", [
    ("10.3390/app16178869", "Applied Sciences", "applsci", "08869"),
    ("10.3390/su18179186", "Sustainability", "sustainability", "09186"),
])
async def test_mdpi_cdn_downloads_when_publisher_blocks(doi, journal, slug, number):
    def handler(request):
        if request.url.host == "api.crossref.org":
            return httpx.Response(200, json={"message": {
                "DOI": doi, "container-title": [journal], "volume": "16" if slug == "applsci" else "18",
                "page": str(int(number)),
            }})
        if request.url.host == "mdpi-res.com":
            return httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"})
        return httpx.Response(403)

    result = await download_pdf(["https://doi.org/" + doi], doi=doi,
                                transport=httpx.MockTransport(handler), validator=lambda _: _valid())
    name = f"{slug}-{'16' if slug == 'applsci' else '18'}-{number}"
    assert result.url == f"https://mdpi-res.com/d_attachment/{slug}/{name}/article_deploy/{name}.pdf"


@pytest.mark.asyncio
async def test_mdpi_url_without_doi_uses_matching_crossref_record():
    visited = []

    def handler(request):
        visited.append(str(request.url))
        if request.url.host == "api.crossref.org":
            base = {"publisher": "MDPI AG", "ISSN": ["2077-0472"],
                    "container-title": ["Agriculture"], "volume": "16", "issue": "2"}
            return httpx.Response(200, json={"message": {"items": [
                {**base, "DOI": "10.3390/agriculture16020142", "page": "142"},
                {**base, "DOI": "10.3390/agriculture16020141", "page": "141"},
            ]}})
        if request.url.host == "mdpi-res.com":
            return httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"})
        return httpx.Response(403)

    result = await download_pdf(["https://www.mdpi.com/2077-0472/16/2/141"],
                                transport=httpx.MockTransport(handler), validator=lambda _: _valid())
    assert result.url == ("https://mdpi-res.com/d_attachment/agriculture/agriculture-16-00141"
                          "/article_deploy/agriculture-16-00141.pdf")
    assert "journals/2077-0472/works" in visited[0]


@pytest.mark.asyncio
async def test_oversized_pdf_reason_survives_later_blocked_source():
    from app.config import settings

    def handler(request):
        if request.url.path.endswith(".pdf"):
            return httpx.Response(200, headers={"content-length": str(settings.paper_pdf_max_bytes + 1)})
        return httpx.Response(403)

    with pytest.raises(FulltextFetchError) as error:
        await download_pdf(["https://publisher.example/large.pdf", "https://publisher.example/blocked"],
                           transport=httpx.MockTransport(handler), validator=lambda _: _valid())
    assert error.value.reason == "content_too_large"


@pytest.mark.asyncio
async def test_client_challenge_has_access_denied_reason():
    def handler(request):
        return httpx.Response(200, content=b"<html><title>Client Challenge</title></html>",
                              headers={"content-type": "text/html"})

    with pytest.raises(FulltextFetchError) as error:
        await download_pdf(["https://www.nature.com/articles/example.pdf"],
                           transport=httpx.MockTransport(handler), validator=lambda _: _valid())
    assert error.value.reason == "content_access_denied"


@pytest.mark.asyncio
async def test_aeeisp_preview_route_survives_blocked_article_page():
    def handler(request):
        if request.url.path.endswith("/10.11975/sample.pdf"):
            return httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"})
        return httpx.Response(403)

    result = await download_pdf(["https://www.aeeisp.com/nygcxb/article/doi/10.11975/sample"],
                                transport=httpx.MockTransport(handler), validator=lambda _: _valid())
    assert result.url == "https://www.aeeisp.com/nygcxb/cn/article/pdf/preview/10.11975/sample.pdf"
