---
trigger: glob
globs: ["**/eda/**", "**/notebooks/**/*.ipynb", "**/eda_*.py"]
description: Exploratory Data Analysis patterns — structure, isolation, and artifacts feeding drift detection
---

# EDA Rules

## Non-negotiable invariants

### D-13 — EDA sandbox isolation
- **Never** read from production data paths (`data/production/`, cloud buckets with live traffic).
- **Always** copy data to `data/raw/` before exploring. EDA must never write to prod paths.
- The service's `/predict` pipeline and the EDA pipeline MUST NEVER share file handles.

### D-14 — Schemas derived from observed ranges
- `src/{service}/schemas.py` must use `Check.in_range(min, max)` for numeric features.
- The `min`/`max` values come from `eda/artifacts/01_dtypes_map.json` (EDA phase 1).
- If EDA hasn't run, the Pandera schema is invalid.

### D-15 — Baseline distributions persisted
- EDA phase 2 MUST produce `eda/artifacts/02_baseline_distributions.pkl`.
- This file is consumed by the drift detection CronJob to compute PSI.
- **Missing this file breaks drift detection silently** — CI should fail if a service has a drift CronJob but no baseline.

### D-16 — Feature engineering with documented rationale
- Every entry in `eda/artifacts/05_feature_proposals.yaml` MUST have a `rationale` field.
- The rationale must reference EDA phase outputs (distribution shape, correlation, leakage check).
- `features.py` comments must cite the proposal entry that justifies each transformation.

## Structural conventions

### Required directory layout
```
eda/
├── reports/
│   ├── 00_ingest_report.md
│   ├── 01_profile.html
│   ├── 02_univariate.html
│   ├── 03_correlations.html
│   └── 04_leakage_audit.md
├── artifacts/
│   ├── 01_dtypes_map.json
│   ├── 02_baseline_distributions.pkl     # consumed by drift detection
│   ├── 03_feature_ranking_initial.csv
│   └── 05_feature_proposals.yaml          # consumed by features.py
└── notebooks/
    └── eda_<dataset_name>.ipynb
```

### Naming conventions
- Phase-numbered outputs: `NN_<description>.<ext>` (e.g., `01_profile.html`, `02_univariate.html`)
- All column names in output artifacts must be `snake_case`
- Notebooks named `eda_<dataset_name>.ipynb` — one notebook per dataset, not per phase

## Leakage gate (hard block)

EDA phase 4 outputs `eda/reports/04_leakage_audit.md` with a `BLOCKED_FEATURES` list.
If `BLOCKED_FEATURES` is non-empty:
- **Training pipeline MUST NOT consume those features**
- `features.py` must reject them via assertion
- Proceed to resolution BEFORE training — do not dismiss the audit

## DVC tracking
- `data/raw/*.csv|parquet` → DVC-tracked (input)
- `eda/artifacts/02_baseline_distributions.pkl` → DVC-tracked (cross-phase input)
- `eda/reports/*.html` → `.gitignore`'d (regenerable, large)

## Dependencies
- Required: `pandas`, `scipy`, `scikit-learn`, `pandera`, `matplotlib`
- Optional heavy: `ydata-profiling` (~500MB). Prefer lightweight mode unless dataset > 100k rows and visual polish matters.
- Never import from `app/` or `src/{service}/training/` — EDA is a leaf dependency.
