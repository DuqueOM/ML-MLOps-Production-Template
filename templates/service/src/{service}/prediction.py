"""Prediction handler for {ServiceName}.

Provides model loading and prediction logic for both single and batch inference.
Used by the FastAPI app and by CLI batch processing.

Usage:
    predictor = ServicePredictor.from_files("models/model.joblib")
    result_df = predictor.predict(input_df)
    predictor.predict_batch("data/new_customers.csv", "results/predictions.csv")

TODO: Rename ServicePredictor → {ServiceName}Predictor.
TODO: Adjust risk_level thresholds for your domain.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

logger = logging.getLogger(__name__)


class ServicePredictor:
    """Model loading and prediction for {ServiceName}.

    Handles both Pipeline models (preprocessor built-in) and legacy models
    where the preprocessor is saved separately.

    Parameters
    ----------
    model : Pipeline or estimator
        Trained model with predict and predict_proba.
    preprocessor : optional
        Separate fitted preprocessor (only for legacy models).
    """

    def __init__(self, model: Any, preprocessor: Any = None) -> None:
        self.model = model
        self.preprocessor = preprocessor

    @classmethod
    def from_files(
        cls,
        model_path: str | Path,
        preprocessor_path: Optional[str | Path] = None,
    ) -> ServicePredictor:
        """Load model from joblib file.

        If the model is a sklearn Pipeline, the preprocessor is already
        included. Pass preprocessor_path only for legacy separate-file models.
        """
        model = joblib.load(model_path)
        preprocessor = None

        if preprocessor_path:
            try:
                preprocessor = joblib.load(preprocessor_path)
                logger.info("Loaded preprocessor from %s", preprocessor_path)
            except Exception as e:
                logger.warning("Could not load preprocessor: %s", e)

        # If model is a Pipeline, check if it already has a preprocessor
        if isinstance(model, Pipeline) and preprocessor is not None:
            logger.warning(
                "Model is a Pipeline but a separate preprocessor was also provided. "
                "The Pipeline's built-in preprocessor will be used."
            )
            preprocessor = None

        logger.info("Model loaded from %s (type=%s)", model_path, type(model).__name__)
        return cls(model, preprocessor)

    def predict(self, X: pd.DataFrame) -> pd.DataFrame:
        """Make predictions on a DataFrame.

        Returns DataFrame with columns: prediction, probability, risk_level.

        TODO: Adjust risk_level thresholds for your domain. For example:
        - Churn: HIGH >= 0.7, MEDIUM >= 0.4, LOW < 0.4
        - Fraud: HIGH >= 0.9, MEDIUM >= 0.5, LOW < 0.5
        """
        if isinstance(self.model, Pipeline):
            predictions = self.model.predict(X)
            probabilities = self.model.predict_proba(X)[:, 1]
        else:
            if self.preprocessor is not None:
                X_transformed = self.preprocessor.transform(X)
            else:
                X_transformed = X
            predictions = self.model.predict(X_transformed)
            probabilities = self.model.predict_proba(X_transformed)[:, 1]

        # Risk level classification — TODO: adjust thresholds per domain
        risk_levels = np.where(
            probabilities >= 0.7, "HIGH",
            np.where(probabilities >= 0.4, "MEDIUM", "LOW"),
        )

        result = pd.DataFrame({
            "prediction": predictions,
            "probability": np.round(probabilities, 4),
            "risk_level": risk_levels,
        })

        logger.info(
            "Predictions: %d total — HIGH=%d, MEDIUM=%d, LOW=%d",
            len(result),
            (risk_levels == "HIGH").sum(),
            (risk_levels == "MEDIUM").sum(),
            (risk_levels == "LOW").sum(),
        )
        return result

    def predict_batch(
        self,
        input_path: str | Path,
        output_path: str | Path,
        include_proba: bool = True,
        threshold: float = 0.5,
    ) -> pd.DataFrame:
        """Batch prediction on a CSV file.

        Parameters
        ----------
        input_path : path to input CSV
        output_path : path to save predictions CSV
        include_proba : include probability column
        threshold : classification threshold (default 0.5)

        Returns
        -------
        DataFrame with original data + prediction columns.
        """
        df = pd.read_csv(input_path)
        logger.info("Batch prediction: loaded %d rows from %s", len(df), input_path)

        result = self.predict(df)

        # Merge predictions with original data
        output_df = pd.concat([df, result], axis=1)

        if not include_proba:
            output_df = output_df.drop(columns=["probability"], errors="ignore")

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_df.to_csv(output_path, index=False)
        logger.info("Batch predictions saved to %s (%d rows)", output_path, len(output_df))

        return output_df

    def explain_prediction(self, X: pd.DataFrame) -> dict[str, Any]:
        """Basic prediction explanation (for advanced SHAP, see explainability.py).

        Returns prediction, probability, risk_level, and input features.
        """
        result = self.predict(X.head(1))
        return {
            "prediction": int(result["prediction"].iloc[0]),
            "probability": float(result["probability"].iloc[0]),
            "risk_level": str(result["risk_level"].iloc[0]),
            "input_features": X.head(1).to_dict(orient="records")[0],
        }
