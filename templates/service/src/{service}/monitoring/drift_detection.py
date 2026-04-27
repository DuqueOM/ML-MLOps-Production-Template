"""PSI-based drift detection for {ServiceName}.

Calculates Population Stability Index per feature using quantile-based bins.
Pushes results to Prometheus via Pushgateway and optionally triggers retraining.

Usage:
    python src/{service}/monitoring/drift_detection.py \\
        --reference data/reference/reference.csv \\
        --current data/production/latest.csv \\
        --output drift_report.json

    python src/{service}/monitoring/drift_detection.py --push-metrics
    python src/{service}/monitoring/drift_detection.py --update-reference
"""

import argparse
import json
import logging
import os
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

# Pandera schema and validator wired in PR-R2-4 (ADR-016): the drift
# CronJob MUST refuse to compute PSI on a malformed frame, otherwise a
# missing or renamed column produces a phantom drift alert (or worse,
# a phantom all-clear). Both imports are fail-soft so this module stays
# importable in stripped environments; the CLI flag --skip-schema is
# the documented escape hatch and emits a loud warning when used.
try:
    from common_utils.input_validation import (
        DriftSchemaError,
        validate_drift_dataframe,
    )
except ImportError:  # pragma: no cover - exercised only without common_utils
    DriftSchemaError = RuntimeError  # type: ignore[assignment,misc]

    def validate_drift_dataframe(df, schema, *, label="drift"):  # type: ignore[no-redef]
        return df


# PR-B2: optional EDA-baseline mode. When the canonical
# ``baseline_distributions.parquet`` produced by the EDA pipeline is
# available, drift detection can compute PSI against the precomputed
# quantile bins instead of recomputing them from a raw reference CSV
# on every run. This:
#  1. Removes the need to keep a multi-GB reference CSV mounted to the
#     drift CronJob (the parquet is typically <1 MB).
#  2. Locks the bin edges to the ones blessed by the operator at EDA
#     time, so a drifting feature cannot silently shift the bins
#     under us (which would mask drift, not reveal it).
#  3. Lets retrain trigger a NEW EDA + parquet refresh, providing a
#     single audit trail for "why did the bins change".
# Import is fail-soft so legacy CSV-reference mode keeps working in
# environments that don't ship the canonical EDA contract yet.
try:
    from common_utils.eda_artifacts import (
        EDAArtifactError,
        load_baseline_distributions,
    )
except ImportError:  # pragma: no cover
    load_baseline_distributions = None  # type: ignore[assignment]
    EDAArtifactError = RuntimeError  # type: ignore[misc,assignment]


try:
    from ..schemas import ServiceInputSchema
except ImportError:  # pragma: no cover - template-level only
    ServiceInputSchema = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — customize per service
# ---------------------------------------------------------------------------
PSI_BINS = 10
PSI_EPSILON = 1e-8

# Per-feature thresholds with domain reasoning
# TODO: Set real thresholds based on feature stability analysis
FEATURE_THRESHOLDS: dict[str, dict[str, float]] = {
    # "feature_a": {"warning": 0.10, "alert": 0.20, "reason": "historically stable"},
    # "feature_b": {"warning": 0.15, "alert": 0.30, "reason": "high natural variance"},
}

DEFAULT_WARNING = 0.10
DEFAULT_ALERT = 0.20

PUSHGATEWAY_URL = "pushgateway:9091"
JOB_NAME = "{service}-drift-detection"


def calculate_psi(
    reference: np.ndarray,
    current: np.ndarray,
    bins: int = PSI_BINS,
    epsilon: float = PSI_EPSILON,
) -> float:
    """Calculate PSI with quantile-based bins (NOT uniform bins).

    Why quantiles: uniform bins can have empty bins at extremes
    → PSI dominated by epsilon, not real data.
    Quantiles guarantee each bin has observations in the reference.

    Args:
        reference: Reference distribution (training data).
        current: Current distribution (production data).
        bins: Number of quantile bins.
        epsilon: Small value to prevent log(0).

    Returns:
        PSI value.
    """
    breakpoints = np.percentile(reference, np.linspace(0, 100, bins + 1))
    breakpoints[0] = -np.inf
    breakpoints[-1] = np.inf

    ref_counts, _ = np.histogram(reference, bins=breakpoints)
    cur_counts, _ = np.histogram(current, bins=breakpoints)

    ref_pct = np.maximum(ref_counts / len(reference), epsilon)
    cur_pct = np.maximum(cur_counts / len(current), epsilon)

    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


