# AUDIT R11 — Auditoría Enterprise/ISO del Repositorio

- **Fecha**: 2026-07-07
- **Alcance**: repositorio completo `ML-MLOps-Production-Template` @ `main` (HEAD `734839c`, versión `0.21.0`)
- **Marco de referencia**: 23 dominios — 19 de auditoría enterprise (gobierno, trazabilidad, calidad, seguridad, dependencias, licencias, CI/CD, reproducibilidad, secretos, configuración, pruebas, documentación, versiones, incidentes, cambios, commits, supply chain, MLOps, evidencias) + 4 complementarios de perspectiva de arquitecto (observabilidad SLI/SLO/OTel, evaluación arquitectónica, deuda técnica, experiencia del desarrollador) — alineado con ISO/IEC 27001 A.8/A.14, NIST SSDF, CIS Software Supply Chain, OWASP SAMM
- **Método**: solo lectura — inspección de working tree, historial git, `gitleaks detect --no-git`, análisis de workflows y configuración. Ningún control fue ejecutado contra GitHub API en vivo; el estado SCM se evalúa contra su fuente de verdad documentada (`docs/governance/branch-protection.md`, ADR-026)

---

## Resumen ejecutivo

| # | Área | Estado | Riesgo | Evidencia clave | Recomendación |
|---|------|--------|--------|-----------------|---------------|
| 1 | Gobierno del repositorio | ⚠️ | Medio | CODEOWNERS con bus factor = 1 divulgado; `required_approving_review_count: 0`; firmas no requeridas | Onboarding de co-maintainer; subir reviews requeridas a ≥1 |
| 2 | Trazabilidad | ✅ | Bajo | Cadena issue→PR→merge→tag→release consistente; PRs numerados en historial | Sin observaciones mayores |
| 3 | Calidad de código | ✅ | Bajo | black/isort/flake8/mypy + pre-commit (8.8 KB de hooks); convención de 120 cols | Considerar Ruff para consolidar linters |
| 4 | Seguridad (secretos en código) | ✅ | Bajo | gitleaks: 0 hallazgos en archivos versionados (3 FP en `__pycache__` no versionado) | Añadir `__pycache__` al allowlist de `.gitleaks.toml` |
| 5 | Dependencias | ✅ | Bajo | Dependabot activo (4 ecosistemas); pinning `~=` universal; `constraints.txt` | Evaluar lockfile completo (`uv.lock`) para el template raíz |
| 6 | Licencias | ✅ | Bajo | Apache-2.0 + NOTICE + DCO.md | Sin observaciones |
| 7 | CI/CD | ✅ | Bajo | 13 workflows raíz + CI de servicio con tests, lint, gitleaks, tfsec, checkov, trivy, SBOM, cosign | Mantener; ver hallazgo M-2 (release del template sin SBOM propio) |
| 8 | Reproducibilidad | ⚠️ | Medio | `~=` (compatible-release) sin lockfile congelado en el template raíz; Docker con init-container y digests en prod | Publicar lockfile de referencia por release |
| 9 | Gestión de secretos | ✅ | Bajo | `common_utils/secrets.py`; IRSA/WI; 0 usos de `os.environ["API_KEY"...]` en paths de producción | Sin observaciones |
| 10 | Gestión de configuraciones | ✅ | Bajo | 7 overlays Kustomize (aws/gcp × dev/staging/prod + batch-only); separación de secretos por entorno documentada | Sin observaciones |
| 11 | Pruebas | ⚠️ | Medio | Gate `--cov-fail-under=90` en CI de servicio; pero `coverage.xml` local del repo raíz: 79 % líneas / 37.5 % branches | Cerrar brecha de cobertura del repo raíz o documentar el alcance del gate |
| 12 | Documentación | ✅ | Bajo | README, ADRs (42 en `docs/decisions/`), CHANGELOG (131 KB), 29 runbooks, CONTRIBUTING, SECURITY.md, MIGRATION | Sin observaciones |
| 13 | Gestión de versiones | ✅ | Bajo | SemVer; tags anotados y **firmados** (verify-tag OK, ED25519); `releases/*.md` por versión | Documentar la coexistencia de tags retroactivos v1.x vs v0.x actual |
| 14 | Gestión de incidentes | ✅ | Bajo | Runbooks `rollback.md`, `secret-breach.md`, `incident-response.md`; workflows `/rollback`, `/secret-breach`; SECURITY.md con canal de divulgación | Sin observaciones |
| 15 | Gestión de cambios | ⚠️ | Medio | PR template + status checks obligatorios; pero commits directos a `main` posibles con 0 reviewers (bypass admin) | Igual que #1: elevar reviews cuando exista segundo maintainer |
| 16 | Auditoría de commits | ✅ | Bajo | Conventional Commits consistentes; commits recientes firmados (`%G?` = G); DCO | Retro-firmado no viable; mantener firma hacia adelante |
| 17 | Supply chain security | ✅ | Bajo | 79 actions SHA-pinned (0 sin pin en workflows raíz); OpenSSF Scorecard; cosign keyless + SBOM CycloneDX/SPDX en CI de servicio; Kyverno verifyImages | Ver M-2 |
| 18 | MLOps | ✅ | Bajo | DVC (`.dvc/config`, `dvc.yaml`); MLflow; `quality_gates.yaml` + JSON Schema; drift PSI + concept drift; promoción a prod = STOP (gobernanza ADR-002) | Sin observaciones |
| 19 | Evidencias | ✅ | Bajo | `ops/audit.jsonl` (protocolo AuditEntry), `VALIDATION_LOG.md` (82 KB), 8 auditorías previas en `docs/audit/`, step summaries en CI | Sin observaciones |
| 20 | Observabilidad (SLI/SLO/OTel) | ✅ | Bajo | `slo-prometheusrule.yaml` con multi-window/multi-burn-rate (SRE Workbook cap. 5); Alertmanager con routing testeado; OTel opt-in | Documentar el opt-in de OTel como decisión; añadir SLA externo de referencia |
| 21 | Arquitectura | ✅ | Bajo | Capas claras (app/common_utils/scripts/k8s/infra); contratos tipados inmutables entre agentes; extensión vía Copier + overlays | Ver A-1 (acoplamiento por vendoring) |
| 22 | Deuda técnica | ⚠️ | Medio | 3.7 % funciones con CC>10; hotspots `sync_agentic_adapters.py::render` (CC 31), `evaluate_evidence` (CC 26); duplicación vendorizada root↔service con drift-gate | Refactor de los 5 hotspots; la duplicación está controlada pero duplica el costo de mantenimiento |
| 23 | Experiencia del desarrollador (DX) | ✅ | Bajo | "Clone → modelo servido en 10 min" con tracks de 5/10 min; devcontainer; 29 targets Make; Copier con delimitadores custom | Ver DX-1 (volumen de documentación como curva de entrada) |

