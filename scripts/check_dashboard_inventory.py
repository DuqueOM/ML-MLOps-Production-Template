#!/usr/bin/env python3
"""Verify that every Grafana dashboard JSON in
``templates/monitoring/grafana/`` is referenced by ``INDEX.md``.

External-feedback gap 6.4 (May 2026 triage): dashboards exist but
are not centrally registered. The INDEX is the source of truth.
This gate makes "shipped" and "registered" identical.

Exit codes
----------
- 0: every dashboard JSON appears in INDEX.md.
- 1: at least one dashboard is unregistered OR INDEX.md mentions a
  file that does not exist.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DASHBOARDS_DIR = REPO_ROOT / "templates" / "monitoring" / "grafana"
INDEX = DASHBOARDS_DIR / "INDEX.md"


def main() -> int:
    if not INDEX.is_file():
        print(f"[dashboards] INDEX missing: {INDEX}")
        return 1

    on_disk = {p.name for p in DASHBOARDS_DIR.glob("dashboard-*.json")}
    text = INDEX.read_text(encoding="utf-8")
    referenced = {name for name in on_disk if name in text}
    unregistered = on_disk - referenced

    # Also fail if INDEX references a file that doesn't exist.
    import re
    referenced_in_doc = set(re.findall(r"dashboard-[A-Za-z0-9_-]+\.json", text))
    missing_on_disk = referenced_in_doc - on_disk

    if not unregistered and not missing_on_disk:
        print(f"[dashboards] OK — {len(on_disk)} dashboard(s) registered.")
        return 0

    if unregistered:
        print(f"[dashboards] {len(unregistered)} unregistered dashboard(s):")
        for n in sorted(unregistered):
            print(f"  - {n} — add a row to {INDEX.relative_to(REPO_ROOT)}")
    if missing_on_disk:
        print(f"[dashboards] {len(missing_on_disk)} INDEX entry without JSON:")
        for n in sorted(missing_on_disk):
            print(f"  - {n} — referenced in INDEX.md but file does not exist")
    return 1


if __name__ == "__main__":
    sys.exit(main())
