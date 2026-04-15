"""Optimized model persistence with integrity validation.

Provides save/load for sklearn models using joblib with:
- Configurable compression (zlib level 3 by default — good size/speed trade-off)
- SHA256 hash validation to detect model corruption
- Metadata extraction (model type, sklearn version, file size, timestamp)
- Proper error handling with descriptive exceptions

Usage:
    from common_utils.model_persistence import save_model, load_model

    # Save with integrity hash
    metadata = save_model(pipeline, "models/model.joblib")
    print(metadata["sha256"])  # "a1b2c3..."

    # Load with integrity validation
    model = load_model("models/model.joblib", expected_hash="a1b2c3...")

    # Load without validation (faster, less safe)
    model = load_model("models/model.joblib")

TODO: In production, store the SHA256 hash in MLflow or a metadata DB
      and validate on every model load to detect silent corruption.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

import joblib

logger = logging.getLogger(__name__)

# Default compression: zlib level 3
# Level 3 gives ~60% of maximum compression at ~20% of the time cost.
# For ML models, going higher (e.g., level 9) saves <5% more space but takes 3-5x longer.
DEFAULT_COMPRESS = ("zlib", 3)

# Pickle protocol 5 (Python 3.8+) supports out-of-band data for large numpy arrays
DEFAULT_PROTOCOL = 5


def _compute_hash(file_path: str | Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def save_model(
    model: Any,
    path: str | Path,
    compress: tuple[str, int] | int = DEFAULT_COMPRESS,
    protocol: int = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    """Save a model to disk with compression and integrity hash.

    Parameters
    ----------
    model : Any
        Trained model (Pipeline, estimator, preprocessor, etc.)
    path : str or Path
        Output file path.
    compress : tuple or int
        Compression setting for joblib.dump.
    protocol : int
        Pickle protocol version.

    Returns
    -------
    dict
        Metadata including sha256, file_size, model_type, timestamp.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    start = time.perf_counter()

    try:
        joblib.dump(model, path, compress=compress, protocol=protocol)
    except Exception as e:
        logger.error("Failed to save model to %s: %s", path, e)
        raise

    elapsed = time.perf_counter() - start
    file_size = path.stat().st_size
    sha256 = _compute_hash(path)

    metadata = {
        "path": str(path),
        "sha256": sha256,
        "file_size_bytes": file_size,
        "file_size_mb": round(file_size / (1024 * 1024), 2),
        "model_type": type(model).__name__,
        "compression": str(compress),
        "protocol": protocol,
        "save_time_seconds": round(elapsed, 3),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    # Try to extract sklearn version
    try:
        import sklearn

        metadata["sklearn_version"] = sklearn.__version__
    except ImportError:
        pass

    logger.info(
        "Model saved: %s (%.2f MB, SHA256=%s, %.3fs)",
        path,
        metadata["file_size_mb"],
        sha256[:12],
        elapsed,
    )
    return metadata


def load_model(
    path: str | Path,
    expected_hash: Optional[str] = None,
) -> Any:
    """Load a model from disk with optional integrity validation.

    Parameters
    ----------
    path : str or Path
        Path to the model file.
    expected_hash : str, optional
        SHA256 hash to validate against. If provided and mismatch,
        raises ValueError.

    Returns
    -------
    Any
        The loaded model.

    Raises
    ------
    FileNotFoundError
        If model file doesn't exist.
    ValueError
        If SHA256 hash doesn't match expected.
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Model file not found: {path}")

    # Validate integrity if hash provided
    if expected_hash:
        actual_hash = _compute_hash(path)
        if actual_hash != expected_hash:
            raise ValueError(
                f"Model integrity check FAILED for {path}.\n"
                f"Expected: {expected_hash}\n"
                f"Actual:   {actual_hash}\n"
                "This may indicate model corruption during transfer."
            )
        logger.info("Integrity check passed: %s", path)

    start = time.perf_counter()
    model = joblib.load(path)
    elapsed = time.perf_counter() - start

    logger.info(
        "Model loaded: %s (type=%s, %.3fs)",
        path,
        type(model).__name__,
        elapsed,
    )
    return model


def get_model_metadata(path: str | Path) -> dict[str, Any]:
    """Extract metadata from a saved model file without fully loading it.

    Returns dict with file_size, sha256, last_modified.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Model file not found: {path}")

    stat = path.stat()
    return {
        "path": str(path),
        "sha256": _compute_hash(path),
        "file_size_bytes": stat.st_size,
        "file_size_mb": round(stat.st_size / (1024 * 1024), 2),
        "last_modified": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(stat.st_mtime)),
    }
