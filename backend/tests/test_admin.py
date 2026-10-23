import os
import sys

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# shared with the other test modules — see test_scoring.py NOTE
TEST_DB = "sqlite+aiosqlite:////tmp/agrihot_test.db"

os.environ["DATABASE_URL"] = TEST_DB
os.environ["CONTENT_FETCH_ENABLED"] = "false"  # no network in tests

from app.config import settings  # noqa: E402
from app.database import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ApiKey, Base, hash_api_key  # noqa: E402

TEST_KEY = "agri_test_key_admin"
ADMIN_PW = "test-admin-password"

engine = create_async_engine(TEST_DB)
TestSession = async_sessionmaker(engine, expire_on_commit=False)


async def override_session():
    async with TestSession() as s:
        yield s


app.dependency_overrides[get_session] = override_session


@pytest_asyncio.fixture(autouse=True)
async def fresh_db(monkeypatch):
    monkeypatch.setattr(settings, "admin_password", ADMIN_PW)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with TestSession() as s:
        s.add(ApiKey(key_hash=hash_api_key(TEST_KEY), name="test-bot"))
        await s.commit()
    yield


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def sample_item(**over):
    base = {
        "title": "农业农村部发布智慧农业发展指导意见",
        "url": "https://example.com/news/1001",
        "summary": "农业农村部今日发布智慧农业发展指导意见，提出到2030年重点任务。",
        "source_name": "示例新闻网",
        "category": "政策",
        "tags": ["智慧农业", "政策"],
    }
    base.update(over)
    return base


async def login(client) -> dict:
    r = await client.post("/api/v1/admin/login", json={"password": ADMIN_PW})
    assert r.status_code == 200, r.text
    return {"X-Admin-Token": r.json()["token"]}


# ---------- login ----------

