---
trigger: always_on
description: Core MLOps conventions, technology stack, and ADR-driven development patterns
---

# MLOps Conventions

## Technology Stack

- **Python**: 3.11+ with type hints on all public functions
- **ML Core**: scikit-learn, XGBoost, LightGBM, pandas, numpy, scipy, Optuna
- **Serving**: FastAPI + uvicorn (single worker in K8s), Pydantic for schemas
- **Data Validation**: Pandera (DataFrameModel, `@check_types`)
- **Explainability**: SHAP KernelExplainer (never TreeExplainer for ensembles)
- **Drift**: Evidently reports, PSI with quantile-based bins, Prometheus Pushgateway
- **Tracking**: MLflow (experiments, model registry, artifact store)
- **Monitoring**: Prometheus + Grafana + AlertManager
- **Infrastructure**: Terraform >= 1.7, GKE + EKS, GCS + S3, Cloud SQL + RDS
- **CI/CD**: GitHub Actions
- **Container**: Docker multi-stage builds, non-root USER, HEALTHCHECK
- **Data Versioning**: DVC with GCS + S3 remotes

## Dependency Pinning

Always use compatible release operator `~=` for ML packages:
```
scikit-learn ~= "1.5.0"   # Allows 1.5.x but not 1.6.0
numpy        ~= "1.26.0"  # numpy 2.x silently corrupts joblib models
```

Never use `==` (causes resolution conflicts) or bare `>=` (allows breaking changes).

## ADR-Driven Development

Every non-trivial architectural decision MUST have an ADR in `docs/decisions/`:
- Use the template at `templates/docs/decisions/adr-template.md`
- Include: Context, Options Considered, Decision, Rationale, Consequences, Revisit When
- Number sequentially: `001-decision-name.md`, `002-decision-name.md`

## Code Quality Standards

- **Coverage**: >= 90% lines, >= 80% branches in `src/`
- **Type hints**: Required on all public functions
- **Docstrings**: Google style
- **Linting**: flake8, black, isort, mypy
- **Testing**: pytest for unit/integration, Locust for load tests

## Engineering Calibration

Before implementing any component, evaluate whether the complexity is proportional to the problem:
- 2-3 models → CronJob + GitHub Actions (not Airflow/Prefect)
- In-memory DataFrames → Pandera (not Great Expectations)
- Simple drift → PSI (not a full feature store)
- Small team → README + ADRs (not Confluence + Notion + Backstage)

Document the scale reasoning in the corresponding ADR.

## File Organization

```
{ServiceName}-{Purpose}/
├── app/              # FastAPI serving layer
├── src/{service}/    # Core ML logic
│   ├── training/     # train.py, features.py, model.py
│   ├── monitoring/   # drift_detection.py, business_kpis.py
│   └── schemas.py    # Pandera DataFrameModel
├── data/
│   ├── raw/          # DVC tracked
│   └── reference/    # Background data for SHAP + drift
├── models/           # Artifacts (gitignored, stored in GCS/S3)
├── tests/            # test_training.py, test_api.py, test_explainer.py
├── Dockerfile
└── requirements.txt
```
