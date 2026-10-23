"""Provider pacing and cooldown contracts using real local HTTP requests."""
import asyncio
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DATABASE_URL', 'sqlite+aiosqlite:////tmp/agrihot_test.db')

from app.config import settings
from app.services import embedding_service


@pytest.mark.asyncio
async def test_requests_are_paced_across_batches_and_callers(embedding_provider, monkeypatch):
    monkeypatch.setattr(settings, 'embedding_min_interval', 0.1)
    vectors, query = await asyncio.gather(
        embedding_service.embed(['农业'] * 17),
        embedding_service.query_vector('田间长势'),
    )
    assert vectors == [[1, 0, 0]] * 17 and query == [1, 0, 0]
    requests = embedding_provider.requests
    assert sorted(len(payload['input']) for _, payload in requests) == [1, 1, 16]
    assert all(after[0] - before[0] >= 0.08 for before, after in zip(requests, requests[1:]))


@pytest.mark.asyncio
async def test_429_blocks_queued_callers_and_recovers(embedding_provider, caplog):
    embedding_provider.responses.append((429, {'Retry-After': '120'}, {
        'error': {'code': '1302', 'message': 'private-provider-detail'},
    }))
    results = await asyncio.gather(
        embedding_service.embed(['农业']),
        embedding_service.query_vector('遥感'),
        return_exceptions=True,
    )
    assert all(isinstance(result, embedding_service.EmbeddingUnavailable) for result in results)
    assert all(str(result) == 'provider_http_429_1302' for result in results)
    assert all(119 < result.retry_after <= 120 for result in results)
    assert len(embedding_provider.requests) == 1
    assert 'code=1302' in caplog.text
    assert 'private-provider-detail' not in caplog.text
    assert settings.embedding_api_key not in caplog.text

    embedding_service._gate.cooldown_until = time.monotonic() - 1
    assert await embedding_service.query_vector('遥感') == [1, 0, 0]
    assert embedding_service.cooldown_remaining() == 0
    assert len(embedding_provider.requests) == 2


@pytest.mark.asyncio
async def test_cached_vectors_work_during_cooldown(embedding_provider):
    assert await embedding_service.query_vector('农业') == [1, 0, 0]
    embedding_provider.responses.append((429, {}, {'error': {'code': 1305}}))
    with pytest.raises(embedding_service.EmbeddingUnavailable, match='provider_http_429_1305'):
        await embedding_service.embed(['新文章'])
    assert await embedding_service.query_vector('农业') == [1, 0, 0]
    assert len(embedding_provider.requests) == 2


@pytest.mark.asyncio
async def test_repeated_rate_limits_back_off_and_success_resets(embedding_provider):
    for expected in (60, 120, 240, 480, 960, 1920, 3600, 3600):
        embedding_service._gate.cooldown_until = 0
        embedding_provider.responses.append((429, {}, {'error': {'code': '1302'}}))
        with pytest.raises(embedding_service.EmbeddingUnavailable) as exc:
            await embedding_service.embed(['农业'])
        assert exc.value.retry_after == expected
    embedding_service._gate.cooldown_until = 0
    await embedding_service.embed(['农业'])
    embedding_provider.responses.append((429, {}, {'error': {'code': '1302'}}))
    with pytest.raises(embedding_service.EmbeddingUnavailable) as exc:
        await embedding_service.embed(['农业'])
    assert exc.value.retry_after == 60


@pytest.mark.asyncio
async def test_insufficient_balance_is_distinct_and_pauses_for_an_hour(embedding_provider):
    embedding_provider.responses.append((429, {}, {'error': {'code': '1113'}}))
    with pytest.raises(embedding_service.EmbeddingUnavailable, match='provider_insufficient_balance') as exc:
        await embedding_service.embed(['农业'])
    assert exc.value.retry_after == 3600


@pytest.mark.asyncio
async def test_http_date_retry_after_is_respected(embedding_provider):
    deadline = datetime.now(timezone.utc) + timedelta(minutes=3)
    embedding_provider.responses.append((429, {'Retry-After': format_datetime(deadline, usegmt=True)}, {}))
    with pytest.raises(embedding_service.EmbeddingUnavailable) as exc:
        await embedding_service.embed(['农业'])
    assert 178 < exc.value.retry_after <= 180


@pytest.mark.asyncio
@pytest.mark.parametrize('header,body,delay', [
    ('invalid', 'not json', 60),
    ('NaN', {'error': {'code': 'private-code'}}, 60),
    ('999999999', {'error': None}, 86400),
])
async def test_invalid_or_excessive_retry_headers_are_bounded(embedding_provider, header, body, delay, caplog):
    embedding_provider.responses.append((429, {'Retry-After': header}, body))
    with pytest.raises(embedding_service.EmbeddingUnavailable, match='^provider_http_429$') as exc:
        await embedding_service.embed(['农业'])
    assert exc.value.retry_after == delay
    assert 'private-code' not in caplog.text


@pytest.mark.asyncio
async def test_other_http_errors_do_not_start_a_rate_limit_cooldown(embedding_provider):
    embedding_provider.responses.append((401, {}, {'error': {'code': '1000'}}))
    with pytest.raises(embedding_service.EmbeddingUnavailable, match='^provider_http_401$'):
        await embedding_service.embed(['农业'])
    assert embedding_service.cooldown_remaining() == 0
    assert await embedding_service.embed(['农业']) == [[1, 0, 0]]
