#!/usr/bin/env python3
"""Fail if the documented adopter scaffold command would serve the wrong template.

Why this exists
---------------
Copier resolves a git source to the **latest tag by version sort** when no
``--vcs-ref`` is given. This repository carries two tag lines at once:

* the active line, ``v0.x`` (currently ``VERSION``), and
* ``v1.0.0``–``v1.12.0``, frozen historical audit snapshots (ADR-014).

``v1.12.0`` sorts above every ``v0.x`` tag, so the bare command

    copier copy https://github.com/DuqueOM/<repo>.git MyService

silently serves the **April 2026 snapshot** rather than the current
template. Measured: 435 files and no ``.copier-answers.yml``, versus 626
files with a correct answers file when pinned to the current release.

Nothing errors. The adopter gets a complete, plausible, stale scaffold.

This guard asserts that every adopter-facing scaffold command pins an
explicit ``--vcs-ref`` and that the pinned ref matches ``VERSION``, so a
release cannot ship while the docs still point at the previous one.

Exit codes:
    0 = every documented command pins the current version
    1 = a command is unpinned, or pins a stale version
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = REPO_ROOT / "VERSION"

# Adopter-facing surfaces. ADRs are deliberately excluded: they are dated
# decision records, not living instructions, and rewriting them to match a
# later release would falsify the record.
DOC_FILES = [
    "README.md",
    "QUICK_START.md",
    "docs/TUTORIAL.md",
    "docs/PROGRESSION.md",
]

# Files carrying executable `copier update` instructions. Unlike the scaffold
# command these may legitimately use a placeholder ref (the target release
# varies), so they are checked for the PRESENCE of --vcs-ref, not its value.
UPDATE_DOC_FILES = [
    "copier.yml",
    "agentic/skills/scaffold-update/SKILL.md",
    "templates/service/agentic/rules/15-template-lifecycle.md",
]

SCAFFOLD_CMD = re.compile(r"copier\s+copy\s+(?P<args>[^\n]*?)https://github\.com/[^\s]+")
# `copier update` is the DESTRUCTIVE path: unpinned it does not merely
# scaffold something stale, it rewrites an existing service backwards.
# Measured on a v0.23.0 service: 627 files -> 435, 582 deleted, and
# .copier-answers.yml itself removed -- so the service loses the very file
# that would let it recover. Any documented `copier update` must be pinned.
UPDATE_CMD = re.compile(r"copier\s+update(?P<args>[^\n]*)")
VCS_REF = re.compile(r"--vcs-ref[= ](?P<ref>\S+)")


def main() -> int:
    if not VERSION_FILE.exists():
        print(f"error: {VERSION_FILE} not found", file=sys.stderr)
        return 1
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    expected = f"v{version}"

    problems: list[str] = []
    checked = 0

    for rel in DOC_FILES:
        path = REPO_ROOT / rel
        if not path.exists():
            problems.append(f"{rel}: adopter doc missing")
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            match = SCAFFOLD_CMD.search(line)
            if not match:
                continue
            checked += 1
            ref_match = VCS_REF.search(match.group("args"))
            if not ref_match:
                problems.append(
                    f"{rel}:{lineno}: `copier copy` has no --vcs-ref. Copier will "
                    f"resolve to the highest-sorting tag, which is a v1.x historical "
                    f"snapshot, not {expected}."
                )
            elif ref_match.group("ref") != expected:
                problems.append(
                    f"{rel}:{lineno}: --vcs-ref={ref_match.group('ref')} but VERSION is {version}. "
                    f"Adopters following this doc would scaffold the wrong release."
                )

    if not checked:
        print(
            "error: found no `copier copy` command in any adopter doc. Either the "
            "docs changed shape or this guard is scanning the wrong files — both "
            "need a human, so this is a failure rather than a pass.",
            file=sys.stderr,
        )
        return 1

    # `copier update` — presence of --vcs-ref only; the ref is a placeholder.
    for rel in UPDATE_DOC_FILES:
        path = REPO_ROOT / rel
        if not path.exists():
            problems.append(f"{rel}: file missing")
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "copier update" not in line:
                continue
            # Prose mentions ("upgrade via `copier update`") are not commands.
            if "--" not in line and not line.strip().startswith(("copier", "$", "#", "4.")):
                continue
            match = UPDATE_CMD.search(line)
            if match and "--vcs-ref" not in match.group("args") and "--vcs-ref" not in line:
                problems.append(
                    f"{rel}:{lineno}: `copier update` without --vcs-ref. Unpinned it "
                    f"DOWNGRADES the service to a frozen v1.x snapshot and deletes "
                    f".copier-answers.yml, removing the update path itself."
                )

    if problems:
        print("error: adopter scaffold command would serve the wrong template:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print(
            "\nFix: pin `--vcs-ref=" + expected + "` in every adopter-facing "
            "`copier copy` example, and re-run this check on every version bump.",
            file=sys.stderr,
        )
        return 1

    print(f"[ OK ] {checked} adopter scaffold command(s) pin --vcs-ref={expected}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
