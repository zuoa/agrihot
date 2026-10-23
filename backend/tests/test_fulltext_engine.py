"""Strategy routing, real document parsers, fallbacks and request boundaries."""
import asyncio
import gzip
import io
import os
import sys

import httpx
import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DATABASE_URL', 'sqlite+aiosqlite:////tmp/agrihot_test.db')

from app.services.fulltext import (
    FetchOptions, FetchResult, FulltextEngine, FulltextFetcher, FulltextFetchError,
    HtmlFetcher, JatsXmlFetcher, JinaFetcher, PdfFetcher,
)
from app.services.fulltext.base import FetchContext, validate_public_source
from app.services.fulltext.extractors import extract_jats

BODY = 'Agricultural research measures productivity, farm income, and rural development. ' * 12
XML = (f'<article><front><article-meta><title-group><article-title>Rural prosperity</article-title>'
       f'</title-group><abstract><p>Abstract only.</p></abstract></article-meta></front>'
       f'<body><sec><title>Methods</title><p>{BODY}</p><sec><title>Results</title><p>Final result.</p></sec>'
       f'<table-wrap><caption><p>Yield measurements</p></caption><table><tr><td>Yield</td><td>42</td></tr></table>'
       f'</table-wrap></sec></body><back><ref-list><ref>Reference text</ref></ref-list></back></article>').encode()
HTML = f'<html><body><nav>UNRELATED NAVIGATION</nav><article><h1>Rural prosperity</h1><p>{BODY}</p></article></body></html>'
DOI = 'https://doi.org/10.3389/fsufs.2026.1904226'
PUBLISHER = 'https://www.frontiersin.org/journals/test/articles/10.3389/fsufs.2026.1904226/full'


async def allow_test_url(url):
    pass


def engine_for(handler, fetchers=None, **options):
    return FulltextEngine(fetchers, options=FetchOptions(**options),
                          transport=httpx.MockTransport(handler), validator=allow_test_url)


