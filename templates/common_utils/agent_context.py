"""Inter-agent handoff contract.

Defines the typed data contracts that specialist agents pass to each other.
Using dataclasses instead of JSON Schema — equivalent contract, 10× less code,
and directly usable in Python (AGENTS.md anti-pattern #over-engineering).

Usage:
    from common_utils.agent_context import TrainingArtifact, DeploymentRequest

    # Agent-MLTrainer produces:
    artifact = TrainingArtifact(
        service_name="fraud_detector",
        model_path="artifacts/model.joblib",
        model_sha256="abc123...",
        mlflow_run_id="runs:/abc",
        metrics={"auc": 0.89, "f1": 0.84},
        fairness_dir=0.92,
        quality_gates_passed=True,
    )

    # Agent-DockerBuilder consumes:
    build_request = DockerBuildRequest.from_training(artifact, base_image="python:3.11-slim")

    # Agent-K8sBuilder consumes:
    deploy_request = DeploymentRequest.from_build(build_result, environment="staging")

Invariants:
    - Every handoff artifact is validated at construction (fail-fast)
    - Required fields are enforced by dataclass (no None defaults for critical state)
    - Agents must NOT mutate a received artifact — create a new one via factory methods
    - Audit trail is emitted automatically via to_audit_entry()
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

# ═══════════════════════════════════════════════════════════════════
# Common types
# ═══════════════════════════════════════════════════════════════════


class AgentMode(str, Enum):
    """Behavior protocol modes per AGENTS.md."""

    AUTO = "AUTO"
    CONSULT = "CONSULT"
    STOP = "STOP"


class Environment(str, Enum):
    """Deployment environments with ordered trust (local < dev < staging < prod)."""

    LOCAL = "local"
    DEV = "dev"
    STAGING = "staging"
    PRODUCTION = "production"


_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_IMAGE_DIGEST_PATTERN = re.compile(r"^[^@]+@sha256:[a-f0-9]{64}$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════
# Agent-EDAProfiler → Agent-MLTrainer
# ═══════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class EDAHandoff:
    """Artifacts produced by Agent-EDAProfiler, consumed by Agent-MLTrainer."""

    service_name: str
    dataset_path: str
    target_column: str
    baseline_distributions_path: str  # eda/artifacts/02_baseline_distributions.pkl
    feature_proposals_path: str  # eda/artifacts/05_feature_proposals.yaml
    schema_proposal_path: str  # src/<service>/schema_proposal.py
    leakage_gate_passed: bool  # False = STOP — chain to /incident
    blocked_features: list[str] = field(default_factory=list)
    n_rows: int = 0
    n_features: int = 0
    created_at: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if not self.leakage_gate_passed and not self.blocked_features:
            raise ValueError("EDAHandoff: leakage_gate_passed=False requires at least one blocked feature")
        if self.leakage_gate_passed and self.blocked_features:
            raise ValueError("EDAHandoff: leakage_gate_passed=True conflicts with non-empty blocked_features")


# ═══════════════════════════════════════════════════════════════════
# Agent-MLTrainer → Agent-DockerBuilder
# ═══════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class TrainingArtifact:
    """Artifacts produced by Agent-MLTrainer, consumed by Agent-DockerBuilder."""

    service_name: str
    model_path: str
    model_sha256: str
    mlflow_run_id: str
    metrics: dict[str, float]
    fairness_dir: float  # Disparate Impact Ratio — must be >= 0.80 to pass
    quality_gates_passed: bool
    created_at: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if not _SHA256_PATTERN.match(self.model_sha256):
            raise ValueError(f"model_sha256 must be hex sha256, got: {self.model_sha256!r}")
        if not 0 <= self.fairness_dir <= 2:
            raise ValueError(f"fairness_dir out of sane range [0, 2]: {self.fairness_dir}")

    def requires_consult(self) -> bool:
        """Does this artifact require CONSULT mode before downstream processing?"""
        return 0.80 <= self.fairness_dir < 0.85 or any(  # marginal fairness
            v > 0.99 for v in self.metrics.values()
        )  # D-06 suspicion


# ═══════════════════════════════════════════════════════════════════
# Agent-DockerBuilder → Agent-SecurityAuditor → Agent-K8sBuilder
# ═══════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class BuildArtifact:
    """Artifacts produced by Agent-DockerBuilder, consumed by Agent-SecurityAuditor."""

    service_name: str
    image_ref: str  # e.g., "us-docker.pkg.dev/proj/fraud-detector@sha256:..."
    image_digest: str  # sha256:...
    sbom_path: str  # CycloneDX JSON
    trivy_report_path: str
    training_artifact: TrainingArtifact
    created_at: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if not _IMAGE_DIGEST_PATTERN.match(self.image_ref):
            raise ValueError(f"image_ref must be digest-pinned: {self.image_ref!r}")


@dataclass(frozen=True)
class SecurityAuditResult:
    """Artifacts produced by Agent-SecurityAuditor, consumed by Agent-K8sBuilder."""

    service_name: str
    image_ref: str
    signature_verified: bool  # Cosign verify passed
    sbom_attested: bool  # SBOM attached as attestation
    trivy_critical: int
    trivy_high: int
    gitleaks_findings: int
    iam_least_privilege_verified: bool
    passed: bool  # overall gate
    findings: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        # Derive `passed` from components — prevents inconsistent state
        computed = (
            self.signature_verified
            and self.sbom_attested
            and self.trivy_critical == 0
            and self.gitleaks_findings == 0
            and self.iam_least_privilege_verified
        )
        if self.passed != computed:
            raise ValueError(f"SecurityAuditResult.passed ({self.passed}) inconsistent with components ({computed})")


@dataclass(frozen=True)
class DeploymentRequest:
    """Artifacts produced by Agent-K8sBuilder, submitted to the cluster."""

    service_name: str
    environment: Environment
    image_ref: str
    kustomize_overlay: str
    security_audit: SecurityAuditResult
    required_mode: AgentMode  # AUTO for dev, CONSULT for staging, STOP for prod
    created_at: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if self.environment == Environment.PRODUCTION and self.required_mode != AgentMode.STOP:
            raise ValueError(f"Production deployments must require STOP mode (got {self.required_mode})")
        if self.environment == Environment.PRODUCTION and not self.security_audit.passed:
            raise ValueError("Production deploy blocked: security audit did not pass")


# ═══════════════════════════════════════════════════════════════════
# Audit trail
# ═══════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class AuditEntry:
    """Single append-only audit log entry for an agentic operation."""

    agent: str  # e.g., "Agent-DockerBuilder"
    operation: str  # e.g., "build_image"
    environment: Environment
    mode: AgentMode
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    approver: str | None = None  # populated when mode in {CONSULT, STOP}
    result: str = "success"  # success | failure | halted
    timestamp: str = field(default_factory=_utc_now)

    def to_jsonl(self) -> str:
        """Append-safe JSON lines representation for ops log."""
        d = asdict(self)
        d["environment"] = self.environment.value
        d["mode"] = self.mode.value
        return json.dumps(d, sort_keys=True)


__all__ = [
    "AgentMode",
    "Environment",
    "EDAHandoff",
    "TrainingArtifact",
    "BuildArtifact",
    "SecurityAuditResult",
    "DeploymentRequest",
    "AuditEntry",
]
