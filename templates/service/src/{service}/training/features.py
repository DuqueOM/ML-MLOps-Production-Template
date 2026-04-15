"""Feature engineering for {ServiceName}.

Transforms raw data into model-ready features. This class is used in both
training and inference pipelines to guarantee consistency.

TODO: Replace the example transformations with your actual feature logic.
"""

import logging
from typing import Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# Target column name — change per service
TARGET_COLUMN = "target"


class FeatureEngineer:
    """Feature engineering pipeline.

    This class encapsulates all transformations from raw data to model
    input features. It is used in:
    - Training (train.py)
    - API inference (fastapi_app.py) — same logic, different entry point
    """

    def __init__(self) -> None:
        self._fitted = False

    def transform(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
        """Transform raw DataFrame into features + target.

        Args:
            df: Raw DataFrame with all columns.

        Returns:
            Tuple of (X features DataFrame, y target Series).
        """
        df = df.copy()

        # --- Feature engineering steps ---
        # TODO: Add your service-specific feature engineering here
        # Examples:
        # df["feature_ratio"] = df["feature_a"] / (df["feature_b"] + 1)
        # df["feature_log"] = np.log1p(df["feature_c"])
        # df["feature_bin"] = pd.cut(df["feature_d"], bins=5, labels=False)

        # --- Separate features and target ---
        y = df[TARGET_COLUMN]
        X = df.drop(columns=[TARGET_COLUMN])

        # --- Drop columns not used by the model ---
        # TODO: List columns to exclude (IDs, timestamps used only for splitting, etc.)
        columns_to_drop: list[str] = []
        X = X.drop(columns=[c for c in columns_to_drop if c in X.columns])

        logger.info(
            "Features engineered: %d rows, %d features", len(X), len(X.columns)
        )
        return X, y

    def transform_inference(self, df: pd.DataFrame) -> pd.DataFrame:
        """Transform input for inference (no target column).

        Args:
            df: Input DataFrame from API request.

        Returns:
            Transformed features DataFrame.
        """
        df = df.copy()

        # TODO: Apply the same transformations as transform() but without
        # accessing the target column. Keep this in sync.

        return df
