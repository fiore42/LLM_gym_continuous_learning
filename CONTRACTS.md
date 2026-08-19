# Project Contracts

[Project rules](PROJECT_RULES.md)
[Loop architecture](LOOPS.md)
[Finite agentic-loop roadmap](ROADMAP.md)
[Evaluation suite](EVALS.md)
[Evaluation method](EVAL_METHOD.md)
[Time-windowed significance digests](DIGESTS.md)

This file is the compatibility boundary for source adapters, durable state,
evidence retrieval, and the separate project loops. A change that breaks a contract
must either preserve a compatibility path or explicitly version and migrate
the contract. Tests should cover every contract marked stable.

## Current project status

The deterministic ingestion and library-update worker is operational for
YouTube and X. The evidence index and retrieval/checkpoint query slice are
operational; the bounded synthesis runner, offline evaluation harness, and
provider adapters are also implemented and have been run against two live
providers. A time-window digest runs a frozen window as one long resumable
task. A 20-card audit of selected significance-v2 decisions is complete: 11 of
18 in-scope claims were fully supported by their mapped passages. Independent
atomic-claim significance ground truth, a period spend ledger, MCP, and
scheduling are not yet complete.

## Deterministic versus stochastic boundary

Deterministic software owns scheduling, discovery, authentication boundaries,
downloads, retries, IDs, publication-date storage, completion state, indexing,
retrieval, citations, checkpoints, and evaluation scoring. These stages must
be reproducible and independently testable.

Stochastic model calls are reserved for semantic work: synthesis, open-ended
summarization, concept extraction, query expansion, and interpretation of
potential conflicts. Their model, immutable prompt version, prompt hash,
inputs, outputs, and usage must be recorded, and their results must be checked
by deterministic citation and evaluation stages. Answer-task attempts retain
the full rendered prompt. High-volume digest rows retain the immutable template
identity and source-item identity so the prompt can be reconstructed locally
without copying every transcript into every checkpoint. Prompt definitions are
append-only JSON artifacts under `prompts/`; a new prompt creates a new version
rather than editing history. A prompt must never silently replace durable state
or an exact rule.

## 1. Source identity contract

Every source has:

- `platform`: lowercase adapter name, such as `youtube` or `x`;
- `source_key`: canonical, stable account/channel identity;
- `canonical_url`: public URL used for citations;
- `source_type`: currently `account` or `channel`.

Equivalent URL spellings must normalize before registry access. For YouTube,
`/@handle` and `/@handle/videos` identify the same source. Source identity
changes are conflicts, not silent updates.

## 2. Content identity contract

Every content item has a stable source-specific `content_id`, canonical URL,
and publication timestamp when available. Storage directories use:

```text
YYYYMMDD_<content-id>
```

The date is the publication date, never the download date. A content ID may
have several evidence units, for example an X post and its video transcript.

## 3. Source adapter contract

An adapter may handle source-specific discovery, authentication, downloads,
and retries, but it must expose source-independent results to downstream
stages. The evidence boundary is represented by `EvidenceAdapter` and
`EvidenceRecord` in `llm_gym/corpus/evidence.py`.

An adapter must:

- return deterministic records for the same local inputs;
- preserve the original source URL and content ID;
- distinguish extracted text from unextracted binary artifacts;
- return warnings separately from failures;
- be safe to rerun without duplicating terminal content;
- provide offline regression tests with injected network/process boundaries.

Adding a source should not require changes to retrieval, citation, evaluation,
or agent-loop code. If it does, the common contract must be extended first.

## 4. Evidence record contract

Each searchable unit contains:

```text
evidence_id       deterministic hash of source identity, content, kind, artifact
platform          source adapter name
source_key        canonical account/channel identity
content_id        source-specific content ID
canonical_url     citation URL
published_at      original publication time, if known
title             optional title
author            optional account/author
kind              transcript, post, attachment_text, or future kind
text              extracted searchable text
locator           transcript/page/timestamp locator, when available
artifact_path     local provenance path
content_hash      hash of extracted text
extraction_status EXTRACTED or an explicit non-searchable status
```