def pdf_bytes(text=BODY):
    """Produce a valid PDF with an actual text layer, not a stub parser result."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'),
                             NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({
        NameObject('/F1'): writer._add_object(font),
    })})
    stream = DecodedStreamObject()
    stream.set_data(f'BT /F1 12 Tf 36 750 Td ({text}) Tj ET'.encode())
    page[NameObject('/Contents')] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.mark.asyncio
async def test_doi_routes_to_publisher_jats_instead_of_reader_doi():
    requested = []

    def handler(request):
        requested.append(str(request.url))
        if str(request.url) == DOI:
            return httpx.Response(302, headers={'Location': PUBLISHER})
        if str(request.url) == PUBLISHER:
            return httpx.Response(200, headers={'Content-Type': 'text/html'}, text='<meta name="citation_xml_url" content="./xml">')
        if request.url.path.endswith('/xml'):
            return httpx.Response(200, headers={'Content-Type': 'text/xml'}, content=XML)
        pytest.fail(f'Unexpected request: {request.url}')

    result = await engine_for(handler).fetch(DOI)
    assert result.fetcher == 'doi>frontiers_xml'
    assert result.source_url == PUBLISHER.removesuffix('/full') + '/xml'
    assert '## Methods' in result.text and '### Results' in result.text
    assert 'Final result.' in result.text and 'Yield measurements' in result.text and 'Reference text' in result.text
    assert len(requested) == 3 and not result.truncated and not result.attempts


@pytest.mark.asyncio
async def test_doi_crossref_fallback_and_redirect_cycle_are_bounded():
    requested = []

    def handler(request):
        requested.append(request.url.host)
        if request.url.host == 'doi.org':
            return httpx.Response(302, headers={'Location': DOI})
        if request.url.host == 'api.crossref.org':
            return httpx.Response(200, json={'message': {'resource': {'primary': {'URL': 'https://journal.example/article'}}}})
        return httpx.Response(200, headers={'Content-Type': 'text/html'}, text=HTML)

    result = await engine_for(handler).fetch(DOI)
    assert result.fetcher == 'doi>html' and BODY.strip() in result.text
    assert requested == ['doi.org', 'api.crossref.org', 'journal.example']


@pytest.mark.asyncio
async def test_failed_doi_can_use_known_open_access_pdf():
    def handler(request):
        if request.url.host in {'doi.org', 'api.crossref.org'}:
            return httpx.Response(404)
        assert str(request.url) == 'https://repository.example/paper.pdf'
        return httpx.Response(200, content=pdf_bytes(), headers={'Content-Type': 'application/pdf'})

    result = await engine_for(handler).fetch(DOI, alternative_urls=['https://repository.example/paper.pdf'])
    assert result.fetcher == 'pdf' and BODY.strip() in result.text
    assert result.attempts[0].fetcher == 'doi' and result.attempts[0].reason == 'doi_resolution_failed'


@pytest.mark.asyncio
@pytest.mark.parametrize('url', ['https://news.example/story', 'https://www.frontiersin.org/articles/paper/full'])
async def test_bad_publisher_xml_falls_back_to_advertised_pdf(url):
    def handler(request):
        if request.url.path.endswith('.xml'):
            return httpx.Response(200, content=b'<article><abstract>Only an abstract</abstract></article>')
        if request.url.path.endswith('.pdf'):
            return httpx.Response(200, content=pdf_bytes())
        return httpx.Response(200, headers={'Content-Type': 'text/html'}, text=(
            '<meta name="citation_xml_url" content="/paper.xml">'
            '<meta name="CITATION_PDF_URL" content="/paper.pdf">' + HTML))

    result = await engine_for(handler).fetch(url)
    assert result.fetcher.endswith('_pdf') and BODY.strip() in result.text
    assert result.attempts[0].reason == 'unsupported_content'


@pytest.mark.asyncio
async def test_html_extraction_removes_navigation_and_retains_body():
    result = await engine_for(lambda request: httpx.Response(200, headers={'Content-Type': 'text/html'}, text=HTML)).fetch('https://news.example/story')
    assert result.fetcher == 'html' and BODY.strip() in result.text and 'UNRELATED NAVIGATION' not in result.text


@pytest.mark.asyncio
async def test_source_failure_uses_reader_without_forwarding_reader_credentials():
    requested = []

    def handler(request):
        requested.append(request)
        if request.url.host == 'news.example':
            assert 'authorization' not in request.headers
            return httpx.Response(403)
        assert request.url.host == 'reader.example' and request.headers['authorization'] == 'Bearer test-key'
        return httpx.Response(200, text='Title: Test\n\nMarkdown Content:\n\n' + BODY)

    result = await engine_for(handler, jina_base_url='https://reader.example', jina_api_key='test-key').fetch('https://news.example/story')
    assert result.fetcher == 'jina' and result.text == BODY.strip()
    assert len(requested) == 2 and result.attempts[0].upstream_status == 403


@pytest.mark.asyncio
async def test_verified_government_tls_fallback_uses_same_path_http():
    requested = []

    def handler(request):
        requested.append(str(request.url))
        if request.url.scheme == 'https':
            raise httpx.ConnectError('CERTIFICATE_VERIFY_FAILED', request=request)
        return httpx.Response(200, headers={'Content-Type': 'text/html'}, text=HTML)

    url = 'https://nynct.gxzf.gov.cn/xwdt/ywkb/t28253108.shtml'
    result = await engine_for(handler).fetch(url)
    assert result.fetcher == 'government_html' and result.source_url == url.replace('https:', 'http:')
    assert requested == [url, url.replace('https:', 'http:')]


@pytest.mark.asyncio
async def test_failed_requests_are_reused_across_strategies():
    requested = []

    def handler(request):
        requested.append(request.url.host)
        if request.url.host == 'province.gov.cn':
            raise httpx.ConnectError('connection failed', request=request)
        return httpx.Response(200, text=BODY)

    result = await engine_for(handler, jina_base_url='https://reader.example').fetch('https://province.gov.cn/story')
    assert result.fetcher == 'jina' and requested == ['province.gov.cn', 'reader.example']
    assert [attempt.fetcher for attempt in result.attempts] == ['government_html', 'html']


@pytest.mark.asyncio
@pytest.mark.parametrize('status,payload,reason', [
    (403, {'status': 40305, 'name': 'AbuseAlleviationError'}, 'reader_domain_blocked'),
    (403, {'name': 'AuthenticationRequiredError'}, 'reader_auth_error'),
    (403, {'message': 'secret provider response'}, 'reader_forbidden'),
    (401, {'message': 'secret provider response'}, 'reader_auth_error'),
])
async def test_reader_reports_domain_blocks_and_auth_errors_separately(status, payload, reason):
    with pytest.raises(FulltextFetchError) as exc:
        await engine_for(lambda request: httpx.Response(status, json=payload), [JinaFetcher()]).fetch('https://news.example/story')
    assert exc.value.reason == reason and exc.value.upstream_status == status
    assert 'secret provider response' not in str(exc.value)


@pytest.mark.asyncio
async def test_invalid_optional_urls_do_not_block_good_primary_or_alternative():
    engine = engine_for(lambda request: httpx.Response(200, headers={'Content-Type': 'text/plain'}, text=BODY), [HtmlFetcher()])
    result = await engine.fetch('https://news.example/story#section', alternative_urls=['ftp://bad.example/file', 'https://news.example/story'])
    assert result.source_url == 'https://news.example/story' and result.attempts[0].reason == 'invalid_url'
    result = await engine.fetch('not a URL', alternative_urls=['https://news.example/story'])
    assert result.text == BODY.strip()


@pytest.mark.asyncio
@pytest.mark.parametrize('url', ['file:///etc/passwd', 'https://user:password@news.example/story', 'https://news.example:invalid/story'])
async def test_invalid_sources_fail_without_request(url):
    with pytest.raises(FulltextFetchError, match='链接无效'):
        await engine_for(lambda request: pytest.fail('No request expected')).fetch(url)


@pytest.mark.asyncio
@pytest.mark.parametrize('url', ['http://127.0.0.1/story', 'http://169.254.169.254/latest', 'http://[::1]/story'])
async def test_direct_sources_must_have_public_addresses(url):
    with pytest.raises(FulltextFetchError) as exc:
        await validate_public_source(url)
    assert exc.value.reason == 'source_not_public'


@pytest.mark.asyncio
async def test_redirect_to_private_source_is_rejected_before_request():
    requested = []

    async def validator(url):
        if httpx.URL(url).host == '127.0.0.1':
            raise FulltextFetchError('source_not_public')

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(302, headers={'Location': 'http://127.0.0.1/private'})

    engine = FulltextEngine([HtmlFetcher()], transport=httpx.MockTransport(handler), validator=validator)
    with pytest.raises(FulltextFetchError) as exc:
        await engine.fetch('https://news.example/story')
    assert exc.value.reason == 'source_not_public' and requested == ['https://news.example/story']


@pytest.mark.asyncio
async def test_cross_origin_redirect_does_not_forward_authorization():
    def handler(request):
        if request.url.host == 'reader.example':
            assert request.headers['authorization'] == 'Bearer test-key'
            return httpx.Response(302, headers={'Location': 'https://source.example/story'})
        assert 'authorization' not in request.headers and 'cookie' not in request.headers
        return httpx.Response(200, text=BODY)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        context = FetchContext(client, FetchOptions(), validator=allow_test_url)
        response = await context.get('https://reader.example/story', trusted=True,
                                     headers={'Authorization': 'Bearer test-key', 'Cookie': 'secret=value'})
        assert response.text == BODY


@pytest.mark.asyncio
async def test_total_deadline_and_cancellation_are_preserved():
    async def slow(request):
        await asyncio.sleep(1)
        return httpx.Response(200, text=BODY)

    with pytest.raises(FulltextFetchError) as exc:
        await engine_for(slow, [HtmlFetcher()], timeout=.02).fetch('https://news.example/story')
    assert exc.value.reason == 'fetch_timeout'
    task = asyncio.create_task(engine_for(slow, [HtmlFetcher()]).fetch('https://news.example/story'))
    await asyncio.sleep(.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_oversized_download_is_rejected_and_output_truncation_is_explicit():
    handler = lambda request: httpx.Response(200, headers={'Content-Type': 'text/plain'}, text=BODY)
    with pytest.raises(FulltextFetchError) as exc:
        await engine_for(handler, [HtmlFetcher()], max_bytes=32).fetch('https://news.example/story')
    assert exc.value.reason == 'content_too_large'
    result = await engine_for(handler, [HtmlFetcher()], max_chars=300).fetch('https://news.example/story')
    assert len(result.text) == 300 and result.truncated


@pytest.mark.asyncio
async def test_gzip_response_is_decoded_once():
    result = await engine_for(lambda request: httpx.Response(200, headers={
        'Content-Type': 'text/plain', 'Content-Encoding': 'gzip',
    }, content=gzip.compress(BODY.encode())), [HtmlFetcher()]).fetch('https://news.example/story')
    assert result.text == BODY.strip()


@pytest.mark.asyncio
async def test_custom_fetcher_registration_and_parser_failure_fallback():
    class CustomFetcher(FulltextFetcher):
        name, priority = 'custom', -10

        def supports(self, url):
            return True

        async def fetch(self, url, context):
            return FetchResult(BODY, url, self.name)

    class BrokenFetcher(CustomFetcher):
        name, priority = 'broken', -20

        def supports(self, url):
            raise RuntimeError('bad plugin')

    engine = engine_for(lambda request: pytest.fail('No network expected'))
    engine.register(CustomFetcher())
    engine.register(BrokenFetcher())
    result = await engine.fetch('https://source.example/story')
    assert result.fetcher == 'custom' and result.attempts[0].reason == 'fetcher_failed'


@pytest.mark.asyncio
@pytest.mark.parametrize('text,reason', [('Short body', 'content_too_short'), ('Access denied\n' + 'x' * 500, 'content_access_denied')])
async def test_error_pages_are_not_returned_as_articles(text, reason):
    with pytest.raises(FulltextFetchError) as exc:
        await engine_for(lambda request: httpx.Response(200, headers={'Content-Type': 'text/plain'}, text=text), [HtmlFetcher()]).fetch('https://news.example/story')
    assert exc.value.reason == reason


@pytest.mark.asyncio
async def test_scanned_or_invalid_pdfs_fail_without_saving_garbage():
    for content, reason in [(pdf_bytes(''), 'pdf_no_text'), (b'<html>Not a PDF</html>', 'unsupported_content')]:
        with pytest.raises(FulltextFetchError) as exc:
            await engine_for(lambda request: httpx.Response(200, content=content), [PdfFetcher()]).fetch('https://source.example/paper.pdf')
        assert exc.value.reason == reason


@pytest.mark.asyncio
async def test_jats_fetcher_rejects_abstract_only_and_external_entities():
    abstract_only = f'<article><front><abstract><p>{BODY}</p></abstract></front></article>'.encode()
    with pytest.raises(FulltextFetchError):
        await engine_for(lambda request: httpx.Response(200, content=abstract_only), [JatsXmlFetcher()]).fetch('https://journal.example/paper.xml')
    entity_xml = b'<!DOCTYPE article [<!ENTITY local SYSTEM "file:///etc/passwd">]><article><body><p>&local;</p></body></article>'
    with pytest.raises(FulltextFetchError):
        extract_jats(entity_xml)
