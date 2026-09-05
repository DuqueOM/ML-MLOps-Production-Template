# Documentation Path Reference Gate

**Status**: Active enforcement (2026-09-04+)
**Enforcement**: `scripts/check_doc_path_refs.py` + `doc-path-refs` job in `.github/workflows/validate-templates.yml` + pre-commit hook `doc-path-refs`
**Baseline**: `.doc-path-baseline.yml`
**Related**: ADR-030 (Copier scaffolding migration), ADR-031 (rule 16 doc coherence), `docs/governance/cicd-templates-drift.md`

## What this gate enforces

Every repo-relative path named inside backticks in living documentation —
or inside a comment in a tracked `.py`, `.yml`, `.yaml`, `.sh` or `Makefile`
— must resolve to a file or directory that exists.

The code-comment half was added on 2026-09-04. The gate shipped scanning
`.md`/`.txt` only, which left the then-current .security-baselines/tfsec.yml
justifying three suppressed HIGH findings against a directory ADR-030 had
deleted, and
a set of test comments describing a layout that had not existed since June.
Measured before widening: **15 unresolved paths across 309 code files** —
small enough for a hard gate.

## Why this gate exists

The Copier migration (ADR-030, commit `fe89e92`, 2026-06-30) relocated
the entire scaffolder payload from `templates/{cicd,k8s,monitoring,docs,
eda,infra,common_utils,scripts}` to `templates/service/*`.

It updated every reference that **executes**: the runtime workflows,
`Makefile`, `.github/CODEOWNERS`, the Kustomize overlays, two contract
tests, `scripts/verify_enterprise_adoption.py`, and
`scripts/check_cicd_template_drift.py` itself — 14 files. Those break
loudly when a path is wrong, so they got fixed.

It updated **none of the prose**. Thirty documents kept pointing at
directories that no longer existed:

| Surface | Examples |
|---|---|
| Root docs | `AGENTS.md`, `README.md`, `CONTRIBUTING.md`, `MIGRATION.md`, `CLAUDE.md` |
| Runbooks | `gcp-wif-setup.md`, `aws-irsa-setup.md`, `terraform-state-bootstrap.md`, `closed-loop-sla.md`, `digest-pin-init-image.md` |
| Governance | `docs/security/compliance-mapping.md`, `docs/PROGRESSION.md` |
| Machine-readable | `llms.txt` |

Nothing noticed, because until this gate no check in the repository
verified that a path named in a document exists.

The failure then compounded. Two audit rounds later, commit `f219895`
("feat: add Agent-QualityGuardian + R11 audit remediation", 2026-07-08)
copied the dead templates/cicd/ path **into the audit tooling itself**:

- `agentic/rules/18-audit-quality.md` scoped its glob list to
  `templates/cicd/**`, a directory that had not existed for eight days
  shy of two months;
- `agentic/workflows/audit-quality.md` ran its Q-01 unpinned-action sweep
  over templates/cicd with `2>/dev/null`, so the missing directory was
  silent.

Both propagated across three adapter surfaces (`agentic/`, `.devin/`,
`templates/service/agentic/`) via the normal sync. The rule that defines
the repository's quality anti-patterns was itself pointing at nothing,
and reported green the entire time.

## The lesson this gate encodes

**Documentation that names a path is making a checkable claim.** The
migration was validated by execution, so everything executable survived
and everything declarative rotted. A repository that enforces byte-level
drift gates on vendored scripts, digest pinning on container images and
SHA pinning on actions had no equivalent check on the claims its own
documents make about its own layout.

## The dual-perspective model

A reference is valid if it resolves from **either** root:

1. the repository root — the perspective of the template repo's docs;
2. `templates/service/` — the perspective of a *generated service*.

The second root is not a convenience. `agentic/**` is mirrored
byte-for-byte into `templates/service/agentic/` (enforced by
`check_vendored_runtime_drift.py`), and `AGENTS.md` / `AGENT_CONTEXT.md`
are vendored verbatim. One text has to serve both readers: the bare form
scripts/refresh_contract.py is correct prose in a rule that executes
inside a scaffolded service, even though this repo only has that file at
`templates/service/scripts/refresh_contract.py`.

