# Finite Agentic-Loop Roadmap

[Project rules](PROJECT_RULES.md)
[Project contracts](CONTRACTS.md)
[Loop architecture](LOOPS.md)
[Evaluation suite](EVALS.md)
[Evaluation method](EVAL_METHOD.md)
[Time-windowed significance digests](DIGESTS.md)

This is the authoritative short-term execution plan. It is intentionally
smaller than the long-term vision. The project should prove one reliable
agentic task before adding general orchestration, MCP, scheduling, or broad
autonomy.

## Objective for the first valid agentic state

Given a question and a fixed snapshot of the local YouTube/X evidence index,
the system must retrieve evidence, draft a cited answer, evaluate it, revise
failed criteria within explicit limits, and either finalize or escalate to a
human with a useful review package.

This is a bounded research task, not yet a general-purpose autonomous
researcher.

## Current position

- Deterministic YouTube/X ingestion and incremental state: operational.
- Cross-platform evidence index and citation-ready retrieval: operational.
- Provider-neutral synthesis and bounded task runner: implemented,
  offline-tested, and run live against Claude Sonnet 5 and GLM-5.2.
- Targeted revisions, budget accounting, resumable checkpoints, and structured
  escalation: implemented and offline-tested.
- Immutable JSON prompt history and full rendered-prompt trace capture:
  implemented and offline-tested.
- Sequential evaluation-suite and provider-comparison runners with per-task
  checkpoints, caches, resume state, and suite cost caps: implemented and run
  live. The current answer suite has 13 reviewed frozen-evidence cases.
- Human semantic calibration: all 13 answer fixtures and seven trajectory
  fixtures are reviewed. The first 20-card digest selected-decision audit is
  complete; 11 of 18 in-scope claims were fully supported by their mapped
  evidence. Independent atomic-claim ground truth remains deferred.
- Live provider validation: watched task runs, repeated prompt/provider runs,
  retrieval-retry traces, and 1-day/7-day/30-day digest reports now exist.
- Background scheduling, MCP, project-improvement automation, and UI:
  deliberately deferred.

## Review disposition before live work

The external reviews were checked against this checkout and the local index:

- The quality gate is permissive for an otherwise well-formed ordinary answer:
  a supported answer can pass with only non-critical citation coverage failing
  (`0.8571` at the current `0.8` threshold). This is a missing signal, not a
  trace-integrity blocker; measure it in M2 before tightening the gate.
- The stop-reason conflation was fixed before the first live run. A quality
  failure after the final allowed round is now distinct from exhaustion of a
  cost, time, or model-call budget.
- Rejected-attempt usage is now stored before the post-attempt checkpoint and
  restored on resume. Digest reports separately count item attempts and actual
  provider requests; legacy checkpoints expose recovered usage as a lower
  bound because failed historical calls cannot be reconstructed.
- Repeated gate failures can still produce very similar retry prompts. This is
  deferred until a trace shows whether the current revision feedback is a
  practical problem.
- The provider-temperature asymmetry finding is stale for this checkout: the
  Anthropic adapter omits `temperature` because Claude Sonnet 5 rejected that
  parameter in live use; the OpenAI-compatible adapter sends `temperature: 0`.
  Provider-specific request shapes are configured and covered by offline tests.
- The retrieval concerns remain measurement targets, but the retrieval layer
  has since been upgraded to Porter stemming, stopword removal, unique
  evidence-item results, and bounded context windows. For the exact
  `reliability_practices` question, the current measurement is 14,917 matching
  chunks and 566 matching evidence items; the Claude workflow source is
  present, while the ColeMedin and mikenevermiss required sources still miss
  the top eight. Do not add embeddings, query rewriting, or full-document
  summaries from this one case. Record the miss and wait for recurrence across
  different questions or a live trace that demonstrates the need.
- The synthesis call now records a bounded evidence diary: for each returned
  item, the model reports whether it was relevant and why. This is a learning
  signal for trace inspection, not proof that retrieval found everything.

This kept the first experiment small: the stop classification was fixed, one
real task was run, and its bounded trace was inspected by hand. The next
implementation priorities now come from the additional manual traces rather
than from predicted failure modes.

