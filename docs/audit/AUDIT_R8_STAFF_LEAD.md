# AUDIT R8 — Staff/Lead Dual-Repo Audit: `template_MLOps` + `agent-local`

- **Fecha**: 2026-07-01
- **Alcance**: auditoría completa de los dos repos del ecosistema —
  `ML-MLOps-Production-Template` (en `main` @ `4cbf89b`, v0.20.0) y
  `agent-local` (en `main` @ `90d672a`, CHANGELOG v0.4.0+unreleased).
- **Nivel**: staff/lead — arquitectura, código, estructura, testing, CI/CD,
  supply chain, seguridad, observabilidad, documentación/gobernanza,
  superficie agéntica, adoptabilidad y competitividad frente a referentes.
- **Método**: evidencia primaria únicamente. Cada afirmación de este informe
  está respaldada por (a) ejecución local de suites y validadores, (b) estado
  vivo de GitHub Actions, (c) lectura de código fuente con `file:line`, o
  (d) **consultas estructurales sobre un grafo de conocimiento del código**
  (tree-sitter + LSP; 9.854 nodos / 18.178 aristas para el template, 784 /
  2.055 para agent-local) — que permite verificar invariantes sobre el 100 %
  de los call sites, no sobre una muestra.
- **Relación con auditorías previas**: sucede a `AUDIT_R7_STAFF_LEAD.md`
  (2026-06-30). Los hallazgos R7 fueron cerrados (Waves 1–4, ADR-029..036);
  este informe audita el estado *posterior* a ese cierre e incorpora por
  primera vez a `agent-local` como objeto de auditoría de pleno derecho.

---

## 1. Resumen ejecutivo

**Veredicto global**: el ecosistema está en el mejor estado de su historia y
por encima del estándar de la industria para repos de su clase. El template
es un producto maduro (9.1/10): CI verde en 4 workflows, 661 funciones de
test, 6 validadores deterministas verdes, cero dead code y cero complejidad
de riesgo verificados por grafo, y el invariante de serving más crítico
(D-24) demostrado estructuralmente sobre todos los call sites del repo.
`agent-local` es una plataforma joven y bien diseñada (7.9/10) cuyo `core/`
está a la altura del template, pero cuya **superficie de app y de proceso
aún no ha vendido la disciplina de enforcement que su hermano ya tiene** —
y esa brecha produjo el hallazgo más significativo de esta ronda:

