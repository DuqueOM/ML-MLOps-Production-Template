"""Contract tests for the Terraform bootstrap split (ADR-015 PR-A2).

The bootstrap layer creates the foundation resources (state bucket, KMS,
registry) that the live layer assumes already exist. These tests enforce
the structural contract:

1. **Both clouds have a bootstrap/ subdirectory** with main.tf
2. **Bootstrap uses LOCAL state** (no `backend` block in main.tf —
   chicken-and-egg with the very buckets it provisions)
3. **State bucket resource exists** in each bootstrap layer
4. **prevent_destroy is set** on foundation resources (a stray
   `terraform destroy` in bootstrap would orphan live state)
5. **README documents the workflow** including capture-outputs step
6. **.gitignore prevents committing local state files** (they contain
   resource IDs that should not be enumerable from the repo)

Pure-stdlib + regex; no `terraform plan` against real cloud required.
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


def _bootstrap_dir(cloud: str) -> Path:
    if TF_ROOT is None:
        pytest.skip("Terraform tree not found in this layout")
    d = TF_ROOT / cloud / "bootstrap"
    if not d.is_dir():
        pytest.skip(f"{d} not present (bootstrap may be optional in this layout)")
    return d


def _read_all_tf(directory: Path) -> str:
    return "\n".join(p.read_text() for p in sorted(directory.glob("*.tf")))


# ---------------------------------------------------------------------------
# Bootstrap directory exists and has the canonical files
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cloud", ["aws", "gcp"])
def test_bootstrap_directory_exists(cloud: str) -> None:
    """Each cloud has a bootstrap/ subdirectory with main.tf and variables.tf."""
    bootstrap = _bootstrap_dir(cloud)
    assert (bootstrap / "main.tf").is_file(), f"{cloud}/bootstrap/main.tf missing"
    assert (bootstrap / "variables.tf").is_file(), f"{cloud}/bootstrap/variables.tf missing"
    assert (bootstrap / "state.tf").is_file(), f"{cloud}/bootstrap/state.tf missing"


# ---------------------------------------------------------------------------
# Bootstrap uses LOCAL state (no backend block)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cloud", ["aws", "gcp"])
def test_bootstrap_uses_local_state(cloud: str) -> None:
    """Bootstrap MUST NOT declare a remote backend.

    Chicken-and-egg: the very state bucket is what we are creating here.
    A remote backend would fail on first init because the bucket does
    not exist yet.
    """
    bootstrap = _bootstrap_dir(cloud)
    main_tf = (bootstrap / "main.tf").read_text()

    # No `backend "..."` block. Strip comments first so the explanatory
    # comment about NOT having a backend doesn't false-positive.
    code_only = "\n".join(line for line in main_tf.splitlines() if not line.lstrip().startswith("#"))
    assert not re.search(r'backend\s+"\w+"\s*\{', code_only), (
        f"{cloud}/bootstrap/main.tf must NOT have a backend block " "(bootstrap uses local state by design — see PR-A2)"
    )


# ---------------------------------------------------------------------------
# State bucket resource exists with prevent_destroy
# ---------------------------------------------------------------------------


def test_gcp_bootstrap_creates_state_bucket() -> None:
    """GCP bootstrap creates a google_storage_bucket for live-layer state."""
    bootstrap = _bootstrap_dir("gcp")
    content = _read_all_tf(bootstrap)

    bucket_resource = re.search(
        r'resource\s+"google_storage_bucket"\s+"tfstate"\s*\{',
        content,
    )
    assert bucket_resource, "GCP bootstrap must define google_storage_bucket.tfstate"


def test_aws_bootstrap_creates_state_bucket_and_lock_table() -> None:
    """AWS bootstrap creates S3 bucket + DynamoDB lock table."""
    bootstrap = _bootstrap_dir("aws")
    content = _read_all_tf(bootstrap)

    s3 = re.search(r'resource\s+"aws_s3_bucket"\s+"tfstate"\s*\{', content)
    ddb = re.search(r'resource\s+"aws_dynamodb_table"\s+"tfstate_locks"\s*\{', content)
    assert s3, "AWS bootstrap must define aws_s3_bucket.tfstate"
    assert ddb, "AWS bootstrap must define aws_dynamodb_table.tfstate_locks (lock table)"


# ---------------------------------------------------------------------------
# Foundation resources have prevent_destroy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cloud", ["aws", "gcp"])
def test_state_bucket_has_prevent_destroy(cloud: str) -> None:
    """A stray `terraform destroy` in bootstrap would orphan live state.

    Foundation resources (state bucket, lock table, KMS key, registry) MUST
    declare `lifecycle { prevent_destroy = true }`.
    """
    bootstrap = _bootstrap_dir(cloud)
    state_tf = (bootstrap / "state.tf").read_text()

    assert (
        "prevent_destroy = true" in state_tf
    ), f"{cloud}/bootstrap/state.tf state bucket must declare prevent_destroy=true"


# ---------------------------------------------------------------------------
# Bootstrap exposes outputs the live layer needs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cloud", ["aws", "gcp"])
def test_bootstrap_exposes_state_bucket_output(cloud: str) -> None:
    """Operator must be able to copy the bucket name into backend-configs/<env>.hcl."""
    bootstrap = _bootstrap_dir(cloud)
    content = _read_all_tf(bootstrap)

    output_block = re.search(
        r'output\s+"tfstate_bucket"\s*\{',
        content,
    )
    assert output_block, f"{cloud}/bootstrap must expose `output.tfstate_bucket`"


# ---------------------------------------------------------------------------
# Local state files are gitignored
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cloud", ["aws", "gcp"])
def test_bootstrap_gitignores_local_state(cloud: str) -> None:
    """Local state files contain resource IDs and should never be committed."""
    bootstrap = _bootstrap_dir(cloud)
    gitignore = bootstrap / ".gitignore"
    assert gitignore.is_file(), f"{cloud}/bootstrap/.gitignore missing"

    content = gitignore.read_text()
    for required in ["terraform.tfstate", ".terraform/"]:
        assert required in content, f"{cloud}/bootstrap/.gitignore must include `{required}`"


# ---------------------------------------------------------------------------
# Top-level README documents the bootstrap workflow
# ---------------------------------------------------------------------------


def test_terraform_readme_documents_bootstrap() -> None:
    """templates/infra/terraform/README.md must explain the bootstrap-then-live flow."""
    if TF_ROOT is None:
        pytest.skip("Terraform tree not found in this layout")
    readme = TF_ROOT / "README.md"
    assert readme.is_file(), "templates/infra/terraform/README.md missing"

    content = readme.read_text().lower()
    for required in ["bootstrap", "live", "chicken-and-egg", "backend-configs"]:
        assert required in content, f"README must mention `{required}`"


# ---------------------------------------------------------------------------
# Bootstrap and live layers do NOT both create the same resource
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cloud", ["aws", "gcp"])
def test_no_resource_collision_between_bootstrap_and_live(cloud: str) -> None:
    """A resource name in both layers would race — only one can win.

    Specifically: state bucket / lock table / KMS keyring (GCP) lives in
    bootstrap. The live layer must not redeclare them.
    """
    if TF_ROOT is None:
        pytest.skip("Terraform tree not found")
    bootstrap = _bootstrap_dir(cloud)
    live_dir = TF_ROOT / cloud
    live_content = "\n".join(p.read_text() for p in live_dir.glob("*.tf") if p.is_file())

    if cloud == "gcp":
        # State bucket and KMS keyring are bootstrap-only.
        forbidden_in_live = [
            r'resource\s+"google_storage_bucket"\s+"tfstate"',
            r'resource\s+"google_kms_key_ring"\s+"main"',
        ]
    else:
        forbidden_in_live = [
            r'resource\s+"aws_s3_bucket"\s+"tfstate"',
            r'resource\s+"aws_dynamodb_table"\s+"tfstate_locks"',
        ]

    for pattern in forbidden_in_live:
        match = re.search(pattern, live_content)
        assert not match, (
            f"{cloud} live layer must not redeclare bootstrap resource " f"matching {pattern!r} (lifecycle conflict)"
        )

    # Sanity check the bootstrap actually does declare them.
    bs_content = _read_all_tf(bootstrap)
    sentinel = forbidden_in_live[0]
    assert re.search(sentinel, bs_content), f"{cloud}/bootstrap should declare {sentinel!r} (test fixture sanity check)"