## Small finite milestones

### M1 — Review and structure a tiny benchmark

Review 10–15 practical research cases from the existing local index. Each case contains a
question, expected key claims, acceptable evidence IDs, any known conflict or
insufficient-evidence condition, a failure-mode target when relevant, and a
development or holdout split. Add only a small number of targeted variants for
missing evidence, distractors, conflicts, malformed citations, stale evidence,
or unsupported claims.

Success means every case is reproducible from a frozen evidence snapshot and
has a human-reviewable expected result and criterion-level annotation fields.
The existing corpus benchmark builder is only a starting-point generator; it
is not itself an evaluation result.

For efficient review, use `scripts/eval_validate_suite.py --case <case_id>`
to inspect one case after full-suite validation. Keep the suite as one atomic
versioned document while the case count is small; revisit file splitting only
after a measured maintenance trigger in a later milestone.

The current suite focuses on practical questions for learning agentic systems:
harnesses, evals, goldens, loop lifecycle, escalation, and measurement. The
time-windowed significance digest is a separate capability described in
[DIGESTS.md](DIGESTS.md), with ranking, deduplication, and precision/recall
evaluation rather than answer classification.

### M1.5 — Make live stop reasons truthful — complete

Before spending money on live runs, fix and test the distinction between
exhausting the allowed quality-revision rounds and exhausting a resource
budget. At present, `budget_stop_reached()` treats `round_number >=
max_rounds` as a budget stop, and the runner therefore reports
`FAILED_BUDGET / BUDGET_EXHAUSTED` when a task simply reaches its final failed
quality attempt. That would corrupt the first trace findings and make the
quality-gate escalation path appear unused.

The smallest acceptable fix is to make the final outcome selection explicit:

- resource limit reached (time, cost, or model calls) → `FAILED_BUDGET`;
- quality gate still failed after the permitted rounds, with resource budget
  remaining → `ESCALATED_FOR_REVIEW`;
- quality gate passed → the existing completed outcome.

Add regression tests for both paths, including a quality failure with `$0`
spent and remaining time/call/cost budget. Do not change retrieval, prompts,
or evaluation strictness in this milestone.

Implemented in `llm_gym/agent/agent_task.py` and `llm_gym/agent/agent_runner.py`.
Regression tests now cover quality exhaustion with remaining resource budget
and genuine cost-budget exhaustion. A live trace can distinguish “the agent
could not meet quality” from “the agent was stopped by a resource limit.”

### M2 — Run one live bounded task and inspect the trace — first run complete

Configure one model provider and run one complete task through:

```text
retrieve → draft → evaluate → revise → finalize or escalate
```

Use no more than three rounds and enforce the existing time, token, and cost
budgets. Record the answer, citations, failed criteria, revisions, checkpoint,
usage, stop reason, and escalation package.

Success means the complete lifecycle runs against real corpus evidence, does
not claim success when the quality gate fails, and produces a trace that can be
inspected and categorized when a criterion fails.

The first run used Claude Sonnet 5 against the reliability-practices
checkpoint. It completed in one model call at approximately $0.0226, assessed
all eight supplied evidence items, marked six relevant and two irrelevant,
and returned a valid cited answer with a `QUALITY_GATE_PASSED` stop reason.
The CLI now includes the complete retrieved evidence set, snippets, locators,
and artifact paths so the human can review the same bounded context seen by
the model.

Manual review found the answer's material claims traceable to the supplied
snippets, while also identifying one minor case of wording stronger than the
source's hedge. This is a successful first trace, not proof that the overall
system is reliable. The review scope is provenance against supplied snippets;
it does not establish that the full corpus was exhaustively searched or that the
underlying sources are universally true.

M2 success is now defined as: at least one complete real-provider lifecycle
has been run, its bounded evidence context and costs are inspectable, and the
human review records both what passed and at least one limitation or
uncertainty.

### M2.1 — Build a small manual trace record before adding automation

