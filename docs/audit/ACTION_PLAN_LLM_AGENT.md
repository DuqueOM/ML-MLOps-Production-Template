# ACTION PLAN — Framework Agéntico LLM Local (WhatsApp + Asistente de Tienda + Plano de Mantenimiento)

> **Autoridad**: ADR-028 (LLM-assist, 4 tiers), AGENTS.md (AUTO/CONSULT/STOP),
> guía oficial Gemma 4.
> **Este documento es el ÚNICO plan vigente del plano LLM** — absorbe y
> reemplaza a `ACTION_PLAN_ADR028.md` (hoy un stub que apunta aquí). Los
> lanes de mantenimiento del template viven en la sección "PLANO DE
> MANTENIMIENTO".
> **Audiencia**: un LLM ejecutor (puede ser menos capaz que el autor) o un humano.
> Cada paso incluye objetivo, archivos exactos, código, verificación y criterio
> de aceptación. **No improvises fuera de los pasos: si un gate falla, detente
> y reporta.**
>
> **Última actualización**: 2026-06-15 (**v3.1** — `agent-local` ejecutado:
> refactor a **plataforma reutilizable** `core/` + `usecases/<dominio>/`,
> repo público, gate de routing F1 **PASADO 20/20** y **F2.0**
> (ExecutiveController + circuit breaker) hecho; ver
> "Estado de ejecución" abajo. v3 base: supervivientes de la revisión
> adversarial R1–R10, `ARCH_REVIEW_LLM_AGENT.md` → ADDENDUM v3).

### Estado de ejecución (2026-06-15)

| Fase | Estado | Evidencia |
|---|---|---|
| F0 — Runtime + bench | ✅ Router E4B PASA gate velocidad | `agent-local/bench/RESULTS.md` |
| F1 — Esqueleto (read-only) | ✅ **COMPLETADO** | repo `agent-local`, suite verde |
| F1 — Gate de routing | ✅ **PASADO 20/20** (intent) | `agent-local/usecases/tienda/evals` |
| F2.0 — ExecutiveController + circuit breaker | ✅ **COMPLETADO** | `core/controller.py`, `core/circuit.py`, 29 tests |
| F2.1 — Tier 1 (12B) fallback | ⏸️ **DIFERIDO por diseño** | entrada condicionada por telemetría (plan §F2.1) |
| F2.2 — Políticas como datos versionados + `decision_id` | ✅ **COMPLETADO** | `policies/policy.yaml`, `core/policy.py`, `tests/test_policy.py` (12), ADR-003 |
| F2.3 — Verificación cruzada + self-consistency acotado | ✅ **COMPLETADO** | `core/controller.py` (`verify`), `tests/test_verifier.py` (7), ADR-004 |
| F2.4 — Tier 3 (31B) | ⏸️ **DIFERIDO por diseño** | descarga condicionada (plan §F2.4) |
| F2.5 — Los 10 eval sets | ✅ **CREADOS** (gate offline) | `usecases/tienda/evals/sets/01..10`, `tests/test_eval_sets.py` — scoring conductual pendiente de modelos |
| F3 — Telemetría de decisiones + shadow mode | ✅ **COMPLETADO** | `core/telemetry.py`, `TelemetryEntry`, `tests/test_telemetry.py` (9), ADR-005 |
| F4 — QLoRA | ⏸️ **GATE no alcanzado (por diseño)** | requiere ≥4 semanas de logs + evals estables (plan §F4) |

> **Frontera alcanzada**: todas las fases *accionables sin hardware/datos* están
> hechas (77 tests verdes). Lo pendiente está bloqueado **por diseño**, no por el
> agente: F2.1/F2.4 (entrada condicionada por telemetría / descarga del 31B),
> scoring conductual de los 10 sets (necesita los tiers corriendo) y F4 (≥4
> semanas de logs). Se desbloquean tras el upgrade de RAM.

### Cómo retomar (checklist de reanudación)

> Esta subsección existe para que **cualquiera** (humano o LLM) pueda retomar
> sin releer todo el plan. Estado a 2026-06-15.

**Lo construido y verde (no tocar salvo refactor con ADR):**

- `core/` (motor agnóstico): `config · schemas · router · tiers · tools ·
  retrieval · policy · agent · controller · telemetry · circuit`.
- `usecases/tienda/` (ejemplo): `config.yaml · tools.py · prompts/ · grammars/ ·
  policies/policy.yaml · budgets.yaml · data/ · evals/sets/01..10`.
- 5 ADRs en `agent-local/docs/decisions/` (001 plataforma · 002 infra · 003
  policy-as-data · 004 verificación cruzada · 005 telemetría).
- **77 tests** verdes; `flake8` + `mypy` limpios; CI sin modelos.

**Comando para verificar el estado en cualquier momento:**

```bash
cd ~/projects/agent-local && .venv/bin/pytest -q && \
  .venv/bin/flake8 core tests --max-line-length 120 --extend-ignore E203,W503 && \
  .venv/bin/mypy core app
```

**Próximas acciones EN ORDEN cuando llegue el upgrade de RAM (≥32GB útiles):**

1. **Levantar los tiers** (F0.2): E4B:8091, 26B:8093 (12B:8092 solo si entra por
   §F2.1). Verificar con `bench/bench.sh`.
2. **Scoring conductual de los 10 sets** (F2.5): correr `evals/run.py` contra los
   tiers vivos; publicar matriz de confusión del router y reportes en
   `evals/reports/`. Gate por tier (tabla §F2.5).
3. **Acumular telemetría** (F3 ya implementado): con tráfico real, `ops/telemetry.jsonl`
   empieza a llenar la evidencia que condiciona F2.1/F2.4/F4.
4. **Decisión F2.1** (entrada del 12B): solo si la telemetría muestra que el 26B
   gasta >25% en tareas "medias" (carga de la prueba invertida).
5. **Decisión F2.4** (descarga del 31B): solo si el set 10 falla con 26B-verificado.
6. **F4 (QLoRA)**: NO antes de ≥4 semanas de logs + evals estables + ADR nuevo.

**Dónde mirar primero si algo falla**: `bench/RESULTS.md` (velocidad/calidad de
modelos), `evals/reports/` (regresión conductual), `ops/telemetry.jsonl`
(decisiones por request). La guía pedagógica 0→100 vive en
`Guia_MLOps/docs/48_AGENT_LOCAL_DE_0_A_100.md`.

**Cambio arquitectónico clave (ADR-001 del agente)**: `agent-local` dejó de ser
una app única y es ahora una **plataforma reutilizable**: la lógica
crítica (loop, policy gate, escalación objetiva, routing con gramática) vive en
`core/` (agnóstico al negocio) y cada dominio es un `usecases/<nombre>/` (config
+ tools + prompts + evals), **nunca un fork de `core/`**. Consumo por
`from core import load_agent` o por HTTP. El asistente de tienda es el use-case
de ejemplo (`usecases/tienda/`).

**Infra (ADR-002 del agente)**: Docker + docker-compose ahora (sin modelos en la
imagen); K8s/Terraform diferidos hasta decidir topología de modelos y volumen;
reuso de módulos del template cuando aplique.

