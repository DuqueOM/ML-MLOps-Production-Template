"""Training fairness gate contracts.

These tests keep the training path aligned with ADR-021: fairness is
evaluated at the same decision threshold selected during model
evaluation, missing protected attributes fail closed, and marginal DIR
values are surfaced to quality gates rather than silently auto-passing.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("mlflow")
pytest.importorskip("optuna")
pytest.importorskip("sklearn")

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

train_module = importlib.import_module("{@ service_slug @}.training.train")


class _StaticProbPipeline:
    def __init__(self, probabilities: list[float]) -> None:
        self._probabilities = np.asarray(probabilities, dtype=float)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        assert len(X) == len(self._probabilities)
        return np.column_stack([1.0 - self._probabilities, self._probabilities])


class _FairnessOnlyTrainer:
    def __init__(self, protected_attributes: list[str]) -> None:
        self.output_dir = Path.cwd()
        self.gates = SimpleNamespace(
            primary_metric="roc_auc",
            primary_threshold=0.80,
            secondary_metric="f1",
            secondary_threshold=0.55,
            protected_attributes=protected_attributes,
            fairness_threshold=0.80,
        )

    _fairness_check = train_module.Trainer._fairness_check
    _quality_gates = train_module.Trainer._quality_gates


def test_fairness_uses_operating_threshold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    trainer = _FairnessOnlyTrainer(["segment"])
    splits = {
        "X_test": pd.DataFrame({"segment": ["A", "A", "A", "B", "B", "B"]}),
        "y_test": pd.Series([1, 1, 1, 1, 1, 1]),
    }
    pipeline = _StaticProbPipeline([0.45, 0.46, 0.47, 0.90, 0.91, 0.92])

    metrics = trainer._fairness_check(pipeline, splits, threshold=0.45)

    assert metrics["dir_segment"] == 1.0
    assert (tmp_path / "fairness.json").exists()


def test_missing_protected_attribute_fails_quality_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    trainer = _FairnessOnlyTrainer(["missing_attr"])
    splits = {
        "X_test": pd.DataFrame({"feature": [0, 1, 2, 3]}),
        "y_test": pd.Series([0, 1, 0, 1]),
    }
    pipeline = _StaticProbPipeline([0.1, 0.9, 0.2, 0.8])

    metrics = trainer._fairness_check(pipeline, splits, threshold=0.5)
    gates = trainer._quality_gates({"roc_auc": 1.0, "f1": 1.0, **metrics})

    assert metrics["dir_missing_attr"] == 0.0
    assert gates["all_passed"] is False
    assert "protected attribute present: missing_attr" in gates["failed"]


def test_consultation_band_blocks_auto_quality_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    trainer = _FairnessOnlyTrainer(["segment"])
    splits = {
        "X_test": pd.DataFrame({"segment": ["A"] * 10 + ["B"] * 10}),
        "y_test": pd.Series([1] * 20),
    }
    pipeline = _StaticProbPipeline([0.9] * 8 + [0.1] * 2 + [0.9] * 10)

    metrics = trainer._fairness_check(pipeline, splits, threshold=0.5)
    gates = trainer._quality_gates({"roc_auc": 1.0, "f1": 1.0, **metrics})

    assert 0.80 <= metrics["dir_segment"] < 0.85
    assert metrics["fairness_consult_segment"] == 1.0
    assert gates["all_passed"] is False
    assert "DIR(segment) outside consultation band" in gates["failed"]
