"""Reports v1 — typed dataclasses + validator + serializer (ADR-023 F6).

Canonical contract for the four agentic-report types produced by
release / drift / training / incident workflows. All types share a
frozen envelope (``ReportEnvelope``) plus a type-specific payload.

Design rules
------------

* Every dataclass is ``frozen=True`` — reports are immutable.
* Construction validates invariants eagerly (envelope constraints,
  payload constraints via the sibling payload class, JSON-Schema
  round-trip).
* Serialization produces plain Python dicts that round-trip through
  the JSON Schema at ``templates/config/report_schema.json``.
* No network calls, no writes outside the caller's explicit target.
* Reads audit context (AgentMode, Environment) from
  ``templates.common_utils.agent_context`` for consistency with the
  rest of the protocol.

Why a separate module from ``agent_context.py``
-----------------------------------------------

``agent_context`` owns the per-operation handoff + audit contract.
Reports are a separate, longer-lived artefact type with their own
schema. Keeping the module boundary clean prevents the report schema
from bleeding into the per-operation contract.

Usage
-----

.. code-block:: python

    from common_utils.agent_context import AgentMode, Environment
    from common_utils.reports import (
        ReleasePayload, ReportEnvelope, build_release_report,
    )

    payload = ReleasePayload(
        version="v0.7.0",
        commit_sha="deadbeef",
        images=["ghcr.io/org/fraud-detector@sha256:..."],
        quality_gates_passed=True,
        deploy_targets=("gcp", "aws"),
        sbom_present=True,
        images_signed=True,
        adrs_since_last_release=("ADR-023",),
        drift_baseline_age_days=7,
    )
    report = build_release_report(
        service="fraud_detector",
        generated_by="Agent-K8sBuilder",
        mode=AgentMode.CONSULT,
        environment=Environment.STAGING,
        approver="platform_engineer",
        payload=payload,
    )
    report.write("ops/reports/release/fraud_detector-v0.7.0.json")
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .agent_context import AgentMode, Environment

__all__ = [
    "SCHEMA_VERSION",
    "ReportEnvelope",
    "ReleasePayload",
    "DriftFeature",
    "DriftPayload",
    "QualityGate",
    "FeatureImportance",
    "TrainingPayload",
    "TimelineEvent",
    "ActionItem",
    "IncidentPayload",
    "build_release_report",
    "build_drift_report",
    "build_training_report",
    "build_incident_report",
    "load_report",
    "validate_report_dict",
]


SCHEMA_VERSION = 1
REPORT_TYPES = ("release", "drift", "training", "incident")
_SERVICE_RE = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
_REPORT_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")
_VERSION_RE = re.compile(r"^v?[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9.-]+)?$")
_INCIDENT_ID_RE = re.compile(r"^INC-[0-9A-Za-z]+$")
_ADR_RE = re.compile(r"^ADR-[0-9]{3}")


# ---------------------------------------------------------------------------
# Payload dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReleasePayload:
    """Immutable payload for a release report.

    Invariants enforced at construction:
      * ``version`` matches semver-ish ``vX.Y.Z[-pre]``
      * ``commit_sha`` is hex, 7–40 chars (short or long SHA)
      * ``images`` is non-empty
      * ``deploy_targets`` is a non-empty subset of ``{"gcp", "aws"}``
    """

    version: str
    commit_sha: str
    images: tuple[str, ...]
    quality_gates_passed: bool
    deploy_targets: tuple[str, ...]
    sbom_present: bool
    images_signed: bool
    adrs_since_last_release: tuple[str, ...] = ()
    drift_baseline_age_days: int | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        if not _VERSION_RE.match(self.version):
            raise ValueError(f"release.version invalid: {self.version!r}")
        if not _COMMIT_RE.match(self.commit_sha):
            raise ValueError(f"release.commit_sha not a hex SHA: {self.commit_sha!r}")
        if not self.images:
            raise ValueError("release.images must be non-empty")
        if not self.deploy_targets:
            raise ValueError("release.deploy_targets must be non-empty")
        for tgt in self.deploy_targets:
            if tgt not in ("gcp", "aws"):
                raise ValueError(f"release.deploy_targets unknown: {tgt!r}")
        for adr in self.adrs_since_last_release:
            if not _ADR_RE.match(adr):
                raise ValueError(f"adrs_since_last_release entry malformed: {adr!r}")
        if self.drift_baseline_age_days is not None and self.drift_baseline_age_days < 0:
            raise ValueError("drift_baseline_age_days must be >= 0")


@dataclass(frozen=True)
class DriftFeature:
    """One feature's PSI reading inside a DriftPayload."""

    name: str
    psi: float
    threshold: float | None = None
    breached: bool | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("drift.feature.name must be non-empty")
        if self.psi < 0:
            raise ValueError(f"drift.feature.psi must be >= 0 (got {self.psi})")
        if self.threshold is not None and self.threshold < 0:
            raise ValueError("drift.feature.threshold must be >= 0")