**Repo público**: https://github.com/DuqueOM/agent-local (Apache-2.0, CI de
tests+lint sin modelos; docs en inglés).

### Decisiones v3 (revisión adversarial — resumen ejecutable)

| Decisión | Estado | Dónde aterriza |
|---|---|---|
| Dos capas + **durable-state-as-data** (tabla `sagas` en SQLite; sin Temporal) | adoptado | F1.6 |
| **ExecutiveController**: fachada `admit/execute/release`, interior de middlewares puros, ≤250 LOC, circuit breaker en memoria | adoptado | F2.0 |
| Cadena determinista pre-router (normalizer → alias → taxonomía → BM25) | adoptado | F1.5 |
| Embedder + **cache semántico**: DIFERIDO — trigger: ≥30% near-dups en logs (medible offline); si entra, cachea la RUTA, jamás la respuesta | trigger | F3 |
| **Arranque sin 12B** (router salta 0→2); entra solo con telemetría que lo exija | adoptado | F0/F2.1 |
| Juez cloud permitido SOLO en lanes de mantenimiento sin PII; high-stakes de clientes = juez local | adoptado | Plano mant. |
| **Reflect condicional** (solo tool-fail o `risk≥medium`); K=3 solo en high-stakes ASÍNCRONO y evals nocturnos | adoptado | F1.6/F2.3 |
| `budgets.yaml` estático por intent + **cap diario de cloud** + `max_reflections: 1`; adaptativo rechazado (revisar con 4 semanas de P95) | adoptado | F1.6 |
| `policies/*.yaml` + `decision_id` + **policy-change-requires-test** (set 06) | adoptado | F2.2 |
| **Telemetría obligatoria** (lane sin eventos no pasa el validator) con naming OTel-compatible (`trace_id`…) | adoptado | F1–F3 |
| Gobernanza del flywheel: PII-redacción al escribir, cuarentena + revisión humana, procedencia por registro, retención 30d crudo | schema ahora | F3/F4 |
| n8n: track diferido (trigger: ≥2 integraciones SaaS reales); core code-first | trigger | P3 |

---

## 0. Contexto fijo (no cambiar sin ADR)

| Recurso | Valor |
|---|---|
| Equipo | ASUS TUF Gaming F16 (FX608JPR) · i7-14650HX (16C/24T) · WSL2 Ubuntu-24.04 |
| GPU / VRAM | RTX 5070 **Laptop**, **8GB VRAM — soldada, fija para siempre** (techo duro) |
| RAM hoy | **2× 8GB DDR5-5600 SODIMM, ambos slots llenos, dual-channel (~90 GB/s)** — sin slot libre; todo upgrade es *reemplazo* |
| RAM techo | **64GB (2×32) = máximo declarado/confiable.** 96GB (2×48) = sobre lo declarado, apuesta sin garantía en HX. 128GB (2×64) = no soportado, no apostar |
| Runtime | llama.cpp (`llama-server`, API OpenAI-compatible) |
| Modelos en disco (`~/ml-models/`) | `gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf` (4.0G) · `gemma-4-12b-it-qat-q4_0.gguf` (6.5G) · `gemma-4-26B_q4_0-it.gguf` (14G) |
| Repos | `~/projects/template_MLOps` (plano de mantenimiento) · `~/projects/agent-local` (**plataforma LLM reutilizable**, repo público; el asistente de tienda es `usecases/tienda/`) |

> ⚠️ **Corrección 2026-06-15**: el "48GB" de versiones previas era un error de
> premisa (se creyó "16GB + slot libre → +32"). La realidad: 2 slots llenos con
> 8GB c/u; el upgrade reemplaza ambos. Objetivo recomendado **64GB (2×32) dual-
> channel** — desbloquea todas las fases pendientes con holgura para el 26B
> Q4_K_M a 16–32k de contexto. Ver §0.5 (upgrade-path RAM↔modelos).

### 0.5 Upgrade-path RAM ↔ modelos (lo que cada nivel de RAM desbloquea)

La VRAM (8GB) es el techo duro e inamovible; la RAM rápida es la palanca. La
velocidad de un MoE la manda **parámetros activos**, no totales
(`tok/s ≈ ~60 GB/s efectivos / (activos × bytes_por_param)`).

| RAM | Modelo "principal" viable | Modelo "juez" (tolera latencia) | Notas |
|---|---|---|---|
| 16GB (hoy) | E4B / 12B Q4 | — | el 26B-A4B no entra cómodo |
| **64GB (2×32, objetivo)** | **Qwen3-30B-A3B** (3B act, Q4 ~17GB) o 26B-A4B (4B act, ~15GB) | Gemma-4 31B Q4 (~17GB) **o** gpt-oss-120B **Q3** (~48GB, 5B act, batch-only, monopoliza RAM) | punto dulce; un solo modelo grande residente a la vez |
| 96GB (2×48, apuesta) | igual + contexto enorme | **gpt-oss-120B Q4** (~60GB, 5B act, ~10-18 tok/s) | la única RAM que mete gpt-oss-120B Q4 cómodo |

**Regla de selección por rol** (la decide el eval, no la intuición):
router = pequeño y estructurado (cabe en VRAM); principal = **MoE de activos
bajos** que quepa en RAM; juez = el más grande que entre, tolera lentitud.
Candidatos a evaluar tras el upgrade: **Qwen3-30B-A3B** como principal (upgrade
real al 26B-A4B); gpt-oss-120B (Q3 en 64GB / Q4 en 96GB) como juez. Mixtral
8×7B / 8×22B **descartados**: activos altos (13B/39B) → lentos en hardware
limitado por ancho de banda, y superados por los MoE de grano fino.

### 0.6 Modelos como configuración (swappability — regla de diseño)

**El modelo detrás de cada tier es CONFIGURACIÓN, nunca código.** Cambiar un
modelo (particular o la familia entera) debe ser editar YAML + re-validar, cero
cambios de código. Esto ya es posible porque el cliente es OpenAI-compatible y
el routing usa GBNF (agnósticos al modelo); esta regla lo formaliza:

1. **Registro `models.yaml`**: cada entrada = `{tier, model_id, gguf_path,
   port, quant, context, role, min_ram_gb, expected_tok_s}`. El tier referencia
   un `model_id`, no una ruta hardcodeada.
2. **Validación de capacidad**: el controller comprueba `min_ram_gb` y VRAM
   disponibles ANTES de cargar — si el modelo no cabe, falla limpio, no swappea.
3. **Gates de eval por ROL, no por modelo** (ya es el diseño, §F2.5): cualquier
   modelo que entra a un tier DEBE re-pasar los eval sets de ese tier. Es lo que
   hace el swap **seguro** en vez de una apuesta.
4. **Runbook de swap**: descargar GGUF → registrar en `models.yaml` →
   `llama-bench` (gate de velocidad) → eval set del tier (gate de calidad) → si
   ambos verdes, promover; si no, revertir el `model_id`. Una entrada en
   `bench/RESULTS.md` por swap.

