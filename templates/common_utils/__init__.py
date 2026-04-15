"""Common utilities for ML/MLOps services.

Shared library providing:
- seed: Reproducibility across Python, NumPy, PyTorch, TensorFlow
- model_persistence: Optimized joblib save/load with SHA256 integrity
- logging: Structured JSON logging for production, human-readable for dev
- telemetry: OpenTelemetry tracing instrumentation

Usage:
    from common_utils import set_seed, save_model, load_model, get_logger

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