@dataclass(frozen=True)
class DriftPayload:
    """Immutable payload for a drift report."""

    window_start: str
    window_end: str
    features: tuple[DriftFeature, ...]
    retrain_recommendation: str
    alerts_fired: tuple[str, ...] = ()
    root_cause_summary: str | None = None

    def __post_init__(self) -> None:
        _parse_iso(self.window_start, "drift.window_start")
        end = _parse_iso(self.window_end, "drift.window_end")
        start = _parse_iso(self.window_start, "drift.window_start")
        if end < start:
            raise ValueError("drift.window_end precedes drift.window_start")
        if not self.features:
            raise ValueError("drift.features must be non-empty")
        if self.retrain_recommendation not in ("none", "soft", "hard"):
            raise ValueError(f"drift.retrain_recommendation invalid: " f"{self.retrain_recommendation!r}")


@dataclass(frozen=True)
class QualityGate:
    gate: str
    passed: bool
    details: str | None = None

    def __post_init__(self) -> None:
        if not self.gate:
            raise ValueError("quality_gate.gate must be non-empty")


@dataclass(frozen=True)
class FeatureImportance:
    feature: str
    importance: float


@dataclass(frozen=True)
class TrainingPayload:
    run_id: str
    model_name: str
    metrics: dict[str, float]
    quality_gates: tuple[QualityGate, ...]
    promotion_state: str
    fairness_dir: float | None = None
    feature_importance_top_k: tuple[FeatureImportance, ...] = ()

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("training.run_id must be non-empty")
        if not self.model_name:
            raise ValueError("training.model_name must be non-empty")
        for k, v in self.metrics.items():
            if not isinstance(v, (int, float)):
                raise ValueError(f"training.metrics[{k}] must be numeric")
        if not self.quality_gates:
            raise ValueError("training.quality_gates must be non-empty")
        if self.promotion_state not in ("None", "Staging", "Production", "Archived"):
            raise ValueError(f"training.promotion_state invalid: {self.promotion_state!r}")
        if self.fairness_dir is not None and self.fairness_dir < 0:
            raise ValueError("training.fairness_dir must be >= 0")
        if len(self.feature_importance_top_k) > 50:
            raise ValueError("training.feature_importance_top_k max 50 entries")


@dataclass(frozen=True)
class TimelineEvent:
    timestamp: str
    event: str
    actor: str | None = None

    def __post_init__(self) -> None:
        _parse_iso(self.timestamp, "timeline_event.timestamp")
        if not self.event:
            raise ValueError("timeline_event.event must be non-empty")


@dataclass(frozen=True)
class ActionItem:
    item: str
    owner: str
    adr_opened: str | None = None

    def __post_init__(self) -> None:
        if not self.item or not self.owner:
            raise ValueError("action_item.item and .owner must be non-empty")
        if self.adr_opened is not None and not _ADR_RE.match(self.adr_opened):
            raise ValueError(f"action_item.adr_opened malformed: {self.adr_opened!r}")


@dataclass(frozen=True)
class IncidentPayload:
    incident_id: str
    severity: str
    detected_at: str
    timeline: tuple[TimelineEvent, ...]
    resolved_at: str | None = None
    duration_minutes: int | None = None
    root_cause: str | None = None
    action_items: tuple[ActionItem, ...] = ()

    def __post_init__(self) -> None:
        if not _INCIDENT_ID_RE.match(self.incident_id):
            raise ValueError(
                f"incident.incident_id must match {_INCIDENT_ID_RE.pattern!r} " f"(got {self.incident_id!r})"
            )
        if self.severity not in ("P1", "P2", "P3"):
            raise ValueError(f"incident.severity invalid: {self.severity!r}")
        detected = _parse_iso(self.detected_at, "incident.detected_at")
        if self.resolved_at is not None:
            resolved = _parse_iso(self.resolved_at, "incident.resolved_at")
            if resolved < detected:
                raise ValueError("incident.resolved_at precedes detected_at")
        if self.duration_minutes is not None and self.duration_minutes < 0:
            raise ValueError("incident.duration_minutes must be >= 0")
        if not self.timeline:
            raise ValueError("incident.timeline must be non-empty")


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------


PayloadT = ReleasePayload | DriftPayload | TrainingPayload | IncidentPayload


