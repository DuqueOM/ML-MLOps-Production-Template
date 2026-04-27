"""Canonical EDA artifact contract — ADR-015 PR-B2.

A single source of truth for the five machine-readable artifacts the
EDA pipeline (``templates/eda/eda_pipeline.py``) produces and that
training / drift / retrain consume. Adopters import from this module
instead of hard-coding file paths so the contract is enforceable.

The five artifacts (canonical names, all under ``eda/artifacts/``):

================================ ================ =========================================================
File                              Format           Purpose
================================ ================ =========================================================
``eda_summary.json``              JSON             Top-level run metadata (target, n_rows, runtime, version)
``schema_ranges.json``            JSON             Per-feature dtype + observed ranges (numeric & categorical)
``baseline_distributions.parquet`` Parquet          Per-feature reference distribution — drift PSI input
``feature_catalog.yaml``          YAML             Proposed transformations with rationale (D-16)
``leakage_report.json``           JSON             Blocked features + thresholds (machine-readable D-13/14)
================================ ================ =========================================================

Why a separate module instead of constants in ``eda_pipeline.py``?
-----------------------------------------------------------------
- ``eda_pipeline.py`` is the PRODUCER. Drift / training are CONSUMERS.
  Putting the path constants in the producer would force every consumer
  to import ``eda``, dragging pandas/numpy onto the import graph of
  modules that may not need them.
- This module imports only stdlib + the loader's own format library
  (``json``, ``yaml``, ``pyarrow``/``pandas`` for parquet — the latter
  only on the relevant loader). Drift-detection consumers that already
  have pandas pay nothing extra; retrain workflow consumers that only
  need the JSON files don't import pandas at all.

Versioning
----------
Every artifact embeds an ``eda_artifact_version`` integer (currently
``ARTIFACT_VERSION = 1``). Loaders raise :class:`EDAArtifactVersionError`
when they encounter a newer or older incompatible version, so a
silently-upgraded pipeline cannot corrupt downstream consumers.

The version is bumped only on a BREAKING schema change. Additive
changes (new optional fields) keep the same version. The bump is the
producer's responsibility; consumers must be updated in lock-step.

Backward-compat with legacy artifacts
-------------------------------------
The old artifact names (``02_baseline_distributions.pkl``,
``05_feature_proposals.yaml``, ``04_leakage_audit.md``) are still
emitted by the pipeline for one transition cycle so existing notebooks
and ad-hoc scripts keep working. Loaders here only accept the canonical
names — anyone consuming the contract is on the new path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ARTIFACT_VERSION is an integer that producers stamp into every file
# they write. Consumers compare strict equality; mismatch raises so a
# silent format break surfaces at load time, not as garbled data three
# layers deep in a PSI computation.
ARTIFACT_VERSION = 1

# Canonical filenames — any consumer that hard-codes a string outside
# this module is a bug. Glob-style search (`grep -r`) over the repo
# should turn up only this file as the producer of these literals.
EDA_SUMMARY_FILENAME = "eda_summary.json"
SCHEMA_RANGES_FILENAME = "schema_ranges.json"
BASELINE_DISTRIBUTIONS_FILENAME = "baseline_distributions.parquet"
FEATURE_CATALOG_FILENAME = "feature_catalog.yaml"
LEAKAGE_REPORT_FILENAME = "leakage_report.json"

ALL_FILENAMES: tuple[str, ...] = (
    EDA_SUMMARY_FILENAME,
    SCHEMA_RANGES_FILENAME,
    BASELINE_DISTRIBUTIONS_FILENAME,
    FEATURE_CATALOG_FILENAME,
    LEAKAGE_REPORT_FILENAME,
)

# Default location relative to a service's repo root. Override via
# ``base_dir`` on every loader to support multi-dataset services.
DEFAULT_ARTIFACTS_DIR = Path("eda") / "artifacts"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class EDAArtifactError(RuntimeError):
    """Base class for every error this module raises."""


class EDAArtifactNotFoundError(EDAArtifactError, FileNotFoundError):
    """Canonical artifact file is missing.

    Inherits from FileNotFoundError so existing ``except FileNotFoundError``
    clauses in caller code continue to work — but the type name carries
    the more precise diagnosis.
    """


class EDAArtifactVersionError(EDAArtifactError):
    """Artifact ``eda_artifact_version`` doesn't match ARTIFACT_VERSION.

    Raised on BOTH older (consumer is newer than producer) and newer
    (producer is newer than consumer) cases. The message names both
    versions so the operator can pick which side to upgrade.
    """


class EDAArtifactSchemaError(EDAArtifactError):
    """Artifact loaded but a required top-level key is missing.

    Catches the ``producer wrote partial output then crashed`` failure
    mode without us having to plumb a ``.complete`` sentinel into every
    file. Each loader names the missing key in the message.
    """


# ---------------------------------------------------------------------------
# Typed dataclasses for the JSON / YAML artifacts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EDASummary:
    """Top-level metadata describing one EDA run.

    Mapped 1:1 to ``eda_summary.json``. Keeping this frozen means a
    consumer cannot accidentally mutate it and write back a corrupted
    file (loaders never write).
    """

    target: str
    n_rows: int
    n_columns: int
    runtime_seconds: float
    pipeline_git_sha: str | None
    eda_artifact_version: int = ARTIFACT_VERSION
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SchemaRangeEntry:
    """One row of ``schema_ranges.json``."""

    name: str
    dtype: str
    nullable: bool
    null_pct: float
    cardinality: int
    # Numeric-only (None for categorical):
    minimum: float | None = None
    maximum: float | None = None
    mean: float | None = None
    std: float | None = None
    # Categorical-only (empty for numeric):
    top_values: tuple[str, ...] = ()


@dataclass(frozen=True)
class LeakageReport:
    """Machine-readable equivalent of ``reports/04_leakage_audit.md``.

    A consumer can JOIN this into training to refuse to start when
    blocked features are still present (PR-B3 wires this). Loaders
    return this dataclass; producers serialize from a dict.
    """

    status: str  # "PASSED" | "BLOCKED"
    blocked_features: tuple[str, ...]
    findings: tuple[dict[str, Any], ...]
    thresholds: dict[str, float]
    eda_artifact_version: int = ARTIFACT_VERSION

    @property
    def passed(self) -> bool:
        return self.status == "PASSED" and not self.blocked_features


# ---------------------------------------------------------------------------
# Loaders — one per artifact
# ---------------------------------------------------------------------------


def _resolve(filename: str, base_dir: Path | str | None) -> Path:
    base = Path(base_dir) if base_dir is not None else DEFAULT_ARTIFACTS_DIR
    path = base / filename
    if not path.exists():
        raise EDAArtifactNotFoundError(
            f"EDA artifact missing: {path}. Run the pipeline first: "
            f"`python -m eda.eda_pipeline --input ... --target ...`"
        )
    return path


def _check_version(payload: dict, where: Path) -> None:
    found = payload.get("eda_artifact_version")
    if found is None:
        raise EDAArtifactSchemaError(
            f"{where}: missing required key 'eda_artifact_version' "
            f"(this loader expects version {ARTIFACT_VERSION})"
        )
    if found != ARTIFACT_VERSION:
        raise EDAArtifactVersionError(
            f"{where}: artifact version {found} does not match "
            f"loader version {ARTIFACT_VERSION}. Re-run the EDA pipeline "
            f"or upgrade the consuming service."
        )


def load_eda_summary(base_dir: Path | str | None = None) -> EDASummary:
    """Load and parse ``eda_summary.json``."""
    path = _resolve(EDA_SUMMARY_FILENAME, base_dir)
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    _check_version(payload, path)
    required = {"target", "n_rows", "n_columns", "runtime_seconds"}
    missing = required - set(payload)
    if missing:
        raise EDAArtifactSchemaError(f"{path}: missing keys {sorted(missing)}")
    return EDASummary(
        target=payload["target"],
        n_rows=int(payload["n_rows"]),
        n_columns=int(payload["n_columns"]),
        runtime_seconds=float(payload["runtime_seconds"]),
        pipeline_git_sha=payload.get("pipeline_git_sha"),
        eda_artifact_version=int(payload["eda_artifact_version"]),
        extras={k: v for k, v in payload.items() if k not in required | {"eda_artifact_version", "pipeline_git_sha"}},
    )


def load_schema_ranges(base_dir: Path | str | None = None) -> tuple[SchemaRangeEntry, ...]:
    """Load and parse ``schema_ranges.json``.

    Returns a tuple of frozen entries; ordering matches the pipeline's
    column order so consumers can rely on it for stable codegen.
    """
    path = _resolve(SCHEMA_RANGES_FILENAME, base_dir)
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    _check_version(payload, path)
    if "features" not in payload:
        raise EDAArtifactSchemaError(f"{path}: missing key 'features'")

    out: list[SchemaRangeEntry] = []
    for entry in payload["features"]:
        out.append(
            SchemaRangeEntry(
                name=entry["name"],
                dtype=entry["dtype"],
                nullable=bool(entry.get("nullable", False)),
                null_pct=float(entry.get("null_pct", 0.0)),
                cardinality=int(entry.get("cardinality", 0)),
                minimum=entry.get("minimum"),
                maximum=entry.get("maximum"),
                mean=entry.get("mean"),
                std=entry.get("std"),
                top_values=tuple(entry.get("top_values", ())),
            )
        )
    return tuple(out)


def load_baseline_distributions(base_dir: Path | str | None = None):
    """Load and parse ``baseline_distributions.parquet``.

    Returns a ``pandas.DataFrame`` in long form with columns:
    ``feature, kind, key, value`` where:

    - ``kind`` ∈ ``{numeric_bin_edge, numeric_stat, categorical_freq}``
    - ``key`` is the bin index / stat name / category label
    - ``value`` is the corresponding number (bin edge / mean / freq)

    Long form is chosen over a per-feature dict-of-dicts because
    parquet stores it efficiently and consumers can pivot with one
    pandas call. Versioning lives in the parquet metadata footer
    (``eda_artifact_version=1``) so we can't write structured headers.

    pandas + pyarrow are imported here lazily so consumers that don't
    need the parquet artifact (e.g. retrain just reading the JSON
    files) don't pay the import cost.
    """
    import pandas as pd  # noqa: PLC0415  — intentional lazy import

    path = _resolve(BASELINE_DISTRIBUTIONS_FILENAME, base_dir)
    df = pd.read_parquet(path)

    # parquet metadata is preserved by pyarrow; pandas exposes it via
    # the ``attrs`` dict if we round-trip through pyarrow Table. To
    # keep the loader portable we instead require the version column.
    if "eda_artifact_version" not in df.columns:
        raise EDAArtifactSchemaError(f"{path}: missing 'eda_artifact_version' column")
    versions = set(df["eda_artifact_version"].unique())
    if versions != {ARTIFACT_VERSION}:
        raise EDAArtifactVersionError(
            f"{path}: artifact version(s) {versions} do not match "
            f"loader version {ARTIFACT_VERSION}"
        )
    required_cols = {"feature", "kind", "key", "value", "eda_artifact_version"}
    missing = required_cols - set(df.columns)
    if missing:
        raise EDAArtifactSchemaError(f"{path}: missing columns {sorted(missing)}")
    return df


def load_feature_catalog(base_dir: Path | str | None = None) -> dict[str, Any]:
    """Load and parse ``feature_catalog.yaml``.

    Returns the parsed YAML as a plain dict — feature engineering
    consumers iterate ``catalog["transforms"]`` and apply each entry.
    Every transform MUST carry a ``rationale`` field (D-16); this
    loader rejects payloads that violate that invariant up-front so
    the failure surfaces here, not during model training.
    """
    import yaml  # noqa: PLC0415  — keeps stdlib-only paths lighter

    path = _resolve(FEATURE_CATALOG_FILENAME, base_dir)
    with path.open("r", encoding="utf-8") as fh:
        payload = yaml.safe_load(fh) or {}

    if not isinstance(payload, dict):
        raise EDAArtifactSchemaError(f"{path}: top-level value must be a YAML mapping")
    _check_version(payload, path)

    transforms = payload.get("transforms")
    if transforms is None:
        raise EDAArtifactSchemaError(f"{path}: missing key 'transforms'")
    if not isinstance(transforms, list):
        raise EDAArtifactSchemaError(f"{path}: 'transforms' must be a list")

    for idx, t in enumerate(transforms):
        if not isinstance(t, dict):
            raise EDAArtifactSchemaError(f"{path}: transforms[{idx}] is not a mapping")
        if "rationale" not in t or not str(t["rationale"]).strip():
            raise EDAArtifactSchemaError(
                f"{path}: transforms[{idx}] (name={t.get('name', '?')}) lacks "
                f"a non-empty 'rationale' (D-16 violation)"
            )
    return payload


def load_leakage_report(base_dir: Path | str | None = None) -> LeakageReport:
    """Load and parse ``leakage_report.json``."""
    path = _resolve(LEAKAGE_REPORT_FILENAME, base_dir)
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    _check_version(payload, path)
    required = {"status", "blocked_features", "findings", "thresholds"}
    missing = required - set(payload)
    if missing:
        raise EDAArtifactSchemaError(f"{path}: missing keys {sorted(missing)}")
    return LeakageReport(
        status=str(payload["status"]),
        blocked_features=tuple(payload["blocked_features"]),
        findings=tuple(payload["findings"]),
        thresholds=dict(payload["thresholds"]),
        eda_artifact_version=int(payload["eda_artifact_version"]),
    )


# ---------------------------------------------------------------------------
# Discovery / introspection helpers (used by tests + scripts)
# ---------------------------------------------------------------------------


def expected_artifact_paths(base_dir: Path | str | None = None) -> tuple[Path, ...]:
    """Return the canonical (filename → full path) tuple for every artifact.

    Useful for tests, CI ``--require-all-artifacts`` checks, and the
    docs generator.
    """
    base = Path(base_dir) if base_dir is not None else DEFAULT_ARTIFACTS_DIR
    return tuple(base / f for f in ALL_FILENAMES)


def missing_artifacts(base_dir: Path | str | None = None) -> tuple[Path, ...]:
    """Return the subset of canonical artifacts that do NOT exist on disk.

    A scaffolded service that has not yet run EDA returns the full
    five; a service mid-pipeline returns whichever phases haven't
    completed. Consumers can use this to produce a single actionable
    error message instead of five separate FileNotFoundError tracebacks.
    """
    return tuple(p for p in expected_artifact_paths(base_dir) if not p.exists())


__all__ = [
    "ARTIFACT_VERSION",
    "ALL_FILENAMES",
    "DEFAULT_ARTIFACTS_DIR",
    "EDA_SUMMARY_FILENAME",
    "SCHEMA_RANGES_FILENAME",
    "BASELINE_DISTRIBUTIONS_FILENAME",
    "FEATURE_CATALOG_FILENAME",
    "LEAKAGE_REPORT_FILENAME",
    "EDAArtifactError",
    "EDAArtifactNotFoundError",
    "EDAArtifactSchemaError",
    "EDAArtifactVersionError",
    "EDASummary",
    "SchemaRangeEntry",
    "LeakageReport",
    "load_eda_summary",
    "load_schema_ranges",
    "load_baseline_distributions",
    "load_feature_catalog",
    "load_leakage_report",
    "expected_artifact_paths",
    "missing_artifacts",
]
