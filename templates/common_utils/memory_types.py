"""Operational Memory Plane — Phase 1 canonical contracts (ADR-018).

Status: Phase 1 — contracts + redaction only. NO storage, NO retrieval,
NO embeddings, NO ingest worker. Phase 1 ships ONLY the typed surface so
downstream contracts (audit log, future memory consumers) can pin against
a stable shape.

Authority: ADR-018 §"Phase plan", ADR-020 §S2-1.

Hard invariants (enforced at construction or by `test_memory_contracts.py`):

1. **Frozen** — `MemoryUnit` is `frozen=True`. No agent may mutate a unit
   in place; agents create new units via factory methods.

2. **Severity normalized** — `severity` MUST be one of the canonical levels
   (`info`, `warn`, `high`, `critical`). Construction refuses any other value.

3. **Sensitivity ≥ ACL minimum** — `sensitivity` MUST be at least as
   restrictive as the implicit ACL of the bucket prefix in `evidence_uri`.
   This prevents a "public-bucket" evidence URI from being labeled
   `internal` (which would let an audit-bucket consumer read it without
   authorization).

4. **Single-tenant** — `tenant_key` is reserved but Phase 1 only accepts
   the literal `"default"` value. Multi-tenant semantics arrive in Phase 6.

5. **Audit trail** — every `MemoryUnit` carries a creation timestamp
   (UTC, ISO 8601). Future Phase-2 ingest layer adds an authoring
   `AuditEntry`; Phase 1 keeps the surface minimal.

6. **No `/predict` path** — this module imports nothing from the FastAPI
   serving layer. The serving path imports nothing from here.
   Enforced structurally: `from common_utils.memory_types import ...` in
   any `service/` Python file is rejected by `test_memory_contracts.py`.

What this module IS NOT:

- Not a query layer. There is no `search()`, no `retrieve()`, no
  embedding API in Phase 1.
- Not a storage layer. There is no DB session, no S3 client.
- Not authoritative. A `MemoryUnit` is **derived evidence**; the
  canonical source of truth is `evidence_uri`.
"""

from __future__ import annotations

import dataclasses
import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping

# ---------------------------------------------------------------------------
# Canonical enums.
# ---------------------------------------------------------------------------


class MemoryKind(str, Enum):
    """The shape of evidence a memory unit summarizes.

    Phase 1 ships these five. Phase 2 may extend (additive only — never
    rename) once ingest workers materialize.
    """

    INCIDENT_POSTMORTEM = "incident_postmortem"
    DRIFT_EVENT = "drift_event"
    DEPLOY_REGRESSION = "deploy_regression"
    SUCCESSFUL_REMEDIATION = "successful_remediation"
    RETRAINING_DECISION = "retraining_decision"


class Severity(str, Enum):
    INFO = "info"
    WARN = "warn"
    HIGH = "high"
    CRITICAL = "critical"


class Sensitivity(str, Enum):
    """ACL tier of the unit's content.

    Ordered restrictiveness: PUBLIC < INTERNAL < CONFIDENTIAL < RESTRICTED.

    The bucket-prefix → minimum-sensitivity mapping enforces invariant #3.
    """

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


SENSITIVITY_RANK: dict[Sensitivity, int] = {
    Sensitivity.PUBLIC: 0,
    Sensitivity.INTERNAL: 1,
    Sensitivity.CONFIDENTIAL: 2,
    Sensitivity.RESTRICTED: 3,
}


# ---------------------------------------------------------------------------
# Bucket prefix → minimum sensitivity (invariant #3).
#
# Adopters override this map at scaffold time via `MEMORY_BUCKET_ACL_MAP`
# environment variable parsed in Phase 2; Phase 1 ships sensible defaults.
# ---------------------------------------------------------------------------

DEFAULT_BUCKET_MIN_SENSITIVITY: dict[str, Sensitivity] = {
    "s3://public/": Sensitivity.PUBLIC,
    "gs://public/": Sensitivity.PUBLIC,
    "s3://audit/": Sensitivity.CONFIDENTIAL,
    "gs://audit/": Sensitivity.CONFIDENTIAL,
    "s3://incidents/": Sensitivity.RESTRICTED,
    "gs://incidents/": Sensitivity.RESTRICTED,
    "s3://secrets/": Sensitivity.RESTRICTED,
    "gs://secrets/": Sensitivity.RESTRICTED,
}


def minimum_sensitivity_for_uri(
    evidence_uri: str,
    bucket_map: Mapping[str, Sensitivity] | None = None,
) -> Sensitivity:
    """Return the minimum sensitivity required for ``evidence_uri``.

    Falls back to ``Sensitivity.INTERNAL`` for unknown prefixes — never
    PUBLIC. The "unknown bucket → at least INTERNAL" default is a safety
    invariant: it is impossible to label a unit PUBLIC without a known-PUBLIC
    bucket prefix.
    """
    bucket_map = bucket_map if bucket_map is not None else DEFAULT_BUCKET_MIN_SENSITIVITY
    for prefix, min_sensitivity in bucket_map.items():
        if evidence_uri.startswith(prefix):
            return min_sensitivity
    return Sensitivity.INTERNAL


# ---------------------------------------------------------------------------
# The canonical Phase 1 record.
# ---------------------------------------------------------------------------


_TENANT_KEY_RE = re.compile(r"^[a-z0-9_-]{1,64}$")