def calculate_psi_from_bins(
    bin_edges: np.ndarray,
    current: np.ndarray,
    *,
    epsilon: float = PSI_EPSILON,
) -> float:
    """PSI variant that uses precomputed bin edges from the EDA baseline.

    Why this exists (PR-B2): the legacy ``calculate_psi`` derives bins
    from the reference array at every call. With a fresh EDA run, the
    quantiles are blessed by the operator and stored in
    ``baseline_distributions.parquet``; recomputing them on every drift
    run defeats the purpose — a drifting feature would silently shift
    the bins, MASKING the drift rather than revealing it.

    Args:
        bin_edges: Quantile breakpoints from the EDA baseline. The first
            and last edges are replaced with ±inf so values outside the
            EDA-time range still bin somewhere (those tail-bin
            contributions ARE part of the drift signal we want).
        current: Current production distribution.
        epsilon: log(0) guard.

    Returns:
        PSI value. Reference percentage is implicit in the bin
        construction (each bin holds 1/N of the reference data by
        definition of quantiles).
    """
    if bin_edges.size < 2:
        # A degenerate baseline (constant feature) → no meaningful PSI.
        return 0.0

    breakpoints = bin_edges.copy().astype(float)
    breakpoints[0] = -np.inf
    breakpoints[-1] = np.inf

    cur_counts, _ = np.histogram(current, bins=breakpoints)
    n_bins = len(breakpoints) - 1

    # Reference is uniform over bins (quantile bins, by construction).
    # Using the empirical 1/n_bins keeps the formula identical to the
    # legacy path when both reference and current are sampled from the
    # same distribution → PSI ≈ 0.
    ref_pct = np.full(n_bins, 1.0 / n_bins)
    cur_pct = np.maximum(cur_counts / max(len(current), 1), epsilon)
    ref_pct = np.maximum(ref_pct, epsilon)

    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


def _bin_edges_from_baseline_df(baseline_df) -> dict[str, np.ndarray]:
    """Pivot the long-form parquet into ``{feature -> bin_edges}``.

    Only numeric features are returned; categorical baselines are
    handled by a different code path (frequency comparison rather than
    quantile PSI) which is out of scope for PR-B2 stage 2.
    """
    bins_df = baseline_df[baseline_df["kind"] == "numeric_bin_edge"].copy()
    if bins_df.empty:
        return {}
    bins_df["key_int"] = bins_df["key"].astype(int)
    bins_df = bins_df.sort_values(["feature", "key_int"])
    out: dict[str, np.ndarray] = {}
    for feature, group in bins_df.groupby("feature"):
        out[str(feature)] = group["value"].to_numpy(dtype=float)
    return out


