# v1.11.0 — Close ADR-016 R2 backlog + ADR-018/019 + OSS package

See [CHANGELOG.md §1.11.0](https://github.com/DuqueOM/ML-MLOps-Production-Template/blob/main/CHANGELOG.md#1110---2026-04-28) for the full breakdown.

## Highlights

- **ADR-016 R2 remediation backlog closed** — PR-R2-1..R2-12 all materially shipped; PR-R2-9b alert-firing scoped as explicit follow-on
- **GCP/AWS Terraform parity tightened**: GCP secrets / logging / kms.tf live layer + 14 parity contract tests + bootstrap split
- **ADR-018 Operational Memory Plane Phase 0** — scope + non-goals + threat model ratified; runtime phases scoped as follow-on PRs
- **ADR-019 Agentic CI Self-Healing Phase 0** — policy YAMLs (`templates/config/ci_autofix_policy.yaml`, `templates/config/model_routing_policy.yaml`) + 10 contract invariants; runtime scripts deferred
- **Model routing recommendation** added to README with explicit `verified_at` honesty caveat
- **OSS package complete**: NOTICE + DCO.md + .github/CODEOWNERS
- **CI hardening**: tfsec `check` block fix, black drift, F541, policy-tests numpy isolation

## Test surface delta from 1.10.0

- +33 contract tests
- +13 policy tests over scaffolded output

## Status at tag

All CI workflows green:

- ✅ Validate Templates
- ✅ CI — Examples, Unit Tests & Coverage
- ✅ Policy Tests (D-XX anti-patterns)

## Known follow-ons (scoped, not regressions)

- PR-R2-9b — alert firing via Prometheus + Pushgateway (Stage 2 of PR-R2-9)
- ADR-018 Phases 1–6 — canonical contracts → ingestion → storage → integration → shadow→enforced → hardening
- ADR-019 Phases 1–6 — context collection → classification → verifier helpers → workflow scaffold → AUTO enablement → CONSULT lane