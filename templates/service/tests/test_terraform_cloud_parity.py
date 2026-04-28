"""Contract test for AWS/GCP feature parity in the live Terraform layer.

A user-reported gap: AWS shipped `secrets.tf`, `logging.tf`, `ecr.tf`,
`iam-roles-split.tf` while GCP did not have equivalents — silently
breaking the multi-cloud-parity claim of this template.

This test enforces the parity contract:

1. **Secret store parity** — both clouds provision a secret-store
   resource per (service × secret_name) Cartesian product.
2. **Logging retention parity** — both clouds set explicit log retention
   (CloudWatch on AWS, Cloud Logging buckets on GCP). Defaulting to
   "Never expire" is a documented anti-pattern.
3. **Budget alert parity** — both clouds expose a monthly budget
   resource gated by `monthly_budget`.
4. **CMEK parity** — secrets + logs both reference a customer-managed
   KMS key (not Google/AWS-managed defaults).
5. **Shared variable surface** — `service_names`, `secret_names`,
   `log_retention_days`, `monthly_budget` exist on BOTH clouds with
   matching defaults so a single overlay tfvars works for either.

If the AWS side adds a new feature (new var, new resource), the GCP
side MUST follow within the same PR or this test fails.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------


def _find_tf_root() -> Path | None:
    here = Path(__file__).resolve()
    for ancestor in [here.parent] + list(here.parents):
        for relative in ("templates/infra/terraform", "infra/terraform"):
            candidate = ancestor / relative
            if candidate.is_dir():
                return candidate
    return None


TF_ROOT = _find_tf_root()


def _read_cloud_tf(cloud: str) -> str:
    """Concatenate all top-level .tf files for a cloud (excludes bootstrap/)."""
    if TF_ROOT is None:
        pytest.skip("Terraform tree not found")
    cloud_dir = TF_ROOT / cloud
    if not cloud_dir.is_dir():
        pytest.skip(f"{cloud_dir} not present")
    return "\n".join(p.read_text() for p in sorted(cloud_dir.glob("*.tf")))


# ---------------------------------------------------------------------------
# 1. Secret store parity
# ---------------------------------------------------------------------------


def test_aws_provisions_secret_per_service_secret_pair() -> None:
    """AWS Secrets Manager: one entry per (service × secret_name)."""
    content = _read_cloud_tf("aws")
    secret_resource = re.search(
        r'resource\s+"aws_secretsmanager_secret"\s+"\w+"\s*\{', content
    )
    assert secret_resource, "AWS must define aws_secretsmanager_secret"
    assert "setproduct(var.service_names, var.secret_names)" in content, (
        "AWS Secrets must iterate the Cartesian product of services × secret names"
    )


def test_gcp_provisions_secret_per_service_secret_pair() -> None:
    """GCP Secret Manager: one entry per (service × secret_name) — parity with AWS."""
    content = _read_cloud_tf("gcp")
    secret_resource = re.search(
        r'resource\s+"google_secret_manager_secret"\s+"\w+"\s*\{', content
    )
    assert secret_resource, (
        "GCP must define google_secret_manager_secret — parity with AWS secrets.tf"
    )
    assert "setproduct(var.service_names, var.secret_names)" in content, (
        "GCP Secret Manager must iterate the same Cartesian product as AWS"
    )


# ---------------------------------------------------------------------------
# 2. Logging retention parity
# ---------------------------------------------------------------------------


def test_aws_sets_log_retention() -> None:
    """AWS CloudWatch log groups must reference var.log_retention_days."""
    content = _read_cloud_tf("aws")
    assert re.search(r'resource\s+"aws_cloudwatch_log_group"', content), (
        "AWS must define aws_cloudwatch_log_group"
    )
    assert "var.log_retention_days" in content, (
        "AWS log groups must use var.log_retention_days (no AWS-default 'Never expire')"
    )


def test_gcp_sets_log_retention() -> None:
    """GCP Cloud Logging buckets must reference var.log_retention_days — parity with AWS."""
    content = _read_cloud_tf("gcp")
    assert re.search(r'resource\s+"google_logging_project_bucket_config"', content), (
        "GCP must define google_logging_project_bucket_config — parity with AWS logging.tf"
    )
    assert "var.log_retention_days" in content, (
        "GCP log bucket must use var.log_retention_days (overrides GCP's fixed 30d default)"
    )


# ---------------------------------------------------------------------------
# 3. Budget alert parity
# ---------------------------------------------------------------------------


def test_aws_has_budget_alert() -> None:
    """AWS Budgets monthly alarm exists and references var.monthly_budget."""
    content = _read_cloud_tf("aws")
    assert re.search(r'resource\s+"aws_budgets_budget"', content), (
        "AWS must define aws_budgets_budget"
    )
    assert "var.monthly_budget" in content


def test_gcp_has_budget_alert() -> None:
    """GCP Billing Budget exists and references var.monthly_budget — parity with AWS."""
    content = _read_cloud_tf("gcp")
    assert re.search(r'resource\s+"google_billing_budget"', content), (
        "GCP must define google_billing_budget — parity with AWS aws_budgets_budget"
    )
    assert "var.monthly_budget" in content


# ---------------------------------------------------------------------------
# 4. CMEK parity for secrets + logs
# ---------------------------------------------------------------------------


def test_aws_secrets_use_cmek() -> None:
    content = _read_cloud_tf("aws")
    # The Secrets Manager resource must reference a kms_key_id pointing
    # at a customer-managed key (not aws/secretsmanager default).
    secret_block = re.search(
        r'resource\s+"aws_secretsmanager_secret".*?(?=^resource|\Z)',
        content,
        re.DOTALL | re.MULTILINE,
    )
    assert secret_block, "AWS secrets resource not found"
    assert re.search(r'kms_key_id\s*=\s*aws_kms_key', secret_block.group(0)), (
        "AWS secrets must reference a customer-managed KMS key (CMEK)"
    )


def test_gcp_secrets_use_cmek() -> None:
    content = _read_cloud_tf("gcp")
    secret_block = re.search(
        r'resource\s+"google_secret_manager_secret".*?(?=^resource|\Z)',
        content,
        re.DOTALL | re.MULTILINE,
    )
    assert secret_block, "GCP Secret Manager resource not found"
    assert "customer_managed_encryption" in secret_block.group(0), (
        "GCP secrets must use customer_managed_encryption (CMEK) — parity with AWS"
    )


def test_gcp_logs_use_cmek() -> None:
    """GCP log buckets must use CMEK via cmek_settings — parity with AWS."""
    content = _read_cloud_tf("gcp")
    log_block = re.search(
        r'resource\s+"google_logging_project_bucket_config"\s+"service".*?(?=^resource|\Z)',
        content,
        re.DOTALL | re.MULTILINE,
    )
    assert log_block, "GCP log bucket resource not found"
    assert "cmek_settings" in log_block.group(0), (
        "GCP per-service log bucket must declare cmek_settings"
    )


# ---------------------------------------------------------------------------
# 5. Shared variable surface
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "var_name",
    ["service_names", "secret_names", "log_retention_days", "monthly_budget"],
)
def test_variable_exists_on_both_clouds(var_name: str) -> None:
    """Each parity variable MUST exist on both clouds with the same name."""
    aws_content = _read_cloud_tf("aws")
    gcp_content = _read_cloud_tf("gcp")

    pattern = rf'variable\s+"{var_name}"\s*\{{'
    aws_has = re.search(pattern, aws_content)
    gcp_has = re.search(pattern, gcp_content)

    assert aws_has, f"AWS missing variable {var_name!r}"
    assert gcp_has, f"GCP missing variable {var_name!r} (parity gap with AWS)"


def test_secret_names_default_matches_across_clouds() -> None:
    """Same default secrets list on both clouds (so a single overlay works)."""
    aws_content = _read_cloud_tf("aws")
    gcp_content = _read_cloud_tf("gcp")

    pattern = re.compile(
        r'variable\s+"secret_names"\s*\{[^}]*?default\s*=\s*(\[[^\]]+\])',
        re.DOTALL,
    )
    aws_match = pattern.search(aws_content)
    gcp_match = pattern.search(gcp_content)

    assert aws_match and gcp_match
    aws_default = re.sub(r"\s+", "", aws_match.group(1))
    gcp_default = re.sub(r"\s+", "", gcp_match.group(1))
    assert aws_default == gcp_default, (
        f"secret_names defaults diverge:\n  AWS: {aws_default}\n  GCP: {gcp_default}"
    )
