"""Drill evidence contract (PR-C3).

A *drill* is a reproducible operational simulation: a script that
constructs deterministic inputs, exercises a production code path,
captures the verdict, and writes evidence to disk. The evidence is
the audit trail — it must be human-readable AND machine-parsable so
the contract test can assert on its shape.

Layout per drill run::

    docs/runbooks/drills/<drill_name>/<run_id>/
        evidence.md          Human-readable narrative
        evidence.json        Machine-readable verdict + facts
        artifacts/           Drill-specific inputs/outputs (CSVs, reports)

``run_id`` is ``<UTC ISO8601 compact>-<short-uuid>``; the timestamp
sorts lexically and the suffix prevents collisions when two drills
run in the same second.

Why split json and md: the markdown is what an auditor reads after
an incident; the json is what the contract test parses to assert
"the drill verdict matches expectation".
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DrillEvidence:
    """Single source of truth for one drill run."""

    drill_name: str
    run_id: str
    started_at: str  # UTC ISO8601
    finished_at: str  # UTC ISO8601
    expected_verdict: str  # what the test will assert on
    actual_verdict: str  # what the drill produced
    passed: bool  # actual == expected
    facts: dict[str, Any] = field(default_factory=dict)  # key numbers
    observations: list[str] = field(default_factory=list)  # narrative bullets
    inputs: dict[str, Any] = field(default_factory=dict)  # determinism receipts
    artifacts: list[str] = field(default_factory=list)  # paths under artifacts/

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    def to_markdown(self) -> str:
        status_emoji = "PASS" if self.passed else "FAIL"
        lines: list[str] = [
            f"# Drill: {self.drill_name}",
            "",
            f"- **run_id**: `{self.run_id}`",
            f"- **started**: `{self.started_at}`",
            f"- **finished**: `{self.finished_at}`",
            f"- **expected verdict**: `{self.expected_verdict}`",
            f"- **actual verdict**: `{self.actual_verdict}`",
            f"- **status**: **{status_emoji}**",
            "",
            "## Inputs (determinism receipts)",
            "",
        ]
        for k, v in sorted(self.inputs.items()):
            lines.append(f"- `{k}`: `{v}`")
        lines += ["", "## Facts", ""]
        for k, v in sorted(self.facts.items()):
            lines.append(f"- `{k}`: `{v}`")
        lines += ["", "## Observations", ""]
        for obs in self.observations:
            lines.append(f"- {obs}")
        if self.artifacts:
            lines += ["", "## Artifacts", ""]
            for a in self.artifacts:
                lines.append(f"- `{a}`")
        lines.append("")
        return "\n".join(lines)


def make_run_id() -> str:
    """``<UTC compact>-<short uuid>`` — sortable + collision-resistant."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}-{uuid.uuid4().hex[:8]}"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_evidence(
    base_dir: Path,
    evidence: DrillEvidence,
) -> Path:
    """Write ``evidence.md`` + ``evidence.json`` under
    ``base_dir/<drill_name>/<run_id>/``.

    Returns the run directory.
    """
    run_dir = base_dir / evidence.drill_name / evidence.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "evidence.md").write_text(evidence.to_markdown(), encoding="utf-8")
    (run_dir / "evidence.json").write_text(evidence.to_json(), encoding="utf-8")
    return run_dir


def default_evidence_root() -> Path:
    """Default base directory: ``docs/runbooks/drills/`` next to the
    nearest ``docs/`` parent, falling back to ``$PWD/docs/runbooks/drills``.

    Honours the ``DRILL_EVIDENCE_ROOT`` env var so CI can redirect
    evidence into a temp dir without touching the repo.
    """
    override = os.getenv("DRILL_EVIDENCE_ROOT")
    if override:
        return Path(override)
    return Path.cwd() / "docs" / "runbooks" / "drills"
