"""Agent contracts against SQLite and (when configured) a real PostgreSQL + pgvector."""
import hashlib
import os
import sys
from datetime import date, timedelta

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DATABASE_URL', 'sqlite+aiosqlite:////tmp/agrihot_test.db')

from app.agent_schemas import SearchIn
from app.config import settings
from app.database import ensure_schema, get_session
from app.main import app
from app.models import AgentApplication, ApiKey, Base, Daily, Item, SearchChunk, SearchJob, Tag, hash_api_key, utcnow
from app.security import issue_admin_token
from app.services import agent_auth, agent_service, embedding_service, ingest_service, search_index_service

BACKENDS = ['sqlite'] + (['postgres'] if os.getenv('AGRIHOT_TEST_POSTGRES_URL') else [])
READ_KEY = 'agent-test-reading-key'
PUSH_KEY = 'agent-test-existing-push-key'
READ_HEADERS = {'Authorization': f'Bearer {READ_KEY}'}


@pytest_asyncio.fixture(params=BACKENDS)
async def db(request, tmp_path, monkeypatch):
    url = os.environ['AGRIHOT_TEST_POSTGRES_URL'] if request.param == 'postgres' else f'sqlite+aiosqlite:///{tmp_path}/agent.db'
    engine = create_async_engine(url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await ensure_schema(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(settings, 'admin_password', 'agent-admin-test')
    monkeypatch.setattr(settings, 'embedding_api_key', '')
    monkeypatch.setattr(settings, 'embedding_dimensions', 3)
    agent_auth._budget.storage.reset()
    embedding_service._query_cache.clear()
    async with factory() as session:
        session.add_all([ApiKey(name='reader', purpose='read', key_hash=hash_api_key(READ_KEY)),
                         ApiKey(name='legacy-crawler', key_hash=hash_api_key(PUSH_KEY))])
        await session.commit()
    async def session_dependency():
        async with factory() as session:
            yield session
    previous = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = session_dependency
    import app.mcp_server as mcp_module
    monkeypatch.setattr(mcp_module, 'get_session', session_dependency)
    yield factory
    if previous:
        app.dependency_overrides[get_session] = previous
    else:
        app.dependency_overrides.pop(get_session, None)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost') as client:
        yield client


async def add_item(factory, title='智慧农业遥感监测进展', **kwargs):
    async with factory() as session:
        item = Item(title=title, summary='使用卫星遥感和机器学习监测农作物长势的新方法。',
                    url='https://example.org/' + hashlib.sha256(title.encode()).hexdigest(),
                    url_hash=hashlib.sha256(title.encode()).hexdigest(), title_simhash=0,
                    **kwargs)
        session.add(item)
        await session.commit()
        return item.id


def admin_headers():
    return {'X-Admin-Token': issue_admin_token()}


@pytest.mark.asyncio
async def test_read_write_separation_and_revocation(client, db):
    assert (await client.post('/api/v1/agent/items', json={})).status_code == 401
    assert (await client.post('/api/v1/agent/items', json={}, headers={'Authorization': 'Bearer wrong'})).status_code == 401
    assert (await client.post('/api/v1/agent/items', json={}, headers={'Authorization': f'Bearer {PUSH_KEY}'})).status_code == 403
    payload = {'title': '全新农业政策正式发布', 'url': 'https://example.org/push', 'summary': '这是一个至少十个字的农业资讯摘要。'}
    assert (await client.post('/api/v1/ingest/items', json=payload, headers={'X-API-Key': READ_KEY})).status_code == 403
    response = await client.post('/api/v1/agent/items', json={}, headers=READ_HEADERS)
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    async with db() as session:
        key = (await session.execute(select(ApiKey).where(ApiKey.purpose == 'read'))).scalar_one()
        assert key.last_used_at is not None
        key.is_active = False
        await session.commit()
    assert (await client.post('/api/v1/agent/items', json={}, headers=READ_HEADERS)).status_code == 401


@pytest.mark.asyncio
async def test_application_approval_is_private_and_once(client, db):
    response = await client.post('/api/v1/agent/applications', json={'name': '研究助手', 'contact': 'reader@example.org', 'use_case': '用于农业研究项目中查询政策和论文资料。'})
    assert response.status_code == 201
    application_id = response.json()['id']
    path = f'/api/v1/admin/agent/applications/{application_id}/review'
    assert (await client.post(path, json={'decision': 'approve'})).status_code == 401
    response = await client.post(path, json={'decision': 'approve'}, headers=admin_headers())
    assert response.status_code == 200
    raw = response.json()['key']
    assert raw.startswith('agri_read_')
    assert (await client.post(path, json={'decision': 'approve'}, headers=admin_headers())).status_code == 409
    listing = await client.get('/api/v1/admin/agent/applications', headers=admin_headers())
    assert raw not in listing.text and 'key_hash' not in listing.text
    assert (await client.post('/api/v1/agent/items', json={}, headers={'Authorization': f'Bearer {raw}'})).status_code == 200
    async with db() as session:
        assert (await session.get(AgentApplication, application_id)).status == 'approved'
        assert (await session.execute(select(ApiKey).where(ApiKey.key_hash == hash_api_key(raw)))).scalar_one().purpose == 'read'


@pytest.mark.asyncio
async def test_application_validation_and_rejection(client):
    assert (await client.post('/api/v1/agent/applications', json={'name': ' ', 'contact': 'abc', 'use_case': ' ' * 20})).status_code == 422
    response = await client.post('/api/v1/agent/applications', json={'name': '拒绝测试', 'contact': 'contact@example.org', 'use_case': '申请用于农业资讯自动汇总与跟踪。'})
    path = f"/api/v1/admin/agent/applications/{response.json()['id']}/review"
    review = await client.post(path, json={'decision': 'reject', 'note': '请补充用途'}, headers=admin_headers())
    assert review.status_code == 200 and review.json()['key'] is None
    assert review.json()['application']['status'] == 'rejected'


@pytest.mark.asyncio
async def test_admin_key_create_preserves_purpose(client):
    for purpose in ('read', 'push'):
        response = await client.post('/api/v1/admin/api-keys', json={'name': purpose, 'purpose': purpose}, headers=admin_headers())
        assert response.status_code == 200
        assert response.json()['purpose'] == purpose
    response = await client.post('/api/v1/admin/api-keys', json={'name': 'old-client'}, headers=admin_headers())
    assert response.json()['purpose'] == 'push'


@pytest.mark.asyncio
async def test_keyword_fulltext_filters_and_missing_body(client, db):
    first = await add_item(db, content='深层正文：小麦条锈病识别与防治。', category='论文')
    second = await add_item(db, title='农业补贴政策解读', category='政策')
    async with db() as session:
        item = await session.get(Item, first)
        item.tags = [Tag(name='作物病害')]
        await session.commit()
    response = await client.post('/api/v1/agent/search', json={'q': '条锈病', 'category': '论文', 'tags': ['作物病害']}, headers=READ_HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [i['id'] for i in body['items']] == [first]
    assert body['degraded'] and body['mode'] == 'keyword'
    assert '条锈病' in body['items'][0]['snippet']
    assert 'content' not in body['items'][0]
    detail = (await client.get(f'/api/v1/agent/items/{first}', headers=READ_HEADERS)).json()
    assert detail['has_fulltext'] and '条锈病' in detail['content']
    assert detail['site_url'].endswith(f'/items/{first}')
    missing = (await client.get(f'/api/v1/agent/items/{second}', headers=READ_HEADERS)).json()
    assert not missing['has_fulltext'] and missing['content_status'] == 'missing'
    assert (await client.get('/api/v1/agent/items/999999', headers=READ_HEADERS)).status_code == 404
    assert (await client.post('/api/v1/agent/search', json={'q': '%_nonexistent'}, headers=READ_HEADERS)).json()['items'] == []


@pytest.mark.asyncio
async def test_time_validation_and_pagination(client, db):
    first = await add_item(db)
    second = await add_item(db, title='另一项农业进展', created_at=utcnow() - timedelta(days=30))
    response = await client.post('/api/v1/agent/items', json={'limit': 1}, headers=READ_HEADERS)
    assert response.json()['items'][0]['id'] == first
    cursor = response.json()['next_before_id']
    response = await client.post('/api/v1/agent/items', json={'limit': 1, 'before_id': cursor}, headers=READ_HEADERS)
    assert response.json()['items'][0]['id'] == second
    response = await client.post('/api/v1/agent/search', json={'q': '农业', 'since': (utcnow() - timedelta(days=1)).isoformat()}, headers=READ_HEADERS)
    assert [i['id'] for i in response.json()['items']] == [first]
    for invalid in ({'q': ' '}, {'q': 'a', 'limit': 51}, {'q': 'a', 'since': '2026-10-23', 'until': '2026-10-01'}):
        assert (await client.post('/api/v1/agent/search', json=invalid, headers=READ_HEADERS)).status_code == 422


@pytest.mark.asyncio
async def test_dailies_include_body_and_cursor(client, db):
    iid = await add_item(db)
    async with db() as session:
        session.add_all([Daily(date=date(2026, 10, day), title=f'日报 {day}', highlights=['要点'], content='完整日报正文', item_ids=[iid]) for day in (21, 22)])
        await session.commit()
    response = await client.get('/api/v1/agent/dailies?limit=1', headers=READ_HEADERS)
    assert response.json()['next_before'] == '2026-10-22'
    response = await client.get('/api/v1/agent/dailies/latest', headers=READ_HEADERS)
    assert response.json()['content'] == '完整日报正文'
    assert response.json()['items'][0]['id'] == iid
    assert (await client.get('/api/v1/agent/dailies/2026-01-01', headers=READ_HEADERS)).status_code == 404


@pytest.mark.asyncio
async def test_index_queue_update_delete_and_retry(client, db):
    iid = await add_item(db)
    async with db() as session:
        job = await session.get(SearchJob, iid)
        assert job.status == 'pending'
        revision = job.revision
    # With no GLM key, real indexing still builds the keyword index and records degradation.
    assert await search_index_service.process_one(db)
    async with db() as session:
        job = await session.get(SearchJob, iid)
        assert job.status == 'lexical' and job.error == 'not_configured'
        assert (await session.execute(select(SearchChunk).where(SearchChunk.item_id == iid))).scalars().all()
        item = await session.get(Item, iid)
        item.content = '更新全文：农业无人机植保。'
        item.tags = [Tag(name='农业无人机')]
        await session.commit()
    async with db() as session:
        job = await session.get(SearchJob, iid)
        assert job.status == 'pending' and job.revision > revision
    assert await search_index_service.process_one(db)
    response = await client.get('/api/v1/admin/agent/index', headers=admin_headers())
    assert response.json()['pending'] == 1 and not response.json()['configured']
    async with db() as session:
        assert await ingest_service.delete_item(session, iid)
        await session.commit()
        assert await session.get(SearchJob, iid) is None
        assert (await session.execute(select(func.count()).select_from(SearchChunk))).scalar_one() == 0


@pytest.mark.asyncio
async def test_hybrid_ranking_and_model_isolation(client, db, monkeypatch):
    relevant = await add_item(db, title='农业卫星对地观测', category='论文')
    other = await add_item(db, title='养殖场成本核算', category='论文')
    fp = embedding_service.fingerprint()
    async with db() as session:
        for iid, vector, content in [(relevant, [1, 0, 0], '作物遥感监测'), (other, [0, 1, 0], '生猪饲料成本')]:
            job = await session.get(SearchJob, iid)
            job.status, job.fingerprint = 'ready', fp
            session.add(SearchChunk(item_id=iid, text=content, lexemes=' '.join(search_index_service.tokens(content)), fingerprint=fp, embedding=vector))
        # A long article must not consume the whole chunk candidate budget.
        session.add_all(SearchChunk(item_id=relevant, position=i+1, text='作物遥感监测', lexemes='作物 遥感 监测', fingerprint=fp, embedding=[1, 0, 0]) for i in range(205))
        await session.commit()
    # Known mathematical vectors validate real DB ranking; no provider request is made.
    monkeypatch.setattr(settings, 'embedding_api_key', 'test-not-sent')
    import time
    embedding_service._query_cache[(fp, '田间长势观测')] = (time.monotonic() + 30, [1, 0, 0])
    response = await client.post('/api/v1/agent/search', json={'q': '田间长势观测', 'category': '论文', 'limit': 1}, headers=READ_HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()['mode'] == 'hybrid'
    assert response.json()['items'][0]['id'] == relevant
    assert not response.json()['degraded']
    response = await client.post('/api/v1/agent/search', json={'q': '田间长势观测', 'category': '论文', 'limit': 2}, headers=READ_HEADERS)
    assert [item['id'] for item in response.json()['items']] == [relevant, other]
    monkeypatch.setattr(settings, 'embedding_model', 'new-model')
    # Model changes requeue ready jobs, so old vectors cannot mix with new queries.
    async with db() as session:
        assert await search_index_service.enqueue_backfill(session) == 2
        assert (await session.get(SearchJob, relevant)).status == 'pending'


@pytest.mark.asyncio
async def test_shared_rate_limit(client, monkeypatch):
    monkeypatch.setattr(settings, 'agent_rate_limit', '1/minute')
    assert (await client.post('/api/v1/agent/items', json={}, headers=READ_HEADERS)).status_code == 200
    assert (await client.get('/api/v1/agent/dailies', headers=READ_HEADERS)).status_code == 429
    assert (await client.get('/api/v1/mcp', headers=READ_HEADERS)).status_code == 429


@pytest.mark.asyncio
async def test_public_discovery_hides_private_routes(client, monkeypatch):
    schema = (await client.get('/openapi.json')).json()
    assert not any('/ingest/' in path or '/admin/' in path for path in schema['paths'])
    assert schema['paths']['/api/v1/agent/search']['post']['security'] == [{'AgentReadKey': []}]
    assert (await client.get('/api/v1/agent')).status_code == 200
    monkeypatch.setattr(settings, 'site_url', 'https://agriculture.example')
    skill = await client.get('/agrihot-skill/SKILL.md')
    assert skill.status_code == 200
    assert 'https://agriculture.example/api/v1/agent' in skill.text
    assert READ_KEY not in skill.text and PUSH_KEY not in skill.text
    assert (await client.get('/llms.txt')).status_code == 200
    assert (await client.get('/api/v1/admin/agent/push-guide')).status_code == 401
    guide = await client.get('/api/v1/admin/agent/push-guide', headers=admin_headers())
    assert guide.status_code == 200 and '/api/v1/ingest/items' in guide.json()['content']


@pytest.mark.asyncio
async def test_existing_key_schema_upgrade_preserves_hashes(client, db):
    engine = db.kw['bind']
    async with engine.begin() as conn:
        await conn.execute(text('ALTER TABLE api_keys DROP COLUMN purpose'))
    await ensure_schema(engine)
    async with db() as session:
        legacy = (await session.execute(select(ApiKey).where(ApiKey.key_hash == hash_api_key(PUSH_KEY)))).scalar_one()
        assert legacy.purpose == 'push' and legacy.is_active
    assert (await client.post('/api/v1/agent/items', json={}, headers={'Authorization': f'Bearer {PUSH_KEY}'})).status_code == 403


@pytest.mark.asyncio
async def test_provider_connection_failure_returns_degradation(client, db, monkeypatch):
    await add_item(db)
    monkeypatch.setattr(settings, 'embedding_api_key', 'local-test-not-a-real-key')
    monkeypatch.setattr(settings, 'embedding_base_url', 'http://127.0.0.1:1')
    monkeypatch.setattr(settings, 'embedding_timeout', 0.2)
    response = await client.post('/api/v1/agent/search', json={'q': '农业'}, headers=READ_HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()['degraded'] and response.json()['items']
    assert 'provider_unavailable' in response.json()['degradation_reasons']


@pytest.mark.asyncio
async def test_mcp_initialize_tools_and_calls(client, db, monkeypatch):
    from app.mcp_server import create_mcp, mcp_app
    mcp, fresh_app = create_mcp()
    monkeypatch.setattr(mcp_app, 'app', fresh_app.app)
    headers = {**READ_HEADERS, 'Accept': 'application/json, text/event-stream'}
    async with mcp.session_manager.run():
        response = await client.post('/api/v1/mcp', json={'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 'agrihot-test', 'version': '1'}}}, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()['result']['serverInfo']['name'] == 'AgriHot'
        response = await client.post('/api/v1/mcp', json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}, headers=headers)
        names = {tool['name'] for tool in response.json()['result']['tools']}
        assert names == {'search_content', 'list_items', 'get_item', 'list_dailies', 'get_daily', 'list_topics'}
        iid = await add_item(db)
        async with db() as session:
            session.add(Daily(date=date(2026, 10, 22), title='MCP 日报', highlights=['要点'], content='农业日报完整内容', item_ids=[iid]))
            await session.commit()
        calls = [('search_content', {'query': {'q': '农业'}}), ('list_items', {'query': {}}), ('get_item', {'item_id': iid}), ('list_dailies', {}), ('get_daily', {}), ('list_topics', {})]
        for name, arguments in calls:
            response = await client.post('/api/v1/mcp', json={'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': name, 'arguments': arguments}}, headers=headers)
            assert response.status_code == 200, response.text
            result = response.json()['result']
            assert not result.get('isError'), result


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv('AGRIHOT_LIVE_EMBEDDING_API_KEY'), reason='Set AGRIHOT_LIVE_EMBEDDING_API_KEY for real GLM API verification')
async def test_glm_live_embeddings_and_search(db, monkeypatch):
    """Opt-in, real paid provider calls. Uses only the dedicated test database."""
    if db.kw['bind'].dialect.name != 'postgresql':
        pytest.skip('Live retrieval requires PostgreSQL + pgvector')
    monkeypatch.setattr(settings, 'embedding_api_key', os.environ['AGRIHOT_LIVE_EMBEDDING_API_KEY'])
    monkeypatch.setattr(settings, 'embedding_base_url', 'https://open.bigmodel.cn/api/paas/v4')
    monkeypatch.setattr(settings, 'embedding_model', 'embedding-3')
    monkeypatch.setattr(settings, 'embedding_dimensions', 1024)
    relevant = await add_item(db, title='卫星遥感用于农田作物生物量估测', category='论文', content='研究利用多光谱卫星影像反演小麦叶面积指数与生物量，监测长势变化。')
    async with db() as session:
        session.add(Item(title='城市交响乐团音乐会', summary='交响乐团演奏古典音乐作品，节目包含钢琴协奏曲与小提琴独奏。',
                         content='音乐会于城市艺术中心举行，观众欣赏莫扎特与贝多芬作品。', category='报道',
                         url='https://example.org/live-test-music', url_hash='live-music', title_simhash=0))
        await session.commit()
    while await search_index_service.process_one(db):
        pass
    async with db() as session:
        status = await search_index_service.status(session)
        assert status['indexed'] == 2, status
        result = await agent_service.search(session, SearchIn(q='通过空间观测了解田间植物生长状况', limit=2))
        assert result['mode'] == 'hybrid' and not result['degraded'], result['degradation_reasons']
        assert result['items'][0]['id'] == relevant
