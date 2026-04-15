"""Pandera DataFrameModel for {ServiceName} input validation.

Used at three validation points:
1. Before training (fail fast on invalid data)
2. At /predict endpoint (SchemaError → HTTP 422)
3. During drift detection (schema mismatch = immediate alert)

TODO: Replace example fields with your actual features.
"""

import pandera.pandas as pa


class ServiceInputSchema(pa.DataFrameModel):
    """Input data schema for {ServiceName}.

    Each field documents type, constraints, and business meaning.
    """

    # TODO: Define your actual features
    feature_a: float = pa.Field(
        ge=0,
        le=150,
        description="Example numeric feature (e.g., age in years)",
    )
    feature_b: float = pa.Field(
        ge=0,
        description="Example numeric feature (e.g., account balance)",
    )
    feature_c: str = pa.Field(
        isin=["category_A", "category_B", "category_C"],
        description="Example categorical feature",
    )
    target: int = pa.Field(
        isin=[0, 1],
        description="Binary target (0=negative, 1=positive)",
        nullable=True,  # Nullable for inference (no target at predict time)
    )

    class Config:
        coerce = True  # Auto-convert types where possible
        strict = False  # Allow extra columns (e.g., ID, timestamp)
