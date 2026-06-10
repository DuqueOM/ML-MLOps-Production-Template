"""Shared pytest fixtures for {ServiceName} test suite.

The fastapi app (`app.main`) uses a lifespan that loads model artifacts
from disk and runs a warm-up. Tests cannot rely on real artifacts being
present, so we patch the loader + warmup at module level BEFORE the
lifespan runs (i.e., before TestClient is instantiated).

The ``client`` fixture here is the canonical test client; individual
tests should depend on it rather than constructing their own.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock  # noqa: F401 — MagicMock kept for downstream tests

import numpy as np
import pytest
from fastapi.testclient import TestClient

# Dual-layout shim (R6 audit, template-context CI lane): in a scaffolded
# service ``common_utils`` is vendored next to ``app/`` and importable
# via pyproject's pythonpath. In the TEMPLATE repo it lives one level up
# at ``templates/common_utils``, which is NOT on sys.path (rootdir is
# templates/service), so every test importing it collection-errored —
# 52 errors that no CI lane saw before the lane existed. Same pattern as
# the explicit sys.path handling in test_load_payload_matches_schema.py.
try:  # pragma: no cover — environment probe
    import common_utils  # noqa: F401
except ImportError:
    _TEMPLATES_ROOT = Path(__file__).resolve().parents[2]
    if (_TEMPLATES_ROOT / "common_utils" / "__init__.py").exists():
        sys.path.insert(0, str(_TEMPLATES_ROOT))

# Importing locust gevent-monkey-patches ssl/socket process-wide, which
# deadlocks anyio's TestClient portals (observed twice: pytest idle in
# ``gevent/hub.py`` / ``do_epoll_wait`` with frozen CPU — R6 audit
# follow-up). The patch fires at IMPORT time, i.e. during pytest
# COLLECTION — so a ``-m`` marker filter is NOT enough (deselected
# modules are still imported). The only safe exclusion is collection
# itself. ``-p no:locust`` in CI additionally blocks locust's
# self-registered pytest plugin.
#
# The Locust↔API parity contract (test_load_payload_matches_schema.py)
# still runs in CI — in its OWN pytest process with RUN_LOCUST_PARITY=1,
# where the monkey-patch lands before asyncio exists and nothing shares
# the interpreter.
collect_ignore = ["load_test.py"]
if not os.environ.get("RUN_LOCUST_PARITY"):
    collect_ignore.append("test_load_payload_matches_schema.py")


# ---------------------------------------------------------------------------
# Mock model: behaves enough like a sklearn pipeline that fastapi_app does
# not crash. Returns deterministic predictions so assertions can be exact.
# ---------------------------------------------------------------------------
class _MockPipeline:
    """Stand-in for a fitted sklearn Pipeline. predict_proba returns
    P(positive)=0.7 always; predict returns class 1 always. Sufficient for
    structural tests of the API contract — not for model behavior tests.
    """

    feature_names_in_ = np.array(["feature_a", "feature_b", "feature_c"])

    def predict_proba(self, X: Any) -> np.ndarray:
        n = len(X) if hasattr(X, "__len__") else 1
        return np.tile([0.3, 0.7], (n, 1))

    def predict(self, X: Any) -> np.ndarray:
        n = len(X) if hasattr(X, "__len__") else 1
        return np.ones(n, dtype=int)


@pytest.fixture(scope="session", autouse=True)
def _patch_model_loading() -> Iterator[None]:
    """Patch load_model_artifacts so the FastAPI lifespan does not require
    real files. Active for the whole test session.

    NOTE: We deliberately do NOT patch ``warm_up_model``. The real function
    returns ``{"status": "skipped", ...}`` cleanly when ``_background_data``
    is None (the mock does not set it), which is the desired behaviour for
    these structural tests AND lets the dedicated unit tests in
    ``templates/tests/unit/test_warmup.py`` exercise the real implementation
    even when both test directories are collected in the same pytest
    session (see CI: .github/workflows/ci-examples.yml).

    Patching ``warm_up_model`` here previously leaked across the session
    boundary because session-scope autouse fixtures stay active until
    teardown, making the contract-level fake visible to tests outside this
    conftest's directory.
    """
    from unittest.mock import patch

    import app.fastapi_app as fastapi_app_mod

    mock_pipeline = _MockPipeline()

    def _fake_load() -> None:
        fastapi_app_mod._model_pipeline = mock_pipeline

    # Set MODEL_VERSION so the API exposes a deterministic value.
    os.environ.setdefault("MODEL_VERSION", "test-0.0.1")

    # ``_start_prediction_logger`` / ``_stop_prediction_logger`` are
    # awaited by the FastAPI lifespan (``app/main.py``); MagicMock would
    # return a non-awaitable and crash before any test runs. AsyncMock
    # preserves the awaitable contract while staying side-effect free.
    with (
        patch.object(fastapi_app_mod, "load_model_artifacts", _fake_load),
        patch.object(fastapi_app_mod, "_start_prediction_logger", AsyncMock()),
        patch.object(fastapi_app_mod, "_stop_prediction_logger", AsyncMock()),
    ):
        # Pre-populate the global so endpoints that read it directly succeed.
        fastapi_app_mod._model_pipeline = mock_pipeline
        yield


@pytest.fixture(autouse=True)
def _env_hygiene() -> Iterator[None]:
    """Snapshot/restore ``os.environ`` around every test (R6 audit S1-2).

    Several tests toggle env vars like ``PREDICTION_LOG_ENABLED`` or
    ``API_AUTH_ENABLED``; without restoration, a leaked value changes
    the FastAPI lifespan behaviour for every later test in the session
    (the observed failure mode: 52 client-fixture errors when
    ``PREDICTION_LOG_ENABLED=true`` leaked into an environment where
    ``common_utils.prediction_logger`` was not importable). Env set by
    session-scoped fixtures during setup is part of the snapshot and
    therefore survives.
    """
    snapshot = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(snapshot)


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    """Single TestClient bound to the FastAPI app. Used as a context
    manager so the lifespan (load + warmup) runs before tests execute.
    """
    # Import inside the fixture so the autouse patch is active first.
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Sample payloads matching templates/service/app/schemas.py
# ---------------------------------------------------------------------------
@pytest.fixture
def valid_payload() -> dict:
    """Minimal valid PredictionRequest. Customize per service."""
    return {
        "entity_id": "test_entity_001",
        "slice_values": {"country": "MX", "channel": "mobile"},
        "feature_a": 42.0,
        "feature_b": 50000.0,
        "feature_c": "category_A",
    }


@pytest.fixture
def batch_payload(valid_payload: dict) -> dict:
    """Minimal valid BatchPredictionRequest with 2 customers."""
    return {"customers": [valid_payload, {**valid_payload, "entity_id": "test_entity_002"}]}
