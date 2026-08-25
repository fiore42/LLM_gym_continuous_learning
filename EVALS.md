# Evaluation Suite

[Project rules](PROJECT_RULES.md)
[Project contracts](CONTRACTS.md)
[Loop architecture](LOOPS.md)
[Finite agentic-loop roadmap](ROADMAP.md)
[Evaluation method](EVAL_METHOD.md)

## Purpose

This suite evaluates the actual project objective: a bounded agent that uses
local YouTube/X evidence, produces a cited answer, evaluates its own result,
revises failed criteria, stops under explicit rules, and escalates unresolved
work.

The machine-readable suite is
[`config/agent_eval_suite.json`](config/agent_eval_suite.json). It contains
corpus-grounded practical answer cases and deterministic trajectory fixtures.
The current answer cases cover harnesses, evals, loop lifecycles, escalation,
and measurement trade-offs. All 13 answer cases and seven trajectory cases are
marked reviewed.

The separate time-windowed significance-digest design is documented in
[`DIGESTS.md`](DIGESTS.md). It is not represented as answer cases because it
requires ranking, deduplication, time cutoffs, and precision/recall labels.

The suite is a reviewed regression and failure-mode fixture set, not a global
quality benchmark. It has been exercised through repeated prompt/provider
runs, but criterion-level semantic labels over stored answers remain a separate
calibration task. The process is defined in [EVAL_METHOD.md](EVAL_METHOD.md).

=== CODEX comment ===
Repeated provider runs were exercised, but repeated distinct prompt arms were
not. The selected prompt version is not forwarded into `SynthesisRequest`; the
current nominal v5 and v6 artifacts all rendered `synthesis-v6`.
=== /CODEX comment ===

Answer cases are failure-mode fixtures for the machinery, not knowledge-
coverage entries. The suite grows only when a new failure mode needs a
fixture; it does not grow with topic curiosity. The knowledge product—a
growing base of validated, cited answers kept current against new material—is
the separate capability described in [DIGESTS.md](DIGESTS.md) and the
validated-answer archive.

## Frozen-evidence and live-retrieval modes

Each answer case contains two distinct tests that share one question:

1. The frozen-evidence synthesis test passes the case's `evidence` array
   directly to the model, as `scripts/eval_run_suite.py` does.
2. The optional retrieval test runs `retrieval_query` against the current
   index and checks whether `retrieval_expected_evidence_ids` are returned.

`expected_outcome` binds only in frozen-evidence mode. It is stable regardless
of corpus growth because the case carries its own evidence, and classifications
are scoped to supplied evidence by contract. A frozen `SUPPORTED` case remains
correct even if contradicting material exists elsewhere in the corpus.

A live-retrieval run of the same question, such as
`scripts/agent_retrieve_evidence_for_question.py` or the live retrieval-retry
loop, may legitimately produce a different
classification because its inputs differ. That divergence is a triage event,
not automatically a benchmark failure:

1. Diff the live-retrieved evidence set against the case's frozen evidence.
2. If the sets differ, classify the finding as retrieval-side: recall/ranking
   change or corpus growth. Compare the recorded `index_signature`.
3. If the sets match and the outcome still differs, classify the finding as
   synthesis-side: model or prompt behavior.

Record the finding under the corresponding failure category. For example,
`independent_evaluation` expects `CONFLICTING_EVIDENCE` in frozen mode but
returned `INSUFFICIENT_EVIDENCE` in a live run because retrieval never surfaced
the curated conflict pair.

## Reviewing individual cases

For assisted review, use `scripts/eval_draft_claim_verification_sheet.py` to propose claim
verdicts and evidence quotes, then confirm or edit each row; only the human
labels feed calibration.

The suite intentionally remains one atomic JSON document while it is small.
This keeps each case, its evidence snapshot, and the evaluation contract
reviewable as one versioned unit. The cases appear before the longer policy
sections for navigation, and the validator can print one case after checking
the whole suite:

```bash
.venv/bin/python scripts/eval_validate_suite.py --case independent_evaluation
```

Use any `case_id` from `answer_cases`. A future split is justified only by a
measured maintenance problem, such as dozens of cases in later milestones;
that change must use an explicit manifest and a `suite_version` migration.

## Corpus-derived coverage

The current cases cover:

- trustworthy and verifiable agent workflows;
- production reliability;
- memory and context retrieval;
- independent evaluation versus same-agent self-review;
- insufficient evidence for an exact metric;
- quality, cost, and latency trade-offs;
- explicit stop-condition semantics;
- harness, loop, and context-engineering boundaries;
- unsupported causal claims;
- cross-platform evidence from YouTube and X.

## Required answer gate

