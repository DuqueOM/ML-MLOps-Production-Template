"""OpenTelemetry tracing — opt-in middleware (May 2026 audit MED-6).

Distributed tracing is an enterprise expectation for multi-cloud serving,
but it is intentionally opt-in (`OTEL_ENABLED=true`) so the default
production image stays slim and the dev experience does not require an
OTLP collector.

Activation contract
-------------------
- ``OTEL_ENABLED=false`` (default): :func:`install_tracing` is a no-op.
  Importing this module never imports `opentelemetry-*` packages.
- ``OTEL_ENABLED=true``: imports ``opentelemetry-api``,
  ``opentelemetry-sdk``, and ``opentelemetry-instrumentation-fastapi``
  (NOT in `requirements.txt` by default — adopter-installed). Wires a
  TracerProvider, an OTLP/HTTP exporter pointed at
  ``OTEL_EXPORTER_OTLP_ENDPOINT``, and adds the FastAPI middleware.

Why a separate module?
----------------------
- The full template ships without OTel deps — adopters with no tracing
  backend should not be forced to install them.
- Cloud-provider stacks have specific exporters (Cloud Trace for GCP,
  ADOT for AWS); a single hard-coded exporter would not fit.

Adopter installation
--------------------
::

    pip install opentelemetry-api opentelemetry-sdk \
                opentelemetry-instrumentation-fastapi \
                opentelemetry-exporter-otlp-proto-http
    export OTEL_ENABLED=true
    export OTEL_SERVICE_NAME=fraud_detector
    export OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector.observability:4318

Then in ``app/main.py``::

    from common_utils.tracing import install_tracing
    install_tracing(app)

Tail-sampling, baggage, and span attributes are configured at the
collector layer (not here) so policy changes don't require a service
redeploy.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def is_enabled() -> bool:
    return os.getenv("OTEL_ENABLED", "false").lower() in {"1", "true", "yes", "on"}


def install_tracing(app: Any) -> None:
    """Wire OpenTelemetry into a FastAPI app.

    No-op when ``OTEL_ENABLED`` is unset/false.
    Logs at WARNING and returns without raising when the OTel packages
    are not installed — tracing failure must NEVER break service startup
    (closed-loop monitoring is "nice to have"; serving must keep running).
    """
    if not is_enabled():
        logger.debug("OTEL_ENABLED unset/false; skipping tracing wiring")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:  # pragma: no cover
        logger.warning(
            "OTEL_ENABLED=true but opentelemetry-* packages not installed: %s. "
            "Service will start without tracing. Install: "
            "`pip install opentelemetry-api opentelemetry-sdk "
            "opentelemetry-instrumentation-fastapi "
            "opentelemetry-exporter-otlp-proto-http`",
            exc,
        )
        return

    service_name = os.getenv("OTEL_SERVICE_NAME") or os.getenv("SERVICE_NAME") or "ml-service"
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": os.getenv("KUBERNETES_NAMESPACE", "ml-services"),
            "service.version": os.getenv("MODEL_VERSION", "0.1.0"),
            "deployment.environment": os.getenv("ENVIRONMENT", "local"),
        }
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
    logger.info(
        "OpenTelemetry tracing enabled (service=%s, endpoint=%s)",
        service_name,
        endpoint,
    )
