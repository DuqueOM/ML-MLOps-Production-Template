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
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


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