Run five additional watched tasks covering different behavior classes:
conflicting evidence, insufficient evidence, an unsupported causal claim,
and two practical learning questions. For each, record outcome, stop reason,
cost, whether the expected evidence was retrieved, whether the answer's
material claims are traceable to supplied snippets, and one lesson.

Do not read every full source for every run. Review the answer and all supplied
snippets first; open the artifact at its locator only when a snippet is
truncated, ambiguous, or appears to reverse the source's meaning. The goal
is to calibrate human labels and discover recurring failure modes, not to
pretend that a single live run proves recall or truth.

Success means six inspectable trace records exist in total, including the first
run, and recurring failures are separated into retrieval, provenance,
wording, evaluation, provider, or loop-control categories. Do not introduce
an LLM judge, embeddings, map-reduce, or a stricter quality gate before this
manual sample is reviewed.

The six attended traces are recorded in `.fieldnotes.md`. They showed two
correct refusals, two retrieval-recall failures, and two mostly supported
answers with claim-level grounding issues. The thin suite runner is now in
place for the next controlled comparison.

### M2.2 — Establish the immutable-prompt baseline — v4 complete

Run the 13 answer cases once with the extracted immutable `synthesis-v4`
prompt using:

```bash
.venv/bin/python scripts/eval_run_suite.py \
  --model claude-sonnet-5 \
  --repetitions 1 \
  --max-cost-usd 1.0
```

The v4 run completed all 13 cases in 75 seconds, made 14 model calls because
one case required a retry, and cost $0.08305. It stored a compact suite
report, resumable suite state, and per-task results with the effective prompt.
The baseline showed one live retry, four expected-`SUPPORTED` cases returning
`INSUFFICIENT_EVIDENCE`, and no budget or escalation stops. The four mismatches
must be reviewed as evidence/question/prompt findings rather than treated as
one failure class.

### M2.3 — Compare prompt v5 against the v4 baseline — complete

*Historical. The default has since advanced to `synthesis-v7`; v5 and v6 are
retained in the registry and remain selectable for comparison.*

At the time, the default was immutable `synthesis-v5`, containing only three
measured changes: define relevance as usable answer evidence rather than topic
similarity, preserve source hedging, and omit unsupported material claims.
The first v5 run was completed, but its per-case paths collided with v4 and
overwrote the detailed v4 traces. The compact v4 report remains, but the
first live retry trace is not recoverable. This is an experiment-integrity
finding: detailed artifacts must be namespaced, not merely summary reports.

The suite runner now supports explicit `--prompt-version` selection and
namespaces per-case outputs and caches by prompt version and suite run ID.
Before spending on the comparison, a human must adjudicate the
`agent_loop_lifecycle` expected label. Read the frozen evidence and decide
whether it establishes all three required claims, especially the explicit
stopping-condition claim. If it does not, change the case label/rubric before
running the comparison; if it does, keep the case unchanged and record why.

After that adjudication, run three repetitions for each prompt version using
separate state, output, and cache paths:

```bash
.venv/bin/python scripts/eval_run_suite.py --model claude-sonnet-5 \
  --prompt-version synthesis-v4 --repetitions 3 --max-cost-usd 1.0 \
  --output data/eval-suite-v4-report.json \
  --state data/eval-suite-v4-state.json \
  --cache-dir data/eval-suite-v4-cache

.venv/bin/python scripts/eval_run_suite.py --model claude-sonnet-5 \
  --prompt-version synthesis-v5 --repetitions 3 --max-cost-usd 1.0 \
  --output data/eval-suite-v5-report.json \
  --state data/eval-suite-v5-state.json \
  --cache-dir data/eval-suite-v5-cache
```

Compare expected-outcome match, per-case consistency, retries, evidence
assessment, cost, and latency. Pay particular attention to whether v5's
caution systematically harms expected-supported cases or only changes one
sample. Do not change retrieval or evaluation thresholds during this test.

The lost retry and the commit-before-experiment rule belong in the fieldnotes
experiment record; `.fieldnotes.md` is intentionally local and ignored by
Git.

### M2.4 — Build the retrieval-retry loop offline — complete

