#!/usr/bin/env bash
# Kyverno admission smoke test — proves the shipped ClusterPolicy
# actually REJECTS non-compliant Pods in a production-labeled
# namespace.
#
# Closes external-feedback gap 1.4 (May 2026 triage):
# the Kyverno policies in `templates/k8s/policies/` had NEVER been
# applied to a real cluster. This script spins up kind, installs
# Kyverno, applies the policy, and asserts the admission webhook
# rejects a `:latest` image — proving the policy is wired, not just
# designed.
#
# Scope of this smoke (and its explicit limits)
# ---------------------------------------------
#  IN scope:
#    - `require-image-digest` policy (pure-pattern match, no network).
#      Rejects any Pod in a `environment=production` / `staging`
#      namespace whose image reference is not pinned to @sha256.
#  OUT of scope:
#    - The `verify-image-signatures` rule requires network access to
#      Rekor + valid Cosign signatures. Proving it end-to-end in CI
#      requires a real signed image, which is covered by the
#      golden-path workflow (L3), not this smoke.
#
# Mode per AGENTS.md: AUTO (reversible — the kind cluster is torn
# down at the end). Safe to wire into CI.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
POLICY_FILE="${REPO_ROOT}/templates/k8s/policies/kyverno-image-verification.yaml"

CLUSTER_NAME="kyverno-smoke"
TEST_NS="test-prod"
KYVERNO_VERSION="${KYVERNO_VERSION:-3.2.6}"

log() { printf '==> %s\n' "$*" >&2; }
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

cleanup() {
  if command -v kind >/dev/null 2>&1; then
    kind delete cluster --name "${CLUSTER_NAME}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

command -v kind >/dev/null 2>&1 || fail "kind not installed"
command -v kubectl >/dev/null 2>&1 || fail "kubectl not installed"
command -v helm >/dev/null 2>&1 || fail "helm not installed"
[[ -f "${POLICY_FILE}" ]] || fail "policy file not found: ${POLICY_FILE}"

log "creating kind cluster: ${CLUSTER_NAME}"
kind create cluster --name "${CLUSTER_NAME}" --wait 120s

log "installing Kyverno ${KYVERNO_VERSION}"
helm repo add kyverno https://kyverno.github.io/kyverno/ >/dev/null
helm repo update >/dev/null
helm install kyverno kyverno/kyverno \
  --version "${KYVERNO_VERSION}" \
  --namespace kyverno \
  --create-namespace \
  --wait \
  --timeout 5m \
  --set admissionController.replicas=1

log "waiting for Kyverno webhook to register"
kubectl -n kyverno rollout status deploy/kyverno-admission-controller --timeout=180s

log "applying shipped ClusterPolicies"
# Replace {ORG}/{REPO} placeholders so the policy YAML parses even
# though the signature rule will not be exercised here (see header).
sed 's|{ORG}/{REPO}|DuqueOM/ML-MLOps-Production-Template|g' "${POLICY_FILE}" \
  | kubectl apply -f -

# Kyverno takes a few seconds to sync the policy into the webhook.
log "waiting for ClusterPolicies to be Ready"
for _ in {1..30}; do
  if kubectl get clusterpolicy require-image-digest -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null | grep -q True; then
    break
  fi
  sleep 2
done

log "creating production-labeled namespace: ${TEST_NS}"
kubectl create ns "${TEST_NS}" --dry-run=client -o yaml | kubectl apply -f -
kubectl label ns "${TEST_NS}" environment=production --overwrite

# ----------------------------------------------------------------------
# Assertion 1 — :latest MUST be rejected
# ----------------------------------------------------------------------
log "ASSERT: Pod with :latest tag should be REJECTED"
REJECT_OUTPUT=$(mktemp)
set +e
kubectl -n "${TEST_NS}" run reject-canary --image=nginx:latest --dry-run=server -o yaml 2>"${REJECT_OUTPUT}"
RC=$?
set -e

if [[ ${RC} -eq 0 ]]; then
  fail "Pod with :latest was ACCEPTED — Kyverno policy not enforcing digest pinning"
fi

if ! grep -q "pinned by digest" "${REJECT_OUTPUT}"; then
  cat "${REJECT_OUTPUT}" >&2
  fail "Pod was rejected but not for the expected reason (digest pinning)"
fi
log "PASS: :latest rejected with expected message"

# ----------------------------------------------------------------------
# Assertion 2 — image pinned by digest in a prod namespace MUST be
# accepted by the digest policy. (We use `--dry-run=server` so the
# Pod is not actually scheduled; Kyverno still evaluates it.)
#
# Note: this uses a public pinned digest for the busybox image. The
# signature rule may still block it since the image is NOT signed by
# our workflow identity, but the digest rule alone must PASS.
# ----------------------------------------------------------------------
log "ASSERT: Pod pinned by digest must not be rejected BY the digest rule"
DIGEST_OUTPUT=$(mktemp)
set +e
kubectl -n "${TEST_NS}" run accept-canary \
  --image='busybox@sha256:9ae97d36d26566ff84e8893c64a6dc4fe8ca6d1144bf5b87b2b85a32def253c7' \
  --dry-run=server -o yaml 2>"${DIGEST_OUTPUT}"
RC=$?
set -e

# The digest rule is `require-image-digest` — we ONLY care that if a
# rejection happens, it is NOT from that rule. The signature rule
# (`check-image-signature`) may still reject, which is expected in
# offline CI. So: if the pod is rejected AND the message contains
# "pinned by digest", this smoke fails. Any other rejection reason
# is acceptable at this layer.
if [[ ${RC} -ne 0 ]] && grep -q "pinned by digest" "${DIGEST_OUTPUT}"; then
  cat "${DIGEST_OUTPUT}" >&2
  fail "Digest-pinned image was rejected by the digest rule — policy is mis-matching"
fi
log "PASS: digest-pinned image not rejected by the digest rule"

log "all assertions passed — Kyverno admission smoke GREEN"
