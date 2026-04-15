"""Model explainability using SHAP for {ServiceName}.

Provides global feature importance and per-prediction explanations via SHAP.
Uses KernelExplainer for complex ensemble/pipeline models (NEVER TreeExplainer
with stacking/voting ensembles — it silently produces incorrect values).

Key invariant:
    SHAP values MUST be computed in ORIGINAL feature space, not post-encoding.
    The wrapper function converts numpy arrays back to DataFrames with column
    names so the Pipeline's internal ColumnTransformer handles encoding.

Usage:
    explainer = ModelExplainer(pipeline, background_data, feature_names)
    global_importance = explainer.feature_importance()
    local_explanation = explainer.explain_prediction(single_sample_df)

TODO: Load background data from data/reference/ (50 representative samples).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class ModelExplainer:
    """SHAP-based model explainability.

    Parameters
    ----------
    model : Pipeline or estimator
        Trained model. If Pipeline, the wrapper handles internal preprocessing.
    background_data : DataFrame or ndarray
        Representative samples for KernelExplainer (50 samples recommended).
    feature_names : list of str
        Original feature names (pre-encoding).
    """

    def __init__(
        self,
        model: Any,
        background_data: Optional[pd.DataFrame] = None,
        feature_names: Optional[List[str]] = None,
    ) -> None:
        self.model = model
        self.background_data = background_data
        self.feature_names = feature_names or []
        self._explainer = None
        self._initialized = False

        if background_data is not None:
            self._initialize_explainer()

    def _initialize_explainer(self) -> None:
        """Initialize SHAP KernelExplainer with predict_proba wrapper.

        The wrapper ensures SHAP computes in ORIGINAL feature space.
        """
        try:
            import shap

            # Convert to numpy if DataFrame
            if isinstance(self.background_data, pd.DataFrame):
                bg_array = self.background_data.values
                if not self.feature_names:
                    self.feature_names = list(self.background_data.columns)
            else:
                bg_array = self.background_data

            self._explainer = shap.KernelExplainer(
                model=self._predict_proba_wrapper,
                data=bg_array,
            )
            self._initialized = True
            logger.info(
                "SHAP KernelExplainer initialized with %d background samples",
                len(bg_array),
            )
        except ImportError:
            logger.warning("shap not installed — explainability disabled")
        except Exception as e:
            logger.error("Failed to initialize SHAP explainer: %s", e)

    def _predict_proba_wrapper(self, X_array: np.ndarray) -> np.ndarray:
        """Wrapper: numpy → DataFrame (with column names) → predict_proba.

        KernelExplainer passes raw numpy arrays. Without this wrapper, SHAP
        would compute in the post-ColumnTransformer space → uninterpretable
        feature names like 'x0_France' instead of 'Geography'.
        """
        X_df = pd.DataFrame(X_array, columns=self.feature_names)
        return self.model.predict_proba(X_df)[:, 1]

    def feature_importance(self, n_samples: int = 100) -> Dict[str, float]:
        """Compute global feature importance via mean |SHAP values|.

        Returns dict of feature_name → importance_score, sorted descending.
        """
        if not self._initialized or self._explainer is None:
            return self._fallback_feature_importance()

        try:
            bg_values = (
                self.background_data.values if isinstance(self.background_data, pd.DataFrame) else self.background_data
            )
            shap_values = self._explainer.shap_values(bg_values, nsamples=n_samples)
            mean_abs = np.abs(shap_values).mean(axis=0)

            importance = {self.feature_names[i]: round(float(mean_abs[i]), 6) for i in range(len(self.feature_names))}
            return dict(sorted(importance.items(), key=lambda x: x[1], reverse=True))
        except Exception as e:
            logger.warning("SHAP feature importance failed: %s", e)
            return self._fallback_feature_importance()

    def explain_prediction(
        self,
        X: pd.DataFrame,
        n_samples: int = 100,
    ) -> Dict[str, Any]:
        """Explain a single prediction with SHAP values.

        Returns dict with base_value, feature_contributions, top risk/protective
        factors, and consistency check (base + sum(SHAP) ≈ prediction).
        """
        if not self._initialized or self._explainer is None:
            return self._fallback_explanation(X)

        try:
            X_array = X.values if isinstance(X, pd.DataFrame) else X
            if X_array.ndim == 1:
                X_array = X_array.reshape(1, -1)

            shap_values = self._explainer.shap_values(X_array[:1], nsamples=n_samples)
            base_value = float(self._explainer.expected_value)

            contributions = {
                self.feature_names[i]: round(float(shap_values[0][i]), 6) for i in range(len(self.feature_names))
            }

            # Consistency check: base + sum(SHAP) should ≈ prediction
            predicted = float(self._predict_proba_wrapper(X_array[:1])[0])
            reconstructed = base_value + sum(contributions.values())

            sorted_contribs = sorted(contributions.items(), key=lambda x: x[1], reverse=True)
            top_risk = [f"{k} (+{v:.4f})" for k, v in sorted_contribs[:3] if v > 0]
            top_protective = [f"{k} ({v:.4f})" for k, v in sorted_contribs[-3:] if v < 0]

            return {
                "method": "kernel_explainer",
                "base_value": round(base_value, 6),
                "feature_contributions": contributions,
                "top_risk_factors": top_risk,
                "top_protective_factors": top_protective,
                "consistency_check": {
                    "actual_score": round(predicted, 6),
                    "reconstructed": round(reconstructed, 6),
                    "difference": round(abs(predicted - reconstructed), 6),
                    "passed": abs(predicted - reconstructed) < 0.01,
                },
            }
        except Exception as e:
            logger.warning("SHAP explanation failed: %s", e)
            return self._fallback_explanation(X)

    def _fallback_feature_importance(self) -> Dict[str, float]:
        """Fallback: extract feature importance from model coefficients/attributes."""
        try:
            from sklearn.pipeline import Pipeline

            model = self.model
            if isinstance(model, Pipeline):
                model = model.named_steps.get("model", model[-1])

            if hasattr(model, "feature_importances_"):
                importances = model.feature_importances_
                return {f"feature_{i}": round(float(v), 6) for i, v in enumerate(importances)}
            elif hasattr(model, "coef_"):
                coefs = np.abs(model.coef_.flatten())
                return {f"feature_{i}": round(float(v), 6) for i, v in enumerate(coefs)}
        except Exception:
            pass
        return {"notice": "SHAP not available, no fallback importance"}

    def _fallback_explanation(self, X: pd.DataFrame) -> Dict[str, Any]:
        """Fallback explanation when SHAP is not available."""
        return {
            "method": "fallback",
            "notice": "SHAP explainer not initialized — install shap and provide background data",
            "input_features": X.head(1).to_dict(orient="records")[0] if len(X) > 0 else {},
        }
