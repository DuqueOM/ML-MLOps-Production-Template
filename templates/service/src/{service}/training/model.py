"""Model definition for {ServiceName}.

Defines the sklearn Pipeline with preprocessing and model.
The model choice should be documented in an ADR with alternatives
and measured trade-offs.

TODO: Replace with your actual model architecture.
"""

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

# ---------------------------------------------------------------------------
# Feature column definitions — customize per service
# ---------------------------------------------------------------------------
NUMERIC_FEATURES: list[str] = [
    # TODO: List your numeric feature column names
    "feature_a",
    "feature_b",
]

CATEGORICAL_FEATURES: list[str] = [
    # TODO: List your categorical feature column names
    "feature_c",
]


def build_pipeline(**model_params) -> Pipeline:
    """Build the full sklearn Pipeline.

    Args:
        **model_params: Hyperparameters passed from Optuna or defaults.

    Returns:
        Unfitted sklearn Pipeline.
    """
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), NUMERIC_FEATURES),
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                CATEGORICAL_FEATURES,
            ),
        ],
        remainder="drop",
    )

    # TODO: Replace with your model choice (see ADR)
    # Options: GradientBoostingClassifier, XGBClassifier, LGBMClassifier,
    #          StackingClassifier, etc.
    model = GradientBoostingClassifier(
        n_estimators=model_params.get("n_estimators", 200),
        max_depth=model_params.get("max_depth", 5),
        learning_rate=model_params.get("learning_rate", 0.1),
        random_state=42,
    )

    pipeline = Pipeline(
        [
            ("preprocessor", preprocessor),
            ("model", model),
        ]
    )

    return pipeline