✅ **Coste de hacerlo ahora vs después**: hacerlo durante la construcción es
trivial (un YAML + un loader); retrofitearlo tras hardcodear rutas es doloroso.
Es además la señal "engineered for change" para entrevista: el sistema no está
casado con Gemma — está casado con *contratos* (JSON con gramática, eval por
tier), y los modelos son intercambiables debajo de ellos.

**Principios no negociables** (copiados del marco — verifícalos en cada PR):

1. Sin fine-tuning en esta etapa: routing + prompts estructurados + retrieval.
2. El modelo nunca muta estado crítico sin validación de políticas.
3. Cada lane necesita eval harness ANTES de subir autonomía.
4. El loop más simple que funcione.
5. Inventario/precios/stock NUNCA en memoria del modelo — siempre API en vivo.
6. Local primero; cloud solo como desborde explícito.

### 0.1 Tier table (reconciliada con los artefactos en disco)

| Tier | Rol | Modelo objetivo | Artefacto HOY | Acción |
|---|---|---|---|---|
| 0 | Router/guardrail | E4B Q4_K_M | E4B QAT Q4_K_XL ✅ | benchear el local primero |
| 1 | Razonamiento medio | 12B Q4_K_M | 12B QAT Q4_0 ✅ | benchear el local primero |
| 2 | Asistente principal | 26B-A4B Q4_K_M | 26B QAT Q4_0 ✅ | benchear el local primero |
| 3 | Verificador/escalación | 31B Q4_K_M | ❌ no descargado | **diferido** — solo si Gate-3 lo exige |

> ⚠️ **Sobre el 31B**: en este hardware rinde ~2–4 tok/s (denso, ancho de banda
> limitado). Es INVIABLE como asistente interactivo pero VIABLE como verificador
> tolerante a latencia (verificación final, evals nocturnos, casos escalados sin
> SLA de chat). No lo descargues hasta el paso F2.4. Cuando toque: repo oficial
> `ggml-org` GGUF Q4_K_M (~17GB).

> 📝 **Política de cuantización**: el marco pide Q4_K_M. Tenemos QAT-Q4_0/Q4_K_XL
> ya descargados. Regla: bench primero lo local (paso F0.3); descarga el Q4_K_M
> de `ggml-org` SOLO si el local falla su gate por calidad (no por velocidad).
> Documenta cualquier cambio en `bench/RESULTS.md`.

### 0.2 Contrato de roles — REGLA DE ARQUITECTURA (no una tabla informativa)

Cada modelo tiene UN rol fijo con contrato. Violar el contrato es un bug de
arquitectura, no una preferencia:

| Modelo | Rol contractual | PUEDE | NO PUEDE |
|---|---|---|---|
| **E4B** | Router / guardrail | clasificar, normalizar alias, emitir JSON de routing con confidence | redactar respuestas al cliente; aprobar nada |
| **12B** | Amortiguador de razonamiento medio | clarificaciones, borradores que otro verificará, fallback E4B→26B | ser destino final de casos comerciales o high-stakes |
| **26B-A4B** | Asistente principal | conversación cliente, matching semántico, planear tools, multi-turn | aprobar sus propias violaciones de política; tocar estado sin policy gate |
| **31B** | **JUEZ** (no worker diario) | verificación final, casos high-stakes escalados, auditorías, evals nocturnos | atender tráfico interactivo; ser fallback por pereza de routing |

Cláusulas:

- **Cláusula del 12B**: permanece en la arquitectura SOLO mientras los evals
  por tier demuestren que reduce escalaciones innecesarias al 26B y mejora
  las clarificaciones. Si dos ciclos de eval seguidos no lo justifican, se
  retira y el router salta 0→2. Está por utilidad medida, no "porque está ahí".
- **Cláusula del juez**: el 31B nunca recibe una tarea que un tier inferior
  no haya intentado, salvo `risk=high` o verificación final. Su tiempo de
  cómputo es caro: cada invocación queda loggeada con su justificación.
- El que redacta NUNCA es el que aprueba: la verificación de una respuesta
  de tier N la hace el policy layer determinista + (si `risk≥medium`) un
  pase de crítica en tier N o N+1 con prompt de verificador, jamás el mismo
  prompt que generó.

---

## FASE 0 — Runtime y bake-off (prerrequisito de todo)

### F0.1 Instalar llama.cpp con soporte CUDA

```bash
cd ~/tools && git clone https://github.com/ggml-org/llama.cpp && cd llama.cpp
cmake -B build -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release -j "$(nproc)" --target llama-server llama-bench llama-cli
# Verificación:
./build/bin/llama-server --version && ./build/bin/llama-bench --help >/dev/null && echo OK
```

**Aceptación**: imprime versión y `OK`. Si CUDA falla, compila sin
`-DGGML_CUDA=ON` y anota "CPU-only" en `bench/RESULTS.md` (los gates de
velocidad bajan 30%).

### F0.2 Lanzar cada modelo como servidor (puertos fijos)

```bash
# Tier 0 (E4B) — puerto 8091
~/tools/llama.cpp/build/bin/llama-server -m ~/ml-models/gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf \
  --port 8091 -ngl 99 -c 8192 --host 127.0.0.1 &
# Tier 1 (12B) — puerto 8092  (-ngl parcial: ~20 capas caben en 8GB VRAM)
~/tools/llama.cpp/build/bin/llama-server -m ~/ml-models/gemma-4-12b-it-qat-q4_0.gguf \
  --port 8092 -ngl 20 -c 16384 --host 127.0.0.1 &
# Tier 2 (26B-A4B) — puerto 8093 (MoE: experts a CPU, atención a GPU)
~/tools/llama.cpp/build/bin/llama-server -m ~/ml-models/gemma-4-26B_q4_0-it.gguf \
  --port 8093 -ngl 99 --override-tensor "ffn_.*_exps.=CPU" -c 16384 --host 127.0.0.1 &
```

> 💡 Solo UN servidor grande a la vez en producción local (RAM). Para el bench
> está bien secuencial: levanta → mide → mata (`pkill -f llama-server`).

### F0.3 Script de benchmark y gates

Crea `~/projects/agent-local/bench/bench.sh`:

```bash
#!/usr/bin/env bash
# Uso: ./bench.sh <puerto> <nombre>
set -euo pipefail
PORT=$1; NAME=$2
PROMPT='Clasifica la intención y responde SOLO JSON: {"intent":"...","tier":0}. Mensaje: "tienen coca de 600 fria?"'
START=$(date +%s.%N)
RESP=$(curl -s http://127.0.0.1:$PORT/v1/chat/completions -H 'Content-Type: application/json' \
  -d "{\"messages\":[{\"role\":\"user\",\"content\":\"$PROMPT\"}],\"max_tokens\":120,\"temperature\":0}")
END=$(date +%s.%N)
TOKENS=$(echo "$RESP" | python3 -c 'import sys,json;print(json.load(sys.stdin)["usage"]["completion_tokens"])')
echo "$NAME: $(echo "$TOKENS/($END-$START)" | bc -l | cut -c1-5) tok/s" | tee -a RESULTS.md
```

**Gates (anótalos en `bench/RESULTS.md`; si uno falla, STOP y reporta):**

