#!/usr/bin/env python3
"""ci_classify_failure.py — read-only CI failure classifier (ADR-019 Phase 1).

Status: Phase 1 — read-only, NO writes, NO PR creation, NO commits.

Consumes the JSON output of ``ci_collect_context.py`` and applies the rules
in ``templates/config/ci_autofix_policy.yaml`` to emit a classification.

Phase 1 contract (acceptance criteria from ADR-019):
- never classifies a `protected_paths` change as AUTO
- never classifies any STOP failure class as AUTO or CONSULT
- never escalates a CONSULT to AUTO based on memory hints (memory is advisory
  and can ONLY escalate prudence — same escalation-only discipline as ADR-010)
- escalates to ``blast_radius_exceeded`` when proposed change exceeds the
  AUTO or CONSULT limits in ``policy.limits``
- output JSON conforms to the stable schema enforced by
  ``test_ci_classify_failure_phase1.py``

Usage::

    python scripts/ci_collect_context.py --log-file failure.log \\
        --changed-files src/foo.py | \\
    python scripts/ci_classify_failure.py

    # Or with explicit policy file:
    python scripts/ci_classify_failure.py \\
        --policy templates/config/ci_autofix_policy.yaml \\
        --context-file context.json

Output schema (stable per ADR-019 §contract test)::

    {
      "schema_version": "1",
      "phase": "shadow",
      "input_signatures": ["<sig>", ...],
      "matched_class": "<failure_class_name|null>",
      "final_mode": "AUTO|CONSULT|STOP",
      "rationale": ["<str>", ...],
      "blast_radius_match": {
        "files_changed": <int>,
        "lines_changed": <int|null>,
        "files_limit": <int>,
        "lines_limit": <int|null>,
        "exceeds_limit": <bool>
      },
      "protected_paths_hit": ["<path>", ...],
      "verifiers_required": ["<verifier>", ...],
      "writes_allowed": false
    }

Authority: ADR-019 §Phase 1, ADR-020 §S1-6.
"""

from __future__ import annotations

