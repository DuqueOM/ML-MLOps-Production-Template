#!/usr/bin/env python3
"""ci_collect_context.py — read-only CI failure context collector (ADR-019 Phase 1).

Status: Phase 1 — read-only, NO writes, NO PR creation, NO commits.

This script ingests a CI failure (GitHub Actions log fragment via stdin or
``--log-file``) plus the PR/commit context (changed file list via
``--changed-files`` or ``git diff --name-only``) and emits a normalized JSON
structure on stdout. The structure is the canonical input to
``ci_classify_failure.py``.

Phase 1 acceptance criteria from ADR-019:
- script never writes anything outside stdout / stderr
- script never imports network libraries
- script never invokes git commands that mutate state
- output is a stable JSON schema covered by a contract test

Usage::

    # From a GitHub Actions step:
    cat $GITHUB_STEP_SUMMARY | python scripts/ci_collect_context.py \\
        --job-name "${{ github.job }}" \\
        --workflow "${{ github.workflow }}" \\
        --pr-number "${{ github.event.pull_request.number }}" \\
        --changed-files-from-stdin < changed_files.txt

    # Local debugging:
    python scripts/ci_collect_context.py --log-file failure.log \\
        --changed-files-from-shell

Output schema (stable per ADR-019 §contract test)::

    {
      "schema_version": "1",
      "phase": "shadow",
      "job_name": "<str>",
      "workflow": "<str>",
      "pr_number": <int|null>,
      "changed_files": ["<path>", ...],
      "error_signatures": ["<str>", ...],
      "log_excerpt": "<truncated str>",
      "log_excerpt_truncated": <bool>,
      "blast_radius_lines": <int|null>
    }

Authority: ADR-019 §Phase 1, ADR-020 §S1-6.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import subprocess  # nosec B404 — used only in --changed-files-from-shell with no user input
import sys
from typing import Iterable

SCHEMA_VERSION = "1"
LOG_EXCERPT_MAX_CHARS = 8_000

# Common error signatures we want the classifier to be able to react to.
# Order matters: more specific patterns first.
ERROR_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("python.import_error", re.compile(r"ModuleNotFoundError: No module named")),
    ("python.syntax_error", re.compile(r"SyntaxError:")),
    ("black.format_drift", re.compile(r"would reformat|black .* would reformat")),
    ("isort.import_drift", re.compile(r"ERROR.*isort|imports are incorrectly sorted")),
    ("flake8.lint", re.compile(r"^\S+\.py:\d+:\d+: [EWF]\d{3,4} ", re.MULTILINE)),
    ("mypy.type_error", re.compile(r"error: .*\[(?:assignment|arg-type|return-value|no-redef)\]")),
    ("pytest.assertion", re.compile(r"^E\s+(?:assert|AssertionError)", re.MULTILINE)),
    ("pytest.collection_error", re.compile(r"ERROR collecting|ERROR while loading")),
    ("yaml.parse_error", re.compile(r"yaml.scanner.ScannerError|yaml.parser.ParserError")),
    ("workflow.lint", re.compile(r"actionlint|workflow.*invalid")),
    ("docs.markdownlint", re.compile(r"markdownlint|MD\d{3}")),
    ("docs.link_check", re.compile(r"markdown-link-check|broken link")),
    ("trivy.cve", re.compile(r"Total: \d+ \(.*CRITICAL: [1-9]")),
    ("gitleaks.secret", re.compile(r"gitleaks.*leaks found", re.IGNORECASE)),
    ("dependency.unresolved", re.compile(r"Could not find a version|No matching distribution")),
]


@dataclasses.dataclass(frozen=True)
class CollectedContext:
    """Canonical Phase 1 read-only context object."""

    schema_version: str
    phase: str
    job_name: str
    workflow: str
    pr_number: int | None
    changed_files: tuple[str, ...]
    error_signatures: tuple[str, ...]
    log_excerpt: str
    log_excerpt_truncated: bool
    blast_radius_lines: int | None

    def to_json(self) -> str:
        return json.dumps(dataclasses.asdict(self), indent=2, sort_keys=True)


def _read_log(args: argparse.Namespace) -> str:
    if args.log_file:
        with open(args.log_file, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


def _read_changed_files(args: argparse.Namespace) -> tuple[str, ...]:
    if args.changed_files_from_stdin:
        # Caller piped a newline-separated file list to a different fd; we read
        # from --changed-files-file in that case to keep stdin available for log.
        if not args.changed_files_file:
            print(
                "ERROR: --changed-files-from-stdin requires --changed-files-file "
                "(stdin is reserved for the log).",
                file=sys.stderr,
            )
            sys.exit(2)
        with open(args.changed_files_file, "r", encoding="utf-8") as fh:
            return tuple(line.strip() for line in fh if line.strip())

    if args.changed_files:
        return tuple(args.changed_files)

    if args.changed_files_from_shell:
        # READ-ONLY git command — never mutates state.
        try:
            out = subprocess.check_output(  # nosec B603 — trusted args, read-only
                ["git", "diff", "--name-only", "HEAD~1...HEAD"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
            return tuple(line.strip() for line in out.splitlines() if line.strip())
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            return tuple()

    return tuple()


def _detect_signatures(log: str) -> tuple[str, ...]:
    signatures: list[str] = []
    for label, pattern in ERROR_PATTERNS:
        if pattern.search(log):
            signatures.append(label)
    return tuple(signatures)


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    head = text[: limit // 2]
    tail = text[-limit // 2 :]
    return f"{head}\n...[truncated {len(text) - limit} chars]...\n{tail}", True


def collect(args: argparse.Namespace) -> CollectedContext:
    log = _read_log(args)
    excerpt, truncated = _truncate(log, LOG_EXCERPT_MAX_CHARS)
    return CollectedContext(
        schema_version=SCHEMA_VERSION,
        phase="shadow",
        job_name=args.job_name or "unknown",
        workflow=args.workflow or "unknown",
        pr_number=args.pr_number if args.pr_number and args.pr_number > 0 else None,
        changed_files=_read_changed_files(args),
        error_signatures=_detect_signatures(log),
        log_excerpt=excerpt,
        log_excerpt_truncated=truncated,
        blast_radius_lines=args.blast_radius_lines,
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Read-only CI failure context collector (ADR-019 Phase 1).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--job-name", default="", help="GitHub Actions job name.")
    p.add_argument("--workflow", default="", help="GitHub Actions workflow name.")
    p.add_argument("--pr-number", type=int, default=0, help="PR number (0 if not a PR).")
    p.add_argument(
        "--log-file",
        default=None,
        help="Path to a file containing the failure log (alternative to stdin).",
    )

    cf_group = p.add_mutually_exclusive_group()
    cf_group.add_argument(
        "--changed-files",
        nargs="*",
        default=None,
        help="Explicit list of changed file paths.",
    )
    cf_group.add_argument(
        "--changed-files-from-stdin",
        action="store_true",
        help="Read changed file list from --changed-files-file (stdin reserved for log).",
    )
    cf_group.add_argument(
        "--changed-files-from-shell",
        action="store_true",
        help="Resolve changed files via 'git diff --name-only HEAD~1...HEAD' (read-only).",
    )
    p.add_argument(
        "--changed-files-file",
        default=None,
        help="Required when --changed-files-from-stdin is set.",
    )

    p.add_argument(
        "--blast-radius-lines",
        type=int,
        default=None,
        help="Optional pre-computed line count of the proposed patch (None when unknown).",
    )
    return p


def main(argv: Iterable[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    ctx = collect(args)
    print(ctx.to_json())
    return 0


if __name__ == "__main__":
    sys.exit(main())
