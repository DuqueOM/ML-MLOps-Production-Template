# ADR-028 Implementation Plan — LLM-Assist on Local Hardware

- **Date**: 2026-06-10
- **Author**: Claude Code (R6 follow-up) — pending maintainer acceptance
- **Implements**: `docs/decisions/ADR-028-llm-assist-integration.md` (Proposed)
- **Hardware target**: laptop — i7-14650HX, 16 GB RAM, RTX 5070 Laptop 8 GB VRAM,
  WSL2 Ubuntu-24.04
- **Models available locally** (`~/projects/LLMS/`): full Gemma-4 catalog —
  e2b / e4b / 12b / 26b-a4b (MoE) / 31b, each in `-it`, `-it-assistant` and
  `-it-qat-q4_0-unquantized` variants. See §0.4 for the selection rationale.

---

## 0. Hardware reality check (read this before anything else)

> **2026-06-10 update**: plan adjusted for the approved RAM upgrade
> (+32 GB module → **48 GB total**). The original 16 GB analysis is kept
> below for reference because Phase 0 may start before the module arrives.

### 0.1 With 48 GB RAM (target state)

RAM stops being the binding constraint; the 8 GB VRAM now only bounds
*speed*, not *feasibility*.

| Model / quant | Weights | Fits where | Expected speed | Verdict |
|---|---|---|---|---|
| e4b QAT @ Q4_0 | ~3–4 GB | Fully in 8 GB VRAM | 35–50 tok/s | ✅ `local-fast`, always-on |
| 12b QAT @ Q4_0 | ~7 GB | ~90% of layers in VRAM | 20–30 tok/s | ✅ `local-deep` **candidate A** |
| 26b-a4b QAT @ Q4_0 | ~14–15 GB | Attention+shared on GPU, experts in RAM | 10–18 tok/s | ✅ `local-deep` **candidate B** |
| 31b QAT @ Q4_0 | ~17–18 GB | ~⅓ layers in VRAM, rest CPU (**dense** — every token pays full cost) | 3–5 tok/s | ❌ as lane worker; optional offline eval-oracle only |
| e2b QAT @ Q4_0 | ~2 GB | VRAM, trivially | 60+ tok/s | spare — only if e4b proves too slow in bulk |

What the upgrade changes concretely:

1. **`local-deep` jumps from Q3 to Q4/Q5** — meaningful quality gain for the
   RCA-draft lane (Q3 MoE quants degrade noticeably; Q4_K_M is near-lossless).
2. **Both servers can run simultaneously** (e4b in VRAM at port 8081,
   26b-a4b in RAM at port 8082) — no more on-demand swapping; the routing
   client picks a tier per request instead of per session.
3. **KV cache headroom** — 16k–32k context on `local-deep` becomes practical,
   which matters for Lane 3 (joined evidence bundles are long).
4. **Phase 0 exit criteria rise accordingly**: local-deep gate moves from
   ≥ 6 tok/s @ 8k ctx to **≥ 8 tok/s @ 16k ctx, Q4_K_M**.
5. What does NOT change: the 8 GB VRAM still rules out dense >8B models at
   useful speed, Lane 1 stays cloud-only (security rationale, not hardware),
   and the fine-tuning rejection stands — ADR-028 §4's trigger is labeled
   volume, not RAM.

Hardware notes for the purchase: confirm the laptop pairs the new 32 GB
SODIMM with the existing 16 GB in flex/dual-channel mode (DDR5-5600 to match);
asymmetric pairing costs a few % bandwidth — irrelevant for MoE expert
streaming, which is latency-bound, not bandwidth-bound at these sizes.

`.wslconfig` after the upgrade:

```ini
[wsl2]
memory=36GB        # leave ~12GB for Windows; both model servers fit resident
swap=8GB           # safety net only — should never be touched in steady state
```

### 0.2 With 16 GB RAM (interim, until the module arrives)

| Model / quant | Weights on disk | Fits where | Expected speed | Verdict |
|---|---|---|---|---|
| e4b @ Q4_K_M | ~4–5 GB | **Fully in 8 GB VRAM** | 35–50 tok/s | ✅ default worker |
| e4b @ Q8 | ~8 GB | VRAM + small CPU spill | 20–30 tok/s | ✅ when quality matters |
| 26b-a4b @ IQ3_M/Q3_K_M | ~11–12 GB | Attention+shared on GPU, experts on CPU RAM | 8–15 tok/s | ⚠️ feasible, tight |
| 26b-a4b @ Q4_K_M | ~15 GB | Does NOT fit (OS+WSL need 5–6 GB) | swap thrashing | ❌ until upgrade |

Interim `.wslconfig`: `memory=11GB`, `swap=16GB`.

Practical sequencing: Phase 0 conversion + e4b benchmarking can start on
16 GB today (quantize the 26b to BOTH Q3 and Q4 in the same session — it is
a one-time CPU job); the Q4 26b benchmark waits for the module.

### 0.3 Strategy (unchanged by the upgrade)

Two local tiers + cloud:

