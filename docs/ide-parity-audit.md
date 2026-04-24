# IDE Parity Audit — Windsurf / Cursor / Claude Code

Date: 2026-04-24 (v1.9.0)

AGENTS.md §IDE Parity Matrix claims the template's invariants (D-01..D-30)
are mirrored across three IDE-specific rule directories:

- `.windsurf/rules/` — 14 files, primary source
- `.cursor/rules/` — 8 files (glob-scoped)
- `.claude/rules/` — 8 files (path-scoped)

This audit confirms the state after v1.9.0 and documents where each
invariant has primary + secondary coverage.

## Coverage matrix

Legend: ✓ = canonical coverage, · = reference/link to canonical, — = not in scope

| Invariant | .windsurf/ | .cursor/ | .claude/ |
|-----------|------------|----------|----------|
| **D-01** workers | `04a-python-serving.md` ✓ | `03-python-serving.mdc` · | `01-serving.md` · |
| **D-02** memory HPA | `02-kubernetes.md` ✓ | `02-kubernetes.mdc` · | `03-kubernetes.md` · |
| **D-03** async predict | `04a-python-serving.md` ✓ | `03-python-serving.mdc` · | `01-serving.md` · |
| **D-04** SHAP KernelExplainer | `04a-python-serving.md` ✓ | `03-python-serving.mdc` · | `01-serving.md` · |
| **D-05** `~=` pinning | `01-mlops-conventions.md` ✓ | `01-mlops-conventions.mdc` · | — |
| **D-06..D-09** | `09-monitoring.md`, `04b-python-training.md` ✓ | `04-python-training.mdc` · | `02-training.md` · |
| **D-10** tfstate | `03-terraform.md` ✓ | — | `04-terraform.md` · |
| **D-11** model-in-image | `07-docker.md`, `02-kubernetes.md` ✓ | `05-docker.mdc` · | `01-serving.md` · |
| **D-12** quality gates | `04b-python-training.md` ✓ | `04-python-training.mdc` · | `02-training.md` · |
| **D-13..D-16** EDA/data | `11-data-eda.md`, `08-data-validation.md` ✓ | `06-data-eda.mdc` · | `06-data-eda.md` · |
| **D-17..D-19** secrets/SBOM | `12-security-secrets.md` ✓ | `07-security-secrets.mdc` · | `07-security-secrets.md` · |
| **D-20..D-22** closed-loop | `13-closed-loop-monitoring.md` ✓ | `08-closed-loop.mdc` · | `08-closed-loop.md` · |
| **D-23** probe split | `02-kubernetes.md`, `04a-python-serving.md` ✓ | `02-kubernetes.mdc` (v1.7.1 note) | `01-serving.md` · (v1.9.0) |
| **D-24** SHAP cache | `04a-python-serving.md` ✓ | `03-python-serving.mdc` (v1.7.1 note) | `01-serving.md` · (v1.9.0) |
| **D-25** graceful shutdown | `02-kubernetes.md` ✓ | `02-kubernetes.mdc` (v1.7.1 note) | `03-kubernetes.md` · (v1.9.0) |
| **D-26** env promotion | `05-github-actions.md` ✓ | `01-mlops-conventions.mdc` · (v1.9.0) | `03-kubernetes.md` · (v1.9.0) |
| **D-27** PDB | `02-kubernetes.md` ✓ | `02-kubernetes.mdc` (v1.7.1 note) | `03-kubernetes.md` · (v1.9.0) |
| **D-28** API contract | `14-api-contracts.md` ✓ | `01-mlops-conventions.mdc` · (v1.9.0) | `01-serving.md` · (v1.9.0) |
| **D-29** Pod Security Standards | `02-kubernetes.md` ✓ | `01-mlops-conventions.mdc` · (v1.9.0) | `03-kubernetes.md` · (v1.9.0) |
| **D-30** SBOM attestation | `05-github-actions.md` (v1.8.1 note); AGENTS.md ✓ | `01-mlops-conventions.mdc` · (v1.9.0) | `03-kubernetes.md` · (v1.9.0) |

## Dynamic Behavior Protocol (ADR-010)

| Location | State |
|----------|-------|
| `AGENTS.md §Dynamic Behavior Protocol` | canonical |
| `.windsurf/rules/01-mlops-conventions.md §Dynamic Behavior Protocol` | ✓ |
| `.cursor/rules/01-mlops-conventions.mdc §Dynamic Behavior Protocol` | ✓ (v1.9.0 parity) |
| `.claude/rules/01-serving.md footer` | referenced |

## Parity principles applied

1. **One canonical source per invariant**: the `.windsurf/` file that
   matches the invariant's primary domain (e.g., K8s invariants live
   in `02-kubernetes.md`). Cursor + Claude rules either restate or
   reference, avoiding three-way drift.
2. **Abbreviated rule files elsewhere**: Cursor `.mdc` and Claude
   `.md` rules are deliberately short — they carry the invariant IDs
   and a one-line fix; full details are in AGENTS.md + windsurf.
3. **Anti-pattern table coverage**: ONLY AGENTS.md and
   `.windsurf/rules/01-mlops-conventions.md` carry the full D-01..D-30
   table; the Cursor `01-mlops-conventions.mdc` duplicates it
   (Cursor users lose AGENTS.md globbing); Claude rules reference the
   table in AGENTS.md.
4. **Rule 14 (API contracts)**: not ported to Cursor/Claude as a
   dedicated file; the invariant ID + commands are referenced from
   the main conventions file and `.claude/01-serving.md`.

## Gaps accepted

- **`.claude/rules/`** does not have a dedicated `09-github-actions.md`
  — deploy gate invariants (D-26) live in `03-kubernetes.md` +
  AGENTS.md. Acceptable: Claude Code's path-scoped rules target
  workflow files under `.github/` via path globs, not a dedicated rule.
- **`.cursor/rules/03-terraform.mdc`** does not exist — Terraform
  guidance is mentioned in `01-mlops-conventions.mdc` and covered by
  `.windsurf/rules/03-terraform.md`. Adding a Cursor Terraform rule
  is low priority (Cursor users typically work in Python contexts).

## Next review trigger

When any of:
- A new invariant (D-31+) is added to AGENTS.md
- A rule gets >10 lines of new content in `.windsurf/`
- Cursor / Claude Code change their rule-file format
- Users report that one IDE is behaving inconsistently with the others

## See also

- AGENTS.md §IDE Parity Matrix — canonical mapping
- This file = audit ≠ source of truth; AGENTS.md remains canonical