def detect_drift(
    reference_path: Optional[str],
    current_path: str,
    output_path: Optional[str] = None,
    *,
    skip_schema: bool = False,
    eda_baseline_dir: Optional[str] = None,
) -> dict:
    """Run drift detection on all numeric features.

    Args:
        reference_path: Path to reference CSV. Required unless
            ``eda_baseline_dir`` is set, in which case it is used only
            for the per-feature reference mean/std cosmetic stats and
            may be omitted (then those stats are reported as ``None``).
        current_path: Path to current production CSV.
        output_path: Optional path to save JSON report.
        skip_schema: Bypass the Pandera validation pass. Off by default;
            set ``True`` only as a temporary forensics tool when the
            reference frame itself is known to be malformed and the
            operator wants to inspect raw PSI anyway. The ``main()``
            CLI exposes this via ``--skip-schema``.
        eda_baseline_dir: Optional directory containing
            ``baseline_distributions.parquet`` produced by the EDA
            pipeline (PR-B2). When provided, PSI is computed against
            the EDA-time precomputed quantile bins rather than
            recomputing them from the reference CSV. This is the
            preferred mode for production drift CronJobs — see the
            module docstring for the full rationale.

    Returns:
        Dict with per-feature PSI scores and status.

    Raises:
        common_utils.input_validation.DriftSchemaError: when the
            current frame fails the schema check and ``skip_schema``
            is False.
        ValueError: when neither ``reference_path`` nor
            ``eda_baseline_dir`` is provided.
    """
    if reference_path is None and eda_baseline_dir is None:
        raise ValueError(
            "detect_drift requires either reference_path (legacy CSV mode) "
            "or eda_baseline_dir (PR-B2 canonical mode)."
        )

    cur_df = pd.read_csv(current_path)
    ref_df = pd.read_csv(reference_path) if reference_path else None

    # Schema validation BEFORE PSI (PR-R2-4): a column rename or a type
    # mismatch in the production pipeline would otherwise look like
    # massive drift. Validate both frames so the earliest failure mode
    # surfaces first; the CronJob entrypoint catches DriftSchemaError
    # and exits with code 3 (distinct from real-drift codes 1/2).
    if skip_schema:
        logger.warning(
            "drift_detection: --skip-schema enabled; PSI will be computed on "
            "an unvalidated frame. Use only for forensics (PR-R2-4)."
        )
    else:
        cur_df = validate_drift_dataframe(cur_df, ServiceInputSchema, label="current")
        if ref_df is not None:
            ref_df = validate_drift_dataframe(ref_df, ServiceInputSchema, label="reference")

    # PR-B2 EDA-baseline mode: load precomputed bin edges once. When
    # this is active, ``ref_df`` is used only for cosmetic mean/std on
    # the report — never for bin construction.
    eda_bin_edges: dict[str, np.ndarray] = {}
    eda_baseline_used = False
    if eda_baseline_dir is not None:
        if load_baseline_distributions is None:
            raise RuntimeError(
                "eda_baseline_dir was provided but common_utils.eda_artifacts "
                "is not importable — install common_utils to use PR-B2 mode."
            )
        baseline_df = load_baseline_distributions(eda_baseline_dir)
        eda_bin_edges = _bin_edges_from_baseline_df(baseline_df)
        eda_baseline_used = True
        logger.info(
            "drift_detection: PR-B2 mode — using EDA baseline at %s " "(%d numeric features with precomputed bins)",
            eda_baseline_dir,
            len(eda_bin_edges),
        )

    # Determine which numeric columns to evaluate. In EDA-baseline mode
    # the source of truth is the parquet (the EDA run defines what is
    # numeric); in CSV mode we fall back to the reference frame's dtype
    # inference exactly as before.
    if eda_baseline_used:
        common_cols = [c for c in eda_bin_edges if c in cur_df.columns]
    else:
        assert ref_df is not None  # guarded above
        numeric_cols = ref_df.select_dtypes(include=[np.number]).columns
        common_cols = [c for c in numeric_cols if c in cur_df.columns]

    # PR-C1 (ADR-015): drift_run_id correlates this drift evaluation
    # across the JSON report, the audit log, GitHub Issues created on
    # alert, and the Pushgateway timestamp gauge. Format: 32-char hex.
    # Honour an inbound $DRIFT_RUN_ID env var so the CronJob workflow
    # can supply a deterministic id (e.g. ``drift-<run_id>-<attempt>``)
    # — same pattern used by the deploy chain for deployment_id.
    drift_run_id = os.getenv("DRIFT_RUN_ID") or uuid.uuid4().hex
    results: dict = {
        "drift_run_id": drift_run_id,
        "timestamp": time.time(),
        "features": {},
    }
    alerts: list[str] = []
    warnings: list[str] = []

    for col in common_cols:
        cur_vals = cur_df[col].dropna().values
        ref_vals = ref_df[col].dropna().values if ref_df is not None else None

        if len(cur_vals) == 0 or (ref_vals is not None and len(ref_vals) == 0):
            continue

        if eda_baseline_used:
            # PR-B2 path: PSI against the precomputed EDA quantile bins.
            psi = calculate_psi_from_bins(eda_bin_edges[col], cur_vals)
        else:
            assert ref_vals is not None
            psi = calculate_psi(ref_vals, cur_vals)

        thresholds = FEATURE_THRESHOLDS.get(col, {})
        warning_thresh = thresholds.get("warning", DEFAULT_WARNING)
        alert_thresh = thresholds.get("alert", DEFAULT_ALERT)

        if psi >= alert_thresh:
            status = "alert"
            alerts.append(col)
        elif psi >= warning_thresh:
            status = "warning"
            warnings.append(col)
        else:
            status = "ok"

        # Cosmetic reference stats — None when running in EDA-baseline
        # mode without a ref CSV; tooling that consumes the report
        # already tolerates None per ADR-016 §2.4.
        ref_mean = round(float(ref_vals.mean()), 4) if ref_vals is not None else None
        ref_std = round(float(ref_vals.std()), 4) if ref_vals is not None else None

        results["features"][col] = {
            "psi": round(psi, 6),
            "status": status,
            "warning_threshold": warning_thresh,
            "alert_threshold": alert_thresh,
            "reference_mean": ref_mean,
            "current_mean": round(float(cur_vals.mean()), 4),
            "reference_std": ref_std,
            "current_std": round(float(cur_vals.std()), 4),
        }

    results["summary"] = {
        "total_features": len(common_cols),
        "alerts": alerts,
        "warnings": warnings,
        "requires_action": len(alerts) > 0,
        "baseline_source": "eda_parquet" if eda_baseline_used else "reference_csv",
    }

    if output_path:
        Path(output_path).write_text(json.dumps(results, indent=2))
        logger.info("Drift report saved to %s", output_path)

    return results


