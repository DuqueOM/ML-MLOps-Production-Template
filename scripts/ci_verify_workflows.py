#!/usr/bin/env python3
"""Static verifier for GitHub Actions workflow files.

The policy layer calls this after workflow-focused autofixes. It does
not try to replace actionlint; if actionlint is installed, it delegates
to it. Otherwise it enforces the repo-local invariants that catch the
most expensive mistakes: YAML parse, top-level mapping, and executable
workflow triggers.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIRS = (REPO_ROOT / ".github" / "workflows", REPO_ROOT / "templates" / "cicd")


def _workflow_files() -> list[Path]:
    files: list[Path] = []
    for root in WORKFLOW_DIRS:
        if root.exists():
            files.extend(sorted(root.glob("*.yml")))
            files.extend(sorted(root.glob("*.yaml")))
    return sorted(set(files))


def _load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError("top-level YAML value must be a mapping")
    return data


def _has_trigger(data: dict) -> bool:
    # YAML 1.1 treats "on" as boolean True in PyYAML; accept both keys.
    return "on" in data or True in data


def main() -> int:
    files = _workflow_files()
    failures: list[str] = []
    for path in files:
        try:
            data = _load(path)
            if "name" not in data:
                failures.append(f"{path.relative_to(REPO_ROOT)}: missing top-level 'name'")
            if "jobs" not in data or not isinstance(data["jobs"], dict):
                failures.append(f"{path.relative_to(REPO_ROOT)}: missing top-level jobs mapping")
            if path.is_relative_to(REPO_ROOT / ".github" / "workflows") and not _has_trigger(data):
                failures.append(f"{path.relative_to(REPO_ROOT)}: missing top-level on trigger")
        except Exception as exc:  # noqa: BLE001 - verifier reports every workflow parser failure.
            failures.append(f"{path.relative_to(REPO_ROOT)}: {exc}")

    if shutil.which("actionlint"):
        proc = subprocess.run(["actionlint", *[str(p) for p in files]], cwd=REPO_ROOT)
        if proc.returncode != 0:
            failures.append("actionlint returned non-zero")

    if failures:
        print("Workflow verification failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"Workflow verification passed ({len(files)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
