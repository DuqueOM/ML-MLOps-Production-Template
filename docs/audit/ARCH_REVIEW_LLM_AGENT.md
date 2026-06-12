# Revisión Arquitectónica — Framework Agéntico Local-First

> Solicitada por el maintainer (2026-06-12) con mandato explícito de crítica
> activa: *"no asumir que las decisiones actuales son correctas"*. Esta
> revisión cuestiona el plan vigente (`ACTION_PLAN_LLM_AGENT.md` v2), valida
> lo que sobrevive a la crítica y propone cambios donde existe algo superior.
> Veredictos en **negrita** al final de cada sección.

---

## 0. Resumen ejecutivo (las 6 decisiones que importan)

| # | Pregunta | Veredicto |
|---|---|---|
| 1 | ¿n8n como orquestador del framework? | **NO en el núcleo agéntico. SÍ opcional como capa de integración/edge** (webhooks, conectores SaaS) |
| 2 | ¿Temporal/Camunda/Airflow? | **No ahora.** Temporal es el candidato correcto SI esto se vuelve producto multi-tenant; Camunda/Airflow no encajan con loops agénticos |
| 3 | ¿Framework de agentes (LangGraph, CrewAI, AutoGen…)? | **No para el núcleo.** El loop propio en Python/FastAPI es la decisión correcta — con LangGraph como única reevaluación futura si el grafo de estados crece |
| 4 | ¿Executive Controller como componente? | **Sí, pero como módulo, no como servicio**: ya existe implícito (router+budget+policy+telemetría); nombrarlo y darle interfaz única es la mejora real |
| 5 | ¿Los 4 modelos Gemma? | **3 confirmados, 2 condicionales**: E4B y 26B-A4B son el corazón; 12B y 31B viven bajo cláusulas de eval (ya codificadas). Falta: un **embedding model** pequeño |
| 6 | ¿El loop de 7 estaciones es óptimo? | **Sí para este dominio.** Tree-search/debate/multi-agente: rechazados con argumentos (abajo). Única adición: self-consistency K=3 SOLO en high-stakes |

---

## 1. Arquitectura general — crítica honesta

**Lo que está bien y sobrevive a la crítica:**

- Local-first con cloud como válvula explícita: correcto para datos de
  clientes/precios y coste marginal cero.
- Contratos Pydantic en cada frontera: es lo que hace el sistema testeable.
- Policy gate determinista separado del modelo: la decisión más importante
  del diseño; ningún framework del mercado te la regala.

**Debilidades reales detectadas (no cosméticas):**

1. **SPOF: el laptop.** Un solo host corre modelos, gateway, tools y memoria.
   Mitigación honesta (no "compra un cluster"): healthchecks por puerto +
   degradación a plantillas + cola persistente (SQLite/WAL) para que un
   reinicio no pierda mensajes de WhatsApp. *Aceptar* el SPOF está bien en
   esta etapa; perder mensajes, no.
2. **Falta una cola explícita.** El plan dice "encola y responde 200" pero no
   define EL componente. Veredicto: **SQLite como cola persistente** (una
   tabla, un worker por conversación). No Redis/RabbitMQ todavía — otra
   pieza de infraestructura que cuidar sin tráfico que la justifique.
3. **Falta el embedding model en el tier table** (ver §6).
4. **Componente innecesario detectado: ninguno.** El diseño ya es austero;
   el riesgo del plan no es exceso sino ejecutar las fases en orden.

---

## 2. Routing de modelos — ¿sobran o faltan?

Crítica a la alineación de 4 modelos:

- **E4B (router)**: imprescindible. Nada más barato clasifica con gramática.
- **26B-A4B (asistente)**: imprescindible. El MoE es la única forma de tener
  conocimiento de 26B a latencia interactiva en 8GB VRAM.
- **12B**: el más cuestionable. Mi crítica: su nicho (razonamiento medio) se
  solapa con ambos vecinos. La cláusula del amortiguador (retiro si 2 ciclos
  de eval no lo justifican) **ya es la respuesta correcta** — pero propongo
  endurecerla: *empieza SIN el 12B en producción* (router salta 0→2) y solo
  introdúcelo si la telemetría muestra que el 26B gasta >25% de su tiempo en
  tareas que el set 07 clasifica como "medias". Carga de la prueba invertida.
