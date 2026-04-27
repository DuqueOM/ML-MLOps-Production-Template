"""Tests for QualityGatesConfig (PR-R2-7).

These tests gate every PR that touches `configs/quality_gates.yaml`
or `src/{service}/config.py`. They cover three concerns:

1. **Schema integrity**: every required field must be present;
   missing keys must fail with a clear ValidationError.
2. **Field validation**: numeric ranges, no whitespace in metric
   names, no duplicate protected attributes.
3. **Demographic-target heuristic**: a target column whose name
   contains a demographic token combined with `protected_attributes:
   []` MUST be rejected at load time, not at promotion time.

The tests deliberately do NOT depend on sklearn/optuna/mlflow being
importable — they exercise the config layer in isolation, so they
run in milliseconds in CI.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

# Direct import so the test file works regardless of how scaffolding
# substitutes `{service}` (the test file is processed by the same
# placeholder substitution as the rest of the package).
from {service}.config import (  # type: ignore[import-not-found]
    DEMOGRAPHIC_TARGET_TOKENS,
    QualityGatesConfig,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


VALID_PAYLOAD: dict = {
    "primary_metric": "roc_auc",
    "primary_threshold": 0.80,
    "secondary_metric": "f1",
    "secondary_threshold": 0.55,
    "fairness_threshold": 0.80,
    "latency_sla_ms": 100.0,
    "protected_attributes": [],
    "promotion_threshold": 0.0,
}


def _write_yaml(tmp_path: Path, payload: dict | str, name: str = "quality_gates.yaml") -> Path:
    p = tmp_path / name
    if isinstance(payload, str):
        p.write_text(textwrap.dedent(payload))
    else:
        p.write_text(yaml.safe_dump(payload))
    return p


# ---------------------------------------------------------------------------
# 1. Schema integrity — required keys
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "missing_key",
    [
        "primary_metric",
        "primary_threshold",
        "secondary_metric",
        "secondary_threshold",
        "protected_attributes",
    ],
)
def test_missing_required_field_rejected(tmp_path: Path, missing_key: str) -> None:
    """Pydantic must refuse to load a config that drops any required key."""
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != missing_key}
    cfg_path = _write_yaml(tmp_path, payload)

    with pytest.raises(ValidationError) as exc_info:
        QualityGatesConfig.from_yaml(cfg_path)

    # The missing field name must appear in the error so the operator
    # knows what to fix. This is the regression we are protecting
    # against (silent default = silent governance regression).
    assert missing_key in str(exc_info.value)


def test_valid_payload_loads(tmp_path: Path) -> None:
    cfg_path = _write_yaml(tmp_path, VALID_PAYLOAD)
    cfg = QualityGatesConfig.from_yaml(cfg_path)

    assert cfg.primary_metric == "roc_auc"
    assert cfg.fairness_threshold == 0.80
    assert cfg.protected_attributes == []


def test_optional_fields_take_defaults(tmp_path: Path) -> None:
    minimal = {
        "primary_metric": "roc_auc",
        "primary_threshold": 0.80,
        "secondary_metric": "f1",
        "secondary_threshold": 0.55,
        "protected_attributes": [],
    }
    cfg_path = _write_yaml(tmp_path, minimal)
    cfg = QualityGatesConfig.from_yaml(cfg_path)

    # These three have defaults; loading without them is allowed.
    assert cfg.fairness_threshold == 0.80
    assert cfg.latency_sla_ms == 100.0
    assert cfg.promotion_threshold == 0.0


# ---------------------------------------------------------------------------
# 2. Field validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("primary_threshold", 1.5),    # > 1.0 nonsensical for a probability metric
        ("primary_threshold", -0.1),   # negative
        ("secondary_threshold", 2.0),  # > 1.0
        ("fairness_threshold", -0.1),
        ("latency_sla_ms", 0.0),       # gt=0.0 — must be strictly positive
        ("latency_sla_ms", -10.0),
        ("promotion_threshold", 1.5),
    ],
)
def test_out_of_range_values_rejected(tmp_path: Path, field: str, bad_value: float) -> None:
    payload = dict(VALID_PAYLOAD)
    payload[field] = bad_value
    cfg_path = _write_yaml(tmp_path, payload)

    with pytest.raises(ValidationError):
        QualityGatesConfig.from_yaml(cfg_path)


@pytest.mark.parametrize("metric", ["", " roc_auc", "roc_auc "])
def test_metric_name_whitespace_rejected(tmp_path: Path, metric: str) -> None:
    payload = dict(VALID_PAYLOAD)
    payload["primary_metric"] = metric
    cfg_path = _write_yaml(tmp_path, payload)

    with pytest.raises(ValidationError):
        QualityGatesConfig.from_yaml(cfg_path)


def test_duplicate_protected_attributes_rejected(tmp_path: Path) -> None:
    payload = dict(VALID_PAYLOAD)
    payload["protected_attributes"] = ["gender", "Gender", "gender"]  # duplicate "gender"
    cfg_path = _write_yaml(tmp_path, payload)

    with pytest.raises(ValidationError):
        QualityGatesConfig.from_yaml(cfg_path)


def test_yaml_top_level_must_be_mapping(tmp_path: Path) -> None:
    cfg_path = _write_yaml(tmp_path, "- not\n- a\n- mapping\n")
    with pytest.raises(ValueError, match="must be a YAML mapping"):
        QualityGatesConfig.from_yaml(cfg_path)


def test_missing_file_raises_filenotfound(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        QualityGatesConfig.from_yaml(tmp_path / "does_not_exist.yaml")


# ---------------------------------------------------------------------------
# 3. Demographic-target heuristic — the heart of PR-R2-7
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("target_col", list(DEMOGRAPHIC_TARGET_TOKENS))
def test_demographic_target_with_empty_protected_rejected(target_col: str) -> None:
    cfg = QualityGatesConfig(**VALID_PAYLOAD)  # protected_attributes=[]
    with pytest.raises(ValueError, match="STOP"):
        cfg.validate_against_data(target_col)


def test_demographic_target_substring_match() -> None:
    """The heuristic uses substring match, not exact match."""
    cfg = QualityGatesConfig(**VALID_PAYLOAD)
    # 'gender' inside 'customer_gender_v2' must still trip the heuristic.
    with pytest.raises(ValueError, match="STOP"):
        cfg.validate_against_data("customer_gender_v2")


def test_demographic_target_with_non_empty_protected_passes() -> None:
    payload = dict(VALID_PAYLOAD)
    payload["protected_attributes"] = ["region"]
    cfg = QualityGatesConfig(**payload)

    # Operator named at least one protected attribute → heuristic
    # accepts even a demographic-looking target column. The DIR check
    # at training time then enforces the actual fairness contract.
    cfg.validate_against_data("gender")


def test_non_demographic_target_with_empty_protected_passes() -> None:
    cfg = QualityGatesConfig(**VALID_PAYLOAD)  # protected_attributes=[]

    # `target` / `is_fraud` / `churn_label` etc. are non-demographic
    # by name; the heuristic stays out of the way for technical
    # classification problems.
    cfg.validate_against_data("target")
    cfg.validate_against_data("is_fraud")
    cfg.validate_against_data("churn_label")


def test_demographic_token_match_is_case_insensitive() -> None:
    cfg = QualityGatesConfig(**VALID_PAYLOAD)
    with pytest.raises(ValueError, match="STOP"):
        cfg.validate_against_data("CustomerGENDER")


# ---------------------------------------------------------------------------
# 4. Round-trip integrity
# ---------------------------------------------------------------------------


def test_dump_then_load_round_trip(tmp_path: Path) -> None:
    """A config produced by Pydantic must reload identically."""
    original = QualityGatesConfig(**VALID_PAYLOAD)
    dumped = original.model_dump()
    cfg_path = _write_yaml(tmp_path, dumped)
    reloaded = QualityGatesConfig.from_yaml(cfg_path)
    assert reloaded.model_dump() == dumped
