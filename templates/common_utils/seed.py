"""Centralized seed setting for ML reproducibility.

Sets seeds for Python random, NumPy, and optionally PyTorch and TensorFlow.
Supports explicit seed argument, environment variable fallback, and default.

Usage:
    from common_utils.seed import set_seed
    set_seed(42)                       # Explicit seed
    set_seed()                         # Uses RANDOM_SEED env var or default 42

    # In training scripts:
    import os
    os.environ["RANDOM_SEED"] = "123"
    set_seed()                         # Uses 123

TODO: If you don't use PyTorch or TensorFlow, the imports are optional
      and will be skipped with a debug log message.
"""

from __future__ import annotations

import logging
import os
import random
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_SEED = 42


def set_seed(seed: Optional[int] = None) -> int:
    """Set random seed for reproducibility across all ML frameworks.

    Priority:
    1. Explicit seed argument
    2. RANDOM_SEED environment variable
    3. Default (42)

    Parameters
    ----------
    seed : int, optional
        Seed value. If None, reads RANDOM_SEED env var or uses 42.

    Returns
    -------
    int
        The seed value that was set.
    """
    if seed is None:
        seed = int(os.environ.get("RANDOM_SEED", str(DEFAULT_SEED)))

    # Python built-in random
    random.seed(seed)

    # NumPy
    np.random.seed(seed)

    # PyTorch (optional)
    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
            # Deterministic mode (slower but reproducible)
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
        logger.debug("PyTorch seed set to %d", seed)
    except ImportError:
        logger.debug("PyTorch not installed — skipping torch seed")

    # TensorFlow (optional)
    try:
        import tensorflow as tf

        tf.random.set_seed(seed)
        logger.debug("TensorFlow seed set to %d", seed)
    except ImportError:
        logger.debug("TensorFlow not installed — skipping tf seed")

    logger.info("Random seed set to %d (python, numpy, torch?, tf?)", seed)
    return seed
