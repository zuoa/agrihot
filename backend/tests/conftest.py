"""Shared test fixtures: reset in-memory admin runtime between tests."""
import pytest


@pytest.fixture(autouse=True)
def isolate_external_services(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, 'content_fetch_enabled', False)
    monkeypatch.setattr(settings, 'deepseek_api_key', '')
    monkeypatch.setattr(settings, 'embedding_api_key', '')


@pytest.fixture(autouse=True)
def disable_rate_limiter():
    """Login is 10/min; the suite now logs in more often than that."""
    from app.api.v1.ingest import limiter

    limiter.enabled = False
    yield
    limiter.enabled = True


@pytest.fixture(autouse=True)
def reset_admin_runtime():
    from app.services import job_runner, runtime_settings, watchlist_service

    runtime_settings.reset()
    watchlist_service.reset()
    job_runner.reset()
    yield
    runtime_settings.reset()
    watchlist_service.reset()
    job_runner.reset()


@pytest.fixture
def embedding_provider(monkeypatch):
    """Exercise the real HTTP client against a local test server, without paid calls."""
    import json
    import threading
    import time
    from collections import OrderedDict, deque
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from types import SimpleNamespace

    from app.config import settings
    from app.services import embedding_service

    provider = SimpleNamespace(responses=deque(), requests=[])

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            provider.requests.append((time.monotonic(), payload))
            if provider.responses:
                status, headers, body = provider.responses.popleft()
            else:
                status, headers = 200, {}
                body = {'data': [{'index': i, 'embedding': [1, 0, 0]} for i in range(len(payload['input']))]}
            encoded = json.dumps(body).encode() if not isinstance(body, str) else body.encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(encoded)))
            for name, value in headers.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    monkeypatch.setattr(embedding_service, '_gate', embedding_service._RequestGate())
    monkeypatch.setattr(embedding_service, '_query_cache', OrderedDict())
    monkeypatch.setattr(settings, 'embedding_api_key', 'local-test-not-a-real-key')
    monkeypatch.setattr(settings, 'embedding_base_url', f'http://127.0.0.1:{server.server_port}')
    monkeypatch.setattr(settings, 'embedding_dimensions', 3)
    monkeypatch.setattr(settings, 'embedding_min_interval', 0)
    monkeypatch.setattr(settings, 'embedding_rate_limit_cooldown', 60)
    try:
        yield provider
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
