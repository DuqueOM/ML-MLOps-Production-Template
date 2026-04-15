#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Build, push, and deploy ML service to Kubernetes
# =============================================================================
# Usage:
#   ./scripts/deploy.sh --service bankchurn --version v1.2.0 --cloud gcp
#   ./scripts/deploy.sh --service bankchurn --version v1.2.0 --cloud aws
#
# Prerequisites:
#   - Docker logged in to container registry
#   - kubectl context set to target cluster
#   - gcloud/aws CLI authenticated
#
# Safety:
#   - Verifies kubectl context before applying
#   - Never overwrites existing image tags (tags are immutable)
#   - Waits for rollout to complete with timeout
#
# TODO: Replace {PROJECT_ID}, {REGION}, {AWS_ACCOUNT_ID} with your values.
# =============================================================================
set -euo pipefail

# --- Configuration ---
SERVICE=""
VERSION=""
CLOUD="gcp"
NAMESPACE="ml-services"
TIMEOUT="300s"

# --- Parse arguments ---
while [[ $# -gt 0 ]]; do
  case $1 in
    --service) SERVICE="$2"; shift 2 ;;
    --version) VERSION="$2"; shift 2 ;;
    --cloud) CLOUD="$2"; shift 2 ;;
    --namespace) NAMESPACE="$2"; shift 2 ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

if [[ -z "$SERVICE" || -z "$VERSION" ]]; then
  echo "Usage: $0 --service <name> --version <tag> [--cloud gcp|aws]"
  exit 1
fi

# --- Verify kubectl context ---
CURRENT_CONTEXT=$(kubectl config current-context)
echo "=== kubectl context: ${CURRENT_CONTEXT} ==="
read -p "Deploy ${SERVICE}:${VERSION} to ${CLOUD}? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "Aborted."
  exit 0
fi

# --- Set registry based on cloud ---
if [[ "$CLOUD" == "gcp" ]]; then
  REGISTRY="{REGION}-docker.pkg.dev/{PROJECT_ID}/ml-images"
elif [[ "$CLOUD" == "aws" ]]; then
  REGISTRY="{AWS_ACCOUNT_ID}.dkr.ecr.{REGION}.amazonaws.com"
else
  echo "Error: --cloud must be gcp or aws"
  exit 1
fi

IMAGE="${REGISTRY}/${SERVICE}-predictor:${VERSION}"

# --- Check if image tag already exists (immutability) ---
echo "=== Checking image tag immutability ==="
if docker manifest inspect "$IMAGE" &>/dev/null 2>&1; then
  echo "ERROR: Image tag ${IMAGE} already exists. Tags are immutable."
  echo "Use a new version tag."
  exit 1
fi

# --- Build Docker image ---
echo "=== Building Docker image ==="
docker build \
  --platform linux/amd64 \
  -t "$IMAGE" \
  -f "Dockerfile" \
  .

# --- Push to registry ---
echo "=== Pushing to ${REGISTRY} ==="
docker push "$IMAGE"

# --- Apply Kustomize overlay ---
echo "=== Applying Kubernetes manifests ==="
OVERLAY_DIR="k8s/overlays/${CLOUD}-production"

if [[ ! -d "$OVERLAY_DIR" ]]; then
  echo "ERROR: Overlay directory not found: ${OVERLAY_DIR}"
  exit 1
fi

# Patch image tag in overlay
cd "$OVERLAY_DIR"
kustomize edit set image "${SERVICE}-predictor=${IMAGE}"
cd - > /dev/null

kustomize build "$OVERLAY_DIR" | kubectl apply -n "$NAMESPACE" -f -

# --- Wait for rollout ---
echo "=== Waiting for rollout (timeout: ${TIMEOUT}) ==="
kubectl rollout status deployment/"${SERVICE}-predictor" \
  -n "$NAMESPACE" \
  --timeout="$TIMEOUT"

# --- Verify deployment ---
echo "=== Deployment verification ==="
kubectl get pods -n "$NAMESPACE" -l "app=${SERVICE}" -o wide

# Health check
POD=$(kubectl get pod -n "$NAMESPACE" -l "app=${SERVICE}" -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n "$NAMESPACE" "$POD" -- curl -s http://localhost:8000/health | python3 -m json.tool

echo "=== Deploy complete: ${SERVICE}:${VERSION} on ${CLOUD} ==="
