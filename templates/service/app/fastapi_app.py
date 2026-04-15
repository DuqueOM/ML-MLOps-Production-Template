"""Async inference endpoints with ThreadPoolExecutor and optional SHAP.

CPU-bound model.predict() runs in a thread pool so the asyncio event loop
stays responsive. SHAP KernelExplainer is used for complex ensemble models.
"""

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Optional

import joblib
import numpy as np
import pandas as pd
import shap
from fastapi import APIRouter, HTTPException
from prometheus_client import Counter, Gauge, Histogram, generate_latest
from starlette.responses import Response

from app.schemas import PredictionRequest, PredictionResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Global state (loaded once at startup via load_model_artifacts)
# ---------------------------------------------------------------------------
_model_pipeline = None
_explainer: Optional[shap.KernelExplainer] = None
_feature_names: list[str] = []
_background_data: Optional[np.ndarray] = None

# ---------------------------------------------------------------------------
# Thread pool for CPU-bound inference — never block the event loop
# ---------------------------------------------------------------------------
_inference_executor = ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="ml-infer",
)

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------
predictions_total = Counter(
    "{service}_predictions_total",
    "Total predictions by risk level",
    ["risk_level", "model_version"],
)

prediction_latency = Histogram(
    "{service}_prediction_latency_seconds",
    "Prediction latency in seconds",
    ["endpoint"],
    buckets=[0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0],
)

prediction_score_distribution = Histogram(
    "{service}_prediction_score",
    "Distribution of model output scores",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
)

model_info = Gauge(
    "{service}_model_info",
    "Model metadata",
    ["version"],
)


def load_model_artifacts() -> None:
    """Load model pipeline and SHAP background data.

    Called once at startup. Models are downloaded by the K8s init container
    into /models/ (emptyDir volume).
    """
    import os

    global _model_pipeline, _explainer, _feature_names, _background_data

    model_path = os.getenv("MODEL_PATH", "/models/model.joblib")
    _model_pipeline = joblib.load(model_path)

    # Load background data for SHAP (50 representative samples)
    bg_path = os.getenv("BACKGROUND_DATA_PATH", "data/reference/background.csv")
    if os.path.exists(bg_path):
        bg_df = pd.read_csv(bg_path)
        _feature_names = list(bg_df.columns)
        _background_data = bg_df.values[:50]

        # Initialize KernelExplainer with predict_proba_wrapper
        _explainer = shap.KernelExplainer(
            model=_predict_proba_wrapper,
            data=_background_data,
        )

    version = os.getenv("MODEL_VERSION", "0.1.0")
    model_info.labels(version=version).set(1)
    logger.info("Loaded model from %s (version=%s)", model_path, version)


def _predict_proba_wrapper(X_array: np.ndarray) -> np.ndarray:
    """SHAP wrapper — computes in ORIGINAL feature space, not transformed.

    KernelExplainer passes numpy arrays; our pipeline expects DataFrames
    with column names. Without this wrapper, SHAP would compute in the
    post-ColumnTransformer space → uninterpretable feature names.
    """
    X_df = pd.DataFrame(X_array, columns=_feature_names)
    return _model_pipeline.predict_proba(X_df)[:, 1]


def _sync_predict(input_dict: dict, explain: bool) -> dict:
    """CPU-bound prediction — runs in thread pool, does NOT block event loop.

    Args:
        input_dict: Raw feature dict from the request.
        explain: Whether to include SHAP feature contributions.

    Returns:
        Prediction response dict.
    """
    import os

    start = time.perf_counter()
    df = pd.DataFrame([input_dict])

    # --- Inference ---
    prob = float(_model_pipeline.predict_proba(df)[:, 1][0])

    # --- Risk level classification ---
    # TODO: Replace thresholds with service-specific values (see ADR)
    if prob >= 0.7:
        risk_level = "HIGH"
    elif prob >= 0.4:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    version = os.getenv("MODEL_VERSION", "0.1.0")
    predictions_total.labels(risk_level=risk_level, model_version=version).inc()
    prediction_score_distribution.observe(prob)

    response = {
        "prediction_score": round(prob, 4),
        "risk_level": risk_level,
        "model_version": version,
    }

    # --- Optional SHAP explanation ---
    if explain and _explainer is not None:
        shap_values = _explainer.shap_values(df.values, nsamples=100)
        base_value = float(_explainer.expected_value)

        contributions = {
            _feature_names[i]: round(float(shap_values[0][i]), 6)
            for i in range(len(_feature_names))
        }

        # Consistency check: base_value + sum(SHAP) ≈ prediction
        reconstructed = base_value + sum(contributions.values())

        sorted_contribs = sorted(
            contributions.items(), key=lambda x: x[1], reverse=True
        )
        top_risk = [f"{k} (+{v:.4f})" for k, v in sorted_contribs[:3] if v > 0]
        top_protective = [f"{k} ({v:.4f})" for k, v in sorted_contribs[-3:] if v < 0]

        response["explanation"] = {
            "method": "kernel_explainer",
            "base_value": round(base_value, 6),
            "feature_contributions": contributions,
            "top_risk_factors": top_risk,
            "top_protective_factors": top_protective,
            "consistency_check": {
                "actual_score": round(prob, 6),
                "reconstructed": round(reconstructed, 6),
                "difference": round(abs(prob - reconstructed), 6),
                "passed": abs(prob - reconstructed) < 0.01,
            },
            "computation_time_ms": round((time.perf_counter() - start) * 1000, 1),
        }

    elapsed = time.perf_counter() - start
    prediction_latency.labels(endpoint="/predict").observe(elapsed)

    return response


@router.post("/predict", response_model=PredictionResponse)
async def predict(
    input_data: PredictionRequest, explain: bool = False
) -> PredictionResponse:
    """Main prediction endpoint.

    Runs inference in a thread pool to avoid blocking the event loop.
    Add ``?explain=true`` for SHAP feature contributions.
    """
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            _inference_executor,
            partial(_sync_predict, input_data.model_dump(), explain),
        )
        return PredictionResponse(**result)
    except Exception as e:
        logger.exception("Prediction failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/metrics")
async def metrics() -> Response:
    """Prometheus metrics endpoint."""
    return Response(content=generate_latest(), media_type="text/plain")
