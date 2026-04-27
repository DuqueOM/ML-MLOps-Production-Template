"""Configuration management for {ServiceName}.

Loads and validates YAML configuration using Pydantic models.
Each config section has its own Pydantic model with defaults and validation.

Usage:
    config = ServiceConfig.from_yaml("configs/config.yaml")
    print(config.model.type)           # "ensemble"
    print(config.data.target_column)   # "target"

TODO: Rename ServiceConfig → {ServiceName}Config (e.g., ChurnConfig).
TODO: Adjust field names, types, and defaults to match your domain.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, List

import yaml
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

# Demographic-target heuristic (PR-R2-7, audit R2 §4.2). Any of these
# tokens appearing as a substring of `data.target_column` (case-fold)
# triggers a STOP if `quality_gates.protected_attributes` is empty —
# silently shipping a model that classifies people on a protected
# axis without DIR enforcement is exactly the failure ADR-005 forbids.
DEMOGRAPHIC_TARGET_TOKENS: tuple[str, ...] = (
    "gender",
    "race",
    "ethnicity",
    "ethnic",
    "religion",
    "age_group",
    "nationality",
    "marital",
    "disability",
    "sexual_orientation",
    "orientation",
    "pregnancy",
)


# ---------------------------------------------------------------------------
# Sub-configs — one per YAML section
# ---------------------------------------------------------------------------


# TODO: Adjust hyperparameter fields and defaults for your model types.
class LogisticRegressionConfig(BaseModel):
    """Logistic Regression hyperparameters."""

    C: float = 0.1
    class_weight: str = "balanced"
    solver: str = "liblinear"
    max_iter: int = 1000


class RandomForestConfig(BaseModel):
    """Random Forest hyperparameters."""

    n_estimators: int = 100
    max_depth: int = 10
    min_samples_split: int = 10
    min_samples_leaf: int = 5
    class_weight: str = "balanced_subsample"
    n_jobs: int = -1


class EnsembleConfig(BaseModel):
    """Ensemble (VotingClassifier) configuration."""

    voting: str = Field("soft", pattern="^(hard|soft)$")
    weights: List[float] = [0.4, 0.6]


class AdvancedModelConfig(BaseModel):
    """Configuration for XGBoost, LightGBM, or Neural Network models."""

    xgboost_params: dict = Field(default_factory=dict)
    lightgbm_params: dict = Field(default_factory=dict)
    neural_network_params: dict = Field(default_factory=dict)
    compare_models: List[str] = Field(
        default_factory=list,
        description="List of model names to train and compare. Best is auto-selected.",
    )


class ModelConfig(BaseModel):
    """Model training configuration."""

    type: str = "ensemble"
    test_size: float = Field(0.2, ge=0.0, le=1.0)
    random_state: int = 42
    cv_folds: int = Field(5, ge=2)
    resampling_strategy: str = "none"

    # Sub-model configs
    ensemble: EnsembleConfig = EnsembleConfig()
    logistic_regression: LogisticRegressionConfig = LogisticRegressionConfig()
    random_forest: RandomForestConfig = RandomForestConfig()
    advanced: AdvancedModelConfig = AdvancedModelConfig()

    @property
    def ensemble_voting(self) -> str:
        """Backward-compatible alias."""
        return self.ensemble.voting


# TODO: Replace target_column and feature lists with your actual column names.
class DataConfig(BaseModel):
    """Data preprocessing configuration."""

    target_column: str = "target"
    categorical_features: List[str] = []
    numerical_features: List[str] = []
    drop_columns: List[str] = []


class MLflowConfig(BaseModel):
    """MLflow tracking configuration."""

    tracking_uri: str = "file:./mlruns"
    experiment_name: str = "{ServiceName}-Production"
    enabled: bool = True


# ---------------------------------------------------------------------------
# Quality gates — promotion thresholds + fairness requirements (PR-R2-7).
# Loaded from a SEPARATE YAML (`configs/quality_gates.yaml`) so the
# governance bar can evolve independently of model hyperparameters
# AND can be reviewed in isolation in PRs.
#
# `protected_attributes` is REQUIRED and has NO default. The intent is
# to force every adopter to make an explicit choice — either name the
# attributes that warrant DIR enforcement, or pass `[]` and own the
# decision. The combination of `[]` + a target_column that looks
# demographic is rejected by validate_against_data (see below).
# ---------------------------------------------------------------------------


class QualityGatesConfig(BaseModel):
    """Promotion thresholds and fairness requirements.

    All fields validate at construction time. Use
    ``QualityGatesConfig.from_yaml`` to load + validate from disk.
    """

    primary_metric: str = Field(
        ...,
        description="Metric name passed to sklearn cross_val_score (e.g. 'roc_auc', 'f1').",
    )
    primary_threshold: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Minimum acceptable value of `primary_metric` on the held-out test set.",
    )
    secondary_metric: str = Field(
        ...,
        description="Second metric used as a sanity check (e.g. 'f1' alongside roc_auc).",
    )
    secondary_threshold: float = Field(..., ge=0.0, le=1.0)

    fairness_threshold: float = Field(
        0.80,
        ge=0.0,
        le=1.0,
        description="Disparate Impact Ratio floor; standard four-fifths rule defaults to 0.80.",
    )
    latency_sla_ms: float = Field(
        100.0,
        gt=0.0,
        description="P95 inference latency SLA. Read by the load-test target.",
    )

    protected_attributes: List[str] = Field(
        ...,
        description=(
            "Feature names whose DIR will be checked. Empty list means "
            "'I have considered fairness and confirm none apply' — combined "
            "with a demographic-looking target_column it is rejected by "
            "validate_against_data."
        ),
    )

    promotion_threshold: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum delta over the current production baseline required "
            "to auto-promote. 0.0 disables baseline-comparison promotion."
        ),
    )

    @field_validator("primary_metric", "secondary_metric")
    @classmethod
    def _no_whitespace(cls, v: str) -> str:
        if not v or v != v.strip():
            raise ValueError("metric name must be non-empty and have no surrounding whitespace")
        return v

    @field_validator("protected_attributes")
    @classmethod
    def _no_duplicates(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("protected_attributes contains duplicates")
        return v

    @classmethod
    def from_yaml(cls, config_path: str | Path) -> QualityGatesConfig:
        """Load + validate a quality_gates.yaml file.

        Pydantic raises ValidationError if any required field
        (`primary_metric`, `primary_threshold`, `secondary_metric`,
        `secondary_threshold`, `protected_attributes`) is missing.
        """
        config_path = Path(config_path)
        if not config_path.exists():
            raise FileNotFoundError(f"Quality-gates config not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

        if not isinstance(data, dict):
            raise ValueError(f"{config_path} must be a YAML mapping at the top level")

        logger.info("Loaded quality-gates config from %s", config_path)
        return cls(**data)

    def validate_against_data(self, target_column: str) -> None:
        """Cross-config sanity check executed by train.py at startup.

        Raises if:
          - `target_column` matches a demographic token AND
            `protected_attributes` is empty.

        This is the heuristic ADR-005 calls out: shipping a classifier
        whose label is itself a protected attribute, without naming
        any protected attribute for DIR enforcement, is almost
        certainly a fairness gap. Failing closed forces the operator
        to either name the attributes or document why they are
        excluded.
        """
        target_lower = target_column.lower()
        flagged_token = next(
            (tok for tok in DEMOGRAPHIC_TARGET_TOKENS if tok in target_lower),
            None,
        )
        if flagged_token and not self.protected_attributes:
            raise ValueError(
                "STOP: target_column='{tc}' contains demographic token '{tok}' "
                "AND protected_attributes is empty. Either populate "
                "protected_attributes in configs/quality_gates.yaml, or "
                "document an explicit ADR explaining why DIR enforcement "
                "is not applicable here (PR-R2-7, ADR-005).".format(tc=target_column, tok=flagged_token)
            )


# ---------------------------------------------------------------------------
# Root config — aggregates all sub-configs
# ---------------------------------------------------------------------------
# TODO: Rename to {ServiceName}Config.
class ServiceConfig(BaseModel):
    """Complete service configuration loaded from YAML.

    Provides sensible defaults for every field so that a minimal YAML
    (or even empty) still validates. Useful for tests and CI.
    """

    model: ModelConfig = ModelConfig()
    data: DataConfig = DataConfig()
    mlflow: MLflowConfig = MLflowConfig()

    @classmethod
    def from_yaml(cls, config_path: str | Path) -> ServiceConfig:
        """Load configuration from YAML file.

        Parameters
        ----------
        config_path : str or Path
            Path to YAML configuration file.

        Returns
        -------
        config : ServiceConfig
            Validated configuration object.

        Raises
        ------
        FileNotFoundError
            If config file doesn't exist.
        ValidationError
            If YAML values fail Pydantic validation.
        """
        config_path = Path(config_path)

        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_dict = yaml.safe_load(f)
        except yaml.YAMLError as e:
            logger.error("Failed to parse YAML %s: %s", config_path, e)
            raise

        if config_dict is None:
            config_dict = {}

        # Provide defaults for missing top-level sections so older/focused
        # configs still validate (especially in tests/CI).
        if "model" not in config_dict:
            config_dict["model"] = ModelConfig().model_dump()
        if "data" not in config_dict:
            config_dict["data"] = DataConfig().model_dump()
        if "mlflow" not in config_dict:
            config_dict["mlflow"] = MLflowConfig().model_dump()

        logger.info("Loaded configuration from %s", config_path)
        return cls(**config_dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to nested dictionary (useful for MLflow param logging)."""
        return self.model_dump()
