#!/usr/bin/env python3
"""Fast enterprise-adoption contract checks.

This verifier targets the practical gaps that block first scaffold, first CI,
and first non-agentic review. It intentionally avoids heavy ML dependencies.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RELEASE = "0.14.0"


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _runbook_refs() -> set[str]:
    scanned = [
        "README.md",
        "QUICK_START.md",
        "docs/ADOPTION.md",
        "templates/Makefile",
        "docs/runbooks/alertmanager-validation.md",
    ]
    refs: set[str] = set()
    pattern = re.compile(r"docs/runbooks/[A-Za-z0-9._/-]+\.md")
    for rel in scanned:
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        refs.update(pattern.findall(path.read_text(encoding="utf-8")))
    return refs


def main() -> int:
    failures: list[str] = []

    for ref in sorted(_runbook_refs()):
        if not (REPO_ROOT / ref).exists():
            failures.append(f"missing runbook reference: {ref}")

    changelog = _read("CHANGELOG.md")
    release_path = REPO_ROOT / f"releases/v{RELEASE}.md"
    if f"## [{RELEASE}] - 2026-05-03" not in changelog:
        failures.append(f"CHANGELOG.md missing {RELEASE} release entry")
    if not release_path.exists():
        failures.append(f"missing releases/v{RELEASE}.md")

    ci = _read("templates/cicd/ci.yml")
    forbidden_ci = [
        "${{ matrix.service }}/requirements.txt",
        "cd ${{ matrix.service }}",
        "${{ matrix.service }}/coverage.xml",
        "${{ matrix.service }}/results/",
        "docker build -t \"$IMAGE\" ${{ matrix.service }}/",
    ]
    for token in forbidden_ci:
        if token in ci:
            failures.append(f"ci.yml still assumes nested service layout: {token}")
    if "docker build -t \"$IMAGE\" ." not in ci:
        failures.append("ci.yml does not build Docker image from scaffolded repo root")

    deploy = _read("templates/cicd/deploy-gcp.yml") + _read("templates/cicd/deploy-aws.yml")
    if "for SERVICE in {ServiceName}" in deploy:
        failures.append("deploy workflows still loop over PascalCase {ServiceName}")
    if "-predictor:${{ steps.version.outputs.v }}" not in deploy:
        failures.append("deploy workflows do not publish {service-name}-predictor images")

    app = _read("templates/service/app/fastapi_app.py")
    training_test = _read("templates/service/tests/test_training.py")
    if "_prepare_model_features" not in app or "transform_inference" not in app:
        failures.append("fastapi_app.py does not enforce inference feature transformation")
    parity_match = re.search(
        r"def test_inference_uses_same_features\(.*?(?=\n    def |\n\n# ---------------------------------------------------------------------------)",
        training_test,
        flags=re.S,
    )
    if parity_match and "pytest.skip(" in parity_match.group(0):
        failures.append("train/inference parity test is still skipped")
    elif not parity_match:
        failures.append("train/inference parity test is missing")

    if "D-01..D-31" in _read("README.md") or "D-01..D-31" in _read("docs/ADOPTION.md"):
        failures.append("D-31 anti-pattern range drift remains in README or ADOPTION")

    if failures:
        print("Enterprise adoption verification failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print("Enterprise adoption verification passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