@dataclasses.dataclass(frozen=True)
class MemoryUnit:
    """Phase 1 canonical memory record.

    A `MemoryUnit` is **derived evidence**: a typed summary of an
    operational artifact (postmortem, drift report, audit entry,
    successful remediation). The canonical source of truth lives at
    `evidence_uri`; the unit only carries enough metadata for retrieval
    and policy checks.

    Construction-time validation enforces every Phase 1 invariant. There
    is intentionally no setter / mutator / `copy_with()` API: agents
    create a new unit explicitly when they want to change a field.
    """

    id: str
    kind: MemoryKind
    summary: str
    evidence_uri: str
    severity: Severity
    sensitivity: Sensitivity
    tenant_key: str
    human_authored: bool
    timestamp: str  # ISO 8601 UTC.

    def __post_init__(self) -> None:  # noqa: D401 — validation block.
        # 1. id MUST be a UUID (string form). Stable, opaque, decoupled
        #    from any storage row id we may add later.
        try:
            uuid.UUID(self.id)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"MemoryUnit.id must be a UUID string; got {self.id!r}") from exc

        # 2. summary MUST be non-empty after strip — empty summaries are a
        #    common ingest bug; refuse them.
        if not isinstance(self.summary, str) or not self.summary.strip():
            raise ValueError("MemoryUnit.summary must be a non-empty string")
        if len(self.summary) > 2_000:
            raise ValueError("MemoryUnit.summary exceeds 2000-char Phase 1 cap")

        # 3. severity MUST be a Severity instance.
        if not isinstance(self.severity, Severity):
            raise TypeError(f"MemoryUnit.severity must be Severity enum; got {type(self.severity).__name__}")

        # 4. sensitivity MUST be a Sensitivity instance AND ≥ bucket minimum.
        if not isinstance(self.sensitivity, Sensitivity):
            raise TypeError(f"MemoryUnit.sensitivity must be Sensitivity enum; got {type(self.sensitivity).__name__}")
        bucket_min = minimum_sensitivity_for_uri(self.evidence_uri)
        if SENSITIVITY_RANK[self.sensitivity] < SENSITIVITY_RANK[bucket_min]:
            raise ValueError(
                "MemoryUnit.sensitivity is below the minimum required by the "
                f"evidence_uri bucket: got {self.sensitivity.value!r}, "
                f"required at least {bucket_min.value!r} for prefix in {self.evidence_uri!r}"
            )

        # 5. evidence_uri MUST be a non-empty URI-like string with a scheme.
        if not isinstance(self.evidence_uri, str) or "://" not in self.evidence_uri:
            raise ValueError(
                "MemoryUnit.evidence_uri must include a scheme (e.g. s3://, gs://, file://); "
                f"got {self.evidence_uri!r}"
            )

        # 6. tenant_key MUST be 'default' in Phase 1.
        if self.tenant_key != "default":
            raise ValueError(
                f"Phase 1 only accepts tenant_key='default'; got {self.tenant_key!r}. "
                "Multi-tenant semantics arrive in Phase 6 (ADR-018)."
            )
        if not _TENANT_KEY_RE.match(self.tenant_key):
            raise ValueError("MemoryUnit.tenant_key contains invalid characters")

        # 7. timestamp MUST parse as ISO 8601 UTC.
        try:
            parsed = datetime.fromisoformat(self.timestamp)
        except ValueError as exc:
            raise ValueError(f"MemoryUnit.timestamp must be ISO 8601; got {self.timestamp!r}") from exc
        if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
            raise ValueError(f"MemoryUnit.timestamp must be UTC (offset +00:00); got {self.timestamp!r}")

        # 8. kind MUST be a MemoryKind instance.
        if not isinstance(self.kind, MemoryKind):
            raise TypeError(f"MemoryUnit.kind must be MemoryKind enum; got {type(self.kind).__name__}")

        # 9. human_authored MUST be a bool. Future retrieval downgrades
        #    confidence for human_authored units without machine corroboration.
        if not isinstance(self.human_authored, bool):
            raise TypeError("MemoryUnit.human_authored must be a bool")

    # ----- Factory & serialization -----

    @classmethod
    def new(
        cls,
        *,
        kind: MemoryKind,
        summary: str,
        evidence_uri: str,
        severity: Severity,
        sensitivity: Sensitivity | None = None,
        tenant_key: str = "default",
        human_authored: bool = False,
        timestamp: str | None = None,
    ) -> "MemoryUnit":
        """Construct a unit. ``id`` and ``timestamp`` are filled in if absent.

        ``sensitivity`` defaults to the bucket minimum derived from
        ``evidence_uri``; this is the safe default and is the value most
        ingest workers should use.
        """
        if sensitivity is None:
            sensitivity = minimum_sensitivity_for_uri(evidence_uri)
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return cls(
            id=str(uuid.uuid4()),
            kind=kind,
            summary=summary,
            evidence_uri=evidence_uri,
            severity=severity,
            sensitivity=sensitivity,
            tenant_key=tenant_key,
            human_authored=human_authored,
            timestamp=timestamp,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the unit to a JSON-friendly dict.

        Enums are emitted as their string values for stable wire format.
        """
        d = dataclasses.asdict(self)
        d["kind"] = self.kind.value
        d["severity"] = self.severity.value
        d["sensitivity"] = self.sensitivity.value
        return d


__all__ = [
    "MemoryKind",
    "Severity",
    "Sensitivity",
    "MemoryUnit",
    "minimum_sensitivity_for_uri",
    "DEFAULT_BUCKET_MIN_SENSITIVITY",
    "SENSITIVITY_RANK",
]
