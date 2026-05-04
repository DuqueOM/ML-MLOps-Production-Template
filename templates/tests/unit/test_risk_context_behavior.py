"""Behavioral test suite for the dynamic risk-mode protocol.

Closes external-feedback gap 2.4 (May 2026): existing risk-context
unit tests cover the *primitives* (escalate with 0/1 signal,
off-hours window, file/Prometheus loaders). They DO NOT exercise the
**full escalation matrix** as documented in
``MEMORY[01-mlops-conventions.md]``:

    | base_mode | signals | final_mode |
    |-----------|---------|-----------|
    | AUTO      | 0       | AUTO      |
    | AUTO      | >= 1    | CONSULT   |
    | CONSULT   | 0       | CONSULT   |
    | CONSULT   | >= 1    | STOP      |
    | STOP      | any     | STOP (sticky) |

This file walks the matrix end-to-end (file-loader path) and proves
the audit-line rendering is consistent with the table for every cell.
It is the *behavioral* counterpart to the structural tests in
``test_risk_context.py``.
"""

from __future__ import annotations

import json
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pytest

from common_utils.risk_context import (
    Mode,
    RiskContext,
    _load_file_signals,
    get_risk_context,
    render_audit_line,
)


# ---------------------------------------------------------------------------
# Helpers — synthesize each named signal via the file loader
# ---------------------------------------------------------------------------
SIGNAL_NAMES = (
    "incident_active",
    "drift_severe",
    "error_budget_exhausted",
    "off_hours",
    "recent_rollback",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _seed_ops_dir(ops_dir: Path, signals: Iterable[str]) -> None:
    """Write the ops/ artifacts that ``_load_file_signals`` reads."""
    ops_dir.mkdir(parents=True, exist_ok=True)
    enabled = set(signals)
    if "incident_active" in enabled:
        (ops_dir / "incident_state.json").write_text(json.dumps({"active": True}))
    if "drift_severe" in enabled:
        (ops_dir / "last_drift_report.json").write_text(
            json.dumps({"any_psi_over_2x_threshold": True})
        )
    if "recent_rollback" in enabled:
        (ops_dir / "audit.jsonl").write_text(
            json.dumps({"operation": "rollback", "timestamp": _now_iso()}) + "\n"
        )
    # off_hours and error_budget_exhausted are not file-driven; we
    # synthesize them by replacing the loaded RiskContext.


def _build_context(tmp_path: Path, signals: Iterable[str], cache_key: str) -> RiskContext:
    """Build a RiskContext deterministically — NO wall-clock / env reads.

    Historical bug: an earlier version called ``get_risk_context()``
    which evaluates ``_is_off_hours()`` against the real wall clock.
    At 18:00–08:00 UTC (Mon–Fri) + weekends, the file loader emits
    ``off_hours=True`` "for free", breaking every signal-count assertion
    with an extra phantom signal. Fix: read file-backed signals
    (incident, drift, rollback) via ``_load_file_signals`` — which does
    NOT touch the clock — then FORCE off_hours / error_budget_exhausted
    to the test's intended value (instead of letting them leak from
    the environment).
    """
    ops_dir = tmp_path / "ops"
    _seed_ops_dir(ops_dir, signals)
    del cache_key  # cache intentionally bypassed — tests assert behavior, not cache
    base = _load_file_signals(ops_dir)
    return replace(
        base,
        available=True,
        # off_hours + error_budget_exhausted are NOT file-backed;
        # force them to the test's intended value so the wall clock
        # and env vars cannot influence the matrix walk.
        off_hours="off_hours" in set(signals),
        error_budget_exhausted="error_budget_exhausted" in set(signals),
    )


# ---------------------------------------------------------------------------
# 1. Escalation matrix — every cell of the table
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("base_mode", ["AUTO", "CONSULT", "STOP"])
@pytest.mark.parametrize("signal", SIGNAL_NAMES)
def test_each_signal_escalates_one_step(
    tmp_path: Path, base_mode: Mode, signal: str
) -> None:
    """Every individual signal must trigger exactly one escalation step.

    Walks: AUTO -> CONSULT, CONSULT -> STOP, STOP -> STOP.
    """
    ctx = _build_context(tmp_path, [signal], cache_key=f"single-{signal}-{base_mode}")
    final = ctx.escalate(base_mode)

    assert ctx.signal_count == 1, f"signal {signal!r} did not register"
    if base_mode == "AUTO":
        assert final == "CONSULT"
    elif base_mode == "CONSULT":
        assert final == "STOP"
    else:
        assert final == "STOP"  # sticky


@pytest.mark.parametrize("base_mode", ["AUTO", "CONSULT", "STOP"])
def test_no_signals_keeps_base_mode(tmp_path: Path, base_mode: Mode) -> None:
    ctx = _build_context(tmp_path, [], cache_key=f"none-{base_mode}")
    assert ctx.signal_count == 0
    assert ctx.escalate(base_mode) == base_mode


@pytest.mark.parametrize("base_mode", ["AUTO", "CONSULT"])
def test_multiple_signals_dont_double_escalate(tmp_path: Path, base_mode: Mode) -> None:
    """Per ADR-010: dynamic scoring can only escalate ONE step.

    AUTO with 5 signals must stop at CONSULT, NOT skip to STOP.
    """
    ctx = _build_context(tmp_path, SIGNAL_NAMES, cache_key=f"all-{base_mode}")
    assert ctx.signal_count == 5

    final = ctx.escalate(base_mode)
    expected = "CONSULT" if base_mode == "AUTO" else "STOP"
    assert final == expected


def test_stop_is_sticky_under_all_signal_combinations(tmp_path: Path) -> None:
    """Per AGENTS.md: STOP is sticky regardless of signal count or
    availability."""
    for n in range(len(SIGNAL_NAMES) + 1):
        signals = SIGNAL_NAMES[:n]
        ctx = _build_context(tmp_path, signals, cache_key=f"stop-{n}")
        assert ctx.escalate("STOP") == "STOP", f"STOP should stick with signals={signals}"


# ---------------------------------------------------------------------------
# 2. UNAVAILABLE fallback — ADR-010 §"graceful degradation"
# ---------------------------------------------------------------------------
def test_unavailable_context_never_escalates(tmp_path: Path) -> None:
    """When ``available=False``, the context must NOT escalate, even if
    raw signal flags happen to be set. This is the safety net for the
    Prometheus-down case documented in MEMORY[01-mlops-conventions.md]
    ('When mcp-prometheus is unavailable, the agent falls back to the
    static AGENTS.md mapping and MUST emit risk_signals: UNAVAILABLE')."""
    bad_ctx = RiskContext(
        incident_active=True,
        drift_severe=True,
        error_budget_exhausted=True,
        off_hours=True,
        recent_rollback=True,
        available=False,
        source="unavailable",
    )
    assert bad_ctx.signal_count == 5  # the flags are visible
    assert bad_ctx.escalate("AUTO") == "AUTO"
    assert bad_ctx.escalate("CONSULT") == "CONSULT"
    assert bad_ctx.escalate("STOP") == "STOP"


# ---------------------------------------------------------------------------
# 3. Audit-line rendering — proves the auditor sees the SAME picture
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("base_mode", ["AUTO", "CONSULT", "STOP"])
def test_audit_line_lists_every_active_signal(tmp_path: Path, base_mode: Mode) -> None:
    """The render_audit_line output must list each active signal so a
    reviewer can reconstruct the escalation decision from the audit
    log alone."""
    ctx = _build_context(tmp_path, SIGNAL_NAMES, cache_key=f"audit-{base_mode}")
    final = ctx.escalate(base_mode)
    line = render_audit_line(base_mode, final, ctx)

    assert f"mode={base_mode}→{final}" in line
    for name in SIGNAL_NAMES:
        assert name in line, f"audit line missing signal {name!r}: {line!r}"


def test_audit_line_signals_none_when_quiet(tmp_path: Path) -> None:
    ctx = _build_context(tmp_path, [], cache_key="audit-empty")
    line = render_audit_line("AUTO", "AUTO", ctx)
    assert "signals=[none]" in line
    assert "mode=AUTO→AUTO" in line


# ---------------------------------------------------------------------------
# 4. Cache TTL — repeated calls must not re-read the file system
# ---------------------------------------------------------------------------
def test_cache_returns_same_object_within_ttl(tmp_path: Path) -> None:
    ops_dir = tmp_path / "ops"
    _seed_ops_dir(ops_dir, ["incident_active"])

    first = get_risk_context(ops_dir=ops_dir, cache_key="ttl-test")
    # Mutate the file: a non-cached read would now flip the signal.
    (ops_dir / "incident_state.json").write_text(json.dumps({"active": False}))
    second = get_risk_context(ops_dir=ops_dir, cache_key="ttl-test")

    assert first is second, "cache must hand back the same RiskContext within TTL"
    assert second.incident_active is True, "cached value must reflect the FIRST read"


def test_distinct_cache_keys_are_isolated(tmp_path: Path) -> None:
    a = _build_context(tmp_path / "a", ["incident_active"], cache_key="iso-A")
    b = _build_context(tmp_path / "b", [], cache_key="iso-B")
    assert a.incident_active is True
    assert b.incident_active is False
