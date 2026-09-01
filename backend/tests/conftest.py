"""Shared test fixtures: reset in-memory admin runtime between tests."""
import pytest


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
