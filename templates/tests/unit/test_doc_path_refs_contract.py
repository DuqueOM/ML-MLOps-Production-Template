"""Contract test for the Documentation Path Reference Gate.

Pins the behaviour of ``scripts/check_doc_path_refs.py`` (see
``docs/governance/doc-path-references.md``). The gate exists because the
Copier migration (ADR-030) relocated the template tree and left 30
documents naming directories that no longer existed, undetected for two
months. A gate that silently stops detecting that is worse than no gate,
so every branch of its decision logic is pinned here.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "check_doc_path_refs.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_doc_path_refs", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load_module()


# --------------------------------------------------------------------------
# Token classification — what counts as a checkable claim
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "token",
    [
        "templates/service/k8s/base/deployment.yaml",
        "scripts/check_doc_path_refs.py",
        "docs/governance/doc-path-references.md",
        ".github/workflows/validate-templates.yml",
    ],
)
def test_literal_repo_paths_are_checked(token: str) -> None:
    assert mod._is_literal_path(token)


@pytest.mark.parametrize(
    "token",
    [
        "agentic/skills/<id>/SKILL.md",  # placeholder
        "docs/incidents/{date}-{service}.md",  # brace placeholder
        "templates/service/**",  # glob
        "scripts/validate_agentic_manifest.py --strict",  # command with args
        ".github/workflows/ci-examples.yml:31",  # file:line reference
        "templates/k8s/base/kustomization.yaml#resources",  # anchor
        "agentic/.../SKILL.md",  # ellipsis
        "src/main.py",  # adopter tree, not ours
        "make batch-inference",  # not a path at all
    ],
)
def test_non_literal_tokens_are_ignored(token: str) -> None:
    """Illustrative tokens are not claims about the tree."""
    assert not mod._is_literal_path(token)


# --------------------------------------------------------------------------
# Frozen records — an ADR must keep its point-in-time paths
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "doc",
    [
        "docs/decisions/ADR-030-copier-scaffolding-migration.md",
        "docs/audit/AUDIT_R11_ISO_ENTERPRISE.md",
        "releases/v0.16.1.md",
        "CHANGELOG.md",
        "VALIDATION_LOG.md",
        "templates/service/docs/decisions/ADR-014-gap-remediation-plan.md",
    ],
)
def test_frozen_records_are_excluded(doc: str) -> None:
    assert mod._is_frozen(doc)


@pytest.mark.parametrize("doc", ["README.md", "docs/ADOPTION.md", "docs/runbooks/incident-response.md"])
def test_living_docs_are_not_frozen(doc: str) -> None:
    assert not mod._is_frozen(doc)


# --------------------------------------------------------------------------
# Dual perspective — one text serves the repo and a generated service
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "doc",
    [
        "agentic/rules/05-github-actions.md",
        ".devin/workflows/load-test.md",
        ".claude/skills/INDEX.md",
        "templates/service/README.md",
        "AGENTS.md",  # vendored byte-identical into templates/service/
        "AGENT_CONTEXT.md",
    ],
)
def test_documents_that_ship_into_a_service_are_dual(doc: str) -> None:
    assert mod._is_dual(doc)


@pytest.mark.parametrize("doc", ["README.md", "CONTRIBUTING.md", "docs/PROGRESSION.md"])
def test_repo_only_documents_are_single_perspective(doc: str) -> None:
    assert not mod._is_dual(doc)


def test_dual_resolution_accepts_the_service_relative_form() -> None:
    """`scripts/refresh_contract.py` is correct inside a scaffolded service."""
    token = "scripts/refresh_contract.py"
    assert not (REPO_ROOT / token).exists()
    assert (REPO_ROOT / "templates" / "service" / token).exists()
    assert mod._resolves(token, dual=True)
    assert not mod._resolves(token, dual=False)


# --------------------------------------------------------------------------
# Baseline parsing and its three failure modes
# --------------------------------------------------------------------------


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_repository_currently_passes() -> None:
    result = _run()
    assert result.returncode == 0, result.stderr
    assert "every repo path reference resolves" in result.stdout


def test_baseline_entries_all_carry_a_reason_and_an_expiry() -> None:
    entries, errors = mod._parse_baseline()
    assert not errors, errors
    assert entries, "baseline parsed as empty — the parser or the file shape changed"


def test_expired_baseline_entry_fails() -> None:
    """An entry past its expiry must block, not linger."""
    result = _run("--as-of", "2099-01-01")
    assert result.returncode == 1
    assert "expired on" in result.stderr


def test_a_new_dead_path_fails(tmp_path: Path) -> None:
    """The case that would have caught commit f219895."""
    victim = REPO_ROOT / "docs" / "ADOPTION.md"
    original = victim.read_text(encoding="utf-8")
    try:
        victim.write_text(original + "\nSee `templates/cicd/ci.yml` for details.\n", encoding="utf-8")
        result = _run()
        assert result.returncode == 1
        assert "templates/cicd/ci.yml" in result.stderr
        assert "docs/ADOPTION.md" in result.stderr
    finally:
        victim.write_text(original, encoding="utf-8")


def test_a_baseline_entry_that_resolves_fails() -> None:
    """The baseline may not outlive its reason."""
    baseline = REPO_ROOT / ".doc-path-baseline.yml"
    original = baseline.read_text(encoding="utf-8")
    try:
        baseline.write_text(
            original
            + "\n  - path: scripts/check_doc_path_refs.py\n"
            + "    reason: deliberately bogus, this file exists\n"
            + "    expiry: 2099-01-01\n",
            encoding="utf-8",
        )
        result = _run()
        assert result.returncode == 1
        assert "now resolves" in result.stderr
    finally:
        baseline.write_text(original, encoding="utf-8")


def test_list_mode_never_fails() -> None:
    """`--list` is an inventory command, not a gate."""
    result = _run("--list")
    assert result.returncode == 0
