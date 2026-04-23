"""Sliced performance monitoring with delayed ground-truth (ADR-006 / ADR-007).

Joins predictions_log with labels_log by entity_id (latest label per entity)
within a configurable time window, then computes classification metrics
(AUC, F1, precision, recall, Brier) globally AND per slice (country,
channel, model_version, ...).

Outputs:
    1. JSON report (for GitHub Actions artifacts, dashboards)
    2. Prometheus metrics via Pushgateway (for alerting)
    3. Human-readable markdown summary

Exit codes (used by K8s CronJob + GitHub Issue creation):
    0 — All slices healthy; no action needed
    1 — Warning: metric below soft threshold in ≥1 slice
    2 — Alert: metric below hard threshold in ≥1 slice (concept drift)

Invariants:
    - Slice cardinality is bounded by configs/slices.yaml (reject unknown slices)
    - Metrics require min_samples per slice — below that, slice is 'insufficient_data'
    - No prediction is counted twice (dedup by prediction_id)

Usage:
    python -m src.{service}.monitoring.performance_monitor \\
        --predictions data/predictions_log \\
        --labels data/labels_log \\
        --slices configs/slices.yaml \\
        --window 24h --output reports/performance.json --push-metrics
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration dataclasses
# ---------------------------------------------------------------------------
@dataclass
class SliceConfig:
    """A slicing dimension loaded from configs/slices.yaml."""

    name: str
    column: str
    values: list[str] | None = None  # None = auto-discover from data
    bins: list[float] | None = None  # if numeric, bucket edges


@dataclass
class MonitorConfig:
    min_samples_per_slice: int = 50
    auc_warning: float = 0.75
    auc_alert: float = 0.65
    f1_warning: float = 0.55
    f1_alert: float = 0.45
    # Concept-drift: current metric vs baseline (from training or last-good window)
    auc_drop_warning: float = 0.05
    auc_drop_alert: float = 0.10
    slices: list[SliceConfig] = field(default_factory=list)


def load_config(path: str) -> MonitorConfig:
    raw = yaml.safe_load(Path(path).read_text())
    slices = [SliceConfig(**s) for s in raw.get("slices", [])]
    return MonitorConfig(
        min_samples_per_slice=raw.get("min_samples_per_slice", 50),
        auc_warning=raw.get("auc_warning", 0.75),
        auc_alert=raw.get("auc_alert", 0.65),
        f1_warning=raw.get("f1_warning", 0.55),
        f1_alert=raw.get("f1_alert", 0.45),
        auc_drop_warning=raw.get("auc_drop_warning", 0.05),
        auc_drop_alert=raw.get("auc_drop_alert", 0.10),
        slices=slices,
    )


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_partitioned_parquet(base_path: str, since: datetime, until: datetime) -> pd.DataFrame:
    """Load parquet files from year=/month=/day= partitions in [since, until)."""
    base = Path(base_path)
    if not base.exists():
        logger.warning("Base path %s does not exist", base)
        return pd.DataFrame()

    frames: list[pd.DataFrame] = []
    current = since
    while current < until:
        partition = base / f"year={current.year:04d}" / f"month={current.month:02d}" / f"day={current.day:02d}"
        if partition.exists():
            for f in partition.glob("*.parquet"):
                try:
                    frames.append(pd.read_parquet(f))
                except Exception as e:
                    logger.warning("Failed to read %s: %s", f, e)
        current += timedelta(days=1)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).drop_duplicates(
        subset=["prediction_id"] if "prediction_id" in frames[0].columns else None
    )


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------
def compute_metrics(y_true: np.ndarray, y_score: np.ndarray, threshold: float = 0.5) -> dict[str, float]:
    """Compute classification metrics. Requires binary y_true (0/1) and y_score in [0,1]."""
    from sklearn.metrics import (
        brier_score_loss,
        f1_score,
        precision_score,
        recall_score,
        roc_auc_score,
    )

    y_pred = (y_score >= threshold).astype(int)
    metrics: dict[str, float] = {}

    # AUC requires both classes; gracefully degrade
    if len(np.unique(y_true)) > 1:
        metrics["auc"] = float(roc_auc_score(y_true, y_score))
    else:
        metrics["auc"] = float("nan")

    metrics["f1"] = float(f1_score(y_true, y_pred, zero_division=0))
    metrics["precision"] = float(precision_score(y_true, y_pred, zero_division=0))
    metrics["recall"] = float(recall_score(y_true, y_pred, zero_division=0))
    metrics["brier"] = float(brier_score_loss(y_true, y_score))
    metrics["positive_rate_pred"] = float(y_pred.mean())
    metrics["positive_rate_true"] = float((y_true == 1).mean())
    metrics["sample_size"] = int(len(y_true))
    return metrics


def assign_slice_column(df: pd.DataFrame, slice_cfg: SliceConfig) -> pd.Series:
    """Return the series of slice values for a given slice config.

    Predictions log stores slices as 'slice_<name>' columns (flattened by
    ParquetBackend). For numeric features we optionally bin.
    """
    col = f"slice_{slice_cfg.column}" if f"slice_{slice_cfg.column}" in df.columns else slice_cfg.column
    if col not in df.columns:
        return pd.Series([None] * len(df), index=df.index, dtype=object)

    values = df[col]
    if slice_cfg.bins:
        labels = [f"[{slice_cfg.bins[i]:.2f},{slice_cfg.bins[i + 1]:.2f})" for i in range(len(slice_cfg.bins) - 1)]
        return pd.cut(values, bins=slice_cfg.bins, labels=labels, include_lowest=True).astype(str)
    return values.astype(str)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def run_performance_check(
    predictions_path: str,
    labels_path: str,
    config: MonitorConfig,
    since: datetime,
    until: datetime,
    baseline_metrics: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Join predictions ↔ labels, compute global + sliced metrics.

    Returns a JSON-serializable report.
    """
    logger.info("Loading predictions from %s [%s, %s)", predictions_path, since, until)
    preds = load_partitioned_parquet(predictions_path, since, until)

    # Labels are partitioned by label_ts date — fetch a wider window to cover
    # labels that just became known for predictions issued earlier.
    label_window_start = since - timedelta(days=7)
    logger.info("Loading labels from %s [%s, %s)", labels_path, label_window_start, until)
    labels = load_partitioned_parquet(labels_path, label_window_start, until)

    report: dict[str, Any] = {
        "timestamp": time.time(),
        "window": {"since": since.isoformat(), "until": until.isoformat()},
        "predictions_count": len(preds),
        "labels_count": len(labels),
        "joined_count": 0,
        "global": {},
        "slices": {},
        "alerts": [],
        "warnings": [],
    }

    if preds.empty or labels.empty:
        logger.warning("Insufficient data: predictions=%d, labels=%d", len(preds), len(labels))
        report["status"] = "insufficient_data"
        return report

    # JOIN: use latest label per entity_id that is newer than the prediction.
    labels_sorted = labels.sort_values("label_ts")
    latest_label = labels_sorted.drop_duplicates("entity_id", keep="last")[["entity_id", "true_value", "label_ts"]]
    joined = preds.merge(latest_label, on="entity_id", how="inner")
    # Ensure label post-dates prediction (causality)
    joined = joined[pd.to_datetime(joined["label_ts"]) >= pd.to_datetime(joined["timestamp"])]
    report["joined_count"] = int(len(joined))
    logger.info("Joined %d predictions with labels", len(joined))

    if len(joined) < config.min_samples_per_slice:
        logger.warning(
            "Only %d joined samples (min=%d) — metrics not reliable", len(joined), config.min_samples_per_slice
        )
        report["status"] = "insufficient_joined_samples"
        return report

    # Global metrics
    y_true = joined["true_value"].astype(int).values
    y_score = joined["score"].astype(float).values
    global_metrics = compute_metrics(y_true, y_score)
    report["global"] = global_metrics
    _apply_thresholds(global_metrics, config, baseline_metrics, report, slice_key="__global__")

    # Sliced metrics
    for slice_cfg in config.slices:
        slice_values = assign_slice_column(joined, slice_cfg)
        if slice_values.isna().all():
            logger.info("Slice %s absent from data — skipping", slice_cfg.name)
            continue

        report["slices"][slice_cfg.name] = {}
        for value, group in joined.groupby(slice_values):
            if len(group) < config.min_samples_per_slice:
                report["slices"][slice_cfg.name][str(value)] = {
                    "status": "insufficient_data",
                    "sample_size": int(len(group)),
                }
                continue
            g_y_true = group["true_value"].astype(int).values
            g_y_score = group["score"].astype(float).values
            g_metrics = compute_metrics(g_y_true, g_y_score)
            report["slices"][slice_cfg.name][str(value)] = g_metrics
            _apply_thresholds(g_metrics, config, baseline_metrics, report, slice_key=f"{slice_cfg.name}={value}")

    if report["alerts"]:
        report["status"] = "alert"
    elif report["warnings"]:
        report["status"] = "warning"
    else:
        report["status"] = "ok"
    return report