Binary video, audio, and documents are not searchable merely because they
exist. They remain preserved ingestion artifacts until an extractor produces a
record. Missing or unsupported extraction must be visible as a warning.

## 5. State and completion contract

The central source registry is authoritative for terminal content decisions.
Per-source state is a worker cache and must agree with the registry under
`scripts/check_state_registry_consistency.py`.

`COMPLETED` means all required artifacts are valid and the final completion
marker was written. Retryable failures must not be treated as terminal.
`SKIPPED_SHORT_NO_SPEECH` is a terminal warning, not a failure. Warnings never
change a successful run into a failure.

## 6. Report and logging contract

Reports are structured JSON and contain source/content IDs, stages, statuses,
warnings, failures, and artifact paths. Logs are redacted JSONL operational
records. Interactive output is a compact view of the same state; it is not the
source of truth. A new run must be filterable independently from prior runs.

## 7. Configuration contract

Operational defaults are loaded from `config/PARAMETERS.json`. CLI arguments
may override a value only when the rules explicitly permit it. The global
maximum ingestion window is defined there and applies to every source adapter.
New global behavior must be added to this file, validated centrally, and
documented here before adapter-specific code consumes it.

## 8. Agent-loop contract

Agent-task loops consume only evidence records and retrieval results. They
must cite canonical URLs plus locators, distinguish `SUPPORTED`,
`INSUFFICIENT_EVIDENCE`, and `CONFLICTING_EVIDENCE`, persist a checkpoint, and
be resumable without repeating completed stages. Checkpoints carry loop
identity, timestamps, current stage, attempts, usage, stop reason, and a
structured human-review package. `FAILED_BUDGET` is distinct from quality-gate
escalation. MCP and scheduling layers may call the loop but must not bypass
these guarantees.

## 9. Library update contract

The library update worker runs stages in this order:

```text
incremental ingestion → evidence collection/index refresh → update checkpoint
```

The index stage runs even when ingestion exits with item-level failures, so
successful local content is not stranded. `data/library-update.json` records
both stage outcomes. A nonzero ingestion result produces
`COMPLETED_WITH_FAILURES`; it must not be reported as a clean update.

## 10. Long-running task contract

The first agent task is an evidence-backed technology brief over a fixed,
human-reviewed benchmark case. A task must
persist its question, input snapshot, current stage, evidence IDs, model and
prompt versions, evaluation policy, attempt count, budgets, and final outcome.

The schema and deterministic quality gate are implemented in
`llm_gym/agent/agent_task.py`; the bounded runner implements targeted revisions,
budget outcomes, resumable checkpoints, and structured escalation packages.

The provider-neutral synthesis interface is implemented in
`llm_gym/agent/synthesis.py`. It accepts only retrieved evidence and rejects
malformed responses or citations that were not supplied in the request.
Prompt definitions are loaded by `llm_gym/agent/prompt_registry.py`; each attempt
stores the complete effective system and user prompts alongside the prompt
version and hash so a historical call can be reconstructed rather than only
identified by a version label.
The provider clients are implemented in `llm_gym/agent/model_client.py`; they read
credentials, endpoints, and model settings from the protected environment and
never write credentials to task outputs or logs. Set `AGENT_PROVIDER=anthropic`
to use Anthropic's Messages API with `ANTHROPIC_API_KEY` and optional
`ANTHROPIC_BASE_URL`. Synthesis and task contracts remain provider-neutral.
Provider clients normalize input/output token usage and calculate estimated
cost only from `AGENT_INPUT_COST_PER_MILLION` and
`AGENT_OUTPUT_COST_PER_MILLION`; zero rates mean unknown cost, not free usage.

Provider request failures are part of the operational trace. HTTP 4xx errors
are recorded with the provider's sanitized response detail and are not retried
automatically; transient 408/409/429 and 5xx errors remain retryable. A
non-retryable provider failure must stop with `PROVIDER_REQUEST_FAILED`, not be
reported as a quality-gate failure.

