---
trigger: glob
globs: ["k8s/**/*.yaml", "k8s/**/*.yml", "helm/**/*.yaml", "helm/**/*.yml"]
description: Kubernetes patterns for ML serving — single-worker pods, CPU-only HPA, init containers
---

# Kubernetes Rules for ML Services

## Single-Worker Pod Pattern (MANDATORY)

`uvicorn --workers N` is an anti-pattern in K8s:
- Multiple workers in one pod share CPU limits → CPU thrashing
- HPA cannot distinguish worker load → scaling signal diluted

Correct pattern: 1 worker per pod, HPA adds pods as needed.

```yaml
containers:
  - name: {service}-predictor
    command: ["uvicorn"]
    args:
      - "app.main:app"
      - "--host=0.0.0.0"
      - "--port=8000"
      # NO --workers flag — default = 1
```

## CPU-Only HPA (MANDATORY)

NEVER use memory as an HPA metric for ML services:
- Model memory footprint is constant (loaded model = fixed RAM)
- Memory-based HPA never scales down: `ceil(replicas × usage / target)` stays constant

```yaml
metrics:
  - type: Resource
    resource:
      name: cpu              # CPU ONLY — never memory
      target:
        type: Utilization
        averageUtilization: 60  # 50-70 based on model weight
behavior:
  scaleDown:
    stabilizationWindowSeconds: 300
    policies:
      - type: Percent
        value: 10
        periodSeconds: 60
  scaleUp:
    stabilizationWindowSeconds: 0
    policies:
      - type: Percent
        value: 100
        periodSeconds: 15
```

## Init Container for Model Download (MANDATORY)

Models are NOT in the Docker image. Downloaded at pod startup via init container:

```yaml
initContainers:
  - name: model-downloader
    image: google/cloud-sdk:slim
    command: ["gsutil", "cp", "gs://BUCKET/SERVICE/model.joblib", "/models/model.joblib"]
    volumeMounts:
      - name: model-storage
        mountPath: /models
volumes:
  - name: model-storage
    emptyDir: {}
```

Why `emptyDir` and not PVC: model is immutable during pod lifetime. No persistence needed.

## Health Probes

```yaml
readinessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 30   # Wait for init container + model load
  periodSeconds: 10
  failureThreshold: 3
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 15
  failureThreshold: 5
```

## Rolling Update Strategy

```yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: 1
    maxUnavailable: 0   # Zero downtime
```

## Kustomize Multi-Cloud

- `k8s/base/` — shared manifests (deployments, HPAs, services)
- `k8s/overlays/gcp/` — Artifact Registry image patches
- `k8s/overlays/aws/` — ECR image patches

Always use Kustomize for image patching, never hardcode registry URLs in base manifests.

## Labels (MANDATORY on every resource)

```yaml
labels:
  app: {service-name}
  version: {semver}
  environment: {staging|production}
  managed-by: {kustomize|helm}
```

## ServiceAccount Annotations

- GCP: `iam.gke.io/gcp-service-account: SA@PROJECT.iam.gserviceaccount.com`
- AWS: `eks.amazonaws.com/role-arn: arn:aws:iam::ACCOUNT:role/ROLE`

Never use hardcoded credentials. Always IRSA (AWS) or Workload Identity (GCP).