def push_metrics(results: dict) -> None:
    """Push PSI scores to Prometheus via Pushgateway.

    PR-C1 (ADR-015): also pushes a ``{service}_drift_run_info`` gauge
    labelled with ``drift_run_id`` so post-incident queries can JOIN
    Prometheus samples to the JSON report and the audit entry.
    """
    registry = CollectorRegistry()

    psi_gauge = Gauge(
        "{service}_psi_score",
        "PSI drift score per feature",
        ["feature"],
        registry=registry,
    )

    timestamp_gauge = Gauge(
        "drift_detection_last_run_timestamp",
        "Unix timestamp of last successful drift detection run",
        registry=registry,
    )

    drift_run_info = Gauge(
        "{service}_drift_run_info",
        "Drift run correlation key (always 1; the value carries the timestamp)",
        ["drift_run_id"],
        registry=registry,
    )

    for feature, data in results.get("features", {}).items():
        psi_gauge.labels(feature=feature).set(data["psi"])

    timestamp_gauge.set(time.time())

    drift_run_id = results.get("drift_run_id", "unknown")
    drift_run_info.labels(drift_run_id=drift_run_id).set(1)

    push_to_gateway(PUSHGATEWAY_URL, job=JOB_NAME, registry=registry)
    logger.info("Metrics pushed to Pushgateway (drift_run_id=%s)", drift_run_id)


def create_github_issue(results: dict, repo: str, token: str) -> None:
    """Create a GitHub Issue when drift alert fires.

    Called by the CronJob when exit code is 2 (alert).
    The CI/CD workflow can also call this via drift-detection.yml.
    """
    alerts = results["summary"]["alerts"]
    drift_run_id = results.get("drift_run_id", "unknown")
    body_lines = [
        "## Drift Alert",
        "",
        f"**drift_run_id**: `{drift_run_id}`",
        f"**Features with alert-level PSI**: {', '.join(alerts)}",
        "",
        "| Feature | PSI | Status | Ref Mean | Cur Mean |",
        "|---------|-----|--------|----------|----------|",
    ]
    for feat, data in results["features"].items():
        body_lines.append(
            f"| {feat} | {data['psi']:.4f} | {data['status']} | "
            f"{data['reference_mean']:.4f} | {data['current_mean']:.4f} |"
        )
    body_lines += ["", "**Action required**: Investigate root cause and trigger `/retrain` if confirmed."]

    payload = json.dumps(
        {
            "title": f"[Drift Alert] {len(alerts)} feature(s) above PSI threshold",
            "body": "\n".join(body_lines),
            "labels": ["drift", "automated"],
        }
    ).encode("utf-8")

    req = Request(
        f"https://api.github.com/repos/{repo}/issues",
        data=payload,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req) as resp:
            issue = json.loads(resp.read())
            logger.info("GitHub Issue created: %s", issue.get("html_url"))
    except Exception as e:
        logger.error("Failed to create GitHub Issue: %s", e)