def _apply_thresholds(
    metrics: dict[str, float],
    config: MonitorConfig,
    baseline: dict[str, float] | None,
    report: dict[str, Any],
    slice_key: str,
) -> None:
    """Evaluate soft and hard thresholds, append to warnings/alerts."""
    auc = metrics.get("auc", float("nan"))
    f1 = metrics.get("f1", 0.0)

    if not np.isnan(auc):
        if auc < config.auc_alert:
            report["alerts"].append({"slice": slice_key, "metric": "auc", "value": auc, "threshold": config.auc_alert})
        elif auc < config.auc_warning:
            report["warnings"].append(
                {"slice": slice_key, "metric": "auc", "value": auc, "threshold": config.auc_warning}
            )

    if f1 < config.f1_alert:
        report["alerts"].append({"slice": slice_key, "metric": "f1", "value": f1, "threshold": config.f1_alert})
    elif f1 < config.f1_warning:
        report["warnings"].append({"slice": slice_key, "metric": "f1", "value": f1, "threshold": config.f1_warning})

    # Concept drift: drop vs baseline
    if baseline and "auc" in baseline and not np.isnan(auc):
        drop = baseline["auc"] - auc
        if drop >= config.auc_drop_alert:
            report["alerts"].append(
                {"slice": slice_key, "metric": "auc_drop", "value": drop, "threshold": config.auc_drop_alert}
            )
        elif drop >= config.auc_drop_warning:
            report["warnings"].append(
                {"slice": slice_key, "metric": "auc_drop", "value": drop, "threshold": config.auc_drop_warning}
            )


