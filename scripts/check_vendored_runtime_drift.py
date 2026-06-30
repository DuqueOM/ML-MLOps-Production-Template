#!/usr/bin/env python3
"""Contract: runtime tools and runbooks that a SCAFFOLDED service needs at
runtime are vendored into ``templates/service/`` and MUST stay byte-identical
to their canonical repo-root originals.

Why this exists
---------------
Copier renders only the ``templates/service/`` subtree (``_subdirectory`` in
``copier.yml``). The meta layer at the repo root — ``scripts/``,
``docs/runbooks/``, etc. — is NOT part of a generated project. But a freshly
scaffolded service still needs a handful of those repo-root tools to function
on its very first CI run and deploy:

- ``scripts/validate_quality_gates.py`` — invoked by the generated
  ``Makefile`` (``make ci``/lint) and ``.github/workflows/ci.yml``.
- ``scripts/audit_record.py`` — invoked by the generated
  ``.github/workflows/deploy-common.yml`` (and retrain / nightly-plan)
  on every deploy, success AND failure (ADR-014 §3.5 audit trail).
- ``docs/runbooks/drift-detection.md`` and ``docs/runbooks/model-retrain.md``
  — linked from the generated ``Makefile`` and operator docs.

The old ``new-service.sh`` solved this by ``cp``-ing these files from the
repo root into each scaffold at generation time. Under Copier there is no
such copy step — the template is the single source of truth — so the files
must physically live inside ``templates/service/``.

That creates a divergence hazard: an edit to the canonical
``scripts/audit_record.py`` would silently leave the vendored copy stale, and
every service generated thereafter would ship outdated audit logic. This gate
closes that hazard exactly like ``check_common_utils_drift.py`` and
``check_cicd_template_drift.py`` close theirs.

What this enforces
------------------
For every (canonical -> vendored) pair below, the two files must be
byte-identical. The vendored copies carry no Copier tokens (verified: zero
``{@`` / ``{%`` / ``{#`` sequences), so Copier renders them as an identity
transform and the runtime behaviour in a generated service matches the
canonical tool exactly.

Usage
-----
    python3 scripts/check_vendored_runtime_drift.py          # check (CI)
    python3 scripts/check_vendored_runtime_drift.py --fix    # resync copies

Exit codes
----------
    0 — all vendored copies are in sync (or --fix succeeded)
    1 — drift detected (a vendored copy differs from its canonical original)
    2 — internal error (a canonical source is missing)
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

# Repo root = parent of ``scripts/``.
REPO_ROOT = Path(__file__).resolve().parent.parent

# Canonical (repo-root) -> vendored (render-root) mapping. Paths are relative
# to REPO_ROOT. Keep this list in sync with what a generated service invokes;
# add a pair here whenever a new repo-root tool becomes a runtime dependency
# of the scaffolded service.
VENDORED_PAIRS: list[tuple[str, str]] = [
    (
        "scripts/audit_record.py",
        "templates/service/scripts/audit_record.py",
    ),
    (
        "scripts/validate_quality_gates.py",
        "templates/service/scripts/validate_quality_gates.py",
    ),
    (
        "docs/runbooks/drift-detection.md",
        "templates/service/docs/runbooks/drift-detection.md",
    ),
    (
        "docs/runbooks/model-retrain.md",
        "templates/service/docs/runbooks/model-retrain.md",
    ),
]


def _check(canonical: Path, vendored: Path) -> str | None:
    """Return a human-readable drift reason, or None when in sync."""
    if not canonical.exists():
        raise FileNotFoundError(f"canonical source missing: {canonical}")
    if not vendored.exists():
        return f"vendored copy missing: {vendored}"
    if not filecmp.cmp(canonical, vendored, shallow=False):
        return f"vendored copy differs from canonical: {vendored}"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Resync vendored copies from their canonical originals.",
    )
    args = parser.parse_args()

    failures: list[str] = []
    fixed: list[str] = []

    for canonical_rel, vendored_rel in VENDORED_PAIRS:
        canonical = REPO_ROOT / canonical_rel
        vendored = REPO_ROOT / vendored_rel
        try:
            reason = _check(canonical, vendored)
        except FileNotFoundError as exc:
            sys.stderr.write(f"ERROR: {exc}\n")
            return 2

        if reason is None:
            continue

        if args.fix:
            vendored.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(canonical, vendored)
            fixed.append(vendored_rel)
        else:
            failures.append(reason)

    if args.fix:
        if fixed:
            sys.stdout.write("[vendored-drift] resynced:\n")
            for path in fixed:
                sys.stdout.write(f"  - {path}\n")
        else:
            sys.stdout.write("[vendored-drift] OK — nothing to resync.\n")
        return 0

    if failures:
        sys.stderr.write(
            "FAIL: vendored runtime files drifted from their canonical "
            "originals.\n"
            "These files are vendored into templates/service/ because Copier "
            "renders only that subtree, yet a generated service needs them at "
            "runtime (see module docstring).\n\n"
        )
        for reason in failures:
            sys.stderr.write(f"  - {reason}\n")
        sys.stderr.write(
            "\nFix: python3 scripts/check_vendored_runtime_drift.py --fix\n"
        )
        return 1

    sys.stdout.write(
        "[vendored-drift] OK — all vendored runtime files match canonical "
        "originals.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
