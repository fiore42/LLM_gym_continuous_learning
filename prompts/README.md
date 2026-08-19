# Prompt registry

[Project rules](../PROJECT_RULES.md)

Prompt definitions are immutable JSON records grouped by task family. Each
family has its own directory because `load_prompt()` selects the record with
the highest `version_number` in that directory when no explicit version is
requested. A new prompt is added as a new JSON file; an existing prompt file is
not edited. Results record the prompt ID, version, SHA-256, full system prompt,
and fully rendered user prompt used for that model call.

| Folder | Purpose | Current default | Primary entry point |
|---|---|---|---|
| [`agent_task/`](agent_task/) | Produce evidence-scoped answers, evidence assessments, citations, and optional retrieval queries | `synthesis-v7` | `scripts/agent_run_task_on_checkpoint.py` |
| [`digest/`](digest/) | Assess one corpus item, select exact supporting passages, and assign a digest significance label | `significance-v2` | `scripts/agent_run_digest.py` |
| [`verification/`](verification/) | Draft advisory answer-to-evidence verification rows for human confirmation | `verification-v1` | `scripts/eval_draft_claim_verification_sheet.py` |

The folder READMEs describe every version and all script entry points that load
the family directly or through the runtime layer.
