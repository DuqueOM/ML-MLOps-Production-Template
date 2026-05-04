"""Unit tests for risk_context — dynamic Behavior Protocol (ADR-010)."""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

_COMMON = Path(__file__).resolve().parents[2] / "common_utils"
sys.path.insert(0, str(_COMMON.parent))

from common_utils.risk_context import (  # noqa: E402
    RiskContext,
    _cache,
    _is_off_hours,
    get_risk_context,
    render_audit_line,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    _cache.clear()
    yield
    _cache.clear()


class TestEscalation:
    def test_stop_is_sticky(self):
        ctx = RiskContext(available=True, source="file", incident_active=True)
        assert ctx.escalate("STOP") == "STOP"

    def test_auto_with_no_signals_stays_auto(self):
        ctx = RiskContext(available=True, source="file")
        assert ctx.escalate("AUTO") == "AUTO"

    def test_auto_with_one_signal_becomes_consult(self):
        ctx = RiskContext(available=True, source="file", incident_active=True)
        assert ctx.escalate("AUTO") == "CONSULT"

    def test_consult_with_one_signal_becomes_stop(self):
        ctx = RiskContext(available=True, source="file", drift_severe=True)
        assert ctx.escalate("CONSULT") == "STOP"

    def test_multiple_signals_still_escalate_once_step(self):
        ctx = RiskContext(
            available=True,
            source="file",
            incident_active=True,
            drift_severe=True,
            off_hours=True,
        )
        assert ctx.escalate("AUTO") == "CONSULT"
        assert ctx.escalate("CONSULT") == "STOP"

    def test_unavailable_never_escalates(self):
        ctx = RiskContext(available=False, source="unavailable", incident_active=True)
        assert ctx.escalate("AUTO") == "AUTO"
        assert ctx.escalate("CONSULT") == "CONSULT"


class TestOffHours:
    def test_weekend_is_off_hours(self):
        saturday = datetime(2026, 4, 25, 10, 0, tzinfo=timezone.utc)  # Sat 10 UTC
        assert _is_off_hours(saturday) is True

    def test_weekday_business_hours_on(self):
        tuesday_noon = datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc)
        assert _is_off_hours(tuesday_noon) is False

    def test_weekday_evening_off(self):
        tuesday_night = datetime(2026, 4, 28, 22, 0, tzinfo=timezone.utc)
        assert _is_off_hours(tuesday_night) is True

    def test_env_override_valid_window(self, monkeypatch):
        """A valid expanded on-hours window (06-22) is honoured."""
        monkeypatch.setenv("MLOPS_ON_HOURS_UTC", "06-22")
        monday_3am = datetime(2026, 4, 27, 3, 0, tzinfo=timezone.utc)
        monday_noon = datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc)
        assert _is_off_hours(monday_3am) is True  # still outside 06-22
        assert _is_off_hours(monday_noon) is False


class TestOnHoursOverrideHardening:
    """Red-team F2 (docs/agentic/red-team-log.md Entry 5): the
    MLOPS_ON_HOURS_UTC parser must refuse spans that cover the whole
    day, because they silently suppress off_hours escalation on
    weekdays. These tests pin the hardened behaviour.
    """

    def test_full_day_span_rejected(self, monkeypatch):
        """00-24 covers the entire day and would silently set
        off_hours=False on weekday 03:00 UTC. F2 forces fallback
        to 08-18 so off_hours=True at 03:00 remains detected.
        """
        monkeypatch.setenv("MLOPS_ON_HOURS_UTC", "00-24")
        monday_3am = datetime(2026, 4, 27, 3, 0, tzinfo=timezone.utc)
        assert _is_off_hours(monday_3am) is True

    def test_reversed_span_rejected(self, monkeypatch):
        """22-06 (reversed) is a config error; fall back to 08-18."""
        monkeypatch.setenv("MLOPS_ON_HOURS_UTC", "22-06")
        monday_3am = datetime(2026, 4, 27, 3, 0, tzinfo=timezone.utc)
        assert _is_off_hours(monday_3am) is True

    def test_degenerate_span_rejected(self, monkeypatch):
        """12-12 (empty window) is a config error; fall back to 08-18."""
        monkeypatch.setenv("MLOPS_ON_HOURS_UTC", "12-12")
        monday_noon = datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc)
        # 12:00 is inside default 08-18, so off_hours should be False.
        assert _is_off_hours(monday_noon) is False

    def test_out_of_range_rejected(self, monkeypatch):
        """Hour > 24 is out-of-range; fall back to 08-18."""
        monkeypatch.setenv("MLOPS_ON_HOURS_UTC", "08-99")
        monday_3am = datetime(2026, 4, 27, 3, 0, tzinfo=timezone.utc)
        assert _is_off_hours(monday_3am) is True

    def test_malformed_rejected(self, monkeypatch):
        """'garbage' is malformed; fall back to 08-18."""
        monkeypatch.setenv("MLOPS_ON_HOURS_UTC", "garbage")
        monday_3am = datetime(2026, 4, 27, 3, 0, tzinfo=timezone.utc)
        assert _is_off_hours(monday_3am) is True

    def test_weekend_still_off_hours_regardless_of_override(self, monkeypatch):
        """Even with a valid-but-expansive override, weekends MUST remain
        off-hours. The check is structural (weekday() >= 5) and runs
        before the env var is consulted.
        """
        monkeypatch.setenv("MLOPS_ON_HOURS_UTC", "00-23")  # valid, wide
        saturday = datetime(2026, 4, 25, 10, 0, tzinfo=timezone.utc)
        assert _is_off_hours(saturday) is True

    def test_warning_emitted_on_rejected_span(self, monkeypatch, caplog):
        """The hardening is OBSERVABLE: a warning is logged when a
        rejected span is encountered. Without a log, ops could not
        distinguish 'config drift' from 'parser working as intended'.
        """
        import logging as _logging

        monkeypatch.setenv("MLOPS_ON_HOURS_UTC", "00-24")
        with caplog.at_level(_logging.WARNING, logger="common_utils.risk_context"):
            _is_off_hours(datetime(2026, 4, 27, 3, 0, tzinfo=timezone.utc))
        assert any(
            "MLOPS_ON_HOURS_UTC" in rec.message and "full day" in rec.message.lower()
            for rec in caplog.records
        ), "Expected a warning mentioning MLOPS_ON_HOURS_UTC and 'full day'."


