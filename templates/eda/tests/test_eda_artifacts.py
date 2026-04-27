"""End-to-end EDA pipeline tests for the canonical artifact contract.

ADR-015 PR-B2 — these tests run the FULL 6-phase pipeline against a
small synthetic dataset and verify that every canonical artifact
described in ``common_utils/eda_artifacts.py`` is produced AND loads
through its corresponding loader.

Why end-to-end and not per-phase?
- The contract is "after a successful run, the 5 canonical artifacts
  exist and validate". Any individual phase can mutate intermediate
  state in ways the per-phase output doesn't expose; only an
  end-to-end run catches integration regressions like "phase 5 forgot
  to call ``_write_feature_catalog``" or "phase 6 wrote
  ``schema_ranges.json`` BEFORE phase 4's leakage_report.json so the
  partial-run sentinel guarantee is broken".

The synthetic dataset is small (200 rows × 6 columns) so the test
runs in <2 seconds, well below the scaffold smoke budget.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Resolve sibling modules without depending on a scaffolded layout.
_TEMPLATES_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_TEMPLATES_ROOT) not in sys.path:
    sys.path.insert(0, str(_TEMPLATES_ROOT))

# common_utils lives at templates/common_utils/; eda_pipeline at templates/eda/.
from common_utils import eda_artifacts as ea  # noqa: E402
from eda import eda_pipeline  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_dataset(tmp_path: Path) -> Path:
    """200-row CSV exercising every code path the pipeline can hit:

    - ``num_normal``: gaussian numeric (passes leakage check)
    - ``num_skewed``: log-normal (triggers log1p proposal in phase 5)
    - ``cat_low``: 3-level categorical (no transform proposed)
    - ``cat_high``: 60-level categorical (triggers target_encode proposal)
    - ``leaky_almost``: correlated 0.3 with target (no leak)
    - ``target``: binary class label
    """
    rng = np.random.default_rng(seed=42)
    n = 200
    df = pd.DataFrame(
        {
            "num_normal": rng.normal(0, 1, n),
            "num_skewed": rng.lognormal(0, 1.5, n),
            "cat_low": rng.choice(["a", "b", "c"], n),
            "cat_high": [f"id_{i % 60}" for i in range(n)],
            "leaky_almost": rng.normal(0, 1, n),
            "target": rng.integers(0, 2, n),
        }
    )
    csv_path = tmp_path / "raw.csv"
    df.to_csv(csv_path, index=False)
    return csv_path


@pytest.fixture
def eda_run(synthetic_dataset: Path, tmp_path: Path) -> Path:
    """Run the full pipeline and return the EDA output directory.

    Asserts the run exited 0 (no leakage) so subsequent tests don't
    have to repeat the exit-code check.
    """
    out_dir = tmp_path / "eda"
    out_dir.mkdir()
    (out_dir / "reports").mkdir()
    (out_dir / "artifacts").mkdir()

    df = eda_pipeline.phase0_ingest(synthetic_dataset, out_dir)
    dtypes_map = eda_pipeline.phase1_profile(df, out_dir)
    baseline = eda_pipeline.phase2_univariate(df, "target", out_dir)
    ranking = eda_pipeline.phase3_correlations(df, "target", out_dir)
    blocked = eda_pipeline.phase4_leakage_gate(df, "target", ranking, out_dir)
    assert blocked == [], f"unexpected leakage block on synthetic data: {blocked}"
    proposals = eda_pipeline.phase5_proposals(df, "target", baseline, out_dir)
    eda_pipeline.phase6_consolidate(df, "target", dtypes_map, baseline, proposals, out_dir, None)
    # phase6_consolidate emits schema_ranges.json; emit eda_summary.json
    # explicitly to mirror what main() does on the COMPLETE path.
    eda_pipeline._write_eda_summary(
        out_dir,
        target="target",
        n_rows=len(df),
        n_columns=len(df.columns),
        runtime_seconds=0.42,
        extras={"status": "complete", "input_path": str(synthetic_dataset)},
    )
    return out_dir


# ---------------------------------------------------------------------------
# 1. All five canonical artifacts exist after a successful run
# ---------------------------------------------------------------------------


def test_all_five_canonical_artifacts_exist(eda_run: Path) -> None:
    artifacts_dir = eda_run / "artifacts"
    missing = ea.missing_artifacts(artifacts_dir)
    assert missing == (), f"missing canonical artifacts: {missing}"


def test_expected_paths_helper_returns_absolute_paths(eda_run: Path) -> None:
    paths = ea.expected_artifact_paths(eda_run / "artifacts")
    assert len(paths) == len(ea.ALL_FILENAMES)
    for p in paths:
        assert p.exists(), f"helper path does not exist: {p}"


# ---------------------------------------------------------------------------
# 2. Each loader successfully parses the corresponding artifact
# ---------------------------------------------------------------------------


def test_load_eda_summary(eda_run: Path) -> None:
    summary = ea.load_eda_summary(eda_run / "artifacts")
    assert summary.target == "target"
    assert summary.n_rows == 200
    assert summary.n_columns == 6
    assert summary.runtime_seconds >= 0
    assert summary.eda_artifact_version == ea.ARTIFACT_VERSION
    assert summary.extras.get("status") == "complete"


def test_load_schema_ranges_includes_every_column(eda_run: Path) -> None:
    entries = ea.load_schema_ranges(eda_run / "artifacts")
    names = {e.name for e in entries}
    expected = {"num_normal", "num_skewed", "cat_low", "cat_high", "leaky_almost", "target"}
    assert expected <= names, f"missing entries: {expected - names}"

    # Numeric features carry numeric stats; categorical ones carry top_values.
    by_name = {e.name: e for e in entries}
    assert by_name["num_normal"].minimum is not None
    assert by_name["num_normal"].maximum is not None
    assert by_name["cat_low"].top_values  # non-empty


def test_load_baseline_distributions_returns_long_form_parquet(eda_run: Path) -> None:
    df = ea.load_baseline_distributions(eda_run / "artifacts")
    assert {"feature", "kind", "key", "value", "eda_artifact_version"} <= set(df.columns)
    # Numeric features have bin edges; categoricals have freq rows.
    kinds = set(df["kind"].unique())
    assert "numeric_bin_edge" in kinds
    assert "categorical_freq" in kinds


def test_load_feature_catalog_enforces_d16_rationale(eda_run: Path) -> None:
    catalog = ea.load_feature_catalog(eda_run / "artifacts")
    assert catalog["eda_artifact_version"] == ea.ARTIFACT_VERSION
    transforms = catalog.get("transforms", [])
    # Synthetic data should propose at least the log1p_num_skewed transform.
    assert len(transforms) >= 1
    for t in transforms:
        assert t.get("rationale", "").strip(), f"D-16 violation: {t!r}"


def test_load_leakage_report_passed_status(eda_run: Path) -> None:
    report = ea.load_leakage_report(eda_run / "artifacts")
    assert report.passed
    assert report.blocked_features == ()
    assert "correlation" in report.thresholds
    assert "near_perfect" in report.thresholds


# ---------------------------------------------------------------------------
# 3. Loader contract — version mismatch raises
# ---------------------------------------------------------------------------


def test_version_mismatch_raises(eda_run: Path) -> None:
    summary_path = eda_run / "artifacts" / ea.EDA_SUMMARY_FILENAME
    payload = json.loads(summary_path.read_text())
    payload["eda_artifact_version"] = ea.ARTIFACT_VERSION + 99
    summary_path.write_text(json.dumps(payload))

    with pytest.raises(ea.EDAArtifactVersionError):
        ea.load_eda_summary(eda_run / "artifacts")


def test_missing_required_key_raises_schema_error(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / ea.EDA_SUMMARY_FILENAME).write_text(
        json.dumps({"eda_artifact_version": ea.ARTIFACT_VERSION, "target": "x"})
    )
    with pytest.raises(ea.EDAArtifactSchemaError, match="missing keys"):
        ea.load_eda_summary(artifacts)


def test_missing_artifact_raises_not_found(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    with pytest.raises(ea.EDAArtifactNotFoundError):
        ea.load_eda_summary(artifacts)


def test_feature_catalog_rejects_missing_rationale(tmp_path: Path) -> None:
    """The D-16 invariant is enforced by the loader, not just the producer."""
    import yaml

    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / ea.FEATURE_CATALOG_FILENAME).write_text(
        yaml.safe_dump(
            {
                "eda_artifact_version": ea.ARTIFACT_VERSION,
                "transforms": [{"name": "log1p_x", "source": "x", "transform": "log1p"}],
            }
        )
    )
    with pytest.raises(ea.EDAArtifactSchemaError, match="rationale"):
        ea.load_feature_catalog(artifacts)


# ---------------------------------------------------------------------------
# 4. The BLOCKED leakage path also produces a valid (non-PASSED) artifact
# ---------------------------------------------------------------------------


def test_leakage_blocked_path_emits_canonical_report(tmp_path: Path) -> None:
    """Synthesise a dataset where one feature is a near-perfect target."""
    rng = np.random.default_rng(seed=7)
    n = 200
    target = rng.integers(0, 2, n)
    df = pd.DataFrame(
        {
            "noise": rng.normal(0, 1, n),
            "leaked": target.astype(float) + rng.normal(0, 0.0001, n),
            "target": target,
        }
    )
    csv = tmp_path / "leaky.csv"
    df.to_csv(csv, index=False)

    out_dir = tmp_path / "eda"
    out_dir.mkdir()
    (out_dir / "reports").mkdir()
    (out_dir / "artifacts").mkdir()

    eda_pipeline.phase0_ingest(csv, out_dir)
    df_clean = pd.read_parquet(tmp_path / "data" / "processed" / "dataset_clean.parquet")
    eda_pipeline.phase1_profile(df_clean, out_dir)
    eda_pipeline.phase2_univariate(df_clean, "target", out_dir)
    ranking = eda_pipeline.phase3_correlations(df_clean, "target", out_dir)
    blocked = eda_pipeline.phase4_leakage_gate(df_clean, "target", ranking, out_dir)
    assert "leaked" in blocked

    report = ea.load_leakage_report(out_dir / "artifacts")
    assert report.status == "BLOCKED"
    assert "leaked" in report.blocked_features
    assert not report.passed
