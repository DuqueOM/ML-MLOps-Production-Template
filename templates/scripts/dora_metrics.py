#!/usr/bin/env python3
"""Compute DORA metrics from GitHub + ops/audit.jsonl data.

The four DORA metrics (deployment frequency, lead time for changes,
change failure rate, mean time to recovery) are lagging indicators of
software delivery performance. This script aggregates them from
observable primitives already emitted by the template:

  Deployment frequency   — successful deploy-prod jobs per week
  Lead time for changes  — PR merge → first prod deploy median
  Change failure rate    — rollback-tagged issues / total prod deploys
  MTTR                   — seconds between rollback trigger and incident close

Reads:
  - GitHub REST API for PR merge timestamps, deploy runs, issues
  - ops/audit.jsonl for the rollback signal (written by rollback skill)

Writes:
  - ops/dora/{YYYY-MM}-metrics.json for dashboards
  - stdout summary

Auth: the GitHub token is read from env (GITHUB_TOKEN). When absent,
the script degrades to ops/audit.jsonl only.

Usage:
  python scripts/dora_metrics.py --repo DuqueOM/ML-MLOps-Production-Template \\
      --since 2026-03-01 --output ops/dora/2026-04-metrics.json
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # allow ops/audit.jsonl-only mode


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _gh_get(url: str, token: str | None, params: dict | None = None) -> list[dict]:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if requests is None:
        return []
    out: list[dict] = []
    while url:
        r = requests.get(url, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            out.extend(data)
        else:  # paginated {items: [...]}
            out.extend(data.get("items", []))
        url = r.links.get("next", {}).get("url")
        params = None
    return out


def compute_deployment_frequency(deploy_runs: list[dict]) -> dict[str, Any]:
    """Successful prod deploys per 7-day window."""
    ts = [_parse_iso(r["created_at"]) for r in deploy_runs if r.get("conclusion") == "success"]
    if not ts:
        return {"count": 0, "per_week": 0.0, "by_week": {}}
    span = (max(ts) - min(ts)).days or 1
    weeks = max(1, span / 7)
    return {
        "count": len(ts),
        "per_week": round(len(ts) / weeks, 2),
        "earliest": _iso(min(ts)),
        "latest": _iso(max(ts)),
    }


def compute_lead_time(merged_prs: list[dict], deploy_runs: list[dict]) -> dict[str, Any]:
    """Median seconds from PR merge to the next successful prod deploy."""
    deploys = sorted(
        [_parse_iso(r["created_at"]) for r in deploy_runs if r.get("conclusion") == "success"]
    )
    if not deploys or not merged_prs:
        return {"median_seconds": None, "p95_seconds": None, "n": 0}
    deltas: list[float] = []
    for pr in merged_prs:
        merged_at_str = pr.get("merged_at")
        if not merged_at_str:
            continue
        merged = _parse_iso(merged_at_str)
        # First deploy AFTER this merge
        later = [d for d in deploys if d >= merged]
        if not later:
            continue
        deltas.append((later[0] - merged).total_seconds())
    if not deltas:
        return {"median_seconds": None, "p95_seconds": None, "n": 0}
    deltas.sort()
    return {
        "median_seconds": int(statistics.median(deltas)),
        "p95_seconds": int(deltas[int(0.95 * (len(deltas) - 1))]),
        "n": len(deltas),
    }


def compute_change_failure_rate(deploy_runs: list[dict], rollback_issues: list[dict]) -> dict[str, Any]:
    """Rollback-tagged issues / total prod deploys."""
    total = len([r for r in deploy_runs if r.get("conclusion") == "success"])
    failures = len(rollback_issues)
    rate = (failures / total) if total else None
    return {"total_deploys": total, "rollbacks": failures, "rate": rate}


def compute_mttr(audit_entries: list[dict]) -> dict[str, Any]:
    """Seconds between rollback start and incident close.

    Heuristic: match rollback operations to the NEXT audit entry with
    operation == 'incident_close'. Unmatched rollbacks are excluded.
    """
    rollbacks = [e for e in audit_entries if e.get("operation") == "rollback"]
    closes = [e for e in audit_entries if e.get("operation") == "incident_close"]
    if not rollbacks or not closes:
        return {"median_seconds": None, "n": 0}
    deltas: list[float] = []
    for rb in rollbacks:
        rb_ts = _parse_iso(rb["timestamp"])
        next_close = min(
            (_parse_iso(c["timestamp"]) for c in closes if _parse_iso(c["timestamp"]) >= rb_ts),
            default=None,
        )
        if next_close is not None:
            deltas.append((next_close - rb_ts).total_seconds())
    if not deltas:
        return {"median_seconds": None, "n": 0}
    deltas.sort()
    return {"median_seconds": int(statistics.median(deltas)), "n": len(deltas)}


def load_audit_entries(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=False, help="owner/repo — skipped if omitted")
    p.add_argument("--since", default=(datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat())
    p.add_argument("--output", default=None)
    p.add_argument("--audit-path", default="ops/audit.jsonl")
    args = p.parse_args()

    token = os.getenv("GITHUB_TOKEN")
    audit = load_audit_entries(Path(args.audit_path))

    deploy_runs: list[dict] = []
    merged_prs: list[dict] = []
    rollback_issues: list[dict] = []

    if args.repo and requests is not None:
        since = args.since
        deploy_runs = _gh_get(
            f"https://api.github.com/repos/{args.repo}/actions/runs",
            token,
            params={"created": f">{since}", "event": "push", "status": "completed", "per_page": 100},
        )
        deploy_runs = [r for r in deploy_runs if "deploy" in r.get("name", "").lower() and "prod" in r.get("name", "").lower()]
        merged_prs = _gh_get(
            f"https://api.github.com/repos/{args.repo}/pulls",
            token,
            params={"state": "closed", "sort": "updated", "direction": "desc", "per_page": 100},
        )
        merged_prs = [pr for pr in merged_prs if pr.get("merged_at") and pr["merged_at"] >= since]
        rollback_issues = _gh_get(
            f"https://api.github.com/search/issues",
            token,
            params={"q": f"repo:{args.repo} is:issue label:rollback created:>{since}"},
        )

    report = {
        "generated_at": _iso(datetime.now(timezone.utc)),
        "since": args.since,
        "deployment_frequency": compute_deployment_frequency(deploy_runs),
        "lead_time_for_changes": compute_lead_time(merged_prs, deploy_runs),
        "change_failure_rate": compute_change_failure_rate(deploy_runs, rollback_issues),
        "mttr": compute_mttr(audit),
    }

    print(json.dumps(report, indent=2))
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2))
        print(f"Wrote {out}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
