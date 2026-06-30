#!/usr/bin/env python3
"""Targeted verifier bundle for ADR-019 autofix candidates.

This script intentionally runs checks with low dependency weight so it
can execute in a clean CI context before the heavier test matrix. The
goal is not exhaustive proof; it is to make the policy's
``targeted-tests`` verifier real and repeatable.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

COMMANDS = (
    [sys.executable, "scripts/validate_agentic.py", "--strict"],
    [sys.executable, "scripts/sync_agentic_adapters.py", "--check"],
    [sys.executable, "scripts/validate_agentic_manifest.py", "--strict"],
    [sys.executable, "scripts/mcp_doctor.py", "--mode", "check"],
    [sys.executable, "scripts/validate_quality_gates.py", "--require-at-least-one"],
    [sys.executable, "scripts/verify_enterprise_adoption.py"],
)


def main() -> int:
    for cmd in COMMANDS:
        print("+", " ".join(cmd))
        proc = subprocess.run(cmd, cwd=REPO_ROOT)
        if proc.returncode != 0:
            return proc.returncode
    print("Targeted verification passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
