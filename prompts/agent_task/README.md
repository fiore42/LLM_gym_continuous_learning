# Agent-task synthesis prompts

[Project rules](../../PROJECT_RULES.md)

## What this prompt is for

A person asks a research question. The retrieval code finds a small set of
possibly useful excerpts from the local corpus. This prompt tells the model to
answer the question using only those excerpts—not its memory or outside
knowledge.

The model must:

- write an answer supported by the supplied material;
- cite the evidence records it used;
- say whether the evidence supports an answer, is insufficient, or conflicts;
- explain which supplied records were actually useful;
- suggest a more focused search when important evidence is still missing.

In plain language, this is the prompt that turns search results into a cited
research answer while making uncertainty visible.

## How it fits into the project

This prompt runs after evidence retrieval. In the ordinary question-answering
workflow, `agent_retrieve_evidence_for_question.py` creates a checkpoint and
`agent_run_task_on_checkpoint.py` uses this prompt to write the answer.

It is also used by the adaptive retrieval loop. If the first evidence set is
thin, the model can suggest a better query. Ordinary code decides whether that
query is allowed, retrieves more evidence, and gives the expanded evidence set
back to the same prompt for a second answer. The model proposes the search;
deterministic code executes and bounds it.

The JSON response includes the answer, its evidence-scoped classification,
citations, an assessment of every supplied evidence item, and any suggested
queries. The evaluation suite uses the same prompt with frozen evidence so
prompt behavior can be compared without retrieval changing underneath it.

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
