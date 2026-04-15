"""Pydantic request/response schemas for the {ServiceName} API.

Define all input features with type, range, and description.
Replace the example fields below with your actual service features.

Schemas provided:
    PredictionRequest       — Single prediction input
    PredictionResponse      — Single prediction output
    BatchPredictionRequest  — Multiple inputs in one request
    BatchPredictionResponse — Multiple outputs
    Explanation             — SHAP feature contribution details
    ConsistencyCheck        — SHAP additivity verification

TODO: Replace example features (feature_a, feature_b, feature_c) with your
      actual domain features. Add Pydantic validators (ge, le, regex, etc.)
      to enforce input ranges and catch invalid data early.
"""

from typing import Any, List, Optional

from pydantic import BaseModel, Field


class PredictionRequest(BaseModel):
    """Input schema for the /predict endpoint.

    Each field documents:
    - Type and constraints (ge, le, regex, etc.)
    - Business meaning

    TODO: Replace these example features with actual service features.
    Example for BankChurn:
        CreditScore: int = Field(..., ge=300, le=850)
        Geography: str = Field(..., pattern="^(France|Germany|Spain)$")
        Gender: str = Field(..., pattern="^(Male|Female)$")
        Age: int = Field(..., ge=18, le=100)
        ...
    """

    feature_a: float = Field(..., ge=0, le=150, description="Example numeric feature (e.g., age)")
    feature_b: float = Field(..., ge=0, description="Example numeric feature (e.g., balance)")
    feature_c: str = Field(..., description="Example categorical feature (e.g., category)")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "feature_a": 42.0,
                    "feature_b": 50000.0,
                    "feature_c": "category_A",
                }
            ]
        }
    }


class ConsistencyCheck(BaseModel):
    """SHAP consistency verification: base_value + sum(SHAP) ≈ prediction.

    This is a mathematical property of SHAP values. If difference > 0.01,
    the wrapper or background data has a bug.
    """

    actual_score: float
    reconstructed: float
    difference: float
    passed: bool


class Explanation(BaseModel):
    """SHAP feature contributions for the prediction.

    method: "kernel_explainer" (always — never TreeExplainer with ensembles)
    base_value: expected model output over background data
    feature_contributions: per-feature SHAP values (original feature space)
    top_risk_factors: features pushing prediction UP
    top_protective_factors: features pushing prediction DOWN
    """

    method: str = "kernel_explainer"
    base_value: Optional[float] = None
    feature_contributions: Optional[dict[str, float]] = None
    top_risk_factors: Optional[list[str]] = None
    top_protective_factors: Optional[list[str]] = None
    consistency_check: Optional[ConsistencyCheck] = None
    computation_time_ms: Optional[float] = None
    detail: Optional[str] = None


class PredictionResponse(BaseModel):
    """Output schema for the /predict endpoint."""

    prediction_score: float = Field(..., ge=0, le=1, description="Model output probability")
    risk_level: str = Field(..., description="Risk classification: LOW, MEDIUM, or HIGH")
    model_version: str = Field(..., description="Version of the model in production")
    explanation: Optional[Explanation] = Field(None, description="SHAP explanation (only when ?explain=true)")


class BatchPredictionRequest(BaseModel):
    """Input schema for the /predict_batch endpoint.

    Accepts a list of individual prediction requests.
    """

    customers: List[PredictionRequest] = Field(
        ..., description="List of inputs to predict", min_length=1, max_length=1000
    )


class BatchPredictionResponse(BaseModel):
    """Output schema for the /predict_batch endpoint."""

    predictions: List[PredictionResponse] = Field(..., description="List of prediction results")
    total_customers: int = Field(..., description="Total number of predictions made")