The six manual traces justify a retrieve↔draft loop: four returned
`INSUFFICIENT_EVIDENCE`, including two cases where curated evidence existed but
live retrieval did not surface it. Build and test this controller with fake
clients before any live run. When a draft reports insufficient evidence and
resources remain, the model may propose a small set of refined queries; the
deterministic controller executes them, deduplicates evidence, and runs a new
draft. The controller, not the model, owns retrieval, budgets, stop rules, and
checkpointing.

Success means offline tests demonstrate: a refined query adds evidence, a
duplicate query does not inflate the evidence set, a successful second draft
can be reached, and a no-new-evidence stop is truthful. The first offline
controller now demonstrates refined-query expansion and duplicate suppression
with fake model and retrieval clients. It is deliberately not wired into the
live runner yet; the next implementation step is to integrate its deterministic
evidence merge, budget, and checkpoint behavior into `run_agent_task`.

### M2.5 — Live-fire the retrieval-retry loop — complete

After M2.3 selects and freezes the prompt version, wire the offline retrieval
controller into a dedicated live script or feature flag without changing the
default suite runner. Run exactly two cases: `what_are_evals` and
`independent_evaluation`. Success is an inspectable trace where round 2 has
more unique evidence than round 1 and the outcome either changes or correctly
does not change. A failure to change the outcome is a useful finding; a missing
round-2 trace is not. Assess both live-fired cases using the frozen-versus-live
triage procedure in `EVALS.md`, not by directly comparing live outcomes with
their frozen `expected_outcome`. Do not run this until the prompt comparison
is complete.

The dedicated live path fired for both requested cases. In one Sonnet run per
case, `independent_evaluation` expanded 8 → 28 evidence items and
`what_are_evals` expanded 8 → 28; both changed from
`INSUFFICIENT_EVIDENCE` in round 1 to a supported classification in round 2.
These are provisional single-arm observations, not quality estimates. The
inspectable traces are
`data/runs/retrieval-retry-independent_evaluation.json` and
`data/runs/retrieval-retry-what_are_evals.json`. Later two-provider trigger
measurement showed why the controller keys on classification **or** thin
relevance rather than treating either self-report as stable; see
`data/runs/trigger-measurement/{agent,open_weight}/summary.json`.

### M3 — Convert semantic review into calibrated evaluation artifacts

The four existing criteria are primarily human semantic-review criteria, not
magic booleans that code can currently determine:

- `evidence_relevant`
- `claims_supported`
- `citations_valid`
- `answer_complete`

Use reviewed failures to create the appropriate artifact: a prompt rule when
the failure is prompt-attributable, a deterministic warning when a reliable
heuristic exists, or a calibrated judge-drafter that proposes a claim-to-
snippet mapping for human audit. Keep the deterministic gate responsible for
format, citation validity, budgets, and stop rules. Add checks only when live
traces demonstrate a need.

Success means the evaluations distinguish a passing answer, a targeted
revision, and an escalation, and recurring failures can be converted into
specific development cases.

M3 candidates include a retrieval-completeness report and a paired
narrow-evidence conflict case. Do not add a new classification enum unless live
trace review shows that scoped wording and the existing conflict evaluation
cannot express the required behavior.

### M4 — Label and calibrate against the M2.3 dataset

Treat the winning arm of M2.3's three-repetition comparison as the canonical
repeatability dataset; do not rerun it under M4. Label a representative sample
of successful, failed, retried, and escalated outputs and record:

- final pass/fail;
- revisions and retries-to-pass;
- whether revisions targeted the failed criterion;
- cost, latency, and model-call count;
- valid stop reason;
- escalation rate and package quality.

Success does not require 100% pass rate. It requires that failures are visible,
bounded, resumable, and correctly classified. These labels become the
calibration set for any future judge-drafter.

Label a representative sample of successful, failed, retried, and escalated
outputs. If an LLM judge is introduced, measure its criterion-level agreement
against those labels on holdout cases before using it for reporting or routing.

### M4.5 — Demonstrate an unattended long-duration batch

Run the canonical 3-repetition × 2-prompt experiment sequentially as one
unattended session under `caffeinate`, with the suite cost cap. Optionally put
a fresh library/index refresh before it to exercise a multi-stage pipeline.
Record wall-clock duration, interruptions, and resume events. This milestone
is about proving unattended operation, not producing new comparison claims.