| Tier | Gate velocidad | Gate calidad |
|---|---|---|
| E4B | ≥ 25 tok/s | 18/20 en el set de routing (F1.6) |
| 12B | ≥ 10 tok/s | supera a E4B en el set de clarificación |
| 26B | ≥ 8 tok/s @16k | supera a 12B en el set de matching semántico |

---

## FASE 1 — Esqueleto del agente (read-only, E4B + 26B)

### F1.1 Crear el repo

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"   # ver pyproject.toml
```

> **NOTA v3.1 (implementado, ADR-001 del agente)**: la estructura objetivo
> original (todo bajo `app/`) evolucionó a una **plataforma reutilizable**. La
> lógica crítica vive en `core/` (agnóstica al negocio) y cada dominio es un
> `usecases/<nombre>/`. Los bloques de código de F1.2–F1.x abajo siguen siendo
> la **referencia conceptual** de cada contrato/estación; su ubicación real es
> `core/` (motor) y `usecases/tienda/` (config + tools del ejemplo).

Estructura real (repo `agent-local`):

```
agent-local/
├── core/                  # MOTOR agnóstico al negocio (fuente única de verdad)
│   ├── config.py          #   UsecaseConfig: carga prompts/grammar/budgets/policy
│   ├── schemas.py         #   contratos Pydantic (intent = str; la gramática fija el set)
│   ├── router.py          #   Tier 0 → JSON estricto (GBNF) + validación allowed_intents
│   ├── tiers.py           #   clientes por tier (endpoints inyectados desde config)
│   ├── tools.py           #   ToolRegistry (la APP ejecuta; namespaces por use-case)
│   ├── retrieval.py       #   BM25 + factory de semantic_retrieval
│   ├── policy.py          #   gate determinista (reglas = datos: PolicyRules)
│   ├── agent.py           #   loop de 7 estaciones (prompts inyectados desde config)
│   └── __init__.py        #   load_agent(name)
├── usecases/tienda/       # USE-CASE de ejemplo (asistente de tienda)
│   ├── config.yaml        #   endpoints, allowed_intents, reglas de policy, prompts
│   ├── tools.py           #   build_registry(config) -> ToolRegistry
│   ├── prompts/ grammars/ data/ policies/ budgets.yaml evals/sets/
│   └── __init__.py        #   expone build_registry
├── core/telemetry.py      #   F3: TelemetrySink (JSONL por request, PII redactada)
├── core/controller.py     #   F2.0: ExecutiveController + circuit breaker + verifier
├── app/main.py            # webhook/transport FastAPI; carga use-case vía AGENT_USECASE
├── tests/ bench/ evals/run.py   # 77 tests verdes (flake8 + mypy limpios)
├── Dockerfile docker-compose.yml pyproject.toml
└── docs/decisions/        # ADR-001 plataforma · 002 infra calibrada · 003 policy-as-data
                           #   · 004 verificación cruzada · 005 telemetría de decisiones
```

**Crear un dominio nuevo** = nueva carpeta `usecases/<nombre>/` (config + tools +
prompts + evals), **nunca** un fork de `core/`.

### F1.2 Contratos (`app/schemas.py`) — escribir PRIMERO

```python
from pydantic import BaseModel, Field
from typing import Literal

class Route(BaseModel):
    intent: Literal["product_lookup", "order_create", "order_status",
                    "smalltalk", "complaint", "policy_question",
                    "maintenance_task", "unknown"]
    tier: Literal[0, 1, 2, 3]
    confidence: float = Field(ge=0.0, le=1.0)  # escalación OBJETIVA, no heurística
    risk: Literal["low", "medium", "high"]
    ambiguity: Literal["low", "medium", "high"]
    tool_needed: bool
    finality: Literal["answer", "clarify", "escalate"]
    expected_followup: bool

class RequestBudget(BaseModel):
    """Presupuesto por request — evita loops bonitos pero caros.
    v3: los valores por intent viven en budgets.yaml (versionado);
    este modelo solo los tipa. Adaptativo: rechazado hasta tener
    >=4 semanas de P95 reales."""
    max_iterations: int = 4
    max_tool_calls: int = 6
    max_reflections: int = 1            # v3: reflect es condicional y acotado
    latency_budget_ms: int = 8000       # SLA del canal (WhatsApp ≈ 8s)
    can_escalate_t3: bool = False       # el 31B requiere permiso explícito
    # cap diario de cloud: contador global en el controller, no por request

class ToolCall(BaseModel):
    tool: str
    args: dict

class Observation(BaseModel):
    tool: str
    ok: bool
    data: dict
    error: str | None = None

class Verdict(BaseModel):
    approved: bool
    violations: list[str] = Field(default_factory=list)
    escalate_to_tier: int | None = None
```

### F1.3 Router Tier 0 con gramática (salida JSON imposible de romper)

`grammars/route.gbnf` (llama.cpp GBNF — fuerza el shape del JSON):

```
root   ::= "{" ws "\"intent\"" ws ":" ws intent "," ws "\"tier\"" ws ":" ws tier "," ws "\"confidence\"" ws ":" ws conf "," ws "\"risk\"" ws ":" ws lvl "," ws "\"ambiguity\"" ws ":" ws lvl "," ws "\"tool_needed\"" ws ":" ws bool "," ws "\"finality\"" ws ":" ws fin "," ws "\"expected_followup\"" ws ":" ws bool ws "}"
intent ::= "\"product_lookup\"" | "\"order_create\"" | "\"order_status\"" | "\"smalltalk\"" | "\"complaint\"" | "\"policy_question\"" | "\"maintenance_task\"" | "\"unknown\""
tier   ::= "0" | "1" | "2" | "3"
conf   ::= "0." [0-9] [0-9]? | "1.0"
lvl    ::= "\"low\"" | "\"medium\"" | "\"high\""
fin    ::= "\"answer\"" | "\"clarify\"" | "\"escalate\""
bool   ::= "true" | "false"
ws     ::= [ \t\n]*
```

`app/router.py`:

```python
import httpx, json
from .schemas import Route

ROUTER_URL = "http://127.0.0.1:8091/v1/chat/completions"
SYSTEM = open("prompts/router.md").read()
GRAMMAR = open("grammars/route.gbnf").read()

RULES = """Reglas de tier (aplícalas tras clasificar):
1. simple/determinista/clasificación -> tier 0
2. razonamiento moderado sin planning -> tier 1
3. cara al cliente, semántico, comercial o multi-tool -> tier 2
4. alto riesgo, ambiguo, o afecta pedidos/dinero/confianza -> tier 3
5. NUNCA saltes directo a 3 salvo risk=high o ambiguity=high.
confidence: tu certeza en ESTA clasificación (0.00-1.0)."""

# Escalación OBJETIVA (en loop.py, no en el prompt):
#   confidence < 0.70           -> sube un tier antes de planear
#   verificación rechaza        -> sube un tier (una sola vez)
#   tier==3 requerido pero budget.can_escalate_t3==False
#                               -> respuesta parcial segura + flag a humano

