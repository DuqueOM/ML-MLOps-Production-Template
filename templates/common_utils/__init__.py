"""Common utilities for ML/MLOps services.

Shared library providing:
- seed: Reproducibility across Python, NumPy, PyTorch, TensorFlow
- model_persistence: Optimized joblib save/load with SHA256 integrity
- logging: Structured JSON logging for production, human-readable for dev
- telemetry: OpenTelemetry tracing instrumentation

Usage:
    from common_utils import set_seed, save_model, load_model, get_logger

Distribution Strategy:
    This library uses a **copy-in** pattern: new-service.sh copies common_utils/
    into each scaffolded service. This is intentional for 1–5 service deployments.

    Trade-offs:
    - ✅ Zero dependency management overhead (no PyPI, no artifact repo)
    - ✅ Each service can diverge if needed (e.g., custom logging format)
    - ⚠️ Updates must be manually propagated to existing services
    - ⚠️ Behavior drift risk if services diverge unintentionally

    When to graduate to a PyPI package:
    - You have >5 services sharing common_utils
    - Multiple teams consume the library
    - You need strict version compatibility guarantees

    To graduate:
    1. Move common_utils/ to its own repo with pyproject.toml
    2. Publish to private PyPI (e.g., GCP Artifact Registry, AWS CodeArtifact)
    3. Pin in each service's requirements.txt: common-utils~=1.0
    4. Add CI to test compatibility across all consumer services

TODO: Copy this directory into your project root as common_utils/
"""

__version__ = "1.0.0"

from .logging import get_logger
from .model_persistence import load_model, save_model
from .seed import set_seed

__all__ = [
    "set_seed",
    "save_model",
    "load_model",
    "get_logger",
]