- `local-fast` = e4b QAT Q4_0 — classification, extraction, doc-diff summaries,
  PR descriptions. Everything high-volume.
- `local-deep` = winner of the 12b-vs-26b-a4b bake-off (§0.4) — low-frequency,
  latency-tolerant jobs (draft RCA reports).
- `cloud` (existing routing tiers) — anything CONSULT-gated that produces
  code patches (Lane 1) or where evals show the local tiers hallucinate.

This maps cleanly onto the existing four-tier `model_routing_policy.yaml`:
local tiers slot UNDER the cheapest cloud tier; escalation-only discipline
(ADR-010) is unchanged — a local model can flag, never approve.

### 0.4 Checkpoint selection from the full Gemma-4 catalog

Three rules drive the picks:

1. **Always convert from the `-it-qat-q4_0-unquantized` checkpoints.** These
   weights were quantization-aware-trained for Q4_0: quantizing them to Q4_0
   GGUF is near-lossless, while quantizing the plain `-it` weights post-hoc
   costs measurable quality at the same size. Since every local tier serves
   at Q4, QAT checkpoints strictly dominate. (The plain `-it` tars already
   downloaded remain useful only if a converter rejects the QAT variant.)
2. **Skip `-assistant` variants and base (non-`-it`) models.** The lanes
   consume grammar-constrained JSON, not chat personality; plain `-it`
   instruction-following is the right tuning target. Base models would need
   few-shot scaffolding for no benefit.
3. **Dense vs MoE is an empirical question at this VRAM size — benchmark,
   don't guess.** The `local-deep` slot has two credible candidates:
   - **12b dense QAT** — ~90% VRAM-resident → faster (20–30 tok/s), and
     dense-12B quality is competitive with a 4B-active MoE on reasoning.
   - **26b-a4b MoE QAT** — RAM-resident experts → slower (10–18 tok/s) but
     26B total parameters carry more world knowledge.
   Phase 0 gains a **bake-off step**: run both against 5 representative
   Lane-3 tasks (RCA drafting from evidence bundles) + the Lane-2 eval set;
   score faithfulness-to-evidence and JSON-schema compliance; the winner
   becomes `local-deep`, the loser is deleted from disk.
4. **31b dense is rejected as a lane worker** — at 8 GB VRAM two-thirds of a
   *dense* model runs on CPU and every token pays the full 31B cost
   (~3–5 tok/s). Optional niche: offline **eval-oracle** that grades lane
   outputs overnight in batch, where 4 tok/s is irrelevant. Do not build
   this before the evals themselves exist.

---

## 1. Phase 0 — Local runtime + benchmark gate (week 1)

Goal: an OpenAI-compatible endpoint on `localhost:8081` (per the enterprise
port convention, 8080–8089 block) serving both tiers, with measured numbers.

1. **Extract + inspect**: untar both models, read `config.json`
   (architecture id, expert count). This decides converter support.
2. **Build llama.cpp with CUDA** in WSL (RTX 5070 = Blackwell, needs CUDA
   12.8+; build with `-DGGML_CUDA=ON`).