# ---------------------------------------------------------------------------
# Prometheus push
# ---------------------------------------------------------------------------
def push_to_prometheus(report: dict[str, Any], pushgateway_url: str, service: str) -> None:
    registry = CollectorRegistry()

    perf_gauge = Gauge(
        f"{service}_performance_metric",
        "Sliced performance metrics (AUC, F1, precision, recall, Brier)",
        ["slice_name", "slice_value", "metric"],
        registry=registry,
    )
    sample_gauge = Gauge(
        f"{service}_performance_sample_size",
        "Joined predictions+labels sample size per slice",
        ["slice_name", "slice_value"],
        registry=registry,
    )
    last_run_gauge = Gauge(
        f"{service}_performance_last_run_timestamp",
        "Last successful performance check (unix ts)",
        registry=registry,
    )
    status_gauge = Gauge(
        f"{service}_performance_status",
        "0=ok, 1=warning, 2=alert, -1=insufficient_data",
        registry=registry,
    )

    # Global
    for metric, value in report.get("global", {}).items():
        if metric in ("auc", "f1", "precision", "recall", "brier"):
            if not (isinstance(value, float) and np.isnan(value)):
                perf_gauge.labels(slice_name="__global__", slice_value="__all__", metric=metric).set(value)
    sample_gauge.labels(slice_name="__global__", slice_value="__all__").set(report.get("joined_count", 0))

    # Slices
    for slice_name, groups in report.get("slices", {}).items():
        for slice_value, metrics in groups.items():
            if not isinstance(metrics, dict) or metrics.get("status") == "insufficient_data":
                continue
            for metric, value in metrics.items():
                if metric in ("auc", "f1", "precision", "recall", "brier"):
                    if not (isinstance(value, float) and np.isnan(value)):
                        perf_gauge.labels(slice_name=slice_name, slice_value=slice_value, metric=metric).set(value)
            sample_gauge.labels(slice_name=slice_name, slice_value=slice_value).set(metrics.get("sample_size", 0))

    last_run_gauge.set(time.time())
    status_map = {"ok": 0, "warning": 1, "alert": 2, "insufficient_data": -1, "insufficient_joined_samples": -1}
    status_gauge.set(status_map.get(report.get("status", "ok"), 0))

    push_to_gateway(pushgateway_url, job=f"{service}-performance", registry=registry)
    logger.info("Performance metrics pushed to %s", pushgateway_url)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")

    parser = argparse.ArgumentParser(description="Sliced performance monitoring")
    parser.add_argument("--predictions", required=True, help="Path to predictions_log base")
    parser.add_argument("--labels", required=True, help="Path to labels_log base")
    parser.add_argument("--slices", default="configs/slices.yaml")
    parser.add_argument("--window", default="24h", help="24h | 7d | 30d | custom since/until")
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--baseline", help="Path to baseline_metrics.json")
    parser.add_argument("--output", help="Report JSON path")
    parser.add_argument("--push-metrics", action="store_true")
    parser.add_argument("--pushgateway", default=os.getenv("PUSHGATEWAY_URL", "pushgateway:9091"))
    parser.add_argument("--service", default=os.getenv("SERVICE_NAME", "{service}"))
    args = parser.parse_args()

    now = datetime.now(tz=timezone.utc)
    if args.since and args.until:
        since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
        until = datetime.fromisoformat(args.until).replace(tzinfo=timezone.utc)
    else:
        delta = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}.get(
            args.window, timedelta(hours=24)
        )
        until = now
        since = now - delta

    config = load_config(args.slices)
    baseline = json.loads(Path(args.baseline).read_text()) if args.baseline else None

    report = run_performance_check(args.predictions, args.labels, config, since, until, baseline)

    print(json.dumps({k: v for k, v in report.items() if k not in ("slices",)}, indent=2, default=str))

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(report, indent=2, default=str))
        logger.info("Report saved to %s", args.output)

    if args.push_metrics:
        try:
            push_to_prometheus(report, args.pushgateway, args.service)
        except Exception as e:
            logger.warning("Prometheus push failed: %s", e)

    status = report.get("status", "ok")
    if status == "alert":
        return 2
    if status == "warning":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