@pytest.mark.asyncio
async def test_login_wrong_password(client):
    r = await client.post("/api/v1/admin/login", json={"password": "nope"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_login_disabled_without_config(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_password", "")
    r = await client.post("/api/v1/admin/login", json={"password": "anything"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_valid_token(client):
    r = await client.get("/api/v1/admin/me")
    assert r.status_code in (401, 403)
    auth = await login(client)
    r = await client.get("/api/v1/admin/me", headers=auth)
    assert r.status_code == 200
    assert r.json()["ok"] is True


@pytest.mark.asyncio
async def test_expired_token_rejected(client):
    from datetime import datetime, timedelta, timezone

    from app.security import issue_admin_token

    expired = issue_admin_token(datetime.now(timezone.utc) - timedelta(days=8))
    r = await client.get("/api/v1/admin/me", headers={"X-Admin-Token": expired})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_legacy_hmac_token_rejected(client):
    r = await client.get("/api/v1/admin/me", headers={"X-Admin-Token": "a" * 64})
    assert r.status_code == 401


# ---------- auth on write endpoints ----------

@pytest.mark.asyncio
async def test_patch_requires_token(client):
    r = await client.patch("/api/v1/admin/items/1", json={"title": "新标题来啦"})
    assert r.status_code in (401, 403)
    r = await client.patch(
        "/api/v1/admin/items/1", json={"title": "新标题来啦"},
        headers={"X-Admin-Token": "bad-token"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_delete_requires_token(client):
    r = await client.delete("/api/v1/admin/items/1")
    assert r.status_code in (401, 403)


# ---------- patch ----------

@pytest.mark.asyncio
async def test_patch_item_fields(client):
    headers = {"X-API-Key": TEST_KEY}
    r = await client.post("/api/v1/ingest/items", json=sample_item(), headers=headers)
    item_id = r.json()["item_id"]

    auth = await login(client)
    r = await client.patch(
        f"/api/v1/admin/items/{item_id}",
        json={
            "title": "修改后的标题：智慧农业指导意见发布",
            "is_selected": True,
            "hotness": 88,
            "category": "行业",
            "tags": ["数字乡村 新标签", "智慧农业"],
        },
        headers=auth,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "修改后的标题：智慧农业指导意见发布"
    assert body["is_selected"] is True
    assert body["hotness"] == 88
    assert body["category"] == "行业"
    assert set(body["tags"]) == {"数字乡村", "新标签", "智慧农业"}

    # 未提供的字段保持不变
    assert body["summary"] == sample_item()["summary"]
    assert body.get("summary_zh") is None


@pytest.mark.asyncio
async def test_patch_summary_zh(client):
    headers = {"X-API-Key": TEST_KEY}
    r = await client.post("/api/v1/ingest/items", json=sample_item(), headers=headers)
    item_id = r.json()["item_id"]

    auth = await login(client)
    zh = "这是一条人工校对过的中文摘要，用于覆盖模型译文。"
    r = await client.patch(
        f"/api/v1/admin/items/{item_id}", json={"summary_zh": zh}, headers=auth,
    )
    assert r.status_code == 200, r.text
    assert r.json()["summary_zh"] == zh
    assert r.json()["summary"] == sample_item()["summary"]

    r = await client.patch(
        f"/api/v1/admin/items/{item_id}", json={"summary_zh": "  "}, headers=auth,
    )
    assert r.json()["summary_zh"] is None


@pytest.mark.asyncio
async def test_patch_unknown_category_falls_back(client):
    headers = {"X-API-Key": TEST_KEY}
    r = await client.post("/api/v1/ingest/items", json=sample_item(), headers=headers)
    item_id = r.json()["item_id"]

    auth = await login(client)
    r = await client.patch(
        f"/api/v1/admin/items/{item_id}", json={"category": "不存在的分类"},
        headers=auth,
    )
    assert r.json()["category"] == "报道"


@pytest.mark.asyncio
async def test_patch_not_found(client):
    auth = await login(client)
    r = await client.patch(
        "/api/v1/admin/items/999", json={"hotness": 1}, headers=auth,
    )
    assert r.status_code == 404


# ---------- manual full-text fetch ----------

FAKE_FULLTEXT = "# 全文\n\n" + "正文段落。" * 100  # > MIN_CONTENT_CHARS


@pytest.mark.asyncio
async def test_fetch_content_requires_token(client):
    r = await client.post("/api/v1/admin/items/1/fetch-content")
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_fetch_content_saves_and_rescores(client, monkeypatch):
    from app.services import content_service, scoring_service

    headers = {"X-API-Key": TEST_KEY}
    r = await client.post("/api/v1/ingest/items", json=sample_item(), headers=headers)
    item_id = r.json()["item_id"]

    async def fake_fetch(url, **kwargs):
        return FAKE_FULLTEXT

    async def fake_deepseek(item):
        assert item.content == FAKE_FULLTEXT  # scoring sees the fresh body
        return '{"relevant": true, "impact": 26, "substance": 22, "depth": 16, "authority": 12, "freshness": 9}'

    monkeypatch.setattr(settings, "content_fetch_enabled", True)
    monkeypatch.setattr(content_service, "fetch_fulltext", fake_fetch)
    monkeypatch.setattr(settings, "deepseek_api_key", "fake-key")
    monkeypatch.setattr(scoring_service, "_call_deepseek", fake_deepseek)

    auth = await login(client)
    r = await client.post(f"/api/v1/admin/items/{item_id}/fetch-content", headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["content"] == FAKE_FULLTEXT
    assert body["score"] == 85
    assert body["is_selected"] is True


@pytest.mark.asyncio
async def test_fetch_content_failure_keeps_item_untouched(client, monkeypatch):
    from app.services import content_service

    headers = {"X-API-Key": TEST_KEY}
    r = await client.post("/api/v1/ingest/items", json=sample_item(), headers=headers)
    item_id = r.json()["item_id"]

    async def fake_fetch(url, **kwargs):
        return None

    monkeypatch.setattr(settings, "content_fetch_enabled", True)
    monkeypatch.setattr(content_service, "fetch_fulltext", fake_fetch)

    auth = await login(client)
    r = await client.post(f"/api/v1/admin/items/{item_id}/fetch-content", headers=auth)
    assert r.status_code == 502
    body = (await client.get(f"/api/v1/items/{item_id}")).json()
    assert body["content"] is None
    assert body["score"] is None  # no rescoring on failure


@pytest.mark.asyncio
async def test_fetch_content_succeeds_even_if_rescoring_raises(client, monkeypatch):
    from app.services import content_service, scoring_service

    result = await client.post('/api/v1/ingest/items', json=sample_item(), headers={'X-API-Key': TEST_KEY})
    item_id = result.json()['item_id']

    async def fetch(url, **kwargs):
        return FAKE_FULLTEXT

    async def fail_score(session, item):
        raise RuntimeError('scoring failed')

    monkeypatch.setattr(settings, 'content_fetch_enabled', True)
    monkeypatch.setattr(settings, 'deepseek_api_key', 'test-not-sent')
    monkeypatch.setattr(content_service, 'fetch_fulltext', fetch)
    monkeypatch.setattr(scoring_service, 'score_item', fail_score)
    result = await client.post(f'/api/v1/admin/items/{item_id}/fetch-content', headers=await login(client))
    assert result.status_code == 200, result.text
    assert result.json()['content'] == FAKE_FULLTEXT
    assert (await client.get(f'/api/v1/items/{item_id}')).json()['content'] == FAKE_FULLTEXT


@pytest.mark.asyncio
async def test_fetch_content_recovers_guangxi_body_and_persists_it(client, reader_server):
    url = 'https://nynct.gxzf.gov.cn/xwdt/ywkb/t28253108.shtml'
    result = await client.post('/api/v1/ingest/items', json=sample_item(url=url, content='此前保存的正文'), headers={'X-API-Key': TEST_KEY})
    item_id = result.json()['item_id']
    reader_server.responses.extend([
        (422, {'message': 'page.goto: net::ERR_CERT_AUTHORITY_INVALID'}),
        (200, 'Title: 正文\n\nMarkdown Content:\n\n' + FAKE_FULLTEXT),
    ])
    result = await client.post(f'/api/v1/admin/items/{item_id}/fetch-content', headers=await login(client))
    assert result.status_code == 200, result.text
    assert result.json()['content'] == FAKE_FULLTEXT and result.json()['url'] == url
    assert (await client.get(f'/api/v1/items/{item_id}')).json()['content'] == FAKE_FULLTEXT
    assert reader_server.requests == ['/' + url, '/' + url.replace('https://', 'http://', 1)]


@pytest.mark.asyncio
@pytest.mark.parametrize('resolve_doi', [True, False])
async def test_fetch_paper_uses_publisher_or_open_access_and_persists_full_body(client, monkeypatch, resolve_doi):
    import httpx

    from app.models import Item, PaperMeta
    from app.services import content_service
    from app.services.fulltext import FulltextEngine

    doi_url = 'https://doi.org/10.3389/test.12345'
    publisher = 'https://www.frontiersin.org/articles/test/full'
    oa_url = 'https://repository.example/paper.xml'
    result = await client.post('/api/v1/ingest/items', json=sample_item(url=doi_url, category='论文'), headers={'X-API-Key': TEST_KEY})
    item_id = result.json()['item_id']
    async with TestSession() as session:
        item = await session.get(Item, item_id)
        item.paper = PaperMeta(oa_url=oa_url)
        await session.commit()

    requests = []

    def handler(request):
        requests.append(str(request.url))
        if request.url.host == 'doi.org':
            return httpx.Response(302, headers={'Location': publisher}) if resolve_doi else httpx.Response(404)
        if request.url.host == 'api.crossref.org':
            return httpx.Response(404)
        if str(request.url) == publisher:
            return httpx.Response(200, headers={'Content-Type': 'text/html'}, text='<meta name="citation_xml_url" content="./xml">')
        if request.url.path.endswith('/xml') or str(request.url) == oa_url:
            return httpx.Response(200, headers={'Content-Type': 'application/xml'}, content=(
                '<article><body><sec><title>Methods</title><p>' + FAKE_FULLTEXT + '</p></sec></body></article>').encode())
        pytest.fail(f'Unexpected request: {request.url}')

    async def allow_test_url(url):
        pass

    monkeypatch.setattr(settings, 'content_fetch_enabled', True)
    monkeypatch.setattr(content_service, 'create_fulltext_engine', lambda: FulltextEngine(
        transport=httpx.MockTransport(handler), validator=allow_test_url,
    ))
    result = await client.post(f'/api/v1/admin/items/{item_id}/fetch-content', headers=await login(client))
    assert result.status_code == 200, result.text
    stored = (await client.get(f'/api/v1/items/{item_id}')).json()
    assert ' '.join(FAKE_FULLTEXT.split()) in stored['content'] and '## Methods' in stored['content']
    assert stored['url'] == doi_url and stored['summary'] == sample_item()['summary']
    assert stored['paper']['oa_url'] == oa_url
    assert (oa_url in requests) == (not resolve_doi)


@pytest.mark.asyncio
@pytest.mark.parametrize('status,provider_body,reason,message', [
    (422, {'message': 'net::ERR_CERT_AUTHORITY_INVALID'}, 'source_tls_error', '证书'),
    (451, {'message': 'private-provider-detail'}, 'reader_blocked', '限制访问'),
])
async def test_fetch_content_explains_failure_and_keeps_saved_body(client, reader_server, status, provider_body, reason, message):
    result = await client.post('/api/v1/ingest/items', json=sample_item(content='已经保存的原文'), headers={'X-API-Key': TEST_KEY})
    item_id = result.json()['item_id']
    reader_server.responses.append((status, provider_body))
    result = await client.post(f'/api/v1/admin/items/{item_id}/fetch-content', headers=await login(client))
    assert result.status_code == 502
    error = result.json()['detail']
    assert error['reason'] == reason and error['upstream_status'] == status
    assert message in error['detail'] and 'private-provider-detail' not in result.text
    assert (await client.get(f'/api/v1/items/{item_id}')).json()['content'] == '已经保存的原文'


@pytest.mark.asyncio
async def test_rescore_item(client, monkeypatch):
    from app.services import scoring_service

    headers = {"X-API-Key": TEST_KEY}
    r = await client.post("/api/v1/ingest/items", json=sample_item(), headers=headers)
    item_id = r.json()["item_id"]

    async def fake_deepseek(item):
        return '{"relevant": true, "impact": 20, "substance": 18, "depth": 14, "authority": 10, "freshness": 8}'

    monkeypatch.setattr(settings, "deepseek_api_key", "fake-key")
    monkeypatch.setattr(scoring_service, "_call_deepseek", fake_deepseek)

    auth = await login(client)
    r = await client.post(f"/api/v1/admin/items/{item_id}/rescore", headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["score"] == 70


@pytest.mark.asyncio
async def test_fetch_content_disabled_returns_503(client, monkeypatch):
    headers = {"X-API-Key": TEST_KEY}
    r = await client.post("/api/v1/ingest/items", json=sample_item(), headers=headers)
    item_id = r.json()["item_id"]

    monkeypatch.setattr(settings, "content_fetch_enabled", False)
    auth = await login(client)
    r = await client.post(f"/api/v1/admin/items/{item_id}/fetch-content", headers=auth)
    assert r.status_code == 503


# ---------- delete ----------

@pytest.mark.asyncio
async def test_admin_delete_item(client):
    headers = {"X-API-Key": TEST_KEY}
    r = await client.post("/api/v1/ingest/items", json=sample_item(), headers=headers)
    item_id = r.json()["item_id"]

    auth = await login(client)
    r = await client.delete(f"/api/v1/admin/items/{item_id}", headers=auth)
    assert r.status_code == 200
    assert (await client.get(f"/api/v1/items/{item_id}")).status_code == 404
