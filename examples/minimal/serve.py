"""FastAPI serving layer for fraud detection.

Demonstrates the complete async inference pattern:
- ThreadPoolExecutor for CPU-bound predict (never blocks event loop)
- SHAP KernelExplainer in original feature space
- Prometheus metrics (counter, histogram, gauge)
- Health endpoint for K8s liveness/readiness probes

Run:
    python train.py          # First, train the model
    uvicorn serve:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from prometheus_client import Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel, Field
from starlette.responses import Response

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class FraudRequest(BaseModel):
    amount: float = Field(ge=0, description="Transaction amount in USD")
    hour: int = Field(ge=0, le=23, description="Hour of transaction (0-23)")
    is_foreign: bool = Field(description="Whether transaction is international")
    merchant_risk: float = Field(ge=0, le=1, description="Merchant risk score")
    distance_from_home: float = Field(ge=0, description="Distance from home in km")


class FraudResponse(BaseModel):
    prediction_score: float
    risk_level: str
    model_version: str
    explanation: Optional[dict] = None


# ---------------------------------------------------------------------------
# Global state — loaded once at startup
# ---------------------------------------------------------------------------
_pipeline = None
_explainer = None
_feature_names: list[str] = []
_background_data: Optional[np.ndarray] = None

# Warm-up flag (D-23) — /ready returns 503 until True so K8s does not
# route the first cold-cache request and violate the P95 SLO. Aligned
# with the canonical pattern in templates/service/app/main.py
# (May 2026 audit MED-9: minimal example was missing this gate).
_warmed_up: bool = False

# Thread pool for CPU-bound inference — NEVER block the event loop.
# max_workers is bounded by the K8s CPU limit so the demo mirrors the
# CPU-aware sizing used in the full template.
_executor = ThreadPoolExecutor(
    max_workers=min(int(os.getenv("INFERENCE_CPU_LIMIT", "4")), os.cpu_count() or 4),
    thread_name_prefix="ml-infer",
)

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------
predictions_total = Counter("fraud_predictions_total", "Total predictions", ["risk_level"])
request_latency = Histogram(
    "fraud_request_duration_seconds",
    "Inference latency",
    ["endpoint"],
    buckets=[0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0],
)
score_distribution = Histogram(
    "fraud_prediction_score",
    "Score distribution",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
)
model_info_gauge = Gauge("fraud_model_info", "Model loaded", ["version"])


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------
def load_artifacts() -> None:
    global _pipeline, _explainer, _feature_names, _background_data

    model_path = os.getenv("MODEL_PATH", "artifacts/model.joblib")
    _pipeline = joblib.load(model_path)
    logger.info("Model loaded from %s", model_path)

    bg_path = os.getenv("BACKGROUND_DATA_PATH", "artifacts/background.csv")
    if Path(bg_path).exists():
        try:
            import shap

            bg_df = pd.read_csv(bg_path)
            _feature_names = list(bg_df.columns)
            _background_data = bg_df.values[:50]
            _explainer = shap.KernelExplainer(_predict_proba_wrapper, _background_data)
            logger.info("SHAP KernelExplainer initialized with %d samples", len(_background_data))
        except ImportError:
            logger.warning("shap not installed — explanations disabled")
        except Exception as e:
            logger.warning("SHAP init failed: %s", e)
    else:
        logger.info("No background data — SHAP disabled")

    model_info_gauge.labels(version=os.getenv("MODEL_VERSION", "0.1.0")).set(1)


def _predict_proba_wrapper(X_array: np.ndarray) -> np.ndarray:
    """SHAP wrapper: numpy → DataFrame → predict_proba.

    KernelExplainer passes raw numpy. Without this wrapper, SHAP would compute
    in post-ColumnTransformer space → wrong feature names. This ensures SHAP
    runs in the ORIGINAL feature space.
    """
    X_df = pd.DataFrame(X_array, columns=_feature_names)
    return _pipeline.predict_proba(X_df)[:, 1]


# ---------------------------------------------------------------------------
# Sync prediction (runs in thread pool, NOT on event loop)
# ---------------------------------------------------------------------------
def _sync_predict(input_dict: dict, explain: bool) -> dict:
    start = time.perf_counter()
    df = pd.DataFrame([input_dict])
    prob = float(_pipeline.predict_proba(df)[:, 1][0])

    risk_level = "HIGH" if prob >= 0.7 else ("MEDIUM" if prob >= 0.4 else "LOW")
    predictions_total.labels(risk_level=risk_level).inc()
    score_distribution.observe(prob)

    result = {
        "prediction_score": round(prob, 4),
        "risk_level": risk_level,
        "model_version": os.getenv("MODEL_VERSION", "0.1.0"),
    }

    if explain and _explainer is not None:
        try:
            shap_values = _explainer.shap_values(df.values, nsamples=100)
            base_value = float(_explainer.expected_value)
            contribs = {_feature_names[i]: round(float(shap_values[0][i]), 6) for i in range(len(_feature_names))}
            reconstructed = base_value + sum(contribs.values())

            result["explanation"] = {
                "method": "kernel_explainer",
                "base_value": round(base_value, 6),
                "feature_contributions": contribs,
                "top_risk_factors": [
                    f"{k} (+{v:.4f})"
                    for k, v in sorted(contribs.items(), key=lambda x: x[1], reverse=True)[:3]
                    if v > 0
                ],
                "consistency_check": {
                    "actual": round(prob, 6),
                    "reconstructed": round(reconstructed, 6),
                    "difference": round(abs(prob - reconstructed), 6),
                    "passed": abs(prob - reconstructed) < 0.01,
                },
            }
        except Exception as e:
            result["explanation"] = {"method": "error", "detail": str(e)}

    request_latency.labels(endpoint="/predict").observe(time.perf_counter() - start)
    return result


# ---------------------------------------------------------------------------
# Warm-up (D-23/D-24) — execute throwaway predict + SHAP at startup so the
# first real request is served with hot caches. Mirrors the canonical
# pattern in templates/service/app/fastapi_app.py::warm_up_model.
# ---------------------------------------------------------------------------
def warm_up() -> dict:
    if _pipeline is None or _background_data is None:
        return {"status": "skipped"}
    report: dict = {"status": "ok"}
    sample_df = pd.DataFrame(_background_data[:1], columns=_feature_names)
    start = time.perf_counter()
    try:
        _ = _pipeline.predict_proba(sample_df)[:, 1]
        report["predict_warmup_ms"] = round((time.perf_counter() - start) * 1000, 2)
    except Exception as e:  # noqa: BLE001 - best-effort
        report["predict_warmup_error"] = str(e)
    if _explainer is not None:
        start = time.perf_counter()
        try:
            _ = _explainer.shap_values(sample_df.values, nsamples=50, silent=True)
            report["shap_warmup_ms"] = round((time.perf_counter() - start) * 1000, 2)
        except Exception as e:  # noqa: BLE001
            report["shap_warmup_error"] = str(e)
    return report


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model artifacts → warm up → flip _warmed_up; drain at shutdown."""
    global _warmed_up
    logger.info("Starting Fraud Detection API...")
    load_artifacts()
    try:
        report = warm_up()
        logger.info("Warm-up complete: %s", report)
    except Exception as e:  # noqa: BLE001 - best-effort
        logger.warning("Warm-up raised unexpectedly (continuing): %s", e)
    _warmed_up = True
    yield
    logger.info("Shutting down.")
    _warmed_up = False  # K8s will stop sending traffic via readiness


app = FastAPI(
    title="Fraud Detection API",
    description="Minimal example — async inference with SHAP + Prometheus",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    """Liveness probe — always 200 if the event loop is alive."""
    return {
        "status": "healthy",
        "version": os.getenv("MODEL_VERSION", "0.1.0"),
    }


@app.get("/ready")
async def ready():
    """Readiness probe — 503 until model loaded AND warm-up complete (D-23)."""
    from fastapi.responses import JSONResponse

    model_loaded = _pipeline is not None
    is_ready = model_loaded and _warmed_up
    body = {
        "status": "ready" if is_ready else "not_ready",
        "model_loaded": model_loaded,
        "warmed_up": _warmed_up,
        "version": os.getenv("MODEL_VERSION", "0.1.0"),
    }
    return JSONResponse(content=body, status_code=200 if is_ready else 503)


@app.post("/predict", response_model=FraudResponse)
async def predict(req: FraudRequest, explain: bool = False):
    if _pipeline is None or not _warmed_up:
        raise HTTPException(503, "Service not ready")
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(_executor, partial(_sync_predict, req.model_dump(), explain))
    return FraudResponse(**result)


@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type="text/plain")


@app.get("/")
async def root():
    return {"service": "Fraud Detection API", "docs": "/docs"}