def update_reference(current_path: str, reference_path: str) -> None:
    """Replace reference data with current production data.

    Called after a successful retraining to reset the drift baseline.
    Keeps a timestamped backup of the old reference.
    """
    ref = Path(reference_path)
    if ref.exists():
        backup = ref.with_suffix(f".backup_{int(time.time())}.csv")
        shutil.copy2(ref, backup)
        logger.info("Backed up old reference to %s", backup)

    shutil.copy2(current_path, reference_path)
    logger.info("Reference updated from %s", current_path)


def main() -> int:
    """CLI entry point with exit codes for CronJob integration.

    Exit codes:
        0 — No drift detected (all features OK)
        1 — Warning-level drift (some features elevated)
        2 — Alert-level drift (action required, triggers issue creation)
        3 — Schema mismatch detected before PSI (PR-R2-4); operator
            must fix the data pipeline before treating it as drift.
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")

    parser = argparse.ArgumentParser(description="Drift detection for {ServiceName}")
    parser.add_argument(
        "--reference",
        help=(
            "Path to reference CSV. Required unless --eda-baseline is set, "
            "in which case it becomes optional and is used only for "
            "cosmetic reference mean/std on the report."
        ),
    )
    parser.add_argument("--current", required=True, help="Path to current production CSV")
    parser.add_argument("--output", help="Path to save JSON report")
    parser.add_argument(
        "--eda-baseline",
        help=(
            "Directory containing baseline_distributions.parquet from the "
            "EDA pipeline (PR-B2). When provided, PSI is computed against "
            "the precomputed quantile bins instead of recomputing from the "
            "reference CSV."
        ),
    )
    parser.add_argument("--push-metrics", action="store_true", help="Push to Pushgateway")
    parser.add_argument("--create-issue", action="store_true", help="Create GitHub Issue on alert")
    parser.add_argument("--update-reference", action="store_true", help="Replace reference with current")
    parser.add_argument(
        "--skip-schema",
        action="store_true",
        help="Bypass Pandera schema validation (forensics only; emits a warning).",
    )
    args = parser.parse_args()

    if not args.reference and not args.eda_baseline:
        parser.error("provide --reference, --eda-baseline, or both")

    try:
        results = detect_drift(
            args.reference,
            args.current,
            args.output,
            skip_schema=args.skip_schema,
            eda_baseline_dir=args.eda_baseline,
        )
    except DriftSchemaError as exc:
        # Distinct exit code so retry/alert logic can tell schema breakage
        # apart from real PSI drift (codes 1/2). Operators should fix the
        # data pipeline, not retrain the model (PR-R2-4).
        logger.error("Drift detection aborted before PSI: %s", exc)
        return 3
    print(json.dumps(results["summary"], indent=2))

    if args.push_metrics:
        push_metrics(results)

    if args.update_reference:
        if not args.reference:
            logger.error(
                "--update-reference requires --reference (CSV mode). "
                "In PR-B2 EDA-baseline mode, refresh the baseline by "
                "re-running the EDA pipeline instead."
            )
            return 3
        update_reference(args.current, args.reference)

    has_alerts = results["summary"]["requires_action"]
    has_warnings = len(results["summary"]["warnings"]) > 0

    if has_alerts:
        logger.warning("ALERT: Drift detected in %s", results["summary"]["alerts"])
        if args.create_issue:
            repo = os.getenv("GITHUB_REPOSITORY", "")
            token = os.getenv("GITHUB_TOKEN", "")
            if repo and token:
                create_github_issue(results, repo, token)
            else:
                logger.warning("GITHUB_REPOSITORY or GITHUB_TOKEN not set — skipping issue")
        return 2
    elif has_warnings:
        logger.info("WARNING: Elevated PSI in %s", results["summary"]["warnings"])
        return 1
    else:
        logger.info("OK: No drift detected")
        return 0


if __name__ == "__main__":
    sys.exit(main())
