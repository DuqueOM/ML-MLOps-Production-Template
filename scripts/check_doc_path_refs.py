#!/usr/bin/env python3
"""Contract: a repo-relative path named in living documentation must resolve.

Why this script exists
----------------------
The Copier migration (ADR-030, commit ``fe89e92``) relocated the whole
scaffolder payload from ``templates/{cicd,k8s,monitoring,docs,eda,infra,
common_utils}`` to ``templates/service/*``. It updated every reference
that *executes* — workflows, ``Makefile``, ``CODEOWNERS``, kustomizations,
tests, and the drift-gate script itself, 14 files in all — because those
break loudly when a path is wrong.

It updated none of the prose. Thirty documents kept pointing at
directories that no longer existed, and nothing noticed, because no check
in this repo verified that a path named in a document exists. Two audit
rounds later, commit ``f219895`` copied the dead ``templates/cicd/`` path
*into the audit tooling itself* — the glob scope of
``agentic/rules/18-audit-quality.md`` and the Q-01 unpinned-action sweep
in ``agentic/workflows/audit-quality.md`` — where it propagated across
three adapter surfaces and sat there, inert and green.

The lesson generalises past that one migration: **documentation that
names a path is making a checkable claim, and an unchecked claim rots.**
This script checks it.

The dual-perspective model
--------------------------
A path reference is valid if it resolves from EITHER of two roots:

1. the repository root — the perspective of the template repo's own docs;
2. ``templates/service/`` — the perspective of a *generated service*, for
   documents that ship into one.

The second root matters because ``agentic/**`` is mirrored byte-for-byte
into ``templates/service/agentic/`` (enforced by
``check_vendored_runtime_drift.py``), and several root documents
(``AGENTS.md``, ``AGENT_CONTEXT.md``) are vendored verbatim as well. One
text has to serve both readers, so ``scripts/audit_record.py`` is correct
prose in a rule that executes inside a scaffolded service even though the
template repo keeps that file at ``templates/service/scripts/``.

Files that ship into a service are resolved against both roots. Files
that never leave the template repo are resolved against the repo root
only, which is the stricter rule.

What is NOT checked
-------------------
- Frozen records: ``docs/decisions/``, ``docs/audit/``, ``releases/``,
  ``CHANGELOG.md``, ``VALIDATION_LOG.md``. An ADR describing the state of
  the tree in May 2026 is *supposed* to name paths that have since moved;
  rewriting them would falsify the record.
- Non-literal tokens: anything carrying a placeholder (``<id>``,
  ``{service_slug}``), a glob, a brace set, shell arguments, a ``file:line``
  suffix, a URL fragment, or an ellipsis. Those are illustrative, not
  claims about the tree.
- Paths outside the repo's own top-level directories. A reference to
  ``src/main.py`` inside a runbook describes the adopter's tree, not ours.

Baseline
--------
``.doc-path-baseline.yml`` carries the references that were already
broken when this gate landed, each with a reason and an ``expiry``, in the
same shape as ``.security-baselines/`` (see
``scripts/check_baselines_expiry.py``). An expired entry fails the gate,
which forces a real decision rather than indefinite tolerance. New dead
paths are never baselined: they fail on the PR that introduces them,
which is the failure mode that would have caught ``f219895``.

Exit codes
----------
- 0: every reference resolves, or is baselined and in-date.
- 1: at least one unresolved reference is not baselined, or a baseline
     entry has expired, or a baseline entry is now obsolete.
- 2: setup error (unreadable baseline).

Usage
-----
::

    python3 scripts/check_doc_path_refs.py
    python3 scripts/check_doc_path_refs.py --list      # print unresolved refs
    python3 scripts/check_doc_path_refs.py --as-of 2027-01-01
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = REPO_ROOT / "templates" / "service"
BASELINE_FILE = REPO_ROOT / ".doc-path-baseline.yml"

# Frozen records — a point-in-time document must keep its point-in-time paths.
FROZEN_PREFIXES = (
    "docs/decisions/",
    "docs/audit/",
    "releases/",
    "templates/service/docs/decisions/",
    "templates/service/docs/audit/",
)
FROZEN_FILES = {"CHANGELOG.md", "VALIDATION_LOG.md"}

# Surfaces that ship into a generated service, and so read correctly from
# either root. `.devin/`, `.cursor/`, `.claude/`, `.codex/` are generated
# from `agentic/` by sync_agentic_adapters.py and inherit its perspective.
DUAL_PREFIXES = (
    "agentic/",
    ".devin/",
    ".cursor/",
    ".claude/",
    ".codex/",
    "templates/service/",
)
# Root documents vendored verbatim into templates/service/ (byte-identical
# per check_vendored_runtime_drift.py), so they read from both roots too.
DUAL_FILES = {"AGENTS.md", "AGENT_CONTEXT.md"}

# Only these prefixes name paths inside THIS repo. Everything else in a
# runbook (`src/`, `data/`, `artifacts/`) describes the adopter's tree.
REPO_PREFIXES = (
    "templates/",
    "scripts/",
    "docs/",
    "agentic/",
    ".github/",
    "examples/",
    ".security-baselines/",
)

# Characters that mark a token as illustrative rather than a literal path.
_NON_LITERAL = set(" <>{}*,()|$#\\:!?\"'")

_BACKTICKED = re.compile(r"`([^`\n]+)`")


def _tracked_docs() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout
    return [p for p in out.split("\0") if p.endswith((".md", ".txt"))]


def _is_frozen(path: str) -> bool:
    return path.startswith(FROZEN_PREFIXES) or path in FROZEN_FILES


def _is_dual(path: str) -> bool:
    return path.startswith(DUAL_PREFIXES) or path in DUAL_FILES


def _is_literal_path(token: str) -> bool:
    if not token.startswith(REPO_PREFIXES):
        return False
    if "..." in token:
        return False
    return not (_NON_LITERAL & set(token))


def _resolves(token: str, dual: bool) -> bool:
    if (REPO_ROOT / token).exists():
        return True
    return bool(dual and (SERVICE_ROOT / token).exists())


def collect_unresolved() -> dict[str, set[str]]:
    """Return ``{unresolved_path: {document, ...}}`` across living docs."""
    found: dict[str, set[str]] = {}
    for doc in _tracked_docs():
        if _is_frozen(doc):
            continue
        try:
            text = (REPO_ROOT / doc).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        dual = _is_dual(doc)
        for match in _BACKTICKED.finditer(text):
            token = match.group(1).strip().rstrip(",.;").rstrip("/")
            if not _is_literal_path(token) or _resolves(token, dual):
                continue
            found.setdefault(token, set()).add(doc)
    return found


def _parse_baseline() -> tuple[dict[str, _dt.date], list[str]]:
    """Parse ``.doc-path-baseline.yml`` without a yaml dependency.

    Entry shape (one per stanza)::

        - path: docs/concept_drift_log.md
          reason: created at runtime by `make performance-review`
          expiry: 2027-03-01
    """
    if not BASELINE_FILE.exists():
        return {}, []
    entries: dict[str, _dt.date] = {}
    errors: list[str] = []
    path: str | None = None
    expiry: str | None = None
    reason: str | None = None

    def flush() -> None:
        nonlocal path, expiry, reason
        if path is None:
            return
        if not expiry:
            errors.append(f"baseline entry '{path}' has no expiry:")
        elif not reason:
            errors.append(f"baseline entry '{path}' has no reason:")
        else:
            try:
                entries[path] = _dt.date.fromisoformat(expiry)
            except ValueError:
                errors.append(f"baseline entry '{path}' has malformed expiry '{expiry}'")
        path = expiry = reason = None

    for raw in BASELINE_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- path:"):
            flush()
            path = line.split(":", 1)[1].strip()
        elif line.startswith("expiry:"):
            expiry = line.split(":", 1)[1].strip()
        elif line.startswith("reason:"):
            reason = line.split(":", 1)[1].strip()
    flush()
    return entries, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="print unresolved refs and exit 0")
    parser.add_argument("--as-of", default=None, help="evaluate expiries against YYYY-MM-DD")
    args = parser.parse_args()

    as_of = _dt.date.fromisoformat(args.as_of) if args.as_of else _dt.date.today()
    unresolved = collect_unresolved()

    if args.list:
        for token, docs in sorted(unresolved.items()):
            print(f"{token}  <- {', '.join(sorted(docs))}")
        return 0

    baseline, errors = _parse_baseline()
    if errors:
        for err in errors:
            sys.stderr.write(f"::error::{err}\n")
        return 2

    new = {t: d for t, d in unresolved.items() if t not in baseline}
    expired = sorted(t for t in unresolved if t in baseline and baseline[t] < as_of)
    obsolete = sorted(t for t in baseline if t not in unresolved)

    if new:
        sys.stderr.write(
            "FAIL: documentation names repo paths that do not exist.\n"
            "A path in prose is a checkable claim; these do not resolve from the\n"
            "repo root, nor from templates/service/ for docs that ship into a\n"
            "generated service.\n\n"
        )
        for token, docs in sorted(new.items()):
            sys.stderr.write(f"  - {token}\n")
            for doc in sorted(docs):
                sys.stderr.write(f"      referenced by {doc}\n")
        sys.stderr.write(
            "\nFix: point the reference at the real path. If the target is created\n"
            "at runtime or is deliberately aspirational, add it to\n"
            ".doc-path-baseline.yml with a reason and an expiry.\n"
        )

    for token in expired:
        sys.stderr.write(
            f"::error::baseline entry '{token}' expired on {baseline[token].isoformat()} "
            "— fix the reference or re-justify with a new expiry\n"
        )
    for token in obsolete:
        sys.stderr.write(
            f"::error::baseline entry '{token}' now resolves — remove it from "
            ".doc-path-baseline.yml so the baseline stays honest\n"
        )

    if new or expired or obsolete:
        return 1

    checked = len(_tracked_docs())
    print(
        f"[doc-path-refs] OK — {checked} tracked documents scanned, "
        f"every repo path reference resolves ({len(baseline)} baselined, all in-date)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