3. **Convert + quantize**:
   `convert_hf_to_gguf.py` → `llama-quantize` → e4b Q4_K_M, 26b-a4b IQ3_M.
   - Fallback if the Gemma-4 arch is too new for llama.cpp: serve via HF
     `transformers` + bitsandbytes 4-bit (e4b only — 26b won't fit that path),
     or check Ollama's registry for an official conversion.
4. **Serve** (two configs, one active at a time — RAM does not allow both):
   ```bash
   # local-fast (default, always-on)
   llama-server -m gemma4-e4b-Q4_K_M.gguf --n-gpu-layers 99 --port 8081
   # local-deep (on-demand, batch jobs only)
   llama-server -m gemma4-26b-a4b-IQ3_M.gguf --n-gpu-layers 99 \
     --override-tensor "exps=CPU" --port 8081
   ```
   `--override-tensor "exps=CPU"` is the MoE trick: shared weights +
   attention on GPU, expert FFNs in CPU RAM — active-4B compute keeps it usable.
5. **Benchmark gate** — `scripts/llm/bench.py`: tok/s, time-to-first-token,
   max usable context, VRAM/RAM occupancy. **Exit criterion**: local-fast
   ≥ 25 tok/s and local-deep ≥ 6 tok/s at 8k context. If local-deep fails
   the gate, drop it and route deep tasks to cloud — do not fight the hardware.

Deliverables: `scripts/llm/serve-fast.sh`, `scripts/llm/serve-deep.sh`,
`scripts/llm/bench.py`, benchmark results recorded in this file.

## 2. Phase 1 — Routing policy + client + eval harness skeleton (weeks 1–2)

1. **`model_routing_policy.yaml`**: add `local-fast` / `local-deep` tiers
   with `verified_at` dates and the benchmark numbers as capability notes.
2. **`scripts/llm/client.py`**: thin wrapper over the OpenAI client pointed
   at `localhost:8081`, with one non-negotiable feature: **grammar-constrained
   JSON output** (llama.cpp GBNF / `response_format json_schema`). Small
   models are unreliable free-form but solid when the decoder is constrained
   to a schema. Every lane consumes schema-validated JSON, never prose.
3. **Eval harness skeleton** (ADR-028 §3 precondition): `evals/` directory,
   pytest-based runner, scenarios converted from `docs/agentic/red-team-log.md`.
   Rule: **no lane graduates CONSULT→AUTO without a regression eval.**

## 3. Phase 2 — Lane 4 first: docs-drift updater (weeks 2–3)

First productive lane, chosen deliberately: cheapest, read-only, mechanically
verifiable, and the R6 audit found four real instances of this drift class.

Design — the LLM is the *writer*, not the *detector*:

1. Deterministic Python extractor collects code-visible facts (rule/skill/
   workflow counts, overlay names, inventory tables) — no LLM involved.
2. Comparator flags doc claims that mismatch the facts.
3. `local-fast` writes the human-readable PR body + proposed doc diffs for
   flagged mismatches only, JSON-constrained.
4. Opens a **CONSULT PR** via `gh`. Human merges.

Runtime: **the laptop is the runner** — WSL systemd timer (weekly), zero CI
dependency, zero cloud cost. This sidesteps the obvious problem that
GitHub-hosted runners cannot reach a local model.

Eval before enabling: seed 10 synthetic drift cases (mutate a count, rename
an overlay), require ≥ 9/10 caught with 0 false patches.

## 4. Phase 3 — Lane 2: memory plane Phase 2 (weeks 3–4)

Per ADR-018/ADR-028: **embeddings-free first**.

1. BM25 (`rank_bm25`) over existing artifacts: `ops/audit.jsonl`,
   `docs/incidents/`, `VALIDATION_LOG.md`, `releases/*.md`, drift reports.
2. `scripts/memory_query.py "<question>"` → top-k chunks → `local-fast`
   summarizes **with file:line citations** (citations are mandatory — an
   answer without a citation is discarded).
3. Eval: 20 historical questions with known answers (from past audits);
   measure recall@5. Only if BM25 recall < 80% do we revisit a vector store.

## 5. Phase 4 — Lane 3: drift/incident triage summarizer (weeks 5–6)

1. Joiner script gathers: Prometheus signals (`prometheus` MCP),
   prediction-log slices, deploy history (`git log` + image digests).
2. `local-deep` (26b-a4b) drafts the RCA in `report_schema.json` shape —
   batch job, minutes-long runtime is acceptable, so the slow tier fits.
3. Draft attaches to the incident issue. **Human owns the conclusion.**
4. Eval: replay 3 historical incidents; the draft must not assert causal
   claims absent from the evidence (hallucinated causality = automatic fail
   → that subtask routes to cloud).

## 6. Phase 5 — Lane 1: CI self-healing Phase 2 (week 7+, gated)

- **Schedule the ADR-019 14-day shadow window NOW** — the ADR flags that an
  unscheduled gate is indefinite by default.
- **Local models are explicitly OUT of this lane's CI path.** Two reasons:
  1. GitHub-hosted runners cannot reach the laptop.
  2. A self-hosted runner on a personal laptop attached to a public repo is
     a known attack vector (fork PRs execute on your machine) — rejected.
- Classification in CI: heuristic-first, cloud cheap-tier where needed.
  Patch generation: cloud, CONSULT, per existing routing policy.
- Local tiers still help here *offline*: nightly local job replays the day's
  CI failures against the classifier prompt to grow the labeled corpus —
  feeding the §4 fine-tuning revisit triggers (>10k labeled events).

## 7. Risks

| Risk | Mitigation |
|---|---|
| 16 GB RAM ceiling | `.wslconfig` 11 GB + NVMe swap; local-deep is on-demand only, never resident |
| Q3 quant degrades 26b-a4b below usefulness | Phase 0 benchmark gate + per-task side-by-side vs e4b-Q4; drop the tier if it loses |
| Gemma-4 arch unsupported by converters | Fallback chain: Ollama registry → transformers+bnb (e4b only) → cloud-only plan still works, lanes are model-agnostic via the OpenAI-compatible client |
| Laptop-as-runner availability | Lanes 2–4 are weekly/on-demand, not latency-sensitive; a missed week is benign |
| Small-model hallucination | Grammar-constrained JSON everywhere; citations mandatory; deterministic detectors upstream of every LLM call |

## 8. Sequence summary

```
Week 1    Phase 0: runtime + benchmark gate          [hard gate]
Weeks 1–2 Phase 1: routing tiers + client + evals    [precondition]
Weeks 2–3 Phase 2: Lane 4 docs-drift  → first CONSULT PRs
Weeks 3–4 Phase 3: Lane 2 memory retrieval
Weeks 5–6 Phase 4: Lane 3 triage summarizer
Week 7+   Phase 5: Lane 1 (cloud-only, shadow-window gated)
```

Fine-tuning remains **rejected** per ADR-028 §4 — nothing about local
hardware changes that calculus; if anything, 8 GB VRAM makes even QLoRA on
the 26B impractical (e4b QLoRA is possible but the volume trigger still
isn't met).
