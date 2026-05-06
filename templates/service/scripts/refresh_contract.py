#!/usr/bin/env python3
"""Regenerate `tests/contract/openapi.snapshot.json` from the live app.

Run this AFTER any intentional change to `app/schemas.py` or endpoint
handlers. Then bump `app.version` in `app/main.py` and commit both
files in one PR. CI rejects snapshot changes without a version bump.

Usage:
    python scripts/refresh_contract.py

Exit codes:
    0 — snapshot updated
    1 — app unavailable (check dependencies)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    try:
        from fastapi.testclient import TestClient

        from app.main import app
    except Exception as exc:  # pragma: no cover
        print(f"error: cannot import app ({exc})", file=sys.stderr)
        return 1

    snap = Path("tests/contract/openapi.snapshot.json")
    snap.parent.mkdir(parents=True, exist_ok=True)

    payload = TestClient(app).get("/openapi.json").json()
    snap.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    print(f"Wrote {snap} — app.version={app.version}")
    print("Next steps:")
    print("  1. Bump app.version in app/main.py (semver rules in rule 14)")
    print("  2. Update CHANGELOG.md §API Contract")
    print("  3. Commit both files in ONE PR — CI enforces pair-change")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