class TestFileSignals:
    def test_no_files_yields_empty_context(self, tmp_path):
        ctx = get_risk_context(ops_dir=tmp_path)
        assert ctx.available is True
        assert ctx.signal_count <= 1  # at most off_hours might flip

    def test_incident_state_detected(self, tmp_path):
        (tmp_path / "incident_state.json").write_text(json.dumps({"active": True}))
        ctx = get_risk_context(ops_dir=tmp_path)
        assert ctx.incident_active is True

    def test_drift_severe_detected(self, tmp_path):
        (tmp_path / "last_drift_report.json").write_text(
            json.dumps({"any_psi_over_2x_threshold": True})
        )
        ctx = get_risk_context(ops_dir=tmp_path)
        assert ctx.drift_severe is True

    def test_recent_rollback_detected(self, tmp_path):
        entry = {
            "agent": "test",
            "operation": "rollback",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        (tmp_path / "audit.jsonl").write_text(json.dumps(entry) + "\n")
        ctx = get_risk_context(ops_dir=tmp_path, cache_key=f"recent-{time.time()}")
        assert ctx.recent_rollback is True

    def test_old_rollback_ignored(self, tmp_path):
        old = datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()
        entry = {"agent": "t", "operation": "rollback", "timestamp": old}
        (tmp_path / "audit.jsonl").write_text(json.dumps(entry) + "\n")
        ctx = get_risk_context(ops_dir=tmp_path, cache_key=f"old-{time.time()}")
        assert ctx.recent_rollback is False


class TestAudit:
    def test_render_audit_line_no_signals(self):
        ctx = RiskContext(available=True, source="file")
        line = render_audit_line("AUTO", "AUTO", ctx)
        assert "mode=AUTO→AUTO" in line
        assert "signals=[none]" in line

    def test_render_audit_line_with_signals(self):
        ctx = RiskContext(
            available=True,
            source="file",
            incident_active=True,
            off_hours=True,
        )
        line = render_audit_line("AUTO", "CONSULT", ctx)
        assert "incident_active" in line
        assert "off_hours" in line


class TestCaching:
    def test_cache_hits_within_ttl(self, tmp_path):
        ctx1 = get_risk_context(ops_dir=tmp_path, cache_key="k1")
        # Write a new file AFTER first call — cached call should not see it
        (tmp_path / "incident_state.json").write_text(json.dumps({"active": True}))
        ctx2 = get_risk_context(ops_dir=tmp_path, cache_key="k1")
        assert ctx1 is ctx2
        assert ctx2.incident_active is False  # cached False

    def test_different_cache_keys_isolated(self, tmp_path):
        ctx1 = get_risk_context(ops_dir=tmp_path, cache_key="a")
        (tmp_path / "incident_state.json").write_text(json.dumps({"active": True}))
        ctx2 = get_risk_context(ops_dir=tmp_path, cache_key="b")
        assert ctx2.incident_active is True


# ---------------------------------------------------------------------------
# Prometheus integration (ADR-014 §4.1)
# ---------------------------------------------------------------------------
class _FakeResponse:
    """Minimal file-like stand-in for urllib.request.urlopen responses."""

    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


def _vector_payload(non_empty: bool) -> dict:
    """Shape of a successful /api/v1/query response with a vector result."""
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [{"metric": {}, "value": [1700000000, "1"]}] if non_empty else [],
        },
    }