- **31B (juez)**: correcto SOLO como juez batch (ya codificado). No comprar
  hasta que el eval 10 falle con 26B-verificado.
- **FALTA: modelo de embeddings** (~0.5GB, p.ej. un embedder multilingüe
  pequeño) — no para vector store todavía, sino para el **semantic router**
  (abajo) y el reranker ligero del retrieval híbrido (§6).

**Estrategias de routing evaluadas:**

| Estrategia | Veredicto |
|---|---|
| Confidence routing | ✅ ya adoptado (v2) — calibrar con eval 01 |
| Budget/latency-aware | ✅ ya adoptado (`RequestBudget`) |
| **Semantic routing** | ✅ **ADOPTAR**: embeddings de intents conocidos + similitud coseno ANTES del E4B. Resuelve el 60-70% del tráfico repetitivo en <5ms sin tocar un LLM. El E4B pasa a ser el fallback del semantic router, no la primera línea |
| Uncertainty routing (entropía de logits) | ⚠️ diferir: llama.cpp expone logprobs, pero calibrar entropía es un proyecto; confidence declarada + evals basta ahora |
| Dynamic/quality-aware (bandits) | ❌ rechazar por ahora: optimizar online sin volumen es ruido. Revisitar con >10k conversaciones loggeadas |

**Veredicto §2: pipeline de routing final =
`cache semántico → E4B con gramática → escalación objetiva`. El 12B entra
solo con carga de la prueba invertida. Añadir embedder pequeño al inventario.**

---

## 3. Executive Controller

¿Debería existir un componente superior para routing/budgets/policy/telemetry/
escalation/retries/circuit-breakers?

**Sí — pero la pregunta correcta es QUÉ FORMA tiene.** Crítica a la versión
"servicio aparte": un controller-servicio duplica la red, añade un salto de
latencia y un segundo SPOF para gobernar... un solo host. Eso es teatro
enterprise.

**Forma correcta: un módulo `controller.py` con interfaz única** que ya casi
existe disperso en el plan (router + budget + policy + telemetría). Diseño:

```python
class ExecutiveController:
    """Única puerta de entrada/salida de cada request. Todo pasa por aquí."""
    def admit(self, msg) -> tuple[Route, RequestBudget]      # semantic cache → route → budget
    def execute(self, route, budget) -> Draft                # delega al loop; aplica retries/CB
    def release(self, draft) -> Final                        # policy gate → telemetría → respuesta
```

Responsabilidades QUE SÍ van aquí: circuit breaker por tier (3 fallos del
puerto 8093 → degradar a 8092 + plantillas, half-open a los 60s), retries
(SOLO de tools idempotentes, jamás del loop entero), presupuesto, telemetría.
Responsabilidades que NO: lógica de negocio, prompts, conocimiento del dominio.

**Riesgo a vigilar**: que el controller engorde hasta ser un god-object. La
defensa: sus tres métodos no crecen; crecen los módulos que orquesta.

**Veredicto §3: adoptar como módulo con la interfaz de 3 métodos. Es la
mejora estructural #1 de esta revisión — convierte invariantes dispersos en
un único punto auditable.**

---

## 4. Agent loop — ¿es óptimo el de 7 estaciones?

Alternativas evaluadas con honestidad:

| Patrón | Veredicto | Por qué |
|---|---|---|
| Loop actual (plan→tools→observe→reflect→critic→policy→final) | ✅ base correcta | mapea 1:1 al dominio: datos vivos + políticas duras |
| **Self-consistency (K muestras, voto)** | ✅ adoptar SOLO en `risk=high` con K=3 | coste 3× justificado únicamente donde un error cuesta dinero; en el resto es latencia tirada |
| Tree search (ToT/MCTS) | ❌ | brilla en puzzles con estado evaluable; "¿tienen coca?" no tiene árbol que explorar. Complejidad sin señal |
| Debate multi-modelo | ❌ | duplica coste para ganar en tareas de juicio abierto; tu verificador + policy gate ya cubren el caso de uso real |
| Multi-agente (crews) | ❌ | N agentes = N² superficies de fallo y prompts que mantener. Anthropic mismo: *the simplest loop that works*. Tu "multi-agente" real ya existe: son los TIERS con contrato |
| Actor-critic | ✅ ya lo tienes | generador (26B) + crítico (26B/31B) ES actor-critic; no necesita el nombre |
| Graph-based (LangGraph) | ⚠️ revisitar si... | el día que tengas >3 flujos con bifurcaciones profundas y necesites checkpointing de estado por nodo. Hoy el grafo es una línea con un ciclo — un `while` con presupuesto lo expresa mejor que un DAG framework |