This is a **batch of short loops**, not one long loop. It demonstrates
unattended operation and resume, but the deterministic controller — not the
agent — owns the duration. Do not describe it as a long-running agent; the
single long-running task is M6.6.

### M4.6 — Harden the retrieval loop for runs measured in tens of minutes — superseded

`run_agent_task` already persists checkpoints and enforces time and cost
budgets. `run_retrieval_retry` does neither: it writes nothing until the run
ends, and only the round count bounds it. At the measured ~45 seconds per
model call, a run of tens of minutes is already permitted by the existing
`max_minutes` budget, so duration is not the missing piece — surviving that
duration is.

**Superseded by the `bounded_loop.py` extraction.** The machinery was extracted
from `run_agent_task` into a shared component rather than copied into the
retrieval loop, and proven against a per-item workload it was not written for.
The digest is its second caller. The retrieval loop itself remains
unhardened — it converges in two rounds, so it was never the loop that needed
to survive tens of minutes. Retarget this milestone only if a long retrieval
run becomes a real requirement.

Original intent, for the record:

- persist a checkpoint after every round, carrying rounds, merged evidence,
  refined queries, usage, and stop reason;
- resume from that checkpoint without repeating completed rounds or losing
  recorded spend;
- enforce elapsed-time and cost budgets between rounds, reusing
  `budget_stop_reached` so a resource stop stays distinct from a quality stop;
- raise `max_rounds` and `max_model_calls` only after the above lands, since
  raising them first only makes an unprotected loop longer.

Success means killing a long run mid-round and restarting it produces a
complete trace with no repeated rounds and no lost usage. Do not add new
task shapes in this milestone.

### M4.7 — Period spend ledger and a notification boundary

Two cost guards exist and both are per-run: a single-task cap
(`agent.max_cost_usd_per_task`) and a budget derived from the size of the work
(`TaskSpec.for_unit_count`, which the digest feeds from window length in days).
Neither knows what any earlier run spent, so nothing bounds spend across a
period. That gap is currently covered by the provider's own console cap, which
is how a measurement run was stopped mid-flight with no local warning.

**Reuse the ingestion window logic rather than inventing a second model.**
Ingestion already bounds work by a window in days
(`ingestion.default_window_days`, `max_window_days`) and already estimates cost
per unit of acquisition (`x.post_read_cost_usd`, `user_read_cost_usd`,
`estimate_x_api_cost`). A period ledger is the same shape applied to model
spend: a window in days, a rate per day, and a refusal when the window's budget
is exhausted. Requesting a 1-day or 3-day pull and requesting a 1-day or 3-day
digest should consult the same accounting, not two parallel ones.

Steps:

- Record every run's spend durably, keyed by day. `data/run-log.jsonl` already
  carries run records; add spend so the ledger is derived rather than a second
  source of truth (Rule 24).
- Before a run starts, reject it when the period budget is already exhausted,
  and report the same distinction the loop already makes: a resource stop, not
  a quality failure.
- Decide and document what a day means — calendar UTC, rolling 24 hours, or per
  invocation. Ingestion's window semantics decide this; do not choose
  separately.

### M4.8 — Notification middleware for cost and budget events

Any cost-related event should be able to reach a human without the human
watching a terminal: a budget stop, a period budget exhausted, a provider
refusal such as a spend cap, an unexpected per-unit cost, and a completed long
run with its total.

The requirement is a **boundary, not an email client**. A single notification
interface with pluggable sinks, so email, push notification, Slack, or a
monitoring console are configurations rather than code changes, and so tests
can assert an event was emitted without sending anything. Sinks are configured
per environment; the default is a local sink that records to the run log only.

Design constraints this project has already earned:

- The event carries the same provenance as the run it describes: prompt
  version, model, index signature, window, spend, stop reason. A notification
  that says "budget exceeded" without saying which run is a page, not a signal.
- Never include credentials or full prompt text in an outbound notification
  (Rule 6). Send identifiers and let the recipient open the artifact.
