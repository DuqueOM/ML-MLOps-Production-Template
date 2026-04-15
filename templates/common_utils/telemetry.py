"""OpenTelemetry tracing integration for ML services.

Provides request-scoped tracing for FastAPI inference endpoints.
Each prediction gets a trace with:
- Request ID (for correlation)
- Model loading latency
- Preprocessing time
- Inference time
- SHAP explanation time (if enabled)
- Total latency

Works with Jaeger, Zipkin, or any OTLP-compatible backend.
Configured via environment variables (no code changes needed).

Environment variables:
    OTEL_ENABLED          — "true" to enable tracing (default: "false")
    OTEL_SERVICE_NAME     — Service name for traces (default: "ml-service")
    OTEL_EXPORTER_OTLP_ENDPOINT — OTLP collector URL (default: "http://localhost:4317")

Usage:
    from common_utils.telemetry import get_tracer, trace_function

    tracer = get_tracer(__name__)

    with tracer.start_as_current_span("predict") as span:
        span.set_attribute("model.version", "1.0.0")
        result = model.predict(X)
        span.set_attribute("prediction.risk_level", "HIGH")

    # Or as a decorator:
    @trace_function("train_step")
    def train_step(X, y):
        ...

TODO: Set OTEL_ENABLED=true and configure OTEL_EXPORTER_OTLP_ENDPOINT
      in your K8s deployment to enable distributed tracing.
"""

from __future__ import annotations

import functools
import logging
import os
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# OpenTelemetry is optional — gracefully degrade if not installed
_OTEL_AVAILABLE = False
_NOOP_TRACER = None

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    _OTEL_AVAILABLE = True
except ImportError:
    logger.debug("OpenTelemetry not installed — tracing disabled")


def _is_enabled() -> bool:
    """Check if tracing is enabled via environment."""
    return os.environ.get("OTEL_ENABLED", "false").lower() == "true"


def _init_tracer_provider() -> None:
    """Initialize the global TracerProvider with OTLP exporter."""
    if not _OTEL_AVAILABLE or not _is_enabled():
        return

    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )

        service_name = os.environ.get("OTEL_SERVICE_NAME", "ml-service")
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))

        trace.set_tracer_provider(provider)
        logger.info(
            "OpenTelemetry tracing enabled: service=%s endpoint=%s",
            service_name,
            endpoint,
        )
    except Exception as e:
        logger.warning("Failed to initialize OpenTelemetry: %s", e)


# Initialize on import if enabled
_init_tracer_provider()


class _NoopSpan:
    """No-op span for when tracing is disabled."""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def __enter__(self) -> "_NoopSpan":
        return self

    def __exit__(self, *args: Any) -> None:
        pass


class _NoopTracer:
    """No-op tracer for when tracing is disabled."""

    def start_as_current_span(self, name: str, **kwargs: Any) -> _NoopSpan:
        return _NoopSpan()


def get_tracer(name: str) -> Any:
    """Get a tracer instance.

    Returns a real OpenTelemetry tracer if available and enabled,
    otherwise returns a no-op tracer that silently ignores all calls.

    Parameters
    ----------
    name : str
        Tracer name (typically __name__).
    """
    if _OTEL_AVAILABLE and _is_enabled():
        return trace.get_tracer(name)
    return _NoopTracer()


def trace_function(
    span_name: Optional[str] = None,
    attributes: Optional[dict[str, str]] = None,
) -> Callable:
    """Decorator to trace a function execution.

    Usage:
        @trace_function("train_epoch")
        def train_epoch(X, y, epoch):
            ...

        @trace_function(attributes={"component": "preprocessing"})
        def preprocess(df):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = get_tracer(func.__module__)
            name = span_name or f"{func.__module__}.{func.__name__}"

            with tracer.start_as_current_span(name) as span:
                if attributes:
                    for k, v in attributes.items():
                        span.set_attribute(k, v)
                try:
                    result = func(*args, **kwargs)
                    span.set_attribute("status", "ok")
                    return result
                except Exception as e:
                    span.set_attribute("status", "error")
                    span.set_attribute("error.type", type(e).__name__)
                    span.set_attribute("error.message", str(e))
                    raise

        return wrapper

    return decorator
