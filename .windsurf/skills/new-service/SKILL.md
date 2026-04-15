---
description: Create a new ML service from scratch using the template system
whenToUse: When building a new ML microservice for a business problem
---

# Create New ML Service

This skill guides the creation of a complete, production-ready ML service using the template system. Follow each phase in order — do not skip phases.

## Phase 1: Define the Service

Before writing code, answer these questions:
1. **Business problem**: What does this service predict/classify/estimate?
2. **Dataset**: Source, size, features, target distribution
3. **Model type**: Classification, regression, NLP, time series?
4. **Scale**: Expected request volume, latency requirements
5. **Explainability**: Is SHAP required? (High-stakes decisions = yes)

Create the service directory:
```bash
export SERVICE_NAME="{ServiceName}-{Purpose}"   # e.g., "BankChurn-Predictor"
export SERVICE_SLUG="{service_slug}"             # e.g., "bankchurn"
cp -r templates/service/ ${SERVICE_NAME}/
```

## Phase 2: Data Validation (Agent-DataValidator)

1. Define Pandera schema in `src/{service}/schemas.py`
2. Implement `data/validate_data.py` with fail-fast logic
3. Check for temporal data → review for leakage
4. Create background data for SHAP (50 representative samples)
5. Version data with DVC: `dvc add data/raw/{dataset}.csv`

## Phase 3: Training Pipeline (Agent-MLTrainer)

1. Implement `FeatureEngineer` class in `src/{service}/training/features.py`
2. Define model in `src/{service}/training/model.py`
3. Implement `Trainer.run()` in `src/{service}/training/train.py`:
   - load_data() + Pandera validation
   - engineer_features()
   - split_train_val_test()
   - cross_validate()
   - evaluate() with optimal threshold
   - fairness_check() (DIR >= 0.80)
   - save_artifacts() with SHA256
   - log_to_mlflow()
   - quality_gates()
4. Configure Optuna (minimum 50 trials)
5. Create MLflow experiment

## Phase 4: Serving API (Agent-APIBuilder)

1. Define Pydantic schemas in `app/schemas.py`
2. Implement FastAPI app in `app/main.py`:
   - `/predict` with ThreadPoolExecutor
   - `/predict?explain=true` with SHAP
   - `/health` endpoint
   - `/metrics` for Prometheus
3. Define `predict_proba_wrapper` for SHAP
4. Write API tests

## Phase 5: Containerization (Agent-DockerBuilder)

1. Customize `Dockerfile` (base image, dependencies)
2. Verify `.dockerignore` excludes models/, data/raw/, tests/
3. Build and test locally:
   ```bash
   docker build -t ${SERVICE_SLUG}:dev .
   docker run -p 8000:8000 ${SERVICE_SLUG}:dev
   curl localhost:8000/health
   ```

## Phase 6: Kubernetes (Agent-K8sBuilder)

1. Create `k8s/base/{service}-deployment.yaml` from template
2. Create `k8s/base/{service}-hpa.yaml` (CPU-only, 50-70%)
3. Create `k8s/base/{service}-service.yaml`
4. Add to `k8s/base/kustomization.yaml`
5. Create patches in `k8s/overlays/gcp/` and `k8s/overlays/aws/`

## Phase 7: Infrastructure (Agent-TerraformBuilder)

1. Add container repository in `infra/terraform/{cloud}/registry.tf`
2. Update bucket prefixes if needed
3. Add IAM permissions for new service
4. `terraform plan` → verify → `terraform apply`

## Phase 8: CI/CD (Agent-CICDBuilder)

1. Add service to build matrix in `.github/workflows/ci.yml`
2. Add service to drift detection matrix
3. Create `retrain-{service}.yml` with quality gates
4. Configure required GitHub Secrets

## Phase 9: Monitoring (Agent-MonitoringSetup)

1. Verify `/metrics` exports service-specific metrics
2. Create Grafana dashboard from template
3. Configure P1-P4 alerts in AlertManager
4. Verify Pushgateway connectivity for drift metrics

## Phase 10: Drift Detection (Agent-DriftSetup)

1. Define PSI thresholds per feature with domain reasoning
2. Implement `drift_detection.py`
3. Create K8s CronJob for scheduled drift checks
4. Configure heartbeat alert (48h timeout)

## Phase 11: Documentation (Agent-DocumentationAI)

1. Create ADR for model selection and any non-trivial decisions
2. Write service `README.md`
3. Update root `AGENTS.md` with new service
4. Create runbook with P1-P4 commands
5. Update main `README.md`

## Phase 12: Testing (Agent-TestGenerator)

1. Data leakage regression test
2. SHAP consistency + non-zero + feature space tests
3. Quality gate test
4. Inference latency SLA test
5. Fairness test
6. Load test with Locust

## Acceptance Criteria

A service is production-ready when ALL of these pass:
- [ ] Test coverage >= 90%
- [ ] Load test < 1% errors under 100 concurrent users
- [ ] P95 latency within SLA
- [ ] Primary metric >= quality gate
- [ ] Fairness DIR >= 0.80
- [ ] Drift detection configured + CronJob running
- [ ] Heartbeat alert configured
- [ ] IRSA/Workload Identity configured
- [ ] ADRs written for all non-trivial decisions
- [ ] README with real metrics
- [ ] Runbook with executable commands
