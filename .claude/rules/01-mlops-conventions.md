# 01-mlops-conventions

**Adapter surface**: `claude`
**Authority**: `AGENTS.md` + `templates/config/agentic_manifest.yaml`
**Canonical source**: `.windsurf/rules/01-mlops-conventions.md`

Read the canonical source in full before acting. This file is a thin
adapter pointer and must not duplicate policy text.

To change this rule, edit `.windsurf/rules/01-mlops-conventions.md`, update the manifest when needed,
then run:

```bash
python3 scripts/sync_agentic_adapters.py
python3 scripts/validate_agentic_manifest.py --strict
```