**Veredicto §4: loop confirmado + self-consistency K=3 en high-stakes como
única adición. Todo lo demás es complejidad buscando un problema.**

---

## 5. Orquestación — la comparación que pediste (n8n incluido)

Primero la distinción que ordena todo el análisis. Hay TRES problemas
distintos que la gente llama "orquestación":

- **(A) Loop agéntico** (segundos, estado en memoria, LLM decide el camino)
- **(B) Workflows duraderos** (horas/días, estado persistente, retries
  exactos: pedidos, pagos, sagas)
- **(C) Integración/ETL/conectores** (webhooks, SaaS, transformaciones)

| Herramienta | Tipo | Madurez | Enterprise-ready | Fortaleza real | Por qué NO para (A) |
|---|---|---|---|---|---|
| **n8n** | C | alta | media (fair-code license, no OSS puro; self-host sí) | 400+ conectores, velocidad de integración brutal | un loop con reflect/critic/policy en nodos visuales es ilegible, indiffeable e intesteable; el estado del loop no es un workflow, es una conversación |
| **Temporal** | B | muy alta | **la referencia** (Uber/Netflix/Stripe-class) | durable execution: el workflow sobrevive crashes con replay determinista | determinismo exigido choca con LLMs no deterministas (se puede con activities, pero pagas un cluster + curva para un laptop) |
| **Camunda** | B | muy alta | alta (BPMN, banca/seguros) | procesos de negocio auditables BPMN | BPMN modela procesos humanos-aprobación, no loops de inferencia; peso Java/Zeebe absurdo aquí |
| **Airflow** | C(batch) | muy alta | alta en DATA eng | DAGs programados, backfills | es un scheduler de batch: latencia de segundos-minutos por tarea, anti-patrón total para chat |
| **Argo Workflows** | B/C en K8s | alta | alta (CNCF) | workflows nativos K8s, ya lo tocas en el template | mismo problema: pods por paso, no loops conversacionales |
| **LangGraph** | A | media-alta | media (LangChain Inc., LangSmith de pago) | grafos de estado con checkpointing para agentes | el MEJOR candidato externo para (A)… pero te acopla a su runtime/abstracciones, y tu loop actual cabe en ~200 líneas que entiendes al 100% |
| OpenAI Agents SDK / Google ADK | A | media/nueva | media | integración nativa con SU nube | gravitan hacia su proveedor; tu principio es local-first |
| CrewAI / AutoGen | A | media | baja-media | prototipado rápido multi-agente | rechazados con el multi-agente (§4); abstracciones gruesas, debugging opaco |
| Semantic Kernel | A | media | media-alta (ecosistema .NET/MS) | plugins/planners en C#/Python | fuera de tu stack; sin ventaja sobre tu loop |
| PydanticAI | A | nueva | media (equipo Pydantic, serio) | agentes tipados con TU misma filosofía de contratos | el más afín ideológicamente; aún joven — robar ideas sí, depender no |
| Haystack | RAG | alta | media-alta | pipelines de retrieval | es para (§6) no para el loop; y tu retrieval file-based aún no lo necesita |

**¿n8n vale la pena EN ALGÚN LUGAR? Sí — en su sitio.** n8n es excelente como
**capa de integración perimetral**: recibir el webhook de WhatsApp, conectar
un CRM/Sheets/Telegram en minutos, notificar a un humano cuando el agente
escala. Eso es (C), su terreno. Propuesta concreta: **track opcional
`integrations/n8n/`** en el template con un flujo exportado (webhook → POST al
gateway del agente → respuesta), documentado como adaptador — el cerebro
NUNCA vive en n8n. Para tu objetivo de aprendizaje/CV: saber n8n suma para
roles de automatización; presentarlo como orquestador de agentes resta ante
un entrevistador senior.

**¿Y la pregunta de fondo — motor propio en Python/FastAPI vs adoptar?**
**Motor propio, confirmado.** Argumentos no complacientes:

1. Tu núcleo diferencial ES el control (policy, budgets, contratos,
   auditoría). Delegarlo a un framework es regalar la tesis del template.