Once a provider response envelope is readable, its token, latency, and cost
usage is recorded before content validation. A response rejected for
truncation, malformed JSON, or invalid citations is still a billed attempt;
the checkpoint must preserve that usage so resume cannot buy the same budget
twice. Paid CLI entry points return a non-zero exit status for unresolved,
budget-stopped, or incomplete work while preserving valid
`INSUFFICIENT_EVIDENCE` and `CONFLICTING_EVIDENCE` results as successful task
outcomes.

Only `RUNNING` task checkpoints are resumable. A terminal failure or escalation
is historical evidence; the next invocation must start a new run unless a
successful cache entry is available.

Anthropic requests must follow the selected model's parameter contract. In
particular, the Sonnet 5 adapter omits `temperature`, `top_p`, and `top_k`,
which that model rejects when explicitly set; deterministic behavior comes
from the prompt and validation stages instead.

Anthropic responses may contain thinking and text content blocks. The adapter
must extract all text blocks and must not assume the first block is text.
For this bounded JSON synthesis task, the adapter explicitly disables adaptive
thinking so the response budget is reserved for the required text output.

An OpenAI-compatible base URL does not imply an OpenAI-compatible request
body. Fields that providers disagree about — currently `response_format` and
`thinking` — are configured per provider prefix as `{PREFIX}_RESPONSE_FORMAT`
and `{PREFIX}_THINKING`, validated at client construction rather than
discovered as an opaque provider error. Unset defaults preserve the OpenAI
shape. Two consequences must be assumed for any new provider until measured:
that reasoning may be enabled by default, which bills as output and can
exhaust `max_output_tokens` before the required JSON is emitted; and that a
lower advertised per-token price does not imply a lower per-task cost.

Each comparison arm must be configured in full. No arm may fall back to
another arm's credentials, model, or body shape, because the comparison
report must record what each arm actually was.

Each synthesis response must also include one `evidence_assessment` entry for
every supplied evidence ID. Each entry records `relevant`, a boolean model
judgment, and a concise `reason`. The runner validates coverage and records
aggregate counts in the trace, but these judgments are diagnostic signals, not
ground truth: a model assessing evidence it was given can miss relevant items.
The v6 prompt may also return up to three `suggested_queries` when evidence is
insufficient. These are proposals only: deterministic controller code decides
whether to execute them, deduplicates returned evidence, and applies all
budgets and stop rules.
The parser may remove a Markdown JSON fence or harmless surrounding prose, but
must reject malformed or non-object responses and include only a bounded
preview in validation diagnostics.

Evidence expansion must trigger on the classification label **or** a thin
relevance count, never on either alone. Both are model self-reports and both
are unstable. Measured over 6 runs per provider, 2 cases × 3 repetitions,
claude-sonnet-5 and glm-5.2, prompt synthesis-v7, identical evidence sets
(`data/runs/trigger-measurement/{agent,open_weight}/summary.json`): on one case
Sonnet held its label constant across all 3 repetitions while its relevance
count moved 3 → 5 → 1, and on the other case it did the reverse. Which signal
is stable varied by model and by case, so neither can be designated the
trustworthy one. On the same measurement, 4 distinct combinations of the two
signals produced 1 identical expansion decision across all 6 runs of one case —
the union absorbs instability that either input alone would pass through to
control flow. The union also fails in the safe direction, biasing toward
retrieving more evidence rather than answering on thin evidence. Provisional:
two providers, two cases.

Do not report a trigger that has not yet fired as one that cannot fire. An
earlier single-arm observation was incorrectly generalized that way, then
superseded when the relevance-only path fired in 1 of 6 Sonnet runs and 2 of 6
GLM-5.2 runs (2 cases × 3 repetitions per arm, prompt `synthesis-v7`):
`data/runs/trigger-measurement/{agent,open_weight}/summary.json`. See Rule 33
in [PROJECT_RULES.md](PROJECT_RULES.md).

The allowed lifecycle is:

```text
prepare → retrieve → draft → evaluate → revise or finalize → checkpoint
                                             ↓
                                          escalate
```