def route(message: str) -> Route:
    r = httpx.post(ROUTER_URL, json={
        "messages": [{"role": "system", "content": SYSTEM + "\n" + RULES},
                     {"role": "user", "content": message}],
        "temperature": 0, "max_tokens": 160, "grammar": GRAMMAR,
    }, timeout=30)
    return Route.model_validate_json(r.json()["choices"][0]["message"]["content"])
```

`prompts/router.md` (versionado en git — NO inline en código):

```markdown
Eres el router de un asistente de tienda por WhatsApp. Clasifica el mensaje
del cliente y produce SOLO el JSON pedido. Normaliza ortografía y alias
mentalmente ("coca"→producto familia Coca-Cola) pero NO resuelvas el pedido.
risk=high si el mensaje implica dinero, pedido o promesa. ambiguity=high si
falta talla/cantidad/variante para actuar.
```

### F1.4 Herramientas (la app ejecuta, el modelo solo las nombra)

`app/tools.py`:

```python
from .schemas import Observation

# Fase 1: stubs read-only contra fixtures. Fase 2: APIs reales.
REGISTRY = {}

def tool(name):
    def deco(fn):
        REGISTRY[name] = fn
        return fn
    return deco

@tool("inventory_lookup")
def inventory_lookup(product_id: str) -> Observation:
    import json
    db = json.load(open("retrieval/data/inventory_fixture.json"))
    item = db.get(product_id)
    return Observation(tool="inventory_lookup", ok=item is not None,
                       data=item or {}, error=None if item else "not_found")

@tool("alias_lookup")
def alias_lookup(text: str) -> Observation:
    import json
    aliases = json.load(open("retrieval/data/aliases.json"))
    hits = [pid for pid, names in aliases.items()
            if any(a in text.lower() for a in names)]
    return Observation(tool="alias_lookup", ok=bool(hits), data={"candidates": hits})

# Mismo patrón: pricing_lookup, order_create (Fase 1: SIEMPRE dry_run=True),
# order_status, crm_lookup, policy_check, semantic_retrieval (BM25, F1.5).

def run(call):  # punto único de ejecución + logging
    fn = REGISTRY.get(call.tool)
    if fn is None:
        return Observation(tool=call.tool, ok=False, data={}, error="unknown_tool")
    return fn(**call.args)