Documents that ship into a service resolve against both roots. Documents
that never leave the template repo resolve against the repo root only.

## What this gate does NOT enforce

- **Frozen records.** `docs/decisions/`, `docs/audit/`, `releases/`,
  `CHANGELOG.md` and `VALIDATION_LOG.md` are excluded. An ADR describing
  the tree as it stood in May 2026 is *supposed* to name paths that have
  since moved; rewriting them would falsify the record. This is the same
  reasoning that keeps historical audit snapshots immutable (ADR-045).
- **Non-literal tokens.** Placeholders (`<id>`, `{service_slug}`), globs,
  brace sets, shell arguments, `file:line` suffixes, URL fragments and
  ellipses are illustrative, not claims about the tree.
- **Paths outside this repo's top-level directories.** A runbook naming
  `src/main.py` is describing the adopter's tree, not ours.
- **Link targets in Markdown link syntax.** In documents, only backticked
  code spans are scanned. Extending to `[text](path)` is a natural
  follow-up and would live in the same script; the `Link Check` job in
  `docs-quality.yml` covers those today.
- **String literals in code.** Only comments are scanned. A path built at
  runtime is program logic, not a claim, and matching it would report
  every `Path(...) / "templates"` expression.
- **Glob and brace shapes.** `deploy-*.yml` and `deploy-{gcp,aws}.yml` are
  legitimate shorthand. A negative lookahead drops them rather than
  reporting the truncated prefix `.../deploy-` as dead — the false
  positive that this widening produced on its first run.
- **Stand-ins and files that must not exist.** Uppercase placeholders
  (`ADR-XXX.md`) and any `*.local.*` path are excluded; the latter is
  gitignored by contract, so a comment naming one is describing something
  that is *supposed* to be absent.
- **Paths written as plain prose.** This is a deliberate convention, not
  a hole: a code span asserts *this resolves today, from this document's
  perspective*. A document discussing a path that has been removed, or
  illustrating a form that is only valid from the other root — this one
  does both — names it without code formatting. That is how you write a
  path you are talking *about* rather than pointing *at*. Do not reach
  for the baseline instead: the baseline is for references that are
  still making a live claim.

## Baseline contract

`.doc-path-baseline.yml` carries the references that were already broken
when the gate landed. The format mirrors `.security-baselines/` (see
`scripts/check_baselines_expiry.py`): every entry is **explicit, dated
and reviewable**, with a `reason` and an `expiry`.

Three failure modes are enforced:

| Condition | Result |
|---|---|
| A path is unresolved and not baselined | fail — the new-defect case |
| A baselined entry is past its `expiry` | fail — forces a fix or a fresh justification |
| A baselined entry now resolves | fail — the baseline may not outlive its reason |

Entries carry one of two classifications, which are not equivalent:

- **`runtime-artifact`** — the file really is created while a generated
  service runs. The reference is correct; the file simply is not tracked.
  Long expiry.
- **`unimplemented`** — the documentation promises something never built.
  These are defects with a doc-shaped symptom: an agent following the
  workflow reaches for a file that is not there. Short expiry on purpose.

New dead paths are **never** baselined. They fail on the PR that
introduces them, which is precisely the failure mode that would have
stopped `f219895`.

## Operational cost

595 documents plus 330 code files, one regex pass each, and a filesystem
`exists()` per candidate token. Tens of milliseconds on a CI runner,
dominated by Python startup. The pre-commit hook fires on `*.md`, `*.txt`,
`*.py`, `*.yml`, `*.yaml`, `*.sh`, any `Makefile`, and the baseline.

## Revisit triggers

- If Markdown link targets are added to the scan, this document and the
  script docstring change together.
- If the repository ever drops the byte-identical vendoring of `agentic/`
  into `templates/service/agentic/`, the dual-perspective model collapses
  to a single root and the `DUAL_PREFIXES` list should be deleted rather
  than maintained.
- When `.doc-path-baseline.yml` reaches zero entries, the baseline file
  and its parsing code can be removed and the gate becomes unconditional.
