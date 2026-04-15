"""Async inference endpoints with ThreadPoolExecutor and optional SHAP.

CPU-bound model.predict() runs in a thread pool so the asyncio event loop
stays responsive for concurrent requests. SHAP KernelExplainer is used for
complex ensemble/pipeline models (NEVER TreeExplainer with stacking).

Endpoints provided by this router:
    POST /predict        — Single prediction (+ optional SHAP explanation)
    POST /predict_batch  — Batch prediction for multiple inputs
    GET  /metrics        — Prometheus metrics (scraped by prometheus.io/scrape)

Key invariants:
    - model.predict() NEVER called directly in async endpoint → run_in_executor
    - SHAP computed in ORIGINAL feature space via _predict_proba_wrapper
    - Prometheus metrics: request count, latency histogram, score distribution

TODO: Replace {service} in metric names with your actual service name.
TODO: Adjust risk level thresholds (0.7/0.4) for your domain.
"""

import asyncio
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import List, Optional

import joblib
import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from prometheus_client import Counter, Gauge, Histogram, generate_latest
from starlette.responses import Response

from app.schemas import (
    BatchPredictionRequest,
    BatchPredictionResponse,
    PredictionRequest,
    PredictionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Global state — loaded once at startup via load_model_artifacts()
# ---------------------------------------------------------------------------
_model_pipeline = None
_explainer = None  # shap.KernelExplainer (lazy — only if background data exists)
_feature_names: list[str] = []
_background_data: Optional[np.ndarray] = None

# ---------------------------------------------------------------------------
# Thread pool for CPU-bound inference — NEVER block the event loop
# max_workers=4 is a safe default for ML inference; K8s HPA handles scale-out
# ---------------------------------------------------------------------------
_inference_executor = ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="ml-infer",
)

# ---------------------------------------------------------------------------
# Prometheus metrics — scraped by Prometheus via /metrics endpoint
# TODO: Replace {service} prefix with your actual service name
# ---------------------------------------------------------------------------
predictions_total = Counter(
    "{service}_predictions_total",
    "Total predictions by risk level and model version",
    ["risk_level", "model_version"],
)

request_latency = Histogram(
    "{service}_request_duration_seconds",
    "Request latency in seconds",
    ["endpoint"],
    buckets=[0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0],
)

prediction_score_distribution = Histogram(
    "{service}_prediction_score",
    "Distribution of model output probability scores",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
)

model_loaded_info = Gauge(
    "{service}_model_info",
    "Model metadata (1 = loaded)",
    ["version"],
)

requests_total = Counter(
    "{service}_requests_total",
    "Total HTTP requests by status",
    ["status"],
)


# ---------------------------------------------------------------------------
# Model loading — called once at startup, can be called again for hot-reload
# ---------------------------------------------------------------------------
def load_model_artifacts() -> None:
    """Load model pipeline and optional SHAP background data.

    Models are downloaded by the K8s init container into /models/ (emptyDir).
    Background data for SHAP should be in data/reference/ (50 representative samples).
    """
    global _model_pipeline, _explainer, _feature_names, _background_data

    model_path = os.getenv("MODEL_PATH", "models/model.joblib")
    _model_pipeline = joblib.load(model_path)

    # Load background data for SHAP KernelExplainer (50 representative samples)
    bg_path = os.getenv("BACKGROUND_DATA_PATH", "data/reference/background.csv")
    if os.path.exists(bg_path):
        try:
            bg_df = pd.read_csv(bg_path)
            _feature_names = list(bg_df.columns)
            _background_data = bg_df.values[:50]

            import shap
            _explainer = shap.KernelExplainer(
                model=_predict_proba_wrapper,
                data=_background_data,
            )
            logger.info("SHAP KernelExplainer initialized with %d samples", len(_background_data))
        except ImportError:
            logger.warning("shap not installed — SHAP explanations disabled")
        except Exception as e:
            logger.warning("Failed to initialize SHAP: %s", e)
    else:
        logger.info("No background data at %s — SHAP explanations disabled", bg_path)

    version = os.getenv("MODEL_VERSION", "0.1.0")
    model_loaded_info.labels(version=version).set(1)
    logger.info("Model loaded from %s (version=%s)", model_path, version)