class TestPrometheusSignals:
    """Mock urllib.request.urlopen to cover the new Prometheus path."""

    def _patch_urlopen(self, monkeypatch, responses: list):
        """Install a fake urlopen that returns successive responses."""
        from common_utils import risk_context as rc

        it = iter(responses)

        def fake_urlopen(_url, timeout=None, context=None):
            # `context=` kwarg added by HIGH-9 (v0.15.0) when the
            # Prometheus loader started passing an SSL context for
            # auth + CA bundle support. Mock accepts it for parity.
            r = next(it)
            if isinstance(r, Exception):
                raise r
            return _FakeResponse(r)

        # Patch inside the module's late-imported urllib reference.
        import urllib.request

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        return rc

    def test_all_queries_succeed_all_false(self, monkeypatch, tmp_path):
        rc = self._patch_urlopen(
            monkeypatch,
            [_vector_payload(False), _vector_payload(False), _vector_payload(False)],
        )
        ctx = rc._load_prometheus_signals("http://prom.local:9090")
        assert ctx.available is True
        assert ctx.source == "prometheus"
        assert ctx.incident_active is False
        assert ctx.drift_severe is False
        assert ctx.error_budget_exhausted is False

    def test_one_query_positive(self, monkeypatch):
        rc = self._patch_urlopen(
            monkeypatch,
            [_vector_payload(True), _vector_payload(False), _vector_payload(False)],
        )
        ctx = rc._load_prometheus_signals("http://prom.local:9090")
        assert ctx.available is True
        assert ctx.incident_active is True
        assert ctx.signal_count >= 1  # off_hours may add more

    def test_http_error_degrades_to_unavailable(self, monkeypatch):
        import urllib.error

        rc = self._patch_urlopen(
            monkeypatch,
            [
                _vector_payload(False),
                urllib.error.URLError("connection refused"),
                _vector_payload(False),
            ],
        )
        ctx = rc._load_prometheus_signals("http://prom.local:9090")
        assert ctx.available is False
        assert ctx.source == "unavailable"

    def test_non_success_status_degrades(self, monkeypatch):
        # _load_prometheus_signals issues one query per signal in
        # _PROMETHEUS_QUERIES (currently 3); each fakes urlopen pulls
        # one response off the iterator. Provide one error response per
        # call so the test does not exhaust the iterator (StopIteration)
        # before the loader has a chance to evaluate the failures.
        error_response = {"status": "error", "error": "query failed", "data": {}}
        rc = self._patch_urlopen(monkeypatch, [error_response, error_response, error_response])
        ctx = rc._load_prometheus_signals("http://prom.local:9090")
        assert ctx.available is False
        assert ctx.source == "unavailable"

    def test_get_risk_context_uses_prometheus_when_url_set(self, monkeypatch, tmp_path):
        rc = self._patch_urlopen(
            monkeypatch,
            [_vector_payload(True), _vector_payload(False), _vector_payload(False)],
        )
        monkeypatch.setenv("PROMETHEUS_URL", "http://prom.local:9090")
        ctx = rc.get_risk_context(ops_dir=tmp_path, cache_key="prom-test")
        assert ctx.source == "prometheus"
        assert ctx.incident_active is True

    def test_get_risk_context_falls_back_when_prom_fails(self, monkeypatch, tmp_path):
        import urllib.error

        rc = self._patch_urlopen(
            monkeypatch,
            [urllib.error.URLError("down"), urllib.error.URLError("down"), urllib.error.URLError("down")],
        )
        # Seed file-side signal so fallback is distinguishable from empty.
        (tmp_path / "incident_state.json").write_text(json.dumps({"active": True}))
        monkeypatch.setenv("PROMETHEUS_URL", "http://prom.local:9090")
        ctx = rc.get_risk_context(ops_dir=tmp_path, cache_key="prom-fail")
        assert ctx.source == "file"
        assert ctx.incident_active is True

    def test_recent_rollback_folded_in_when_prom_up(self, monkeypatch, tmp_path):
        rc = self._patch_urlopen(
            monkeypatch,
            [_vector_payload(False), _vector_payload(False), _vector_payload(False)],
        )
        # Simulate a recent rollback entry in the audit log.
        audit = tmp_path / "audit.jsonl"
        recent = datetime.now(timezone.utc).isoformat()
        audit.write_text(
            json.dumps(
                {
                    "timestamp": recent,
                    "operation": "rollback",
                    "result": "success",
                }
            )
            + "\n"
        )
        monkeypatch.setenv("PROMETHEUS_URL", "http://prom.local:9090")
        ctx = rc.get_risk_context(ops_dir=tmp_path, cache_key="prom-rollback")
        assert ctx.source == "prometheus"
        assert ctx.recent_rollback is True