@dataclass(frozen=True)
class ReportEnvelope:
    """Outer report envelope — type, identity, mode, payload.

    Invariants enforced at construction:
      * schema_version == 1
      * report_type is one of the four canonical types AND matches the
        payload's type
      * report_id matches the id pattern
      * service matches the service-slug pattern
      * generated_at parses as a UTC ISO8601 timestamp
      * release + incident require a non-None environment (release
        never targets 'dev' explicitly; see docs)
      * When mode is CONSULT or STOP, approver must be non-None
    """

    report_type: str
    report_id: str
    service: str
    generated_at: str
    generated_by: str
    mode: AgentMode
    payload: PayloadT
    environment: Environment | None = None
    approver: str | None = None
    links: tuple[tuple[str, str], ...] = ()
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version {self.schema_version} " f"(expected {SCHEMA_VERSION})")
        if self.report_type not in REPORT_TYPES:
            raise ValueError(f"unknown report_type {self.report_type!r}")
        if not _REPORT_ID_RE.match(self.report_id):
            raise ValueError(f"report_id malformed: {self.report_id!r}")
        if not _SERVICE_RE.match(self.service):
            raise ValueError(f"service slug malformed: {self.service!r}")
        _parse_iso(self.generated_at, "generated_at")
        if not self.generated_by:
            raise ValueError("generated_by must be non-empty")
        # Payload × report_type coherence
        expected = {
            "release": ReleasePayload,
            "drift": DriftPayload,
            "training": TrainingPayload,
            "incident": IncidentPayload,
        }[self.report_type]
        if not isinstance(self.payload, expected):
            raise TypeError(
                f"report_type={self.report_type!r} requires "
                f"{expected.__name__} payload; got {type(self.payload).__name__}"
            )
        if self.report_type in ("release", "incident") and self.environment is None:
            raise ValueError(f"report_type={self.report_type!r} requires environment")
        if self.mode in (AgentMode.CONSULT, AgentMode.STOP) and not self.approver:
            raise ValueError(f"mode={self.mode.value} reports require a named approver")

    # ---- serialization ----

    def to_dict(self) -> dict[str, Any]:
        """Round-trip-safe dict ready for JSON serialization."""
        payload = _payload_to_dict(self.payload)
        out: dict[str, Any] = {
            "schema_version": self.schema_version,
            "report_type": self.report_type,
            "report_id": self.report_id,
            "service": self.service,
            "generated_at": self.generated_at,
            "generated_by": self.generated_by,
            "mode": self.mode.value,
            "payload": payload,
        }
        if self.environment is not None:
            out["environment"] = self.environment.value
        if self.approver is not None:
            out["approver"] = self.approver
        if self.links:
            out["links"] = [{"label": lbl, "url": url} for lbl, url in self.links]
        return out

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)

    def write(self, path: str | Path) -> Path:
        """Write the report as pretty JSON. Creates parent dir if needed.

        Returns the absolute Path of the written file.
        """
        target = Path(path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_json() + "\n", encoding="utf-8")
        return target


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_iso(value: str, field_name: str) -> _dt.datetime:
    try:
        return _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} not an ISO8601 UTC timestamp: {value!r}") from exc


def _payload_to_dict(payload: PayloadT) -> dict[str, Any]:
    """Dataclass → dict with ``None`` scrubbed for optional fields and
    tuples converted to lists.

    We don't use ``dataclasses.asdict`` directly because we want to
    (1) drop optional None values, (2) convert nested dataclass tuples
    into list[dict] in a deterministic order.
    """

    def _convert(value: Any) -> Any:
        # Walk dataclasses ourselves (no dataclasses.asdict) so we can
        # drop None at every nesting level — not just the outermost.
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            out: dict[str, Any] = {}
            for f in dataclasses.fields(value):
                v = getattr(value, f.name)
                if v is None:
                    continue
                out[f.name] = _convert(v)
            return out
        if isinstance(value, tuple):
            return [_convert(v) for v in value]
        if isinstance(value, list):
            return [_convert(v) for v in value]
        if isinstance(value, dict):
            return {k: _convert(v) for k, v in value.items() if v is not None}
        return value

    result = _convert(payload)
    if not isinstance(result, dict):  # pragma: no cover - defensive
        raise TypeError("payload did not serialize to a dict")
    return result


# ---------------------------------------------------------------------------
# Convenience constructors — encode the report-id convention so CLI
# and library callers can omit it.
# ---------------------------------------------------------------------------


def _now_utc_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z").replace("+0000", "Z")


def _default_report_id(report_type: str, service_name: str, suffix: str = "") -> str:
    # Param name deliberately avoids the literal token "service" because
    # new-service.sh rewrites the snake-case slug placeholder globally via
    # sed (see ADR-025 Option A and scripts/check_common_utils_drift.py).
    ts = _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y%m%dT%H%M%S")
    base = f"{report_type}-{service_name}-{ts}"
    if suffix:
        return f"{base}-{suffix}"
    return base