def _predict_proba_wrapper(X_array: np.ndarray) -> np.ndarray:
    """SHAP wrapper: numpy → DataFrame (with column names) → predict_proba.

    KernelExplainer passes raw numpy arrays. Without this wrapper, SHAP would
    compute in the post-ColumnTransformer space → feature names like 'x0_France'
    instead of 'Geography'. This ensures SHAP runs in ORIGINAL feature space.
    """
    X_df = pd.DataFrame(X_array, columns=_feature_names)
    return _model_pipeline.predict_proba(X_df)[:, 1]


# ---------------------------------------------------------------------------
# Synchronous prediction — runs in thread pool via run_in_executor
# ---------------------------------------------------------------------------
def _sync_predict(input_dict: dict, explain: bool) -> dict:
    """CPU-bound prediction logic.

    This function runs inside ThreadPoolExecutor, NOT on the event loop.
    It handles inference, risk classification, metrics, and optional SHAP.
    """
    start = time.perf_counter()
    df = pd.DataFrame([input_dict])

    # --- Inference ---
    prob = float(_model_pipeline.predict_proba(df)[:, 1][0])

    # --- Risk level classification ---
    # TODO: Adjust thresholds for your domain (document in ADR)
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
        try:
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
        except Exception as e:
            logger.warning("SHAP explanation failed: %s", e)
            response["explanation"] = {"method": "error", "detail": str(e)}

    elapsed = time.perf_counter() - start
    request_latency.labels(endpoint="/predict").observe(elapsed)

    return response


def _sync_predict_batch(inputs: List[dict]) -> List[dict]:
    """Batch prediction — CPU-bound, runs in thread pool."""
    start = time.perf_counter()
    df = pd.DataFrame(inputs)

    probas = _model_pipeline.predict_proba(df)[:, 1]
    version = os.getenv("MODEL_VERSION", "0.1.0")

    results = []
    for prob in probas:
        prob = float(prob)
        risk_level = "HIGH" if prob >= 0.7 else ("MEDIUM" if prob >= 0.4 else "LOW")
        predictions_total.labels(risk_level=risk_level, model_version=version).inc()
        prediction_score_distribution.observe(prob)
        results.append({
            "prediction_score": round(prob, 4),
            "risk_level": risk_level,
            "model_version": version,
        })

    elapsed = time.perf_counter() - start
    request_latency.labels(endpoint="/predict_batch").observe(elapsed)
    return results


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/predict", response_model=PredictionResponse)
async def predict(
    input_data: PredictionRequest, explain: bool = False
) -> PredictionResponse:
    """Single prediction endpoint.

    Runs inference in ThreadPoolExecutor to avoid blocking the event loop.
    Add ``?explain=true`` for SHAP feature contributions.
    """
    if _model_pipeline is None:
        requests_total.labels(status="503").inc()
        raise HTTPException(status_code=503, detail="Model not loaded")

    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            _inference_executor,
            partial(_sync_predict, input_data.model_dump(), explain),
        )
        requests_total.labels(status="200").inc()
        return PredictionResponse(**result)
    except Exception as e:
        requests_total.labels(status="500").inc()
        logger.exception("Prediction failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/predict_batch", response_model=BatchPredictionResponse)
async def predict_batch(request: BatchPredictionRequest) -> BatchPredictionResponse:
    """Batch prediction endpoint for multiple inputs.

    Runs all predictions in a single ThreadPoolExecutor call for efficiency.
    """
    if _model_pipeline is None:
        requests_total.labels(status="503").inc()
        raise HTTPException(status_code=503, detail="Model not loaded")

    loop = asyncio.get_running_loop()
    try:
        inputs = [item.model_dump() for item in request.customers]
        results = await loop.run_in_executor(
            _inference_executor,
            partial(_sync_predict_batch, inputs),
        )
        requests_total.labels(status="200").inc()
        predictions = [PredictionResponse(**r) for r in results]
        return BatchPredictionResponse(
            predictions=predictions,
            total_customers=len(predictions),
        )
    except Exception as e:
        requests_total.labels(status="500").inc()
        logger.exception("Batch prediction failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/metrics")
async def metrics() -> Response:
    """Prometheus metrics endpoint — scraped by prometheus.io/scrape annotation."""
    return Response(content=generate_latest(), media_type="text/plain")
