#!/usr/bin/env python3
"""Contract: CI templates in ``templates/service/.github/workflows/`` must
not lag ``.github/workflows/`` for shared GitHub Actions versions.

Why this exists
---------------
Dependabot's ``github-actions`` ecosystem only scans
``.github/workflows/`` (relative to the configured ``directory:``).
It does NOT scan template files in ``templates/service/.github/workflows/`` because those
files are scaffolder inputs, not executable workflows of the template
repo itself. As a result, every action version bump that Dependabot
opens (e.g., ``actions/upload-artifact v4 -> v7``) lands ONLY in
``.github/workflows/`` while the corresponding reference in
``templates/service/.github/workflows/`` ages silently.

The blast radius is real: ``templates/scripts/new-service.sh`` copies
``templates/service/.github/workflows/*.yml`` verbatim into every scaffolded service. A
service generated today off a stale template starts life with
deprecated action versions and inherits the blindspot — its own
Dependabot will open the same bumps the template already merged,
multiplying maintenance cost across every adopter.

What this enforces
------------------
For every action ``X`` that appears in BOTH ``.github/workflows/``
and ``templates/service/.github/workflows/``, the set of versions used in templates must
be a subset of the set of versions used in runtime workflows. In
practice this means: if runtime is on ``v7`` and templates are on
``v4``, fail. If runtime has ``{v3.7.0}`` and templates have
``{v3, v3.7.0}``, the floating ``v3`` is rejected because runtime
chose to pin exact.

What this does NOT enforce
--------------------------
- Action versions in ``templates/service/.github/workflows/`` that are NOT also used in
  ``.github/workflows/``. Some template-only actions exist (e.g.,
  ``google-github-actions/auth``, ``aws-actions/configure-aws-credentials``)
  precisely because the template repo doesn't deploy to a real cloud
  but adopters do. Those have no parallel reference to compare against
  and are out of scope here.
- Whether a shared action SHOULD be used in both places. Architecture
  decisions about which actions belong where live in ADRs.
- SHA-pinned versus tag-pinned references. Tag drift is the immediate
  blindspot; SHA pinning is a separate hardening that lives in
  ``docs/governance/`` if/when adopted.

Exit codes
----------
- 0: clean (or no shared actions found)
- 1: drift detected (reports each diverging action)
- 2: setup error (missing directories, parse failure)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / ".github" / "workflows"
TEMPLATE_DIR = REPO_ROOT / "templates" / "service" / ".github" / "workflows"

# Match `uses: <action>@<version>` allowing optional comments / params.
# The action name is everything up to '@'; the version is the rest of the
# token until whitespace or end-of-line. We accept both quoted and unquoted
# YAML forms, since `uses:` is always a scalar in GitHub Actions syntax.
_USES_RE = re.compile(r"""(?x)
    ^\s*
    -?\s*                       # optional list dash
    uses:\s*['"]?               # the key + optional quoting
    (?P<action>[^'"@\s]+)       # the action reference (no '@', no whitespace)
    @
    (?P<version>[^\s'"#]+)      # the version: tag, branch, or SHA
""")


def _collect_versions(directory: Path) -> dict[str, set[str]]:
    """Walk ``directory`` and return ``{action_name: {version, ...}}``."""
    versions: dict[str, set[str]] = {}
    if not directory.exists():
        return versions
    for path in sorted(directory.rglob("*.y*ml")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            sys.stderr.write(f"[cicd-drift] WARN: skipping non-utf8 file {path}\n")
            continue
        for line in text.splitlines():
            match = _USES_RE.match(line)
            if match:
                versions.setdefault(match.group("action"), set()).add(
                    match.group("version")
                )
    return versions


def _format_versions(versions: set[str]) -> str:
    return "{" + ", ".join(sorted(versions)) + "}"


def main() -> int:
    if not RUNTIME_DIR.exists():
        sys.stderr.write(f"[cicd-drift] runtime dir not found: {RUNTIME_DIR}\n")
        return 2
    if not TEMPLATE_DIR.exists():
        sys.stderr.write(f"[cicd-drift] template dir not found: {TEMPLATE_DIR}\n")
        return 2

    runtime = _collect_versions(RUNTIME_DIR)
    templates = _collect_versions(TEMPLATE_DIR)
    shared = sorted(set(runtime) & set(templates))

    if not shared:
        print(
            "[cicd-drift] OK — no shared actions between "
            ".github/workflows/ and templates/service/.github/workflows/."
        )
        return 0

    drifts: list[tuple[str, set[str], set[str]]] = []
    for action in shared:
        rv = runtime[action]
        tv = templates[action]
        # Drift = templates use any version not in runtime's set.
        # (Runtime is the source of truth: Dependabot updated it.)
        if not tv.issubset(rv):
            drifts.append((action, rv, tv))

    if drifts:
        sys.stderr.write(
            "FAIL: templates/service/.github/workflows/ uses outdated GitHub Actions versions "
            "compared to .github/workflows/.\n"
            "Dependabot only scans .github/workflows/, so template references "
            "age silently and propagate to every scaffolded service.\n\n"
        )
        for action, rv, tv in drifts:
            extra = sorted(tv - rv)
            sys.stderr.write(
                f"  - {action}\n"
                f"      runtime ({len(rv)} ref{'s' if len(rv) != 1 else ''}):  "
                f"{_format_versions(rv)}\n"
                f"      templates ({len(tv)} ref{'s' if len(tv) != 1 else ''}): "
                f"{_format_versions(tv)}\n"
                f"      template-only versions to remove or upgrade: {extra}\n\n"
            )
        sys.stderr.write(
            "Fix: bump the offending references in templates/service/.github/workflows/*.yml to a "
            "version already used in .github/workflows/. If the template "
            "intentionally needs a different version (e.g., for backward "
            "compat with a specific runner), add an exception to this script "
            "with a comment linking to the ADR or governance doc.\n"
        )
        return 1

    total_shared = len(shared)
    print(
        f"[cicd-drift] OK — {total_shared} shared action"
        f"{'s' if total_shared != 1 else ''} between runtime and templates, "
        "all versions in sync."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
