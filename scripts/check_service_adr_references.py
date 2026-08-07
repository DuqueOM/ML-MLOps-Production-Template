#!/usr/bin/env python3
"""Fail if a generated service would carry unresolvable ADR references.

The problem
-----------
Template-provided files inside the Copier render root cite decisions as
bare ``ADR-NNN``. Those identifiers belong to the **template's** numbering
sequence, and the render root references far more of them than it ships:
at the time this guard was written, **40 distinct ADRs referenced, 6
vendored**.

For an adopter that produces two distinct failures:

1. Their own ``ADR-017`` and the template's ``ADR-017`` are different
   documents wearing the same name.
2. A link or reference checker flags the other 34 as missing files —
   which is what surfaced this defect in a real consuming repository.

Why this guard and not a rename
-------------------------------
Renaming to ``template-ADR-NNN`` inside the render root is structurally
blocked: ``check_vendored_runtime_drift.py`` holds ``templates/service/
agentic``, the shipped ADR files, and the config schemas **byte-identical**
to their repo-root counterparts. Rewriting identifiers there would either
break that gate or fork the generated service from upstream, making every
future ``copier update`` a conflict.

So the contract is a resolution layer instead: every template ADR the
render root references must be resolvable from
``templates/service/docs/decisions/README.md`` — either vendored in that
directory, or covered by the documented upstream pointer.

This guard asserts the resolution doc exists, names the vendored set
accurately, and carries the upstream URL. It is deliberately dependency-free.

Exit codes:
    0 = every referenced ADR is resolvable
    1 = the resolution layer is missing, stale, or incomplete
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RENDER_ROOT = REPO_ROOT / "templates" / "service"
DECISIONS_DIR = RENDER_ROOT / "docs" / "decisions"
RESOLUTION_DOC = DECISIONS_DIR / "README.md"

ADR_TOKEN = re.compile(r"ADR-(\d{3})")

# The upstream location an adopter resolves non-vendored ADRs from. The
# resolution doc must point somewhere; a doc that explains the collision
# without saying where to look is not a resolution.
UPSTREAM_MARKER = "docs/decisions"

# Placeholder used in templates/examples, never a real ADR.
PLACEHOLDER_IDS = {"099"}


def _referenced_ids() -> set[str]:
    ids: set[str] = set()
    for path in RENDER_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or ".git" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        ids.update(ADR_TOKEN.findall(text))
    return ids - PLACEHOLDER_IDS


def _vendored_ids() -> set[str]:
    if not DECISIONS_DIR.is_dir():
        return set()
    ids: set[str] = set()
    for path in DECISIONS_DIR.glob("ADR-*.md"):
        found = ADR_TOKEN.findall(path.name)
        ids.update(found)
    return ids


def main() -> int:
    problems: list[str] = []

    if not RESOLUTION_DOC.exists():
        print(
            f"error: {RESOLUTION_DOC.relative_to(REPO_ROOT)} is missing.\n"
            "Generated services cite template ADRs by bare ADR-NNN; without a\n"
            "resolution doc those references are unresolvable for the adopter\n"
            "and collide with the adopter's own numbering.",
            file=sys.stderr,
        )
        return 1

    doc = RESOLUTION_DOC.read_text(encoding="utf-8")
    referenced = _referenced_ids()
    vendored = _vendored_ids()

    if not referenced:
        print(
            "error: no ADR references found in the render root. Either the "
            "render root moved or this guard is scanning the wrong tree — "
            "both need a human, so this is a failure rather than a pass.",
            file=sys.stderr,
        )
        return 1

    if not vendored:
        problems.append("no vendored ADR files found in templates/service/docs/decisions/")

    # Every vendored ADR must be listed in the resolution doc, so the table
    # cannot silently drift from what actually ships.
    for adr_id in sorted(vendored):
        if f"ADR-{adr_id}" not in doc:
            problems.append(
                f"ADR-{adr_id} is vendored into the generated service but is not listed "
                f"in {RESOLUTION_DOC.name} — the adopter cannot tell it apart from their own."
            )

    # The doc must say where non-vendored ADRs resolve.
    if UPSTREAM_MARKER not in doc:
        problems.append(
            f"{RESOLUTION_DOC.name} does not point at an upstream location for the "
            f"{len(referenced - vendored)} referenced-but-not-vendored ADRs."
        )

    # The doc must name the collision explicitly; that is its whole job.
    if "template-ADR-" not in doc:
        problems.append(
            f"{RESOLUTION_DOC.name} does not state the disambiguation convention "
            "(template-ADR-NNN) adopters should use in their own prose."
        )

    if problems:
        print("error: generated services would carry unresolvable ADR references:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    dangling = len(referenced - vendored)
    print(
        f"[ OK ] {len(referenced)} template ADRs referenced, {len(vendored)} vendored, "
        f"{dangling} resolvable via {RESOLUTION_DOC.name}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
