"""Dynamic risk scoring for the Agent Behavior Protocol (ADR-010).

Agents invoke :func:`get_risk_context` at the start of CONSULT/AUTO
operations to determine whether live system signals warrant ESCALATING
to a stricter mode (AUTO → CONSULT, CONSULT → STOP). The protocol never
RELAXES based on risk context: STOP is sticky.

Signal sources (by priority):
    1. mcp-prometheus — live Prometheus queries (preferred, ADR-010)
    2. local files ops/incident_state.json, ops/last_drift_report.json
       (fallback when MCP is unavailable)
    3. degraded mode — return an UNAVAILABLE context; caller falls back
       to the static AGENTS.md mapping

Consumers:
    - .windsurf/skills/**/SKILL.md invocations
    - CI jobs that emit the [AGENT MODE: ...] signal
    - Pre-deploy checks in deploy-common.yml (future enhancement)

Engineering Calibration (ADR-001):
    - The module is a 200-line helper, not a distributed policy engine.
    - Dynamic scoring can ONLY escalate; ADR-005 static mapping is the
      conservative floor.
    - Escalation thresholds live in code here so they are version-controlled
      alongside AGENTS.md.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

Mode = Literal["AUTO", "CONSULT", "STOP"]

_CACHE_TTL_SECONDS = 60
_cache: dict[str, tuple[float, "RiskContext"]] = {}


@dataclass(frozen=True)
class RiskContext:
    """Snapshot of live risk signals.

    Attributes:
        incident_active: A P1/P2 alert is firing.
        drift_severe:    Any feature's PSI > 2x its alert threshold.
        error_budget_exhausted: SLO burn rate says the budget is blown.
        off_hours: UTC Mon–Fri 18:00–08:00 OR Sat/Sun (business default).
        recent_rollback: A rollback audit issue was created in the last 6h.
        available: True if the signal source responded; False = fallback.
        source: "prometheus" | "file" | "unavailable".
    """

    incident_active: bool = False
    drift_severe: bool = False
    error_budget_exhausted: bool = False
    off_hours: bool = False
    recent_rollback: bool = False
    available: bool = False
    source: str = "unavailable"
    raw: dict = field(default_factory=dict)

    @property
    def signal_count(self) -> int:
        return sum(
            [
                self.incident_active,
                self.drift_severe,
                self.error_budget_exhausted,
                self.off_hours,
                self.recent_rollback,
            ]
        )

    def escalate(self, base_mode: Mode) -> Mode:
        """Apply the dynamic escalation table from ADR-010.

        Rules:
            AUTO + any 1 signal    → CONSULT
            CONSULT + any 1 signal → STOP
            STOP                   → STOP (always sticky)

        When :attr:`available` is False, returns ``base_mode`` unchanged
        (fallback — graceful degradation per ADR-010).
        """
        if base_mode == "STOP":
            return "STOP"
        if not self.available:
            return base_mode
        if self.signal_count == 0:
            return base_mode
        return "STOP" if base_mode == "CONSULT" else "CONSULT"


# ---------------------------------------------------------------------------
# Signal sources
# ---------------------------------------------------------------------------
def _load_file_signals(ops_dir: Path) -> RiskContext:
    """Fallback signal loader: reads ops/ artifacts written by CronJobs."""
    raw: dict = {}
    incident_active = False
    drift_severe = False
    recent_rollback = False

    incident_file = ops_dir / "incident_state.json"
    if incident_file.exists():
        try:
            data = json.loads(incident_file.read_text())
            raw["incident_state"] = data
            incident_active = bool(data.get("active", False))
        except Exception as exc:
            logger.debug("Could not parse incident_state.json: %s", exc)

    drift_file = ops_dir / "last_drift_report.json"
    if drift_file.exists():
        try:
            data = json.loads(drift_file.read_text())
            raw["drift_report"] = data
            drift_severe = bool(data.get("any_psi_over_2x_threshold", False))
        except Exception as exc:
            logger.debug("Could not parse last_drift_report.json: %s", exc)

    audit_log = ops_dir / "audit.jsonl"
    if audit_log.exists():
        try:
            six_hours_ago = time.time() - 6 * 3600
            for line in audit_log.read_text().splitlines()[-200:]:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("operation", "").startswith("rollback"):
                    ts_str = entry.get("timestamp", "")
                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
                        if ts >= six_hours_ago:
                            recent_rollback = True
                            raw["recent_rollback_entry"] = entry
                            break
                    except ValueError:
                        continue
        except Exception as exc:
            logger.debug("Could not scan audit.jsonl: %s", exc)

    return RiskContext(
        incident_active=incident_active,
        drift_severe=drift_severe,
        recent_rollback=recent_rollback,
        off_hours=_is_off_hours(),
        available=True,
        source="file",
        raw=raw,
    )


def _is_off_hours(now: datetime | None = None) -> bool:
    """Return True on weekends or weekday evenings/nights (UTC).

    Business default: 18:00–08:00 UTC Mon–Fri counts as off-hours.
    Weekends are always off-hours. Override via environment variable
    ``MLOPS_ON_HOURS_UTC`` (format "HH-HH", e.g. "06-20").
    """
    now = now or datetime.now(timezone.utc)
    if now.weekday() >= 5:  # Saturday / Sunday
        return True
    span = os.getenv("MLOPS_ON_HOURS_UTC", "08-18")
    try:
        start_s, end_s = span.split("-")
        start = int(start_s)
        end = int(end_s)
    except ValueError:
        start, end = 8, 18
    return not (start <= now.hour < end)


def _load_prometheus_signals(_prom_url: str) -> RiskContext:
    """Placeholder for mcp-prometheus-driven signals.

    When mcp-prometheus is wired in the agent's runtime, this function
    should query:
      * `sum(ALERTS{severity=~"P1|P2", alertstate="firing"})`
      * `max(...psi_score / ...psi_alert_threshold) > 2`
      * `1 - slo:availability:ratio_rate30d > 1`
      * `max({service}_performance_last_run_timestamp)` vs now (heartbeat)

    Until then, return UNAVAILABLE so the caller falls back to file signals
    or static mapping (ADR-010 graceful degradation).
    """
    return RiskContext(available=False, source="unavailable")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def get_risk_context(
    *,
    ops_dir: Path | str = "ops",
    prometheus_url: str | None = None,
    cache_key: str = "default",
) -> RiskContext:
    """Return a :class:`RiskContext` honoring ADR-010 source priority.

    Results are cached for 60 seconds per cache_key so repeated
    invocations within a single agentic workflow do not amplify load.
    """
    now = time.time()
    if cache_key in _cache:
        ts, ctx = _cache[cache_key]
        if now - ts < _CACHE_TTL_SECONDS:
            return ctx

    prom_url = prometheus_url or os.getenv("PROMETHEUS_URL")
    ctx: RiskContext
    if prom_url:
        ctx = _load_prometheus_signals(prom_url)
        if not ctx.available:
            ctx = _load_file_signals(Path(ops_dir))
    else:
        ctx = _load_file_signals(Path(ops_dir))

    _cache[cache_key] = (now, ctx)
    return ctx


def render_audit_line(base_mode: Mode, final_mode: Mode, ctx: RiskContext) -> str:
    """Return a one-line human-readable summary for audit logs."""
    signals = []
    if ctx.incident_active:
        signals.append("incident_active")
    if ctx.drift_severe:
        signals.append("drift_severe")
    if ctx.error_budget_exhausted:
        signals.append("error_budget_exhausted")
    if ctx.off_hours:
        signals.append("off_hours")
    if ctx.recent_rollback:
        signals.append("recent_rollback")
    sig_str = ",".join(signals) if signals else "none"
    return f"mode={base_mode}→{final_mode} source={ctx.source} signals=[{sig_str}]"