**Veredicto global**: madurez alta (nivel "enterprise-ready con salvedades"). Ningún hallazgo crítico. 5 hallazgos de riesgo medio (M-1…M-4 derivados de una causa raíz común — **proyecto uni-maintainer** — y A-1, deuda técnica localizada) y 4 bajos (L-1…L-3, DX-1).

---

## Hallazgos detallados

### M-1 (Medio) — Gobierno: revisiones requeridas = 0 y firmas de commit no exigidas en SCM

- **Evidencia**: `docs/governance/branch-protection.md` — ruleset `main-branch-baseline`: `required_approving_review_count: 0`, `required_signatures: disabled`, bypass `RepositoryRole: admin`.
- **Análisis**: la protección de `main` es real (PR obligatorio, 6 status checks requeridos, linear history, no force-push, no deletion), pero con 0 reviewers un actor único puede fusionar sin segunda mirada. El repositorio **divulga esto honestamente** en `.github/CODEOWNERS` (sección "Maintainership disclosure", audit HIGH-2 de mayo 2026) — es una limitación aceptada y documentada, no una omisión. Para un adoptante con obligaciones SOC 2 / separación de funciones, esto es bloqueante tal cual.
- **Recomendación**: (a) onboarding de co-maintainer (ya trackeado como ADR-024 TBD en CODEOWNERS); (b) al hacerlo, subir a `required_approving_review_count: 1` y habilitar `required_signatures`; (c) los adoptantes deben reemplazar CODEOWNERS con sus propios handles (ya instruido en el propio archivo).

