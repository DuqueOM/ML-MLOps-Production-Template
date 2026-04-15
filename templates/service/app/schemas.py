"""Pydantic request/response schemas for the {ServiceName} API.

Define all input features with type, range, and description.
Replace the example fields below with your actual service features.
"""

from typing import Optional

from pydantic import BaseModel, Field


class PredictionRequest(BaseModel):
    """Input schema for the /predict endpoint.

    Each field documents:
    - Type and constraints (ge, le, regex, etc.)
    - Business meaning
    """

    # TODO: Replace these example features with actual service features
    feature_a: float = Field(
        ..., ge=0, le=150, description="Example numeric feature (e.g., age)"
    )
    feature_b: float = Field(
        ..., ge=0, description="Example numeric feature (e.g., balance)"
    )
    feature_c: str = Field(
        ..., description="Example categorical feature (e.g., category)"
    )

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
    """SHAP consistency verification: base_value + sum(SHAP) ≈ prediction."""

    actual_score: float
    reconstructed: float
    difference: float
    passed: bool


class Explanation(BaseModel):
    """SHAP feature contributions for the prediction."""

    method: str = "kernel_explainer"
    base_value: float
    feature_contributions: dict[str, float]
    top_risk_factors: list[str]
    top_protective_factors: list[str]
    consistency_check: ConsistencyCheck
    computation_time_ms: float


class PredictionResponse(BaseModel):
    """Output schema for the /predict endpoint."""

    prediction_score: float = Field(
        ..., ge=0, le=1, description="Model output probability"
    )
    risk_level: str = Field(
        ..., description="Risk classification: LOW, MEDIUM, or HIGH"
    )
    model_version: str = Field(..., description="Version of the model in production")
    explanation: Optional[Explanation] = Field(
        None, description="SHAP explanation (only when ?explain=true)"
    )
