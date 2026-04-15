"""Custom classifiers and model wrappers for {ServiceName}.

Provides a ResampleClassifier that wraps any sklearn estimator with optional
resampling strategies for imbalanced datasets:
- SMOTE oversampling (requires imblearn)
- Random undersampling (requires imblearn)
- Class weight balancing (built-in)

Usage:
    from src.{service}.models import ResampleClassifier
    clf = ResampleClassifier(
        estimator=RandomForestClassifier(),
        strategy="oversample",
        random_state=42,
    )
    clf.fit(X_train, y_train)
    predictions = clf.predict(X_test)

TODO: If your dataset is balanced, set strategy="none" (default) and skip
      imblearn installation entirely.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.utils.validation import check_is_fitted

logger = logging.getLogger(__name__)


class ResampleClassifier(BaseEstimator, ClassifierMixin):
    """Classifier wrapper with resampling for imbalanced datasets.

    Parameters
    ----------
    estimator : sklearn estimator, optional
        Base classifier. Defaults to LogisticRegression if None.
    strategy : {"none", "oversample", "undersample", "class_weight"}
        Resampling strategy:
        - "none"         → No resampling (use for balanced data).
        - "oversample"   → SMOTE on minority class (pip install imbalanced-learn).
        - "undersample"  → Random undersampling of majority class.
        - "class_weight"  → Pass-through; estimator must support class_weight param.
    random_state : int
        Seed for reproducibility.

    Attributes
    ----------
    classes_ : ndarray
        Unique class labels after fit.
    estimator_ : estimator
        Fitted base estimator.
    """

    def __init__(
        self,
        estimator: BaseEstimator | None = None,
        strategy: str = "none",
        random_state: int = 42,
    ) -> None:
        self.estimator = estimator
        self.strategy = strategy
        self.random_state = random_state

    def fit(self, X: pd.DataFrame | np.ndarray, y: pd.Series | np.ndarray) -> ResampleClassifier:
        """Fit with optional resampling.

        Parameters
        ----------
        X : array-like of shape (n_samples, n_features)
        y : array-like of shape (n_samples,)

        Returns
        -------
        self
        """
        from sklearn.linear_model import LogisticRegression

        # Default estimator if none provided
        if self.estimator is None:
            self.estimator_ = LogisticRegression(random_state=self.random_state)
        else:
            self.estimator_ = self.estimator

        self.classes_ = np.unique(y)
        X_resampled, y_resampled = self._apply_resampling(X, y)
        self.estimator_.fit(X_resampled, y_resampled)

        logger.info(
            "ResampleClassifier fitted: strategy='%s', " "original=%d samples, resampled=%d samples",
            self.strategy,
            len(y),
            len(y_resampled),
        )
        return self

    def predict(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        """Predict class labels."""
        check_is_fitted(self, "estimator_")
        return self.estimator_.predict(X)

    def predict_proba(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        """Predict class probabilities."""
        check_is_fitted(self, "estimator_")
        return self.estimator_.predict_proba(X)

    def _apply_resampling(
        self, X: pd.DataFrame | np.ndarray, y: pd.Series | np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """Apply the configured resampling strategy."""
        # Convert pandas to numpy if needed
        if isinstance(X, pd.DataFrame):
            X = X.values
        if isinstance(y, pd.Series):
            y = y.values

        if self.strategy == "none":
            return X, y

        elif self.strategy == "oversample":
            try:
                from imblearn.over_sampling import SMOTE

                smote = SMOTE(random_state=self.random_state)
                return smote.fit_resample(X, y)
            except ImportError:
                logger.warning(
                    "imblearn not installed — falling back to no resampling. "
                    "Install with: pip install imbalanced-learn"
                )
                return X, y

        elif self.strategy == "undersample":
            try:
                from imblearn.under_sampling import RandomUnderSampler

                rus = RandomUnderSampler(random_state=self.random_state)
                return rus.fit_resample(X, y)
            except ImportError:
                logger.warning("imblearn not installed — falling back to no resampling.")
                return X, y

        elif self.strategy == "class_weight":
            # No resampling; the estimator handles class_weight internally
            return X, y

        else:
            raise ValueError(
                f"Unknown resampling strategy: '{self.strategy}'. "
                "Valid options: none, oversample, undersample, class_weight"
            )
