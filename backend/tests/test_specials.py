"""Behavioral coverage for evidence lineage, publication and editorial controls."""
import copy
import os
from datetime import timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ.setdefault('DATABASE_URL', 'sqlite+aiosqlite:////tmp/agrihot_test.db')

from app.config import settings
from app.database import ensure_schema, get_session
from app.main import app
from app.models import Base, Item, SearchChunk, SearchJob, Special, SpecialVersion, utcnow
from app.security import issue_admin_token
from app.services import special_service as service
from app.special_schemas import Candidate


@pytest_asyncio.fixture
async def database(tmp_path):
    url = os.getenv('AGRIHOT_TEST_SPECIALS_POSTGRES_URL') or f"sqlite+aiosqlite:///{tmp_path}/specials.db"
    if url.startswith('postgresql'):
        assert url.rsplit('/', 1)[-1].startswith('agrihot_specials_test_'), 'Use a dedicated agrihot_specials_test_ database'
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await ensure_schema(engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def client(database, monkeypatch):
    async def dependency():
        async with database() as session:
            yield session
    old = dict(app.dependency_overrides)
    app.dependency_overrides[get_session] = dependency
    monkeypatch.setattr(settings, "admin_password", "test-specials-password")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
    app.dependency_overrides.update(old)


@pytest_asyncio.fixture
async def material(database):
    async with database() as session:
        for i in range(1, 5):
            session.add(Item(id=i, title=f"田间视觉模型泛化研究之{i}", url=f"https://research.example/{i}", url_hash=str(i), title_simhash=i,
                             summary=f"研究{i}在独立田间数据上评估视觉模型。跨地域测试存在性能差异，仍需更多验证。",
                             content=f"研究{i}采用跨地域田间数据进行训练与测试，模型在新的地区性能下降。该研究只针对一种作物，并未证明适用于其他作物。",
                             source_name=f"研究机构{i}", published_at=utcnow() - timedelta(days=i), category="论文", score=80))
        await session.commit()
    candidate = Candidate(kind="research", title="田间视觉模型如何适应不同地域", scope="比较田间视觉模型跨地域应用中的数据条件、性能差异和适用边界。",
                          items=[{"item_id": i, "role": "core", "reason": "围绕田间视觉模型跨地域泛化问题提供独立实验", "evidence_group": f"study-{i}"} for i in range(1, 4)])
    sources = await service.prepare_sources(candidate, database)
    def claim(i):
        return {"text": "跨地域测试存在性能差异，仍需更多验证。", "kind": "finding",
                "citations": [{"source_id": f"i{i}", "quote": "跨地域测试存在性能差异，仍需更多验证"}]}
    document = {"overview": claim(1), "findings": [claim(i) for i in range(1, 4)], "comparisons": [], "timeline": [], "extensions": []}
    return candidate, sources, document


async def publish(database, material):
    candidate, sources, document = material
    return await service.publish(candidate, document, sources, service.input_hash(candidate, sources), database)


@pytest.mark.asyncio
async def test_publish_detail_filters_and_sitemap(database, material, client):
    special_id, changed = await publish(database, material)
    assert changed
    listing = (await client.get('/api/v1/specials/featured')).json()
    assert listing['specials'][0]['id'] == special_id
    assert listing['specials'][0]['source_count'] == 3
    detail = (await client.get(f'/api/v1/specials/{special_id}', params={'page_size': 2})).json()
    assert len(detail['articles']) == 2 and detail['total'] == 3
    assert detail['articles'][0]['reason']
    assert 'content' not in detail['articles'][0]['item']
    assert all('text' not in s and 'hash' not in s for s in detail['sources'])
    assert (await client.get('/api/v1/specials', params={'item_id': 1})).json()['total'] == 1
    assert (await client.get('/api/v1/specials', params={'kind': 'event'})).json()['total'] == 0
    assert (await client.get('/api/v1/specials', params={'q': '%'})).json()['total'] == 0
    assert f'/specials/{special_id}' in (await client.get('/sitemap.xml')).text


@pytest.mark.asyncio
async def test_changed_sources_never_publish_stale_facts(database, material, client):
    special_id, _ = await publish(database, material)
    async with database() as session:
        item = await session.get(Item, 1)
        item.content = "原文已纠错：此前结论撤回，不能继续引用。"
        await session.commit()
    assert (await client.get('/api/v1/specials/featured')).json()['specials'] == []
    assert (await client.get(f'/api/v1/specials/{special_id}')).status_code == 404
    assert f'/specials/{special_id}' not in (await client.get('/sitemap.xml')).text
    with pytest.raises(ValueError, match='来源已变更'):
        await publish(database, material)


@pytest.mark.asyncio
async def test_valid_previous_version_is_available(database, material, client):
    special_id, _ = await publish(database, material)
    candidate, _, document = material
    candidate.existing_id = special_id
    candidate.items.append(candidate.items[0].model_copy(update={'item_id': 4, 'evidence_group': 'study-4'}))
    sources = await service.prepare_sources(candidate, database)
    await service.publish(candidate, document, sources, service.input_hash(candidate, sources), database)
    async with database() as session:
        await session.delete(await session.get(Item, 4))
        await session.commit()
    response = await client.get(f'/api/v1/specials/{special_id}')
    assert response.status_code == 200 and response.json()['item_count'] == 3


@pytest.mark.asyncio
async def test_noop_refresh_keeps_date_and_skips_network(database, material, monkeypatch):
    special_id, _ = await publish(database, material)
    candidate, _, _ = material
    candidate.existing_id = special_id
    async def forbidden(*args):
        pytest.fail('unchanged input must not call external services')
    monkeypatch.setattr(service, 'llm', forbidden)
    monkeypatch.setattr(service, 'supplement', forbidden)
    assert await service.generate_one(candidate, database) == (special_id, False)
    async with database() as session:
        assert await session.scalar(select(func.count()).select_from(SpecialVersion)) == 1


@pytest.mark.asyncio
async def test_fabricated_quotes_and_false_consensus_rejected(database, material):
    _, sources, document = material
    forged = copy.deepcopy(document)
    forged['findings'][0]['citations'][0]['quote'] = '这个结论在来源中根本不存在'
    with pytest.raises(ValueError, match='摘录'):
        service.validate_evidence(forged, sources)
    forged = copy.deepcopy(document)
    forged['findings'][0]['kind'] = 'shared'
    with pytest.raises(ValueError, match='共同发现'):
        service.validate_evidence(forged, sources)


@pytest.mark.asyncio
async def test_same_doi_and_reposts_cannot_create_hotspot(database, material):
    candidate, _, _ = material
    async with database() as session:
        for i in range(1, 4):
            item = await session.get(Item, i)
            item.category = '报道'
            item.summary += ' 原始论文：https://doi.org/10.1234/shared-study'
        await session.commit()
    sources = await service.prepare_sources(candidate, database)
    assert len({s['evidence_group'] for s in sources}) == 1
    assert not service.eligible(candidate, sources)


@pytest.mark.asyncio
async def test_missing_or_old_dates_do_not_manufacture_hotness(database, material):
    candidate, sources, _ = material
    for source in sources:
        source['published_at'] = None
    assert not service.eligible(candidate, sources)
    for source in sources:
        source['published_at'] = (utcnow() - timedelta(days=61)).isoformat()
    assert not service.eligible(candidate, sources)


@pytest.mark.asyncio
async def test_verifier_failure_keeps_previous_version(database, material, monkeypatch):
    special_id, _ = await publish(database, material)
    candidate, _, document = material
    candidate.existing_id = special_id
    async with database() as session:
        item = await session.get(Item, 1)
        item.summary += ' 新资料补充了不同的数据条件。'
        await session.commit()
    async def llm(system, payload):
        return document if system == service.COMPOSE else {'approved': False, 'reason': '结论超出证据'}
    async def supplement(queries):
        return [], 'unavailable'
    monkeypatch.setattr(service, 'llm', llm)
    monkeypatch.setattr(service, 'supplement', supplement)
    with pytest.raises(ValueError, match='结论超出证据'):
        await service.generate_one(candidate, database)
    async with database() as session:
        assert await session.scalar(select(func.count()).select_from(SpecialVersion)) == 1


@pytest.mark.asyncio
async def test_admin_authorization_lock_withdraw_and_merge(database, material, client):
    special_id, _ = await publish(database, material)
    assert (await client.get('/api/v1/admin/specials')).status_code == 401
    headers = {'X-Admin-Token': issue_admin_token()}
    edited = await client.patch(f'/api/v1/admin/specials/{special_id}', headers=headers, json={'title': '人工修订的田间模型泛化专题', 'pinned': True})
    assert edited.status_code == 200, edited.text
    record = (await client.get(f'/api/v1/admin/specials/{special_id}', headers=headers)).json()
    assert 'title' in record['locked_fields']
    await client.patch(f'/api/v1/admin/specials/{special_id}', headers=headers, json={'status': 'withdrawn'})
    assert (await client.get(f'/api/v1/specials/{special_id}')).status_code == 404
    candidate, sources, document = material
    candidate.title = '目标专题标题'
    target_id, _ = await service.publish(candidate, document, sources, service.input_hash(candidate, sources), database)
    merged = await client.post(f'/api/v1/admin/specials/{special_id}/merge', headers=headers, json={'target_id': target_id})
    assert merged.status_code == 200
    assert (await client.get(f'/api/v1/specials/{special_id}')).json()['redirect_to'] == target_id


@pytest.mark.asyncio
async def test_dry_run_has_no_database_side_effects(database, material, monkeypatch):
    candidate, _, _ = material
    async def discover(system, payload):
        return {'candidates': [candidate.model_dump()]}
    monkeypatch.setattr(service, 'llm', discover)
    result = await service.run_once(factory=database, dry_run=True)
    assert len(result['candidates']) == 1
    async with database() as session:
        assert await session.scalar(select(func.count()).select_from(Special)) == 0
        assert await session.scalar(select(func.count()).select_from(SpecialVersion)) == 0


@pytest.mark.asyncio
async def test_model_group_renaming_and_reason_changes_are_not_updates(database, material):
    candidate, sources, _ = material
    before = service.input_hash(candidate, sources)
    for index, link in enumerate(candidate.items):
        link.evidence_group = f'renamed-{index}'
        link.reason = '新的表述方式，仍然是同一篇文章及同一研究。'
    after = await service.prepare_sources(candidate, database)
    assert service.input_hash(candidate, after) == before


@pytest.mark.asyncio
async def test_failed_new_candidate_is_retained_as_retryable_draft(database, material, monkeypatch):
    candidate, _, _ = material
    async def llm(system, payload):
        if system == service.DISCOVER:
            return {'candidates': [candidate.model_dump()]}
        raise ValueError('上游暂不可用')
    async def supplement(queries):
        return [], 'unavailable'
    monkeypatch.setattr(service, 'llm', llm)
    monkeypatch.setattr(service, 'supplement', supplement)
    result = await service.run_once(factory=database)
    assert result['failed'] == 1
    async with database() as session:
        row = await session.scalar(select(Special))
        assert row.status == 'draft' and row.last_error == '上游暂不可用'


@pytest.mark.asyncio
async def test_semantic_background_uses_ready_current_fingerprint(database, material):
    from app.services import embedding_service
    async with database() as session:
        if session.bind.dialect.name != 'postgresql':
            return  # The same suite additionally runs on real pgvector when configured.
        fp = embedding_service.fingerprint()
        for i, vector in [(1, [1., 0., 0.]), (2, [0.99, 0.01, 0.]), (3, [-1., 0., 0.])]:
            job = await session.get(SearchJob, i)
            job.status, job.fingerprint = 'ready', fp
            session.add(SearchChunk(item_id=i, position=0, text='田间研究', lexemes='', fingerprint=fp, embedding=vector))
        await session.commit()
        results = await service.semantic_background(session, [1], {1})
        assert {row.id for row in results} == {2}


@pytest.mark.asyncio
async def test_shared_references_do_not_merge_independent_papers(database, material):
    candidate, _, _ = material
    async with database() as session:
        for i in range(1, 4):
            item = await session.get(Item, i)
            item.summary += ' 参考背景文献 https://doi.org/10.1234/shared-reference'
            item.doi = f'10.5678/independent-{i}'
        await session.commit()
    sources = await service.prepare_sources(candidate, database)
    assert len({s['evidence_group'] for s in sources}) == 3


@pytest.mark.asyncio
async def test_worker_restart_preserves_special_task_parameters(database, monkeypatch):
    import json
    from app.models import PipelineState
    from app.services import content_worker, job_runner
    monkeypatch.setattr(content_worker, 'SessionLocal', database)
    monkeypatch.setattr(job_runner, 'SessionLocal', database)
    class Interrupted(BaseException):
        pass
    async def interrupted(params):
        raise Interrupted()
    monkeypatch.setitem(job_runner.HANDLERS, 'specials_generate', interrupted)
    with pytest.raises(Interrupted):
        await job_runner.run('specials_generate', {'special_id': 12})
    await content_worker._recover_interrupted()
    params = await content_worker._claim('specials_generate')
    assert params == {'special_id': 12}
    async with database() as session:
        state = await session.get(PipelineState, 'job:specials_generate')
        assert json.loads(state.value)['status'] == 'running'


@pytest.mark.asyncio
async def test_schedule_only_runs_once_after_business_time(database, monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from app.services import special_scheduler
    monkeypatch.setattr(special_scheduler, 'SessionLocal', database)
    calls = []
    async def spawn(name):
        calls.append(name)
        return True
    monkeypatch.setattr(special_scheduler.job_runner, 'spawn', spawn)
    await special_scheduler.tick(datetime(2026, 10, 30, 9, 59, tzinfo=ZoneInfo('Asia/Shanghai')))
    assert calls == []
    for _ in range(2):
        await special_scheduler.tick(datetime(2026, 10, 30, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai')))
    assert calls == ['specials_generate']


@pytest.mark.asyncio
async def test_external_search_snippets_are_never_used_as_evidence(monkeypatch):
    import httpx
    from app.services import special_research
    from app.services.fulltext.base import FulltextFetchError
    requests = []
    async def handler(request):
        requests.append(str(request.url))
        if 'openalex' in request.url.host:
            return httpx.Response(200, json={'results': []})
        return httpx.Response(200, json={'results': [{'title': '仅有搜索摘要的网页', 'url': 'https://research.example/evidence', 'content': '未经抓取和验证的搜索摘要'}]})
    class UnavailableReader:
        async def fetch(self, url):
            raise FulltextFetchError('source_unavailable')
    real_client = httpx.AsyncClient
    monkeypatch.setattr(settings, 'tavily_api_key', 'local-test-only')
    monkeypatch.setattr(special_research.httpx, 'AsyncClient', lambda **kwargs: real_client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(special_research, 'create_fulltext_engine', UnavailableReader)
    sources, status = await special_research.supplement(['query1', 'query2', 'query3'])
    assert sources == [] and status == 'unavailable'
    assert len(requests) == 3


@pytest.mark.asyncio
async def test_discovery_to_publish_and_next_daily_run_is_idempotent(database, material, monkeypatch):
    candidate, _, document = material
    calls = {'compose': 0, 'external': 0}
    async def llm(system, payload):
        if system == service.DISCOVER:
            proposed = candidate.model_copy(deep=True)
            if payload['existing']:
                proposed.existing_id = payload['existing'][0]['id']
                proposed.scope = '模型重新描述了范围，但不应扩大已有专题讨论的问题。'
            return {'candidates': [proposed.model_dump()]}
        if system == service.COMPOSE:
            calls['compose'] += 1
            return document
        return {'approved': True, 'reason': ''}
    async def supplement(queries):
        calls['external'] += 1
        return [], 'unavailable'
    monkeypatch.setattr(service, 'llm', llm)
    monkeypatch.setattr(service, 'supplement', supplement)
    first = await service.run_once(factory=database)
    second = await service.run_once(factory=database)
    assert first['created'] == 1 and first['failed'] == 0
    assert second['created'] == 0 and second['updated'] == 0 and second['skipped'] == 1
    assert calls == {'compose': 1, 'external': 1}
    async with database() as session:
        assert await session.scalar(select(func.count()).select_from(Special)) == 1
        assert await session.scalar(select(func.count()).select_from(SpecialVersion)) == 1
        record = await session.scalar(select(Special))
        assert record.scope == candidate.scope


@pytest.mark.asyncio
async def test_timeline_dates_require_source_support(database, material):
    _, sources, document = material
    source_date = sources[0]['published_at'][:10]
    doc = copy.deepcopy(document)
    doc['timeline'] = [{'date': source_date, 'claim': doc['findings'][0]}]
    service.validate_evidence(doc, sources)
    doc['timeline'][0]['date'] = '2001-01-01'
    with pytest.raises(ValueError, match='时间线日期'):
        service.validate_evidence(doc, sources)


@pytest.mark.asyncio
async def test_cron_multiple_daily_slots_and_worker_restart(database, monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from app.services import runtime_settings, special_scheduler
    monkeypatch.setattr(special_scheduler, 'SessionLocal', database)
    async with database() as session:
        await runtime_settings.patch(session, {'specials_cron': '0 10,18 * * *'})
        await session.commit()
    calls = []
    async def spawn(name):
        calls.append(name)
        return True
    monkeypatch.setattr(special_scheduler.job_runner, 'spawn', spawn)
    for hour in (10, 10, 17, 18, 18):
        runtime_settings.reset()  # The next tick loads the persisted config and deduplication marker.
        await special_scheduler.tick(datetime(2026, 10, 30, hour, 0, tzinfo=ZoneInfo('Asia/Shanghai')))
    assert calls == ['specials_generate', 'specials_generate']


@pytest.mark.asyncio
async def test_cron_weekdays_runtime_changes_and_disabled_schedule(database, monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from app.services import runtime_settings, special_scheduler
    monkeypatch.setattr(special_scheduler, 'SessionLocal', database)
    async def configure(**values):
        async with database() as session:
            await runtime_settings.patch(session, values)
            await session.commit()
    await configure(specials_cron='0 10 * * 1-5')
    calls = []
    async def spawn(name):
        calls.append(name)
        return True
    monkeypatch.setattr(special_scheduler.job_runner, 'spawn', spawn)
    zone = ZoneInfo('Asia/Shanghai')
    await special_scheduler.tick(datetime(2026, 10, 31, 10, 0, tzinfo=zone))  # Saturday
    assert calls == []
    await configure(specials_cron='*/15 * * * *')
    await special_scheduler.tick(datetime(2026, 10, 31, 10, 15, tzinfo=zone))
    assert len(calls) == 1
    await configure(specials_enabled=False)
    await special_scheduler.tick(datetime(2026, 10, 31, 10, 30, tzinfo=zone))
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_legacy_daily_setting_migrates_to_cron(database, monkeypatch):
    import json
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from app.models import PipelineState
    from app.services import runtime_settings, special_scheduler
    monkeypatch.setattr(special_scheduler, 'SessionLocal', database)
    async with database() as session:
        session.add(PipelineState(key=runtime_settings.STATE_KEY, value=json.dumps({'specials_time': '11:45'})))
        session.add(PipelineState(key='specials:last_scheduled_day', value='2026-10-30'))
        await session.commit()
        await runtime_settings.load(session)
    assert runtime_settings.snapshot()['specials_cron']['value'] == '45 11 * * *'
    assert 'specials_time' not in runtime_settings.snapshot()
    calls = []
    async def spawn(name):
        calls.append(name)
        return True
    monkeypatch.setattr(special_scheduler.job_runner, 'spawn', spawn)
    await special_scheduler.tick(datetime(2026, 10, 30, 11, 45, tzinfo=ZoneInfo('Asia/Shanghai')))
    assert calls == []  # Do not repeat today's legacy run during migration.
    async with database() as session:
        await runtime_settings.patch(session, {'specials_cron': '0 12 * * *'})
        await session.commit()
    assert runtime_settings.get('specials_cron') == '0 12 * * *'
    await special_scheduler.tick(datetime(2026, 10, 30, 12, 0, tzinfo=ZoneInfo('Asia/Shanghai')))
    assert calls == ['specials_generate']


@pytest.mark.asyncio
async def test_admin_cron_preview_and_persistence(database, client):
    from app.services import runtime_settings
    headers = {'X-Admin-Token': issue_admin_token()}
    assert (await client.post('/api/v1/admin/settings/specials-preview', json={'expression': '0 10 * * *'})).status_code == 401
    before = (await client.get('/api/v1/admin/settings', headers=headers)).json()
    response = await client.post('/api/v1/admin/settings/specials-preview', headers=headers, json={'expression': '0 10,18 * * *'})
    assert response.status_code == 200, response.text
    assert len(response.json()['next_runs']) == 3
    assert response.json()['timezone'] == 'Asia/Shanghai'
    after = (await client.get('/api/v1/admin/settings', headers=headers)).json()
    assert before['writable'] == after['writable']  # Preview does not save a draft.
    saved = await client.patch('/api/v1/admin/settings', headers=headers, json={'specials_cron': ' 0   10,18 * * * '})
    assert saved.status_code == 200, saved.text
    assert saved.json()['writable']['specials_cron']['value'] == '0 10,18 * * *'
    runtime_settings.reset()
    async with database() as session:
        await runtime_settings.load(session)
    assert runtime_settings.get('specials_cron') == '0 10,18 * * *'
    for expression in ('bad', '0 0 10 * * *', '@daily', '0 25 * * *', '0 0 30 2 *'):
        invalid = await client.patch('/api/v1/admin/settings', headers=headers, json={'specials_cron': expression})
        assert invalid.status_code == 422, invalid.text
    assert runtime_settings.get('specials_cron') == '0 10,18 * * *'


def test_cron_next_runs_use_business_timezone_and_support_intervals():
    from datetime import datetime, timezone
    from app.services.cron_schedule import cron_preview
    result = cron_preview('0 10 * * *', 'Asia/Shanghai', now=datetime(2026, 10, 30, 1, 59, tzinfo=timezone.utc))
    assert result['next_runs'][0] == datetime(2026, 10, 30, 2, 0, tzinfo=timezone.utc)
    result = cron_preview('0 */6 * * *', 'Asia/Shanghai', now=datetime(2026, 10, 30, 1, 0, tzinfo=timezone.utc))
    assert result['next_runs'][0] == datetime(2026, 10, 30, 4, 0, tzinfo=timezone.utc)
    result = cron_preview('0 10 * * MON-FRI', 'Asia/Shanghai', now=datetime(2026, 10, 30, 3, 0, tzinfo=timezone.utc))
    assert result['next_runs'][0] == datetime(2026, 11, 2, 2, 0, tzinfo=timezone.utc)
