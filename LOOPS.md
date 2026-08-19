# Loop Architecture

[Project rules](PROJECT_RULES.md)
[Project contracts](CONTRACTS.md)
[Finite agentic-loop roadmap](ROADMAP.md)
[Evaluation method](EVAL_METHOD.md)
[Time-windowed significance digests](DIGESTS.md)

The project contains several different loops. They are deliberately separate;
one loop may invoke another only through an explicit parent/child relationship.
No loop may run indefinitely or silently change the contract of another loop.

## Current status

- `SOURCE_INGESTION`: operational for configured YouTube and X sources.
- `LIBRARY_UPDATE`: operational as `scripts/ingest_update_library_incrementally.py`; external
  scheduling is not installed.
- `RESEARCH_QUERY`: operational for deterministic retrieval and checkpoints.
- `AGENT_TASK`: bounded runner implemented, offline-tested, and run live against
  Claude Sonnet 5 and GLM-5.2.
- `MODEL_EVALUATION`: deterministic repeated-run and provider-comparison
  harnesses implemented and exercised live; human semantic labels remain the
  quality-calibration gap.
- `DIGEST`: 1-day and 7-day runs completed; a provisional single-arm 30-day,
  328-item GLM-5.2 stress run escalated with 321 accepted assessments
  (`data/digests/2026-07-08-to-2026-08-07-youtube-glm-5.2-open-weight-report.json`).
  A seven-day significance-v2 run accepted 46 of 49 original items and
  escalated three after bounded retries. Its completed 20-card audit found 11
  of 18 in-scope claims fully supported by their selected evidence.
  Each item is a bounded unit that may retry, with a checkpoint after every unit.
- `PROJECT_IMPROVEMENT`: planned; the roadmap/evaluation orchestrator is not
  implemented yet.

## Loop taxonomy

| Loop type | Trigger | Responsibility | Model use | State/output |
|---|---|---|---|---|
| `SOURCE_INGESTION` | One source run | Discover and persist new YouTube/X content | None | Source report and registry state |
| `LIBRARY_UPDATE` | Manual or scheduled update | Run incremental ingestion, then refresh the evidence index | None | `data/library-update.json` |
| `RESEARCH_QUERY` | One user question | Retrieve and cite evidence | None initially | Research checkpoint |
| `AGENT_TASK` | One bounded research task | Draft, evaluate, retry, finalize, or escalate | Yes, behind a tested adapter | Task checkpoint and result |
| `MODEL_EVALUATION` | One comparison suite | Run identical cases through two providers and compare measured outcomes | Yes, through `AGENT_TASK` | Benchmark report and comparison artifacts |
| `DIGEST` | One frozen corpus window | Assess every item in the window and rank what changed | Yes, one bounded assessment unit per item; rejected responses may retry | Window snapshot and digest report |
| `PROJECT_IMPROVEMENT` | One roadmap iteration | Implement one objective and evaluate the project | Optional planning/review | Improvement checkpoint and local commit after success |

## Execution relationships

```text
LIBRARY_UPDATE
  └── SOURCE_INGESTION (one per configured source)

AGENT_TASK
  └── RESEARCH_QUERY (one or more retrieval stages)

MODEL_EVALUATION
  └── AGENT_TASK (same task cases, one run per provider)

PROJECT_IMPROVEMENT
  └── tests, evaluations, documentation, and optionally an AGENT_TASK review
```

`LIBRARY_UPDATE` is the background data-maintenance loop. `AGENT_TASK` is the
bounded answer loop and has live provider traces. `DIGEST` is the longer,
per-item workload used to demonstrate checkpoint/resume behavior; it is a
parallel map, not dependent long-horizon reasoning. `PROJECT_IMPROVEMENT` is
the future background development loop. A research query is not a daily
updater, and a library update is not an answer-generation task.

## Shared runtime metadata

Every loop report or checkpoint should identify:

- `loop_type`;
- `run_id`;
- `parent_run_id`, when it is a child loop;
- current stage;
- start and finish times;
- status and stop reason;
- budgets and usage, when applicable.

The runtime taxonomy is implemented in `llm_gym/shared/loops.py`. Run logs also
carry `loop_type`, allowing each loop to be filtered independently.

## Stop rules

- `SOURCE_INGESTION`: stop after the source discovery/download run completes;
  retryable content remains eligible for a future run.
- `LIBRARY_UPDATE`: stop after ingestion and index refresh, even if some source
  items failed; report the failure state clearly.
- `RESEARCH_QUERY`: stop after retrieval and citation checkpointing.
- `AGENT_TASK`: stop on quality-gate success, budget exhaustion, maximum rounds,
  or human escalation.
- `MODEL_EVALUATION`: stop after every benchmark case has been run for both
  providers or the suite budget is reached; report incomplete comparisons.
- `PROJECT_IMPROVEMENT`: stop after one roadmap objective, full regression
  tests, evaluations, documentation update, budget review, and a successful
  local commit. Failed or escalated work must not be committed as successful.

The deterministic loops own state, budgets, retrieval, and stop decisions.
Stochastic model calls are permitted only inside `AGENT_TASK` and optionally
for planning/review inside `PROJECT_IMPROVEMENT`; their outputs never bypass
deterministic evaluation or escalation rules.

## Project-improvement commit rule

The project-improvement loop must commit after each successfully completed
roadmap task. “Successful” requires the task-specific boolean evaluations, the
full regression suite, Markdown/compile checks, and status-document update to
pass. The loop may create local commits automatically, but pushing remains a
separate explicitly authorized action.

## Finite validation order

The validation sequence began with a single `AGENT_TASK` over fixed evidence
and has now reached the digest calibration stage. Follow
[ROADMAP.md](ROADMAP.md) in this order:

```text
M1 reviewed fixtures → M2 live tasks and retrieval retry →
M3/M4 semantic labels and calibration → M5 provider contact/comparison →
M6 digest labels, ranking, and long-run validation
```

Do not treat `PROJECT_IMPROVEMENT`, MCP, or scheduling as prerequisites for
the current M6 calibration work. They remain later capabilities.
