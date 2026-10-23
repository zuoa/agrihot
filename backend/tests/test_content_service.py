"""Reader diagnostics and the verified Guangxi public HTTP article fallback."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DATABASE_URL', 'sqlite+aiosqlite:////tmp/agrihot_test.db')

from app.services import content_service

URL = 'https://nynct.gxzf.gov.cn/xwdt/ywkb/t28253108.shtml'
BODY = '# 从国内创新到国际协同\n\n' + '2026智慧农业博览会集中展示农业科技创新成果。' * 30
TLS_ERROR = {'code': 422, 'message': 'page.goto: net::ERR_CERT_AUTHORITY_INVALID; private-provider-detail'}


@pytest.mark.asyncio
async def test_guangxi_source_certificate_failure_retries_public_http_article(reader_server):
    reader_server.responses.extend([(422, TLS_ERROR), (200, 'Title: 智慧农业博览会\n\nMarkdown Content:\n\n' + BODY)])
    assert await content_service.fetch_fulltext(URL, raise_errors=True) == BODY
    assert reader_server.requests == ['/' + URL, '/' + URL.replace('https://', 'http://', 1)]


@pytest.mark.asyncio
async def test_successful_https_fetch_does_not_retry(reader_server):
    reader_server.responses.append((200, BODY))
    assert await content_service.fetch_fulltext(URL, raise_errors=True) == BODY
    assert reader_server.requests == ['/' + URL]


@pytest.mark.asyncio
@pytest.mark.parametrize('url', [
    'https://other.example/article.shtml',
    'https://nynct.gxzf.gov.cn.other.example/article.shtml',
])
async def test_other_sources_and_authenticated_urls_do_not_downgrade(url, reader_server):
    reader_server.responses.append((422, TLS_ERROR))
    with pytest.raises(content_service.FulltextFetchError) as exc:
        await content_service.fetch_fulltext(url, raise_errors=True)
    assert exc.value.reason == 'source_tls_error' and exc.value.upstream_status == 422
    assert len(reader_server.requests) == 1


@pytest.mark.asyncio
async def test_authenticated_source_url_is_rejected_before_any_request(reader_server):
    with pytest.raises(content_service.FulltextFetchError) as exc:
        await content_service.fetch_fulltext('https://account:password@nynct.gxzf.gov.cn/article.shtml', raise_errors=True)
    assert exc.value.reason == 'invalid_url'
    assert not reader_server.requests


@pytest.mark.asyncio
@pytest.mark.parametrize('status,body,reason', [
    (422, TLS_ERROR, 'source_tls_error'),
    (429, 'private-provider-detail', 'reader_rate_limited'),
    (451, 'private-provider-detail', 'reader_blocked'),
    (401, 'private-provider-detail', 'reader_auth_error'),
    (403, {'status': 40305, 'name': 'AbuseAlleviationError'}, 'reader_domain_blocked'),
    (403, 'private-provider-detail', 'reader_forbidden'),
    (500, 'private-provider-detail', 'reader_http_error'),
    (200, 'too short', 'content_too_short'),
])
async def test_failures_are_best_effort_for_background_and_explicit_for_manual_fetch(reader_server, status, body, reason, caplog):
    reader_server.responses.extend([(status, body), (status, body)])
    url = 'https://example.org/article'
    assert await content_service.fetch_fulltext(url) is None
    with pytest.raises(content_service.FulltextFetchError) as exc:
        await content_service.fetch_fulltext(url, raise_errors=True)
    assert exc.value.reason == reason
    assert 'private-provider-detail' not in str(exc.value) and 'private-provider-detail' not in caplog.text
    assert len(reader_server.requests) == 2


@pytest.mark.asyncio
async def test_fallback_failure_reports_its_actual_error_and_stops(reader_server):
    reader_server.responses.extend([(422, TLS_ERROR), (429, 'rate limit')])
    with pytest.raises(content_service.FulltextFetchError) as exc:
        await content_service.fetch_fulltext(URL, raise_errors=True)
    assert exc.value.reason == 'reader_rate_limited' and exc.value.upstream_status == 429
    assert len(reader_server.requests) == 2
