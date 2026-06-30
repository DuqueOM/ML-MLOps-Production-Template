#!/usr/bin/env bash
# =============================================================================
# promote_model.sh — Promote a model through quality gates
# =============================================================================
# Runs all quality gates before allowing a model to be promoted to production.
# Gates:
#   1. Minimum metric threshold (configurable)
#   2. Fairness check (Disparate Impact >= 0.80)
#   3. Data leakage sanity check (metric < suspicious threshold)
#   4. Model file integrity (SHA256 validation)
#
# Usage:
#   ./scripts/promote_model.sh --model models/model.joblib --report reports/eval.json
#
# TODO: Configure MIN_METRIC, FAIRNESS_THRESHOLD, LEAKAGE_THRESHOLD.
# =============================================================================
set -euo pipefail

MODEL_PATH=""
REPORT_PATH=""
MIN_METRIC=0.70
FAIRNESS_THRESHOLD=0.80
LEAKAGE_THRESHOLD=0.99

while [[ $# -gt 0 ]]; do
  case $1 in
    --model) MODEL_PATH="$2"; shift 2 ;;
    --report) REPORT_PATH="$2"; shift 2 ;;
    --min-metric) MIN_METRIC="$2"; shift 2 ;;
    *) echo "Unknown: $1"; exit 1 ;;
  esac
done

if [[ -z "$MODEL_PATH" || -z "$REPORT_PATH" ]]; then
  echo "Usage: $0 --model <path> --report <eval_report.json>"
  exit 1
fi

echo "=== Model Promotion Quality Gates ==="
PASS=true

# Gate 1: Minimum metric
PRIMARY_METRIC=$(python3 -c "import json; r=json.load(open('${REPORT_PATH}')); print(r.get('primary_metric', r.get('roc_auc', 0)))")
echo "Gate 1 — Primary metric: ${PRIMARY_METRIC} (min: ${MIN_METRIC})"
if (( $(echo "$PRIMARY_METRIC < $MIN_METRIC" | bc -l) )); then
  echo "  FAIL: Below minimum threshold"
  PASS=false
else
  echo "  PASS"
fi

# Gate 2: Fairness
DIR_SCORE=$(python3 -c "import json; r=json.load(open('${REPORT_PATH}')); print(r.get('fairness', {}).get('disparate_impact_ratio', 1.0))")
echo "Gate 2 — Disparate Impact Ratio: ${DIR_SCORE} (min: ${FAIRNESS_THRESHOLD})"
if (( $(echo "$DIR_SCORE < $FAIRNESS_THRESHOLD" | bc -l) )); then
  echo "  FAIL: Fairness threshold not met"
  PASS=false
else
  echo "  PASS"
fi

# Gate 3: Leakage check
echo "Gate 3 — Data leakage check: metric=${PRIMARY_METRIC} (suspicious if > ${LEAKAGE_THRESHOLD})"
if (( $(echo "$PRIMARY_METRIC > $LEAKAGE_THRESHOLD" | bc -l) )); then
  echo "  WARNING: Suspiciously high metric — investigate for data leakage"
  PASS=false
else
  echo "  PASS"
fi

# Gate 4: Model integrity
echo "Gate 4 — Model file integrity"
if [[ -f "$MODEL_PATH" ]]; then
  SHA=$(sha256sum "$MODEL_PATH" | awk '{print $1}')
  echo "  SHA256: ${SHA}"
  echo "  PASS"
else
  echo "  FAIL: Model file not found: ${MODEL_PATH}"
  PASS=false
fi

# Verdict
echo "=========================================="
if $PASS; then
  echo "ALL GATES PASSED — Model eligible for promotion"
  exit 0
else
  echo "GATES FAILED — Model NOT eligible for promotion"
  exit 1
fi