- Emission must not be able to fail a run. A sink that times out is a warning,
  not a failure (Rule 11).
- Deduplicate: a 328-item run must not send 328 notifications. Batch per run,
  or per threshold crossing.

This is not needed for any current milestone and must not block M6.6. It
becomes necessary the moment a run is scheduled rather than launched by hand.

### M5a — Open-weight provider smoke contact — complete

This was asked for directly in the last session ("please look at GLM 5.2") and
is the smallest open commitment. It is not blocked by M1–M4: an adapter smoke
test needs no trustworthy ruler, only a working request.

Configure the `OPEN_WEIGHT_*` environment variables and run one benchmark case
through GLM 5.2. Capture the trace and record provider-contract surprises; do
not draw model-quality conclusions from one case. Expect contract differences:
the Anthropic adapter needed six fixes on first contact, and the truncation and
JSON-fence defects were both found live rather than offline.

Also record *why* the comparison matters, so the reason is not reconstructed
later from memory: open weights can be deployed on-premise, which is the only
serving option for regulated customers such as banks. Cost is the second
reason, not the first.

### M5b — Optional provider comparison

Only after M1–M4 pass, run the same cases with one frontier provider and one
open-weight provider. Keep evidence, prompts, output schema, budgets, and
evaluations identical. Compare quality, retries, escalations, latency, and
estimated cost. The comparison also tests cost and on-premise deployment
options relevant to regulated customers. Do not add routing until reviewed.

### M6 — Significance digest v1, in small steps

The digest is the second capability and the answer to a question the current
work cannot answer: what does a *long-running* agentic task look like here?
A single question converges in two rounds, so no amount of budget makes it run
for tens of minutes. A digest over a time window has dozens of items to assess
and therefore a legitimate reason to run long. M6.6 is where the digest and
the long-running demonstration become the same artifact.

Ship the steps in order. Each is independently useful, independently testable,
and most cost nothing. Do not skip to M6.6.

#### M6.1 — Frozen window selection — complete

Select corpus items by `published_at` against an explicit window, and freeze
the selection to a snapshot file with its `index_signature`. Deterministic and
free, so it is offline-testable like retrieval. Success means the same window
and index always yield the same item set, and the snapshot records how many
items were considered versus selected.

Window freezing now also removes non-substantive transcript placeholders before
any paid call. The rule removes bracketed caption cues and asks whether any
letter or number remains; it does not use a length threshold or make a semantic
quality judgement. On the seven-day YouTube window it excluded two
`[MUSIC PLAYING]`-only items and retained 47 substantive items.

#### M6.2 — Human audit of selected digest decisions — complete

Do not label whole transcripts: they contain multiple independently judgeable
claims. Sample 20 existing seven-day GLM-5.2 assessments, stratified across the
four hidden model labels. Show the explicit model-generated claim, its mapped
set of one to three exact selected evidence passages, and its YouTube channel
or X account. Hide context by default; make it available only to interpret a
selected passage, never to supply facts absent from the evidence set. Decide
AI/agent scope first. Record out-of-scope items as selection failures and omit
them from significance scoring. For in-scope items, keep the proposed model
label and reason hidden while recording evidence support, a human classification,
and a rationale. Then reveal the reason and label, checking whether the reason
adds unsupported material and whether the label is reasonable.

Use `scripts/eval_audit_digest_claims.py` and the immutable v1 audit rubric.
The audit requires a significance-v2 digest report; it rejects historical v1
reports because their single evidence quote cannot establish a compound
summary. Prompt-versioned artifact names preserve both experiments.
Success means 20 source-hashed scope decisions, evidence-support verdicts and
human classifications where applicable, reason and label reviews for in-scope
items, and a provisional report with scope, support, and accepted-decision
counts. Do not report precision, recall, or ranking quality: model-selected
passages cannot reveal missed claims.

Deferred: build a true gold set around atomic candidate developments and add a
separate missed-claim discovery pass. A second reviewer, agreement,
adjudication, confidence metadata, larger samples, and judge calibration follow
only after that annotation unit is proven useful.