2. El loop completo son ~200-400 líneas con CERO magia. LangGraph te ahorra
   ~100 de ellas y te cuesta una dependencia con churn alto.
3. Aprenderás más (objetivo declarado) construyendo el motor y LEYENDO cómo
   LangGraph/PydanticAI resuelven checkpointing, que importándolos.
4. Cláusula de revisión honesta: si llegas a (a) >3 flujos con grafos
   profundos, o (b) necesidad real de durable-execution multi-día →
   reevaluar LangGraph (a) o Temporal (b) con un ADR. Triggers escritos,
   no dogma.

**Veredicto §5: motor propio. n8n = adaptador edge opcional. Temporal = ADR
futuro con trigger explícito. Resto: descartados con causa.**

---

## 6. Retrieval y memoria — arquitectura objetivo

La escalera vigente (file-based → BM25 → vector) es correcta; lo que faltaba
es el dibujo del estado FINAL para no improvisarlo después:

```
query → [0 semantic cache (embeddings, hits exactos)]
      → [1 alias/taxonomía (determinista, productos)]
      → [2 híbrido: BM25 + dense embeddings → RRF (reciprocal rank fusion)]
      → [3 reranker ligero (solo top-20 → top-3, cross-encoder pequeño)]
      → contexto compacto con citas obligatorias
```

- Taxonomía/ontología: el `categorias.json` jerárquico YA es tu ontología.
  No adoptar un triple-store; un JSON versionado en PR es más auditable.
- Memoria de cliente: resúmenes de conversación (generados por E4B, 1 párrafo,
  PII-redactados) + preferencias estables. JAMÁS stock/precios (línea sagrada).
- Vector DB: cuando el gate recall@5<80% dispare — **sqlite-vec o LanceDB**
  (embebidos, cero servicios nuevos), NO un Pinecone/Weaviate gestionado.
- El reranker y los embeddings reutilizan el embedder de §2.

**Veredicto §6: adoptar el dibujo objetivo; implementar por gates como ya
está pactado. Híbrido BM25+dense con RRF es el estándar de la industria
(Elastic/Anthropic contextual retrieval) y tu camino natural.**

---

## 7. Policy Engine — diseño enterprise

Lo existente (checks deterministas + verificador) es la base correcta. Para
nivel enterprise faltan tres piezas, todas baratas:

1. **Políticas como datos, no como código**: mover umbrales y reglas a
   `policies/*.yaml` versionado (qué tools puede llamar cada intent, montos
   máximos, compromisos prohibidos, tonos por canal). El runtime las carga;
   un PR las cambia; el diff ES el audit trail de compliance.
2. **Decisiones con ID**: cada veredicto del gate emite
   `{policy_version, rules_fired, decision_id}` en la telemetría — trazable
   de la respuesta del cliente a la regla exacta que la permitió.
3. **Two-person rule para mutaciones nuevas**: una tool de escritura nueva
   entra con `dry_run` forzado hasta que (a) su eval pasa y (b) un humano
   firma el PR que la arma. Es AUTO/CONSULT/STOP aplicado a tools.

❌ Rechazado: OPA/Cedar/motores de policy externos — otra runtime para
evaluar lo que 30 líneas de Python + YAML expresan mejor a esta escala.
Trigger de reevaluación: multi-tenant con políticas por cliente.

---

## 8. Evaluaciones — el sistema continuo

El plan v2 ya tiene los 10 sets + gates por tier + shadow. Lo que esta
revisión añade:

- **Golden set congelado** (50 casos, NUNCA crece ni se edita) separado del
  set vivo: mide deriva del sistema a largo plazo; el set vivo mide cobertura.
- **Replay como primera clase**: la telemetría JSONL debe poder re-ejecutarse
  (`evals/replay.py --from logs/2026-06-12.jsonl --against new-prompt`) —
  cada cambio de prompt se prueba contra tráfico real de ayer antes de ver
  tráfico de hoy.
- **Eval del router como matriz de confusión publicada** por ciclo, no solo
  accuracy: las escalaciones de más cuestan latencia; las de menos, calidad.
- Online: el shadow del 10% ya pactado + tasa de "lo confirmo y te escribo"
  (proxy de policy-blocks) como métrica de producto.

---

## 9. Observabilidad — completar el dibujo

Sobre la telemetría v2 existente, dos adiciones y un rechazo:

