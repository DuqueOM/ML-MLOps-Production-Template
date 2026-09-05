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

# `copier update` instructions are NOT enumerated by hand.
#
# v0.24.0 shipped a hand-written list of three files and missed
# `agentic/workflows/scaffold-update.md` -- the one an operator actually
# executes as /scaffold-update, and which is vendored into every generated
# service. A guard whose coverage is a literal list is only ever as complete
# as the moment someone last remembered to edit it, which is exactly the
# defect class this repo keeps finding.
#
# So: SCAN the tree. Anything that looks like an executable `copier update`
# must be pinned, wherever it lives.
#
# Directories holding historical records rather than live instructions.
# Rewriting them would falsify the record.
HISTORICAL_DIRS = ("releases", "docs/audit")
HISTORICAL_FILES = ("CHANGELOG.md", "VALIDATION_LOG.md", "MIGRATION.md")

SCAN_EXTENSIONS = (".md", ".yml", ".yaml", ".sh")
# Extensionless files that still hold executable instructions. A Makefile has
# no suffix, so the extension filter below skipped it — and that is exactly
# where `make scaffold-update` lived, unpinned, while this guard passed. The
# comment above says coverage must not be a literal list; scoping by
# extension was the same mistake wearing a different hat.
SCAN_FILENAMES = ("Makefile", "makefile", "GNUmakefile", "Justfile", "justfile")

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

    # `copier update` — scanned, not enumerated. Presence of --vcs-ref only;
    # the target release varies so a placeholder ref is legitimate.
    update_cmds_seen = 0
    for path in sorted(REPO_ROOT.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in SCAN_EXTENSIONS and path.name not in SCAN_FILENAMES:
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel.startswith(".git/") or "__pycache__" in rel:
            continue
        if rel in HISTORICAL_FILES or rel.startswith(tuple(d + "/" for d in HISTORICAL_DIRS)):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(lines, start=1):
            if "copier update" not in line:
                continue
            stripped = line.strip()
            # An executable command starts the line (optionally after a shell
            # prompt or list marker). Prose like "upgrade via `copier update`"
            # is a mention, not an instruction, and is left alone.
            is_command = (
                stripped.startswith(("copier update", "$ copier update"))
                or stripped.startswith(("python -m copier update", "python3 -m copier update"))
                or bool(re.match(r"^[-*\d.]+\s+.*`?copier update\s+--", stripped))
            )
            if not is_command:
                continue
            update_cmds_seen += 1
            match = UPDATE_CMD.search(line)
            if match and "--vcs-ref" not in match.group("args"):
                problems.append(
                    f"{rel}:{lineno}: executable `copier update` without --vcs-ref. "
                    f"Copier resolves an unpinned source to the highest-sorting tag, so the "
                    f"service jumps to a release nobody chose — including across a major. "
                    f"ADR-045 moved the frozen v1.x snapshots out of the version namespace, "
                    f"which removed the catastrophic form of this (627 files -> 435, "
                    f".copier-answers.yml deleted); the safety now rests entirely on that "
                    f"namespace staying clean. Pin the ref instead of relying on it."
                )

    if not update_cmds_seen:
        problems.append(
            "no executable `copier update` command found anywhere. Either the docs "
            "changed shape or this scan is broken — both need a human."
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