The paid prerequisite is complete. The live GLM-5.2 v2 run attempted the
original 49-item snapshot, accepted 46 assessments, escalated three after 75
provider calls, and cost $0.4217194:
`data/digests/2026-07-31-to-2026-08-07-youtube-glm-5.2-open-weight-significance-v2-report.json`.
One of four initially unresolved items recovered when the retry allowance was
raised; two persistent failures were transcript placeholders and one was a long
source whose generated quote repeatedly failed exact grounding. This is why
future window freezing now excludes non-substantive sources before model calls.
The deterministic 20-card packet was prepared from the 46 accepted assessments.
The blind and reveal phases are complete, with the canonical result at
`data/human-labels/digest-claim-audit-v1/glm-5.2-audit-report.json`:

- 20 cards reviewed: 18 in scope and two out-of-scope selection failures;
- claim-to-evidence support: 11 fully supported, six partially supported, one
  not supported;
- model-reason support: 15 fully supported and three partially supported;
- exact blind human/model class match: 8/18;
- all 18 model labels were judged reasonable alternatives after reveal;
- strict accepted decisions: 11/18, requiring full claim support, full reason
  support, and an acceptable label.

Do not collapse these into one accuracy number. Exact class match and
reasonable-alternative acceptance measure different things, and the latter's
18/18 result does not erase the low exact agreement. The measured failure class
is claim-to-evidence completeness: seven in-scope summaries contained material
details not established by their mapped passages. The audit still says nothing
about claims the model missed, recall, or corpus-level ranking quality.

#### M6.3 — Deterministic near-duplicate grouping (no model call)

Group items describing the same development using cheap signals first: shared
canonical URLs, repeated titles, high lexical overlap. Report groups rather
than collapsing them silently. Measure grouping against separately reviewed
item-to-item duplicate relationships; do not infer duplication from M6.2's
passage audit. Only if this measurably fails should a model be involved — the
same order used for retrieval, where stemming came before embeddings.

#### M6.4 — Per-item significance assessment — complete

For one item at a time, extract the claimed change, the problem it addresses,
and the evidence supporting it, then assign a significance judgement with a
citation. One item per call keeps each unit bounded, inspectable, and
independently retryable — and it is what makes the total run long without any
single call being long. Register the prompt in its own family under
`prompts/`, as `verification` already is; do not add a second unversioned
prompt.

#### M6.5 — Ranked report with escalation

Assemble assessed items into a short ranked digest with citations and
calibrated uncertainty. Escalate borderline or high-impact claims to a human
review package rather than presenting hype as fact, reusing the escalation
package structure from the task runner. The report must distinguish a new
significant item from one that supersedes or contradicts an existing validated
answer, even if supersession is detected manually in v1.

#### M6.6 — The long-running run — stress run executed; calibration incomplete

Run the whole digest over one frozen window as a single bounded task: dozens
of per-item calls, checkpointed after each, under explicit time and cost
budgets, resumable after interruption. The shared bounded-loop extraction from
M4.6 has landed and is used by the digest runner.

Success is not the wall-clock number. It is that a run of tens of minutes can
be killed and resumed, reports truthful stop reasons, keeps its spend
accounted, and produces an inspectable trace per item. M6.2 can audit selected
decision support, while M6.3 can evaluate duplicate grouping. Precision and
recall on significant developments remain blocked on the deferred atomic-claim
gold set and missed-claim discovery pass. Use those eventual metrics—not the
answer-case labels
`SUPPORTED` / `INSUFFICIENT_EVIDENCE` / `CONFLICTING_EVIDENCE`, which do not
describe ranking.

The committed 30-day GLM-5.2 report is a provisional single-arm stress result,
not a clean success: one run selected 328 items, retained 321 accepted
assessments and 10 rejection records, cost $1.7308288, and ended
`ESCALATED_FOR_REVIEW`
(`data/digests/2026-07-08-to-2026-08-07-youtube-glm-5.2-open-weight-report.json`).
Three IDs occur in both accepted and rejected lists; current compatibility
logic removes those stale rejection rows on resume, leaving seven unresolved
items to retry. The historical report does not contain an explicit resume-event
ledger, so kill-and-resume remains an operator-observed result rather than a
repository-verifiable claim. The M6.2 selected-decision audit cannot establish
precision or recall.

