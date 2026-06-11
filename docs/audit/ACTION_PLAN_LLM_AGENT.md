# ACTION PLAN — Framework Agéntico LLM Local (WhatsApp + Asistente de Tienda + Plano de Mantenimiento)

> **Autoridad**: ADR-028 (LLM-assist, 4 tiers), AGENTS.md (AUTO/CONSULT/STOP),
> ACTION_PLAN_ADR028.md (Fase 0 de benchmarks), guía oficial Gemma 4.
> **Audiencia**: un LLM ejecutor (puede ser menos capaz que el autor) o un humano.
> Cada paso incluye objetivo, archivos exactos, código, verificación y criterio
> de aceptación. **No improvises fuera de los pasos: si un gate falla, detente
> y reporta.**
>
> **Última actualización**: 2026-06-11.

---

## 0. Contexto fijo (no cambiar sin ADR)

| Recurso | Valor |
|---|---|
| Hardware | 48GB RAM (~36GB útiles), RTX 5070 Laptop 8GB VRAM, WSL2 Ubuntu-24.04 |
| Modelos en disco (`~/ml-models/`) | `gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf` (4.0G) · `gemma-4-12b-it-qat-q4_0.gguf` (6.5G) · `gemma-4-26B_q4_0-it.gguf` (14G) |
| Runtime | llama.cpp (`llama-server`, API OpenAI-compatible) |
| Repos | `~/projects/template_MLOps` (plano de mantenimiento) · `~/projects/agent-local` (NUEVO — asistente de tienda) |

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
mkdir -p ~/projects/agent-local/{app,bench,evals/sets,retrieval/data,prompts,grammars,tests}
cd ~/projects/agent-local && git init
python3 -m venv .venv && .venv/bin/pip install fastapi uvicorn httpx pydantic pytest rank-bm25 pyyaml
```

Estructura objetivo:

```
agent-local/
├── app/
│   ├── main.py            # webhook WhatsApp + orquestador
│   ├── router.py          # Tier 0 → JSON estricto
│   ├── loop.py            # planner→tools→observe→verify→finalize
│   ├── tiers.py           # clientes por puerto/modelo
│   ├── tools.py           # registro de herramientas (la APP las ejecuta)
│   ├── policy.py          # checker pre-respuesta
│   └── schemas.py         # Pydantic de TODOS los contratos
├── grammars/route.gbnf    # gramática JSON del router
├── prompts/*.md           # system prompts versionados
├── retrieval/             # alias, políticas, plantillas (file-based)
├── evals/                 # harness + 10 sets
└── bench/
```

### F1.2 Contratos (`app/schemas.py`) — escribir PRIMERO

```python
from pydantic import BaseModel, Field
from typing import Literal

class Route(BaseModel):
    intent: Literal["product_lookup", "order_create", "order_status",
                    "smalltalk", "complaint", "policy_question",
                    "maintenance_task", "unknown"]
    tier: Literal[0, 1, 2, 3]
    risk: Literal["low", "medium", "high"]
    ambiguity: Literal["low", "medium", "high"]
    tool_needed: bool
    finality: Literal["answer", "clarify", "escalate"]
    expected_followup: bool

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
root   ::= "{" ws "\"intent\"" ws ":" ws intent "," ws "\"tier\"" ws ":" ws tier "," ws "\"risk\"" ws ":" ws lvl "," ws "\"ambiguity\"" ws ":" ws lvl "," ws "\"tool_needed\"" ws ":" ws bool "," ws "\"finality\"" ws ":" ws fin "," ws "\"expected_followup\"" ws ":" ws bool ws "}"
intent ::= "\"product_lookup\"" | "\"order_create\"" | "\"order_status\"" | "\"smalltalk\"" | "\"complaint\"" | "\"policy_question\"" | "\"maintenance_task\"" | "\"unknown\""
tier   ::= "0" | "1" | "2" | "3"
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
5. NUNCA saltes directo a 3 salvo risk=high o ambiguity=high."""

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

### F1.6 Loop mínimo (`app/loop.py`) y webhook (`app/main.py`)

Loop: `route() → plan (tier elegido, máx 5 tool-calls nombradas) → run tools →
observar (schema compacto) → verificar (mismo tier en Fase 1) → finalizar`.
Stop-conditions duras: máx 4 iteraciones; si `finality=clarify` dos veces
seguidas → UNA pregunta directa al usuario; si oscila → plantilla segura.

Webhook FastAPI: `POST /webhook/whatsapp` valida firma (token en env
`WA_VERIFY_TOKEN`), encola el mensaje, responde 200 inmediato, procesa async y
contesta vía API de WhatsApp Business (env `WA_TOKEN`, `WA_PHONE_ID`). En Fase
1 puedes probar TODO con `POST /dev/message {"text": "..."}` sin WhatsApp.

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

## FASE 2 — Tiers intermedios, verificador, políticas y evals completos

### F2.1 Tier 1 (12B) como fallback intermedio
`app/tiers.py`: cliente por tier (puertos 8091–8094). Regla de escalación: si
el verificador del tier N rechaza o `confidence<umbral`, re-ejecuta plan en
N+1 (una sola vez).

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

### F2.3 Pase de crítica (verificación cruzada)
Para `risk=medium|high`: la respuesta del 26B pasa por un prompt de verificador
("¿consistente con los datos de tools? ¿promete algo no confirmado? ¿claro para
el cliente?") en el MISMO 26B (Fase 2a) y en 31B cuando exista (Fase 2b).

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

**Gates de graduación**: router en umbral → 26B > 12B en tareas reales →
31B solo donde su coste se justifique → ningún lane sube de autonomía sin
regresión verde (`pytest -m regression`).

---

## FASE 3 — Observabilidad y mejora continua
1. Logging de conversaciones (JSONL: route, plan, tools, verdicts, latencias
   por tier) con PII redactada.
2. Análisis offline semanal de fallos → nuevos casos a los sets (el eval set
   CRECE con producción).
3. Refinamiento de prompts SOLO con evidencia de evals (diff versionado en
   `prompts/`).
4. Generación sintética de variantes (alias regionales, faltas de ortografía)
   usando el 26B local — revisión humana antes de entrar al set.
5. Shadow mode: toda decisión de routing se loggea junto a "qué habría hecho
   el tier superior" en una muestra del 10%.

## FASE 4 — QLoRA (gate estratégico, NO antes)
Solo con: ≥4 semanas de logs, evals estables, y un patrón de estilo/tono/
política que el prompting no resuelva. Entrenar SOLO comportamiento estable
(tono, formato, protocolo de marca). PROHIBIDO entrenar sobre inventario,
stock o precios. Requiere ADR nuevo en el template.

---

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

## EVIDENCIA COMPARATIVA portfolio vs template (experimento)

> Ver discusión: el template NO mejora métricas de modelo (mismos datos +
> mismo algoritmo = mismo AUC). La comparación honesta es de **ingeniería**:

| Dimensión | Portfolio (manual) | Template (medir) |
|---|---|---|
| Tiempo a servicio desplegable | semanas (real) | horas (`new-service.sh` + datos) |
| Líneas escritas a mano | todas | solo `train.py` + features |
| Incidentes de serving | 3 sufridos | 0 esperados (D-01..D-32 los previenen) |
| Gates automáticos | añadidos a posteriori | día cero |
| Paridad de métricas | AUC 0.87 | **debe ser ≈ igual** (valida la migración) |

Pasos: scaffold con `new-service.sh BankChurnT bankchurn_t` → portar
features/training del portfolio → correr gates → desplegar con overlay dev →
tabla en `docs/evidence/COMPARATIVE_BANKCHURN.md`. **La paridad de AUC es el
resultado correcto; el delta está en tiempo, defectos evitados y gobernanza.**

---

## Cronograma y criterios de aceptación globales

| Semana | Hito |
|---|---|
| 1 | F0 completa (bench + RESULTS.md) · P2.5 skill data-cleaning |
| 2–3 | F1 completa (router+loop+retrieval+webhook dev, read-only) · P2.4 ingest |
| 4–5 | F2 (policy, verifier, 10 sets) · P2.1–P2.2 rollout L4 + runbooks |
| 6–7 | F3 (logging, shadow) · P2.3 cierre ventana 14d · experimento comparativo |
| 8 | P3.1–P3.2 · release candidate v1.0.0 del template |

**Aceptación global** (checklist final): router elige bien el tier en la
mayoría de casos · resuelve ambigüedad de producto con UNA pregunta máximo ·
cero alucinación de stock (eval 09/10 verdes) · estable en el laptop (un
modelo grande activo a la vez) · 31B selectivo · todo testeable y observable ·
ninguna respuesta expone chain-of-thought.
