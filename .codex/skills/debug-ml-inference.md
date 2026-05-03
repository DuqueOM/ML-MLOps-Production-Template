# debug-ml-inference (Codex pointer)

**Canonical**: `.windsurf/skills/debug-ml-inference/SKILL.md`
**Authority**: `AGENTS.md#Agent Behavior Protocol`
**Manifest entry**: `agentic_manifest.yaml#skills[id=debug-ml-inference]`

## When to invoke from Codex

- Latency spike alert in Grafana / Alertmanager.
- Wrong predictions reported by a downstream consumer.
- Event-loop blocking suspected (high p99 with low CPU).
- "Why is the inference path slow on staging?" type questions.

## Mode

- AUTO. Read-only diagnostic walking the inference path: app code,
  HPA + pod limits, recent Prometheus metrics, recent traces if
  available.

## Codex-specific notes

- Required MCPs: `kubectl` (read-only `get/describe/logs`),
  `prometheus` (query latency histograms, error rates, throughput).
  Both must be `--read-only` in the Codex MCP config; the skill
  never asks for write access.
- Invariants the skill watches: D-01 (uvicorn workers), D-03
  (`run_in_executor`), D-23 (`/ready` gating), D-25 (model warm-up
  in lifespan). The full inspection sequence is in the canonical
  SKILL.md — this pointer does not duplicate it.