- ✅ **Trace ID por conversación** propagado a tools y tiers (un campo, no
  una plataforma). Cuando haya dolor real de correlación: OpenTelemetry
  exportando a... los MISMOS Prometheus/Grafana del template. Cero
  herramientas nuevas.
- ✅ **Coste por request** como métrica derivada (tokens×tier + segundos de
  GPU): el FinOps del módulo 21 aplicado a agentes.
- ❌ LangSmith/LangFuse/W&B-LLM: paneles bonitos, lock-in temprano. Tu JSONL
  + Grafana cubre el 90%; revisitar con equipo >1.

---

## 10. Evolución futura (fine-tuning y más allá)

Confirmo el gate vigente (Fase 4: >10k eventos etiquetados + patrón estable
que el prompting no resuelve) y ordeno la escalera con triggers:

```
HOY: prompts + retrieval + evals
 └─ trigger >10k ejemplos + gap de estilo persistente
     → QLoRA sobre E4B/12B (tono, formato, protocolo de marca) — NUNCA hechos
 └─ trigger: pares preferencia abundantes de los veredictos del juez
     → DPO/preference optimization (los rechazos del critic SON el dataset)
 └─ RLHF/RLAIF clásico: ❌ horizonte visible — coste/infra sin caso de negocio
 └─ Continual learning: vía retrieval (la memoria aprende), no vía pesos
```

La generación sintética ya pactada (variantes regionales revisadas) es el
único "data flywheel" que necesitas este año.

---

## Cambios accionables que esta revisión introduce al plan

| # | Cambio | Fase |
|---|---|---|
| R1 | Semantic cache/router con embedder pequeño delante del E4B | F1.5+ |
| R2 | `ExecutiveController` como módulo de 3 métodos + circuit breakers | F2 |
| R3 | Cola persistente SQLite (un worker por conversación) | F1.6 |
| R4 | 12B fuera del arranque; entra con carga de la prueba invertida | F2.1 |
| R5 | Self-consistency K=3 solo en `risk=high` | F2.3 |
| R6 | `policies/*.yaml` + decision_id en telemetría | F2.2 |
| R7 | Golden set congelado + `evals/replay.py` | F2.5 |
| R8 | Track opcional `integrations/n8n/` como adaptador edge documentado | P3 |
| R9 | Trace ID + coste/request en telemetría | F3 |
| R10 | ADR-trigger escrito para Temporal (durable, multi-tenant) y LangGraph (>3 grafos profundos) | P3 |

---

# ADDENDUM v3 — Revisión adversarial de R1–R10 (2026-06-12)

> Mandato del maintainer: someter las propias propuestas R1–R10 al mismo
> escrutinio que el resto, sin optimizar por acuerdo, proponiendo quintas
> alternativas donde existan. Resultado honesto: **3 propuestas se revisan
> a la baja, 1 se difiere con trigger, 6 sobreviven con refinamientos.**
> Formato por ítem: ataque → veredicto → complejidad/impacto → prioridad.

## A-R1. Modelo de tres capas (A/B/C) — REVISADO A LA BAJA

**Ataque**: ¿la capa B (workflows duraderos) existe HOY en este sistema?
Solo hay UN caso latente (pedido → confirmación → seguimiento, días). Crear
una "capa" arquitectónica para un caso es taxonomía sin sustancia — el mismo
teatro que criticamos en los microservicios.

**Quinta alternativa (adoptada)**: **dos capas + un patrón**. A (loop) y C
(integración) son capas reales con código propio. B no es una capa: es el
patrón *durable-state-as-data* — una tabla `sagas` en la MISMA SQLite de la
cola (estado, paso, deadline, retries) + un sweep periódico del worker. Cero
runtimes nuevos; Temporal sigue siendo el ADR-trigger si las sagas pasan de
~3 tipos o exigen exactly-once distribuido.
**Complejidad**: baja (1 tabla + 1 función). **Prioridad: AHORA** (F1.6).

## A-R2. Posicionamiento de n8n — ENDURECIDO EN CONTRA

**Ataque a mi propia propuesta del track `integrations/n8n/`**: para UN solo
canal (WhatsApp), un flujo n8n es un contenedor más que operar, una superficie
de auth más, JSON exportado in-diffeable, y una licencia fair-code en un
template que presume de supply-chain limpio. El webhook FastAPI son 40 líneas
testeables.

