"""Unit tests for sliced performance monitoring (ADR-007)."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

_TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "service" / "src" / "{service}" / "monitoring"
sys.path.insert(0, str(_TEMPLATE_PATH))

from performance_monitor import (  # type: ignore[import-not-found]  # noqa: E402
    MonitorConfig,
    SliceConfig,
    _apply_thresholds,
    assign_slice_column,
    compute_metrics,
    load_config,
    load_partitioned_parquet,
    run_performance_check,
)


# ---------------------------------------------------------------------------
# compute_metrics
# ---------------------------------------------------------------------------
class TestComputeMetrics:
    def test_perfect_classifier(self) -> None:
        y_true = np.array([0, 0, 1, 1])
        y_score = np.array([0.1, 0.2, 0.8, 0.9])
        m = compute_metrics(y_true, y_score)
        assert m["auc"] == 1.0
        assert m["f1"] == 1.0
        assert m["sample_size"] == 4

    def test_single_class_auc_is_nan(self) -> None:
        m = compute_metrics(np.zeros(5, dtype=int), np.array([0.1, 0.2, 0.3, 0.4, 0.5]))
        assert np.isnan(m["auc"])

    def test_brier_score_present(self) -> None:
        y_true = np.array([1, 0, 1, 0])
        y_score = np.array([0.8, 0.1, 0.9, 0.2])
        m = compute_metrics(y_true, y_score)
        assert 0.0 <= m["brier"] <= 1.0


# ---------------------------------------------------------------------------
# Slice assignment
# ---------------------------------------------------------------------------
class TestAssignSliceColumn:
    def test_categorical_slice_from_slice_prefix(self) -> None:
        df = pd.DataFrame({"slice_country": ["MX", "US", "MX"]})
        out = assign_slice_column(df, SliceConfig(name="by_country", column="country"))
        assert list(out) == ["MX", "US", "MX"]

    def test_numeric_slice_with_bins(self) -> None:
        df = pd.DataFrame({"score": [0.1, 0.5, 0.9]})
        out = assign_slice_column(df, SliceConfig(name="bucket", column="score", bins=[0.0, 0.3, 0.7, 1.0]))
        assert "[0.00,0.30)" in out.values
        assert "[0.70,1.00)" in out.values

    def test_missing_column_returns_none_series(self) -> None:
        df = pd.DataFrame({"other": [1, 2]})
        out = assign_slice_column(df, SliceConfig(name="x", column="missing"))
        assert out.isna().all()


# ---------------------------------------------------------------------------
# Threshold application
# ---------------------------------------------------------------------------
class TestApplyThresholds:
    def test_auc_alert_below_hard_threshold(self) -> None:
        report = {"alerts": [], "warnings": []}
        cfg = MonitorConfig(auc_warning=0.75, auc_alert=0.65)
        _apply_thresholds({"auc": 0.50, "f1": 0.9}, cfg, None, report, "__global__")
        assert len(report["alerts"]) == 1
        assert report["alerts"][0]["metric"] == "auc"

    def test_auc_warning_between_thresholds(self) -> None:
        report = {"alerts": [], "warnings": []}
        cfg = MonitorConfig(auc_warning=0.75, auc_alert=0.65, f1_warning=0.55, f1_alert=0.45)
        _apply_thresholds({"auc": 0.70, "f1": 0.9}, cfg, None, report, "country=MX")
        assert len(report["warnings"]) == 1
        assert report["warnings"][0]["slice"] == "country=MX"

    def test_baseline_concept_drift_triggers_alert(self) -> None:
        report = {"alerts": [], "warnings": []}
        cfg = MonitorConfig(auc_drop_warning=0.05, auc_drop_alert=0.10)
        _apply_thresholds({"auc": 0.70, "f1": 0.9}, cfg, {"auc": 0.85}, report, "__global__")
        # drop = 0.85 - 0.70 = 0.15 > 0.10
        auc_drop_alerts = [a for a in report["alerts"] if a["metric"] == "auc_drop"]
        assert len(auc_drop_alerts) == 1

    def test_no_alerts_on_healthy_metrics(self) -> None:
        report = {"alerts": [], "warnings": []}
        cfg = MonitorConfig()
        _apply_thresholds({"auc": 0.92, "f1": 0.85}, cfg, {"auc": 0.90}, report, "__global__")
        assert report["alerts"] == []
        assert report["warnings"] == []


# ---------------------------------------------------------------------------
# load_config + slices.yaml
# ---------------------------------------------------------------------------
class TestLoadConfig:
    def test_load_slices_yaml(self, tmp_path: Path) -> None:
        cfg_yaml = tmp_path / "slices.yaml"
        yaml.safe_dump(
            {
                "min_samples_per_slice": 100,
                "auc_alert": 0.60,
                "slices": [
                    {"name": "by_country", "column": "country", "values": ["MX", "US"]},
                    {"name": "by_bucket", "column": "score", "bins": [0.0, 0.5, 1.0]},
                ],
            },
            cfg_yaml.open("w"),
        )
        cfg = load_config(str(cfg_yaml))
        assert cfg.min_samples_per_slice == 100
        assert cfg.auc_alert == 0.60
        assert len(cfg.slices) == 2
        assert cfg.slices[0].name == "by_country"
        assert cfg.slices[1].bins == [0.0, 0.5, 1.0]


# ---------------------------------------------------------------------------
# load_partitioned_parquet
# ---------------------------------------------------------------------------
class TestLoadPartitionedParquet:
    def test_missing_base_returns_empty(self, tmp_path: Path) -> None:
        df = load_partitioned_parquet(
            str(tmp_path / "nonexistent"),
            datetime(2026, 4, 23, tzinfo=timezone.utc),
            datetime(2026, 4, 24, tzinfo=timezone.utc),
        )
        assert df.empty

    def test_reads_multiple_days(self, tmp_path: Path) -> None:
        base = tmp_path / "log"
        for day, rows in [(22, 2), (23, 3)]:
            partition = base / "year=2026" / "month=04" / f"day={day:02d}"
            partition.mkdir(parents=True)
            pd.DataFrame({"prediction_id": [f"p{day}-{i}" for i in range(rows)]}).to_parquet(
                partition / "batch_1.parquet"
            )
        df = load_partitioned_parquet(
            str(base),
            datetime(2026, 4, 22, tzinfo=timezone.utc),
            datetime(2026, 4, 24, tzinfo=timezone.utc),
        )
        assert len(df) == 5


# ---------------------------------------------------------------------------
# Full pipeline — integration-ish
# ---------------------------------------------------------------------------
class TestRunPerformanceCheck:
    def _seed_data(self, tmp_path: Path) -> tuple[str, str]:
        preds = tmp_path / "preds"
        labels = tmp_path / "labels"
        (preds / "year=2026" / "month=04" / "day=23").mkdir(parents=True)
        (labels / "year=2026" / "month=04" / "day=23").mkdir(parents=True)

        # 200 predictions: 100 MX (good perf), 100 US (bad perf)
        rng = np.random.default_rng(42)
        rows = []
        for i in range(100):
            rows.append(
                {
                    "prediction_id": f"mx{i}",
                    "entity_id": f"mx{i}",
                    "timestamp": "2026-04-23T10:00:00+00:00",
                    "model_version": "v1",
                    "score": float(0.7 if i < 80 else 0.2),  # mostly correct for MX
                    "slice_country": "MX",
                }
            )
        for i in range(100):
            rows.append(
                {
                    "prediction_id": f"us{i}",
                    "entity_id": f"us{i}",
                    "timestamp": "2026-04-23T10:00:00+00:00",
                    "model_version": "v1",
                    "score": float(rng.uniform(0, 1)),  # random for US — bad AUC
                    "slice_country": "US",
                }
            )
        pd.DataFrame(rows).to_parquet(preds / "year=2026" / "month=04" / "day=23" / "batch.parquet")

        # Labels: MX mostly positive, US balanced random
        label_rows = []
        for i in range(100):
            label_rows.append(
                {
                    "entity_id": f"mx{i}",
                    "label_ts": "2026-04-23T15:00:00+00:00",
                    "true_value": 1 if i < 80 else 0,
                    "label_source": "test",
                }
            )
        for i in range(100):
            label_rows.append(
                {
                    "entity_id": f"us{i}",
                    "label_ts": "2026-04-23T15:00:00+00:00",
                    "true_value": int(rng.integers(0, 2)),
                    "label_source": "test",
                }
            )
        pd.DataFrame(label_rows).to_parquet(labels / "year=2026" / "month=04" / "day=23" / "batch.parquet")
        return str(preds), str(labels)

    def test_pipeline_produces_global_and_sliced_metrics(self, tmp_path: Path) -> None:
        preds, labels = self._seed_data(tmp_path)
        config = MonitorConfig(
            min_samples_per_slice=50,
            slices=[SliceConfig(name="by_country", column="country", values=["MX", "US"])],
        )
        report = run_performance_check(
            preds,
            labels,
            config,
            since=datetime(2026, 4, 23, tzinfo=timezone.utc),
            until=datetime(2026, 4, 24, tzinfo=timezone.utc),
        )
        assert report["status"] in {"ok", "warning", "alert"}
        assert report["predictions_count"] == 200
        assert report["labels_count"] == 200
        assert report["joined_count"] == 200
        assert "auc" in report["global"]
        assert "by_country" in report["slices"]
        assert "MX" in report["slices"]["by_country"]
        assert "US" in report["slices"]["by_country"]
        # MX should have much better AUC than US by construction
        mx_auc = report["slices"]["by_country"]["MX"]["auc"]
        us_auc = report["slices"]["by_country"]["US"]["auc"]
        assert mx_auc > us_auc + 0.2

    def test_insufficient_data_status(self, tmp_path: Path) -> None:
        config = MonitorConfig()
        # no data seeded
        report = run_performance_check(
            str(tmp_path / "preds"),
            str(tmp_path / "labels"),
            config,
            since=datetime(2026, 4, 23, tzinfo=timezone.utc),
            until=datetime(2026, 4, 24, tzinfo=timezone.utc),
        )
        assert report["status"] == "insufficient_data"