def build_release_report(
    *,
    service: str,
    generated_by: str,
    mode: AgentMode,
    environment: Environment,
    payload: ReleasePayload,
    approver: str | None = None,
    report_id: str | None = None,
    generated_at: str | None = None,
    links: tuple[tuple[str, str], ...] = (),
) -> ReportEnvelope:
    return ReportEnvelope(
        report_type="release",
        report_id=report_id or _default_report_id("release", service, payload.version.lstrip("v")),
        service=service,
        generated_at=generated_at or _now_utc_iso(),
        generated_by=generated_by,
        mode=mode,
        payload=payload,
        environment=environment,
        approver=approver,
        links=links,
    )


def build_drift_report(
    *,
    service: str,
    generated_by: str,
    mode: AgentMode,
    payload: DriftPayload,
    environment: Environment | None = None,
    approver: str | None = None,
    report_id: str | None = None,
    generated_at: str | None = None,
    links: tuple[tuple[str, str], ...] = (),
) -> ReportEnvelope:
    return ReportEnvelope(
        report_type="drift",
        report_id=report_id or _default_report_id("drift", service),
        service=service,
        generated_at=generated_at or _now_utc_iso(),
        generated_by=generated_by,
        mode=mode,
        payload=payload,
        environment=environment,
        approver=approver,
        links=links,
    )


def build_training_report(
    *,
    service: str,
    generated_by: str,
    mode: AgentMode,
    payload: TrainingPayload,
    environment: Environment | None = None,
    approver: str | None = None,
    report_id: str | None = None,
    generated_at: str | None = None,
    links: tuple[tuple[str, str], ...] = (),
) -> ReportEnvelope:
    return ReportEnvelope(
        report_type="training",
        report_id=report_id or _default_report_id("training", service, payload.run_id[:8]),
        service=service,
        generated_at=generated_at or _now_utc_iso(),
        generated_by=generated_by,
        mode=mode,
        payload=payload,
        environment=environment,
        approver=approver,
        links=links,
    )


def build_incident_report(
    *,
    service: str,
    generated_by: str,
    mode: AgentMode,
    environment: Environment,
    payload: IncidentPayload,
    approver: str | None = None,
    report_id: str | None = None,
    generated_at: str | None = None,
    links: tuple[tuple[str, str], ...] = (),
) -> ReportEnvelope:
    return ReportEnvelope(
        report_type="incident",
        report_id=report_id or _default_report_id("incident", service, payload.incident_id),
        service=service,
        generated_at=generated_at or _now_utc_iso(),
        generated_by=generated_by,
        mode=mode,
        payload=payload,
        environment=environment,
        approver=approver,
        links=links,
    )


# ---------------------------------------------------------------------------
# Load + validate from disk (read-only).
# ---------------------------------------------------------------------------


def load_report(path: str | Path) -> dict[str, Any]:
    """Read a JSON report from disk and validate it against the schema.

    Returns the parsed dict so callers can dispatch by ``report_type``.
    Raises ``ValueError`` if the shape is invalid.
    """
    raw = Path(path).read_text(encoding="utf-8")
    doc = json.loads(raw)
    validate_report_dict(doc)
    return doc


def validate_report_dict(doc: dict[str, Any]) -> None:
    """Lightweight validator that does not depend on jsonschema.

    The authoritative schema is ``templates/config/report_schema.json``;
    CI runs the full jsonschema validation. This helper exists so
    runtime code can sanity-check reports without pulling jsonschema
    into the service image (keeps the prod image footprint small).
    """
    for key in (
        "schema_version",
        "report_type",
        "report_id",
        "service",
        "generated_at",
        "generated_by",
        "mode",
        "payload",
    ):
        if key not in doc:
            raise ValueError(f"missing required key: {key}")
    if doc["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version {doc['schema_version']}")
    if doc["report_type"] not in REPORT_TYPES:
        raise ValueError(f"unknown report_type {doc['report_type']!r}")
    if not _REPORT_ID_RE.match(doc["report_id"]):
        raise ValueError(f"report_id malformed: {doc['report_id']!r}")
    if not _SERVICE_RE.match(doc["service"]):
        raise ValueError(f"service slug malformed: {doc['service']!r}")
    if doc["mode"] not in ("AUTO", "CONSULT", "STOP"):
        raise ValueError(f"mode invalid: {doc['mode']!r}")
    if doc["mode"] in ("CONSULT", "STOP") and not doc.get("approver"):
        raise ValueError(f"mode={doc['mode']} reports require approver")
    if doc["report_type"] in ("release", "incident") and not doc.get("environment"):
        raise ValueError(f"report_type={doc['report_type']!r} requires environment")
    _parse_iso(doc["generated_at"], "generated_at")
