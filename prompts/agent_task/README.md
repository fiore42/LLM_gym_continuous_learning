# Agent-task synthesis prompts

[Project rules](../../PROJECT_RULES.md)

This family turns one question and a bounded set of supplied evidence into a
JSON answer. The response includes an evidence-scoped classification,
citations, and one assessment for every supplied evidence item. Newer versions
can also propose retrieval queries; deterministic code decides whether to run
those queries and when to stop.

## Versions

| Version | What it does |
|---|---|
| `synthesis-v4` | Establishes the evidence-scoped answer, classification, citation, and per-item assessment contract. |
| `synthesis-v5` | Defines relevance as usable support rather than topical similarity, preserves source hedging, and omits unsupported material. |
| `synthesis-v6` | Adds `suggested_queries` when an insufficient-evidence result could benefit from another retrieval attempt. |
| `synthesis-v7` | Current default. Also permits targeted query suggestions when evidence is thin or only partly answers the question, including a supported but incomplete answer. |

## Scripts that use this family

| Script | How it uses the prompt |
|---|---|
| `scripts/agent_run_task_on_checkpoint.py` | Runs the bounded answer task over a frozen retrieval checkpoint. It uses the current default (`synthesis-v7`). |
| `scripts/eval_run_suite.py` | Runs frozen evaluation cases through the same answer task. `--prompt-version` selects a historical or current version explicitly; omission selects the latest version. |
| `scripts/agent_run_retrieval_retry.py` | Uses the current default for each synthesis round. Suggested queries can cause one bounded evidence expansion before redrafting. |
| `scripts/agent_measure_retrieval_trigger.py` | Repeats `agent_run_retrieval_retry.py`, so it uses the current default while measuring why retrieval expansion fired. |
| `scripts/eval_compare_model_providers.py` | Calls the shared bounded answer runner for each provider and therefore uses the current default. |
| `run_prompt_comparison.sh` | Calls `eval_run_suite.py --prompt-version ...` for two explicitly named historical prompt arms, then compares their reports. |

The loader path is `llm_gym/agent/prompt_registry.py` →
`llm_gym/agent/synthesis.py` → `llm_gym/agent/agent_runner.py`. The runtime
stores the complete rendered prompt in every synthesis attempt, not only the
version name.
