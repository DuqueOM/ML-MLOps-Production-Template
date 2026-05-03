"""Operational Memory Plane — Phase 1 redaction pipeline (ADR-018).

Status: Phase 1 — pure-string redaction. NO ingest worker, NO storage.

Authority: ADR-018 §"Mitigations" — D-17 redaction at ingest. Every
``MemoryUnit.summary`` and every textual evidence excerpt MUST pass
through this pipeline before it is persisted, indexed, or surfaced to
agents.

Hard invariant (covered by `test_memory_redaction.py`):

    No string matching `gitleaks` patterns or PII patterns survives the
    pipeline. Patterns matched are replaced with a redacted placeholder
    that preserves length information for forensic analysis but never
    leaks the secret itself.

The redaction is **conservative**: false positives (a non-secret matching
a pattern) are accepted as the cost of the safety guarantee. False
negatives (a real secret slipping through) are not. Adopters extending
the pattern set MUST add tests in `test_memory_redaction.py`.

Pattern sources:

- `templates/common_utils/secrets.py` (existing token detector — we
  reuse its regex catalogue where possible).
- `.gitleaks.toml` (the canonical project-level secret config).
- A small PII set (email, US SSN, phone, IBAN) that gitleaks does not
  cover but ingest workers commonly encounter in postmortem text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

# ---------------------------------------------------------------------------
# Pattern catalogue.
#
# Each pattern is (label, compiled-regex). Labels appear in the redaction
# report so investigators can correlate redactions back to a class.
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # AWS access keys — gitleaks core pattern.
    ("aws_access_key_id", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("aws_secret_access_key", re.compile(r"(?<![A-Za-z0-9/+=])[A-Za-z0-9/+=]{40}(?![A-Za-z0-9/+=])")),
    # GCP API keys.
    ("gcp_api_key", re.compile(r"AIza[0-9A-Za-z\-_]{35}")),
    # GitHub PAT classic + fine-grained.
    ("github_pat_classic", re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("github_pat_fine", re.compile(r"github_pat_[A-Za-z0-9_]{82}")),
    # Slack tokens.
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    # OpenAI API keys (sk-... legacy + sk-proj-... project).
    ("openai_api_key_legacy", re.compile(r"sk-[A-Za-z0-9]{32,}")),
    ("openai_api_key_proj", re.compile(r"sk-proj-[A-Za-z0-9_\-]{20,}")),
    # Anthropic API keys.
    ("anthropic_api_key", re.compile(r"sk-ant-api03-[A-Za-z0-9_\-]{32,}")),
    # JWT-like (three base64url segments separated by dots).
    ("jwt_like", re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
    # Generic Bearer tokens in URLs / headers.
    ("bearer_token", re.compile(r"(?i)Bearer\s+[A-Za-z0-9_\-\.=]{20,}")),
    # Private key blocks.
    (
        "pem_private_key",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    ),
    # Connection strings with embedded password.
    (
        "connection_string_with_password",
        re.compile(r"(?i)(postgres|mysql|mongodb|redis)(\+srv)?://[^:\s]+:[^@\s]+@[^\s]+"),
    ),
]

_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # RFC-5322-ish email.
    ("email", re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")),
    # US SSN (NNN-NN-NNNN). Conservative: spaces also.
    ("us_ssn", re.compile(r"\b\d{3}[- ]\d{2}[- ]\d{4}\b")),
    # E.164 phone (+ country code, 8-15 digits).
    ("e164_phone", re.compile(r"(?<!\d)\+[1-9]\d{7,14}(?!\d)")),
    # IBAN (loose: 2 letters + 2 digits + 11..30 alphanumerics).
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")),
    # IPv4 address (info — not a secret, but useful in postmortem context).
    ("ipv4", re.compile(r"(?<!\d)((25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(25[0-5]|2[0-4]\d|1?\d?\d)(?!\d)")),
]


REDACTION_PLACEHOLDER = "[REDACTED:{label}:len={length}]"


@dataclass(frozen=True)
class RedactionReport:
    """Side-channel info about what was redacted, without leaking the secret.

    Phase 1 emits a simple count; Phase 2 may add coarse position info if
    investigators need it. Investigation must NEVER receive the cleartext
    of a redacted match.
    """

    counts: dict[str, int]

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def _apply_patterns(text: str, patterns: Iterable[tuple[str, re.Pattern[str]]]) -> tuple[str, dict[str, int]]:
    """Return (redacted_text, counts_per_label)."""
    counts: dict[str, int] = {}
    out = text
    for label, pat in patterns:
        # We use a closure to capture both the label and the matched length.
        def _replace(m: re.Match[str], _label: str = label) -> str:
            return REDACTION_PLACEHOLDER.format(label=_label, length=len(m.group(0)))

        new_out, n = pat.subn(_replace, out)
        if n > 0:
            counts[label] = counts.get(label, 0) + n
            out = new_out
    return out, counts


def redact(text: str) -> tuple[str, RedactionReport]:
    """Run the canonical redaction pipeline on ``text``.

    Returns the redacted text and a :class:`RedactionReport` describing
    how many matches per label were redacted.

    The function is **idempotent**: redacting an already-redacted string
    is a no-op (placeholders themselves do not match any pattern).
    """
    if not isinstance(text, str):
        raise TypeError(f"redact() requires str input; got {type(text).__name__}")

    redacted, secret_counts = _apply_patterns(text, _SECRET_PATTERNS)
    redacted, pii_counts = _apply_patterns(redacted, _PII_PATTERNS)

    merged: dict[str, int] = {}
    for d in (secret_counts, pii_counts):
        for k, v in d.items():
            merged[k] = merged.get(k, 0) + v

    return redacted, RedactionReport(counts=merged)


def redact_strict(text: str) -> str:
    """Run :func:`redact` and raise if anything is redacted.

    Useful at validation seams where a redaction is a contract violation
    (e.g. the input was supposed to be redacted by an upstream layer).
    """
    redacted, report = redact(text)
    if report.total > 0:
        raise ValueError(
            "redact_strict refused: input contained redactable patterns "
            f"(counts={report.counts}). Pre-redact upstream and retry."
        )
    return redacted


__all__ = [
    "redact",
    "redact_strict",
    "RedactionReport",
    "REDACTION_PLACEHOLDER",
]
