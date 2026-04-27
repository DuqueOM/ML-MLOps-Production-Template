"""EDA gate enforcement at the start of training (PR-B2 stage 2).

Verifies that ``Trainer.__init__`` (more precisely ``_enforce_eda_gate``)
correctly:

1. Raises ``EDAGateError`` when ``leakage_report.json`` exists and shows
   ``status=BLOCKED`` — the load-bearing rule.
2. Lets training proceed when the report is PASSED.
3. Lets training proceed (with a warning) when the artifacts directory
   does not exist — the back-compat path for services that haven't yet
   adopted the canonical EDA contract.
4. Refuses to construct when ``feature_catalog.yaml`` is malformed
   (missing rationale on any transform — D-16 violation).

We construct the gate in isolation, side-stepping the rest of
``Trainer.__init__``: the upstream parts (``QualityGatesConfig`` load
+ FeatureEngineer init) are independently tested in
``test_quality_gates_config.py`` and re-running them here would just
slow the suite without adding coverage.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest
import yaml

# Skip the whole module if the heavy training-module deps (mlflow,
# optuna, sklearn) aren't installed — the gate logic itself is stdlib
# only, but importing ``{service}.training.train`` pulls them in via
# its top-level imports. The scaffold-smoke run installs the real
# requirements.txt so these tests execute there.
pytest.importorskip("mlflow")
pytest.importorskip("optuna")
pytest.importorskip("sklearn")

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Import the templated module directly. The literal ``{service}`` path
# component is intentional — these tests run against the unsubstituted
# template, exactly the way `test_quality_gates_config.py` does.
train_module = importlib.import_module("{service}.training.train")
EDAGateError = train_module.EDAGateError

import common_utils.eda_artifacts as ea  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers — build a minimal Trainer subclass that ONLY exercises the gate.
# ---------------------------------------------------------------------------


class _GateOnlyTrainer:
    """Stand-in for ``Trainer`` that runs only ``_enforce_eda_gate``.

    Building the real ``Trainer`` here would require a valid
    ``configs/quality_gates.yaml`` on disk, MLflow imports succeeding,
    and a target column matching the data fixture. None of that
    matters for testing the gate; this stub binds the bound method
    to a minimal namespace and calls it.
    """

    def __init__(self, eda_artifacts_dir: str | Path | None) -> None:
        self.eda_artifacts_dir = str(eda_artifacts_dir) if eda_artifacts_dir is not None else None

    _enforce_eda_gate = train_module.Trainer._enforce_eda_gate


def _write_summary(artifacts: Path) -> None:
    """Required for completeness checks but the gate itself doesn't read it."""
    (artifacts / ea.EDA_SUMMARY_FILENAME).write_text(
        json.dumps(
            {
                "eda_artifact_version": ea.ARTIFACT_VERSION,
                "target": "y",
                "n_rows": 100,
                "n_columns": 3,
                "runtime_seconds": 0.1,
            }
        )
    )


def _write_leakage(artifacts: Path, *, status: str, blocked: list[str]) -> None:
    payload = {
        "eda_artifact_version": ea.ARTIFACT_VERSION,
        "status": status,
        "blocked_features": blocked,
        "findings": [{"feature": f, "reason": "synthetic", "severity": "P1"} for f in blocked],
        "thresholds": {"correlation": 0.95, "near_perfect": 0.9999, "mi": 0.90},
    }
    (artifacts / ea.LEAKAGE_REPORT_FILENAME).write_text(json.dumps(payload))


def _write_feature_catalog(artifacts: Path, *, valid: bool) -> None:
    transforms = [
        {"name": "log1p_x", "source": "x", "transform": "log1p", "rationale": "skew>1.0 (phase 2)"},
    ]
    if not valid:
        transforms.append({"name": "encode_y", "source": "y", "transform": "target_encode"})  # no rationale
    (artifacts / ea.FEATURE_CATALOG_FILENAME).write_text(
        yaml.safe_dump({"eda_artifact_version": ea.ARTIFACT_VERSION, "transforms": transforms})
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_blocked_leakage_report_raises_eda_gate_error(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    _write_summary(artifacts)
    _write_leakage(artifacts, status="BLOCKED", blocked=["leaky_feature"])
    _write_feature_catalog(artifacts, valid=True)

    trainer = _GateOnlyTrainer(eda_artifacts_dir=artifacts)
    with pytest.raises(EDAGateError, match="leaky_feature"):
        trainer._enforce_eda_gate()


def test_passed_leakage_report_allows_training(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    _write_summary(artifacts)
    _write_leakage(artifacts, status="PASSED", blocked=[])
    _write_feature_catalog(artifacts, valid=True)

    trainer = _GateOnlyTrainer(eda_artifacts_dir=artifacts)
    with caplog.at_level("INFO"):
        trainer._enforce_eda_gate()  # must not raise
    log_text = " ".join(r.message for r in caplog.records)
    assert "PASSED" in log_text
    assert "transform" in log_text


def test_missing_artifacts_dir_skips_gate_with_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    nonexistent = tmp_path / "no_eda_yet"
    trainer = _GateOnlyTrainer(eda_artifacts_dir=nonexistent)
    with caplog.at_level("WARNING"):
        trainer._enforce_eda_gate()  # back-compat: no raise
    assert any("does not exist" in r.message for r in caplog.records)


def test_disabled_gate_via_none(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    trainer = _GateOnlyTrainer(eda_artifacts_dir=None)
    with caplog.at_level("INFO"):
        trainer._enforce_eda_gate()
    assert any("explicitly disabled" in r.message for r in caplog.records)


def test_malformed_feature_catalog_blocks(tmp_path: Path) -> None:
    """Loader raises EDAArtifactSchemaError on missing rationale (D-16)."""
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    _write_summary(artifacts)
    _write_leakage(artifacts, status="PASSED", blocked=[])
    _write_feature_catalog(artifacts, valid=False)

    trainer = _GateOnlyTrainer(eda_artifacts_dir=artifacts)
    with pytest.raises(ea.EDAArtifactSchemaError, match="rationale"):
        trainer._enforce_eda_gate()


def test_partial_artifacts_only_leakage(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """leakage_report.json present, feature_catalog.yaml missing → still passes."""
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    _write_summary(artifacts)
    _write_leakage(artifacts, status="PASSED", blocked=[])
    # No feature_catalog.yaml on purpose

    trainer = _GateOnlyTrainer(eda_artifacts_dir=artifacts)
    with caplog.at_level("INFO"):
        trainer._enforce_eda_gate()  # must not raise
    log_text = " ".join(r.message for r in caplog.records)
    assert "PASSED" in log_text