#### Deliberately excluded from v1

No scheduling, no MCP, no multi-window operation, no automatic supersession
detection. The first encyclopedia artifact is an index over existing validated
answer checkpoints — question, date, corpus `index_signature`, outcome, and
citation list — an organisational task over artifacts that already exist, not
a new capability.

## Deferred work

- Splitting `scripts/` into subdirectories is deferred: the flat prefix-grouped layout is the interim index and keeps the demo surface shallow.

Do not implement these to reach the first valid agentic state:

- generic multi-agent orchestration or sub-agent graphs;
- automatic task decomposition;
- live web search beyond the local corpus;
- autonomous production actions;
- scheduler/background service;
- MCP façade;
- broad evaluator catalogs or a generic evaluation framework;
- full Promptfoo adoption; it remains optional experiment/CI tooling;
- semantic retrieval or document extraction unless benchmark failures justify
  them;
- corpus-wide per-document summaries or exhaustive recall sweeps unless live
  traces and reviewed cases justify them; summaries must remain derived,
  versioned, refreshable, and linked to the original artifacts;
- automated project-improvement loop;
- UI and performance optimization.

## Next single objective

Since the last revision: M5a ran against GLM-5.2, M2.5 produced live
retrieval-expansion traces, the shared bounded-loop component superseded M4.6,
and digest reports now cover 1-day, 7-day, and 30-day windows. The 30-day run
ended escalated, which surfaced accounting, resume, rejection, and reporting
defects rather than proving clean autonomous completion.

**Next: convert the seven incomplete claim mappings into one narrow
significance-v3 hypothesis, then evaluate it on a fresh holdout.** The completed
20-card audit is development evidence and must not be reused as proof that the
resulting prompt improved. The likely target is claim narrowing: every named
entity, quantity, capability, and recommendation in the summary must be
established by the mapped passages. This does not close the larger
ranking-recall gap.

Then, in rough value order:

1. **M6.5 — ranked report with escalation, including supersession.** Supersession
   is the dependency that would turn the digest from a parallel map into a chain,
   which is the property a long agentic loop is actually judged on.
2. **M6.3 — deterministic duplicate grouping.** Owns the `DUPLICATE` label the
   model is deliberately forbidden from assigning.
3. **M4.7 / M4.8 — period spend ledger and notification boundary.** Not needed
   until a run is scheduled rather than launched by hand, at which point nobody
   is watching the terminal.

Note that the suite is at `suite_version` 6 while the last comparison data is
version 4, so any fresh prompt comparison needs a re-run; the `suite_version`
guard will refuse to mix them. Still do not start an LLM judge as authoritative,
semantic retrieval, or full-document summarization.

## Session handoff

At the end of each session, update this file and the status sections of
`README.md`, `BUILD_MCP.md`, `LOOPS.md`, and `docs/history/PROJECT_BOOTSTRAP.md`. Record the
current milestone, files changed, tests run, live-provider results separately,
known failures, and the next single objective. One successful roadmap task
must produce regression tests, documentation updates, and a local commit;
pushing remains an explicit separate action. After every library update that
changes the corpus, rerun `scripts/eval_validate_suite.py --check-retrieval`.
A newly failing expectation is a finding to triage (retrieval regression versus
corpus growth), not automatically a case edit; the last passing
`index_signature` identifies what changed.

The completed 20-card M6.2 result is recorded in these places so the experiment
has one artifact and consistent summaries:

1. generate
   `data/human-labels/digest-claim-audit-v1/glm-5.2-audit-report.json` as the
   canonical machine-readable result;
2. add the denominators and limitations to the M6.2 completion note here;
3. add one row to `README.md`'s live-artifact table and update its current
   objective;
4. update `DIGESTS.md` current status and `data/human-labels/README.md`;
5. record the interpretation—not just the score—in `.fieldnotes.md`, then
   update the current local briefing section at the top of `.dossier.md` and the
   human-boundary slide in `.slides.md`.
