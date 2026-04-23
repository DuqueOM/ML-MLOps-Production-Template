"""Unit tests for ground_truth ingester (D-20 invariants + CSV stub).

The ground_truth.py module ships with a CSV-backed stub so the scaffolded
service can be tested end-to-end without a real warehouse. Each service that
adopts the template replaces fetch_labels_from_source() with its actual query.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
import yaml

# Import from templates/service/src/{service}/monitoring/ground_truth.py
# The scaffolded service will have its own slug in place of {service}.
_TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "service" / "src" / "{service}" / "monitoring"
sys.path.insert(0, str(_TEMPLATE_PATH))

from ground_truth import (  # type: ignore[import-not-found]  # noqa: E402
    GroundTruthIngester,
    LabelRecord,
    fetch_labels_from_source,
)


class TestLabelRecord:
    def test_valid_record(self) -> None:
        r = LabelRecord(entity_id="u1", label_ts="2026-04-23T00:00:00+00:00", true_value=1.0)
        assert r.entity_id == "u1"
        assert r.label_source == "external_system"

    def test_missing_entity_id_raises(self) -> None:
        with pytest.raises(ValueError, match="entity_id"):
            LabelRecord(entity_id="", label_ts="2026-04-23T00:00:00+00:00", true_value=1.0)

    def test_is_frozen(self) -> None:
        r = LabelRecord(entity_id="u1", label_ts="2026-04-23T00:00:00+00:00", true_value=1.0)
        with pytest.raises((AttributeError, Exception)):
            r.true_value = 2.0  # type: ignore[misc]


class TestCSVSource:
    def test_csv_source_filters_by_window(self, tmp_path: Path) -> None:
        csv = tmp_path / "labels.csv"
        df = pd.DataFrame(
            [
                {"entity_id": "u1", "label_ts": "2026-04-22T12:00:00", "true_value": 1.0},
                {"entity_id": "u2", "label_ts": "2026-04-23T08:00:00", "true_value": 0.0},
                {"entity_id": "u3", "label_ts": "2026-04-24T01:00:00", "true_value": 1.0},
            ]
        )
        df.to_csv(csv, index=False)
        config = {"source_type": "csv", "csv_path": str(csv)}
        since = datetime(2026, 4, 23, tzinfo=timezone.utc)
        until = datetime(2026, 4, 24, tzinfo=timezone.utc)
        records = fetch_labels_from_source(since, until, config)
        assert len(records) == 1
        assert records[0].entity_id == "u2"

    def test_unknown_source_raises(self) -> None:
        config = {"source_type": "snowflake_foo"}
        with pytest.raises(NotImplementedError, match="snowflake_foo"):
            fetch_labels_from_source(
                datetime(2026, 4, 23, tzinfo=timezone.utc),
                datetime(2026, 4, 24, tzinfo=timezone.utc),
                config,
            )


class TestGroundTruthIngester:
    def test_ingest_writes_partitioned_parquet(self, tmp_path: Path) -> None:
        csv = tmp_path / "labels.csv"
        pd.DataFrame([{"entity_id": "u1", "label_ts": "2026-04-23T10:00:00", "true_value": 1.0}]).to_csv(
            csv, index=False
        )

        config_path = tmp_path / "cfg.yaml"
        yaml.safe_dump(
            {"source_type": "csv", "csv_path": str(csv), "output_base": str(tmp_path / "labels_log")},
            config_path.open("w"),
        )

        ingester = GroundTruthIngester.from_config(str(config_path))
        since = datetime(2026, 4, 23, tzinfo=timezone.utc)
        until = datetime(2026, 4, 24, tzinfo=timezone.utc)
        n = ingester.ingest(since, until)
        assert n == 1

        partition = tmp_path / "labels_log" / "year=2026" / "month=04" / "day=23"
        files = list(partition.glob("batch_*.parquet"))
        assert len(files) == 1
        df = pd.read_parquet(files[0])
        assert df.iloc[0]["entity_id"] == "u1"
        assert df.iloc[0]["true_value"] == 1.0
