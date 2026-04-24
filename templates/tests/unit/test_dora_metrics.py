"""Unit tests for dora_metrics (D4, v1.9.0)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

import dora_metrics as d  # noqa: E402


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_deployment_frequency_empty():
    r = d.compute_deployment_frequency([])
    assert r["count"] == 0
    assert r["per_week"] == 0.0


def test_deployment_frequency_counts_only_successful():
    now = datetime(2026, 4, 1, tzinfo=timezone.utc)
    runs = [
        {"conclusion": "success", "created_at": _iso(now)},
        {"conclusion": "success", "created_at": _iso(now + timedelta(days=7))},
        {"conclusion": "failure", "created_at": _iso(now + timedelta(days=8))},
    ]
    r = d.compute_deployment_frequency(runs)
    assert r["count"] == 2


def test_lead_time_for_changes_matches_next_deploy():
    base = datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc)
    merged = [{"merged_at": _iso(base)}]
    deploys = [
        {"conclusion": "success", "created_at": _iso(base + timedelta(hours=2))},
        {"conclusion": "success", "created_at": _iso(base + timedelta(days=1))},
    ]
    r = d.compute_lead_time(merged, deploys)
    assert r["median_seconds"] == 7200
    assert r["n"] == 1


def test_lead_time_skips_prs_before_any_deploy():
    base = datetime(2026, 4, 1, tzinfo=timezone.utc)
    merged = [{"merged_at": _iso(base)}]
    deploys = [{"conclusion": "success", "created_at": _iso(base - timedelta(days=1))}]
    r = d.compute_lead_time(merged, deploys)
    assert r["n"] == 0
    assert r["median_seconds"] is None


def test_change_failure_rate():
    base = datetime(2026, 4, 1, tzinfo=timezone.utc)
    deploys = [
        {"conclusion": "success", "created_at": _iso(base)},
        {"conclusion": "success", "created_at": _iso(base + timedelta(days=1))},
        {"conclusion": "success", "created_at": _iso(base + timedelta(days=2))},
        {"conclusion": "success", "created_at": _iso(base + timedelta(days=3))},
    ]
    rollback_issues = [{"number": 10}, {"number": 11}]
    r = d.compute_change_failure_rate(deploys, rollback_issues)
    assert r["rate"] == 0.5
    assert r["total_deploys"] == 4
    assert r["rollbacks"] == 2


def test_mttr_matches_next_incident_close():
    t0 = datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc)
    audit = [
        {"operation": "rollback", "timestamp": _iso(t0)},
        {"operation": "incident_close", "timestamp": _iso(t0 + timedelta(minutes=45))},
        {"operation": "rollback", "timestamp": _iso(t0 + timedelta(days=3))},
        {"operation": "incident_close", "timestamp": _iso(t0 + timedelta(days=3, hours=1))},
    ]
    r = d.compute_mttr(audit)
    # Two deltas: 2700s and 3600s; median = 3150
    assert r["n"] == 2
    assert r["median_seconds"] == 3150


def test_mttr_no_close_yields_null():
    audit = [{"operation": "rollback", "timestamp": _iso(datetime.now(timezone.utc))}]
    r = d.compute_mttr(audit)
    assert r["median_seconds"] is None


def test_load_audit_entries_missing_file(tmp_path):
    assert d.load_audit_entries(tmp_path / "nonexistent.jsonl") == []


def test_load_audit_entries_parses(tmp_path):
    p = tmp_path / "audit.jsonl"
    p.write_text(json.dumps({"operation": "x", "timestamp": "2026-01-01T00:00:00+00:00"}) + "\n")
    entries = d.load_audit_entries(p)
    assert len(entries) == 1
    assert entries[0]["operation"] == "x"