Only deterministic evaluators may approve finalization. A retry must target a
failed criterion and must stop when the maximum rounds, time, token, or cost
budget is reached. Unresolved tasks produce a human-review package rather than
an apparently successful answer. Identical task inputs and versions must reuse
the cache when the prior result passed its evaluation policy.

Classification scope is limited to the evidence supplied to the task:

- SUPPORTED means the supplied retrieved evidence answers the question without
  material disagreement;
- INSUFFICIENT_EVIDENCE means the supplied evidence does not establish an
  answer;
- CONFLICTING_EVIDENCE means the supplied evidence contains materially
  different claims.

These labels must not be presented as exhaustive claims about the entire
corpus or field. Retrieval completeness is a separate deterministic concern.
Search metadata must report the requested limit, returned count, matched
evidence/chunk counts, truncation, and index version where available.

Retrieval context is also deterministic and bounded. Query stopwords must not
drive matching; FTS morphology uses the versioned offline Porter tokenizer;
results are unique evidence items; and each returned `snippet` contains nearby
matched transcript chunks joined with `[…]` when matches are separated. The
full source remains available through `artifact_path` and `locator`; snippets
are review context, not a substitute for reading the source when meaning is
ambiguous.

The synthesis CLI output must include the complete retrieved evidence set used
for the model request, including every bounded snippet and its provenance
fields. This makes manual review self-contained and makes clear that the
closed-book model was evaluated against supplied snippets, not unseen source
documents.

Synthesis traces should expose the model's evidence assessments so reviewers
can compare returned, distinct, relevant, cited, and omitted evidence. This
does not prove recall: identifying evidence that should have been retrieved
requires a human-reviewed gold set or a deliberate exhaustive topic sweep.

Every retrieval-semantics change must increment the index version and rebuild
the derived SQLite/FTS index. Research checkpoints and answer caches must carry
the index signature and be invalidated automatically when it changes. This
preserves the source corpus and evidence records; invalidating derived answers
must never delete collected information.

The `PROJECT_IMPROVEMENT` loop has an additional commit requirement: after a
roadmap task passes its boolean evaluations, full regression suite,
documentation checks, and budget review, it creates one local commit. Failed
or escalated tasks must not be committed as successful work. Pushing remains a
separate authorized operation.

The bounded runner in `llm_gym/agent/agent_runner.py` implements retry, cache,
checkpoint, quality-gate, and escalation behavior. It does not claim a task
success when the quality gate fails.

The first validation scope is intentionally limited to four boolean
evaluations: evidence relevance, claim support, citation validity, and answer
completeness. Each evaluator returns a boolean and a diagnostic. Additional
evaluators are extensions, not prerequisites, unless a benchmark case requires
one to express its expected behavior.

## 11. Evaluation-method contract

Executable Level 1 checks, human/validated-judge Level 2 checks, and
controlled Level 3 experiments must remain distinguishable in reports. Every
meaningful failure or human disagreement must be attributable to a criterion,
failure category, evaluation version, benchmark split, and trace. Critical
deterministic failures must not be hidden by weighted partial scores.

Benchmark changes must preserve a development/holdout distinction. A judge may
not be treated as authoritative until its agreement with human labels has been
measured on unseen cases. Evaluation criteria are versioned; changing their
meaning invalidates directly comparable prior results.

The complete annotation, trace, metric, and experiment requirements are in
[EVAL_METHOD.md](EVAL_METHOD.md). This contract is compatible with optional
external runners such as Promptfoo, but external tooling must not replace the
project's evidence and trajectory contracts.

### Budget derivation contract

Both budgets are runaway guards and both scale with the work; only the
*ceilings* are absolute. A single flat cap serves neither a short answer task
nor a hundreds-of-items digest: it becomes idle headroom for the former and a
surprisingly close wall for the latter.

The call budget is fitted to the unit count. The cost budget is fitted to a
figure the caller supplies, because the caller knows its own unit economics: a
digest derives it from window length in days, at
`digest.max_cost_usd_per_window_day`. Per-day calibration averages over the
number and length of items produced in that window; per-item spend remains
variable. Left unset, `agent.max_cost_usd_per_task` applies.