### M-2 (Medio) — Supply chain: el release del template no genera SBOM/firma propia

- **Evidencia**: `templates/service/.github/workflows/ci.yml:236-275` genera SBOM (syft, CycloneDX+SPDX) y firma imágenes con cosign keyless — pero eso aplica a los **servicios scaffolded**. `.github/workflows/release-on-tag.yml` (el release del template mismo) no produce SBOM ni attestation del artefacto de release.
- **Análisis**: el template no publica imágenes, así que el riesgo es menor; pero un auditor SLSA preguntará por provenance del propio artefacto de release (tarball/tag).
- **Recomendación**: añadir `actions/attest-build-provenance` o SBOM del árbol fuente al job de `release-on-tag.yml`. Los tags ya están firmados (mitigación parcial).

### M-3 (Medio) — Reproducibilidad: sin lockfile congelado

- **Evidencia**: `templates/service/requirements.txt` usa `~=` (política deliberada, memoria de convenciones y comentario sobre numpy 2.x); existe `templates/service/constraints.txt` pero no un lockfile con hashes (`uv.lock`, `pip-compile --generate-hashes`).
- **Análisis**: `~=` evita roturas mayores pero no garantiza reconstrucción bit-a-bit dentro de un año (criterio #8 del marco). ADR-035 adoptó uv — el paso natural es committear el lock.
- **Recomendación**: publicar un lockfile de referencia por release del servicio scaffolded; mantener `~=` en `requirements.txt` como declaración de intención.

### M-4 (Medio) — Pruebas: cobertura real del repo raíz por debajo del estándar declarado

- **Evidencia**: `coverage.xml` local (no versionado): `line-rate: 0.7908`, `branch-rate: 0.375`. El estándar del proyecto declara ≥90 % líneas / ≥80 % branches. El gate `--cov-fail-under=90` existe en `templates/service/.github/workflows/ci.yml:82` y `templates/service/Makefile:121`, pero cubre `src/` + `app/` del **servicio**, no los scripts/validadores del repo raíz.
- **Análisis**: puede ser un artefacto local parcial (una sola corrida de subconjunto), pero un auditor exigirá el reporte de CI como evidencia primaria. La brecha de branch coverage (37.5 % vs 80 %) es la señal más débil del dominio de pruebas.
- **Recomendación**: (a) verificar la cobertura real del lane raíz en CI (`ci-examples.yml` / `validate-templates.yml`) y adjuntarla como evidencia; (b) si la brecha es real, ampliar tests de `scripts/` y `common_utils/`; (c) borrar `coverage.xml`/`.coverage` obsoletos del working tree para no confundir auditorías futuras.

### L-1 (Bajo) — Higiene del working tree

- **Evidencia**: `alertmanager-0.25.0.linux-amd64.tar.gz` (29 MB) y su directorio extraído presentes en el working tree. **No están versionados** (`git ls-files` limpio, status limpio) — solo son clutter local.
- **Recomendación**: eliminarlos localmente; confirmar que el patrón está en `.gitignore`.

### L-2 (Bajo) — Falsos positivos de gitleaks en `__pycache__`

- **Evidencia**: `gitleaks detect --no-git` reporta 3 hits `private-key`, todos en `.pyc` compilados de `test_memory_redaction.py` (fixture de test de redacción). No versionados.
- **Recomendación**: excluir `__pycache__/` en `.gitleaks.toml` para que corridas locales `--no-git` queden en 0.

### A-1 (Medio) — Deuda técnica: duplicación estructural root↔service y hotspots de complejidad

- **Evidencia**:
  - Duplicación vendorizada byte-a-byte: `scripts/validate_agentic_manifest.py` ≡ `templates/service/scripts/validate_agentic_manifest.py` (737 líneas c/u), `scripts/sync_agentic_adapters.py` ≡ su copia de servicio (467 líneas c/u), `scripts/audit_record.py` ídem. Total ≈ 1.900 líneas mantenidas por duplicado.
  - Complejidad ciclomática (análisis AST propio, 1.342 funciones en 33.037 líneas Python versionadas): **3.7 % de funciones con CC > 10** — bajo para el tamaño del repo. Hotspots: `_collect_names` CC 43 (test), `mcp_doctor.py::_collect_errors` CC 36, `sync_agentic_adapters.py::render` CC 31, `evidence_bundle.py::evaluate_evidence` CC 26 / 145 líneas, `audit_record.py::main` CC 24 / 167 líneas.
  - Archivos grandes: `eda_pipeline.py` 882 líneas, `fastapi_app.py` 812 líneas.
- **Análisis**: la duplicación NO es accidental — es vendoring deliberado con gate de drift (`scripts/check_cicd_template_drift.py` + job `cicd-template-drift` en `validate-templates.yml`, política en `docs/governance/cicd-templates-drift.md`). El riesgo de divergencia silenciosa está mitigado; el costo residual es que cada fix se aplica dos veces (los commits "Wave A drift" del historial son la prueba de que ese costo ya se pagó al menos una vez). Los hotspots de CC se concentran en tooling agéntico y validadores, no en el path de inferencia (`fastapi_app.py` mantiene funciones bajo CC 20 pese a sus 812 líneas).
- **Recomendación**: (a) refactorizar `render` y `evaluate_evidence` extrayendo sub-funciones (son los dos con mayor CC en código no-test de producción); (b) evaluar convertir los scripts vendorizados en un paquete instalable único referenciado por ambos lados, eliminando la clase de defecto en vez de detectarla; (c) partir `eda_pipeline.py` por fases si crece más.

### DX-1 (Bajo) — Curva de entrada documental

- **Evidencia**: `README.md` 55 KB, `AGENTS.md` 44 KB, `CHANGELOG.md` 131 KB, `VALIDATION_LOG.md` 82 KB en la raíz; 42 ADRs; 29 runbooks.
- **Análisis**: el onboarding ejecutable es excelente (ver dominio 23), pero el primer contacto visual con la raíz del repo presenta ~300 KB de Markdown. `QUICK_START.md` y `llms.txt` mitigan (rutas de entrada curadas), y la audiencia objetivo (equipos de plataforma) lo tolera; aun así, un adoptante casual puede no encontrar la puerta.
- **Recomendación**: mantener; opcionalmente mover `VALIDATION_LOG.md` a `docs/` y enlazar desde README para despejar la raíz.

### L-3 (Bajo) — Doble esquema de tags

- **Evidencia**: coexisten tags `v1.7.0…v1.12.0` (retroactivos, ADR-014 §4.5) con la línea actual `v0.x` (`VERSION` = 0.21.0). Está documentado en ADR-014, pero confunde a `sort -V` y a cualquier tooling que asuma monotonía.
- **Recomendación**: nota aclaratoria en `docs/RELEASING.md` sobre cuál línea es autoritativa.

---

## Verificación por dominio (evidencia bruta)

1. **Gobierno**: `.github/CODEOWNERS` (62 líneas, cobertura de paths críticos), `docs/governance/branch-protection.md` + `scripts/setup_branch_protection.sh` + ADR-026 (triple-sync exigido), permisos por agente en AGENTS.md. MFA: no verificable desde el repo (control organizacional GitHub).
2. **Trazabilidad**: merges con referencia a PR (`#43…#49`), releases con notas por versión en `releases/`, CHANGELOG por versión, ADRs enlazados desde commits.
3. **Calidad**: `.pre-commit-config.yaml` (8.8 KB), lint gates en `validate-templates.yml` ("Python Lint + Type Check" es status check requerido).
4. **Seguridad**: gitleaks en CI (check requerido "Self-audit: gitleaks + tfsec + checkov + trivy fs") y en local — 0 hallazgos versionados.
5. **Dependencias**: `.github/dependabot.yml` — github-actions (semanal), docker, terraform GCP/AWS (mensual); PRs de Dependabot #45–#49 fusionados en historial reciente.
6. **Licencias**: Apache-2.0 raíz, `NOTICE`, `DCO.md`; sin dependencias copyleft detectadas en `requirements.txt` (stack MIT/BSD/Apache: sklearn, fastapi, mlflow…).
7. **CI/CD**: quién despliega = Environment Protection Rules (`dev` auto, `staging` 1 reviewer, `production` 2 reviewers + wait_timer 5m — con el descargo de bus-factor); pipeline versionado y SHA-pinned; despliegue prod solo vía GitHub Actions (modo STOP en AGENTS.md).
8. **Reproducibilidad**: Dockerfile multi-stage, modelo vía init-container (nunca en imagen), digests `@sha256` exigidos en staging/prod (regla D-17/D-19), pero ver M-3.
9. **Secretos**: `common_utils/secrets.py`, tabla de entornos (dotenv local / GitHub Secrets CI / Secret Manager+CSI en staging-prod), rotación = STOP con runbook.
10. **Configuración**: overlays `gcp-dev|staging|prod`, `aws-dev|staging|prod`, `batch-only`; `docs/environment-promotion.md`.
11. **Pruebas**: unit + integración + regresión + carga (`/load-test`), negativos (tests de anti-patrones D-XX en `policy-tests.yml`); ver M-4.
12. **Documentación**: 42 archivos en `docs/decisions/`, 29 runbooks, `MIGRATION.md`, `QUICK_START.md`, `docs/COMPLIANCE_MAPPING.md` (mapeo explícito a marcos — punto fuerte inusual).
13. **Versiones**: `git verify-tag v0.21.0` → "Good git signature… ED25519" ✔.
14. **Incidentes**: `docs/incidents/` con plantilla, skill `incident-postmortem`, `RUNBOOK.md` raíz.
15. **Cambios**: `pull_request_template.md` + `pr-evidence-check.yml` (workflow que exige evidencia en PRs).
16. **Commits**: 100 % Conventional Commits en los últimos 40; firmas `G` (válidas) desde ~fcb28c4 en adelante, `N` en historial anterior (esperado, firma adoptada después).
17. **Supply chain**: `scorecard.yml` (OpenSSF), 79 `uses:` pinned a SHA-40 y 0 pinned solo a tag en workflows raíz, cosign v2.4.0 pinned, Kyverno smoke test en CI.
18. **MLOps**: `templates/service/dvc.yaml` + `.dvc/config` (versionado de datos), MLflow (tracking + registry, promoción Production = STOP), `configs/quality_gates.yaml` con schema validado por test, drift PSI + concept-drift skills, fairness DIR ≥ 0.80 pre-deploy, lineage vía `agent_context.py` (handoffs tipados inmutables).
19. **Evidencias**: `ops/audit.jsonl` append-only + `scripts/audit_record.py` + espejo en GHA step summary; `VALIDATION_LOG.md`; este informe se suma a la serie R4–R10 en `docs/audit/`.

---

## Dominios complementarios (perspectiva de arquitecto)

### 20. Observabilidad — SLI / SLO / OTel / Prometheus / Alertmanager ✅

- **SLI/SLO formales**: `templates/service/k8s/base/slo-prometheusrule.yaml` — 9 reglas `record:`/`alert:` que implementan **multi-window/multi-burn-rate** según Google SRE Workbook cap. 5: recording rules `sli:availability`, `sli:latency_500ms`, `error_budget:availability`, con burn-rate fast/slow (`14.4×` @ 1h / `6.0×` @ 6h) y severidades P2+page.
- **SLO de lazo cerrado (ML-específico)**: `docs/runbooks/closed-loop-sla.md` define SLOs de ingesta de ground-truth (`ground_truth_ingestion_lag_seconds`), regresión de performance (-2 % vs ventana de 7 días) y su escalado a `/incident` — cubre el fallo silencioso típico de ML que un SLO de disponibilidad no ve.
- **Métricas**: instrumentación nativa en `fastapi_app.py` (4 Counter, 2 Histogram, 3 Gauge) + `prometheus-client ~= 0.21.0`.
- **Alerting**: `monitoring/alertmanager.yml` + `alertmanager-rules.yaml` (11 alertas) + `alerts-template.yaml` (8 alertas Prometheus), y — poco común — **el routing de Alertmanager tiene test propio** (`monitoring/tests/test_alertmanager_routing.py`), validado además por runbook (`docs/runbooks/alertmanager-validation.md`).
- **Dashboards**: 5 dashboards Grafana versionados (business, closed-loop, DORA, edge, template) con inventario en `docs/observability/dashboards-inventory.md`; KPIs de negocio en `business-kpis.md`; correlación log↔trace documentada en `log-trace-correlation.md`; cobertura por "estaciones" en `monitoring-stations.md`.
- **Tracing**: `common_utils/tracing.py` — OpenTelemetry **opt-in** (`OTEL_ENABLED=true` activa TracerProvider + exportador OTLP/HTTP + middleware FastAPI; el import es perezoso para no imponer las dependencias `opentelemetry-*` al baseline).
- **Brechas menores**: (a) el opt-in de OTel es razonable para un template, pero merece una línea en un ADR de observabilidad para que el auditor no lo lea como ausencia; (b) no hay un documento de **SLA** externo de ejemplo (el SLO existe; el contrato con el consumidor no está plantillado); (c) logs: promtail presente, pero la retención/costo de logs no está presupuestada en el cost-review.
- **Veredicto**: por encima del estándar enterprise típico — la mayoría de organizaciones no testean su routing de Alertmanager ni versionan burn-rates.

### 21. Evaluación arquitectónica — modularidad, cohesión, acoplamiento ✅

- **Modularidad**: separación limpia de planos — `app/` (serving), `common_utils/` (20 módulos de runtime compartido con responsabilidades unitarias: `secrets`, `tracing`, `risk_context`, `prediction_logger`…), `scripts/` (tooling), `k8s/` + `infra/` (plataforma), `agentic/` (gobernanza de agentes), `monitoring/` (observabilidad). Cada plano es sustituible sin tocar los demás.
- **Cohesión**: alta en `common_utils` — módulos de ~200-450 líneas con una responsabilidad cada uno. Excepciones: `fastapi_app.py` (812 líneas) concentra endpoints + lifespan + métricas + SHAP; funcional pero es el candidato natural a partirse en routers si el template crece.
- **Acoplamiento**: el mecanismo dominante de desacoplamiento son **contratos tipados inmutables** (`agent_context.py`: dataclasses `frozen=True` con validación en construcción — p. ej. `DeploymentRequest` no se puede construir para prod sin auditoría de seguridad aprobada). Esto sube el acoplamiento a nivel de tipo (deseable) y lo baja a nivel de implementación. El acoplamiento problemático es el **vendoring root↔service** (ver A-1): acoplamiento por copia, mitigado con drift-gate en CI pero no eliminado.
- **Extensibilidad**: tres ejes documentados — (a) scaffolding por Copier con delimitadores custom `{@ @}` que no chocan con Jinja de los servicios generados; (b) overlays Kustomize por nube/entorno (7); (c) perfiles de stack conmutables (`/stack-switch`, ADR-033/D-35). Añadir una nube o un entorno no requiere tocar `base/`.
- **Mantenibilidad**: reforzada por la disciplina ADR (42 decisiones con triggers de revisión) y por gates que convierten convenciones en checks ejecutables (`policy-tests.yml` testea los anti-patrones D-XX). El riesgo de mantenibilidad real es organizacional (bus factor 1, M-1), no estructural.
- **Veredicto**: arquitectura deliberada y defendible; el único acoplamiento cuestionable (vendoring) está identificado, justificado por escrito y vigilado por CI.

### 22. Deuda técnica — complejidad, duplicación, hotspots ⚠️

Ver hallazgo **A-1**. Datos duros del análisis (AST, 1.342 funciones):

| Métrica | Valor | Umbral típico | Estado |
|---|---|---|---|
| Funciones con CC > 10 | 49/1.342 (3.7 %) | < 5 % | ✅ |
| Peor CC en código de producción | 31 (`sync_agentic_adapters.py::render`) | < 15 | ⚠️ |
| Función más larga | 167 líneas (`audit_record.py::main`) | < 60 | ⚠️ |
| Líneas duplicadas por vendoring | ≈ 1.900 (×2) | 0 estructural | ⚠️ mitigado (drift-gate) |
| Archivo más grande | 882 líneas (`eda_pipeline.py`) | < 500 | ⚠️ |

- **Hotspots de cambio**: el historial reciente concentra churn en la superficie agéntica (`agentic/`, adapters `.devin/.claude/.cursor/.codex` — 4 copias sincronizadas por `sync_agentic_adapters.py`) y en CHANGELOG/docs. El hotspot de riesgo es precisamente donde CC y churn coinciden: el tooling de sincronización de adapters.
- **Code smells**: no se detectó dead code evidente ni God-classes; los smells son "funciones-guión" largas en CLI tooling (aceptable) y el tamaño de `fastapi_app.py`.
- **Veredicto**: deuda baja y localizada; el proyecto ya practica el pago de deuda vía auditorías R4-R10 con planes de acción versionados.

### 23. Experiencia del desarrollador (DX) ✅

- **Bootstrap**: `QUICK_START.md` promete y estructura "**clone → primer modelo servido en 10 minutos**" con dos tracks: Track A (5 min, `examples/minimal/`, sin Docker ni cluster) y Track B (10 min, `copier copy` + suite de tests local). La existencia del track sin-cluster elimina la barrera de entrada clásica de los templates MLOps.
- **Entorno reproducible**: `.devcontainer/` (devcontainer.json + post-create.sh) y `docker-compose.yml` para el stack local; perfiles local-first (ADR-033) evitan exigir cuentas cloud para empezar.
- **Automatización**: `Makefile` raíz con 29 targets + Makefile por servicio; workflows slash (`/new-service`, `/onboard`, `/eda`…) para operadores de agentes; `scripts/mcp_doctor.py` para diagnóstico del entorno agéntico.
- **Onboarding guiado**: `QUICK_START.md` → `docs/TUTORIAL.md` → `docs/ADOPTION.md` (24 KB, por olas) → `docs/PROGRESSION.md`; skill `template-onboard` entrevista al adoptante y emite su contexto. `CONTRIBUTING.md` + plantillas de PR/issue cierran el ciclo de contribución.
- **Extender el template**: Copier con `copier update` (`/scaffold-update`) da a los adoptantes un canal de re-sincronización con upstream — la mayoría de templates se abandonan tras el fork; este tiene mecanismo anti-abandono.
- **Fricciones**: (a) volumen documental en raíz (DX-1); (b) el contrato de gobernanza asume que el adoptante configure rulesets y environments de GitHub a mano (`make setup-github` lo asiste, modo CONSULT); (c) clutter local de 29 MB detectado (L-1) sugiere que el propio flujo de validación local deja residuos.
- **Veredicto**: DX por encima de la media enterprise; el tiempo-a-primer-éxito está diseñado, medido y con dos escalones.

---

## Limitaciones de esta auditoría

- No se consultó la GitHub API en vivo: estado real de rulesets, MFA de colaboradores, y Environment Protection Rules se evaluaron contra su documentación canónica (que el repo mantiene sincronizada por política de triple-commit ADR-026).
- No se ejecutó escaneo de CVEs (trivy/grype) en esta corrida; ese control corre como status check requerido en CI ("Self-audit") y se acepta como evidencia delegada.
- El escaneo de historial completo de git (`gitleaks detect` sin `--no-git`) no se repitió; existe runbook dedicado `docs/runbooks/secret-history-scan.md` y un rewrite de historial previo documentado (commit `403070a`).