Two different gates exist, at two different layers. Conflating them overstates
what runs automatically, so they are stated separately.

### The declared fixture criteria

Every answer case declares `required_evaluations`, drawn from the vocabulary
defined in the suite's `evaluation_contract`. Four are mandatory in every case:

1. `evidence_relevant`
2. `claims_supported`
3. `citations_valid`
4. `answer_complete`

`scripts/eval_validate_suite.py` enforces that these four are *defined* in the
contract (`REQUIRED_ANSWER_EVALUATIONS`) and that no case references an
undefined name. **That is a schema check, not an execution.** No code scores an
answer against `claims_supported`; these names record what a reviewer is
expected to judge, and semantic support is established by human review
(`scripts/eval_draft_claim_verification_sheet.py` and the digest claim audit in
[EVAL_METHOD.md](EVAL_METHOD.md)), not by the runtime.

The suite also defines optional evaluations for classification calibration,
conflict handling, source diversity, temporal calibration, and uncertainty.
They should be enabled when the benchmark case requires them, not added as
unbounded complexity to every task. They are declarative in the same way.

### The enforced runtime gate

What actually stops or retries a live answer task is
`llm_gym/agent/agent_runner.py::_evaluate`, which applies seven structural
checks through `evaluate_quality`:

| Evaluation | Critical | What it checks |
|---|---|---|
| `answer_nonempty` | yes | The answer text is not blank |
| `citations_present` | yes | At least one citation was returned |
| `citation_validation` | yes | Every cited ID was supplied to the model |
| `classification_valid` | yes | The label is one of the three permitted values |
| `conflict_citation_coverage` | yes | A `CONFLICTING_EVIDENCE` result cites at least two distinct sources |
| `citation_coverage` | no | At least `min(2, len(evidence))` distinct citations |
| `output_schema` | no | Answer and classification are both present |

A run passes when no critical check fails and the pass fraction reaches
`agent.minimum_eval_pass_fraction` (currently 0.8). Every critical check is
structural and mechanically decidable. **None of them establishes that the
cited passage supports the claim** — that is the boundary this project has
measured rather than assumed, and it is why the human audit exists.

Classification is scoped to the supplied retrieved evidence. In particular,
CONFLICTING_EVIDENCE means that the supplied items materially disagree; it does
not mean that the entire corpus or field is conflicted. Answers must say that
retrieved sources disagree when that is the evidence available. Retrieval
completeness and conflict detection are separate evaluation dimensions.

## Trajectory gate

Answer quality alone is insufficient. The trajectory fixtures verify that the
agent:

- targets a failed criterion on revision;
- does not treat identical repeated failures as progress;
- distinguishes budget exhaustion from quality-gate escalation;
- resumes from checkpoints without repeating completed work;
- stops immediately after a valid pass;
- creates an actionable human-review package;
- invalidates cached results when task or evaluation inputs change.

## Review protocol

Before any paid model run, review every answer case for:

- whether the expected outcome is correct;
- whether each required claim is actually supported by the supplied evidence;
- whether the evidence selection is balanced across YouTube and X;
- whether the wording tests calibrated uncertainty rather than trivia;
- whether required and forbidden citation IDs are appropriate.

After review, run each case at least three times with one provider. A model
comparison is optional and comes only after single-provider trajectory results
are trustworthy. A passing suite does not require 100% answer success; it
requires evidence-scoped classification, bounded retries, valid citations, and useful
escalation when quality is not reached.

## Current execution order

1. Validate the 13 reviewed answer fixtures and seven reviewed trajectory
   fixtures offline.
2. After a corpus update, rerun the optional retrieval expectations and triage
   any changed evidence set before editing a case.
3. After a prompt or agent-behavior change, run repeated frozen-evidence cases
   with namespaced reports and decompose aggregate ties per case.
4. Inspect stored traces and convert only recurring failures into targeted
   development fixtures or deterministic checks.
5. Calibrate an advisory model judge against human criterion labels only if the
   review workload demonstrates a need.
6. Compare providers only with identical model-independent inputs and without
   treating a small comparison as a quality ranking.

The suite also contains optional retrieval expectations. Run them against the
local index with:

```bash
.venv/bin/python scripts/eval_validate_suite.py --check-retrieval
```

These checks verify that natural-language queries surface designated evidence;
they do not yet measure exhaustive retrieval recall.

After every library update that changes the corpus, rerun
`scripts/eval_validate_suite.py --check-retrieval`. A newly failing
expectation is a finding to triage—retrieval regression versus corpus growth—
not automatically a case edit. The recorded `index_signature` of the last
passing check identifies what changed.

Promptfoo is optional future tooling for provider/prompt sweeps and reporting;
it is not required for the first valid agentic task.
