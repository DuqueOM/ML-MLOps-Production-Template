"""FastAPI application entry point for {ServiceName}.

Provides:
    /predict       — Single prediction (async, ThreadPoolExecutor)
    /predict_batch — Batch prediction (async, ThreadPoolExecutor)
    /health        — Liveness/readiness probe (healthy/degraded/unhealthy)
    /metrics       — Prometheus metrics endpoint
    /model/info    — Model metadata
    /model/reload  — Hot-reload model without pod restart
    /docs          — Swagger UI

Architecture decisions:
    - CPU-bound inference runs in ThreadPoolExecutor → never blocks event loop
    - CORS enabled for development; restrict in production via config
    - Model loaded at startup via lifespan, NOT per request
    - health returns "degraded" if model is None (not yet loaded)

TODO: Replace {ServiceName} with your actual service name.
TODO: Restrict CORS origins for production deployment.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.fastapi_app import load_model_artifacts, router

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — replaces deprecated @app.on_event("startup")
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model artifacts at startup, clean up at shutdown."""
    logger.info("Starting {ServiceName} API — loading model artifacts...")
    try:
        load_model_artifacts()
        logger.info("Model artifacts loaded successfully")
    except Exception as e:
        logger.error("Failed to load model artifacts: %s", e)
        # Continue startup — health endpoint will report "degraded"
    yield
    logger.info("Shutting down {ServiceName} API")


app = FastAPI(
    title="{ServiceName} API",
    description="{One sentence describing the business problem solved}",
    version=os.getenv("MODEL_VERSION", "0.1.0"),
    docs_url="/docs",
    redoc_url=None,
    lifespan=lifespan,
)

# --- CORS ---
# TODO: Restrict origins in production (e.g., ["https://your-dashboard.example.com"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


# ---------------------------------------------------------------------------
# Health — Liveness and readiness probes
# ---------------------------------------------------------------------------
@app.get("/health")
async def health() -> dict:
    """Health check endpoint for K8s liveness/readiness probes.

    Returns:
        {"status": "healthy"|"degraded", "version": "...", "model_loaded": bool}

    healthy  = model loaded and serving predictions
    degraded = app running but model not available (still starting or load failed)
    """
    from app.fastapi_app import _model_pipeline

    model_loaded = _model_pipeline is not None
    return {
        "status": "healthy" if model_loaded else "degraded",
        "version": os.getenv("MODEL_VERSION", "0.1.0"),
        "model_loaded": model_loaded,
    }


# ---------------------------------------------------------------------------
# Model management
# ---------------------------------------------------------------------------
@app.get("/model/info")
async def model_info() -> dict:
    """Return model metadata."""
    from app.fastapi_app import _model_pipeline

    return {
        "model_loaded": _model_pipeline is not None,
        "model_type": type(_model_pipeline).__name__ if _model_pipeline else None,
        "version": os.getenv("MODEL_VERSION", "0.1.0"),
        "model_path": os.getenv("MODEL_PATH", "models/model.joblib"),
    }


@app.post("/model/reload")
async def model_reload() -> dict:
    """Hot-reload model artifacts without pod restart.

    Useful when init container downloads a new model version.
    """
    try:
        load_model_artifacts()
        return {"status": "reloaded", "version": os.getenv("MODEL_VERSION", "0.1.0")}
    except Exception as e:
        logger.error("Model reload failed: %s", e)
        return {"status": "error", "detail": str(e)}


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------
@app.get("/")
async def root() -> dict:
    """API root — service identification."""
    return {
        "message": "{ServiceName} API",
        "version": os.getenv("MODEL_VERSION", "0.1.0"),
        "docs": "/docs",
    }
