#!/usr/bin/env python3
"""Contract: templates/common_utils/ must stay placeholder-free.

Implements ADR-025 Option A — the interim guard for the "shared
library" distribution gap until a proper package (Option B/C) lands.

Why this shape
--------------
``templates/scripts/new-service.sh`` copies ``templates/common_utils/``
verbatim into each scaffolded service and THEN runs a global sed pass
over the whole target tree, rewriting template placeholders
(``{ServiceName}``, ``{service}``, ``{SERVICE}``, ``{service-name}``,
``{ORG}``, ``{REPO}``). By construction the scaffolded copy will
diverge from the template iff a file in ``common_utils/`` contains one
of those placeholders — because only then will sed edit it.

So the only way a scaffolded ``common_utils/`` can drift from the
canonical source is if somebody writes a template placeholder *inside*
``common_utils/``. That would silently fork adopters' copies. This
script catches that class of bug deterministically and in O(100ms),
without needing to execute the scaffolder (which pulls in ~1.6 GB of
``.terraform`` provider caches and takes minutes).

An end-to-end scaffold-and-diff was considered and rejected: see
``docs/decisions/ADR-025-common-utils-distribution.md`` §"Validation
strategy". The full scaffold is already covered by
``scripts/test_scaffold.sh`` (slow job); this is the fast invariant
gate that runs on every PR.

What this does NOT enforce
--------------------------
- Drift in adopters' already-scaffolded services. Option A's
  documented trade-off is that adopters must re-pull
  ``common_utils/`` themselves; see ADR-025.
- Correctness of ``common_utils/`` code — covered by unit tests.

Exit codes: 0 = clean, 1 = placeholder drift found, 2 = setup error.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_COMMON_UTILS = REPO_ROOT / "templates" / "common_utils"

# Placeholders rewritten by new-service.sh's sed pass.
# ``{SERVICE}`` is matched with a negative look-behind for ``$`` so
# legitimate shell/python f-string expansions like ``${SERVICE}`` and
# ``f"{SERVICE}"`` (which the scaffolder itself preserves via a perl
# rule) are not flagged.
PLACEHOLDER_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("{ServiceName}", re.compile(r"\{ServiceName\}")),
    ("{service-name}", re.compile(r"\{service-name\}")),
    ("{service}", re.compile(r"\{service\}")),
    ("{ORG}", re.compile(r"\{ORG\}")),
    ("{REPO}", re.compile(r"\{REPO\}")),
    ("{SERVICE}", re.compile(r"(?<!\$)\{SERVICE\}")),
]


def _iter_common_utils_files() -> list[Path]:
    return [
        p
        for p in TEMPLATE_COMMON_UTILS.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    ]


def _scan_file(path: Path) -> list[tuple[int, str, str]]:
    """Return (line_number, placeholder, line_text) hits for one file."""
    hits: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # Binary artifact — skip; common_utils is python-only by policy
        return hits
    for lineno, line in enumerate(text.splitlines(), start=1):
        for name, pattern in PLACEHOLDER_PATTERNS:
            if pattern.search(line):
                hits.append((lineno, name, line.rstrip()))
    return hits


def main() -> int:
    if not TEMPLATE_COMMON_UTILS.exists():
        sys.stderr.write(
            f"template common_utils/ not found at {TEMPLATE_COMMON_UTILS}\n"
        )
        return 2

    failures: list[str] = []
    scanned = 0
    for path in _iter_common_utils_files():
        scanned += 1
        for lineno, placeholder, snippet in _scan_file(path):
            rel = path.relative_to(REPO_ROOT)
            failures.append(f"{rel}:{lineno}  placeholder {placeholder} -> {snippet}")

    if failures:
        sys.stderr.write(
            "FAIL: placeholder found inside templates/common_utils/ "
            "(ADR-025 Option A drift guard).\n"
            "Any placeholder here would be rewritten by new-service.sh's "
            "global sed pass and silently fork adopters' scaffolded copies.\n\n"
        )
        for line in failures:
            sys.stderr.write(f"  - {line}\n")
        sys.stderr.write(
            "\nFix: remove the placeholder from common_utils/ (it must be "
            "service-agnostic shared code). If the reference is genuinely "
            "needed, move that file OUT of common_utils/ into the service "
            "template, or parameterise via env/config instead of textual "
            "substitution.\n"
        )
        return 1

    print(
        f"[common_utils-drift] OK — {scanned} files scanned, "
        "no scaffold-rewriteable placeholders found."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
