"""Drift detection wired to the EDA baseline (PR-B2 stage 2).

Verifies the new ``--eda-baseline DIR`` mode of
``drift_detection.detect_drift``:

1. PSI computed against the canonical
   ``baseline_distributions.parquet`` is approximately zero when the
   "current" production data is sampled from the same distribution
   the baseline was built from (no drift → PSI ≈ 0).
2. PSI flags an alert when the current data is shifted away from the
   baseline (drift → PSI > alert threshold).
3. The two modes (legacy CSV reference / PR-B2 EDA parquet) produce
   PSI values within a small tolerance for the same input data — the
   PR-B2 path doesn't introduce a numerical regression on already-
   stable features.
4. The summary now carries a ``baseline_source`` field so an operator
   reading the JSON report knows which path produced the numbers.
5. The ``calculate_psi_from_bins`` helper exists and behaves
   deterministically.

These tests are CPU-only and run in <1s; they exercise the actual
production code path the drift CronJob will use.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

pytest.importorskip("numpy")
pytest.importorskip("pandas")
pytest.importorskip("pyarrow")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# Importing drift_detection requires prometheus_client + the templated
# schemas module. Skip the whole module when missing.
pytest.importorskip("prometheus_client")

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Repo root for common_utils
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_REPO_ROOT / "templates") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "templates"))

drift = importlib.import_module("{service}.monitoring.drift_detection")
import common_utils.eda_artifacts as ea  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def reference_csv(tmp_path: Path) -> Path:
    """1000-row reference frame with two numeric features."""
    rng = np.random.default_rng(seed=0)
    df = pd.DataFrame(
        {
            "feature_a": rng.normal(0, 1, 1000),
            "feature_b": rng.normal(5, 2, 1000),
        }
    )
    out = tmp_path / "reference.csv"
    df.to_csv(out, index=False)
    return out


@pytest.fixture
def baseline_parquet(tmp_path: Path, reference_csv: Path) -> Path:
    """Synthesise a canonical baseline_distributions.parquet from
    the reference frame using the same quantile-bin construction the
    EDA pipeline performs in phase 2.
    """
    df = pd.read_csv(reference_csv)
    rows: list[dict] = []
    for col in df.columns:
        edges = np.quantile(df[col], np.linspace(0, 1, 11))
        edges = np.unique(edges)
        for i, edge in enumerate(edges):
            rows.append({"feature": col, "kind": "numeric_bin_edge", "key": str(i), "value": float(edge)})
        rows.append({"feature": col, "kind": "numeric_stat", "key": "mean", "value": float(df[col].mean())})
        rows.append({"feature": col, "kind": "numeric_stat", "key": "std", "value": float(df[col].std())})
    out_df = pd.DataFrame(rows)
    out_df["eda_artifact_version"] = ea.ARTIFACT_VERSION

    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    out_df.to_parquet(artifacts_dir / ea.BASELINE_DISTRIBUTIONS_FILENAME, index=False)
    return artifacts_dir


@pytest.fixture
def current_no_drift_csv(tmp_path: Path) -> Path:
    """Same generative process as the reference → PSI must be ~0."""
    rng = np.random.default_rng(seed=1)
    df = pd.DataFrame(
        {
            "feature_a": rng.normal(0, 1, 800),
            "feature_b": rng.normal(5, 2, 800),
        }
    )
    out = tmp_path / "current_clean.csv"
    df.to_csv(out, index=False)
    return out


@pytest.fixture
def current_drifted_csv(tmp_path: Path) -> Path:
    """Shifted distribution on feature_a → PSI must trip alert."""
    rng = np.random.default_rng(seed=2)
    df = pd.DataFrame(
        {
            "feature_a": rng.normal(3, 1, 800),  # mean shifted +3σ
            "feature_b": rng.normal(5, 2, 800),  # unchanged
        }
    )
    out = tmp_path / "current_drift.csv"
    df.to_csv(out, index=False)
    return out


# ---------------------------------------------------------------------------
# 1. calculate_psi_from_bins helper
# ---------------------------------------------------------------------------


def test_psi_from_bins_returns_zero_for_identical_distribution() -> None:
    rng = np.random.default_rng(0)
    sample = rng.normal(0, 1, 5000)
    edges = np.quantile(sample, np.linspace(0, 1, 11))
    psi = drift.calculate_psi_from_bins(edges, sample)
    assert psi < 0.01, f"identical-distribution PSI should be ~0, got {psi}"


def test_psi_from_bins_flags_shifted_distribution() -> None:
    rng = np.random.default_rng(0)
    ref = rng.normal(0, 1, 5000)
    current = rng.normal(3, 1, 5000)  # heavily shifted
    edges = np.quantile(ref, np.linspace(0, 1, 11))
    psi = drift.calculate_psi_from_bins(edges, current)
    assert psi > drift.DEFAULT_ALERT, f"shifted-distribution PSI should exceed alert ({drift.DEFAULT_ALERT}), got {psi}"


def test_psi_from_bins_handles_degenerate_edges() -> None:
    """A constant-feature baseline yields a 1-element bin array; PSI must not blow up."""
    edges = np.array([1.0])
    assert drift.calculate_psi_from_bins(edges, np.array([1.0, 1.0, 1.0])) == 0.0


# ---------------------------------------------------------------------------
# 2. detect_drift in EDA-baseline mode
# ---------------------------------------------------------------------------


def test_detect_drift_eda_baseline_no_drift(
    baseline_parquet: Path, current_no_drift_csv: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Bypass Pandera schema validation since the synthetic frames don't
    # match the templated ServiceInputSchema (which expects service-
    # specific columns). Schema validation is exercised by its own
    # tests; this one focuses on the PSI math.
    results = drift.detect_drift(
        reference_path=None,
        current_path=str(current_no_drift_csv),
        eda_baseline_dir=str(baseline_parquet),
        skip_schema=True,
    )

    assert results["summary"]["baseline_source"] == "eda_parquet"
    assert results["summary"]["requires_action"] is False
    for feat, data in results["features"].items():
        assert (
            data["psi"] < drift.DEFAULT_WARNING
        ), f"feature {feat}: PSI {data['psi']} above warning threshold on no-drift data"
        # In EDA-baseline-only mode (no reference CSV), reference stats are None.
        assert data["reference_mean"] is None
        assert data["reference_std"] is None


def test_detect_drift_eda_baseline_flags_alert(baseline_parquet: Path, current_drifted_csv: Path) -> None:
    results = drift.detect_drift(
        reference_path=None,
        current_path=str(current_drifted_csv),
        eda_baseline_dir=str(baseline_parquet),
        skip_schema=True,
    )
    assert results["summary"]["requires_action"] is True
    assert "feature_a" in results["summary"]["alerts"]
    # feature_b was untouched; must NOT be in alerts.
    assert "feature_b" not in results["summary"]["alerts"]


def test_detect_drift_legacy_and_eda_modes_agree(
    reference_csv: Path, baseline_parquet: Path, current_no_drift_csv: Path
) -> None:
    """Numerical regression guard: the two modes should give close PSI
    on the same data when both reference and EDA baseline come from the
    same source distribution. Allows generous tolerance because the
    legacy mode uses the EMPIRICAL reference percentage while the new
    mode uses the THEORETICAL 1/n_bins; the gap is small but nonzero.
    """
    legacy = drift.detect_drift(
        reference_path=str(reference_csv),
        current_path=str(current_no_drift_csv),
        skip_schema=True,
    )
    eda_mode = drift.detect_drift(
        reference_path=None,
        current_path=str(current_no_drift_csv),
        eda_baseline_dir=str(baseline_parquet),
        skip_schema=True,
    )
    for feat in legacy["features"]:
        a = legacy["features"][feat]["psi"]
        b = eda_mode["features"][feat]["psi"]
        assert abs(a - b) < 0.02, f"PSI divergence on {feat}: legacy={a} eda={b}"


def test_detect_drift_requires_either_mode() -> None:
    with pytest.raises(ValueError, match="reference_path"):
        drift.detect_drift(
            reference_path=None,
            current_path="/dev/null",
            eda_baseline_dir=None,
            skip_schema=True,
        )


# ---------------------------------------------------------------------------
# 3. Long-form parquet pivot
# ---------------------------------------------------------------------------


def test_bin_edges_helper_pivots_long_form(baseline_parquet: Path) -> None:
    df = pd.read_parquet(baseline_parquet / ea.BASELINE_DISTRIBUTIONS_FILENAME)
    edges = drift._bin_edges_from_baseline_df(df)
    assert set(edges.keys()) == {"feature_a", "feature_b"}
    for feat, arr in edges.items():
        assert arr.ndim == 1
        # Edges must be sorted ascending (quantile output).
        assert np.all(np.diff(arr) >= 0), f"non-monotonic edges on {feat}: {arr}"
