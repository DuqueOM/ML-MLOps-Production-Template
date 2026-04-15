# TECHNICAL SPECIFICATION: ML-MLOps Production template
## Professional Blueprint for Agent-Based Creation and Maintenance Systems

**Version**: 1.0 | **Purpose**: Canonical definition of a production-grade ML template for use as agent context

---

## TABLE OF CONTENTS

1. [Purpose and Design Philosophy](#1-purpose)
2. [System Architecture Overview](#2-architecture)
3. [ML Services: Detailed Specification Template](#3-ml-services)
4. [Complete Technology Stack](#4-stack)
5. [Infrastructure as Code](#5-iac)
6. [Kubernetes and Serving Patterns](#6-kubernetes)
7. [MLflow and Experiment Tracking](#7-mlflow)
8. [Observability: Prometheus + Grafana + AlertManager](#8-observability)
9. [Data Validation: Pandera](#9-data-validation)
10. [Drift Detection and Automatic Retraining](#10-drift)
11. [CI/CD: GitHub Actions](#11-cicd)
12. [Explainability: SHAP KernelExplainer](#12-shap)
13. [Multi-Cloud: GCP + AWS](#13-multicloud)
14. [Architecture Decision Records (ADRs)](#14-adrs)
15. [Quality Standards and Testing](#15-testing)
16. [FinOps and Cost Management](#16-finops)
17. [Documentation and Communication](#17-documentation)
18. [System Invariants (Rules That Are Never Violated)](#18-invariants)
19. [Success Metrics by Dimension](#19-metrics)
20. [Agent Specification: What to Build and What to Target](#20-agents)

---

## 1. PURPOSE AND DESIGN PHILOSOPHY

### Declared Purpose

A production-grade ML template demonstrates **Mid-Senior MLOps Engineer** operational competence through real ML services deployed in production, multi-cloud (GCP + AWS), with infrastructure as code, complete CI/CD, drift monitoring, explainability, and a set of ADRs that document real technical decisions with their trade-offs.

This is not an academic project. It is evidence that the engineer can:
- Build and operate ML systems in real production environments
- Make justified and documented architecture decisions
- Balance performance, cost, complexity, and maintainability
- Debug production problems (CPU thrashing, event loop blocking, data leakage)
- Communicate technical decisions to both technical and non-technical audiences

### Design Philosophy

```
PRINCIPLE 1: "It works AND doesn't ruin the business"
  Maximum performance at any cost does not exist.
  Every decision has a documented trade-off (ADR).

PRINCIPLE 2: "Infrastructure Honesty"
  If the system has a known problem, it is explicitly documented.
  Known limitations live in ADRs, not hidden in code comments.

PRINCIPLE 3: "K8s-native patterns"
  Do not adapt VM patterns to K8s. Use HPA, not multi-workers.
  No multi-worker Gunicorn in K8s. No memory-based HPA for ML services.

PRINCIPLE 4: "Explainability as a first-class citizen"
  ML models that affect business decisions must be explainable.
  SHAP integration is production-grade, not just a notebook demo.

PRINCIPLE 5: "No over-engineering"
  A full orchestrator (Airflow, Prefect) for 2-3 models = over-engineering.
  CronJob + GitHub Actions = correct scale.
  The solution must match the scale of the problem.
```

### MLOps Maturity Level Demonstrated

```
LEVEL 0: No automation (no evidence in the template)
LEVEL 1: Infrastructure monitoring (latency, errors, CPU) ✅
LEVEL 2: Data drift detection (PSI per feature) ✅
LEVEL 3: Drift-triggered automatic retraining with quality gates ✅
LEVEL 4: Explainability in production (?explain=true) ✅
LEVEL 5: Multi-cloud with documented trade-offs ✅
```

---

## 2. SYSTEM ARCHITECTURE OVERVIEW

### High-Level Map

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        ML-MLOps Production template                             │
│                                                                                 │
│  DATA                TRAINING              SERVING              MONITORING      │
│  ────────            ────────────          ───────────          ────────────    │
│  DVC                 GitHub Actions        FastAPI + K8s        Prometheus      │
│  GCS/S3              Pandera (validate)    Kubernetes HPA       Grafana         │
│  Raw datasets        MLflow Tracking       GKE (GCP)            AlertManager    │
│  Reference data      Optuna (tune)         EKS (AWS)            Evidently       │
│                      Quality Gates         Argo Rollouts        SHAP (explain)  │
│                      MLflow Registry       Kustomize overlays   Drift CronJob   │
│                                            Ingress (nginx/NLB)  Pushgateway     │
│                                                                                 │
│  INFRASTRUCTURE                                                                 │
│  ─────────────────                                                              │
│  Terraform IaC                                                                  │
│  GCP: GKE + Cloud SQL + GCS + Artifact Registry                                 │
│  AWS: EKS + RDS + S3 + ECR                                                      │
│  Secrets: GCP Secret Manager + AWS Secrets Manager                              │
│  State: GCS backend + S3+DynamoDB backend                                       │
│                                                                                 │
│  CI/CD (.github/workflows/)                                                     │
│  ─────────────────────────                                                      │
│  ci.yml (lint, test, build)                                                     │
│  ci-infra.yml (tfsec, checkov, validate)                                        │
│  deploy-gcp.yml / deploy-aws.yml                                                │
│  drift-detection.yml                                                            │
│  retrain-{service}.yml (triggered by drift)                                     │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Repository Directory Structure

```
ML-MLOps-template/
│
├── {ServiceA}-Predictor/             # Service 1: [business domain description]
│   ├── app/
│   │   ├── main.py                  # FastAPI app, /predict and /health endpoints
│   │   ├── fastapi_app.py           # Async inference, SHAP integration
│   │   └── schemas.py               # Pydantic request/response models
│   ├── src/{service-a}/
│   │   ├── training/
│   │   │   ├── train.py             # Trainer.run() — full pipeline
│   │   │   ├── features.py          # Feature engineering class
│   │   │   └── model.py             # Model definition
│   │   ├── monitoring/
│   │   │   ├── drift_detection.py   # PSI calculator + CronJob script
│   │   │   ├── business_kpis.py     # Business metrics from confusion matrix
│   │   │   └── evidently_reporter.py
│   │   └── schemas.py               # InputSchema (Pandera)
│   ├── data/
│   │   ├── raw/                     # Raw dataset (DVC tracked)
│   │   └── reference/              # Background data for SHAP + drift reference
│   ├── models/                      # Model artifacts (gitignored, GCS/S3)
│   ├── tests/
│   │   ├── test_training.py
│   │   ├── test_api.py
│   │   └── test_explainer.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── {ServiceB}-Analyzer/              # Service 2: [business domain description]
│   ├── app/
│   ├── src/{service-b}/
│   │   ├── training/
│   │   └── schemas.py
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
│
├── {ServiceC}-Pipeline/              # Service 3: [business domain description]
│   ├── app/
│   ├── src/{service-c}/
│   │   ├── training/
│   │   └── schemas.py
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
│
├── infra/
│   └── terraform/
│       ├── aws/                     # EKS, RDS, S3, ECR, Route53, IRSA
│       └── gcp/                     # GKE, Cloud SQL, GCS, Artifact Registry, WI
│
├── k8s/
│   ├── base/                        # K8s base manifests (all services)
│   │   ├── {service-a}-deployment.yaml
│   │   ├── {service-a}-hpa.yaml     # CPU-only HPA
│   │   ├── {service-a}-service.yaml
│   │   ├── monitoring/             # Prometheus, Grafana, AlertManager
│   │   ├── mlflow/                 # MLflow deployment, two-ingress pattern
│   │   ├── drift-detection-cronjob.yaml
│   │   └── alertmanager-rules.yaml
│   ├── overlays/
│   │   ├── gcp/                    # GCP image patches (Artifact Registry URLs)
│   │   └── aws/                    # AWS image patches (ECR URLs)
│   └── kustomization.yaml
│
├── monitoring/
│   ├── grafana/                    # Dashboard JSON files
│   └── prometheus/                 # Alerting rules
│
├── .github/
│   └── workflows/
│       ├── ci.yml
│       ├── ci-infra.yml
│       ├── deploy-gcp.yml
│       ├── deploy-aws.yml
│       ├── drift-detection.yml
│       └── retrain-{service}.yml
│
├── docs/
│   └── decisions/                  # ADRs (N decisions)
│       ├── 001-{decision}.md
│       └── ...
│
├── scripts/
│   ├── sagemaker/                  # SageMaker integration (optional)
│   └── vertex_ai/                  # Vertex AI integration (optional)
│
├── tests/
│   └── infra/                      # Terraform testing (tfsec, checkov)
│
├── .dvc/                           # DVC config (GCS + S3 remotes)
├── AGENTS.md                       # Rules for maintenance agents
└── README.md                       # template overview
```

---

## 3. ML SERVICES: DETAILED SPECIFICATION TEMPLATE

Each ML service in the template follows this specification template. Fill in the bracketed fields for each concrete service.

### Service Specification Template

**Purpose**: [One sentence describing the business problem solved. Example: Predicts the probability of [outcome] for [subject], enabling [business team] to [action].]

**Dataset**: [Name / source] — [N rows], [N features], [target distribution — e.g., class imbalance %]

**Input Features** (document every feature):
```
[FeatureName]  [type, range/categories]  [business meaning]
[FeatureName]  [type, range/categories]  [business meaning]
...
```

**Model**: [Architecture chosen, see ADR-XXX]
```python
# Document the full pipeline here
pipeline = Pipeline([
    ('feature_engineer', [FeatureEngineerClass]()),
    ('preprocessor', ColumnTransformer([...])),
    ('model', [ModelClass](...))
])
```

**Production Metrics** (measured, not estimated):
```
[Primary metric]:    [value]
[Secondary metric]:  [value]
[Fairness metric]:   [value]  ← Always include a fairness check
```

**Serving Latency** (measured on actual hardware):
```
GCP ([instance type]):  p50=[X]ms, p95=[Y]ms (idle)
AWS ([instance type]):  p50=[X]ms, p95=[Y]ms (idle)
Under load ([N] users): GCP p50=[X]ms, AWS p50=[Y]ms
(See ADR-0XX for the documented trade-off)
```

**Special Features** (document non-standard capabilities):
- `?explain=true`: [What it does and approximate latency]
- [Custom threshold]: [Why it's not 0.5 and what value was chosen]
- [Any special preprocessing]: [Why it's needed]

**Drift Detection Strategy**:
- [Metric used]: PSI / KS-test / OOV rate / YoY comparison / [other]
- [Rationale]: Why this metric and not standard PSI (e.g., seasonal patterns)
- Warning threshold: [value]
- Alert threshold: [value]

---

## 4. COMPLETE TECHNOLOGY STACK

### Python and ML

```python
# Pin versions with compatible release operator ~= (see ADR on dependency pinning)
python            = "3.11+"

# ML Core
scikit-learn      ~= "[version]"
xgboost           ~= "[version]"   # If used
lightgbm          ~= "[version]"   # If used
pandas            ~= "[version]"
numpy             ~= "[version]"
scipy             ~= "[version]"
optuna            ~= "[version]"   # Hyperparameter tuning

# Data Validation
pandera           ~= "[version]"   # Schemas, DataFrameModel, checks

# Explainability
shap              ~= "[version]"   # KernelExplainer for complex ensembles

# Drift Detection & Monitoring
evidently         ~= "[version]"   # HTML drift reports
prometheus_client ~= "[version]"   # Prometheus metrics from Python

# Serving
fastapi           ~= "[version]"
uvicorn           ~= "[version]"
pydantic          ~= "[version]"

# MLflow
mlflow            ~= "[version]"

# Big Data (if needed)
pyspark           ~= "[version]"   # Only for services processing large datasets

# Testing
pytest            ~= "[version]"
locust            ~= "[version]"   # Load testing
```

### Infrastructure and Platforms

```
Cloud Platforms:    GCP (primary) + AWS (secondary parity)
Kubernetes:         GKE (GCP) + EKS (AWS)
IaC:                Terraform >= 1.7
Container Registry: Artifact Registry (GCP) + ECR (AWS)
Storage:            GCS (GCP) + S3 (AWS)
Database:           Cloud SQL PostgreSQL (GCP) + RDS PostgreSQL (AWS)
Secrets:            GCP Secret Manager + AWS Secrets Manager
ML Tracking:        MLflow [version] (self-hosted on K8s)
Data Versioning:    DVC (remotes on GCS + S3)
Monitoring Stack:   Prometheus + Grafana + AlertManager + Pushgateway
Ingress:            NGINX Ingress Controller (GCP) + AWS NLB (AWS)
CI/CD:              GitHub Actions
Security Scan:      tfsec + checkov (for Terraform)
Load Testing:       Locust
```

---

## 5. INFRASTRUCTURE AS CODE

### Terraform — Modules and Resources

**Applied Principles**:
- Remote state always (S3+DynamoDB for AWS, GCS for GCP)
- Compatible release pinning (`~=` in Python, `>=` in Terraform)
- Secrets in Secrets Manager / Secret Manager — NEVER in tfvars
- IRSA (AWS) and Workload Identity (GCP) — no credentials in pods
- Separation by functional files (network.tf, compute.tf, storage.tf, etc.)
- `staging.tfvars` + `terraform.tfvars` (prod) — same modules, different scale

**GCP — Resources**:
```hcl
# compute.tf
resource "google_container_cluster" "gke" {
  name                     = "${var.project_name}-gke-${var.environment}"
  enable_autopilot         = false
  networking_mode          = "VPC_NATIVE"
  workload_identity_config { workload_pool = "${var.project_id}.svc.id.goog" }
  network_policy           { enabled = true }
  private_cluster_config   { enable_private_nodes = true }
}

resource "google_container_node_pool" "nodes" {
  machine_type = var.machine_type    # e.g., e2-medium — see cost ADR
  node_config {
    workload_metadata_config { mode = "GKE_METADATA" }
    oauth_scopes = ["https://www.googleapis.com/auth/cloud-platform"]
  }
  autoscaling { min_node_count = 1; max_node_count = 5 }
}
```

**AWS — Resources**:
```hcl
# compute.tf
resource "aws_eks_cluster" "eks" {
  name    = "${var.project_name}-eks-${var.environment}"
  version = "[k8s_version]"
}

resource "aws_iam_openid_connect_provider" "eks" {
  # Enables IRSA (IAM Roles for Service Accounts)
  url             = aws_eks_cluster.eks.identity[0].oidc[0].issuer
  client_id_list  = ["sts.amazonaws.com"]
}

resource "aws_eks_node_group" "nodes" {
  instance_types = [var.eks_node_instance_type]   # e.g., t3.medium — see cost ADR
  scaling_config { min_size = 1; max_size = 5; desired_size = 2 }
}
```

**Security baseline** (non-negotiable for every environment):
```
✅ KMS encryption (S3: aws:kms, GCS: CMEK where applicable)
✅ Public access blocked on all buckets
✅ Access logging → dedicated bucket (not self-referential)
✅ Versioning enabled on data and model buckets
✅ Lifecycle rules (archive after N days, expire after M days)
✅ IAM least privilege (read-only for model serving, read-write for mlflow)
✅ Network policies in K8s
✅ Private nodes in GKE
✅ Database: SSL required, IAM auth enabled
```

---

## 6. KUBERNETES AND SERVING PATTERNS

### The Single-Worker Pod Pattern

**Fundamental rule**: `uvicorn --workers N` is an anti-pattern in K8s.

```
ANTI-PATTERN:                        CORRECT PATTERN:
┌─── Pod (1000m CPU) ───┐            ┌─── Pod 1 (1000m CPU) ──┐
│  Worker 1 + Worker 2  │            │  Worker 1               │
│  Share 1000m          │   →        └────────────────────────┘
│  CPU thrashing        │            ┌─── Pod 2 (1000m CPU) ──┐
└────────────────────────┘            │  Worker 1               │
                                      └────────────────────────┘
                                      (HPA adds pods as needed)
```

**Deployment configuration** (all services):
```yaml
containers:
  - name: {service}-predictor
    command: ["uvicorn"]
    args:
      - "app.main:app"
      - "--host=0.0.0.0"
      - "--port=8000"
      # NO --workers: default = 1
    resources:
      requests:
        cpu: "[value based on profiling]"
        memory: "[value based on profiling]"
      limits:
        cpu: "[value based on profiling]"
        memory: "[value based on profiling]"
```

### CPU-Only HPA

**Fundamental rule**: NEVER use memory as an HPA metric for ML services.

The memory of an ML pod is constant (the loaded model always occupies the same amount). With memory as the metric, HPA never scales down:
```
ceil(replicas × memory_usage / target) = ceil(3 × 67% / 80%) = 3
→ Always 3 replicas even if traffic is 0
```

```yaml
# Correct HPA for all ML services
metrics:
  - type: Resource
    resource:
      name: cpu                         # CPU ONLY — never memory
      target:
        type: Utilization
        averageUtilization: [50-70]     # Higher for lighter models

behavior:
  scaleDown:
    stabilizationWindowSeconds: 300     # 5 min before scaling down
    policies:
      - type: Percent
        value: 10
        periodSeconds: 60
  scaleUp:
    stabilizationWindowSeconds: 0       # Scale up immediately
    policies:
      - type: Percent
        value: 100
        periodSeconds: 15
```

**Fixed memory footprints** — document these per service:
```
{ServiceA}:  ~[N]Mi ([model type] + [dependencies])
{ServiceB}:  ~[N]Mi ([model type] + [dependencies])
{ServiceC}:  ~[N]Mi ([model type] + [dependencies])
```

### Async Inference with ThreadPoolExecutor

**Problem**: `sklearn.predict()` (and most ML frameworks) are synchronous and block asyncio's event loop.

**Solution**: `asyncio.run_in_executor()` with ThreadPoolExecutor

```python
# Mandatory pattern for prediction endpoints
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import asyncio

_inference_executor = ThreadPoolExecutor(
    max_workers=4,          # Tune based on CPU cores available
    thread_name_prefix="ml-infer"
)

def _sync_predict(input_dict: dict, explain: bool) -> PredictionResponse:
    """CPU-bound — runs in thread pool, does not block event loop."""
    df = pd.DataFrame([input_dict])
    prob = float(model_pipeline.predict_proba(df)[:, 1][0])
    # ... build response

@app.post("/predict")
async def predict(input_data: InputSchema, explain: bool = False):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _inference_executor,
        partial(_sync_predict, input_data.model_dump(), explain)
    )
```

**Why this works**: Most ML frameworks (sklearn, XGBoost, LightGBM) release the GIL during C extensions → real parallelism with threads.

**Measured result template**:
- BEFORE (sync): [X]% error rate under [N] concurrent users
- AFTER (async): [Y]% error rate, CPU reduced from [A]m to [B]m

### Init Container for Models

Models are NOT included in the Docker image. They are downloaded on pod startup.

```yaml
# Pattern for all services
initContainers:
  - name: model-downloader
    image: google/cloud-sdk:slim   # GCP; use aws-cli for AWS
    command:
      - gsutil               # or: aws s3 cp
      - cp
      - gs://[model-bucket]/[service]/model.joblib
      - /models/model.joblib
    volumeMounts:
      - name: model-storage
        mountPath: /models

containers:
  - name: {service}-predictor
    env:
      - name: MODEL_PATH
        value: /models/model.joblib
    volumeMounts:
      - name: model-storage
        mountPath: /models

volumes:
  - name: model-storage
    emptyDir: {}    # Ephemeral, destroyed with the pod
```

**Why `emptyDir` and not PVC**: The model is immutable during the pod's lifetime. No persistence needed between pods. emptyDir is simpler, cheaper, and aligns with the stateless pattern.

### Kustomize for Multi-Cloud

```
k8s/
├── base/               # Manifests shared between GCP and AWS
│   └── {service}-deployment.yaml (with image placeholders)
│
└── overlays/
    ├── gcp/
    │   └── kustomization.yaml  # Patches image with Artifact Registry URL
    └── aws/
        └── kustomization.yaml  # Patches image with ECR URL
```

```yaml
# overlays/gcp/kustomization.yaml
images:
  - name: {service}-predictor
    newName: [REGION]-docker.pkg.dev/[PROJECT_ID]/ml-images/{service}
    newTag: [VERSION]

# overlays/aws/kustomization.yaml
images:
  - name: {service}-predictor
    newName: [ACCOUNT].dkr.ecr.[REGION].amazonaws.com/ml-template/{service}
    newTag: [VERSION]
```

---

## 7. MLFLOW AND EXPERIMENT TRACKING

### MLflow Architecture on K8s

```
mlflow server \
  --backend-store-uri postgresql://mlflow:${DB_PASS}@${DB_HOST}/mlflow \
  --default-artifact-root gs://[mlflow-artifacts-bucket]/ \
  --host 0.0.0.0 \
  --port 5000
```

**Two-Ingress Pattern** (required due to NGINX Ingress limitations with MLflow):
```yaml
# Ingress 1: ML services ({service-a}, {service-b}, {service-c})
# Ingress 2: Monitoring stack (MLflow, Grafana, Prometheus)
# Reason: MLflow requires special proxy configuration that cannot be
# mixed with ML service ingress rules without causing conflicts
```

### Tracking Hierarchy

```
MLflow Experiment "[ServiceName]-Production"
  └── Run: "[ModelType]-v[X.Y.Z]"
      ├── Parameters: {key hyperparameters documented}
      ├── Metrics:    {primary metric, secondary metrics, fairness metrics}
      ├── Artifacts:  {model.joblib, feature_importance.png, confusion_matrix.png}
      └── Tags:       {git_commit: "[SHA]", environment: "production"}

MLflow Model Registry "[ServiceName]Classifier"
  ├── Version N-1 → Archived
  ├── Version N   → Production  ← ACTIVE
  └── Version N+1 → Staging (candidate)
```

### Model Promotion with Quality Gates

```python
def should_promote(new_metrics: dict, current_prod_metrics: dict) -> bool:
    """
    Quality gates before promoting to production.
    A model retrained on drifted data may be WORSE than the current one.
    Every project defines its own gates; the structure is always the same.
    """
    return all([
        # Gate 1: No regression > [threshold]% on primary metric
        new_metrics["primary_metric"] >= current_prod_metrics["primary_metric"] * 0.95,

        # Gate 2: Minimum acceptable value for primary metric
        new_metrics["primary_metric"] >= [MINIMUM_THRESHOLD],

        # Gate 3: Secondary metric minimum
        new_metrics["secondary_metric"] >= [MINIMUM_THRESHOLD],

        # Gate 4: P95 latency does not increase > 20%
        new_metrics["p95_latency_ms"] <= current_prod_metrics["p95_latency_ms"] * 1.20,

        # Gate 5: Fairness — Disparate Impact Ratio ≥ 0.80 per protected attribute
        new_metrics["dir_attribute_1"] >= 0.80,
        new_metrics["dir_attribute_2"] >= 0.80,
    ])
```

---

## 8. OBSERVABILITY: PROMETHEUS + GRAFANA + ALERTMANAGER

### Metrics Exported by Each Service

Each FastAPI service exposes Prometheus metrics at `/metrics`:

```python
from prometheus_client import Counter, Histogram, Gauge

# Business metrics (not just infrastructure)
predictions_total = Counter(
    '{service}_predictions_total',
    'Total predictions by risk level',
    ['risk_level', 'model_version']
)

prediction_latency = Histogram(
    '{service}_prediction_latency_seconds',
    'Prediction latency in seconds',
    ['endpoint'],
    buckets=[0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0]
)

prediction_score_distribution = Histogram(
    '{service}_prediction_score',
    'Distribution of model output scores',
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
)

# Drift metrics (pushed from CronJob via Pushgateway)
psi_score_per_feature = Gauge(
    '{service}_psi_score',
    'PSI drift score per feature',
    ['feature']
)

drift_detection_last_run_timestamp = Gauge(
    'drift_detection_last_run_timestamp',
    'Unix timestamp of last successful drift detection run'
)
```

### Critical Alerts Configured

```yaml
groups:
- name: ml_sla
  rules:

  # P1: High error rate (immediate rollback)
  - alert: HighErrorRate
    expr: rate(http_requests_total{service="{service}",status=~"5.."}[5m]) > 0.05
    for: 2m
    labels: {severity: P1}

  # P2: Primary metric degraded (urgent retraining)
  - alert: PrimaryMetricDegraded
    expr: {service}_rolling_{metric}_7d < [THRESHOLD]
    for: 1h
    labels: {severity: P2}

  # P3: Significant drift on critical feature
  - alert: CriticalFeatureDriftHigh
    expr: {service}_psi_score{feature="[critical_feature]"} > 0.20
    for: 1h
    labels: {severity: P3}

  # P4: Incipient drift (monitor closely)
  - alert: DriftWarning
    expr: {service}_psi_score > 0.10
    for: 6h
    labels: {severity: P4}

  # Heartbeat: drift detection did not run in 48h
  - alert: DriftDetectionHeartbeatMissing
    expr: (time() - drift_detection_last_run_timestamp) > 172800
    for: 5m
    labels: {severity: P2}
```

### P1–P4 Runbook Template

```
P1 (15 min SLA): Immediate rollback
  kubectl rollout undo deployment/{service}-predictor -n [namespace]

P2 (4 hours SLA): Trigger retraining
  gh workflow run retrain-{service}.yml

P3 (24 hours SLA): Investigate + plan retraining
  → Review PSI per feature in Grafana
  → Identify root cause (upstream data change? concept drift?)

P4 (1 week SLA): Document the trend
  → Log in the tracking table
  → Schedule a review meeting
```

---

## 9. DATA VALIDATION: PANDERA

### Why Pandera and Not Great Expectations

```
Great Expectations has 100+ dependencies vs ~12 for Pandera.
GE solves problems related to data stores (SQL, S3, Spark) and
shared team documentation — use cases that do not apply when:
  - Models use in-memory DataFrames from sklearn pipelines
  - The team is small (< 5 ML engineers)
  - There are no external data store contracts to validate

For sklearn models with in-memory DataFrames:
✅ Pandera: correct and sufficient
❌ Great Expectations: over-engineering

GE has no native Prometheus/Grafana integration.
Integrating GE with Grafana requires: GE → Python bridge →
prometheus_client → Pushgateway → Prometheus → Grafana.
Unjustified complexity for small-scale ML pipelines.

When GE IS the right choice:
  - Multiple data sources (SQL + S3 + Kafka)
  - Shared data contracts between teams
  - Need for auto-generated HTML data documentation
  - Spark or Databricks pipelines
```

### Validation Schemas

```python
import pandera.pandas as pa

class ServiceInputSchema(pa.DataFrameModel):
    """
    Define one schema per service. Each field documents:
    - Type
    - Valid range or categories
    - Nullability
    """
    [feature_name]: [type] = pa.Field([constraints])
    [feature_name]: [type] = pa.Field([constraints])
    # ... one line per feature

    class Config:
        coerce = True   # Auto-convert types where possible
        strict = False  # Allow extra columns

# Usage in training and API
@pa.check_types
def validate_input(df: pa.typing.DataFrame[ServiceInputSchema]) -> pd.DataFrame:
    return df

# Generates SchemaError with descriptive message on violation
# Example: "column '[feature]' failed validator check '[constraint]'"
```

### Validation at Multiple Pipeline Points

```
POINT 1: data/validate_data.py
  → When loading the raw dataset before training
  → "Fail fast": training does not start with invalid data

POINT 2: API endpoint /predict
  → Input validation before inference
  → SchemaError → HTTP 422 with descriptive message

POINT 3: Drift detection
  → Schema validation of the production batch before calculating PSI
  → Schema mismatch = immediate alert (features added/removed upstream)
```

---

## 10. DRIFT DETECTION AND AUTOMATIC RETRAINING

### PSI (Population Stability Index) as Primary Metric

```python
def calculate_psi(reference, current, bins=10, epsilon=1e-8):
    """
    PSI with quantile-based bins (NOT uniform bins).

    Why quantiles: uniform bins can have empty bins at extremes
    → PSI dominated by epsilon, not real data.
    Quantiles guarantee each bin has observations in the reference.

    Interpretation:
    PSI < 0.10:  No significant change
    0.10 ≤ PSI < 0.20: Moderate change → monitor
    PSI ≥ 0.20:  Significant change → action required
    """
    breakpoints = np.percentile(reference, np.linspace(0, 100, bins + 1))
    breakpoints[0]  = -np.inf
    breakpoints[-1] = np.inf

    ref_counts, _ = np.histogram(reference, bins=breakpoints)
    cur_counts, _ = np.histogram(current, bins=breakpoints)

    ref_pct = np.maximum(ref_counts / len(reference), epsilon)
    cur_pct = np.maximum(cur_counts / len(current), epsilon)

    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))
```

### Thresholds per Service (With Domain Reasoning)

For each service, document why each threshold was chosen:

```
{ServiceA}:
  [stable_feature]:    warning=[X], alert=[Y]
    Reason: [e.g., "historically stable, tight thresholds appropriate"]
  [volatile_feature]:  warning=[X+0.05], alert=[Y+0.10]
    Reason: [e.g., "high natural variance, looser threshold prevents false positives"]
  [categorical_feature]: warning=[X], alert=[Y]
    Reason: [e.g., "binary feature, PSI is sufficient"]

{ServiceC} (if it has temporal patterns):
  IMPORTANT: Standard PSI will flag EVERY seasonal change as drift.
  Use Year-over-Year comparison instead:
    warning=[15%] change vs same period last year
    alert=[30%] change vs same period last year
```

### The Complete Retraining Loop

```
1. K8s CronJob (scheduled, e.g., daily at 02:00 UTC)
   → Downloads production data from GCS/S3
   → Calculates PSI per feature against reference dataset
   → Pushes metrics to Prometheus via Pushgateway

2. If PSI > threshold on critical feature:
   → Calls GitHub API with workflow_dispatch
   → Triggers: retrain-{service}.yml

3. retrain-{service}.yml:
   → Downloads fresh data (last N days)
   → Executes Trainer.run() with Optuna (N trials)
   → Calculates quality gates

4. Quality gates (ALL must pass):
   → Primary metric > [absolute threshold]
   → Primary metric >= production_metric × 0.95 (no regression)
   → Secondary metric >= [threshold]
   → Fairness: DIR >= 0.80 per protected attribute
   → P95 latency <= current × 1.20

5. If ALL PASS: promote in MLflow Registry + upload to GCS/S3 + rolling restart
   If ANY FAIL: open GitHub Issue automatically + keep current model

6. Heartbeat alert in AlertManager triggers P2 if the CronJob
   has not reported its timestamp in 48 hours
   (detects silently broken CronJobs)
```

---

## 11. CI/CD: GITHUB ACTIONS

### Implemented Workflows

```yaml
# ci.yml — On every push to main/develop
jobs:
  lint:
    - flake8, black --check, isort --check
    - mypy (type checking)

  test:
    - pytest with coverage >= 90%
    - Tests per service (test_training, test_api, test_explainer)

  build:
    - docker build --cache-from
    - trivy scan (image vulnerabilities)
    - docker push (only on main)

# ci-infra.yml — When infra/ or k8s/ changes
jobs:
  terraform-gcp:
    - terraform fmt -check
    - terraform validate
    - tfsec --format json
    - checkov -d infra/terraform/gcp

  terraform-aws:
    - (same pattern)

# deploy-{cloud}.yml — On release tag or manual dispatch
jobs:
  deploy:
    - kubectl apply -k k8s/overlays/{cloud}/
    - kubectl rollout status (verifies complete rollout)
    - Smoke test (curl /health)
    - Success/failure notification

# drift-detection.yml — Scheduled (e.g., daily at 02:00 UTC)
jobs:
  drift-detection:
    strategy:
      matrix:
        project: [{ServiceA}, {ServiceB}, {ServiceC}]
    steps:
      - run: python monitoring/drift_detection.py ...
        continue-on-error: true          # Drift does not block CI
      - if: steps.drift.outcome == 'failure'
        uses: actions/github-script@v7  # Creates GitHub Issue automatically
```

### Deployment Strategy (Zero Downtime)

```yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: 1         # Maximum 1 additional pod during deploy
    maxUnavailable: 0   # Zero pods down at any moment

# New pods pass readiness probe BEFORE old ones are terminated:
readinessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 30   # Wait for init container to download the model
  periodSeconds: 10
  failureThreshold: 3
```

---

## 12. EXPLAINABILITY: SHAP KERNELEXPLAINER

### Why KernelExplainer (Not TreeExplainer)

```
TreeExplainer does NOT work with stacking ensembles or complex pipelines:
→ Cannot trace contributions through a meta-learner
→ Error: "Model type not yet supported"

KernelExplainer:
→ Treats the model as a black box
→ Perturbs features and observes prediction changes
→ Works with ANY model type
→ Higher latency (~seconds) — acceptable for opt-in, high-stakes endpoints
```

### The predict_proba_wrapper — The Critical Piece

```python
def predict_proba_wrapper(X_array: np.ndarray) -> np.ndarray:
    """
    Why this wrapper is fundamental:

    KernelExplainer calls the function with numpy arrays.
    Our Pipeline expects DataFrames with column names.

    WITHOUT this wrapper: SHAP calculates in TRANSFORMED space
    → "[encoded_feature_variant]: +0.02" — uninterpretable to stakeholders

    WITH this wrapper: SHAP calculates in ORIGINAL feature space
    → "[original_feature]: -0.013" — directly actionable
    """
    X_df = pd.DataFrame(X_array, columns=original_feature_names)
    return pipeline.predict_proba(X_df)[:, 1]  # P(positive class)

explainer = shap.KernelExplainer(
    model=predict_proba_wrapper,
    data=X_background.values[:50],   # 50 samples: balance precision/speed
)
```

### Production Output Format

```json
{
  "prediction_score": "[0.0 to 1.0]",
  "risk_level": "[LOW|MEDIUM|HIGH]",
  "explanation": {
    "method": "kernel_explainer",
    "base_value": "[population mean prediction]",
    "feature_contributions": {
      "[feature_1]":  "[signed contribution value]",
      "[feature_2]":  "[signed contribution value]",
      "...": "..."
    },
    "top_risk_factors": ["[feature (+contribution)]"],
    "top_protective_factors": ["[feature (-contribution)]"],
    "consistency_check": {
      "actual_score": "[model output]",
      "reconstructed": "[base_value + sum(contributions)]",
      "difference": "[should be < 0.001]",
      "passed": true
    },
    "computation_time_ms": "[measured latency]"
  }
}
```

**Consistency property** (always must hold):
```
base_value + Σ(shap_values) ≈ predict_proba(input)
[X] + [Y] = [Z] ✅   (tolerance < 0.001)
```

---

## 13. MULTI-CLOUD: GCP + AWS

### Latency Documentation Template (Fill with Real Measurements)

| Service | GCP p50 (idle) | AWS p50 (idle) | GCP p50 (50u load) | AWS p50 (50u load) |
|---|---|---|---|---|
| {ServiceA} | [X]ms | [X]ms | [X]ms | [X]ms |
| {ServiceB} | [X]ms | [X]ms | [X]ms | [X]ms |
| {ServiceC} | [X]ms | [X]ms | [X]ms | [X]ms |

**Document the root cause of any significant difference** in the corresponding ADR:
```
[Service] is [CPU-bound / I/O-bound / memory-bound].
GCP [instance type]: [CPU spec, allocation model]
AWS [instance type]: [CPU spec, allocation model]

DECISION: Accept the difference. Both clouds meet the <[N]ms idle SLA.
Upgrade to [more expensive instance]: $[X]/mo vs current $[Y]/mo: [rejected/accepted].
See ADR-0XX for the full cost analysis.
```

### Multi-Cloud Costs Template

```
GCP production:  ~$[X]/mo
AWS production:  ~$[Y]/mo
Total monthly:   ~$[Z]/mo

GCP staging:     ~$[X]/mo (Preemptible VMs)
AWS staging:     ~$[Y]/mo
```

---

## 14. ARCHITECTURE DECISION RECORDS (ADRs)

Every non-trivial architectural decision has an ADR. The minimum required ADR set for a production ML template covers these categories:

| Category | ADR Title Template | Core Decision |
|---|---|---|
| **K8s Serving** | CPU-Only HPA | NEVER use memory as HPA metric for ML |
| **K8s Serving** | emptyDir + Init Container | Models downloaded at pod startup, not in the image |
| **K8s Serving** | Single-Worker Pod | `--workers 1` always; concurrency via HPA |
| **K8s Serving** | Async Inference ThreadPool | `run_in_executor` for CPU-bound model calls |
| **Model Selection** | [ModelType] for [Service] | [Architecture] vs alternatives: [metric] improvement |
| **Dependencies** | Compatible Release Pinning | `~=` in requirements, not `==` or `>=` without cap |
| **Retraining** | Drift-Triggered Retraining | [Orchestrator choice] + GitHub Actions |
| **Data Storage** | Feature Store Decision | [Why yes or why deferred] |
| **Data Quality** | Data Leakage Prevention | [How and why features were reviewed for leakage] |
| **Explainability** | SHAP KernelExplainer | KernelExplainer only compatible with [model type] |
| **Performance** | Cloud Performance Parity | Accepted difference: $[X]/mo vs $[Y]/mo for parity |
| **Platform** | Custom vs Managed Platforms | Custom K8s primary + managed as complement |
| **Multi-Cloud** | Multi-Cloud Parity Policy | Same API contracts in GCP and AWS |
| **Security** | Security Scanner Policy | Tiered remediation: staging advisory / prod blocking |
| **IaC** | Terraform Remote State | Cloud-native backends per cloud |
| **UI** | Demo Tools Not Deployed | Swagger UI sufficient; demo tools stay local |
| **Simplification** | When NOT to Build | Complexity must justify itself with proportional value |

Each ADR follows this structure:
```markdown
# ADR-NNN: [Title]

**Status**: Proposed | Accepted | Deprecated | Superseded by ADR-NNN
**Date**: YYYY-MM-DD

## Context
[What problem are we solving? What constraints exist?]

## Options Considered
| Option | Pros | Cons |
|--------|------|------|

## Decision
[What we decided]

## Rationale
[Why this option over the others]

## Consequences
- **Positive**: [what we gain]
- **Negative**: [what we trade off]

## Revisit When
[Conditions that would invalidate this decision]
```

---

## 15. QUALITY STANDARDS AND TESTING

### Test Pyramid

```
                     ┌─────────────────┐
                     │  Load Tests     │  Locust: N/100 concurrent users
                     │  (End-to-end)   │  Validates SLAs in production-like env
                     ├─────────────────┤
                     │  API Tests      │  FastAPI TestClient
                     │  (Integration)  │  Validates endpoints, schemas, error handling
                     ├─────────────────┤
                     │  Unit Tests     │  pytest
                     │                 │  Training, features, explainer
                     └─────────────────┘
```

### Mandatory Tests per Service (Templates)

```python
# 1. Data leakage regression test (critical for temporal data)
def test_no_data_leakage():
    """Primary metric must not be unrealistically high — if so, there is leakage."""
    _, metrics = train_model()
    assert metrics['primary_metric'] < [SUSPICIOUSLY_HIGH_THRESHOLD], \
        f"Possible data leakage: metric={metrics['primary_metric']}"

# 2. SHAP regression test: values must not be all zeros
def test_shap_values_not_all_zero(explainer, sample_input):
    """SHAP returning zeros is a known failure mode — it must never happen."""
    result = explainer.explain(sample_input)
    non_zero = [v for v in result["feature_contributions"].values() if abs(v) > 0.001]
    assert len(non_zero) >= [MINIMUM_INFORMATIVE_FEATURES]

# 3. SHAP consistency property
def test_shap_consistency(pipeline, explainer, sample_input):
    actual = float(pipeline.predict_proba(sample_input)[:, 1][0])
    result = explainer.explain(sample_input)
    reconstructed = result["base_value"] + sum(result["feature_contributions"].values())
    assert abs(actual - reconstructed) < 0.01

# 4. SHAP is in original feature space, not transformed space
def test_feature_space_is_original(explainer, sample_input):
    result = explainer.explain(sample_input)
    assert set(result["feature_contributions"].keys()) == set(ORIGINAL_FEATURES)
    # If this fails: the wrapper is computing SHAP post-ColumnTransformer

# 5. Primary metric quality gate
def test_model_meets_quality_gate():
    _, metrics = train_with_cross_validation()
    assert metrics['primary_metric'] >= [PRODUCTION_QUALITY_GATE], \
        f"Metric {metrics['primary_metric']} below quality gate"

# 6. Inference latency SLA
def test_inference_latency():
    start = time.time()
    pipeline.predict_proba(sample_df)
    elapsed = (time.time() - start) * 1000
    assert elapsed < [LATENCY_SLA_MS], f"Inference {elapsed}ms exceeds SLA"

# 7. Fairness check
def test_fairness_disparate_impact():
    """No protected attribute should have DIR < 0.80."""
    _, metrics = evaluate_model_by_group()
    for attribute in PROTECTED_ATTRIBUTES:
        assert metrics[f'dir_{attribute}'] >= 0.80, \
            f"Fairness violation: DIR for {attribute} = {metrics[f'dir_{attribute}']}"
```

### Coverage Target

```
Lines of code: ≥ 90% coverage in src/
Branches:      ≥ 80% coverage
```

---

## 16. FINOPS AND COST MANAGEMENT

### Applied Rules

```
1. Spot/Preemptible for training (70% discount):
   - All training jobs = Spot/Preemptible
   - Checkpointing enabled for long training jobs (> 2h)

2. On-Demand for serving (APIs must always be available):
   - All serving deployments = On-Demand

3. CPU-only HPA to avoid over-provisioning:
   - No memory HPA = no idle pods stuck at minimum replicas

4. Automatic lifecycle policies in GCS/S3:
   - Models: archive after [N] days, delete after [M] days
   - Datasets: same policy, adjusted for data retention requirements

5. Budget alerts in Terraform:
   - Alert at 50% and 90% of monthly budget per cloud
   - Forecast alert at 100% projected spend

6. Destroy non-production environments when not in use:
   - RULE: Never leave a cluster running overnight if not actively needed
   - Use: `terraform destroy -var-file=staging.tfvars`
```

### TCO Template

```
Compute serving ([N] APIs × 2 clouds):  ~$[X]/mo
Compute training (Spot, monthly avg):    ~$[X]/mo
Databases (Cloud SQL + RDS):             ~$[X]/mo
Storage (GCS + S3):                      ~$[X]/mo
Registry (Artifact Registry + ECR):      ~$[X]/mo
Monitoring and Logging:                  ~$[X]/mo
TOTAL estimated:                         ~$[TOTAL]/mo

Ephemeral demo (create and destroy same day): ~$[2-10]
```

---

## 17. DOCUMENTATION AND COMMUNICATION

### Documentation Types in the template

```
1. ADRs (docs/decisions/)
   → Audience: ML engineers, tech leads
   → Content: Why this technical decision was made
   → Format: Status, Context, Decision, Alternatives, Consequences

2. Per-service README ({Service}/README.md)
   → Audience: any new engineer
   → Content: How to run the service, what it does, metrics
   → Format: Quick start, endpoints, metrics, deploy

3. Infrastructure READMEs (infra/terraform/*)
   → Audience: DevOps/Platform engineers
   → Content: How to deploy the infrastructure
   → Format: Prerequisites, resources, security, troubleshooting

4. AGENTS.md (repo root)
   → Audience: AI agents for maintenance
   → Content: Rules that agents must follow
   → Format: Invariants, DO NOT VIOLATE patterns, design decisions

5. Runbooks (docs/runbooks/)
   → Audience: On-call engineers
   → Content: What to do when something fails
   → Format: P1-P4 severity, executable steps, exact commands

6. Progressive Learning Guides (optional)
   → Audience: Engineers from Junior to Staff
   → Content: How to understand each technical decision in depth
   → Format: analogy → theory → code → exercises → interview questions
```

### AGENTS.md — Rules for Maintenance Agents

```markdown
# Patterns that agents must NEVER violate:

## NEVER use uvicorn --workers N in K8s
Reason: CPU thrashing under pod CPU limits.
Single-worker + horizontal HPA is always the answer.

## NEVER use memory as an HPA metric for ML services
Reason: Model memory footprint is constant → HPA never scales down.
CPU is the only valid metric for ML serving pods.

## NEVER call model.predict_proba() directly in an async endpoint
Reason: Blocks asyncio's event loop.
Always use asyncio.run_in_executor() with ThreadPoolExecutor.

## NEVER use TreeExplainer with complex ensemble pipelines
Reason: Not supported. Always use KernelExplainer with predict_proba_wrapper.

## NEVER use == in requirements.txt for ML dependencies
Reason: Resolution conflicts between packages.
Always use ~= (compatible release).

## NEVER use memory-based scaling for ML pods
Reason: Documented in the HPA ADR. See k8s/base/*.hpa.yaml for correct values.

## NEVER omit quality gates before promoting a model
Reason: A model retrained on drifted data can be worse than the current one.
See the promote_model script for the complete gate list.
```

---

## 18. SYSTEM INVARIANTS (Rules That Are Never Violated)

These properties must be preserved by any agent or developer modifying the system:

### Infrastructure Invariants

```
I-01: IRSA (AWS) and Workload Identity (GCP) always enabled.
      Pods NEVER have hardcoded cloud credentials.

I-02: Terraform state always remote.
      NEVER terraform.tfstate in the repository.

I-03: Secrets always in Secrets Manager / Secret Manager.
      NEVER passwords in committed tfvars.

I-04: Docker images always without embedded models.
      Models are downloaded via init container at startup.

I-05: Docker image tags always immutable in ECR/Artifact Registry.
      NEVER overwrite an existing tag.
```

### ML Serving Invariants

```
I-06: uvicorn --workers = 1 in all K8s pods.
      No exceptions. Concurrency = ThreadPoolExecutor + HPA.

I-07: HPA only with CPU as the metric.
      No memory, no custom metrics, only CPU.

I-08: Model inference in FastAPI always async (run_in_executor).
      NEVER a synchronous call in an async endpoint.

I-09: Classification threshold documented and justified.
      If not 0.5, the ADR explains why and what value was chosen.
```

### Model Quality Invariants

```
I-10: Minimum production metric threshold defined per service.
      Any model below that threshold is not promoted.

I-11: Fairness check before every deploy (DIR >= 0.80 per protected attribute).
      NEVER deploy without verifying fairness.

I-12: SHAP values in ORIGINAL feature space.
      NEVER in transformed space (post-encoding columns).

I-13: Primary metric sanity check (detect data leakage).
      If metric > [suspiciously high threshold], investigate leakage before promoting.
```

### Documentation Invariants

```
I-14: Every non-trivial architectural decision has an ADR.
      "Non-trivial" = decision with evaluated alternatives and trade-offs.

I-15: Costs documented with real dates (not generic estimates).
      ADRs and READMEs contain real measured numbers.

I-16: Production problems documented with evidence.
      "Service latency was [X]ms with [N] workers" — always with measured data.
```

---

## 19. SUCCESS METRICS BY DIMENSION

### Latency SLAs (Fill with Real Values)

```
{ServiceA} (idle):  P50 < [N]ms, P95 < [N]ms
{ServiceB} (idle):  P50 < [N]ms, P95 < [N]ms
{ServiceC} (idle):  P50 < [N]ms, P95 < [N]ms
```

### Availability SLAs

```
Error rate under peak load ([N] users): < 1%
Drift detection CronJob:                ✅ [X]/7 successful last 7 days
Health probe passage:                   ✅ No restarts in last [N] days
```

### Model Quality Gates (Per Service)

```
{ServiceA}:  [primary_metric] >= [X], [secondary_metric] >= [X], DIR >= 0.80
{ServiceB}:  [primary_metric] >= [X], [secondary_metric] >= [X]
{ServiceC}:  [primary_metric] >= [X] and < [leakage_threshold]
```

### Test Coverage

```
Unit + Integration:  >= 90% lines, >= 80% branches
Load tests:          Validated on both clouds with [N] concurrent users
Regression tests:    Data leakage, SHAP zeros, SHAP consistency, fairness
```

---

## 20. AGENT SPECIFICATION: WHAT TO BUILD AND WHAT TO TARGET

### 20.1 The Agent System — Proposed Architecture

```
LAYER 1: ORCHESTRATOR (plans which agents to activate)
  → Receives: "create a new ML service for [business problem]"
  → Determines: which specialist agents are needed and in what order
  → Manages: task dependencies (cannot deploy before training completes)

LAYER 2: SPECIALIST AGENTS
  ├── Agent-DataValidator    Creates Pandera schemas for new datasets
  ├── Agent-MLTrainer        Sets up the training pipeline, selects model
  ├── Agent-APIBuilder       Generates FastAPI app with async inference
  ├── Agent-DockerBuilder    Creates optimized Dockerfile (no model, with init container)
  ├── Agent-K8sBuilder       Generates K8s manifests (deployment, HPA, service, ingress)
  ├── Agent-TerraformBuilder Creates/modifies IaC for new resources
  ├── Agent-CICDBuilder      Configures GitHub Actions workflows
  ├── Agent-MonitoringSetup  Adds Prometheus metrics, Grafana dashboards, alerts
  ├── Agent-DriftSetup       Configures drift detection (PSI thresholds, CronJob)
  ├── Agent-DocumentationAI  Generates ADRs, READMEs, runbooks
  └── Agent-TestGenerator    Generates unit, integration, and regression tests

LAYER 3: MAINTENANCE AGENTS (always running)
  ├── Agent-DriftMonitor     Monitors PSI scores, triggers alerts
  ├── Agent-RetrainingAgent  Executes retraining when drift is detected
  ├── Agent-CostAuditor      Reviews costs against budget
  └── Agent-DocUpdater       Keeps documentation in sync with code
```

### 20.2 Mandatory Context for Each Agent

Any agent working on this template must have access to:

```
IMMUTABLE KNOWLEDGE (must be in the agent's system prompt):
  1. The complete list of ADRs with their decisions (section 14)
  2. The system invariants (section 18)
  3. The rules in AGENTS.md
  4. The exact technology stack (section 4)
  5. The mandatory K8s patterns (section 6)

DYNAMIC KNOWLEDGE (must be queried each session):
  1. Current deployment state (kubectl get pods)
  2. Current model versions in production (MLflow Registry)
  3. Current PSI scores (Prometheus query)
  4. Current month's costs (billing dashboard)
  5. Open GitHub Issues related to drift/errors
```

### 20.3 Checklist for Building a New ML Service

An agent building a new ML service must execute these steps in order:

```
PHASE 1: DATA AND VALIDATION (Agent-DataValidator)
□ Define the Pandera schema for the dataset (classes + types + ranges)
□ Implement validate_data.py with fail-fast logic
□ Identify if the dataset has temporal data → review for leakage
□ Create background data for SHAP (50 representative samples)
□ Version data with DVC and configure remote GCS/S3

PHASE 2: TRAINING PIPELINE (Agent-MLTrainer)
□ Implement FeatureEngineer (X → X_transformed)
□ Define the model (with justification of the choice)
□ Implement the trainer with these mandatory steps:
  1. load_data() + Pandera validation
  2. engineer_features()
  3. split_train_val_test() (no temporal leakage if dates exist)
  4. cross_validate()
  5. evaluate() with optimal threshold
  6. fairness_check() (DIR >= 0.80)
  7. save_artifacts() with SHA256
  8. log_to_mlflow()
  9. quality_gates()
□ Configure Optuna for hyperparameter tuning (minimum 50 trials)
□ Define service-specific quality gates
□ Create MLflow experiment and Model Registry entry

PHASE 3: SERVING API (Agent-APIBuilder)
□ Implement FastAPI app with:
  □ Pydantic schemas (request + response)
  □ ThreadPoolExecutor for inference (NEVER synchronous in async endpoint)
  □ /predict endpoint with Pandera input validation
  □ /predict?explain=true with SHAP KernelExplainer (if model requires it)
  □ /health endpoint (liveness + readiness)
  □ /metrics endpoint (Prometheus)
  □ Metrics: request_total, latency_histogram, prediction_score_distribution
□ Define predict_proba_wrapper if using SHAP (original feature space)
□ API tests: test_predict_valid_input, test_predict_invalid_schema, test_health

PHASE 4: CONTAINERIZATION (Agent-DockerBuilder)
□ Dockerfile with:
  □ python:3.11-slim as base
  □ No embedded models (downloaded via init container)
  □ pip install with --no-cache-dir
  □ Non-root user
  □ CMD ["uvicorn", "app.main:app", "--host=0.0.0.0", "--port=8000"]
    (no --workers — K8s manages scale)
□ .dockerignore: exclude models/, data/raw/, *.pyc, __pycache__, tests/

PHASE 5: KUBERNETES (Agent-K8sBuilder)
□ deployment.yaml:
  □ resources.requests.cpu and resources.limits.cpu
  □ Init container for model download (emptyDir volume)
  □ Liveness probe: /health, delay=30s
  □ Readiness probe: /health, delay=30s, failureThreshold=3
  □ IRSA annotation (AWS) or Workload Identity annotation (GCP) on ServiceAccount
□ hpa.yaml:
  □ metrics: CPU ONLY (no memory)
  □ target: 50-70% depending on model weight
  □ behavior.scaleDown.stabilizationWindowSeconds: 300
  □ behavior.scaleUp.stabilizationWindowSeconds: 0
□ service.yaml: ClusterIP
□ Add to kustomization.yaml in base/ and create patches in overlays/gcp/ and overlays/aws/

PHASE 6: INFRASTRUCTURE (Agent-TerraformBuilder)
□ Add new repository in registry.tf (ECR or Artifact Registry)
□ Update bucket prefixes if the service needs its own namespace in S3/GCS
□ Add IAM permissions if the service needs access to additional resources
□ terraform plan + terraform apply

PHASE 7: CI/CD (Agent-CICDBuilder)
□ Add the service to the build matrix in ci.yml
□ Create workflow deploy-{service}.yml (GCP and AWS)
□ Add the service to the drift-detection.yml matrix
□ Create retrain-{service}.yml with the service's quality gates
□ Configure required GitHub Secrets

PHASE 8: MONITORING AND OBSERVABILITY (Agent-MonitoringSetup)
□ Prometheus: verify /metrics exports the service's metrics
□ Grafana: create a dashboard for the new service (latency, error rate, predictions)
□ AlertManager: configure P1-P4 alerts for the new service
□ Pushgateway: verify the drift CronJob can push metrics

PHASE 9: DRIFT DETECTION (Agent-DriftSetup)
□ Define PSI thresholds per feature (with domain reasoning)
□ Determine if standard PSI or alternative metric is needed (e.g., YoY for time series)
□ Create drift_detection.py for the new service
□ Configure K8s CronJob YAML
□ Configure heartbeat alert in AlertManager

PHASE 10: DOCUMENTATION (Agent-DocumentationAI)
□ Create ADR for every non-trivial architectural decision
□ Create service README.md with: purpose, features, model, metrics, endpoints
□ Update AGENTS.md if there are new service-specific invariants
□ Update the template's main README with the new service
□ Create runbook for the new service (P1-P4 with executable commands)

PHASE 11: FINAL TESTING (Agent-TestGenerator)
□ Service-specific regression tests (e.g., leakage check, SHAP zeros)
□ Load test with Locust: [N] users, 2 minutes, verify P95 < SLA
□ End-to-end test: Terraform → K8s deploy → API prediction → drift detection
```

### 20.4 Acceptance Criteria for "Production-Ready"

A service is production-ready in this template when ALL of these are met:

```
TECHNICAL:
□ Test coverage >= 90%
□ Load test passed (< 1% errors under 100 concurrent users)
□ P95 latency within the documented SLA
□ Primary metric >= defined quality gate
□ Fairness check passed (DIR >= 0.80 per protected attribute)

OPERATIONAL:
□ Drift detection configured and CronJob running
□ Heartbeat alert configured in AlertManager
□ Budget alert updated to include the new service
□ IRSA/Workload Identity configured (zero hardcoded credentials)
□ Rollback procedure documented in the runbook

DOCUMENTATION:
□ ADR for each non-trivial architectural decision
□ Complete README with real production metrics
□ Executable runbook with P1-P4 commands
□ AGENTS.md updated with new service invariants
```

### 20.5 Anti-Patterns That Agents Must Detect and Correct

A maintenance agent reviewing existing code must alert on:

```
DETECTOR-01: uvicorn --workers N in any Dockerfile or deployment YAML
  → Action: Change to 1 worker, add ThreadPoolExecutor in the endpoint

DETECTOR-02: Memory HPA in any HorizontalPodAutoscaler
  → Action: Remove the memory metric, verify the HPA scales correctly

DETECTOR-03: model.predict() called directly in an async endpoint
  → Action: Wrap in run_in_executor with ThreadPoolExecutor

DETECTOR-04: shap.TreeExplainer with any ensemble/pipeline/stacking
  → Action: Change to KernelExplainer with predict_proba_wrapper

DETECTOR-05: == in requirements.txt (except for testing tools)
  → Action: Change to ~= for ML packages

DETECTOR-06: Unrealistically high primary metric (> suspicion threshold)
  → Action: Investigate data leakage, review feature engineering

DETECTOR-07: SHAP background data containing only one class
  → Action: Replace with a representative sample (matching production distribution)

DETECTOR-08: PSI calculated with uniform bins (not quantile-based)
  → Action: Refactor to use quantile bins from the reference distribution

DETECTOR-09: Drift detection without a heartbeat alert
  → Action: Add AlertManager alert to detect silently broken CronJobs

DETECTOR-10: terraform.tfstate in the git repository
  → Action: Move to remote state immediately, rotate all exposed secrets

DETECTOR-11: Models included in the Docker image
  → Action: Remove from Dockerfile, implement init container pattern

DETECTOR-12: No quality gates before kubectl rollout restart in a retraining pipeline
  → Action: Add all gates (primary metric, secondary metric, fairness, latency) before deploy
```

---

## EXECUTIVE SUMMARY FOR AGENTS

An agent working on this template is building or maintaining a real production MLOps system with these characteristics:

**What it is**: A set of ML services in GCP + AWS with infrastructure as code, automatic drift detection, production-grade SHAP explainability, complete CI/CD, and ADRs documenting every non-trivial decision.

**What it is not**: An academic project, a Jupyter notebook collection, or a demo with no real production infrastructure.

**The golden rule**: If it doesn't have an ADR justifying the decision, a test verifying the behavior, and a metric measuring the impact — it is not done.

**The quality standard**: The code must withstand review by a Staff Engineer without finding K8s anti-patterns, unjustified decisions, or violated invariants.

**The ultimate objective**: A template that answers the question "Can you operate ML systems in production at enterprise level?" with concrete, measurable evidence.