> **R8-01 (HIGH)**: `app/main.py` ejecuta el loop completo del agente
> (multi-segundo, multi-LLM-call) **síncronamente dentro de un endpoint
> `async def`**, bloqueando el event loop — exactamente la clase de defecto
> que el template cataloga como D-24 ("NEVER `model.predict()` directly in
> async endpoint") y gatea con contract test. La plataforma que generaliza
> la filosofía de gobernanza del template viola su invariante de serving
> insignia.

Ningún hallazgo es Critical; ninguno afecta CI (ambos repos verdes en
GitHub). El patrón transversal de los 12 hallazgos es uno solo y es la tesis
de este informe: **`agent-local` adoptó la filosofía del template
(policy-as-data, telemetría-contrato, ADRs, fail-closed) pero todavía no sus
*gates* (doc-coherence, secret-scan, contract tests de serving, alcance de
lint completo)** — la diferencia entre "diseñado correcto" y "imposible de
degradar en silencio" que el propio template enseña.

### Scorecard

| Dimensión | Peso | template_MLOps | agent-local |
|---|:-:|:-:|:-:|
| Arquitectura y estructura | 1.2 | **9.5** | **9.0** |
| Calidad de código | 1.2 | **8.5** | **7.0** |
| Testing y verificación | 1.2 | **9.0** | **8.0** |
| CI/CD y supply chain | 1.0 | **9.5** | **6.5** |
| Seguridad | 1.0 | **9.0** | **7.5** |
| IaC / K8s (template) · Telemetría/observabilidad (agent-local) | 0.8 | **9.0** | **9.0** |
| Documentación y gobernanza | 1.0 | **9.5** | **8.0** |
| Superficie agéntica (template) · Evals (agent-local) | 1.0 | **9.5** | **7.0** |
| Adoptabilidad / DX | 0.8 | **8.5** | **8.5** |
| Competitividad frente a referentes | 0.8 | **9.0** | **8.5** |
| **Global ponderado** | | **9.1 / 10** | **7.9 / 10** |

Lectura del delta (9.1 vs 7.9): no es diferencia de talento de diseño — el
`core/` de agent-local puntúa como el template. Es diferencia de **edad de
enforcement**: el template lleva 8 rondas de auditoría convirtiendo
disciplina social en gates deterministas; agent-local lleva cero. El plan de
acción (§7) cierra exactamente esa brecha.

---

## 2. Metodología y base de evidencia

| Fuente | template_MLOps | agent-local |
|---|---|---|
| Suite local | `pytest -q` desde raíz **falla en colección** (R8-05); suites scoped verdes vía CI | 112 tests, **todos verdes** localmente |
| Validadores | 6/6 verdes: doc-coherence (6 checks), validate_agentic, manifest `--strict`, sync `--check`, vendored-drift, common_utils-drift | no existen (hallazgo R8-04/R8-06) |
| GitHub Actions (main) | 4/4 workflows verdes (pr-smoke-lane, CI-Examples 3m46s, Validate-Templates 2m26s, Template-Context 2m33s) | CI verde (lint+mypy+tests, matrix py3.11/3.12) |
| Lint local | pre-commit (black/isort/flake8/mypy/bandit/gitleaks) verde en último commit | mypy 17 files clean; flake8 clean bajo config CI; **black falla en 2 archivos fuera del alcance de CI** |
| Grafo de conocimiento | 9.854 nodos / 18.178 aristas; consultas de dead-code, complejidad, call-sites de `.predict*`, clones | 784 nodos / 2.055 aristas; mismas consultas |
| Lectura de código | `fastapi_app.predict()` + configuración deployment/Dockerfile/requirements | `controller.py` (491 LOC) completo, `policy.py`, `telemetry.py`, `app/main.py`, `evals/run.py` completos |

**Verificación estructural destacable** (imposible con grep): la consulta
`MATCH (caller:Function)-[:CALLS]->(callee) WHERE callee.name IN
['predict','predict_proba'] AND NOT caller.file_path CONTAINS '/tests/'`
sobre el template devuelve **exactamente 10 call sites**, y los 10 son
legítimos por diseño: `_sync_predict`/`_sync_predict_batch` (ejecutan DENTRO
del `ThreadPoolExecutor`), `warm_up_model` (pre-tráfico), y
`champion_challenger.compare_models` + `train.run_quality_gates` (offline).
Cero handlers async llamando al modelo directamente. Esto es una prueba
repo-total de D-24, más fuerte que el contract test existente
(`test_fastapi_template_contract._assert_no_direct_model_predict`), que
cubre un archivo.

---

## 3. `template_MLOps` — análisis por dimensión

### 3.1 Arquitectura y estructura — 9.5

- **Separación canónico/generado impecable** (ADR-027): `agentic/` es la
  única fuente editada a mano; `.cursor/ .claude/ .codex/ .devin/` son
  render de `sync_agentic_adapters.py`, verificado con `--check` en CI.
  17 rules / 20 skills / 16 workflows, cada activo con ancla `authority:`
  resuelta por el validador `--strict`.
- **Render Copier fiel** (ADR-030): `templates/service/` espeja el layout de
  salida; delimitadores `{@ @}` con cero colisiones verificadas en 249
  archivos; `copier update` real (no re-scaffold destructivo).
- **Composición del footprint**: 167 Python / 125 YAML / 35 HCL / 14 Bash —
  la proporción YAML+HCL (≈49 % de archivos) es coherente con un producto
  cuya identidad es infraestructura gobernada, no una librería.
- **Vendoring con gate**: los 4 archivos que Copier obligó a duplicar tienen
  `check_vendored_runtime_drift.py` (byte-idéntico o CI rojo) — el patrón
  ADR-025 aplicado consistentemente. El grafo confirma: **cero aristas
  `SIMILAR_TO` inesperadas** una vez excluidos los pares vendorizados
  declarados.
- Nada de sobre-arquitectura detectada: 20 entry points, todos scripts CLI
  con `main()`, ninguna capa de indirección sin consumidor.

### 3.2 Calidad de código — 8.5

**Fortalezas (verificadas por grafo, alcance repo-total):**
- **Cero dead code**: tres cortes de consulta distintos (templates/service
  sin tests; common_utils+src; repo entero con `is_entry_point=false`)
  devuelven cero funciones sin llamador.
- **Cero funciones de producción con ciclomática ≥ 10**. La profundidad
  máxima de loops anidados transitiva en código real es 5
  (`sync_agentic_adapters.render`, `fairness.run_fairness_audit`) — ambas
  estructuralmente justificadas (render de árbol de adapters; fairness
  interseccional), no smells.
- `fastapi_app.predict()` ([fastapi_app.py:626-693](../../templates/service/app/fastapi_app.py))
  es código de serving ejemplar: executor + `partial`, validación Pandera de
  segunda muralla en el path single (paridad PR-R2-4), 422 propagado
  verbatim (nunca enmascarado como 500), fire-and-forget logging que jamás
  bloquea la respuesta (D-21/D-22), y métrica por status.
- Pinning de dependencias de libro: `~=` en todo, **con la razón como
  comentario** (`numpy ~= 1.26.0  # numpy 2.x silently corrupts joblib models`).

**Debilidades:**
- **R8-05 (MEDIUM)** — `pytest -q` desde la raíz del repo **rompe en
  colección** con `ModuleNotFoundError: No module named 'tests.conftest'` /
  `'tests.test_alertmanager_routing'`. Causa raíz confirmada: tres paquetes
  hermanos llamados `tests`, los tres con `__init__.py`
  (`templates/service/tests/`, `templates/service/eda/tests/`,
  `templates/service/monitoring/tests/`) colisionan en `sys.modules` bajo el
  import-mode `prepend` por defecto. CI no lo ve porque nunca corre pytest
  desde la raíz (usa invocaciones scoped con `--rootdir` y `-p no:locust`),
  pero la raíz **sí** declara `[tool.pytest.ini_options]` con `addopts` —
  es un flujo soportado que regresó. Fix en §7 (P0-2).
- **R8-08 (LOW)** — al correr desde raíz, `templates/tests/unit/test_prediction_logger.py`
  emite `PytestUnknownMarkWarning: Unknown pytest.mark.asyncio`: el entorno
  raíz no tiene `pytest-asyncio` (CI-Examples lo instala explícitamente).
  Sin el plugin, un test async marcado se recolecta y "pasa" sin ejecutar el
  coroutine — silencioso exactamente del modo que el repo detesta.

### 3.3 Testing y verificación — 9.0

- **661 funciones de test** en el repo, organizadas por intención: contract
  tests (API shape, métricas, alert-routing, K8s vocabulary, Terraform
  parity), policy tests (scaffold D-01..D-35), integración
  (train→serve→drift e2e real), red-team regression
  (`test_red_team_regression.py`), y unit.
- La clase de test más valiosa del repo es el **contract test que codifica
  un anti-patrón**: `test_d35_local_profile_no_cloud_deps`,
  `_assert_no_direct_model_predict`, `test_predict_error_does_not_leak_exception_message` —
  cada invariante de AGENTS.md con dientes ejecutables. Es el patrón que
  agent-local aún no vendoriza (§5).
- 4 lanes de CI con presupuestos de tiempo sanos (25s smoke / 2-4 min lanes
  completas) — feedback rápido sin sacrificar cobertura.
- Descuento (−1.0): la regresión R8-05 demuestra que "la suite raíz" no
  tiene un guardián propio — ningún lane de CI la ejecuta tal cual, así que
  puede romperse sin señal (y se rompió).

### 3.4 CI/CD y supply chain — 9.5

- Cadena de deploy **pin-por-digest de extremo a extremo**: push → resolve
  digest → Cosign sign+attest (SBOM) → Kyverno verify-by-digest. Tags
  inmutables (D-09-adjacent). Esto está por encima de lo que publican la
  mayoría de templates ML de referencia.
- `release-on-tag.yml` idempotente con extracción verificada (fix reciente
  auditado en VALIDATION_LOG).
- Gates deterministas como familia coherente: `check_doc_coherence`,
  `check_vendored_runtime_drift`, `check_common_utils_drift`,
  `check_dashboard_inventory`, `check_cicd_template_drift`,
  `check_baselines_expiry` — un patrón único (`check_*.py`, fail-closed,
  seeded green) aplicado seis veces. Arquitectura de proceso, no scripts
  sueltos.
- pre-commit con gitleaks + bandit + mypy + validadores agénticos.
- Sin hallazgos en esta dimensión. El 0.5 restante es headroom, no defecto.

### 3.5 Seguridad — 9.0

- IRSA/WI en vez de credenciales estáticas (D-17/D-18); 5 identidades
  por-propósito (ADR-017); Pod Security Standards `restricted` con
  namespaces etiquetados (D-29); NetworkPolicy por overlay **incluido el
  caso batch cuyo selector base no matchea** (ADR-036 — el tipo de detalle
  que separa un overlay correcto de uno que cuelga init containers).
- Error sanitization con test dedicado; auth opcional con
  passthrough/enforcement testeado en ambos modos.
- `.gitleaks.toml` + `.security-baselines/` (checkov, tfsec) versionados con
  expiry check — las excepciones de seguridad caducan, no se acumulan.

### 3.6 IaC / K8s — 9.0

Verificado a nivel de archivo (deployment.yaml): initContainers para el
modelo (D-11, línea 67), `terminationGracePeriodSeconds: 30` con preStop y
comentario de headroom vs uvicorn timeout (D-25, línea 172+196),
`readinessProbe → /ready` gateado por warm-up **distinto de**
`livenessProbe → /health` (D-23, líneas 256/264 — con el comentario que
explica por qué liveness no debe reiniciar un pod en warm-up). Dockerfile
non-root con `COPY --chown` y HEALTHCHECK. Los overlays (6 env×cloud +
batch-only) compilan en el lane verde `Validate Templates` de CI.

### 3.7 Documentación y gobernanza — 9.5

- **36 ADRs activos + 1 lápida** (ADR-012, práctica de inmutabilidad de IDs
  correcta), todos con formato consistente, alternativas y revisit triggers.
- Rule 16 + `check_doc_coherence.py` (6 checks) hace que "shipped" y
  "documentado" sean la misma cosa para versión, conteos, índice de ADRs,
  llms.txt y nota de release — y está **verde hoy**.
- 26 notas de release en `releases/`; CHANGELOG Keep-a-Changelog con
  entradas [Unreleased] disciplinadas; VALIDATION_LOG como evidencia de
  ejecución. 9 documentos de auditoría/planes previos en `docs/audit/` —
  el repo tiene memoria institucional real.

### 3.8 Superficie agéntica — 9.5

- 17/20/16 con manifest `authority:` estricto; AUTO/CONSULT/STOP con
  escalación dinámica (ADR-010, escalación-only); 35 anti-patrones con
  acción correctiva y skill `rule-audit` que los verifica con evidencia
  file:line. La `ADR-037` recién canonizada (separación dual de namespaces
  de retrieval) mantiene el estándar: controles falsificables, no promesas.
- Es el diferenciador competitivo del producto y está mejor gobernado que
  el resto del repo — que ya está bien gobernado.

### 3.9 Adoptabilidad / DX — 8.5

- `copier copy` + `copier update` reales; perfiles `local/staging/prod`
  mapeados a AUTO/CONSULT/STOP con D-35 testeado; mapeo CCDS; `uv` aditivo;
  overlay batch-only como on-ramp; `new-service.sh` como wrapper de
  transición con deprecación. Las 6 palancas del audit de adaptabilidad
  cerradas y verificables.
- Descuento: la primera experiencia del contribuidor AL REPO (no al servicio
  generado) incluye hoy `pytest` raíz roto (R8-05) y un warning async
  confuso (R8-08) — fricción de onboarding interna, no de adopter.

### 3.10 Competitividad — 9.0

| Referente | Lo que ofrece | Lo que este template tiene y él no |
|---|---|---|
| Cookiecutter Data Science | layout reconocible | gobernanza agéntica, CI/CD completo, supply chain firmado, K8s/TF, quality gates |
| ZenML | stack profiles, orquestación | perfiles sin framework pesado; gates de fairness/leakage; Copier update; enforcement determinista |
| Made With ML | pedagogía del *why* | producto ejecutable + REDACTED-PRIVATE-REPO como plano pedagógico separado |
| Kedro | pipelines opinados | serving K8s endurecido (D-01..D-35), multi-cloud parity, promoción gobernada |
| BentoML | serving DX (batching) | evaluado con contrato de invariantes previo (ADR-032, Fase 0) — la relación correcta con un frontier tool |

Ningún referente combina scaffolding actualizable + gobernanza agéntica
ejecutable + supply chain attestado. El nicho es real y está defendido con
evidencia (README frontier comparison). El punto pendiente de
competitividad no es de features sino de **prueba social** (adopters
externos, issues de terceros) — fuera del alcance de código.

---

## 4. `agent-local` — análisis por dimensión

### 4.1 Arquitectura y estructura — 9.0

- **La proporción más elocuente del repo**: `core/` = 1.773 LOC en 11
  módulos, ningún archivo > 500 LOC, y un use-case nuevo = ~130 LOC de
  carpeta delgada (`usecases/tienda/tools.py` 121 + YAMLs). La promesa de
  ADR-001 ("dominio nuevo = carpeta, nunca fork") es medible y se cumple.
- `ExecutiveController` ([controller.py:100-195](file:///home/duqueom/projects/agent-local/core/controller.py))
  con admit/execute/release es un facade genuinamente delgado: routing +
  budget en admit; loop adaptativo con **deadline chequeado antes de cada
  estación opcional** y presupuesto de latencia propagado como timeout
  por-llamada (`call_tier`, líneas 239-255); policy gate + telemetría en
  release. El circuit breaker degrada por `effective_tier` y el caso "todo
  abierto" degrada a plantilla segura en vez de 500. Los grafos lo
  confirman: clusters de cohesión 0.63-1.0, hotspots exactamente donde deben
  estar (`check_policy` fan-in 17, `ToolRegistry.run` 16).
- Parser estructurado ADR-007 con **fallback legacy explícitamente diseñado
  para no poder regresionar** (`_parse_structured_calls` devuelve `None` ≠
  `[]` para distinguir "no es el formato" de "cero tools") — señal de
  madurez de diseño de contratos.

### 4.2 Calidad de código — 7.0

**Fortalezas**: mypy limpio en 17 archivos; `_coerce` con el guard de
string-quoted-nunca-numérico (el teléfono `"+5215551234"` no se vuelve
float — comentado con el ejemplo); `_split_args` respeta nesting y quotes;
cero dead code y cero complejidad ≥ 10 por grafo (los `transitive_loop_depth`
3-5 son todos tests o `dev_message`).

**Hallazgos** (detalle completo en §6):

- **R8-01 (HIGH)** — [app/main.py:78-108](file:///home/duqueom/projects/agent-local/app/main.py):
  `async def dev_message(...)` ejecuta `AGENT.handle(...)` — una cadena
  síncrona de N llamadas HTTP a llama-server (plan→tools→reflect→generate→
  critic, segundos de pared) — **directamente en el event loop**. Toda
  petición concurrente (incluido `/health`) queda bloqueada mientras un
  request está en vuelo. Es la clase D-24 del template, en el repo que
  generaliza su gobernanza. Con un solo usuario dev no duele; como
  plataforma ("teams can adopt across domains" — README) es el primer bug
  que un adopter con 2 usuarios simultáneos encontrará. Fix trivial (§7
  P0-1): quitar `async` (FastAPI corre endpoints `def` en threadpool) o
  `run_in_executor`. Y — lección del template — **acompañarlo de un contract
  test** que impida reintroducirlo.
- **R8-02 (MEDIUM)** — [app/main.py:108](file:///home/duqueom/projects/agent-local/app/main.py):
  `raise HTTPException(status_code=500, detail=str(e))` filtra el mensaje de
  la excepción interna al cliente. El template tiene un test dedicado contra
  exactamente esto (`test_predict_error_does_not_leak_exception_message`).
- **R8-03 (MEDIUM)** — [core/controller.py:353-366](file:///home/duqueom/projects/agent-local/core/controller.py):
  `reflect()` llama al tier (`max_tokens=128`), **descarta el valor de
  retorno** y solo incrementa `reflections_made`. La reflexión no alimenta
  `generate()` (que solo lee `observations`) ni se registra en telemetría.
  Hoy la estación es un costo puro de tokens+latencia en cada request
  medium/high-risk, sin efecto en la respuesta. O se cablea (append como
  observación sintética / contexto del generador) o se elimina — lo actual
  es lo peor de ambos mundos.
- **R8-04 (MEDIUM)** — drift de versión triple: `pyproject.toml:7` dice
  `0.2.0`, [app/main.py:34](file:///home/duqueom/projects/agent-local/app/main.py)
  y `:62` hardcodean `"0.2.0"`, mientras CHANGELOG y commits van por
  **v0.4.0**. Es exactamente la clase de drift que motivó el rule-16 gate
  del template (cuyo audit R7 encontró `llms.txt` congelado en una era
  anterior). agent-local no tiene gate que lo atrape.
- **R8-09 (LOW)** — [app/main.py:111-122](file:///home/duqueom/projects/agent-local/app/main.py):
  el stub del webhook documenta "retorna 501" pero responde **200** con body
  `not_implemented` — un cliente WhatsApp real interpretaría entrega
  exitosa. Debe ser `JSONResponse(status_code=501, ...)`.
- **R8-11 (INFO)** — docstrings en español en `app/` y `evals/` vs inglés en
  `core/` — inconsistencia de convención (el template es English-first).
- **R8-10 (INFO)** — `Verdict.escalate_to_tier=3`
  ([policy.py:106](file:///home/duqueom/projects/agent-local/core/policy.py))
  no es consumido por nadie: `release()` va directo a safe_fallback. Campo
  de contrato muerto — documentar como reservado o cablearlo.

### 4.3 Testing y verificación — 8.0

- 94 funciones / 112 tests recolectados, **100 % verdes**, bien dirigidos:
  breaker (half-open, open-skips-tiers), controller (degradación por tier
  caído, presupuesto de latencia, parsing estructurado con fence/unknown-tool/
  fallback-legacy), policy (stock-claim exige lookup vivo), verifier
  (judge en tier superior, low-risk skip).
- Lo que falta es lo que el template ya aprendió a exigir: (a) **contract
  test de no-bloqueo del event loop** (habría atrapado R8-01); (b) gate de
  cobertura (el template declara ≥90/80); (c) un test que fije la versión
  única (habría atrapado R8-04).

### 4.4 CI/CD — 6.5

- Lo que hay está bien razonado: matrix 3.11/3.12, lint+mypy+tests, y el
  comentario de cabecera de `ci.yml` documenta POR QUÉ no corren modelos en
  runners (ADR-002: self-hosted en máquina personal sobre repo público =
  vector de ataque conocido). Esa es una decisión de seguridad correcta y
  citable, no una carencia.
- **R8-06 (LOW)** — el alcance de lint es `core app usecases tests`, dejando
  fuera `conftest.py` (raíz) y `evals/` — y hoy **ambos fallan black**. El
  harness de evals es un artefacto de gobernanza (produce la evidencia de
  gates F0.3); que viva fuera del lint es una gotera por donde ya entró
  drift.
- **R8-12 (LOW)** — sin secret-scanning (gitleaks) ni bandit en CI ni
  pre-commit, en un repo cuyo `docker-compose` y `.env` tocan rutas de
  modelos y (Fase 2) tokens de WhatsApp. El `.env.example` actual está
  limpio; el gate es para el día que deje de estarlo.
- Sin release automation (no hay tags de git visibles pese a versiones de
  CHANGELOG) — aceptable pre-1.0, pero la mitad del drift R8-04 nace aquí.

### 4.5 Seguridad — 7.5

- **Fuerte donde importa al diseño**: tools read-only/dry-run fail-closed
  (ADR-006), policy gate determinista que ninguna respuesta puede saltarse,
  parsing con `ast.literal_eval` (nunca eval), telemetría sin payloads de
  cliente por esquema. `.env.example` con higiene correcta.
- Débil en la corteza: R8-02 (leak de detalle de excepción), R8-12 (sin
  scanners), y `uvicorn.run(..., reload=True)` en el `__main__` de
  producción-por-defecto (reload es dev-only; menor porque el README manda
  docker-compose).

### 4.6 Telemetría / observabilidad — 9.0

[telemetry.py](file:///home/duqueom/projects/agent-local/core/telemetry.py)
es el mejor archivo del repo: contrato Pydantic validado antes de escribir,
**redacción de PII en el momento de escritura, nunca después**, patrones
conservadores con `_SAFE_KEYS` para no corromper trace_ids/timestamps (con
el porqué documentado — ADR-005), naming OTel-aligned para que adoptar OTel
sea un cambio de transporte. `TelemetryEntry` captura ruta, tier final,
escalación con razón, fallos de tools, verdict de policy Y de critic,
latencias por estación, tokens por tier, presupuesto agotado y provenance
con quarantine. Pocos productos comerciales de agentes emiten esto.

### 4.7 Documentación y gobernanza — 8.0

- 8 ADRs con calidad uniforme (el más reciente, ADR-008, con revisit
  triggers específicos); CHANGELOG Keep-a-Changelog con la nota pre-1.0
  correcta; README con narrativa de linaje que posiciona el repo sin
  sobrevender ("Phase 1", "gated") — honestidad de estado que las
  auditorías previas del template forzaron y aquí nació de serie.
- Descuentos: R8-04 (drift de versión sin gate) y la ausencia de un índice
  de evidencia tipo VALIDATION_LOG (los reports de evals existen en
  `evals/reports/` pero nada los indexa ni los exige).

### 4.8 Evals — 7.0

- Existe un harness real con casos versionados por use-case
  (`usecases/tienda/evals/sets/`), reports JSON con timestamp, y un gate
  F0.3 históricamente en 20/20 — esto ya es más que la mayoría de repos de
  agentes.
- **R8-07 (LOW)** — [evals/run.py](file:///home/duqueom/projects/agent-local/evals/run.py):
  el gate está **hardcodeado en `correct_intent >= 18` absoluto** (línea
  136) — con un set de 40 casos, 45 % de accuracy "pasaría el gate"; debe
  ser ratio (`>= 0.90`). Además `datetime.utcnow()` (deprecado en 3.12,
  naive) en líneas 54/153, p95 con off-by-one (`int(n*0.95)` sin clamp,
  línea 119), y es uno de los 2 archivos que fallan black (R8-06). El
  harness que produce la evidencia de los gates merece el rigor de los
  gates.

### 4.9 Adoptabilidad — 8.5

Config-as-data completa (budgets, policy versionada, prompts por use-case),
`.env.example` + docker-compose con imagen oficial de llama.cpp, quickstart
de un comando. La barrera real de adopción es inherente al dominio (hardware
para GGUF), no al repo.

### 4.10 Competitividad — 8.5

| Referente | Su fuerte | Lo que agent-local tiene y él no |
|---|---|---|
| LangGraph | grafos de estado, ecosistema | gate de policy **determinista** post-generación (no otro LLM), presupuesto de latencia por estación, breaker por tier, telemetría-contrato con PII redaction — en 1.7k LOC auditables |
| CrewAI | multi-agente rápido de armar | disciplina single-agent gobernado: evals con gate escrito ANTES de autonomía, escalación objetiva |
| Google ADK | full-stack managed, evaluación integrada | 100 % local/aire-gapped, cero vendor, costo marginal cero, y el mismo patrón (policy fuera del modelo) sin plataforma |
| smolagents | minimalismo | comparable en tamaño pero con circuit breaker, budgets, verificación cross-tier y policy gate que smolagents no trae |

El nicho — "agente local multi-tier con gobernanza determinista y
telemetría de contrato" — no lo ocupa ningún framework mainstream. La
guía de agentes de datos de Google Cloud (2026) valida el vocabulario
(contexto→razonamiento→orquestación, evaluación pre-producción, AgentOps)
sin invalidar ninguna decisión local. El riesgo competitivo es de
*visibilidad*, no de diseño; la única brecha técnica emergente razonable es
la interoperabilidad MCP (el conector estándar de facto 2026) — candidata a
ADR, no urgencia.

---

## 5. Análisis comparativo cross-repo: la matriz de paridad de gobernanza

La tesis del ecosistema es "la misma filosofía de gobernanza generaliza a un
dominio nuevo". Esta matriz mide cuánto de la filosofía viajó **con
enforcement** y cuánto viajó solo como cultura:

| Disciplina | template_MLOps | agent-local | Brecha |
|---|:-:|:-:|---|
| ADRs con formato + revisit triggers | ✅ 36 | ✅ 8 | — |
| CHANGELOG Keep-a-Changelog | ✅ | ✅ | — |
| Policy-as-data versionada | ✅ (quality_gates.yaml) | ✅ (policy.yaml + decision_id) | — |
| Telemetría con redacción PII | ✅ (memory_redaction) | ✅ (write-time) | — |
| Fail-closed por defecto | ✅ | ✅ (tools, gate) | — |
| **Gate de coherencia documental** | ✅ rule 16 + 6 checks CI | ❌ | R8-04 vivo (versión 0.2.0 vs 0.4.0) |
| **Secret scanning** | ✅ gitleaks + baselines con expiry | ❌ | R8-12 |
| **Contract test de serving (event loop)** | ✅ D-24 + test | ❌ | R8-01 vivo |
| **Error sanitization testeada** | ✅ test dedicado | ❌ | R8-02 vivo |
| **Lint de superficie completa** | ✅ pre-commit repo-total | ❌ scoped | R8-06 vivo (2 archivos con drift) |
| Gate de cobertura | ✅ ≥90/80 | ❌ | — |
| Release notes + tags | ✅ 26 notas + tags firmados | ❌ | mitad de R8-04 |

**Conclusión comparativa**: cada ❌ de la columna agent-local tiene un
hallazgo R8 vivo asociado en su fila. No es coincidencia — es la
demostración empírica de la tesis del propio template: *las disciplinas sin
gate driftean, siempre, incluso con el mismo autor y la misma intención*.
El plan de acción (§7) es, en esencia, "vendorizar los gates que faltan".

---

## 6. Registro de hallazgos

| ID | Sev. | Repo | Evidencia | Resumen |
|---|---|---|---|---|
| R8-01 | **HIGH** | agent-local | `app/main.py:78-108` | Loop multi-LLM síncrono dentro de `async def` — bloquea el event loop (clase D-24) |
| R8-02 | MEDIUM | agent-local | `app/main.py:108` | `HTTPException(detail=str(e))` filtra internals al cliente |
| R8-03 | MEDIUM | agent-local | `core/controller.py:353-366` | `reflect()` descarta el output del tier — costo sin efecto |
| R8-04 | MEDIUM | agent-local | `pyproject.toml:7`, `app/main.py:34,62` vs CHANGELOG | Versión 0.2.0 en 3 sitios; CHANGELOG en v0.4.0; sin gate |
| R8-05 | MEDIUM | template | 3× `tests/__init__.py` hermanos | `pytest -q` raíz rompe en colección; CI scoped no lo cubre |
| R8-06 | LOW | agent-local | `ci.yml` lint scope vs `black --check .` | `conftest.py` + `evals/run.py` fuera de lint; ambos fallan black hoy |
| R8-07 | LOW | agent-local | `evals/run.py:118-137,54,153` | Gate absoluto 18/20 (no ratio), `utcnow()` deprecado, p95 off-by-one |
| R8-08 | LOW | template | `templates/tests/unit/test_prediction_logger.py` raíz | Sin `pytest-asyncio` local los tests async "pasan" sin ejecutar |
| R8-09 | LOW | agent-local | `app/main.py:111-122` | Webhook stub responde 200; docstring promete 501 |
| R8-10 | INFO | agent-local | `core/policy.py:106` | `escalate_to_tier` emitido y nunca consumido |
| R8-11 | INFO | agent-local | `app/`, `evals/` | Docstrings ES/EN mezclados (core es EN) |
| R8-12 | LOW | agent-local | `.github/workflows/ci.yml` | Sin gitleaks/bandit en CI ni pre-commit |

Cero Critical. Cero hallazgos que rompan CI hoy. R8-01 es el único que
afectaría a un adopter en runtime.

---

## 7. Plan de acción priorizado

### P0 — corrige defectos observables (≤ 1 sesión)

1. **[agent-local] R8-01 + R8-02 + contract test** — en `app/main.py`:
   convertir `dev_message` a `def` (threadpool de FastAPI) o envolver
   `AGENT.handle` en `run_in_executor`; reemplazar `detail=str(e)` por un
   mensaje genérico + log interno con trace_id. Añadir
   `tests/test_app_serving_contract.py` con: (a) assert de que ningún
   endpoint `async def` llama `Agent.handle` directo (inspección AST, patrón
   del template), (b) assert de que un error interno no aparece en el body.
2. **[template] R8-05 + R8-08** — en `pyproject.toml` raíz añadir
   `--import-mode=importlib` a `addopts` (los 3 paquetes `tests` conviven
   bajo importlib) y `pytest-asyncio` al extra dev raíz con
   `asyncio_mode = "auto"`. Validar `pytest -q` raíz completo verde y
   añadir un job liviano de CI (o extender pr-smoke-lane) que ejecute **la
   colección** desde raíz (`pytest --collect-only -q`) para que la suite
   raíz tenga guardián.
3. **[agent-local] R8-09** — webhook stub → `JSONResponse(status_code=501)`.

### P1 — cierra la brecha de enforcement (la fila ❌ de §5)

4. **[agent-local] R8-04** — una sola fuente de versión: leer
   `importlib.metadata.version("agent-local")` en `app/main.py`; bump
   pyproject a la versión real del CHANGELOG; añadir
   `scripts/check_coherence.py` mínimo (versión pyproject == último heading
   de CHANGELOG == ADR count en README) como job de CI — el port del rule-16
   del template a escala agent-local (30 líneas, no el sistema completo).
5. **[agent-local] R8-06** — CI lint a superficie completa:
   `black --check .` / `isort --check-only .` / `flake8 .` (con excludes
   explícitos si hace falta) + aplicar el formato pendiente a `conftest.py`
   y `evals/run.py` en el mismo PR.
6. **[agent-local] R8-12** — gitleaks en CI (action oficial, 1 job) +
   pre-commit config espejo de la del template recortada (black/isort/
   flake8/mypy/gitleaks).
7. **[agent-local] R8-03** — decisión de diseño con mini-ADR: (a) cablear la
   reflexión (su output entra como observación sintética
   `Observation(tool="reflection", ...)` que `generate()` ya consumiría), o
   (b) eliminar la estación y su budget. Recomendación: (a) — es lo que el
   plan §F2 promete — con un test de que la reflexión aparece en el contexto
   del generador.

### P2 — endurecimiento y deuda menor

8. **[agent-local] R8-07** — gate de evals por ratio (`accuracy_intent >=
   0.90`), `datetime.now(timezone.utc)`, p95 con clamp
   (`min(idx, n-1)` o `statistics.quantiles`), black-format (cae con P1-5).
9. **[agent-local] R8-10/R8-11** — documentar `escalate_to_tier` como
   reservado (o consumirlo en `release()` regenerando en tier 3 antes del
   fallback); unificar docstrings a inglés en `app/` y `evals/`.
10. **[agent-local] tags + releases** — al cerrar P1-4, taggear la versión
    corregida y adoptar el patrón `releases/` del template (una nota por
    versión) — barato ahora, caro de reconstruir después.
11. **[ecosistema] ADR de interop MCP** — evaluar exponer `ToolRegistry`
    como servidor MCP / consumir tools MCP (validado como estándar de facto
    por la industria 2026). Proposed-first, patrón ADR-032: contrato de
    invariantes antes de código.

### Explícitamente NO recomendado

- **No** montar el sistema doc-coherence completo del template en
  agent-local (6 checks, cascade map) — a 1.7k LOC el check mínimo de P1-4
  cumple el principio de calibración; el sistema completo sería
  sobre-ingeniería hoy.
- **No** añadir gate de cobertura a agent-local todavía — con 112 tests
  sobre 2k LOC la cobertura real es alta; un número-gate sin historia de
  regresiones es ceremonia. Revisitar al primer bug que un test hubiera
  atrapado.
- **No** correr modelos en CI de agent-local — la postura ADR-002 es
  correcta; la evidencia de calidad de modelo sigue siendo local y
  versionada en `evals/reports/`.

---

## 8. Cierre

El template llega a R8 sin ningún hallazgo nuevo de arquitectura, seguridad
o supply chain — las 8 rondas de auditoría convergieron: lo que queda son
dos asperezas de DX local (R8-05/R8-08) en un flujo que CI no vigilaba.
`agent-local` demuestra que la filosofía generaliza (su core puntúa como el
template) y simultáneamente demuestra el teorema central del template: **la
cultura sin gates driftea** — cada disciplina que viajó sin su enforcement
tiene hoy un hallazgo vivo con file:line. El plan P0/P1 convierte esa
demostración en paridad; ejecutado, la puntuación proyectada de agent-local
es ≈ 8.8 sin cambiar una línea de su diseño.

*Auditoría R8 realizada con evidencia primaria: suites y validadores
ejecutados localmente, estado vivo de GitHub Actions, lectura de código
fuente, y verificación estructural por grafo de conocimiento (tree-sitter +
LSP) sobre el 100 % de los call sites para los invariantes graph-checkables.*