**Veredicto revisado**: el core queda code-first (confirmado); el track n8n
**se difiere con trigger**: se crea solo cuando existan ≥2 integraciones SaaS
reales (CRM + algo). Hasta entonces, n8n vive solo como párrafo de
posicionamiento en docs. ¿Alguna alternativa como runtime primario? Re-evaluadas
Temporal/Camunda/LangGraph contra el criterio 5-10 años: ninguna desplaza al
runtime propio — el argumento decisivo es que el diferencial del template ES
el control (policy/budgets/auditoría) y eso no se delega.
**Prioridad: DIFERIDO** (trigger escrito en P3).

## A-R3. ExecutiveController — SOBREVIVE con forma refinada

**Ataque**: riesgo god-object real; además un objeto con 6 sub-módulos
acumula estado mutable compartido.

**Refinamiento adoptado**: la fachada de 3 métodos se queda, pero el interior
es un **pipeline de middlewares puros** (`admit = compose(normalize, cache,
route, budget)`) — cada middleware una función `(ctx) -> ctx` testeable
aislada. Tope duro: ~250 LOC el módulo completo; si crece, se parte. Circuit
breaker: estado EN MEMORIA (re-aprende en segundos tras restart; persistirlo
sería complejidad sin beneficio).
**Complejidad**: media-baja. **Prioridad: AHORA** (F2.0).

## A-R4. Semantic router pre-E4B — RECHAZADO COMO PROPUESTO (mi error)

**Ataque (fatal)**: con CERO tráfico no hay "tráfico repetido" que cachear —
es optimización prematura de manual. Peor: en un bot COMERCIAL, un falso
positivo del cache semántico responde sobre el producto equivocado (riesgo de
negocio, no solo de latencia). Y añade un modelo más que operar el día 1.

**Veredicto revisado**: la cadena determinista (normalizer → alias →
taxonomía → BM25) SÍ va el día 1 — cero modelos nuevos, ya estaba en el plan.
El **embedder + cache semántico se difiere con trigger medible**: cuando la
telemetría muestre ≥30% de queries near-duplicadas que la capa de alias no
resolvió (medible OFFLINE sobre los logs, sin servir embeddings). Y cuando
entre: **se cachea la RUTA, jamás la respuesta** — toda respuesta pasa por
tools en vivo + policy gate siempre.
**Prioridad: DIFERIDO con trigger** (F3, análisis offline semanal).

## A-R5. Responsabilidades de modelos — CONFIRMADO con dos matices

**Matiz 1 (a favor del 12B que yo descarté rápido)**: con 36GB, 12B (6.5G) y
26B (14G) SÍ co-residen — el argumento "un modelo grande a la vez" no aplica
entre ellos. Aun así gana la simplicidad operativa: **arranque sin 12B**
confirmado; su entrada es barata cuando la telemetría la justifique (el
artefacto queda en disco).
**Matiz 2 (juez)**: para lanes de mantenimiento SIN PII (docs-drift, evals del
template), un juez cloud cheap-tier puede superar al 31B local en calidad y
latencia — permitido. Para high-stakes de CLIENTES, el juez es local por la
línea de privacidad: el 31B se sostiene.
**Prioridad: AHORA** (regla de arranque) / juez-cloud anotado en lanes.

## A-R6. Loop / reflexión — REFINADO (reflect condicional)

**Ataque**: `reflect` incondicional añade un pase de modelo (1–3s) a intents
tool-light donde no aporta — presupuesto de latencia tirado en el caso común.

**Refinamiento adoptado — profundidad adaptativa**: `reflect` corre SOLO si
(a) una tool falló/contradijo el plan, o (b) `risk≥medium`. Smalltalk y
lookups limpios van plan→tools→policy→final.
**Self-consistency K=3**: mi propia propuesta no sobrevive al presupuesto —
3 pases del 26B revientan los 8s de WhatsApp. Revisado: K=3 SOLO en flujos
high-stakes ASÍNCRONOS (confirmaciones de pedido donde 15-20s son aceptables)
y en evals nocturnos; el high-stakes interactivo usa pase único + juez.
**Prioridad: AHORA** (es un `if`, no un sistema).

## A-R7. Budget engine — CONFIRMADO estático, adaptativo RECHAZADO por ahora

