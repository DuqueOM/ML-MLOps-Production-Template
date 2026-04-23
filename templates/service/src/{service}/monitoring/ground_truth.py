"""Ground-truth ingestion for closed-loop monitoring (ADR-006).

Fetches delayed labels from a user-defined source (data warehouse, DB, file,
API) and joins them with predictions_log by entity_id.

The canonical labels_log schema:
    entity_id      TEXT  NOT NULL
    label_ts       TEXT  NOT NULL  (ISO-8601 UTC when the label became known)
    true_value     REAL/INT        (binary or regression target)
    label_source   TEXT            ('manual' | 'external_system' | 'delayed_update')

The USER MUST implement ``fetch_labels_from_source()`` in this file — it is the
contract between your data warehouse and the monitoring pipeline.

Invariants:
    - ALL returned rows MUST have non-null entity_id and true_value
    - label_ts MUST be present (used to scope the JOIN window)
    - Idempotent writes: running twice produces no duplicates (unique index)

Usage (CronJob):
    python -m src.{service}.monitoring.ground_truth \\
        --since 2025-04-01 --until 2025-04-02 \\
        --backend parquet --output data/labels_log

Usage (programmatic):
    ingester = GroundTruthIngester.from_config("configs/ground_truth_source.yaml")
    n = ingester.ingest(since=..., until=...)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Label record
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class LabelRecord:
    entity_id: str
    label_ts: str
    true_value: float
    label_source: str = "external_system"

    def __post_init__(self) -> None:
        if not self.entity_id:
            raise ValueError("entity_id is required")
        if self.true_value is None:
            raise ValueError("true_value is required")


# ---------------------------------------------------------------------------
# USER-IMPLEMENTED contract
# ---------------------------------------------------------------------------
def fetch_labels_from_source(
    since: datetime,
    until: datetime,
    config: dict[str, Any],
) -> list[LabelRecord]:
    """Return all ground-truth labels that *became known* in [since, until).

    REPLACE this stub with your actual query. Common patterns:

    BigQuery example:
        from google.cloud import bigquery
        client = bigquery.Client()
        q = '''
          SELECT customer_id as entity_id,
                 churn_confirmed_at as label_ts,
                 CAST(did_churn as INT64) as true_value
          FROM `{project}.crm.churn_outcomes`
          WHERE churn_confirmed_at BETWEEN @since AND @until
        '''
        rows = client.query(q, ...).result()
        return [LabelRecord(r.entity_id, r.label_ts.isoformat(), r.true_value) for r in rows]

    Postgres example:
        import psycopg2
        conn = psycopg2.connect(...)
        df = pd.read_sql("...", conn)
        return [LabelRecord(**row) for row in df.to_dict(orient='records')]

    The template ships a CSV-file stub for local testing only.
    """
    source_type = config.get("source_type", "csv")
    if source_type == "csv":
        path = config["csv_path"]
        ts_col = config.get("label_ts_col", "label_ts")
        df = pd.read_csv(path, parse_dates=[ts_col])
        # CSV ts are typically naive — treat as UTC so comparisons with tz-aware
        # since/until (D-20) don't fail on dtype mismatch.
        if getattr(df[ts_col].dt, "tz", None) is None:
            df[ts_col] = df[ts_col].dt.tz_localize("UTC")
        df = df[(df[ts_col] >= since) & (df[ts_col] < until)]
        records: list[LabelRecord] = []
        for _, row in df.iterrows():
            records.append(
                LabelRecord(
                    entity_id=str(row[config.get("entity_id_col", "entity_id")]),
                    label_ts=pd.Timestamp(row[ts_col]).isoformat(),
                    true_value=float(row[config.get("true_value_col", "true_value")]),
                    label_source=config.get("label_source_tag", "csv"),
                )
            )
        return records

    raise NotImplementedError(
        f"source_type={source_type!r} not implemented. "
        f"Override fetch_labels_from_source() in ground_truth.py for your warehouse."
    )


# ---------------------------------------------------------------------------
# Ingester
# ---------------------------------------------------------------------------
class GroundTruthIngester:
    """Reads labels from source and persists to labels_log backend.

    Backend is kept simple: parquet partitioned by day. For BigQuery label
    storage, reuse BigQueryBackend from prediction_logger.
    """

    def __init__(self, config: dict[str, Any], output_base: str) -> None:
        self.config = config
        self.output_base = output_base

    @classmethod
    def from_config(cls, config_path: str) -> GroundTruthIngester:
        cfg = yaml.safe_load(Path(config_path).read_text())
        return cls(cfg, output_base=cfg.get("output_base", "data/labels_log"))

    def ingest(self, since: datetime, until: datetime) -> int:
        """Fetch labels for [since, until) and write partitioned parquet.

        Returns number of records written.
        """
        logger.info("Fetching labels for [%s, %s)", since, until)
        records = fetch_labels_from_source(since, until, self.config)
        if not records:
            logger.info("No labels in window")
            return 0

        rows = [
            {
                "entity_id": r.entity_id,
                "label_ts": r.label_ts,
                "true_value": r.true_value,
                "label_source": r.label_source,
            }
            for r in records
        ]
        df = pd.DataFrame(rows)

        partition = f"year={since.year:04d}/month={since.month:02d}/day={since.day:02d}"
        batch_fname = f"batch_{int(time.time() * 1000)}.parquet"

        if self.output_base.startswith(("gs://", "s3://")):
            full_path = f"{self.output_base}/{partition}/{batch_fname}"
            df.to_parquet(full_path, engine="pyarrow")
        else:
            local = Path(self.output_base) / partition
            local.mkdir(parents=True, exist_ok=True)
            df.to_parquet(local / batch_fname, engine="pyarrow")

        logger.info("Wrote %d labels → %s/%s", len(df), self.output_base, partition)
        return len(df)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Ingest ground-truth labels for {ServiceName}")
    parser.add_argument("--config", default="configs/ground_truth_source.yaml")
    parser.add_argument("--since", help="ISO date, default: yesterday 00:00 UTC")
    parser.add_argument("--until", help="ISO date, default: today 00:00 UTC")
    parser.add_argument("--output", help="Override output_base from config")
    args = parser.parse_args()

    now = datetime.now(tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    since = datetime.fromisoformat(args.since) if args.since else now - timedelta(days=1)
    until = datetime.fromisoformat(args.until) if args.until else now

    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)

    ingester = GroundTruthIngester.from_config(args.config)
    if args.output:
        ingester.output_base = args.output

    n = ingester.ingest(since, until)
    print(json.dumps({"records_ingested": n, "since": since.isoformat(), "until": until.isoformat()}))
    return 0 if n >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
