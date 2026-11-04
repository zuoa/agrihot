"""Behavioral coverage for evidence lineage, publication and editorial controls."""
import copy
import json
import os
from datetime import datetime, timedelta, timezone

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


@pytest.fixture
def model_requests(monkeypatch):
    import httpx
    from collections import deque
    from types import SimpleNamespace

    provider = SimpleNamespace(responses=deque(), requests=[], waits=[])

    async def handler(request):
        provider.requests.append(json.loads(request.content))
        response = provider.responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response

    async def wait(delay):
        provider.waits.append(delay)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(service.httpx, 'AsyncClient', lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setattr(service, 'sleep', wait)
    monkeypatch.setattr(settings, 'deepseek_api_key', 'retry-secret-not-for-logs')
    return provider


async def publish(database, material):
    candidate, sources, document = material
    return await service.publish(candidate, document, sources, service.input_hash(candidate, sources), database)


@pytest.mark.asyncio
async def test_event_progress_keeps_ids_through_rewrites_and_highlights_only_new_nodes(database, material, client):
    from app.services import special_timeline
    candidate, sources, document = material
    candidate.kind = 'event'
    document['timeline'] = [{'date': special_timeline.source_day(sources[0]), 'date_basis': 'published',
                             'title': '跨地域评估结果发布', 'claim': copy.deepcopy(document['findings'][0])}]
    special_id, _ = await publish(database, material)
    first = (await client.get(f'/api/v1/specials/{special_id}')).json()
    original_id = first['document']['timeline'][0]['id']
    assert original_id and first['new_progress_ids'] == []
    assert first['latest_progress']['title'] == '跨地域评估结果发布'
    # A rewrite using the same evidence must not become a new progress node.
    rewritten = copy.deepcopy(first['document'])
    rewritten['timeline'][0].pop('id')
    rewritten['timeline'][0]['claim']['text'] = '跨地域测试提示仍需进一步验证。'
    rewritten = special_timeline.prepare(rewritten, first['document'], sources)
    assert rewritten['timeline'][0]['id'] == original_id
    assert special_timeline.new_ids(rewritten, first['document']) == []
    # Append a genuinely later release, retaining the old node even if omitted.
    async with database() as session:
        item = await session.get(Item, 4)
        item.published_at = utcnow()
        item.summary = '新一轮试验扩大了测试地域，新增两个独立数据集进行验证。'
        await session.commit()
    candidate.existing_id = special_id
    candidate.items.append(type(candidate.items[0])(item_id=4, role='core', reason='新一轮试验提供进一步验证结果', evidence_group='study-4'))
    sources = await service.prepare_sources(candidate, database)
    latest = copy.deepcopy(document)
    latest['timeline'] = [{'date': special_timeline.source_day(sources[-1]), 'date_basis': 'published', 'title': '新一轮试验扩大验证范围',
                           'claim': {'text': '新增两个独立数据集进行验证。', 'kind': 'finding',
                                     'citations': [{'source_id': 'i4', 'quote': '新增两个独立数据集进行验证。'}]}}]
    await service.publish(candidate, latest, sources, service.input_hash(candidate, sources), database)
    second = (await client.get(f'/api/v1/specials/{special_id}')).json()
    assert len(second['document']['timeline']) == 2
    assert original_id in {row['id'] for row in second['document']['timeline']}
    assert len(second['new_progress_ids']) == 1 and original_id not in second['new_progress_ids']
    assert second['latest_progress']['title'] == '新一轮试验扩大验证范围'


@pytest.mark.asyncio
async def test_progress_date_basis_and_duplicate_reports(material):
    from app.services import special_timeline
    candidate, sources, document = material
    day = special_timeline.source_day(sources[0])
    row = {'date': day, 'date_basis': 'event', 'claim': copy.deepcopy(document['findings'][0])}
    document['timeline'] = [row]
    with pytest.raises(service.EvidenceValidationError) as error:
        service.validate_evidence(document, sources, kind='event')
    assert error.value.errors[0]['code'] == 'timeline_evidence'
    row['date_basis'] = 'published'
    service.validate_evidence(document, sources, kind='event')
    document['timeline'].append(copy.deepcopy(row))
    merged = special_timeline.prepare(document, None, sources)
    assert len(merged['timeline']) == 1
    legacy = copy.deepcopy(document)
    for entry in legacy['timeline']:
        entry.pop('date_basis', None)
    assert special_timeline.prepare(legacy, None, sources)['timeline'][0]['date_basis'] == 'published'
    future = copy.deepcopy(document)
    tomorrow = (utcnow() + timedelta(days=2)).date().isoformat()
    future['timeline'] = [{**row, 'date': tomorrow}]
    with pytest.raises(service.EvidenceValidationError) as error:
        service.validate_evidence(future, sources, kind='event')
    assert any(issue['code'] == 'timeline_date' for issue in error.value.errors)
    with pytest.raises(service.EvidenceValidationError):
        service.validate_evidence(merged, sources, kind='research')


@pytest.mark.asyncio
async def test_progress_preserves_only_valid_history_and_limits_to_latest_15(material):
    from app.services import special_timeline
    _, sources, document = material
    old = copy.deepcopy(document)
    old['timeline'] = [{'date': '2026-01-01', 'claim': copy.deepcopy(document['findings'][0])}]
    # Historical nodes with unsupported dates disappear rather than invent evidence.
    assert special_timeline.prepare(document, old, sources)['timeline'] == []
    rows = []
    for day in range(1, 18):
        rows.append({'date': f'2026-10-{day:02}', 'date_basis': 'published', 'claim': copy.deepcopy(document['findings'][0])})
    document['timeline'] = rows
    result = special_timeline.prepare(document, None, sources)
    assert len(result['timeline']) == 15 and result['timeline'][0]['date'] == '2026-10-17' and result['timeline'][-1]['date'] == '2026-10-03'


@pytest.mark.asyncio
async def test_reading_aids_do_not_invalidate_published_facts(database, material, client):
    from app.services.editorial_service import apply_manual
    special_id, _ = await publish(database, material)
    async with database() as session:
        item = await session.get(Item, 1)
        apply_manual(item, {'attention_point': '研究保留了跨地域性能差异，应用前仍需对照具体实验条件。',
                            'source_provenance': {'type': 'research'}})
        await session.commit()
    response = await client.get(f'/api/v1/specials/{special_id}')
    assert response.status_code == 200
    assert response.json()['articles'][0]['item']['attention_point']


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
async def test_citation_errors_identify_every_invalid_reference(material):
    _, sources, document = material
    document['overview']['citations'][0]['source_id'] = '1'
    document['findings'][0]['citations'][0]['quote'] = '不存在于原始材料的模型改写'
    document['comparisons'] = [{
        'item_id': 1, 'object': '', 'method': '', 'data': '', 'result': '', 'limitation': '',
        'citations': [{'source_id': 'missing', 'quote': '不存在于原始材料的摘录'}],
    }]
    document['timeline'] = [{'date': sources[0]['published_at'][:10], 'claim': copy.deepcopy(document['findings'][0])}]
    document['extensions'] = [{'kind': 'method', 'title': '跨域评估', 'body': copy.deepcopy(document['findings'][0])}]

    with pytest.raises(service.EvidenceValidationError) as caught:
        service.validate_evidence(document, sources)

    errors = caught.value.errors
    assert {e['path'] for e in errors} == {
        'overview.citations[0].source_id', 'findings[0].citations[0].quote',
        'comparisons[0].citations[0].source_id', 'timeline[0].claim.citations[0].quote',
        'extensions[0].body.citations[0].quote',
        'overview.citations', 'comparisons[0].citations',
    }
    assert errors[0]['source_id'] == '1' and '来源不存在' in errors[0]['reason']
    assert errors[1]['source_id'] == 'i1' and '摘录与原文不符' in errors[1]['reason']
    assert '共 7 处' in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize('quote', [
    '跨地域测试存在性能差异……仍需更多验证',  # Discontinuous excerpts.
    '跨地域测试存在性能差异,仍需更多验证',  # Changed source punctuation.
    '        ',
])
async def test_inexact_or_blank_excerpts_remain_invalid(material, quote):
    _, sources, document = material
    document['overview']['citations'][0]['quote'] = quote
    with pytest.raises(service.CitationValidationError):
        service.validate_evidence(document, sources)


@pytest.mark.asyncio
async def test_generation_corrects_all_citations_before_review(database, material, monkeypatch):
    candidate, _, document = material
    external = {'id': 'e1', 'kind': 'external', 'basis': 'abstract',
                'text': 'Cross-region evaluation reveals performance differences under changing field conditions.'}
    corrected = copy.deepcopy(document)
    corrected['extensions'] = [{'kind': 'method', 'title': '跨域评估', 'body': {
        'text': '跨地域评估可用于分析不同田间条件下的性能差异。', 'kind': 'inference',
        'citations': [{'source_id': 'e1', 'quote': external['text']}],
    }}]
    invalid = copy.deepcopy(corrected)
    invalid['overview']['citations'][0]['source_id'] = '1'
    invalid['extensions'][0]['body']['citations'][0]['quote'] = '跨地域评估表明田间条件变化时存在性能差异。'
    compose_calls, review_calls, external_calls = [], [], []

    async def llm(system, payload):
        if system == service.DISCOVER:
            return {'candidates': [candidate.model_dump()]}
        if system == service.COMPOSE:
            compose_calls.append(copy.deepcopy(payload))
            return invalid if len(compose_calls) == 1 else corrected
        assert system == service.VERIFY
        review_calls.append(copy.deepcopy(payload))
        return {'approved': True, 'reason': ''}

    async def supplement(queries):
        external_calls.append(queries)
        return [copy.deepcopy(external)], 'academic_only'

    monkeypatch.setattr(service, 'llm', llm)
    monkeypatch.setattr(service, 'supplement', supplement)
    result = await service.run_once(factory=database)

    assert result['created'] == 1 and result['failed'] == 0
    assert len(compose_calls) == 2 and len(review_calls) == 1 and len(external_calls) == 1
    first, retry = compose_calls
    assert 'previous_document' not in first and 'validation_errors' not in first
    assert retry['sources'] == first['sources'] == review_calls[0]['sources']
    assert retry['previous_document'] == invalid
    assert {e['path'] for e in retry['validation_errors']} == {
        'overview.citations[0].source_id', 'extensions[0].body.citations[0].quote', 'overview.citations',
    }
    assert review_calls[0]['document'] == corrected
    async with database() as session:
        versions = (await session.scalars(select(SpecialVersion))).all()
        assert len(versions) == 1 and versions[0].document == corrected
        special = await session.scalar(select(Special))
        assert special.status == 'published' and special.last_error is None


@pytest.mark.asyncio
@pytest.mark.parametrize('break_citation_after_review', [False, True])
async def test_semantic_rejection_is_revised_and_rechecked_with_current_date(database, material, monkeypatch, break_citation_after_review):
    candidate, _, corrected = material
    invalid = copy.deepcopy(corrected)
    invalid['overview']['text'] = '这些研究共同证明模型适用于所有作物，跨地域均能保持优秀性能。'
    # Correct excerpts alone cannot establish whether a conclusion follows from them.
    feedback = {'approved': False, 'reason': '概述遗漏适用边界并制造共同结论', 'issues': [{
        'path': 'overview.text', 'source_ids': ['i1', 'i2', 'i3'],
        'reason': '来源仅检验一种作物且跨地域性能下降，改为有条件的单项发现，不能外推所有作物。',
    }]}
    as_of = datetime(2026, 11, 4, 16, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(service, 'utcnow', lambda: as_of)
    monkeypatch.setattr(settings, 'daily_timezone', 'Asia/Shanghai')
    compose, reviews, supplements, logs = [], [], [], []

    async def llm(system, payload):
        if system == service.DISCOVER:
            return {'candidates': [candidate.model_dump()]}
        assert payload['today'] == '2026-11-05' and payload['as_of'] == as_of.isoformat()
        if system == service.COMPOSE:
            compose.append(copy.deepcopy(payload))
            if len(compose) == 1:
                return invalid
            if break_citation_after_review and len(compose) == 2:
                bad_quote = copy.deepcopy(corrected)
                bad_quote['overview']['citations'][0]['quote'] = '改稿时生成的错误摘录并不存在于来源'
                return bad_quote
            return corrected
        assert system == service.VERIFY
        reviews.append(copy.deepcopy(payload))
        return feedback if len(reviews) == 1 else {'approved': True, 'reason': '', 'issues': []}

    async def supplement(queries):
        supplements.append(queries)
        return [], 'no_results'

    async def report(**entry):
        logs.append(entry)

    monkeypatch.setattr(service, 'llm', llm)
    monkeypatch.setattr(service, 'supplement', supplement)
    result = await service.run_once(factory=database, report=report)

    assert result['created'] == 1 and result['failed'] == 0
    assert len(compose) == (3 if break_citation_after_review else 2) and len(reviews) == 2
    assert len(supplements) == 1
    assert compose[1]['previous_document'] == invalid and compose[1]['review_feedback'] == feedback
    assert all(call['sources'] == compose[0]['sources'] for call in [*compose, *reviews])
    assert reviews[0]['document'] == invalid and reviews[1]['document'] == corrected
    assert any(e['stage'] == 'repair' and e['details'].get('review_feedback') == feedback for e in logs)
    if break_citation_after_review:
        assert compose[2]['review_feedback'] == feedback
        assert compose[2]['validation_errors'][0]['code'] == 'quote_mismatch'
    async with database() as session:
        versions = (await session.scalars(select(SpecialVersion))).all()
        assert len(versions) == 1 and versions[0].document == corrected


@pytest.mark.asyncio
async def test_semantic_revision_cannot_bypass_citation_gate_or_retry_forever(database, material, monkeypatch):
    candidate, _, document = material
    invalid = copy.deepcopy(document)
    invalid['overview']['citations'][0]['quote'] = '修正后仍然伪造的证据摘录，不属于原文'
    calls = []

    async def llm(system, payload):
        if system == service.DISCOVER:
            return {'candidates': [candidate.model_dump()]}
        calls.append(system)
        if system == service.COMPOSE:
            return invalid if 'review_feedback' in payload else document
        return {'approved': False, 'reason': '结论需要收窄至来源的限定条件'}

    async def supplement(queries):
        return [], 'academic_only'

    monkeypatch.setattr(service, 'llm', llm)
    monkeypatch.setattr(service, 'supplement', supplement)
    result = await service.run_once(factory=database)
    assert result['failed'] == 1 and result['created'] == 0
    assert calls == [service.COMPOSE, service.VERIFY, service.COMPOSE, service.COMPOSE]
    async with database() as session:
        special = await session.scalar(select(Special))
        assert special.status == 'draft' and special.external_status == 'academic_only'
        assert 'quote' in special.last_error
        assert await session.scalar(select(func.count()).select_from(SpecialVersion)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('review', [
    {'approved': 'true', 'reason': ''},
    {'approved': True, 'reason': '', 'issues': [{'path': 'overview', 'reason': '仍存在无依据的共同结论'}]},
])
async def test_malformed_or_contradictory_approval_never_publishes(database, material, monkeypatch, review):
    candidate, _, document = material

    async def llm(system, payload):
        if system == service.DISCOVER:
            return {'candidates': [candidate.model_dump()]}
        return document if system == service.COMPOSE else review

    async def supplement(queries):
        return [], 'no_results'

    monkeypatch.setattr(service, 'llm', llm)
    monkeypatch.setattr(service, 'supplement', supplement)
    result = await service.run_once(factory=database)
    assert result['failed'] == 1 and result['created'] == 0
    async with database() as session:
        assert await session.scalar(select(func.count()).select_from(SpecialVersion)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('problem', [
    'comparison_citation', 'comparison_item', 'shared_evidence', 'internal_evidence',
    'timeline_evidence', 'timeline_date', 'document_kind', 'schema',
])
async def test_all_document_checks_can_be_repaired_before_independent_review(database, material, monkeypatch, problem):
    candidate, sources, document = material
    comparison = {'item_id': 2, 'object': '田间视觉模型', 'method': '跨地域评估', 'data': '田间数据',
                  'result': '跨地域存在性能差异', 'limitation': '仅一种作物',
                  'citations': copy.deepcopy(document['findings'][0]['citations'])}
    invalid, corrected = copy.deepcopy(document), copy.deepcopy(document)
    external = {'id': 'e1', 'kind': 'external', 'basis': 'abstract', 'text': '外部原始论文只用于说明方法的应用边界。'}
    if problem in {'comparison_citation', 'comparison_item'}:
        invalid['comparisons'] = [comparison]
        if problem == 'comparison_item':
            comparison['item_id'] = 999  # A row number or a fabricated item ID.
        corrected['comparisons'] = [{**comparison, 'item_id': 2,
                                     'citations': copy.deepcopy(document['findings'][1]['citations'])}]
    elif problem == 'shared_evidence':
        invalid['findings'][0]['kind'] = 'shared'
    elif problem == 'internal_evidence':
        invalid['findings'][0]['citations'] = [{'source_id': 'e1', 'quote': external['text']}]
    elif problem in {'timeline_evidence', 'timeline_date'}:
        candidate.kind = 'event'
        invalid['timeline'] = [{'date': '2001-01-01' if problem == 'timeline_evidence' else '2026-02-30',
                                'claim': copy.deepcopy(document['findings'][0])}]
        corrected['timeline'] = [{'date': sources[0]['published_at'][:10], 'claim': copy.deepcopy(document['findings'][0])}]
    elif problem == 'document_kind':
        candidate.kind = 'event'
        invalid['comparisons'] = [{**comparison, 'citations': copy.deepcopy(document['findings'][1]['citations'])}]
    else:
        invalid['findings'] = invalid['findings'][:1]
    calls, reviewed = [], []

    async def llm(system, payload):
        if system == service.DISCOVER:
            return {'candidates': [candidate.model_dump()]}
        if system == service.COMPOSE:
            calls.append(copy.deepcopy(payload))
            return invalid if len(calls) == 1 else corrected
        assert system == service.VERIFY
        reviewed.append(copy.deepcopy(payload))
        return {'approved': True, 'reason': ''}

    async def supplement(queries):
        return [external], 'academic_only'

    monkeypatch.setattr(service, 'llm', llm)
    monkeypatch.setattr(service, 'supplement', supplement)
    result = await service.run_once(factory=database)

    assert result['created'] == 1 and result['failed'] == 0
    assert len(calls) == 2 and len(reviewed) == 1
    reviewed_document = copy.deepcopy(reviewed[0]['document'])
    for row in reviewed_document['timeline']:
        for key in ('id', 'title', 'date_basis'):
            row.pop(key, None)
    assert reviewed_document == corrected
    assert calls[0]['sources'] == calls[1]['sources'] == reviewed[0]['sources']
    assert {e['code'] for e in calls[1]['validation_errors']} == {problem}
    assert calls[1]['previous_document'] == invalid
    if problem == 'comparison_citation':
        error = calls[1]['validation_errors'][0]
        assert error['path'] == 'comparisons[0].citations'
        assert error['source_id'] == 'i2' and error['actual_source_ids'] == ['i1']
    assert calls[0]['comparison_sources'] == [{'item_id': i, 'source_id': f'i{i}'} for i in range(1, 4)]
    assert calls[0]['schema']['$defs']['Comparison']['properties']['item_id']['enum'] == [1, 2, 3]
    assert calls[0]['schema']['$defs']['Citation']['properties']['source_id']['enum'] == ['i1', 'i2', 'i3', 'e1']
    async with database() as session:
        version = await session.scalar(select(SpecialVersion))
        assert version.document == reviewed[0]['document']


@pytest.mark.asyncio
async def test_comparison_repair_failure_retains_previous_version(database, material, monkeypatch):
    special_id, _ = await publish(database, material)
    candidate, _, document = material
    candidate.existing_id = special_id
    async with database() as session:
        item = await session.get(Item, 1)
        item.summary += ' 新增田间实验的验证条件。'
        await session.commit()
    invalid = copy.deepcopy(document)
    invalid['comparisons'] = [{'item_id': 2, 'object': '', 'method': '', 'data': '', 'result': '', 'limitation': '',
                               'citations': document['findings'][0]['citations']}]
    calls = []

    async def llm(system, payload):
        assert system == service.COMPOSE, 'invalid comparisons must never reach independent review'
        calls.append(payload)
        return invalid

    async def supplement(queries):
        return [], 'no_results'

    monkeypatch.setattr(service, 'llm', llm)
    monkeypatch.setattr(service, 'supplement', supplement)
    result = await service.run_once(factory=database, special_id=special_id)

    assert result['failed'] == 1 and len(calls) == 2
    async with database() as session:
        version = await session.scalar(select(SpecialVersion))
        assert version.document == document
        assert await session.scalar(select(func.count()).select_from(SpecialVersion)) == 1
        special = await session.get(Special, special_id)
        assert special.status == 'published'
        assert 'comparisons[0].citations' in special.last_error and 'i2' in special.last_error


@pytest.mark.asyncio
@pytest.mark.parametrize('existing', [False, True])
@pytest.mark.parametrize('review_rejects', [False, True])
async def test_failed_correction_or_review_keeps_published_content(database, material, monkeypatch, existing, review_rejects):
    candidate, _, document = material
    special_id = (await publish(database, material))[0] if existing else None
    if existing:
        async with database() as session:
            item = await session.get(Item, 1)
            item.summary += ' 新材料增加了田间验证条件。'
            await session.commit()
    invalid = copy.deepcopy(document)
    invalid['findings'][0]['citations'][0]['quote'] = '这个模型生成的摘录始终不在原文中'
    compose_calls, review_calls = [], []

    async def llm(system, payload):
        if system == service.DISCOVER:
            return {'candidates': [candidate.model_dump()]}
        if system == service.COMPOSE:
            compose_calls.append(payload)
            return document if review_rejects and len(compose_calls) >= 2 else invalid
        assert system == service.VERIFY and review_rejects, 'invalid citations must never reach review'
        assert payload['document'] == document
        review_calls.append(payload)
        return {'approved': False, 'reason': '修正后的结论仍超出证据'}

    async def supplement(queries):
        return [], 'no_results'

    monkeypatch.setattr(service, 'llm', llm)
    monkeypatch.setattr(service, 'supplement', supplement)
    result = await service.run_once(factory=database, special_id=special_id)

    assert result['failed'] == 1 and result['created'] == result['updated'] == 0
    assert len(compose_calls) == (3 if review_rejects else 2)
    assert len(review_calls) == 2 * int(review_rejects)
    async with database() as session:
        special = await session.scalar(select(Special))
        assert special.status == ('published' if existing else 'draft')
        assert special.external_status == 'no_results'
        if review_rejects:
            assert special.last_error == '修正后的结论仍超出证据'
        else:
            assert 'findings[0].citations[0].quote' in special.last_error
            assert 'i1' in special.last_error and '摘录与原文不符' in special.last_error
        versions = (await session.scalars(select(SpecialVersion))).all()
        assert len(versions) == int(existing)
        if existing:
            assert versions[0].document == document


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
@pytest.mark.parametrize('repeat_title', [False, True])
async def test_title_only_sources_cannot_support_claims_or_count_as_core(database, material, repeat_title):
    candidate, _, document = material
    async with database() as session:
        item = await session.get(Item, 3)
        item.summary = item.title if repeat_title else ' '
        item.summary_zh = item.title if repeat_title else None
        item.content = item.title if repeat_title else None
        await session.commit()
    sources = await service.prepare_sources(candidate, database)
    title_only = next(s for s in sources if s['item_id'] == 3)
    assert title_only['basis'] == 'title'
    diagnostics = service.eligibility_report(candidate, sources)
    assert diagnostics['eligible'] is False and diagnostics['core_count'] == diagnostics['recent_core_count'] == 2
    assert diagnostics['title_only_item_ids'] == [3]
    assert any('只有标题' in reason for reason in diagnostics['reasons'])
    document['findings'][2]['citations'][0]['quote'] = title_only['title']
    with pytest.raises(service.EvidenceValidationError) as caught:
        service.validate_evidence(document, sources)
    assert caught.value.errors == [{
        'path': 'findings[2].citations[0].source_id', 'source_id': 'i3', 'code': 'source_title_only',
        'reason': '该来源只有标题，不能支持正文结论；删除此引用及无其他证据支持的论断',
    }]


@pytest.mark.asyncio
@pytest.mark.parametrize('replacement_available', [False, True])
async def test_title_only_material_is_replaced_or_skipped_before_drafting(database, material, monkeypatch, replacement_available):
    candidate, _, document = material
    async with database() as session:
        for item_id in ([3] if replacement_available else [3, 4]):
            item = await session.get(Item, item_id)
            item.summary, item.summary_zh, item.content = '', None, None
        await session.commit()
    calls = []

    async def llm(system, payload):
        calls.append(system)
        if system == service.DISCOVER:
            articles = {a['id']: a for a in payload['articles']}
            assert articles[3]['basis'] == 'title'
            return {'candidates': [candidate.model_dump()]}
        assert replacement_available, 'a pool with only two substantive articles cannot be repaired'
        if system == service.RESELECT:
            assert payload['material_diagnostics']['title_only_item_ids'] == [3]
            return {'items': [*candidate.model_dump()['items'][:2], {
                'item_id': 4, 'role': 'core', 'reason': '独立实验提供跨地域条件证据', 'evidence_group': 'study-4',
            }]}
        if system == service.COMPOSE:
            assert {s['item_id'] for s in payload['sources']} == {1, 2, 4}
            corrected = copy.deepcopy(document)
            corrected['findings'][2]['citations'][0]['source_id'] = 'i4'
            return corrected
        assert system == service.VERIFY
        return {'approved': True, 'reason': ''}

    async def supplement(queries):
        assert replacement_available
        return [], 'no_results'

    monkeypatch.setattr(service, 'llm', llm)
    monkeypatch.setattr(service, 'supplement', supplement)
    result = await service.run_once(factory=database)
    assert result['failed'] == 0 and result['created'] == int(replacement_available)
    assert result['skipped'] == int(not replacement_available)
    assert calls == [service.DISCOVER] + ([service.RESELECT, service.COMPOSE, service.VERIFY] if replacement_available else [])
    async with database() as session:
        assert await session.scalar(select(func.count()).select_from(Special)) == int(replacement_available)


@pytest.mark.asyncio
@pytest.mark.parametrize('dry_run', [False, True])
@pytest.mark.parametrize('shortage', ['background', 'same_doi', 'missing_date', 'no_fresh', 'event_window', 'missing_item'])
async def test_ineligible_selections_are_skipped_with_specific_diagnostics_before_generation(database, material, monkeypatch, dry_run, shortage):
    candidate, _, _ = material
    if shortage == 'background':
        candidate.items[2].role = 'background'
    if shortage == 'event_window':
        candidate.kind = 'event'
    async with database() as session:
        for i in range(1, 4):
            item = await session.get(Item, i)
            if shortage == 'same_doi':
                item.category = '报道'
                item.summary += ' 原始论文：https://doi.org/10.1234/one-result'
            elif shortage == 'missing_date' and i == 1:
                item.published_at = None
            elif shortage == 'no_fresh':
                item.published_at = utcnow() - timedelta(days=8 + i)
            elif shortage == 'event_window':
                item.published_at = utcnow() - timedelta(days=20 + i)
        await session.commit()
    logs = []

    async def report(**entry):
        logs.append(entry)

    async def llm(system, payload):
        if system == service.RESELECT:
            return {'items': [i.model_dump() for i in candidate.items]}
        assert system == service.DISCOVER, 'insufficient evidence must not reach composition'
        articles = {a['id']: a for a in payload['articles']}
        if shortage == 'missing_date':
            assert articles[1]['eligibility'] == {'event_core': False, 'research_core': False, 'fresh': False}
        elif shortage == 'event_window':
            assert articles[1]['eligibility'] == {'event_core': False, 'research_core': True, 'fresh': False}
        elif shortage == 'same_doi':
            assert {articles[i]['primary_doi'] for i in range(1, 4)} == {'10.1234/one-result'}
        if shortage == 'missing_item':
            async with database() as session:
                await session.delete(await session.get(Item, 3))
                await session.commit()
        return {'candidates': [candidate.model_dump()]}

    async def forbidden(*args):
        pytest.fail('insufficient selections must not use external services')

    monkeypatch.setattr(service, 'llm', llm)
    monkeypatch.setattr(service, 'supplement', forbidden)
    result = await service.run_once(factory=database, dry_run=dry_run, report=report)

    assert result['skipped'] == 1 and result['failed'] == result['created'] == result['updated'] == 0
    entry = next(e for e in logs if e['stage'] == 'eligibility' and e['level'] == 'warning')
    details = entry['details']
    assert details['title'] == candidate.title and details['eligible'] is False and details['reasons']
    assert '材料不足：' in entry['message']
    assert all('published_at' in a and 'evidence_group' in a for a in details['articles'])
    if shortage == 'background':
        assert details['core_count'] == details['recent_core_count'] == 2
        assert '核心文章 2/3' in entry['message']
    elif shortage == 'same_doi':
        assert details['independent_groups'] == 1
        assert len({a['evidence_group'] for a in details['articles']}) == 1
        assert '独立证据 1/2' in entry['message']
    elif shortage == 'missing_date':
        assert details['recent_core_count'] == 2 and '无日期' in entry['message']
    elif shortage == 'no_fresh':
        assert details['recent_core_count'] == 3 and details['fresh_core_count'] == 0
        assert '近7天发表的核心文章 0/1' in entry['message']
    elif shortage == 'event_window':
        assert details['window_days'] == 14 and details['recent_core_count'] == 0
        assert '近14天发表的核心文章 0/3' in entry['message']
    else:
        assert details['missing_item_ids'] == [3]
    async with database() as session:
        assert await session.scalar(select(func.count()).select_from(Special)) == 0
        assert await session.scalar(select(func.count()).select_from(SpecialVersion)) == 0


@pytest.mark.asyncio
async def test_future_dates_are_background_and_do_not_supply_recent_evidence(material):
    candidate, sources, _ = material
    sources[0]['published_at'] = (utcnow() + timedelta(days=1)).isoformat()
    result = service.eligibility_report(candidate, sources)
    assert result['eligible'] is False and result['recent_core_count'] == 2
    article = result['articles'][0]
    assert article['event_core'] is article['research_core'] is article['fresh'] is False


@pytest.mark.asyncio
async def test_insufficient_existing_special_keeps_publication_and_records_reason(database, material, monkeypatch):
    special_id, _ = await publish(database, material)
    async with database() as session:
        for i in range(1, 4):
            item = await session.get(Item, i)
            item.published_at = utcnow() - timedelta(days=8 + i)
        await session.commit()

    async def forbidden(*args):
        pytest.fail('material preflight must happen before generation')

    async def reselect(system, payload):
        assert system == service.RESELECT
        return {'items': []}

    monkeypatch.setattr(service, 'llm', reselect)
    monkeypatch.setattr(service, 'supplement', forbidden)
    result = await service.run_once(factory=database, special_id=special_id)

    assert result['skipped'] == 1 and result['failed'] == result['updated'] == 0
    async with database() as session:
        special = await session.get(Special, special_id)
        assert special.status == 'published' and '近7天发表的核心文章 0/1' in special.last_error
        assert await session.scalar(select(func.count()).select_from(SpecialVersion)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('dry_run', [False, True])
@pytest.mark.parametrize('shortage', ['background', 'missing_date', 'no_fresh', 'same_doi'])
async def test_insufficient_core_selection_is_repaired_before_generation(database, material, monkeypatch, dry_run, shortage):
    candidate, _, document = material
    proposed = candidate.model_dump()
    if shortage == 'background':
        proposed['items'][2]['role'] = 'background'
    async with database() as session:
        for item_id in range(1, 4):
            item = await session.get(Item, item_id)
            if shortage == 'missing_date' and item_id == 1:
                item.published_at = None
            elif shortage == 'no_fresh':
                item.published_at = utcnow() - timedelta(days=10 + item_id)
            elif shortage == 'same_doi':
                item.category = '报道'
                item.summary += ' 原始论文：https://doi.org/10.1234/one-result'
        await session.commit()
    selected = copy.deepcopy(proposed['items'])
    if shortage == 'missing_date':
        selected[0]['role'] = 'background'
    selected.append({**candidate.items[0].model_dump(), 'item_id': 4, 'evidence_group': 'study-4'})
    calls, logs = [], []

    async def report(**entry):
        logs.append(entry)

    async def llm(system, payload):
        calls.append(system)
        if system == service.DISCOVER:
            items = payload['schema']['$defs']['DiscoveryCandidate']['properties']['items']
            assert items['minContains'] == 3 and items['contains']['properties']['role']['const'] == 'core'
            assert payload['limits']['min_core_items'] == 3
            return {'candidates': [proposed]}
        if system == service.RESELECT:
            assert payload['previous_candidate']['scope'] == candidate.scope
            assert payload['material_diagnostics']['eligible'] is False
            assert 4 in {a['id'] for a in payload['articles']}, 'Offer unselected site articles to fill the gap'
            return {'items': selected}
        assert not dry_run
        if system == service.COMPOSE:
            sources = {s['item_id']: s for s in payload['sources']}
            assert set(sources) == {1, 2, 3, 4}
            if shortage in {'background', 'missing_date'}:
                assert sum(s['role'] == 'core' for s in sources.values()) == 3
            if shortage == 'same_doi':
                assert len({s['evidence_group'] for s in sources.values()}) == 2
            return document
        assert system == service.VERIFY
        return {'approved': True, 'reason': ''}

    async def supplement(queries):
        assert not dry_run
        return [], 'no_results'

    monkeypatch.setattr(service, 'llm', llm)
    monkeypatch.setattr(service, 'supplement', supplement)
    result = await service.run_once(factory=database, dry_run=dry_run, report=report)
    assert result['skipped'] == result['failed'] == 0
    assert calls == [service.DISCOVER, service.RESELECT] + ([] if dry_run else [service.COMPOSE, service.VERIFY])
    assert any(entry['stage'] == 'reselect' and '检查通过' in entry['message'] for entry in logs)
    if dry_run:
        assert len(result['candidates']) == 1 and len(result['candidates'][0]['items']) == 4
    else:
        assert result['created'] == 1
    async with database() as session:
        assert await session.scalar(select(func.count()).select_from(SpecialVersion)) == int(not dry_run)
        assert await session.scalar(select(func.count()).select_from(Special)) == int(not dry_run)


@pytest.mark.asyncio
@pytest.mark.parametrize('repair_result', ['empty', 'still_insufficient', 'unknown_id', 'duplicate', 'overflow', 'invalid', 'error', 'truncated'])
async def test_unsuccessful_material_reselection_is_bounded_and_does_not_block_other_topics(database, material, monkeypatch, repair_result):
    candidate, _, document = material
    insufficient = candidate.model_dump()
    insufficient['title'] = '需要补选材料的独立选题'
    insufficient['scope'] += '侧重另一项具体应用条件。'
    insufficient['items'][2]['role'] = 'background'
    calls, logs = [], []

    async def report(**entry):
        logs.append(entry)

    async def llm(system, payload):
        calls.append(system)
        if system == service.DISCOVER:
            return {'candidates': [insufficient, candidate.model_dump()]}
        if system == service.RESELECT:
            if repair_result == 'error':
                raise service.ModelRequestError('DeepSeek 服务繁忙（HTTP 503）')
            if repair_result == 'truncated':
                raise service.ModelOutputLimitError('补选输出被截断')
            if repair_result == 'invalid':
                return {'items': 'invalid'}
            selected = copy.deepcopy(insufficient['items'])
            if repair_result == 'empty':
                selected = []
            elif repair_result == 'unknown_id':
                selected[2].update(item_id=99999, role='core')
            elif repair_result == 'duplicate':
                selected[2] = selected[0]
            elif repair_result == 'overflow':
                selected = [{**selected[0], 'item_id': i} for i in range(1, 8)]
            return {'items': selected}
        assert payload['title'] == candidate.title, 'Only the valid candidate may reach composition or review'
        return document if system == service.COMPOSE else {'approved': True, 'reason': ''}

    async def supplement(queries):
        return [], 'no_results'

    monkeypatch.setattr(service, 'llm', llm)
    monkeypatch.setattr(service, 'supplement', supplement)
    result = await service.run_once(factory=database, report=report)
    assert result['skipped'] == result['created'] == 1 and result['failed'] == 0
    assert calls.count(service.RESELECT) == 1 and calls.count(service.COMPOSE) == 1
    assert any(entry['stage'] == 'eligibility' and '材料不足' in entry['message'] for entry in logs)
    async with database() as session:
        special, = (await session.scalars(select(Special))).all()
        assert special.title == candidate.title and special.status == 'published'
        assert await session.scalar(select(func.count()).select_from(SpecialVersion)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('items_locked', [False, True])
async def test_existing_special_reselection_preserves_history_scope_groups_and_manual_locks(database, material, monkeypatch, items_locked):
    from app.models import SpecialItem

    candidate, sources, document = material
    candidate.scope *= 6  # Existing/manual scopes may exceed discovery's shorter output limits.
    candidate.items.append(candidate.items[0].model_copy(update={'item_id': 4, 'role': 'background', 'evidence_group': 'study-4'}))
    sources = await service.prepare_sources(candidate, database)
    special_id, _ = await service.publish(candidate, document, sources, service.input_hash(candidate, sources), database)
    async with database() as session:
        link = await session.scalar(select(SpecialItem).where(SpecialItem.special_id == special_id, SpecialItem.item_id == 3))
        link.role = 'background'
        item = await session.get(Item, 1)
        item.summary += ' 新增跨地域验证条件。'
        special = await session.get(Special, special_id)
        special.locked_fields = ['items'] if items_locked else []
        await session.commit()
    calls = []

    async def llm(system, payload):
        calls.append(system)
        if system == service.RESELECT:
            assert not items_locked
            assert payload['previous_candidate']['scope'] == candidate.scope
            return {'items': [i.model_dump() for i in candidate.items[:3]]}
        assert payload['scope'] == candidate.scope
        by_id = {s['item_id']: s for s in payload['sources']}
        assert set(by_id) == {1, 2, 3, 4} and by_id[4]['role'] == 'background'
        assert by_id[3]['role'] == 'core'
        assert {i: s['evidence_group'] for i, s in by_id.items()} == {s['item_id']: s['evidence_group'] for s in sources}
        return document if system == service.COMPOSE else {'approved': True, 'reason': ''}

    async def supplement(queries):
        return [], 'no_results'

    monkeypatch.setattr(service, 'llm', llm)
    monkeypatch.setattr(service, 'supplement', supplement)
    result = await service.run_once(factory=database, special_id=special_id)
    assert result['failed'] == 0 and result['updated'] == int(not items_locked)
    assert calls == ([] if items_locked else [service.RESELECT, service.COMPOSE, service.VERIFY])
    async with database() as session:
        special = await session.get(Special, special_id)
        assert special.status == 'published' and special.scope == candidate.scope
        assert await session.scalar(select(func.count()).select_from(SpecialVersion)) == (1 if items_locked else 2)


@pytest.mark.asyncio
async def test_material_reselection_cannot_create_a_duplicate_existing_topic(database, material, monkeypatch):
    from app.models import SpecialItem

    candidate, _, _ = material
    proposed = candidate.model_dump()
    proposed['items'][2]['role'] = 'background'
    async with database() as session:
        for item_id in (5, 6):
            session.add(Item(id=item_id, title=f'相关独立研究{item_id}', url=f'https://research.example/{item_id}',
                             url_hash=str(item_id), title_simhash=item_id, summary='跨地域测试存在性能差异，仍需更多验证。',
                             published_at=utcnow() - timedelta(days=1), category='论文', source_name='研究机构'))
        existing = Special(kind='research', title='已存在的相关研究专题', scope=candidate.scope + '关注既有研究条件。')
        session.add(existing)
        await session.flush()
        for item_id in (4, 5, 6):
            session.add(SpecialItem(special_id=existing.id, item_id=item_id, role='core',
                                    reason='已有议题的核心研究材料', evidence_group=f'study-{item_id}'))
        await session.commit()
    calls, logs = [], []

    async def report(**entry):
        logs.append(entry)

    async def llm(system, payload):
        calls.append(system)
        if system == service.DISCOVER:
            return {'candidates': [proposed]}
        assert system == service.RESELECT, 'A duplicate must be rejected before composition'
        return {'items': [{**candidate.items[0].model_dump(), 'item_id': item_id, 'evidence_group': f'study-{item_id}'}
                          for item_id in (1, 2, 4, 5)]}

    monkeypatch.setattr(service, 'llm', llm)
    result = await service.run_once(factory=database, report=report)
    assert result['skipped'] == 1 and result['created'] == result['failed'] == 0
    assert calls == [service.DISCOVER, service.RESELECT]
    assert any(entry['stage'] == 'skip' and '重叠' in entry['message'] for entry in logs)
    async with database() as session:
        assert await session.scalar(select(func.count()).select_from(Special)) == 1
        assert await session.scalar(select(func.count()).select_from(SpecialVersion)) == 0


@pytest.mark.asyncio
async def test_globally_missing_publication_dates_do_not_trigger_material_reselection(database, material, monkeypatch):
    candidate, _, _ = material
    async with database() as session:
        for item in (await session.scalars(select(Item))).all():
            item.published_at = None
        await session.commit()
    calls = []

    async def llm(system, payload):
        calls.append(system)
        assert system == service.DISCOVER
        return {'candidates': [candidate.model_dump()]}

    monkeypatch.setattr(service, 'llm', llm)
    result = await service.run_once(factory=database)
    assert result['skipped'] == 1 and result['created'] == result['failed'] == 0
    assert calls == [service.DISCOVER]
    async with database() as session:
        assert await session.scalar(select(func.count()).select_from(Special)) == 0


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
@pytest.mark.parametrize('overflow', ['candidates', 'items', 'reason', 'scope', 'queries', 'extra'])
async def test_discovery_rejects_oversized_output_before_creating_drafts(database, material, monkeypatch, overflow):
    candidate, _, _ = material
    proposed = candidate.model_dump()
    if overflow == 'items':
        proposed['items'] = [{**proposed['items'][0], 'item_id': i} for i in range(1, 8)]
    elif overflow == 'reason':
        proposed['items'][0]['reason'] = '长' * 41
    elif overflow == 'scope':
        proposed['scope'] = '长' * 121
    elif overflow == 'queries':
        proposed['queries'] = ['检索一', '检索二']
    elif overflow == 'extra':
        proposed['analysis'] = '选题阶段不应输出长篇综合分析。'

    async def llm(system, payload):
        assert system == service.DISCOVER, 'oversized selections must not reach composition'
        return {'candidates': [proposed] * (4 if overflow == 'candidates' else 1)}

    monkeypatch.setattr(service, 'llm', llm)
    if overflow == 'candidates':
        with pytest.raises(ValueError):
            await service.run_once(factory=database)
    else:
        result = await service.run_once(factory=database)
        assert result['skipped'] == 1 and result['failed'] == result['created'] == 0
    async with database() as session:
        assert await session.scalar(select(func.count()).select_from(Special)) == 0
        assert await session.scalar(select(func.count()).select_from(SpecialVersion)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('problem', ['two_articles', 'empty_articles', 'missing_articles', 'duplicate_articles', 'bad_role', 'long_reason', 'not_an_object'])
async def test_invalid_proposal_does_not_discard_other_valid_topics(database, material, monkeypatch, problem):
    candidate, _, document = material
    invalid = candidate.model_dump()
    invalid['title'] = '这是一条应当跳过的无效候选'
    if problem == 'two_articles':
        invalid['items'] = [{**invalid['items'][0], 'item_id': 6514}, {**invalid['items'][1], 'item_id': 6436}]
    elif problem == 'empty_articles':
        invalid['items'] = []
    elif problem == 'missing_articles':
        del invalid['items']
    elif problem == 'duplicate_articles':
        invalid['items'][1]['item_id'] = invalid['items'][0]['item_id']
    elif problem == 'bad_role':
        invalid['items'][0]['role'] = 'unsupported'
    elif problem == 'long_reason':
        invalid['items'][0]['reason'] = '长' * 41
    else:
        invalid = None
    logs, reviewed = [], []

    async def report(**entry):
        logs.append(entry)

    async def llm(system, payload):
        if system == service.DISCOVER:
            assert payload['schema']['$defs']['DiscoveryCandidate']['properties']['items']['minItems'] == 3
            return {'candidates': [invalid, candidate.model_dump()]}
        if system == service.COMPOSE:
            assert payload['title'] == candidate.title
            return document
        assert system == service.VERIFY
        reviewed.append(payload)
        return {'approved': True, 'reason': ''}

    async def supplement(queries):
        return [], 'no_results'

    monkeypatch.setattr(service, 'llm', llm)
    monkeypatch.setattr(service, 'supplement', supplement)
    result = await service.run_once(factory=database, report=report)

    assert result['created'] == result['skipped'] == 1 and result['failed'] == 0
    assert len(reviewed) == 1
    warning = next(e for e in logs if e['level'] == 'warning')
    assert '已跳过' in warning['message']
    if problem == 'two_articles':
        assert '2/3' in warning['message'] and warning['details']['item_ids'] == [6514, 6436]
    async with database() as session:
        special = await session.scalar(select(Special))
        assert special.title == candidate.title and special.status == 'published'
        assert await session.scalar(select(func.count()).select_from(Special)) == 1
        assert await session.scalar(select(func.count()).select_from(SpecialVersion)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('dry_run', [False, True])
async def test_two_article_selection_finishes_as_skip_and_keeps_admin_diagnostics(database, material, client, monkeypatch, dry_run):
    from app.services import job_runner

    candidate, _, _ = material
    proposed = candidate.model_dump()
    proposed['items'] = proposed['items'][:2]
    calls = []

    async def llm(system, payload):
        assert system == service.DISCOVER, 'an insufficient proposal must never reach composition or review'
        calls.append(payload)
        return {'candidates': [proposed]}

    async def forbidden(*args):
        pytest.fail('an insufficient proposal must not use external services')

    monkeypatch.setattr(service, 'llm', llm)
    monkeypatch.setattr(service, 'supplement', forbidden)
    monkeypatch.setattr(service, 'SessionLocal', database)
    monkeypatch.setattr(job_runner, 'SessionLocal', database)
    result = await job_runner.run('specials_generate', {'dry_run': dry_run})

    assert result['status'] == 'ok' and result['error'] is None
    assert result['stats']['skipped'] == 1 and result['stats']['failed'] == result['stats']['created'] == 0
    assert len(calls) == 1
    headers = {'X-Admin-Token': issue_admin_token()}
    jobs = (await client.get('/api/v1/admin/jobs', headers=headers)).json()['jobs']
    job = next(j for j in jobs if j['name'] == 'specials_generate')
    assert job['status'] == 'ok' and job['stats']['skipped'] == 1
    warning = next(e for e in job['logs'] if e['level'] == 'warning')
    assert '2/3' in warning['message'] and warning['details']['required_articles'] == 3
    async with database() as session:
        assert await session.scalar(select(func.count()).select_from(Special)) == 0
        assert await session.scalar(select(func.count()).select_from(SpecialVersion)) == 0


@pytest.mark.asyncio
async def test_discovery_applies_runtime_quota_to_prompt_schema_and_validation(database, material, monkeypatch):
    from app.services import runtime_settings

    candidate, _, _ = material
    async with database() as session:
        await runtime_settings.patch(session, {'specials_max_new': 1})
        await session.commit()
        await runtime_settings.load(session)

    async def llm(system, payload):
        assert system == service.DISCOVER
        assert payload['existing'] == []
        assert payload['limits']['max_candidates'] == payload['limits']['max_new'] == 1
        assert payload['limits']['max_updates'] == 0
        assert payload['schema']['properties']['candidates']['maxItems'] == 1
        return {'candidates': [candidate.model_dump(), candidate.model_dump()]}

    monkeypatch.setattr(service, 'llm', llm)
    with pytest.raises(ValueError, match='输出预算'):
        await service.run_once(factory=database)
    async with database() as session:
        assert await session.scalar(select(func.count()).select_from(Special)) == 0


@pytest.mark.asyncio
async def test_discovery_truncation_retries_smaller_and_publishes_only_complete_output(database, material, monkeypatch):
    import httpx
    from app.services import job_runner

    candidate, _, document = material
    calls = {'discover': [], 'compose': [], 'verify': []}

    async def handler(request):
        body = json.loads(request.content)
        assert body['max_tokens'] == 8192
        system = body['messages'][0]['content']
        payload = json.loads(body['messages'][1]['content'])
        if system.startswith(service.DISCOVER):
            stage = 'discover'
            truncated = not calls[stage]
            result = {'candidates': [candidate.model_dump()]}
        elif system.startswith(service.COMPOSE):
            stage, truncated, result = 'compose', False, document
        else:
            assert system.startswith(service.VERIFY)
            stage, truncated, result = 'verify', False, {'approved': True, 'reason': ''}
        calls[stage].append(payload)
        return httpx.Response(200, json={
            'choices': [{'finish_reason': 'length' if truncated else 'stop', 'message': {
                'content': '{"candidates":[{"title":"不完整的选题' if truncated else json.dumps(result, ensure_ascii=False),
            }}],
            'usage': {'prompt_tokens': 1000, 'completion_tokens': 8192 if truncated else 200},
        })

    real_client = httpx.AsyncClient
    monkeypatch.setattr(service.httpx, 'AsyncClient', lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setattr(settings, 'deepseek_api_key', 'test-output-budget')
    monkeypatch.setattr(job_runner, 'SessionLocal', database)
    monkeypatch.setattr(service, 'SessionLocal', database)

    async def supplement(queries):
        return [], 'no_results'

    monkeypatch.setattr(service, 'supplement', supplement)
    result = await job_runner.run('specials_generate')

    assert result['status'] == 'ok' and result['stats']['created'] == 1 and result['stats']['failed'] == 0
    assert len(calls['discover']) == 2 and len(calls['compose']) == len(calls['verify']) == 1
    first, retry = calls['discover']
    assert first['limits']['max_candidates'] == 3 and first['limits']['max_items_per_candidate'] == 6
    assert retry['limits']['max_candidates'] == 1 and retry['limits']['max_items_per_candidate'] == 4
    assert retry['schema']['properties']['candidates']['maxItems'] == 1
    assert retry['schema']['$defs']['DiscoveryCandidate']['properties']['items']['maxItems'] == 4
    assert retry['articles'] == first['articles'] and retry['existing'] == first['existing']
    assert any(e['level'] == 'warning' and '重试' in e['message'] for e in result['logs'])
    async with database() as session:
        specials = (await session.scalars(select(Special))).all()
        assert len(specials) == 1 and specials[0].title == candidate.title
        versions = (await session.scalars(select(SpecialVersion))).all()
        assert len(versions) == 1 and versions[0].document == document


@pytest.mark.asyncio
async def test_manual_regeneration_keeps_larger_existing_material(database, material, monkeypatch):
    candidate, _, document = material
    async with database() as session:
        for i in range(5, 9):
            session.add(Item(id=i, title=f'跨地域田间模型的独立研究{i}', url=f'https://research.example/{i}', url_hash=str(i),
                             title_simhash=i, summary='跨地域测试存在性能差异，仍需更多验证。', source_name=f'机构{i}',
                             published_at=utcnow() - timedelta(days=1), category='论文', score=80))
        await session.commit()
    candidate.items.extend(candidate.items[0].model_copy(update={'item_id': i, 'evidence_group': f'study-{i}'}) for i in range(4, 9))
    candidate.scope = '比较田间视觉模型跨地域应用中的数据条件与适用边界。' * 6
    sources = await service.prepare_sources(candidate, database)
    special_id, _ = await service.publish(candidate, document, sources, service.input_hash(candidate, sources), database)
    async with database() as session:
        item = await session.get(Item, 1)
        item.summary += ' 新增田间实验的验证条件。'
        await session.commit()

    async def llm(system, payload):
        assert system != service.DISCOVER
        assert len(payload['sources']) == 8 and payload['scope'] == candidate.scope
        return document if system == service.COMPOSE else {'approved': True, 'reason': ''}

    async def supplement(queries):
        return [], 'no_results'

    monkeypatch.setattr(service, 'llm', llm)
    monkeypatch.setattr(service, 'supplement', supplement)
    result = await service.run_once(factory=database, special_id=special_id)
    assert result['updated'] == 1 and result['failed'] == 0
    async with database() as session:
        latest = await session.scalar(select(SpecialVersion).order_by(SpecialVersion.id.desc()).limit(1))
        assert len(latest.signatures) == 8


@pytest.mark.asyncio
@pytest.mark.parametrize('selected_count', [2, 3])
async def test_short_discovery_response_preserves_history_and_evidence_groups(database, material, monkeypatch, selected_count):
    candidate, _, document = material
    async with database() as session:
        for i in range(5, 10):
            session.add(Item(id=i, title=f'跨地域田间模型的独立研究{i}', url=f'https://research.example/{i}', url_hash=str(i),
                             title_simhash=i, summary='跨地域测试存在性能差异，仍需更多验证。', source_name=f'机构{i}',
                             published_at=utcnow() - timedelta(days=1), category='论文', score=80))
        await session.commit()
    candidate.items.extend(candidate.items[0].model_copy(update={'item_id': i, 'evidence_group': f'study-{i}'}) for i in range(4, 9))
    sources = await service.prepare_sources(candidate, database)
    special_id, _ = await service.publish(candidate, document, sources, service.input_hash(candidate, sources), database)
    proposed = candidate.model_dump()
    proposed['existing_id'] = special_id
    proposed['items'] = [
        {**candidate.items[0].model_dump(), 'item_id': 1, 'evidence_group': 'same-study'},
        {**candidate.items[1].model_dump(), 'item_id': 2, 'evidence_group': 'other-study'},
        {**candidate.items[0].model_dump(), 'item_id': 9, 'evidence_group': 'same-study'},
    ]
    if selected_count == 2:
        proposed['items'].pop(1)

    async def llm(system, payload):
        if system == service.DISCOVER:
            return {'candidates': [proposed]}
        by_id = {s['item_id']: s for s in payload['sources']}
        assert set(by_id) == set(range(1, 10)), 'a short selection must retain all eight existing sources'
        assert by_id[1]['evidence_group'] == by_id[9]['evidence_group']
        assert len({s['evidence_group'] for s in by_id.values()}) == 8
        return document if system == service.COMPOSE else {'approved': True, 'reason': ''}

    async def supplement(queries):
        return [], 'no_results'

    monkeypatch.setattr(service, 'llm', llm)
    monkeypatch.setattr(service, 'supplement', supplement)
    result = await service.run_once(factory=database)
    assert result['updated'] == 1 and result['failed'] == 0
    async with database() as session:
        latest = await session.scalar(select(SpecialVersion).order_by(SpecialVersion.id.desc()).limit(1))
        assert len(latest.signatures) == 9


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
async def test_special_job_loads_runtime_settings_and_publishes(database, material, monkeypatch):
    from app.services import job_runner, runtime_settings

    candidate, _, document = material
    async with database() as session:
        await runtime_settings.patch(session, {'specials_max_new': 1})
        await session.commit()
    runtime_settings.reset()
    monkeypatch.setattr(job_runner, 'SessionLocal', database)
    monkeypatch.setattr(service, 'SessionLocal', database)

    async def llm(system, payload):
        if system == service.DISCOVER:
            assert runtime_settings.get('specials_max_new') == 1
            return {'candidates': [candidate.model_dump()]}
        if system == service.COMPOSE:
            return document
        assert system == service.VERIFY
        return {'approved': True, 'reason': ''}

    async def supplement(queries):
        return [], 'no_results'

    monkeypatch.setattr(service, 'llm', llm)
    monkeypatch.setattr(service, 'supplement', supplement)

    result = await job_runner.run('specials_generate')

    assert result['status'] == 'ok', result['error']
    assert result['stats']['created'] == 1
    async with database() as session:
        published = await service.public_specials(session)
        assert len(published) == 1
        assert published[0][0].title == candidate.title


@pytest.mark.asyncio
@pytest.mark.parametrize('failure_stage', ['discover', 'compose', 'repair', 'verify'])
async def test_special_job_recovers_from_model_overload(database, material, client, monkeypatch, model_requests, failure_stage):
    import httpx
    from app.services import job_runner

    candidate, _, document = material
    invalid = copy.deepcopy(document)
    invalid['overview']['citations'][0]['quote'] = '不存在于原文的摘录，需要修正'
    phases = [('discover', {'candidates': [candidate.model_dump()]}),
              ('compose', invalid if failure_stage == 'repair' else document)]
    if failure_stage == 'repair':
        phases.append(('repair', document))
    phases.append(('verify', {'approved': True, 'reason': ''}))
    for stage, output in phases:
        if stage == failure_stage:
            model_requests.responses.append(httpx.Response(503, text='provider-error-body-must-not-be-logged'))
        model_requests.responses.append(httpx.Response(200, json={
            'id': f'request-{stage}',
            'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(output)}}],
        }))
    monkeypatch.setattr(job_runner, 'SessionLocal', database)
    monkeypatch.setattr(service, 'SessionLocal', database)

    async def supplement(queries):
        return [], 'no_results'

    monkeypatch.setattr(service, 'supplement', supplement)
    result = await job_runner.run('specials_generate')
    assert result['status'] == 'ok' and result['stats']['created'] == 1 and result['stats']['failed'] == 0
    assert model_requests.waits == [2]
    assert len(model_requests.requests) == len(phases) + 1
    index = next(i for i, (stage, _) in enumerate(phases) if stage == failure_stage)
    assert model_requests.requests[index] == model_requests.requests[index + 1], 'Retry the same stage and payload'
    warning, = [entry for entry in result['logs'] if entry['level'] == 'warning' and '自动重试' in entry['message']]
    assert warning['stage'] == failure_stage and 'HTTP 503' in warning['message']
    assert warning['details']['attempt'] == 1 and warning['details']['next_attempt'] == 2
    assert warning['details']['retry_delay_seconds'] == 2
    recovered = next(entry for entry in result['logs'] if entry['details'] and entry['details'].get('request_id') == f'request-{failure_stage}')
    assert recovered['details']['attempt'] == 2
    headers = {'X-Admin-Token': issue_admin_token()}
    jobs = (await client.get('/api/v1/admin/jobs', headers=headers)).json()['jobs']
    job = next(job for job in jobs if job['name'] == 'specials_generate')
    assert any(entry['message'] == warning['message'] for entry in job['logs'])
    assert 'retry-secret-not-for-logs' not in json.dumps(job)
    assert 'provider-error-body-must-not-be-logged' not in json.dumps(job)
    assert service._reporter.get() is None
    async with database() as session:
        assert await session.scalar(select(func.count()).select_from(SpecialVersion)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('failure_stage', ['discover', 'verify'])
async def test_model_overload_stops_after_bounded_retries_and_retains_version(database, material, monkeypatch, model_requests, failure_stage):
    import httpx
    from app.services import job_runner

    special_id, _ = await publish(database, material)
    if failure_stage == 'verify':
        async with database() as session:
            item = await session.get(Item, 1)
            item.summary += ' 新增验证条件。'
            await session.commit()
        model_requests.responses.append(httpx.Response(200, json={
            'choices': [{'message': {'content': json.dumps(material[2])}}],
        }))
    model_requests.responses.extend(httpx.Response(503) for _ in range(3))
    monkeypatch.setattr(job_runner, 'SessionLocal', database)
    monkeypatch.setattr(service, 'SessionLocal', database)

    async def supplement(queries):
        return [], 'no_results'

    monkeypatch.setattr(service, 'supplement', supplement)
    result = await job_runner.run('specials_generate', {'special_id': special_id} if failure_stage == 'verify' else {})
    assert model_requests.waits == [2, 4]
    assert len(model_requests.requests) == (4 if failure_stage == 'verify' else 3)
    error, = [entry for entry in result['logs'] if entry['stage'] == failure_stage and entry['level'] == 'error']
    assert '服务繁忙' in error['message'] and 'HTTP 503' in error['message'] and '已尝试 3 次' in error['message']
    assert error['details']['attempt'] == error['details']['max_attempts'] == 3
    if failure_stage == 'discover':
        assert result['status'] == 'error' and result['error'] == error['message']
    else:
        assert result['stats']['failed'] == 1 and result['stats']['updated'] == 0
    async with database() as session:
        row = await session.get(Special, special_id)
        assert row.status == 'published'
        assert await session.scalar(select(func.count()).select_from(SpecialVersion)) == 1
        if failure_stage == 'verify':
            assert row.last_error == error['message']


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [400, 401, 402, 403, 422])
async def test_model_configuration_errors_are_not_retried(model_requests, status):
    import httpx

    model_requests.responses.append(httpx.Response(status, text='private-provider-body'))
    with pytest.raises(service.ModelRequestError, match=f'HTTP {status}') as error:
        await service.llm(service.DISCOVER, {})
    assert len(model_requests.requests) == 1 and model_requests.waits == []
    assert 'private-provider-body' not in str(error.value)
    assert 'retry-secret-not-for-logs' not in str(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', [408, 429, 500, 502, 504, 'ReadTimeout', 'ConnectError', 'ReadError', 'RemoteProtocolError'])
async def test_model_transient_failures_retry_the_same_request(model_requests, failure):
    import httpx

    model_requests.responses.append(httpx.Response(failure) if isinstance(failure, int) else getattr(httpx, failure)('private-error-details'))
    model_requests.responses.append(httpx.Response(200, json={'choices': [{'message': {'content': '{"candidates": []}'}}]}))
    assert await service.llm(service.DISCOVER, {'articles': []}) == {'candidates': []}
    assert model_requests.waits == [2]
    assert len(model_requests.requests) == 2 and model_requests.requests[0] == model_requests.requests[1]


@pytest.mark.asyncio
@pytest.mark.parametrize(('header', 'delay'), [
    ('7', 7), ('Tue, 03 Nov 2026 09:02:16 GMT', 12),
    ('invalid', 2), ('-5', 2), ('nan', 2), ('inf', 2), ('0', 2),
    ('61', None), ('7200', None),
])
async def test_model_retry_respects_provider_delay_without_unbounded_waits(model_requests, monkeypatch, header, delay):
    import httpx

    monkeypatch.setattr(service.time, 'time', lambda: datetime.fromisoformat('2026-11-03T09:02:04+00:00').timestamp())
    model_requests.responses.append(httpx.Response(503, headers={'Retry-After': header}))
    model_requests.responses.append(httpx.Response(200, json={'choices': [{'message': {'content': '{}'}}]}))
    if delay is None:
        with pytest.raises(service.ModelRequestError, match='服务端要求等待较长时间'):
            await service.llm(service.DISCOVER, {})
        assert len(model_requests.requests) == 1 and model_requests.waits == []
    else:
        assert await service.llm(service.DISCOVER, {}) == {}
        assert len(model_requests.requests) == 2 and model_requests.waits == [delay]


@pytest.mark.asyncio
async def test_model_invalid_response_is_not_retried(model_requests):
    import httpx

    model_requests.responses.append(httpx.Response(200, text='private-invalid-response'))
    with pytest.raises(service.ModelRequestError, match='不是有效 JSON'):
        await service.llm(service.DISCOVER, {})
    assert len(model_requests.requests) == 1 and model_requests.waits == []


@pytest.mark.asyncio
async def test_model_retry_does_not_swallow_cancellation(model_requests, monkeypatch):
    import asyncio
    import httpx

    async def cancelled(delay):
        raise asyncio.CancelledError

    monkeypatch.setattr(service, 'sleep', cancelled)
    model_requests.responses.append(httpx.Response(503))
    with pytest.raises(asyncio.CancelledError):
        await service.llm(service.DISCOVER, {})
    assert len(model_requests.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('failure_stage', ['discover', 'compose', 'repair', 'verify', None])
async def test_special_job_retains_model_diagnostics_in_admin_output(database, material, client, monkeypatch, failure_stage):
    import httpx
    from app.services import job_runner

    candidate, _, document = material
    invalid = copy.deepcopy(document)
    invalid['overview']['citations'][0]['quote'] = '模型改写的摘录并不存在于任何原文'
    truncated_output = '{"candidates":[' + '截断内容' * 1500
    requests = []

    async def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body['max_tokens'] == service.MAX_OUTPUT_TOKENS
        system = body['messages'][0]['content']
        payload = json.loads(body['messages'][1]['content'])
        if system.startswith(service.DISCOVER):
            stage, result = 'discover', {'candidates': [candidate.model_dump()]}
        elif system.startswith(service.VERIFY):
            stage, result = 'verify', {'approved': True, 'reason': ''}
        else:
            stage = 'repair' if 'previous_document' in payload else 'compose'
            result = invalid if failure_stage == 'repair' and stage == 'compose' else document
        truncated = stage == failure_stage
        return httpx.Response(200, json={
            'id': f'request-{stage}', 'model': 'test-editorial-model',
            'choices': [{'finish_reason': 'length' if truncated else 'stop',
                         'message': {'content': truncated_output if truncated else json.dumps(result, ensure_ascii=False)}}],
            'usage': {'prompt_tokens': 1000, 'completion_tokens': 8192 if truncated else 128,
                      'total_tokens': 9192 if truncated else 1128},
        })

    real_client = httpx.AsyncClient
    monkeypatch.setattr(service.httpx, 'AsyncClient', lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setattr(settings, 'deepseek_api_key', 'diagnostics-secret-not-for-logs')
    monkeypatch.setattr(job_runner, 'SessionLocal', database)
    monkeypatch.setattr(service, 'SessionLocal', database)

    async def supplement(queries):
        return [], 'no_results'

    monkeypatch.setattr(service, 'supplement', supplement)
    result = await job_runner.run('specials_generate', {'dry_run': False})
    assert service._reporter.get() is None  # Reporters must not leak into another task.
    assert requests

    assert (await client.get('/api/v1/admin/jobs')).status_code == 401
    headers = {'X-Admin-Token': issue_admin_token()}
    jobs = (await client.get('/api/v1/admin/jobs', headers=headers)).json()['jobs']
    job = next(j for j in jobs if j['name'] == 'specials_generate')
    assert len(job['logs']) == len(result['logs'])
    for entry, saved in zip(job['logs'], result['logs']):
        assert datetime.fromisoformat(entry['at']) == datetime.fromisoformat(saved['at'])
        assert {k: v for k, v in entry.items() if k != 'at'} == {k: v for k, v in saved.items() if k != 'at'}
    assert 'diagnostics-secret-not-for-logs' not in json.dumps(job)
    assert job['logs'][0]['stage'] == 'load'
    if failure_stage:
        entry = next(e for e in job['logs'] if e['stage'] == failure_stage and e['level'] == 'error')
        details = entry['details']
        assert '输出限制' in entry['message'] and '8192' in entry['message']
        assert details['finish_reason'] == 'length' and details['completion_tokens'] == 8192
        assert details['prompt_tokens'] == 1000 and details['total_tokens'] == 9192
        assert details['max_tokens'] == 8192 and details['output_chars'] == len(truncated_output)
        assert details['request_id'] == f'request-{failure_stage}' and details['model'] == 'test-editorial-model'
        assert details['elapsed_seconds'] >= 0
        assert details['output_head'] == truncated_output[:1500] and details['output_tail'] == truncated_output[-1500:]
        assert details['output_preview_truncated'] is True
        if failure_stage == 'discover':
            assert job['status'] == 'error' and '输出限制' in job['error']
            assert len(requests) == 2, 'discovery must stop after one smaller retry'
        else:
            assert job['stats']['failed'] == 1
            async with database() as session:
                draft = await session.scalar(select(Special))
                assert draft.status == 'draft' and '输出限制' in draft.last_error
        async with database() as session:
            assert await session.scalar(select(func.count()).select_from(SpecialVersion)) == 0
    else:
        assert job['status'] == 'ok' and job['stats']['created'] == 1
        returned = [e for e in job['logs'] if e['details'] and e['details'].get('finish_reason') == 'stop']
        assert {e['stage'] for e in returned} == {'discover', 'compose', 'verify'}
        assert all(e['details']['completion_tokens'] == 128 for e in returned)
        assert job['logs'][-1]['stage'] == 'complete'


@pytest.mark.asyncio
async def test_job_diagnostics_are_bounded_preserve_parameters_and_reset_on_rerun(database, monkeypatch):
    from app.models import PipelineState
    from app.services import job_runner

    monkeypatch.setattr(job_runner, 'SessionLocal', database)
    snapshots = []

    async def handler(params):
        for index in range(job_runner.MAX_JOB_LOGS + 2):
            await job_runner.append_log('specials_generate', stage='test', message=f'记录 {index}')
        async with database() as session:
            state = json.loads((await session.get(PipelineState, 'job:specials_generate')).value)
            assert state['params'] == params
        snapshots.append(await job_runner.get_job('specials_generate'))
        raise ValueError('保留日志的失败任务')

    monkeypatch.setitem(job_runner.HANDLERS, 'specials_generate', handler)
    result = await job_runner.run('specials_generate', {'special_id': 12})
    assert result['status'] == 'error'
    assert snapshots[0]['status'] == 'running'
    assert len(result['logs']) == job_runner.MAX_JOB_LOGS
    assert result['logs'][0]['message'] == '记录 2'

    async def rerun(params):
        assert (await job_runner.get_job('specials_generate'))['logs'] == []
        await job_runner.append_log('specials_generate', stage='test', message='本次的新日志')
        return {'created': 1}

    monkeypatch.setitem(job_runner.HANDLERS, 'specials_generate', rerun)
    result = await job_runner.run('specials_generate')
    assert result['status'] == 'ok' and len(result['logs']) == 1
    assert result['logs'][0]['message'] == '本次的新日志'


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
