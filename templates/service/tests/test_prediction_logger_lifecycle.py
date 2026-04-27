"""Tests for the ``_start_prediction_logger`` fail-fast contract (Phase 1.1).

These tests cover the env-aware degradation matrix introduced by the
runtime-closure work:

==============  ==========================  =========================
ENVIRONMENT     common_utils importable     Expected behaviour
==============  ==========================  =========================
dev / local     no                          warn + return cleanly
staging / prod  no                          RuntimeError
any             yes                         start logger normally
any             enabled=false               no-op, return cleanly
==============  ==========================  =========================

The intent is to make sure a developer running the service locally
without ``common_utils`` on the path is *not* blocked, while a
production-class image without ``common_utils`` cannot start — drift
detection and SLO accounting both depend on the closed-loop feed.
"""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import patch

import pytest

import app.fastapi_app as fastapi_app_mod

# Capture the real function at IMPORT time. The session-scope autouse
# fixture in conftest.py patches ``fastapi_app_mod._start_prediction_logger``
# with ``AsyncMock()`` so the lifespan can run without side effects in the
# rest of the suite. We bypass that patch here because these tests need to
# exercise the real env-aware fail-fast contract.
_real_start_prediction_logger = fastapi_app_mod._start_prediction_logger


@pytest.fixture(autouse=True)
def _clear_global_logger() -> None:
    """Each test starts with no logger handle."""
    fastapi_app_mod._prediction_logger = None
    yield
    fastapi_app_mod._prediction_logger = None


def _run(coro):
    """Run an async coroutine synchronously without pytest-asyncio.

    The template ships with anyio (transitive via FastAPI) but not
    pytest-asyncio; using ``asyncio.run`` keeps the test surface minimal
    and avoids adding a dev dependency just for four tests.
    """
    return asyncio.run(coro)


def test_disabled_returns_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    """``PREDICTION_LOG_ENABLED=false`` is the explicit opt-out path."""
    monkeypatch.setenv("PREDICTION_LOG_ENABLED", "false")
    # Even with common_utils missing, opt-out must not raise.
    with patch.object(fastapi_app_mod, "_PREDICTION_LOGGING_AVAILABLE", False):
        _run(_real_start_prediction_logger())
    assert fastapi_app_mod._prediction_logger is None


def test_dev_env_warns_and_returns(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """In dev, a missing common_utils degrades to a warning."""
    monkeypatch.setenv("PREDICTION_LOG_ENABLED", "true")
    monkeypatch.setenv("ENVIRONMENT", "dev")
    with (
        patch.object(fastapi_app_mod, "_PREDICTION_LOGGING_AVAILABLE", False),
        caplog.at_level(logging.WARNING, logger=fastapi_app_mod.logger.name),
    ):
        _run(_real_start_prediction_logger())
    assert fastapi_app_mod._prediction_logger is None
    assert any("[dev]" in rec.message for rec in caplog.records)


def test_local_env_warns_and_returns(monkeypatch: pytest.MonkeyPatch) -> None:
    """`local` is treated as dev — same tolerance."""
    monkeypatch.setenv("PREDICTION_LOG_ENABLED", "true")
    monkeypatch.setenv("ENVIRONMENT", "local")
    with patch.object(fastapi_app_mod, "_PREDICTION_LOGGING_AVAILABLE", False):
        _run(_real_start_prediction_logger())
    assert fastapi_app_mod._prediction_logger is None


@pytest.mark.parametrize("env", ["staging", "production", "prod", ""])
def test_non_dev_env_raises(monkeypatch: pytest.MonkeyPatch, env: str) -> None:
    """Any non-dev environment (including the empty default → prod) must
    raise. This is the regression guard for the original silent-degrade
    bug that motivated PR-R2-1 / Phase 1.1.
    """
    monkeypatch.setenv("PREDICTION_LOG_ENABLED", "true")
    if env:
        monkeypatch.setenv("ENVIRONMENT", env)
    else:
        monkeypatch.delenv("ENVIRONMENT", raising=False)
    with patch.object(fastapi_app_mod, "_PREDICTION_LOGGING_AVAILABLE", False):
        with pytest.raises(RuntimeError, match="common_utils.prediction_logger"):
            _run(_real_start_prediction_logger())
