---
paths:
  - "eda/**/*"
  - "**/notebooks/**/*.ipynb"
  - "**/eda_*.py"
---

# EDA Rules

## Invariants (D-13 to D-16)
- **D-13**: Never EDA on production data. Copy to `data/raw/` first.
- **D-14**: Pandera `Check.in_range` uses observed ranges from `eda/artifacts/01_dtypes_map.json`
- **D-15**: Phase 2 MUST produce `eda/artifacts/02_baseline_distributions.pkl` — this file is the drift CronJob input in production
- **D-16**: Every entry in `eda/artifacts/05_feature_proposals.yaml` must cite a `rationale`

## 6-phase pipeline (scripted in templates/eda/eda_pipeline.py)
0. Ingest + snake_case normalization
1. Structural profile
2. Univariate + baseline_distributions.pkl (**quantile bins** for PSI)
3. Correlations + VIF + feature ranking
4. Leakage HARD GATE (exit 1 if blocked features non-empty)
5. Feature proposals with rationale
6. Consolidation → schema_proposal.py (review, do NOT overwrite schemas.py)

## Required outputs
```
eda/
├── reports/     (00-04 + eda_summary.md)
├── artifacts/   (01_dtypes_map.json, 02_baseline_distributions.pkl, 03_ranking.csv, 05_feature_proposals.yaml)
└── notebooks/   (eda_<dataset>.ipynb)
```

See AGENTS.md (D-13 to D-16), ADR-004, `.windsurf/skills/eda-analysis/SKILL.md`, workflow `/eda`.