Budget figures are set from measurement, not intuition. The current calibration
inputs are 6 Sonnet retrieval-trigger runs (2 cases × 3 repetitions, 14 provider
requests, $0.540322 total) and 3 GLM-5.2 digest windows (1, 7, and 30 days; 382
selected items). These are provisional single-arm measurements, not universal
economics. The answer-run artifact is
`data/runs/trigger-measurement/agent/summary.json`; digest artifacts are the
three reports in `data/digests/`.

`TaskSpec.for_unit_count` fits the call budget to the unit count, never below
the configured default and never above `agent.max_model_calls_ceiling`. The
ceiling is not redundant: a derived budget grows along with a bug in the
estimate that produced it, so a window selection returning fifty thousand items
must still meet something absolute.

The fitted value divides by `stop_at_budget_fraction`, because the guard stops
at that fraction of the budget. A budget fitted exactly to the work guarantees
the run stops short — 328 units against a 0.8 fraction halts at 262.

The guard tracks two counters. `count_unit` records completed workload units;
`count_model_calls` records provider requests, including retries inside a unit.
The call budget is enforced against the second counter. A digest reserves its
configured retry allowance when deriving the budget, while the cost budget
still bounds the actual billed usage.

### Digest significance contract

The digest assesses one corpus item per bounded unit. A unit starts with one
model request and may retry a response rejected by provider or quote/schema
validation. Keeping one item per unit makes work inspectable and independently
retryable, and lets a run last tens of minutes without any single request being
long. A single request over a whole window is cheaper to build and cannot be
debugged.

Each significance-v2 assessment returns the claimed change, the problem it
addresses, a significance label from `SIGNIFICANT`, `INCREMENTAL`,
`UNSUPPORTED`, `PROMOTIONAL`, a reason, and one to three evidence entries. Each
entry maps one concise claim component to a **verbatim span copied from the
item text**. The complete claim must be no broader than the union of those
entries. Deterministic code locates every span in the source, comparing with
whitespace collapsed so a reflowed line break is not treated as a misquote,
and rejects the response when any span cannot be found. Historical
significance-v1 reports retain their single-span shape. The judgement is
therefore auditable rather than trusted: a confident assessment quoting
something the item never said fails at validation, not downstream.

Window freezing excludes source text containing only bracketed transcript cues
or no alphanumeric content before a model call. This is a deterministic source-
quality rule, not a semantic filter: no minimum transcript length or topic
judgement is applied. The exclusion count belongs in the frozen snapshot and
freeze-command output.

One retry per item is the default. A caller may explicitly request zero to five
retries; the call budget must reserve the selected allowance and the report must
record it. More retries never justify weakening exact-quote or schema
validation, and unresolved items remain visible as human escalation.

`DUPLICATE` is deliberately not a label a model may assign. Duplication is a
deterministic property of a group of items, decided by code as retrieval and
scoring are, not a judgement about one item seen alone.

Only the supplied item reaches the model. An assessment must not be able to
cite, or be influenced by, an item it was not given.

### Model comparison contract

The `MODEL_EVALUATION` loop compares providers, not prompts or
datasets. Each comparison case must use the same question, retrieved evidence
IDs, prompt version, task limits, evaluation-policy version, and output schema.
The report must retain the provider/model identity and record at least:

- pass rate and critical-evaluation failures;
- retries-to-pass and escalation rate;
- model-call count, per-call latency, and output tokens per second;
- estimated cost, when the provider exposes sufficient usage data.

Latency is recorded per provider call as time-to-last-token, since both
clients block until the whole response is read. Report throughput alongside
it, and prefer throughput when ranking providers: raw latency scales with how
much the model chose to write, so a more verbose model looks slower than it
is. Compute throughput from summed tokens over summed time, never as the mean
of per-call rates.

An A/B result must not silently choose a production default. It produces a
versioned comparison report first; routing or default selection is a separate
explicit decision based on the measured trade-offs.
