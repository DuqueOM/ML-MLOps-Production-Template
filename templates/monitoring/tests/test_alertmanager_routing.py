"""Contract test — Alertmanager routing is exercised end-to-end (R4-M5).

Authority: ACTION_PLAN_R4 §S2-4 + ADR-020 §M5.

R4-M5 flagged that the template shipped alert RULES
(`templates/monitoring/alertmanager-rules.yaml`) but no one had ever
exercised the ROUTING end-to-end. A mis-routed P1 would fire, find
no receiver match, and silently fall into the catch-all — we would
only discover the mis-route during a real incident.

This test closes the gap in two complementary ways:

1. **amtool path (preferred)** — when `amtool` is on PATH, use
   ``amtool config routes test --config.file=... <labels>`` to ask
   the real Alertmanager binary where each synthetic alert lands.
   This is the authoritative check (it parses the config with the
   same code Alertmanager uses at runtime).

2. **Pure-Python fallback (always runs)** — a minimal routing
   simulator parses the YAML and walks the `route:` tree top-down
   applying the same `matchers` semantics. It exists so the test
   has teeth in CI images that ship without amtool.

Both paths must agree — divergence means either the simulator or
the config has drifted from Alertmanager's semantics.

The invariants enforced (one parametrised test per row):

    severity=critical + action=page      → oncall-pager       (P1)
    severity=warning  + action=ticket    → platform-tickets   (P2)
    severity=warning  + action=retrain   → ml-retrain         (P3)
    severity=info     + action=heartbeat → ops-chat           (P4)
    alertname=NoMatch                    → ops-chat           (default)

A final structural check locks:
- every named receiver in `routes:` is defined in `receivers:`
- `config.file` parses under `amtool check-config` (when available)
- the file is a sibling of `alertmanager-rules.yaml` so operators
  find both in one directory listing.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG = REPO_ROOT / "templates" / "monitoring" / "alertmanager.yml"
RULES = REPO_ROOT / "templates" / "monitoring" / "alertmanager-rules.yaml"

# Canonical routing table — the single source of truth for both
# test assertions and the runbook. If this list changes, the runbook
# §"Expected routing table" table must change in the same PR (the
# doc-inventory test will catch stale docs once merged).
ROUTING_MATRIX: list[tuple[dict[str, str], str, str]] = [
    # (labels, expected_receiver, priority_label)
    ({"severity": "critical", "action": "page"}, "oncall-pager", "P1"),
    ({"severity": "warning", "action": "ticket"}, "platform-tickets", "P2"),
    ({"severity": "warning", "action": "retrain"}, "ml-retrain", "P3"),
    ({"severity": "info", "action": "heartbeat"}, "ops-chat", "P4"),
    ({"alertname": "NoMatch"}, "ops-chat", "default"),
]


# ---------------------------------------------------------------------------
# Pure-Python routing simulator — used as fallback AND cross-check.
# ---------------------------------------------------------------------------


def _parse_matcher(expr: str) -> tuple[str, str]:
    """Parse a simple ``key="value"`` or ``key=value`` matcher.

    The template config uses only equality matchers (no ``=~`` regex),
    so this intentionally stays narrow. If a future edit introduces
    regex matchers, this function must grow to match — failing loud
    here is better than silently mis-routing.
    """
    if "=~" in expr:
        raise NotImplementedError(
            f"regex matcher {expr!r} not supported by the simulator; "
            "if the template needs regex routing, extend this helper "
            "AND add a new test case."
        )
    key, _, value = expr.partition("=")
    key = key.strip()
    value = value.strip().strip('"').strip("'")
    return key, value


def _route_matches(route: dict, labels: dict[str, str]) -> bool:
    for m in route.get("matchers") or []:
        k, v = _parse_matcher(m)
        if labels.get(k) != v:
            return False
    # Legacy `match:` dict syntax (older alertmanager) — support in case
    # adopters copy the template into an older cluster.
    for k, v in (route.get("match") or {}).items():
        if labels.get(k) != v:
            return False
    return True


def _simulate_route(config: dict, labels: dict[str, str]) -> str:
    """Walk the routing tree top-down returning the chosen receiver."""
    root = config["route"]
    chosen = root["receiver"]
    for sub in root.get("routes") or []:
        if _route_matches(sub, labels):
            chosen = sub["receiver"]
            if not sub.get("continue"):
                break
    return chosen


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def config_path() -> Path:
    assert CONFIG.exists(), f"missing config: {CONFIG}"
    return CONFIG


@pytest.fixture(scope="module")
def parsed_config(config_path: Path) -> dict:
    return yaml.safe_load(config_path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def amtool_bin() -> str | None:
    """Resolve ``amtool`` from PATH or the sibling unpack dir.

    Returns ``None`` if amtool is not available; the test then runs
    in simulator-only mode and records an XFAIL-equivalent skip for
    the amtool-authoritative assertions (which still run as skips,
    not false passes).
    """
    on_path = shutil.which("amtool")
    if on_path:
        return on_path
    local = REPO_ROOT / "alertmanager-0.25.0.linux-amd64" / "amtool"
    if local.exists():
        return str(local)
    return None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "labels,expected,priority",
    ROUTING_MATRIX,
    ids=[row[2] for row in ROUTING_MATRIX],
)
def test_simulator_routes_alert(
    parsed_config: dict, labels: dict[str, str], expected: str, priority: str
) -> None:
    """Pure-Python simulator agrees with the expected receiver."""
    got = _simulate_route(parsed_config, labels)
    assert got == expected, (
        f"[{priority}] labels={labels} expected receiver={expected!r} "
        f"but simulator returned {got!r}. Either the config drifted or "
        "the simulator needs an update to match new matcher semantics."
    )


@pytest.mark.parametrize(
    "labels,expected,priority",
    ROUTING_MATRIX,
    ids=[row[2] for row in ROUTING_MATRIX],
)
def test_amtool_routes_alert(
    amtool_bin: str | None,
    config_path: Path,
    labels: dict[str, str],
    expected: str,
    priority: str,
) -> None:
    """Authoritative Alertmanager binary agrees with the expected receiver.

    Uses ``amtool config routes test`` which returns the receiver name
    on stdout. Skipped cleanly when amtool is not installed — the
    simulator test above still guards the contract.
    """
    if amtool_bin is None:
        pytest.skip("amtool not available; simulator test guards the contract.")
    args = [amtool_bin, "config", "routes", "test", f"--config.file={config_path}"]
    args += [f"{k}={v}" for k, v in labels.items()]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=15)
    assert proc.returncode == 0, (
        f"amtool exited {proc.returncode}: stdout={proc.stdout!r} "
        f"stderr={proc.stderr!r}"
    )
    got = proc.stdout.strip().splitlines()[-1].strip()
    assert got == expected, (
        f"[{priority}] amtool routed {labels} → {got!r}, expected {expected!r}. "
        "The authoritative Alertmanager parser disagrees with the template "
        "contract — fix the config or update ROUTING_MATRIX."
    )


def test_amtool_check_config_passes(amtool_bin: str | None, config_path: Path) -> None:
    """``amtool check-config`` validates the YAML against the real schema.

    Catches structural errors (misspelled keys, wrong types, undefined
    receivers) that the simulator would not notice.
    """
    if amtool_bin is None:
        pytest.skip("amtool not available")
    proc = subprocess.run(
        [amtool_bin, "check-config", str(config_path)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0, (
        f"amtool check-config failed: stdout={proc.stdout!r} "
        f"stderr={proc.stderr!r}"
    )
    assert "SUCCESS" in proc.stdout, (
        f"amtool check-config did not report SUCCESS: {proc.stdout!r}"
    )


def test_every_routed_receiver_is_defined(parsed_config: dict) -> None:
    """No route may reference a receiver that is not defined.

    A dangling receiver name is the most common mis-configuration and
    is NOT caught by the simulator (it returns the name verbatim). The
    amtool `check-config` test above catches it too, but we duplicate
    here so the contract holds even without amtool.
    """
    defined = {r["name"] for r in parsed_config["receivers"]}
    # Collect all receiver references (root + child routes).
    referenced: set[str] = {parsed_config["route"]["receiver"]}
    for sub in parsed_config["route"].get("routes") or []:
        referenced.add(sub["receiver"])
    missing = referenced - defined
    assert not missing, (
        f"routes reference undefined receivers: {sorted(missing)}. "
        "Either define them under `receivers:` or remove the route."
    )


def test_config_sibling_of_rules_file() -> None:
    """Operators should find routing and rules in the same directory.

    An adopter who greps for `alertmanager` in `templates/monitoring/`
    must see both files — splitting them across directories is a known
    trap for on-call handover.
    """
    assert CONFIG.parent == RULES.parent, (
        f"expected alertmanager.yml and alertmanager-rules.yaml in the "
        f"same directory; got {CONFIG.parent} vs {RULES.parent}"
    )


def test_inhibit_rule_suppresses_lower_severity(parsed_config: dict) -> None:
    """P1 must suppress P2/P3/P4 for the same service.

    A known failure mode: a pod restart storm fires `ServiceDown` (P1)
    and `HighLatency` (P2) simultaneously, paging on-call twice for
    the same root cause. The inhibit rule must suppress the P2.
    """
    rules = parsed_config.get("inhibit_rules") or []
    assert rules, "inhibit_rules missing; P1 storms will double-page"
    # Find the critical→warning|info rule.
    critical_rules = [
        r
        for r in rules
        if any('severity="critical"' in m for m in (r.get("source_matchers") or []))
    ]
    assert critical_rules, (
        "no inhibit rule with source severity=critical; adopters will "
        "get paged twice per service outage."
    )
    r = critical_rules[0]
    assert "service" in (r.get("equal") or []), (
        "inhibit rule must `equal: [service]` so it only suppresses the "
        "same service, not unrelated warnings cluster-wide."
    )
