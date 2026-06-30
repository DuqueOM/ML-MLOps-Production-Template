#!/usr/bin/env bash
# Health check script for deployed ML service
# Usage: ./scripts/health_check.sh --service bankchurn --namespace ml-services
set -euo pipefail

SERVICE="${1:?Usage: $0 <service-name> [namespace]}"
NAMESPACE="${2:-ml-services}"

echo "=== Health Check: ${SERVICE} in ${NAMESPACE} ==="

# Pod status
kubectl get pods -n "$NAMESPACE" -l "app=${SERVICE}" -o wide

# Health endpoint
POD=$(kubectl get pod -n "$NAMESPACE" -l "app=${SERVICE}" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [[ -n "$POD" ]]; then
  echo "--- /health ---"
  kubectl exec -n "$NAMESPACE" "$POD" -- curl -sf http://localhost:8000/health 2>/dev/null | python3 -m json.tool || echo "UNHEALTHY"
  echo "--- /model/info ---"
  kubectl exec -n "$NAMESPACE" "$POD" -- curl -sf http://localhost:8000/model/info 2>/dev/null | python3 -m json.tool || echo "N/A"
else
  echo "ERROR: No running pods found for ${SERVICE}"
  exit 1
fi
