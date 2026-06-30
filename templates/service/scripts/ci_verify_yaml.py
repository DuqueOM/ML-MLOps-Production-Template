#!/usr/bin/env python3
"""Parse every YAML file that belongs to the template contract.

This is a lightweight verifier used by ADR-019 self-healing policy.
It deliberately avoids formatters and network calls: its job is to
prove a proposed fix did not leave YAML syntactically broken.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
PRUNE = {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", "__pycache__", "node_modules", "site"}
SUFFIXES = {".yaml", ".yml"}


def _is_pruned(path: Path) -> bool:
    return bool(set(path.parts) & PRUNE) or any((parent / "pyvenv.cfg").exists() for parent in path.parents)


def main() -> int:
    failures: list[str] = []
    for path in sorted(p for p in REPO_ROOT.rglob("*") if p.suffix in SUFFIXES and not _is_pruned(p)):
        try:
            with path.open("r", encoding="utf-8") as fh:
                # load_all supports Kubernetes multi-document YAML.
                # BaseLoader treats mkdocs !!python/name tags as plain
                # tagged scalars instead of importing plugin modules.
                list(yaml.load_all(fh, Loader=yaml.BaseLoader))
        except Exception as exc:  # noqa: BLE001 - verifier reports all parser failures uniformly.
            failures.append(f"{path.relative_to(REPO_ROOT)}: {exc}")

    if failures:
        print("YAML verification failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print("YAML verification passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