```

> ⚠️ **`order_create` en Fase 1 es SIEMPRE `dry_run=True`.** El flag real lo
> habilita el policy layer en Fase 2, nunca el modelo.

### F1.5 Retrieval file-based (antes que cualquier vector store)

`retrieval/data/aliases.json` (semilla — crece con los logs):

```json
{
  "SKU-COCA-600": ["coca", "cocacola", "coca cola", "coca de 600", "refresco coca"],
  "SKU-FRIJOL-NEGRO-1KG": ["frijol", "frijol negro", "frijol americano", "frijoles"]
}
```

BM25 sobre archivos (`app/retrieval.py`): indexa `retrieval/data/*.md`
(políticas de tienda, promociones, plantillas de objeciones) con `rank-bm25`;
expón `semantic_retrieval(query, k=3)` como tool. **Nada de stock/precio aquí.**

### F1.6 Loop formal (`app/loop.py`) y webhook (`app/main.py`)

El loop completo tiene 7 estaciones — en Fase 1 `reflect` y `critic` pueden
ser el mismo modelo con prompts distintos; en Fase 2 `critic` sube de tier:

```
route → plan → tools → observe → reflect → critic → policy → finalize
  E4B    tierN   app     app      tierN    tierN/N+1  determinista  tierN
```

- **plan**: máx `budget.max_tool_calls` herramientas, nombradas explícitamente.
- **observe**: resultados de tools inyectados en schema compacto.
- **reflect**: el modelo contrasta su plan con las observaciones — ¿falta un
  dato? ¿la herramienta contradijo la suposición? (1 pase, sin chain-of-thought
  expuesto).
- **critic**: prompt de verificador (NO el de generación): consistencia con
  datos vivos, claridad, cero inventario alucinado, cero promesas ilegales.
- **policy**: gate determinista (F2.2) — **invariante: NINGUNA respuesta final
  sale sin pasar `product_exists`, `stock_confirmed`, `price_confirmed`,
  `no_overpromise` y `tone_brand`**. Sin excepciones, ni siquiera smalltalk
  que mencione productos.
- **finalize**: formato cliente, corto y comercial.

Stop-conditions duras (del `RequestBudget`): `max_iterations`; si
`finality=clarify` dos veces seguidas → UNA pregunta directa al usuario;
si oscila → plantilla segura; si `latency_budget_ms` se agota → respuesta
parcial segura + flag.

**Profundidad adaptativa (v3)**: `reflect` corre SOLO si (a) una tool falló o
contradijo el plan, o (b) `risk≥medium`. Smalltalk y lookups limpios van
`plan→tools→policy→final` — el pase extra de modelo no se paga donde no aporta.

Webhook FastAPI: `POST /webhook/whatsapp` valida firma (token en env
`WA_VERIFY_TOKEN`), encola el mensaje, responde 200 inmediato, procesa async y
contesta vía API de WhatsApp Business (env `WA_TOKEN`, `WA_PHONE_ID`). En Fase
1 puedes probar TODO con `POST /dev/message {"text": "..."}` sin WhatsApp.

**Cola y estado durable (v3)** — una sola SQLite (`app/state.db`, WAL):

- tabla `queue(conv_id, msg, status, ts)` — un worker por conversación
  (orden garantizado); un crash NO pierde mensajes.
- tabla `sagas(saga_id, tipo, paso, estado, deadline, retries)` — el patrón
  *durable-state-as-data* para flujos multi-día (pedido → confirmación →
  seguimiento) con un sweep periódico del worker. **Sin Temporal**: ese es un
  ADR-trigger (≥3 tipos de saga o exactly-once distribuido).
- `budgets.yaml`: presupuesto por intent (los defaults del schema son
  fallback); cap diario de cloud como contador del controller.

### F1.7 Set de routing + tests (gate de la fase)

`evals/sets/01_intent.jsonl` — 20 casos mínimos (5 product_lookup con alias y
faltas de ortografía, 3 order_create, 3 complaint, 3 smalltalk, 3 policy, 3
ambiguos que DEBEN salir `finality=clarify`). Runner `evals/run.py`: lee JSONL,
llama `route()`, compara `intent/tier/finality`, imprime accuracy y guarda
`evals/reports/<fecha>_intent.json`.

**Aceptación Fase 1**: router ≥ 18/20; loop end-to-end responde un
`product_lookup` con alias + fixture de stock sin alucinar inventario;
`pytest tests/` verde; todo read-only.

---

## FASE 2 — Controller, tiers intermedios, verificador, políticas y evals

### F2.0 ExecutiveController (`app/controller.py`) — v3

Fachada única por la que pasa TODO request; interior de **middlewares puros**
(`(ctx) -> ctx`, testeables aislados). Tope duro: ≤250 LOC o se parte.

```python
class ExecutiveController:
    def admit(self, msg) -> Ctx:      # normalize → alias/BM25 → route(E4B) → budget
    def execute(self, ctx) -> Ctx:    # loop adaptativo; retries SOLO de tools
                                      # idempotentes; circuit breaker por tier
                                      # (3 fallos → degradar un tier + plantillas,
                                      # half-open 60s; estado EN MEMORIA)
    def release(self, ctx) -> Final:  # policy gate → telemetría → finalize
```

Qué NO va aquí: prompts, lógica de negocio, conocimiento del dominio.

### F2.1 Tier 1 (12B) como fallback intermedio — ENTRADA CONDICIONADA (v3)
**Arranque SIN 12B**: el router salta 0→2. El artefacto queda en disco; el
12B entra solo cuando la telemetría muestre que el 26B gasta >25% de su
tiempo en tareas que el set 07 clasifica como "medias" (carga de la prueba
invertida). Si entra: `app/tiers.py` cliente por puerto; escalación si el
verificador del tier N rechaza o `confidence<umbral`, re-ejecuta en N+1 (una
sola vez).

### F2.2 Policy layer (`app/policy.py`) — gate determinista, NO LLM

```python
CHECKS = [
    ("product_exists",  lambda ctx: ctx.product is not None),
    ("stock_confirmed", lambda ctx: ctx.stock_checked_live),
    ("price_confirmed", lambda ctx: ctx.price_checked_live),
    ("order_rules",     lambda ctx: ctx.order is None or ctx.order.valid()),
    ("no_overpromise",  lambda ctx: not ctx.reply_mentions_unavailable_promise()),
    ("tone_brand",      lambda ctx: ctx.reply_passes_tone_lint()),
]
def check(ctx) -> Verdict:
    fails = [n for n, f in CHECKS if not f(ctx)]
    return Verdict(approved=not fails, violations=fails,
                   escalate_to_tier=3 if fails else None)
```

Si falla: escalar a Tier 3 → o pedir aclaración → o respuesta parcial segura
(en ese orden). El modelo JAMÁS aprueba su propia violación.

**Políticas como datos (v3)**: umbrales, tools permitidas por intent, montos
máximos, compromisos prohibidos y tono por canal viven en `policies/*.yaml`
(versionado — el diff del PR ES el audit trail de compliance). Cada veredicto
emite `{policy_version, rules_fired, decision_id}` a telemetría. **Regla
policy-change-requires-test**: ningún cambio de YAML se mergea sin su caso en
el set 06 que falle sin el cambio. OPA/Rego: rechazado a esta escala
(re-evaluar solo con multi-tenant).

### F2.3 Pase de crítica (verificación cruzada)
Para `risk=medium|high`: la respuesta del 26B pasa por un prompt de verificador
("¿consistente con los datos de tools? ¿promete algo no confirmado? ¿claro para
el cliente?") en el MISMO 26B (Fase 2a) y en 31B cuando exista (Fase 2b).

**Self-consistency (v3, acotado)**: K=3 con voto SOLO en flujos high-stakes
ASÍNCRONOS (confirmación de pedido, 15–20s aceptables) y en evals nocturnos.
En interactivo, 3 pases del 26B revientan el budget de 8s: pase único + juez.

### F2.4 Tier 3 (31B) — descarga condicionada
Descarga `ggml-org` Q4_K_M (~17GB) SOLO si: (a) el eval de high-stakes (set 10)
falla con 26B-verificado, o (b) los evals nocturnos lo justifican. Úsalo
exclusivamente en: verificación final, evals nocturnos, escalaciones sin SLA.

### F2.5 Los 10 sets de evaluación
En `evals/sets/`: `01_intent`, `02_alias_match`, `03_oos_substitution`,
`04_upsell`, `05_objections`, `06_policy_violation`, `07_ambiguity`,
`08_multiturn`, `09_tool_failure`, `10_high_stakes` (20–40 casos c/u, JSONL:
`{"input":..., "expected":..., "must_escalate":bool, "must_call_tools":[...]}`).
El runner mide: accuracy, corrección de escalación, corrección de tools, tasa
de alucinación (mención de stock/precio no presente en observations), latencia,
adherencia a políticas. Reportes versionados en `evals/reports/`.

**v3 — dos instrumentos adicionales**:

- **Golden set congelado** (`evals/golden/`, 50 casos, NUNCA se edita ni
  crece): mide deriva del sistema a largo plazo; los sets vivos miden
  cobertura. Editar el golden = invalidar la serie histórica.
- **Replay contra tráfico real**: `evals/replay.py --from logs/<dia>.jsonl
  --against <prompt|policy>` — todo cambio de prompt/política se prueba
  contra el tráfico de ayer ANTES de ver el de hoy.
- La matriz de confusión del router se publica por ciclo (no solo accuracy):
  escalar de más cuesta latencia; de menos, calidad.

**Gates de graduación POR TIER** (obligatorios antes de promover cualquier
cambio de prompt, modelo o regla — no basta el eval global):

| Tier | Gana en SU rol si... | Set que lo mide |
|---|---|---|
| E4B | precisión de routing ≥ umbral y confidence calibrada (alta conf ⇒ alta precisión) | 01_intent |
| 12B | reduce escalaciones innecesarias al 26B y mejora clarificaciones vs E4B | 07_ambiguity + 01 |
| 26B | supera al 12B en matching semántico/comercial real | 02, 03, 04, 05, 08 |
| 31B | atrapa violaciones que el 26B-verificado dejó pasar, en high-stakes | 06, 10 |

Reglas: ningún lane sube de autonomía sin regresión verde
(`pytest -m regression`) · un tier que pierde en su propio rol dos ciclos
seguidos se reconfigura o se retira (cláusula del 12B, §0.2) · el 31B
justifica coste/latencia solo en los casos seleccionados — si el eval
muestra que el 26B-verificado le empata, el 31B queda solo para evals
nocturnos.

---

## FASE 3 — Observabilidad y mejora continua
1. **Telemetría de decisiones** (JSONL por request, PII redactada) — campos
   obligatorios, porque sin esto el refinamiento es adivinanza:

   ```json
   {"ts": "...", "trace_id": "...", "route": {...}, "tier_final": 2,
    "confidence": 0.84, "escalated": false, "escalation_reason": null,
    "tools": ["alias_lookup", "inventory_lookup"], "tool_failures": [],
    "policy_verdict": {"approved": true, "violations": [],
                       "policy_version": "...", "decision_id": "..."},
    "critic_verdict": "approved", "latency_ms": {"route": 320, "total": 4100},
    "cost": {"tokens_by_tier": {"0": 160, "2": 840}},
    "budget_exhausted": false, "outcome": "answered",
    "provenance": {"source": "prod", "reviewer": null, "quarantine": true}}
   ```

   **v3 — tres reglas duras**: (1) la telemetría es CONTRATO, no buena
   práctica — un lane que no emite el schema no pasa el validator (el
   prediction-logger D-20 del mundo agéntico); (2) naming alineado a
   semconv de OTel (`trace_id` propagado a tools y tiers) para que adoptar
   OTel después sea un swap de transporte (trigger: equipo >1 o >1 host);
   (3) PII redactada EN EL MOMENTO de escritura, nunca después.

   Con esto se mejoran prompts, prompts de verificación y reglas de
   escalación con datos, no con intuición — y los campos `provenance` son
   la semilla gobernada del flywheel de F4: nada sale de cuarentena hacia
   un dataset sin revisión humana por lotes; crudo se retiene 30 días,
   curado indefinido; los rechazos del juez generan los pares de DPO.
2. Análisis offline semanal de fallos → nuevos casos a los sets (el eval set
   CRECE con producción).
3. **Ciclo de crecimiento del retrieval** (antes que cualquier LoRA): cada
   semana, los términos de cliente que el alias-lookup NO resolvió pasan a
   revisión → entradas nuevas en `aliases.json` / equivalencias de categoría /
   variantes regionales, vía PR. El retrieval madura con tráfico real; el
   modelo no memoriza nada.
4. Refinamiento de prompts SOLO con evidencia de evals (diff versionado en
   `prompts/`).
5. Generación sintética de variantes (alias regionales, faltas de ortografía)
   usando el 26B local — revisión humana antes de entrar al set.
6. Shadow mode: toda decisión de routing se loggea junto a "qué habría hecho
   el tier superior" en una muestra del 10%.

## FASE 4 — QLoRA (gate estratégico, NO antes)
Solo con: ≥4 semanas de logs, evals estables, y un patrón de estilo/tono/
política que el prompting no resuelva. Entrenar SOLO comportamiento estable
(tono, formato, protocolo de marca). PROHIBIDO entrenar sobre inventario,
stock o precios. Requiere ADR nuevo en el template.

---

## PLANO DE MANTENIMIENTO — lanes ADR-028 sobre el MISMO stack

> Absorbido de `ACTION_PLAN_ADR028.md` (ahora stub). Los lanes reutilizan los
> tiers, el cliente con gramática y el eval harness de las fases anteriores —
> es un segundo consumidor del mismo runtime, no otro sistema.

### L-4 Docs-drift updater (primer lane productivo — barato y verificable)

El LLM es el *redactor*, no el *detector*:

1. Extractor Python determinista recoge hechos visibles en código (conteos de
   rules/skills/workflows, nombres de overlays, tablas de inventario).
2. Comparador marca claims de docs que no coinciden — sin LLM.
3. `E4B` redacta el cuerpo del PR + diffs de docs SOLO para los mismatches,
   JSON-constrained.
4. Abre **PR CONSULT** vía `gh`. Humano mergea.

Runtime: **el laptop es el runner** (timer systemd semanal en WSL) — cero
dependencia de CI, cero coste cloud. Eval de admisión: 10 casos sintéticos de
drift sembrados (mutar un conteo, renombrar un overlay) → ≥9/10 detectados con
0 parches falsos.

### L-2 Memory plane Fase 2 (= P2.4) — embeddings-free primero

1. BM25 sobre artefactos existentes: `ops/audit.jsonl`, `docs/incidents/`,
   `VALIDATION_LOG.md`, `releases/*.md`, reportes de drift.
2. `scripts/memory_query.py "<pregunta>"` → top-k chunks → `E4B` resume **con
   citas file:line obligatorias** — una respuesta sin cita se descarta.
3. Eval: 20 preguntas históricas con respuesta conocida; recall@5 ≥ 80% o se
   reevalúa vector store (no antes).

### L-3 Triage de drift/incidentes

1. Joiner reúne: señales Prometheus (MCP), slices del prediction-log,
   historial de deploys (`git log` + digests).
2. `26B-A4B` redacta el borrador de RCA en `report_schema.json` — job batch,
   minutos de runtime aceptables.
3. El borrador se adjunta al issue. **El humano es dueño de la conclusión.**
4. Eval: replay de 3 incidentes históricos; causalidad alucinada (afirmar
   causa ausente de la evidencia) = fallo automático → esa subtarea va a cloud.

### L-1 CI self-healing Fase 2 — los modelos locales quedan FUERA del path de CI

Dos razones de seguridad (no de capacidad):

1. Los runners de GitHub no alcanzan el laptop.
2. Un runner self-hosted en laptop personal sobre repo público es un vector de
   ataque conocido (PRs de forks ejecutan en tu máquina) — **rechazado**.

En CI: clasificación heurística primero, cloud cheap-tier donde haga falta;
generación de parches en cloud, CONSULT, según `model_routing_policy.yaml`
(los tiers locales se registran ahí DEBAJO del tier cloud más barato; la
disciplina de solo-escalación de ADR-010 no cambia — un modelo local puede
señalar, nunca aprobar). Los tiers locales ayudan *offline*: job nocturno que
reproduce los fallos de CI del día contra el prompt clasificador para crecer
el corpus etiquetado (alimenta los triggers de revisión de fine-tuning, >10k
eventos etiquetados).

### Riesgos del plano (heredados y vigentes)

| Riesgo | Mitigación |
|---|---|
| Arquitectura Gemma-4 no soportada por converters | cadena de fallback: GGUF oficial → registry Ollama → cloud-only (los lanes son agnósticos vía cliente OpenAI-compatible) |
| Quant degrada al 26B bajo utilidad | gate de bench Fase 0 + side-by-side por tarea vs E4B; si pierde, se elimina el tier |
| Disponibilidad del laptop-runner | lanes semanales/on-demand, no sensibles a latencia; una semana perdida es benigna |
| Alucinación de modelo pequeño | JSON con gramática en todo; citas obligatorias; detectores deterministas aguas arriba de cada llamada LLM |

📝 **Fine-tuning sigue RECHAZADO** (ADR-028 §4): el trigger es volumen
etiquetado (>10k), no hardware. La Fase 4 de este plan es el único camino y
exige ADR nuevo.

## INTEGRACIÓN P2 (template_MLOps, 1–2 meses — desbloquea v1.0.0)

| # | Entregable | Pasos concretos |
|---|---|---|
| P2.1 | **Evidencia L4**: rollout real GKE+EKS | `deploy-gke` y `deploy-aws` skills sobre el servicio ejemplo → capturar `kubectl get pods/svc`, Grafana, coste → entradas fechadas en `ops/VALIDATION_LOG.md` → screenshots a `docs/evidence/` |
| P2.2 | 4 runbooks pendientes | `docs/runbooks/`: `gke-rollout.md`, `eks-rollout.md`, `rollback-validado.md`, `coste-ventana-l4.md` — formato de los 5 existentes |
| P2.3 | Ventana shadow 14 días (ADR-019 Fase 2) | activar prediction logger en el ejemplo, cron diario de captura, al día 14: reporte de drift con `drift-check` |
| P2.4 | ADR-018 Fase 2: ingest + retrieval | **REUSAR este stack**: `scripts/memory_ingest.py` (file-based, BM25 igual que F1.5) sobre `ops/audit.jsonl` + ADRs; lane `memory-retrieval` llama a E4B local (puerto 8091) con gramática |
| P2.5 | Skill + módulo `data-cleaning` | `agentic/skills/data-cleaning/SKILL.md` (modo AUTO) + `templates/common_utils/data_cleaning.py` (imputación, outliers, tipos — con tests) + sync adapters + validator strict |

## INTEGRACIÓN P3 (estratégico)

1. **Nicho en README** (primer párrafo): "ML tabular supervisado en K8s, 1–10
   modelos, GCP/AWS, con salidas documentadas a Vertex/SageMaker".
2. **Harness de evaluación agéntica en CI**: escenarios donde el agente DEBE
   escalar/negarse según AUTO/CONSULT/STOP, construidos sobre el red-team-log
   existente. Mismo runner de `evals/run.py` — los sets viven en
   `agentic/evals/`. Gate en `validate-templates.yml`.
3. **Variante LLM-serving del template**: evaluar como track separado SOLO
   tras v1.0.0 (ADR requerido; el asistente de tienda es el caso de estudio).

## EVIDENCIA COMPARATIVA portfolio vs template (DOS experimentos)

> Son dos preguntas distintas y cada una necesita su experimento. Mezclarlas
> destruye la credibilidad de ambas.

### E-A: Migración con paridad (valida el TEMPLATE como contenedor)

Portar el pipeline del portfolio TAL CUAL (mismas features, mismo algoritmo,
mismos hiperparámetros, misma semilla) sobre el scaffold del template.

| Dimensión | Portfolio (manual) | Template (medir) |
|---|---|---|
| Tiempo a servicio desplegable | semanas (real) | horas (`new-service.sh` + datos) |
| Líneas escritas a mano | todas | solo `train.py` + features |
| Incidentes de serving | 3 sufridos | 0 (D-01..D-32 los previenen) |
| Gates automáticos | a posteriori | día cero |
| Métricas | AUC 0.87 | **≈ igual — paridad = migración fiel** |

### E-B: Re-desarrollo asistido (valida el PROCESO agéntico end-to-end)

Partir SOLO del dataframe crudo y ejecutar el ciclo completo asistido:
skill `eda-analysis` → skill `data-cleaning` (P2.5) → feature engineering →
selección de modelo + HPO (Optuna) → gates (leakage, fairness) → serving.
Aquí el proceso NO es idéntico al manual, así que las métricas PUEDEN y
suelen mejorar — por mecanismos identificables: limpieza más sistemática,
leakage detectado por gate, búsqueda de hiperparámetros más disciplinada,
selección de modelo más amplia.

**Objetivo declarado**: como mínimo paridad en una fracción del tiempo;
como meta, mejora atribuible. **Guardarraíles de honestidad** (sin esto el
experimento no vale):

1. **Mismo test set congelado** que el portfolio, intocable — nada de
   "probar hasta ganar" (eso es test-set shopping, no mejora).
2. Cada delta de métrica **atribuido a su mecanismo** en MLflow: run del
   baseline vs run asistido, con el cambio concreto etiquetado (p. ej.
   "imputación por grupo", "feature X eliminada por leakage-gate",
   "HPO 200 trials vs 30 manuales").
3. Validación con CV temporal idéntica a la original.
4. Si la mejora no llega, se publica igual: "paridad en 1/10 del tiempo"
   ya es la victoria de ingeniería.

La frase para entrevista: *"el template no mejora el modelo por arte de
magia; mejora el PROCESO que produce el modelo — y un proceso mejor
encuentra mejoras que el manual dejó sobre la mesa, con cada una trazada
en MLflow"*.

Salida de ambos: `docs/evidence/COMPARATIVE_BANKCHURN.md` con las dos
tablas + links a los runs de MLflow.

---

## FAULT-INJECTION DRILL — known-answer monitoring (aprovecha los datasets del portfolio)

> Idea del maintainer, adoptada: ya que probamos los datasets del portfolio,
> **inyectamos a propósito los fallos que documentamos en los ADRs** y
> verificamos que la superficie de monitoreo CORRECTA los detecta. Convierte
> "el sistema detecta fallos" (afirmación) en "inyecté ESTE fallo conocido y
> la alarma esperada disparó en T segundos" (evidencia con ground-truth).

⚠️ **Distinción crítica (no la pierdas)**: los incidentes de los ADRs son
**clases de fallo distintas**, cada una con su superficie de detección. Meterlas
todas a "drift" es el error que haría parecer que el monitoreo no sirve.

| Fallo (origen) | Clase | Cómo se inyecta | Superficie que DEBE detectar | Resultado esperado |
|---|---|---|---|---|
| 81% errores (D-01) | concurrencia/serving | overlay con `uvicorn --workers 4` | load test: error-rate + p95 | error-rate ↑, no drift |
| SHAP ceros (D-04) | bug compatibilidad | TreeExplainer sobre el Stacking | **contract test** | test rojo en CI, no runtime |
| HPA no baja (D-03) | config infra | HPA por memoria en overlay | métrica de réplicas en el tiempo | réplicas planas tras caída de tráfico |
| Fuga datos (ChicagoTaxi) | integridad training | re-introducir feature filtrada | **leakage gate** en `train.py` | promoción bloqueada |
| **Data drift** | distribución | perturbar 1-2 features | PSI en `run_drift_drill.py` | PSI > umbral, alerta |
| **Concept drift** | relación X→y | invertir relación en un slice | performance sliced | métrica del slice cae |

**Deliverable**: `templates/scripts/drills/fault_injection_matrix.py` — un caso
por fila, cada uno con: función de inyección, superficie esperada, y un assert
de "esta alarma y no otra debió dispararse". Cada ejecución emite una entrada a
`VALIDATION_LOG.md` (fallo, superficie esperada, alarma observada, tiempo de
detección).

**Por qué importa para el portfolio/CV**: no solo prueba el monitoreo —
demuestra que sabes **qué superficie atrapa cada clase de fallo**, el criterio
que distingue a un junior de alguien con experiencia de producción. Y es
grabable (pieza audiovisual E18) ANTES de cualquier L4 cloud: solo necesita el
servicio local + monitoreo local. Mejor relación evidencia/coste de la guía.

**Gate honesto**: cada fila debe detectarse en SU superficie (no en otra). Si
inyectas data-drift y salta el contract test pero NO el PSI, el bug está en tu
detector de drift, no en el drill — y eso también es un hallazgo que se publica.

---

## Cronograma y criterios de aceptación globales

| Semana | Hito |
|---|---|
| 1 | F0 completa (bench + RESULTS.md) · P2.5 skill data-cleaning |
| 2–3 | F1 completa (router+loop+retrieval+webhook dev, read-only) · P2.4 ingest |
| 4–5 | F2 (policy, verifier, 10 sets) · P2.1–P2.2 rollout L4 + runbooks |
| 6–7 | F3 (logging, shadow) · P2.3 cierre ventana 14d · experimento comparativo · **fault-injection drill (E18)** |
| 8 | P3.1–P3.2 · release candidate v1.0.0 del template |

**Aceptación global** (checklist final): router elige bien el tier en la
mayoría de casos · resuelve ambigüedad de producto con UNA pregunta máximo ·
cero alucinación de stock (eval 09/10 verdes) · estable en el laptop (un
modelo grande activo a la vez) · 31B selectivo · todo testeable y observable ·
ninguna respuesta expone chain-of-thought.
