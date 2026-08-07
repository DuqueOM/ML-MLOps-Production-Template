#!/usr/bin/env python3
"""Fail if the gitleaks version drifts between its three declaration sites.

Why this exists
---------------
gitleaks changed its config dialect at 8.25: versions below it silently
ignore the plural ``[[allowlists]]`` tables that ``.gitleaks.toml`` uses,
and versions at or above it reject the deprecated singular ``[allowlist]``
form outright.

That makes a version mismatch between the local hook and CI *silent in both
directions*: two scans of the same tree apply different allowlists, and
neither side reports a problem. The local scan is the one contributors
trust, so the failure mode is a false green at exactly the moment a secret
would be entering the history.

The version therefore lives in three places that must move together:

  1. ``.pre-commit-config.yaml``                     — ``rev:`` of the gitleaks hook
  2. ``templates/service/.pre-commit-config.yaml``   — same, for scaffolded services
  3. ``.github/workflows/validate-templates.yml``    — ``GITLEAKS_VERSION``

This script is the guard. It is intentionally dependency-free (no PyYAML)
so it runs anywhere, including a bare copier post-copy environment.

Exit codes:
    0 = all three agree and are >= the minimum safe version
    1 = drift, missing declaration, or a version below the config dialect floor
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Below this, gitleaks ignores the plural [[allowlists]] tables this repo
# uses -- which is the whole failure this guard exists to prevent.
MIN_SAFE = (8, 25, 0)

ROOT_PRECOMMIT = REPO_ROOT / ".pre-commit-config.yaml"
SERVICE_PRECOMMIT = REPO_ROOT / "templates" / "service" / ".pre-commit-config.yaml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "validate-templates.yml"

GITLEAKS_REPO = "https://github.com/gitleaks/gitleaks"


def _parse_version(raw: str) -> tuple[int, ...]:
    return tuple(int(part) for part in raw.strip().lstrip("v").split("."))


def _precommit_rev(path: Path) -> str | None:
    """Return the ``rev:`` pinned for the gitleaks repo in a pre-commit config.

    Hand-rolled rather than YAML-parsed to keep this dependency-free: find
    the gitleaks ``repo:`` line, then the first ``rev:`` after it.
    """
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    for idx, line in enumerate(lines):
        if GITLEAKS_REPO in line and line.strip().startswith("- repo:"):
            for following in lines[idx + 1 : idx + 15]:
                match = re.match(r"\s*rev:\s*(\S+)", following)
                if match:
                    return match.group(1)
            return None
    return None


def _ci_version(path: Path) -> str | None:
    if not path.exists():
        return None
    match = re.search(r'GITLEAKS_VERSION:\s*["\']?([0-9][0-9.]*)["\']?', path.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def main() -> int:
    found: dict[str, str | None] = {
        str(ROOT_PRECOMMIT.relative_to(REPO_ROOT)): _precommit_rev(ROOT_PRECOMMIT),
        str(SERVICE_PRECOMMIT.relative_to(REPO_ROOT)): _precommit_rev(SERVICE_PRECOMMIT),
        str(CI_WORKFLOW.relative_to(REPO_ROOT)): _ci_version(CI_WORKFLOW),
    }

    missing = [site for site, version in found.items() if version is None]
    if missing:
        print("error: gitleaks version not declared in:", file=sys.stderr)
        for site in missing:
            print(f"  - {site}", file=sys.stderr)
        return 1

    normalized = {site: str(version).lstrip("v") for site, version in found.items() if version is not None}
    distinct = set(normalized.values())

    if len(distinct) != 1:
        print("error: gitleaks version DRIFT — the three sites disagree:", file=sys.stderr)
        for site, version in normalized.items():
            print(f"  {version:<12} {site}", file=sys.stderr)
        print(
            "\nA mismatch across the 8.25 boundary changes which allowlist\n"
            "dialect is honoured, so local and CI scan the same tree with\n"
            "different rules and neither reports it. Bump all three together.",
            file=sys.stderr,
        )
        return 1

    version_str = distinct.pop()
    try:
        parsed = _parse_version(version_str)
    except ValueError:
        print(f"error: unparseable gitleaks version {version_str!r}", file=sys.stderr)
        return 1

    if parsed < MIN_SAFE:
        floor = ".".join(str(part) for part in MIN_SAFE)
        print(
            f"error: gitleaks {version_str} is below the config-dialect floor {floor}.\n"
            "Versions below it silently ignore the [[allowlists]] tables in\n"
            ".gitleaks.toml, so the scan applies rules nobody reviewed.",
            file=sys.stderr,
        )
        return 1

    print(f"[ OK ] gitleaks pinned to {version_str} in all 3 sites (>= {'.'.join(map(str, MIN_SAFE))})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
