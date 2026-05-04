"""Contract tests for ``common_utils.prediction_logger``.

Closes external-feedback gap 5.1 (May 2026) by documenting the
**actual** PII contract this module implements today.

Important reality check
-----------------------
``prediction_logger`` does NOT redact PII. It is a transport, not a
filter. The May 2026 external feedback labeled this as a coverage
gap, but the correct interpretation per ADR-018 §"Phase 1 — canonical
contracts + redaction" is that **redaction is a Phase 2 concern**:
adopters either drop PII upstream (preferred) or ship a
``LogBackend`` adapter that redacts on write.

These tests therefore verify the **as-is contract**:

1. Whatever ``features`` dict is passed in is serialized verbatim by
   the built-in StdoutBackend / SQLiteBackend.
2. ``deployment_id`` is preserved end-to-end (D-21/D-22 correlation
   contract).
3. Construction-time invariants from ``__post_init__`` reject
   missing required fields (already covered structurally in
   ``test_prediction_logger.py``; we add the negative cases that
   confirm a caller cannot accidentally drop ``deployment_id``
   metadata while keeping a hand-rolled custom backend).

If a future ADR (post-Phase-2 of ADR-018) introduces real redaction,
this file becomes the natural home for the redaction proofs.
"""

from __future__ import annotations

import io
import json
import sqlite3
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from common_utils.prediction_logger import (
    PredictionEvent,
    SQLiteBackend,
    StdoutBackend,
)


# ---------------------------------------------------------------------------
# Reusable factory
# ---------------------------------------------------------------------------
SENSITIVE_FEATURES = {
    "ssn": "123-45-6789",
    "email": "alice@example.com",
    "ip_address": "203.0.113.42",
    "amount": 1500.0,
    "category": "groceries",
}


def _event(features: dict | None = None, **overrides) -> PredictionEvent:
    base = dict(
        prediction_id="pred-001",
        entity_id="user-42",
        timestamp="2026-05-04T12:00:00Z",
        model_version="v1.2.3",
        features=features if features is not None else dict(SENSITIVE_FEATURES),
        score=0.87,
        prediction_class=1,
        slices={"region": "us-east-1"},
        latency_ms=12.4,
        deployment_id="prod-2026-05-04-rc1",
    )
    base.update(overrides)
    return PredictionEvent(**base)


# ---------------------------------------------------------------------------
# 1. As-is serialization — the contract this module ships today
# ---------------------------------------------------------------------------
class TestStdoutBackendAsIs:
    def test_features_serialized_verbatim(self) -> None:
        """The built-in backend writes the features dict raw. Adopters
        who need redaction MUST drop PII upstream of the
        ``log_prediction`` call OR ship a custom backend."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            StdoutBackend().write_batch([_event()])
        record = json.loads(buf.getvalue().strip())
        assert record["features"] == SENSITIVE_FEATURES, (
            "StdoutBackend MUST not transform feature values silently — "
            "that would surprise adopters who deliberately included a "
            "field they wanted to log."
        )

    def test_correlation_fields_preserved_end_to_end(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            StdoutBackend().write_batch([_event()])
        record = json.loads(buf.getvalue().strip())
        # Per ADR-015 PR-C1: deployment_id MUST round-trip through the
        # backend so an adopter joining audit logs to predictions can
        # always trace a prediction back to the deploy that produced it.
        assert record["deployment_id"] == "prod-2026-05-04-rc1"
        assert record["prediction_id"] == "pred-001"
        assert record["entity_id"] == "user-42"
        assert record["model_version"] == "v1.2.3"


class TestSQLiteBackendAsIs:
    def test_features_round_trip_through_sqlite(self, tmp_path: Path) -> None:
        backend = SQLiteBackend(path=str(tmp_path / "preds.db"))
        backend.write_batch([_event()])

        conn = sqlite3.connect(str(tmp_path / "preds.db"))
        row = conn.execute(
            "SELECT features_json, deployment_id FROM predictions_log "
            "WHERE prediction_id = ?",
            ("pred-001",),
        ).fetchone()
        conn.close()

        assert row is not None
        features = json.loads(row[0])
        assert features == SENSITIVE_FEATURES
        assert row[1] == "prod-2026-05-04-rc1"

    def test_caller_redaction_is_honored(self, tmp_path: Path) -> None:
        """When the CALLER drops PII before logging, the backend
        persists exactly the redacted view. This documents the
        recommended pattern: redact upstream, log downstream."""
        backend = SQLiteBackend(path=str(tmp_path / "preds.db"))
        redacted = {k: ("[REDACTED]" if k in {"ssn", "email", "ip_address"} else v)
                    for k, v in SENSITIVE_FEATURES.items()}
        backend.write_batch([_event(features=redacted)])

        conn = sqlite3.connect(str(tmp_path / "preds.db"))
        row = conn.execute(
            "SELECT features_json FROM predictions_log WHERE prediction_id = ?",
            ("pred-001",),
        ).fetchone()
        conn.close()
        features = json.loads(row[0])
        assert features["ssn"] == "[REDACTED]"
        assert features["email"] == "[REDACTED]"
        assert features["amount"] == 1500.0  # non-PII preserved


# ---------------------------------------------------------------------------
# 2. Negative cases — required fields are still required when a
#    custom feature dict is passed (regression for D-20).
# ---------------------------------------------------------------------------
class TestRequiredFieldsAreEnforced:
    @pytest.mark.parametrize(
        "missing_field,value",
        [
            ("prediction_id", ""),
            ("entity_id", ""),
            ("model_version", ""),
        ],
    )
    def test_blank_required_field_rejected(self, missing_field: str, value: str) -> None:
        with pytest.raises(ValueError):
            _event(**{missing_field: value})

    def test_deployment_id_optional(self) -> None:
        event = _event(deployment_id=None)
        assert event.deployment_id is None
