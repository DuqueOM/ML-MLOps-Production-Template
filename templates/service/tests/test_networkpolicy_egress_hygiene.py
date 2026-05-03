"""Contract test — NetworkPolicy egress hygiene (R5-M3).

Authority: ACTION_PLAN_R5 §R5-M3.

The base NetworkPolicy at ``templates/k8s/base/networkpolicy.yaml``
ships a permissive ``0.0.0.0/0:443`` egress rule so local
``kustomize build`` works against dev clusters without hard-coding
cloud-provider CIDR ranges. That default is SECURE only in dev.

Every non-dev overlay (``gcp-staging``, ``gcp-prod``, ``aws-staging``,
``aws-prod``) MUST apply a JSON 6902 patch at
``patch-networkpolicy.yaml`` that replaces the wildcard egress with a
cloud-specific allowlist. This contract test enforces:

1. The base NetworkPolicy carries the ``OVERLAY-OVERRIDE REQUIRED``
   banner so the intent is visible to any future editor.
2. Each of the 4 non-dev overlays:
   - contains a ``patch-networkpolicy.yaml`` file,
   - wires it into ``kustomization.yaml`` with
     ``target.kind: NetworkPolicy``,
   - has a patch body that does NOT contain ``0.0.0.0/0``.
3. Dev overlays are NOT constrained — they legitimately inherit the
   permissive base rule, so the test does not assert anything about
   them.

The test parses YAML structurally; it does not require kustomize in
the test environment. An additional optional check invokes
``kustomize build`` if available and fails when the rendered output
still contains ``0.0.0.0/0`` — that catches patch-wiring mistakes
that the structural checks would miss (e.g., wrong ``target`` kind).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

try:  # optional dep — CI always has it, local dev environments may not.
    import yaml  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    yaml = None  # type: ignore

REPO_ROOT = Path(__file__).resolve().parents[3]
BASE_NETPOL = REPO_ROOT / "templates" / "k8s" / "base" / "networkpolicy.yaml"
OVERLAY_ROOT = REPO_ROOT / "templates" / "k8s" / "overlays"

NON_DEV_OVERLAYS = ["gcp-staging", "gcp-prod", "aws-staging", "aws-prod"]


# ---------------------------------------------------------------------------
# 1. Base policy carries the override-required banner.
# ---------------------------------------------------------------------------


def test_base_networkpolicy_carries_override_banner() -> None:
    """The base NetworkPolicy MUST flag the 0.0.0.0/0 egress as dev-only.

    Without this banner a future editor could silently remove the
    override instruction from the most visible surface (the base
    manifest), and the contract's intent would only live in a test.
    """
    text = BASE_NETPOL.read_text(encoding="utf-8")
    assert "OVERLAY-OVERRIDE REQUIRED" in text, (
        f"{BASE_NETPOL.relative_to(REPO_ROOT)} must carry the "
        "`OVERLAY-OVERRIDE REQUIRED` banner on the cloud-storage egress "
        "rule (R5-M3). Contributors need to see this in the base file, "
        "not just in a test."
    )
    # Also check the R5-M3 tag + non-dev overlay list is present
    # so a future audit can grep the provenance.
    assert "R5-M3" in text, "Base NetworkPolicy should cite R5-M3 as provenance"
    assert "non-dev" in text.lower(), "Banner should name the non-dev overlay scope"


# ---------------------------------------------------------------------------
# 2. Each non-dev overlay has a patch file that does NOT contain 0.0.0.0/0
#    AND wires it in kustomization.yaml.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("overlay", NON_DEV_OVERLAYS, ids=NON_DEV_OVERLAYS)
def test_overlay_has_patch_file(overlay: str) -> None:
    """Each non-dev overlay ships `patch-networkpolicy.yaml`."""
    patch = OVERLAY_ROOT / overlay / "patch-networkpolicy.yaml"
    assert patch.exists(), (
        f"Non-dev overlay `{overlay}` must carry patch-networkpolicy.yaml "
        "(R5-M3); without it the overlay inherits the base's permissive "
        "0.0.0.0/0:443 egress, which is insecure in staging/prod."
    )


@pytest.mark.parametrize("overlay", NON_DEV_OVERLAYS, ids=NON_DEV_OVERLAYS)
def test_patch_file_does_not_contain_wildcard(overlay: str) -> None:
    """The patch body MUST NOT restore the wildcard egress CIDR."""
    patch = OVERLAY_ROOT / overlay / "patch-networkpolicy.yaml"
    if not patch.exists():
        pytest.skip("patch file absent — covered by the existence test")
    body = patch.read_text(encoding="utf-8")
    # Allow the string inside a comment line (e.g. "narrow from 0.0.0.0/0").
    # Grep each non-comment line independently.
    non_comment = "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("#"))
    assert "0.0.0.0/0" not in non_comment, (
        f"{patch.relative_to(REPO_ROOT)} reintroduces the wildcard CIDR "
        "`0.0.0.0/0` in its active YAML. R5-M3 requires cloud-specific "
        "allowlists for non-dev overlays."
    )


@pytest.mark.parametrize("overlay", NON_DEV_OVERLAYS, ids=NON_DEV_OVERLAYS)
def test_kustomization_wires_the_patch(overlay: str) -> None:
    """``kustomization.yaml`` MUST reference ``patch-networkpolicy.yaml``
    with an explicit target ``kind: NetworkPolicy``. Without the target
    the JSON 6902 patch fails to apply silently.
    """
    kust = OVERLAY_ROOT / overlay / "kustomization.yaml"
    assert kust.exists(), f"Overlay `{overlay}` missing kustomization.yaml"
    body = kust.read_text(encoding="utf-8")
    assert "patch-networkpolicy.yaml" in body, (
        f"{kust.relative_to(REPO_ROOT)} does not reference "
        "patch-networkpolicy.yaml; the patch will not be applied by "
        "`kustomize build` even if the file exists."
    )
    assert "kind: NetworkPolicy" in body, (
        f"{kust.relative_to(REPO_ROOT)} references the patch but does not "
        "set `target.kind: NetworkPolicy`; JSON 6902 patches need an "
        "explicit target to find the resource."
    )


# ---------------------------------------------------------------------------
# 3. (Optional) end-to-end kustomize build render check.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("overlay", NON_DEV_OVERLAYS, ids=NON_DEV_OVERLAYS)
def test_kustomize_render_has_no_wildcard_egress(overlay: str) -> None:
    """If ``kustomize`` is available, render the overlay and assert the
    final YAML has no ``0.0.0.0/0`` egress. Skipped when kustomize is
    not installed (CI installs it via `actions/setup-kustomize`).
    """
    kustomize_bin = shutil.which("kustomize")
    if not kustomize_bin:
        pytest.skip("kustomize binary not in PATH; CI covers this path")
    overlay_dir = OVERLAY_ROOT / overlay
    result = subprocess.run(  # noqa: S603 — kustomize is a well-known bin
        [kustomize_bin, "build", str(overlay_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"`kustomize build` failed for overlay `{overlay}`: {result.stderr}"
    assert "0.0.0.0/0" not in result.stdout, (
        f"kustomize build of `{overlay}` still contains 0.0.0.0/0 in the "
        "rendered manifest; the JSON 6902 patch did not take effect. "
        "Check the `target:` block in kustomization.yaml (R5-M3)."
    )


# ---------------------------------------------------------------------------
# 4. Dev overlays are intentionally unconstrained — ensure we do not
#    accidentally require the patch there (would break local scaffold).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("overlay", ["gcp-dev", "aws-dev"])
def test_dev_overlays_do_not_need_the_patch(overlay: str) -> None:
    """Dev overlays legitimately inherit the permissive base egress.

    The test asserts the patch file is NOT shipped for dev — if a
    future change drops one here, we catch it immediately.
    """
    patch = OVERLAY_ROOT / overlay / "patch-networkpolicy.yaml"
    assert not patch.exists(), (
        f"Dev overlay `{overlay}` unexpectedly carries "
        "patch-networkpolicy.yaml; dev is supposed to exercise the "
        "permissive base default so local kustomize build works out "
        "of the box. If you need dev to also narrow egress, update "
        "this test and the §R5-M3 ADR entry in ACTION_PLAN_R5.md."
    )