import argparse
import dataclasses
import fnmatch
import json
import sys
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    print("ERROR: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY_PATH = REPO_ROOT / "templates" / "config" / "ci_autofix_policy.yaml"
SCHEMA_VERSION = "1"

# Canonical signature → candidate failure-class mapping. Multiple signatures can
# point to the same class; the classifier picks the most specific match per
# §Phase 1 deterministic-fallback rule.
SIGNATURE_TO_CLASS: dict[str, list[str]] = {
    "black.format_drift": ["formatter_drift"],
    "isort.import_drift": ["formatter_drift"],
    "flake8.lint": ["formatter_drift"],
    "docs.markdownlint": ["docs_quality_minor"],
    "docs.link_check": ["docs_quality_minor"],
    "yaml.parse_error": ["syntax_config_minor"],
    "workflow.lint": ["workflow_nonprod_fix"],
    "pytest.assertion": ["test_fixture_alignment"],
    "pytest.collection_error": ["test_fixture_alignment", "build_harness_fix"],
    "python.import_error": ["build_harness_fix"],
    "python.syntax_error": ["build_harness_fix"],
    "mypy.type_error": ["test_fixture_alignment"],
    "trivy.cve": ["security_or_auth"],
    "gitleaks.secret": ["security_or_auth"],
    "dependency.unresolved": ["dependency_pin_nonruntime"],
}


@dataclasses.dataclass(frozen=True)
class BlastRadiusMatch:
    files_changed: int
    lines_changed: int | None
    files_limit: int
    lines_limit: int | None
    exceeds_limit: bool


@dataclasses.dataclass(frozen=True)
class Classification:
    schema_version: str
    phase: str
    input_signatures: tuple[str, ...]
    matched_class: str | None
    final_mode: str
    rationale: tuple[str, ...]
    blast_radius_match: BlastRadiusMatch
    protected_paths_hit: tuple[str, ...]
    verifiers_required: tuple[str, ...]
    writes_allowed: bool

    def to_json(self) -> str:
        d = dataclasses.asdict(self)
        return json.dumps(d, indent=2, sort_keys=True)


def _path_matches_any(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(path, p) or fnmatch.fnmatch(path, f"**/{p}") for p in patterns)


def _check_protected_paths(changed_files: list[str], policy: dict[str, Any]) -> list[str]:
    protected = policy.get("protected_paths") or []
    return [f for f in changed_files if _path_matches_any(f, protected)]


def _candidate_classes(signatures: list[str]) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    for sig in signatures:
        for cls in SIGNATURE_TO_CLASS.get(sig, []):
            if cls not in seen:
                seen.add(cls)
                candidates.append(cls)
    return candidates


def _select_class(
    candidates: list[str],
    changed_files: list[str],
    policy: dict[str, Any],
) -> tuple[str | None, list[str]]:
    """Pick the most-specific class whose allowed_paths cover all changed files.

    Phase 1 deterministic rule: iterate in candidate order; take the first one
    whose allowed_paths cover ALL changed files AND whose blocked_if_paths_match
    are not hit. If none matches, return None (caller decides STOP fallback).
    """
    classes = policy.get("failure_classes") or {}
    rationale: list[str] = []

    for cls_name in candidates:
        cls = classes.get(cls_name)
        if not cls:
            rationale.append(f"candidate {cls_name!r} not in policy.failure_classes")
            continue

        # STOP classes never have allowed_paths and never auto-match in Phase 1.
        # They are only selected via direct security/infra/quality_gate signatures.
        if cls.get("mode") == "STOP":
            return cls_name, [f"signature {cls_name!r} is STOP class"]

        allowed = cls.get("allowed_paths") or []
        blocked = cls.get("blocked_if_paths_match") or []

        if changed_files:
            if not all(_path_matches_any(f, allowed) for f in changed_files):
                rationale.append(
                    f"{cls_name!r}: not all changed files match allowed_paths {allowed!r}"
                )
                continue
            if any(_path_matches_any(f, blocked) for f in changed_files):
                rationale.append(f"{cls_name!r}: at least one file matches blocked_if_paths_match")
                continue

        return cls_name, [f"selected {cls_name!r}: paths covered, no block hit"]

    return None, rationale


def _blast_radius(policy: dict[str, Any], mode: str, changed_files: list[str], lines: int | None) -> BlastRadiusMatch:
    limits = (policy.get("limits") or {}).get(mode.lower()) or {}
    files_limit = int(limits.get("max_files_changed", 0)) or 999
    lines_limit_raw = limits.get("max_lines_changed")
    lines_limit = int(lines_limit_raw) if lines_limit_raw is not None else None

    files_changed = len(changed_files)
    exceeds = files_changed > files_limit
    if lines is not None and lines_limit is not None and lines > lines_limit:
        exceeds = True

    return BlastRadiusMatch(
        files_changed=files_changed,
        lines_changed=lines,
        files_limit=files_limit,
        lines_limit=lines_limit,
        exceeds_limit=exceeds,
    )


def classify(context: dict[str, Any], policy: dict[str, Any]) -> Classification:
    signatures = list(context.get("error_signatures") or [])
    changed_files = list(context.get("changed_files") or [])
    blast_lines = context.get("blast_radius_lines")

    rationale: list[str] = []

    # Step 1 — protected paths short-circuit to STOP, regardless of signature.
    protected_hits = _check_protected_paths(changed_files, policy)
    if protected_hits:
        return Classification(
            schema_version=SCHEMA_VERSION,
            phase="shadow",
            input_signatures=tuple(signatures),
            matched_class="blast_radius_exceeded",
            final_mode="STOP",
            rationale=tuple(
                [f"protected paths hit: {protected_hits!r}", "policy §protected_paths forces STOP"]
            ),
            blast_radius_match=_blast_radius(policy, "consult", changed_files, blast_lines),
            protected_paths_hit=tuple(protected_hits),
            verifiers_required=tuple(),
            writes_allowed=False,
        )

    # Step 2 — derive candidate classes from signatures.
    candidates = _candidate_classes(signatures)
    if not candidates:
        rationale.append("no signatures matched any failure class — STOP for human review")
        return Classification(
            schema_version=SCHEMA_VERSION,
            phase="shadow",
            input_signatures=tuple(signatures),
            matched_class=None,
            final_mode="STOP",
            rationale=tuple(rationale),
            blast_radius_match=_blast_radius(policy, "consult", changed_files, blast_lines),
            protected_paths_hit=tuple(),
            verifiers_required=tuple(),
            writes_allowed=False,
        )

    # Step 3 — pick the most-specific class whose paths are covered.
    matched_class, select_rationale = _select_class(candidates, changed_files, policy)
    rationale.extend(select_rationale)

    if matched_class is None:
        return Classification(
            schema_version=SCHEMA_VERSION,
            phase="shadow",
            input_signatures=tuple(signatures),
            matched_class=None,
            final_mode="STOP",
            rationale=tuple(rationale + ["no candidate class covers all changed files — STOP"]),
            blast_radius_match=_blast_radius(policy, "consult", changed_files, blast_lines),
            protected_paths_hit=tuple(),
            verifiers_required=tuple(),
            writes_allowed=False,
        )

    cls = (policy.get("failure_classes") or {}).get(matched_class) or {}
    base_mode = cls.get("mode", "STOP")
    verifiers = tuple(cls.get("verifiers") or [])

    # Step 4 — blast radius check escalates AUTO/CONSULT to STOP.
    blast = _blast_radius(policy, base_mode if base_mode != "STOP" else "consult", changed_files, blast_lines)
    final_mode = base_mode
    if blast.exceeds_limit and base_mode in ("AUTO", "CONSULT"):
        final_mode = "STOP"
        matched_class = "blast_radius_exceeded"
        rationale.append(
            f"blast radius exceeded ({blast.files_changed} files, "
            f"{blast.lines_changed} lines vs limits {blast.files_limit}/{blast.lines_limit}) — STOP"
        )

    return Classification(
        schema_version=SCHEMA_VERSION,
        phase="shadow",
        input_signatures=tuple(signatures),
        matched_class=matched_class,
        final_mode=final_mode,
        rationale=tuple(rationale),
        blast_radius_match=blast,
        protected_paths_hit=tuple(),
        verifiers_required=verifiers,
        writes_allowed=False,  # Phase 1 is shadow only.
    )


def _load_policy(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _load_context(args: argparse.Namespace) -> dict[str, Any]:
    if args.context_file:
        with open(args.context_file, "r", encoding="utf-8") as fh:
            return json.load(fh)
    if not sys.stdin.isatty():
        return json.load(sys.stdin)
    print("ERROR: provide --context-file or pipe JSON to stdin.", file=sys.stderr)
    sys.exit(2)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Read-only CI failure classifier (ADR-019 Phase 1).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--policy",
        default=str(DEFAULT_POLICY_PATH),
        help="Path to ci_autofix_policy.yaml",
    )
    p.add_argument(
        "--context-file",
        default=None,
        help="Path to ci_collect_context.py JSON output (alternative to stdin).",
    )
    return p


def main(argv: Iterable[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    policy_path = Path(args.policy)
    if not policy_path.exists():
        print(f"ERROR: policy file not found: {policy_path}", file=sys.stderr)
        return 2

    policy = _load_policy(policy_path)
    context = _load_context(args)
    classification = classify(context, policy)
    print(classification.to_json())
    return 0


if __name__ == "__main__":
    sys.exit(main())