**Ataque al "adaptativo"**: budgets que se auto-ajustan son un feedback loop
más que debuggear, sin datos para fundarlo. **Veredicto**: budgets ESTÁTICOS
por intent en `budgets.yaml` (versionado, diffeable) + un **cap diario de
cloud** (contador simple). Adaptatividad: revisar con P95 reales de ≥4
semanas. Se añade `max_reflections: 1` al RequestBudget (cierra A-R6).
**Prioridad: AHORA.**

## A-R8. Policy YAML — SOBREVIVE con una exigencia extra

Alternativas re-evaluadas (Rego/OPA, CUE, DSL Python): YAML+Pydantic gana en
auditabilidad por no-ingenieros y en cero-runtimes. **Exigencia añadida**:
cada cambio de `policies/*.yaml` DEBE llegar con su caso en el set 06 que
falle sin el cambio (policy-change-requires-test). Las políticas-como-datos
sin tests son configuración mágica.
**Prioridad: AHORA** (F2.2).

## A-R9. Telemetría — ELEVADA a obligatoria; OTel diferido bien diferido

**Veredicto**: la telemetría pasa de "buena práctica" a **contrato del
template**: un lane sin emisión del schema de eventos NO pasa el validator
(es el equivalente agéntico del prediction logger D-20). OTel: se difiere,
PERO los nombres de campos se alinean desde hoy a semconv de OTel
(`trace_id`, `span`…) para que la migración futura sea un swap de transporte,
no un rename masivo.
**Prioridad: AHORA** (naming) / OTel con trigger (equipo >1 o >1 host).

## A-R10. Pipeline de aprendizaje continuo — CONFIRMADO con gobernanza dura

**Ataque**: capturar correcciones de usuarios directo a datasets = riesgo de
privacidad Y de envenenamiento (un usuario malicioso "enseña" al bot).
**Gobernanza adoptada (innegociable)**: (1) redacción de PII en el momento de
ESCRITURA del log, no después; (2) **cuarentena**: nada entra a un dataset sin
revisión humana por lotes; (3) procedencia por registro (`source`, `reviewer`,
`policy_version`); (4) retención: crudo 30 días, curado indefinido; (5) los
veredictos del juez generan pares para DPO — ese es el flywheel legítimo.
**Prioridad: el SCHEMA ahora** (campos en telemetría), el pipeline en F4.

## Arquitectura integrada resultante (v3)

```
WhatsApp/canales ──► webhook FastAPI (code-first; n8n = trigger-diferido)
        │
        ▼
  cola SQLite (worker/conversación) + tabla sagas (durable-state-as-data)
        │
        ▼
ExecutiveController (fachada 3 métodos; middlewares puros; CB en memoria)
  admit:  normalize → alias/taxonomía/BM25 → E4B(gramática+confidence)
          → budget(budgets.yaml + cap cloud diario)
  execute: loop adaptativo [plan → tools → observe → (reflect?) → critic]
           tiers: E4B / 26B (12B y cache semántico: triggers escritos)
  release: policy gate (policies/*.yaml + decision_id + test obligatorio)
           → telemetría OBLIGATORIA (naming OTel-compatible, PII-redactada,
             campos de procedencia para el flywheel DPO) → finalize
        │
        ▼ (sin SLA / sin PII)
   31B juez local · juez cloud SOLO lanes de mantenimiento · evals nocturnos
```

| Ítem | Estado v3 | Cuándo |
|---|---|---|
| Dos capas + durable-state-as-data (tabla sagas) | adoptado | F1.6 |
| n8n track | diferido (≥2 integraciones SaaS) | trigger P3 |
| Controller fachada+middlewares, ≤250 LOC | adoptado | F2.0 |
| Cadena determinista pre-router | adoptado (ya estaba) | F1.5 |
| Embedder + cache semántico | **diferido** (≥30% near-dups en logs; cachea RUTA) | trigger F3 |
| Arranque sin 12B / juez-cloud solo sin-PII | adoptado | F0/F2 |
| Reflect condicional + K=3 solo async/evals | adoptado | F1.6/F2.3 |
| budgets.yaml estático + cap cloud + max_reflections | adoptado | F1.6 |
| policies.yaml + decision_id + policy-change-requires-test | adoptado | F2.2 |
| Telemetría obligatoria, naming OTel-compatible | adoptado | F1–F3 |
| Gobernanza del flywheel (cuarentena/procedencia/retención) | schema ahora, pipeline F4 | F3/F4 |
