# Runbook: {ServiceName}

## Service Overview

- **Service**: {ServiceName}
- **Model**: {Model type}
- **SLA**: P95 < {X}ms, availability 99.9%
- **On-call**: {team/contact}

## P1 — Service Down (15 min SLA)

### Symptoms
- Error rate > 5%
- Health endpoint returning non-200
- Pods in CrashLoopBackOff

### Immediate Actions

```bash
# 1. Rollback to previous version
kubectl rollout undo deployment/{service}-predictor -n {namespace}
kubectl rollout status deployment/{service}-predictor -n {namespace}

# 2. Verify recovery
curl -f http://{service-endpoint}/health

# 3. Check error rate dropping
# Prometheus: rate(http_requests_total{service="{service}",status=~"5.."}[5m])
```

### Escalation
- If rollback fails → page platform team
- If rollback succeeds → schedule P2 investigation

## P2 — Metric Degradation (4 hours SLA)

### Symptoms
- Rolling primary metric below quality gate
- Significant drift alert (PSI >= 0.20 on critical feature)

### Actions

```bash
# 1. Check drift scores
curl 'http://prometheus:9090/api/v1/query?query={service}_psi_score'

# 2. If drift confirmed, trigger retraining
gh workflow run retrain-{service}.yml -f reason="P2: metric degradation"

# 3. Monitor retraining quality gates
gh run list --workflow=retrain-{service}.yml --limit=1
```

## P3 — Warning Drift (24 hours SLA)

### Symptoms
- PSI between 0.10 and 0.20 on one or more features

### Actions

```bash
# 1. Run detailed drift analysis
python src/{service}/monitoring/drift_detection.py \
  --reference data/reference/reference.csv \
  --current data/production/latest.csv \
  --output drift_report.json

# 2. Review feature-level breakdown
cat drift_report.json | python -m json.tool

# 3. If single feature: investigate upstream data change
# 4. If multiple features: schedule retraining
# 5. Document findings in drift tracking log
```

## P4 — Incipient Drift (1 week SLA)

### Symptoms
- Small PSI increases trending upward over multiple days

### Actions

- Review Grafana PSI dashboard for trend
- Compare with seasonal patterns (YoY if applicable)
- Document in weekly review
- Schedule proactive retraining if trend continues

## Health Checks

```bash
# Pod status
kubectl get pods -l app={service} -n {namespace}

# Resource usage
kubectl top pod -l app={service} -n {namespace}

# Recent logs
kubectl logs -l app={service} -n {namespace} --since=30m --tail=100

# HPA status
kubectl get hpa {service}-hpa -n {namespace}
```

## Key URLs

- **Grafana Dashboard**: {URL}
- **Prometheus**: {URL}
- **AlertManager**: {URL}
- **MLflow**: {URL}
