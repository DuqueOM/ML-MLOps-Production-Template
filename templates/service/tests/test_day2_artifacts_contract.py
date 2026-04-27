"""PR-A4 — Day-2 ops artifacts contract.

Two artifacts ship under PR-A4:

  1. ``docs/runbooks/day-2-operations.md`` — the single multi-cloud
     Day-2 ops runbook. ADR-015's rejected-items table explicitly
     refused the two-runbook split (`CHECKLIST_DAY2_GCP.md` +
     `CHECKLIST_DAY2_AWS.md`); this file IS the canonical alternative.

  2. ``.github/workflows/terraform-plan-nightly.yml`` (in the
     scaffolded service) / ``cicd/terraform-plan-nightly.yml`` (in
     the template repo) — the nightly drift-detection workflow.

This test asserts both artifacts are present and carry the load-
bearing structural elements they're meant to. It is YAML/Markdown
only — no terraform, no kubectl, no GitHub API.

Why a structural test (instead of a "does it work" test): the
correctness of `terraform plan` is owned by HashiCorp, and the
correctness of every bash snippet in the runbook is owned by the
operator running it. What the TEMPLATE owes is the *contract*:
both artifacts exist, both cover the agreed topics, neither has
silently lost a section due to a careless edit. This is the same
philosophy as PR-C2 (alert routing) and PR-A5b (placeholder
vocabulary): structural gates that prevent regression.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml


def _candidate_paths(rel: str) -> list[Path]:
    """Resolve ``rel`` against both layout candidates (scaffolded
    service root + template repo). Same convention as PR-C2 / A5b."""
    here = Path(__file__).resolve()
    return [prefix / rel for prefix in (here.parents[1], here.parents[2], here.parents[2] / "templates")]


def _find_one(candidates: list[Path]) -> Path | None:
    for p in candidates:
        if p.is_file():
            return p
    return None


# ---------------------------------------------------------------------------
# Day-2 runbook
# ---------------------------------------------------------------------------

REQUIRED_RUNBOOK_SECTIONS = (
    "Universal preflight",
    "scale a deployment",
    "drain a node",
    "certificate rotation",
    "secret rotation",
    "cost spike triage",
    "terraform drift check",
    "backup verification",
    "model rollback",
)

# Both clouds MUST be tagged (the rejected-items table mandates a
# single multi-cloud file, which is meaningful only if both clouds
# actually appear in it).
REQUIRED_CLOUD_TAGS = ("**GCP**", "**AWS**")


def _runbook_path() -> Path:
    candidates = _candidate_paths("docs/runbooks/day-2-operations.md")
    found = _find_one(candidates)
    if found is None:
        pytest.fail("day-2-operations.md not found at any of:\n  - " + "\n  - ".join(str(c) for c in candidates))
    return found


def test_day2_runbook_exists_and_has_required_sections() -> None:
    text = _runbook_path().read_text(encoding="utf-8")
    missing = [s for s in REQUIRED_RUNBOOK_SECTIONS if s.lower() not in text.lower()]
    assert not missing, "day-2-operations.md missing required sections (PR-A4 contract):\n  - " + "\n  - ".join(missing)


def test_day2_runbook_covers_both_clouds() -> None:
    text = _runbook_path().read_text(encoding="utf-8")
    missing = [tag for tag in REQUIRED_CLOUD_TAGS if tag not in text]
    assert not missing, (
        "day-2-operations.md must cover both clouds (the single-runbook "
        "design is the rejected-items rationale; not having both clouds "
        "tagged means the design intent has been lost):\n  - " + "\n  - ".join(missing)
    )


def test_day2_runbook_uses_kebab_for_k8s_names() -> None:
    """A K8s name in a runbook command MUST use ``{service-name}``
    (kebab) per PR-A5b. A snake `{service}` here would break copy-
    pasted commands at deploy time on snake_case slugs.
    """
    text = _runbook_path().read_text(encoding="utf-8")
    bad: list[tuple[int, str]] = []
    # Match `kubectl ... {service}` patterns where {service} is in a
    # K8s name position (preceding/trailing kebab chars).
    rx = re.compile(r"\{service\}-[a-z]|kubectl[^\n]*\{service\}\b")
    for n, line in enumerate(text.splitlines(), 1):
        if rx.search(line):
            # Allow one explicit Prometheus query line that documents
            # the snake-case rationale by carrying both `{service}` and
            # the words "Prometheus" or "snake-case".
            if "Prometheus" in line or "snake-case" in line.lower():
                continue
            bad.append((n, line.strip()))
    assert not bad, (
        "day-2-operations.md uses `{service}` (snake) in a K8s-name "
        "context (must be `{service-name}` kebab per PR-A5b):\n" + "\n".join(f"  L{n}: {ln}" for n, ln in bad)
    )


# ---------------------------------------------------------------------------
# Nightly terraform-plan workflow
# ---------------------------------------------------------------------------


def _workflow_path() -> Path:
    # In the scaffolded layout new-service.sh copies cicd/*.yml into
    # .github/workflows/, so the workflow lives there. In the template
    # repo it lives under templates/cicd/.
    here = Path(__file__).resolve()
    candidates = [
        here.parents[1] / ".github" / "workflows" / "terraform-plan-nightly.yml",
        here.parents[2] / "cicd" / "terraform-plan-nightly.yml",
        here.parents[2] / "templates" / "cicd" / "terraform-plan-nightly.yml",
    ]
    found = _find_one(candidates)
    if found is None:
        pytest.fail("terraform-plan-nightly.yml not found at any of:\n  - " + "\n  - ".join(str(c) for c in candidates))
    return found


def test_workflow_exists_and_parses() -> None:
    yaml.safe_load(_workflow_path().read_text(encoding="utf-8"))


def test_workflow_has_schedule_trigger() -> None:
    """A "nightly" workflow that lacks ``on.schedule`` is just a
    workflow_dispatch, not a drift detector."""
    raw = _workflow_path().read_text(encoding="utf-8")
    doc = yaml.safe_load(raw)
    triggers = doc.get(True) or doc.get("on") or {}
    # PyYAML parses bare `on:` as the boolean True. Either form is fine.
    assert isinstance(triggers, dict), f"unexpected `on:` shape: {type(triggers)}"
    assert "schedule" in triggers, (
        "terraform-plan-nightly.yml has no `on.schedule` — a nightly "
        "drift check must run on a schedule, not just on-demand."
    )
    schedule = triggers["schedule"]
    assert isinstance(schedule, list) and schedule, "schedule list is empty"
    crons = [s.get("cron") for s in schedule if isinstance(s, dict)]
    assert any(crons), "no cron expression in schedule entries"


def test_workflow_runs_plan_only_never_apply() -> None:
    """Hard contract: the nightly workflow uses ``plan`` only.
    ``apply`` here would defeat the gate ADR-015 codifies (apply is
    CONSULT in staging and STOP in prod)."""
    raw = _workflow_path().read_text(encoding="utf-8")
    # Match the literal `terraform apply` shell invocation; ignore
    # comment mentions (those are explanatory).
    apply_lines = [
        (n, line.rstrip())
        for n, line in enumerate(raw.splitlines(), 1)
        if re.search(r"^\s*[^#].*\bterraform\s+apply\b", line)
    ]
    assert not apply_lines, (
        "terraform-plan-nightly.yml contains a non-comment "
        "`terraform apply` invocation. Apply is CONSULT/STOP per "
        "ADR-015 and never belongs in a scheduled workflow:\n" + "\n".join(f"  L{n}: {ln}" for n, ln in apply_lines)
    )


def test_workflow_covers_both_clouds() -> None:
    raw = _workflow_path().read_text(encoding="utf-8")
    doc = yaml.safe_load(raw)
    jobs = doc.get("jobs") or {}
    job_names = set(jobs.keys())
    expected = {"plan-gcp", "plan-aws"}
    missing = expected - job_names
    assert not missing, (
        f"terraform-plan-nightly.yml missing per-cloud jobs: {sorted(missing)}\n"
        f"present: {sorted(job_names)}\n"
        "The single-workflow + two-job design is intentional (one per "
        "cloud, one state lock per job). Removing a cloud here means "
        "drift in that cloud is undetected."
    )


def test_workflow_uses_oidc_not_static_credentials() -> None:
    """D-18 invariant: cloud-native credential delegation only.
    Static `AWS_ACCESS_KEY_ID` / `GOOGLE_APPLICATION_CREDENTIALS_JSON`
    in this workflow would directly violate the security memory."""
    raw = _workflow_path().read_text(encoding="utf-8")
    forbidden = (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS_JSON",
        "GCP_SA_KEY",  # canonical name for a long-lived JSON key secret
    )
    bad = [k for k in forbidden if k in raw]
    assert not bad, (
        f"terraform-plan-nightly.yml references static-credential "
        f"secret names: {bad}\n"
        "D-18 mandates IRSA (AWS) / Workload Identity Federation (GCP). "
        "Use `secrets.AWS_ROLE_ARN` + `aws-actions/configure-aws-credentials@v4` "
        "and `secrets.GCP_WIF_PROVIDER` + `google-github-actions/auth@v2`."
    )


def test_workflow_opens_issue_on_drift() -> None:
    """The point of detecting drift is acting on it. A workflow that
    silently returns non-zero without surfacing what drifted just
    teaches operators to ignore the red X.
    """
    raw = _workflow_path().read_text(encoding="utf-8")
    assert "infra-drift" in raw, (
        "terraform-plan-nightly.yml does not appear to open a tagged "
        "issue on drift. Expected an `actions/github-script@v7` step "
        "creating an issue with label `infra-drift`."
    )


def test_workflow_records_audit_entry() -> None:
    """ADR-014 §3.5 requires every agentic operation to emit an
    AuditEntry. The nightly drift check is one such operation."""
    raw = _workflow_path().read_text(encoding="utf-8")
    assert "audit_record.py" in raw, (
        "terraform-plan-nightly.yml does not invoke "
        "`scripts/audit_record.py`. Without this, the per-day drift "
        "verdict never reaches `ops/audit.jsonl` (ADR-014 §3.5)."
    )


def test_audit_record_cli_actually_works_with_workflow_args(
    tmp_path: pytest.TempPathFactory,
) -> None:
    """Smoke test: invoke `audit_record.py` with the EXACT argument
    shape the new workflow uses, against a tmp ``ops/audit.jsonl``,
    and assert (a) exit 0, (b) one new JSONL line, (c) it parses with
    the expected fields.

    This closes a loop the structural test
    ``test_workflow_records_audit_entry`` deliberately does NOT close
    — that one only asserts the YAML CONTAINS the invocation. If the
    CLI's argument grammar regressed (e.g. ``--final-mode`` renamed
    to ``--effective-mode``), the structural test would still pass
    while the workflow would fail every night until a human noticed.
    """
    import subprocess
    import sys

    # Locate audit_record.py. Same dual-layout convention as elsewhere:
    # in scaffolded service it lives at scripts/audit_record.py
    # (copied by new-service.sh); in template repo it lives at
    # /repo-root/scripts/audit_record.py.
    here = Path(__file__).resolve()
    candidates = [
        here.parents[1] / "scripts" / "audit_record.py",
        here.parents[2] / "scripts" / "audit_record.py",
        here.parents[3] / "scripts" / "audit_record.py",
    ]
    cli = next((p for p in candidates if p.is_file()), None)
    if cli is None:
        pytest.skip("audit_record.py not present in any candidate path; " "skipping smoke test")

    # Find common_utils so audit_record can import it. Same dual-layout
    # logic as the drills test.
    extra_path = None
    for prefix in (here.parents[1], here.parents[2], here.parents[3]):
        if (prefix / "common_utils").is_dir():
            extra_path = str(prefix)
            break
        if (prefix / "templates" / "common_utils").is_dir():
            extra_path = str(prefix / "templates")
            break

    env = {
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": extra_path or "",
        "HOME": str(tmp_path),
    }

    # Mirror the workflow's invocation verbatim — same agent name,
    # same operation slug, same JSON shape on inputs/outputs.
    audit_dir = tmp_path / "ops"
    audit_dir.mkdir()
    proc = subprocess.run(
        [
            sys.executable,
            str(cli),
            "--agent",
            "terraform-plan-nightly",
            "--operation",
            "infra_drift_check",
            "--environment",
            "dev",
            "--base-mode",
            "AUTO",
            "--final-mode",
            "AUTO",
            "--result",
            "success",
            "--inputs",
            '{"trigger":"schedule","cloud":"both"}',
            "--outputs",
            '{"gcp":"success","aws":"success","run_url":"https://example/run/1"}',
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, (
        f"audit_record.py exited {proc.returncode} with workflow args. "
        f"stderr:\n{proc.stderr}\nstdout:\n{proc.stdout}"
    )

    audit_log = audit_dir / "audit.jsonl"
    assert audit_log.is_file(), (
        f"audit_record.py exited 0 but ops/audit.jsonl was not created. "
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    lines = [ln for ln in audit_log.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1, f"expected 1 audit line, got {len(lines)}"

    import json

    entry = json.loads(lines[0])
    # Field names the workflow's --outputs depends on existing on the
    # downstream side of the ledger. If `agent` becomes `agent_name`
    # one day, the workflow's audit step will silently misroute.
    assert entry.get("agent") == "terraform-plan-nightly"
    assert entry.get("operation") == "infra_drift_check"
    assert entry.get("environment") == "dev"
    assert entry.get("result") == "success"
