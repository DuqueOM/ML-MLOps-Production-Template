"""FastAPI application entry point for {ServiceName}.

Provides /predict, /health, and /metrics endpoints.
Model inference runs in ThreadPoolExecutor to avoid blocking the event loop.
"""

import logging
import os

from fastapi import FastAPI

from app.fastapi_app import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="{ServiceName} API",
    description="{One sentence describing the business problem solved}",
    version=os.getenv("MODEL_VERSION", "0.1.0"),
    docs_url="/docs",
    redoc_url=None,
)

app.include_router(router)


@app.on_event("startup")
async def startup_event() -> None:
    """Load model and background data at startup — NOT per request."""
    from app.fastapi_app import load_model_artifacts

    load_model_artifacts()
    logger.info("Model artifacts loaded successfully")


@app.get("/health")
async def health() -> dict:
    """Liveness and readiness probe endpoint."""
    return {"status": "healthy", "version": os.getenv("MODEL_VERSION", "0.1.0")}
