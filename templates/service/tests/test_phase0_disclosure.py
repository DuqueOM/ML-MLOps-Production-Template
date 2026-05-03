"""Contract test for R4 audit finding C2 — Phase-0 disclosure for ADR-018/019.

Two invariants guard against silent regression of the Phase-0 status
of the Operational Memory Plane (ADR-018) and the Agentic CI
Self-Healing lane (ADR-019):

1. **Section heading banner** — the `## Operational Memory Plane` and
   `## Agentic CI self-healing` sections in `README.md` MUST carry a
   banner block containing the canonical phrase
   "Phase 0 only. Runtime NOT implemented." until the corresponding
   ADR transitions out of Phase 0.

2. **Hero list disclaimer** — the §"What this template is" bullet list
   that mentions self-healing AND Memory Plane MUST mark each as
   "Phase 0; not implemented yet".

3. **Maturity matrix row** — the §"Production-ready scope" table MUST
   list each capability with a "Phase 0 — runtime not implemented"
   status (NOT "Production-ready" and NOT "Optional companion" alone).

If a future contributor flips ADR-018 or ADR-019 status to Phase 1+ in
the ADR file, they MUST also update this test alongside removing the
banner. The test is a reminder, not a permanent block.

Authority: R4 audit C2, ADR-020, ACTION_PLAN_R4 §S0-2.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
README = REPO_ROOT / "README.md"
ADR_018 = REPO_ROOT / "docs" / "decisions" / "ADR-018-operational-memory-plane.md"
ADR_019 = REPO_ROOT / "docs" / "decisions" / "ADR-019-agentic-ci-self-healing.md"

CANONICAL_BANNER_PHRASE = "Phase 0 only. Runtime NOT implemented."

MEMORY_HEADING = "## Operational Memory Plane"
SELF_HEALING_HEADING = "## Agentic CI self-healing"


@pytest.fixture(scope="module")
def readme_text() -> str:
    assert README.exists(), f"README.md not found at {README}"
    return README.read_text(encoding="utf-8")


def _section_after(text: str, heading: str, max_chars: int = 1500) -> str:
    """Return the first `max_chars` after `heading` in `text` (banner zone)."""
    idx = text.find(heading)
    assert idx != -1, f"README is missing the {heading!r} heading"
    return text[idx : idx + max_chars]


def _adr_phase_status(adr_path: Path) -> str:
    """Return the Status line from an ADR file, normalized to lowercase."""
    text = adr_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip().lower()
        if stripped.startswith("- **status**") or stripped.startswith("- **status:**"):
            return stripped
    pytest.fail(f"ADR {adr_path.name} is missing a Status line")
    return ""  # unreachable


def _is_phase_0(adr_path: Path) -> bool:
    status = _adr_phase_status(adr_path)
    return "phase 0" in status


# ---------------------------------------------------------------------------
# Invariant 1 — section banner present while ADR is Phase 0.
# ---------------------------------------------------------------------------


def test_memory_plane_section_carries_phase0_banner(readme_text: str) -> None:
    if not _is_phase_0(ADR_018):
        pytest.skip("ADR-018 is no longer Phase 0 — banner no longer mandatory.")
    section = _section_after(readme_text, MEMORY_HEADING)
    assert CANONICAL_BANNER_PHRASE in section, (
        f"§'{MEMORY_HEADING}' must carry the canonical phrase "
        f"{CANONICAL_BANNER_PHRASE!r} while ADR-018 is in Phase 0. "
        "See docs/audit/ACTION_PLAN_R4.md §S0-2."
    )


def test_self_healing_section_carries_phase0_banner(readme_text: str) -> None:
    if not _is_phase_0(ADR_019):
        pytest.skip("ADR-019 is no longer Phase 0 — banner no longer mandatory.")
    section = _section_after(readme_text, SELF_HEALING_HEADING)
    assert CANONICAL_BANNER_PHRASE in section, (
        f"§'{SELF_HEALING_HEADING}' must carry the canonical phrase "
        f"{CANONICAL_BANNER_PHRASE!r} while ADR-019 is in Phase 0. "
        "See docs/audit/ACTION_PLAN_R4.md §S0-2."
    )


# ---------------------------------------------------------------------------
# Invariant 2 — hero list bullets flag both capabilities.
# ---------------------------------------------------------------------------


def test_hero_list_marks_self_healing_phase0(readme_text: str) -> None:
    if not _is_phase_0(ADR_019):
        pytest.skip("ADR-019 is no longer Phase 0 — hero-list flag no longer required.")
    # Locate the "What this template is" hero bullets and check the
    # self-healing line carries the phase flag.
    hero_idx = readme_text.find("## What this template is")
    assert hero_idx != -1
    hero_block = readme_text[hero_idx : hero_idx + 2500]
    self_healing_line = next(
        (line for line in hero_block.splitlines() if "CI self-healing" in line),
        None,
    )
    assert self_healing_line is not None, "Hero bullet for CI self-healing is missing."
    assert "Phase 0" in self_healing_line and "not implemented yet" in self_healing_line, (
        "Hero list bullet for CI self-healing must declare 'Phase 0; not implemented yet'. "
        "See docs/audit/ACTION_PLAN_R4.md §S0-2."
    )


def test_hero_list_marks_memory_plane_phase0(readme_text: str) -> None:
    if not _is_phase_0(ADR_018):
        pytest.skip("ADR-018 is no longer Phase 0.")
    hero_idx = readme_text.find("## What this template is")
    assert hero_idx != -1
    hero_block = readme_text[hero_idx : hero_idx + 2500]
    memory_line = next(
        (line for line in hero_block.splitlines() if "Operational Memory Plane" in line),
        None,
    )
    assert memory_line is not None, "Hero bullet for Operational Memory Plane is missing."
    assert "Phase 0" in memory_line and "not implemented yet" in memory_line, (
        "Hero list bullet for Operational Memory Plane must declare 'Phase 0; not implemented yet'. "
        "See docs/audit/ACTION_PLAN_R4.md §S0-2."
    )


# ---------------------------------------------------------------------------
# Invariant 3 — maturity matrix row uses the right status string.
# ---------------------------------------------------------------------------


def test_maturity_matrix_self_healing_row(readme_text: str) -> None:
    if not _is_phase_0(ADR_019):
        pytest.skip("ADR-019 is no longer Phase 0.")
    matrix_idx = readme_text.find("## Production-ready scope")
    assert matrix_idx != -1
    matrix_block = readme_text[matrix_idx : matrix_idx + 3000]
    row = next(
        (line for line in matrix_block.splitlines() if "Agentic CI self-healing" in line and "|" in line),
        None,
    )
    assert row is not None, "Maturity matrix row for Agentic CI self-healing is missing."
    assert "Phase 0" in row and "runtime not implemented" in row.lower(), (
        "Maturity matrix row for Agentic CI self-healing must declare 'Phase 0 — runtime not implemented'. "
        "See docs/audit/ACTION_PLAN_R4.md §S0-2."
    )


def test_maturity_matrix_memory_plane_row(readme_text: str) -> None:
    if not _is_phase_0(ADR_018):
        pytest.skip("ADR-018 is no longer Phase 0.")
    matrix_idx = readme_text.find("## Production-ready scope")
    assert matrix_idx != -1
    matrix_block = readme_text[matrix_idx : matrix_idx + 3000]
    row = next(
        (line for line in matrix_block.splitlines() if "Operational Memory Plane" in line and "|" in line),
        None,
    )
    assert row is not None, "Maturity matrix row for Operational Memory Plane is missing."
    assert "Phase 0" in row and "runtime not implemented" in row.lower(), (
        "Maturity matrix row for Operational Memory Plane must declare 'Phase 0 — runtime not implemented'. "
        "See docs/audit/ACTION_PLAN_R4.md §S0-2."
    )
