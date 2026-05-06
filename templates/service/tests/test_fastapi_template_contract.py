"""FastAPI template contract tests.

These tests protect the serving invariants that make the scaffold usable
as an enterprise FastAPI ML service instead of a thin demo API.
They are intentionally structural: adopters should keep them and adjust
only service-specific payload tests in ``test_api.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[1]
FASTAPI_APP = SERVICE_ROOT / "app" / "fastapi_app.py"
MAIN_APP = SERVICE_ROOT / "app" / "main.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _function_source(path: Path, function_name: str) -> str:
    source = _source(path)
    lines = source.splitlines()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            return "\n".join(lines[node.lineno - 1 : node.end_lineno])
    raise AssertionError(f"function {function_name!r} not found in {path}")


def _assert_no_direct_model_predict(path: Path, async_endpoint: str) -> None:
    tree = ast.parse(_function_source(path, async_endpoint))
    forbidden_attrs = {"predict", "predict_proba"}
    direct_calls = [
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute) and node.attr in forbidden_attrs
    ]
    assert not direct_calls, (
        f"{async_endpoint} calls model prediction APIs directly: "
        f"{direct_calls}. Async endpoints must delegate CPU-bound inference "
        "to run_in_executor."
    )


def test_openapi_exposes_required_serving_surface(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = set(schema["paths"])

    assert {
        "/predict",
        "/predict_batch",
        "/health",
        "/ready",
        "/metrics",
        "/model/info",
        "/model/reload",
    }.issubset(paths)


def test_async_endpoints_delegate_cpu_bound_inference() -> None:
    predict_source = _function_source(FASTAPI_APP, "predict")
    batch_source = _function_source(FASTAPI_APP, "predict_batch")

    assert "run_in_executor" in predict_source
    assert "partial(_sync_predict" in predict_source
    assert "run_in_executor" in batch_source
    assert "partial(_sync_predict_batch" in batch_source
    _assert_no_direct_model_predict(FASTAPI_APP, "predict")
    _assert_no_direct_model_predict(FASTAPI_APP, "predict_batch")


def test_feature_parity_is_applied_before_model_calls() -> None:
    assert "_prepare_model_features" in _function_source(FASTAPI_APP, "_sync_predict")
    assert "_prepare_model_features" in _function_source(FASTAPI_APP, "_sync_predict_batch")
    assert "_prepare_model_features" in _function_source(FASTAPI_APP, "_predict_proba_wrapper")

    loader_source = _function_source(FASTAPI_APP, "_load_feature_engineer")
    assert "training.features" in loader_source
    assert "FeatureEngineer" in loader_source
    assert "FEATURE_ENGINEERING_REQUIRED" in loader_source


def test_readiness_is_split_from_liveness_and_warmup_gated() -> None:
    health_source = _function_source(MAIN_APP, "health")
    ready_source = _function_source(MAIN_APP, "ready")

    assert '"status": "healthy"' in health_source
    assert "_model_pipeline" in ready_source
    assert "model_loaded and _warmed_up" in ready_source
    assert "status_code=200 if is_ready else 503" in ready_source


def test_auth_and_admin_surfaces_are_explicitly_guarded() -> None:
    main_source = _source(MAIN_APP)
    router_source = _source(FASTAPI_APP)

    assert '"/model/info", dependencies=[Depends(verify_api_key)]' in main_source
    assert '"/model/reload", dependencies=[Depends(require_admin)]' in main_source
    assert "dependencies=[Depends(verify_api_key)]" in router_source
    assert '"/predict"' in router_source
    assert '"/predict_batch"' in router_source


def test_serving_security_and_observability_hooks_are_present() -> None:
    main_source = _source(MAIN_APP)
    router_source = _source(FASTAPI_APP)

    assert "CORS_ORIGINS" in main_source
    assert "if _cors_origins:" in main_source
    assert "install_error_envelope(app)" in main_source
    assert "install_tracing(app)" in main_source
    assert "PredictionEvent(" in router_source
    assert "prediction_log_errors_total.inc()" in router_source
    assert '@router.get("/metrics")' in router_source


def test_modelless_startup_is_restricted_to_dev_and_ci() -> None:
    source = _function_source(FASTAPI_APP, "load_model_artifacts")

    assert "ALLOW_MODELLESS_STARTUP" in source
    assert "_SyntheticGoldenPathModel" in source
    assert "ENVIRONMENT" in source
    assert "staging" in source
    assert "production" in source
    assert "not permitted" in source
