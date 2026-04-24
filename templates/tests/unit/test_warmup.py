"""Unit tests for model warm-up (D-23/D-24).

Warm-up must:
  1. Return "skipped" status if model or background data are missing
  2. Execute a successful dummy predict in normal conditions
  3. Execute SHAP warm-up if the explainer is ready
  4. NEVER raise — failures degrade to a report entry, not an exception
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

# Ensure `app.fastapi_app` resolves: add templates/service to sys.path
_SERVICE_ROOT = Path(__file__).resolve().parents[2] / "service"
sys.path.insert(0, str(_SERVICE_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _stub_module_globals(module, **attrs):
    """Write attributes onto a module's namespace for test isolation."""
    for name, value in attrs.items():
        setattr(module, name, value)


@pytest.fixture
def fastapi_app_module(monkeypatch):
    # Import lazily so the monkeypatch window starts with a clean slate
    import app.fastapi_app as mod  # noqa: WPS433 — intentional local import

    # Snapshot + restore
    original = {k: getattr(mod, k) for k in ("_model_pipeline", "_explainer", "_feature_names", "_background_data")}
    yield mod
    for k, v in original.items():
        setattr(mod, k, v)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestWarmUp:
    def test_skipped_when_model_missing(self, fastapi_app_module):
        _stub_module_globals(fastapi_app_module, _model_pipeline=None, _background_data=None)
        report = fastapi_app_module.warm_up_model()
        assert report["status"] == "skipped"

    def test_skipped_when_background_missing(self, fastapi_app_module):
        _stub_module_globals(fastapi_app_module, _model_pipeline=MagicMock(), _background_data=None)
        report = fastapi_app_module.warm_up_model()
        assert report["status"] == "skipped"

    def test_predict_warmup_measured(self, fastapi_app_module):
        model = MagicMock()
        model.predict_proba = MagicMock(return_value=np.array([[0.4, 0.6]]))
        bg = np.array([[1.0, 2.0, 3.0]])

        _stub_module_globals(
            fastapi_app_module,
            _model_pipeline=model,
            _explainer=None,
            _feature_names=["a", "b", "c"],
            _background_data=bg,
        )
        report = fastapi_app_module.warm_up_model()
        assert report["status"] == "ok"
        assert "predict_warmup_ms" in report
        assert report["predict_warmup_ms"] >= 0
        model.predict_proba.assert_called_once()

    def test_shap_warmup_runs_when_explainer_ready(self, fastapi_app_module):
        model = MagicMock()
        model.predict_proba = MagicMock(return_value=np.array([[0.4, 0.6]]))
        explainer = MagicMock()
        explainer.shap_values = MagicMock(return_value=np.array([[0.1, 0.2, 0.3]]))
        bg = np.array([[1.0, 2.0, 3.0]])

        _stub_module_globals(
            fastapi_app_module,
            _model_pipeline=model,
            _explainer=explainer,
            _feature_names=["a", "b", "c"],
            _background_data=bg,
        )
        report = fastapi_app_module.warm_up_model()
        assert report["status"] == "ok"
        assert "shap_warmup_ms" in report
        explainer.shap_values.assert_called_once()

    def test_predict_failure_does_not_raise(self, fastapi_app_module):
        model = MagicMock()
        model.predict_proba = MagicMock(side_effect=RuntimeError("boom"))
        bg = np.array([[1.0]])

        _stub_module_globals(
            fastapi_app_module,
            _model_pipeline=model,
            _explainer=None,
            _feature_names=["a"],
            _background_data=bg,
        )
        # Must not raise — warm-up is best-effort (D-22 spirit)
        report = fastapi_app_module.warm_up_model()
        assert "predict_warmup_error" in report

    def test_shap_failure_does_not_raise(self, fastapi_app_module):
        model = MagicMock()
        model.predict_proba = MagicMock(return_value=np.array([[0.4, 0.6]]))
        explainer = MagicMock()
        explainer.shap_values = MagicMock(side_effect=RuntimeError("shap boom"))
        bg = np.array([[1.0]])

        _stub_module_globals(
            fastapi_app_module,
            _model_pipeline=model,
            _explainer=explainer,
            _feature_names=["a"],
            _background_data=bg,
        )
        report = fastapi_app_module.warm_up_model()
        assert "predict_warmup_ms" in report
        assert "shap_warmup_error" in report
