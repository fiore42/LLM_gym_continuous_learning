# Evaluation Method and Improvement Flywheel

[Project rules](PROJECT_RULES.md)
[Project contracts](CONTRACTS.md)
[Evaluation suite](EVALS.md)
[Finite agentic-loop roadmap](ROADMAP.md)
[Time-windowed significance digests](DIGESTS.md)

This document defines how the project learns from evaluation results. It is
separate from EVALS.md, which defines the current executable cases and boolean
checks.

## Purpose

The project must improve through measured error analysis rather than by adding
models, prompts, retrieval methods, or frameworks based on intuition. The
evaluation flywheel is:

~~~text
run → inspect traces → label failures → categorize errors → add targeted cases
→ change one thing → run regression and holdout checks → record the decision
~~~

The loop distinguishes deterministic contract violations, semantic quality
judgments, and operational outcomes such as latency, cost, retries, and
escalation.

## Evaluation levels

### Level 1 — deterministic regression checks

Run on every code or contract change. These checks must not require a network,
credentials, or a paid model call.

Examples include output schema validity, citations drawn from supplied
evidence, valid citation URLs and locators, required and forbidden evidence
rules, expected classification, targeted revisions, valid stage order and stop
reason, resumable checkpoints, budget enforcement, safe cache identity, and
warning/failure separation.

### Level 2 — human and calibrated-judge evaluation

Run periodically on a representative sample of real or benchmark outputs.
Human labels are the reference until a judge demonstrates acceptable
agreement on an unseen holdout set. Each label should be criterion-specific
and initially binary where the underlying question is binary. A product
classification such as digest significance keeps its named target classes. A
short rationale and failure category are more valuable than an unexplained
score. Reviewers must inspect
the bounded retrieved context first, then open the `artifact_path` at its
`locator` when a sentence, negation, or surrounding qualification is not
clear. The displayed snippet is a pointer for evaluation, not proof by itself.

The propose-and-confirm workflow in `scripts/eval_draft_claim_verification_sheet.py` may draft
claim-to-evidence verdicts and quote spans to reduce reviewer effort. The
deterministic quote check can downgrade fabricated quotes, but the drafter is
advisory forever: only the human verdict is authoritative, and agreement must
be measured on labeled data, including holdout cases, before any judge output
is used for reporting or routing.

#### Digest claim audit

A complete transcript is not a valid single significance unit: one source can
contain several claims with different evidential strength and practical
importance. M6.2 therefore audits 20 compact, model-selected passages instead
of assigning one label to each full transcript:

1. Select 20 existing assessments with a deterministic allocation balanced as
   far as the available hidden-label population permits. Include every present
   label; do not manufacture equal strata when one label has fewer candidates.
2. Show the reviewer the explicit model-generated claim, the mapped set of one
   to three exact AI-selected evidence passages, and the mnemonic YouTube
   channel or X account. Each passage names the claim component it supports.
   Keep surrounding context hidden by default. The reviewer may request it only
   to clarify a pronoun, negation, or incomplete thought; nearby facts cannot
   rescue an incomplete evidence set.
   Ask scope first: a general technology, security, or business claim without a
   substantive AI/agent connection is `OUT_OF_SCOPE`, stops there, and is
   reported as a selection failure rather than a significance judgement.
3. For in-scope cards, hide the model's proposed label and reason until the
   evidence-support verdict, human classification, and rationale are saved. Model
   suggestions can shift subjective human labels
   and inflate measured performance
   ([Schroeder et al., 2025](https://aclanthology.org/2025.findings-acl.1323/);
   [Choi et al., 2024](https://aclanthology.org/2024.emnlp-main.1230/)).
4. Reveal the model reason and label. Audit whether the reason adds unsupported
   material. Show the blind human/model label comparison explicitly: an exact
   match records `AGREE` automatically; when the labels differ, ask whether the
   model label is nevertheless a reasonable alternative for the supported
   content. Never change the locked blind label during this phase.
5. Report scope, evidence-support, reason-support, label-alignment, and
   accepted-decision counts. Call the result a **provisional model-decision
   audit**.
6. Do not report precision, recall, or corpus-level ranking quality. The sample
   was selected by the model being audited and cannot expose claims it missed.

Run this protocol with `scripts/eval_audit_digest_claims.py`. The local packet
contains the explicit claim, compact evidence, and hashes, but no proposed
model label or reason. The current packet samples 20 of 46 accepted
significance-v2 assessments with a 7/6/1/6 allocation across
`SIGNIFICANT`/`INCREMENTAL`/`UNSUPPORTED`/`PROMOTIONAL`; the single
`UNSUPPORTED` assessment is included rather than oversampled or invented.
This follows broader recommendations to define the construct, use clear
rubrics, blind human comparisons, and calibrate automated graders rather than
assuming validity
([van der Lee et al., 2019](https://aclanthology.org/W19-8643/);
[OpenAI evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices);
[Anthropic agent eval guidance](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)).

Deferred work begins with the structurally correct gold-set unit: one atomic
candidate development with evidence, plus a separate source-review process for
discovering candidates the model missed. Only that design can support recall.
A second reviewer, agreement statistics, adjudication, larger samples, and
judge calibration come after the unit is correct. NIST's ARIA work is a useful
model for that later training/assessment/adjudication phase
([NIST AI 700-2](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.700-2.pdf)).

After the 20 blind decisions and reveal phase are complete, the canonical
result is
`data/human-labels/digest-claim-audit-v1/glm-5.2-audit-report.json`. Record
scope, support, reason-support, label-alignment, and accepted-decision
denominators separately; do not collapse them into one accuracy number.

The first completed audit found 18/20 cards in scope. Claim-to-evidence support
was 11 full, six partial, and one unsupported; reason support was 15 full and
three partial. Exact blind label alignment was 8/18, while all 18 revealed
model labels were judged reasonable alternatives. The strict accepted-decision
count was 11/18. This makes claim-to-evidence completeness the demonstrated
failure class and makes these 20 cards development data, not a holdout for a
future prompt revision.

### Level 3 — controlled experiments and A/B tests

Run only after the single-provider baseline and Level 2 calibration are stable.
Compare one controlled variable at a time, such as provider, prompt, retrieval
configuration, or retry policy. Keep the evidence snapshot, task limits,
evaluator version, and output schema fixed.

The synthesis trace also records a model-generated evidence diary: one
relevance judgment and reason for every supplied item. Use it to identify
patterns such as repeated irrelevant retrievals or evidence that is repeatedly
read but not cited. Do not treat it as an authoritative answer about what was
missing from retrieval; the model cannot label evidence it never received.

## Failure annotation contract

Every failed or disputed criterion should record case ID, criterion, boolean
result, failure mode, severity, human label, human critique, evaluation
version, benchmark split, and experiment ID.

The initial failure taxonomy is:

- unsupported claim;
- missing important evidence;
- irrelevant evidence;
- invalid citation;
- citation does not support claim;
- incorrect classification;
- overconfident wording;
- ignored conflict;
- incomplete answer;
- ineffective retry;
- invalid stop decision;
- non-actionable escalation;
- conflict overclaimed beyond retrieved evidence;
- conflict missed due to narrow retrieval.

New categories may be added when recurring failures cannot be represented by
the existing taxonomy. Existing category meanings must not change silently;
increment the evaluation version when the rubric changes.

The deterministic scope check is a coarse safety net for common wording. It
cannot recognize every indirect corpus-wide claim, so Level 2 human or judge
review remains necessary.

Future recall work is deliberately separate from this diary. Candidate steps
are query decomposition, unique-evidence recall measurement on reviewed cases,
and only then semantic retrieval or precomputed summaries if live traces
justify them. Summaries are lossy and must not replace original artifacts;
derived summaries would require their own version, provenance, refresh rule,
and holdout tests.

## Benchmark design

The benchmark should remain small and scenario-focused. Each core scenario
should have a normal case plus targeted variants for missing evidence,
distractors, conflict, malformed citations, stale evidence, or unsupported
numeric/causal claims when relevant.

Cases are divided into development and holdout splits. Development cases may
guide prompt or implementation changes; holdout cases must not be used to tune
prompts, evaluators, or routing.

Every report must include denominators and per-criterion results. A small
benchmark must not be presented as a statistically definitive global quality
score, and 100% is not a required objective.

## Human and judge alignment

Before introducing an LLM judge:

1. sample successful, failed, retried, and escalated outputs;
2. label them by criterion with a short critique;
3. record disagreements rather than forcing false consensus;
4. add recurring failures to the development benchmark;
5. reserve unseen examples for calibration.

A judge must return a criterion label, critique, and confidence or rationale.
Its agreement with human labels must be reported per criterion on the holdout
set. The judge may provide diagnostics, but it must not override deterministic
contract failures such as fabricated citations.

## Trace inspection

Evaluation results must remain inspectable through the complete task trace:
question and corpus snapshot, retrieved evidence IDs, model and prompt
versions, answer and citations, evaluator results and critiques, revision
requests and outputs, usage/cost/latency, and final stop/escalation state.

The first implementation may use JSON/JSONL and a small local viewer. A full UI
is not required for the first valid agentic state.

## Metrics

Reports should keep these dimensions separate:

- critical-evaluation pass rate;
- diagnostic-evaluation pass rate;
- citation and claim-support failures;
- retries-to-pass;
- escalation rate;
- repeated-run consistency;
- latency and model-call count;
- estimated cost;
- corpus or ingestion coverage when relevant.

Do not replace these with one generic score. A weighted score may summarize a
run, but critical citation/support failures must remain visible and must not be
hidden by partial credit.

## Experiment record

Each improvement experiment should record its hypothesis, one changed
variable, baseline suite and evaluator versions, model/prompt/corpus snapshot,
development and holdout results, human disagreement, operational metrics,
decision, and follow-up action.

The roadmap should count completed experiments and validated behaviors, not
only added features.

## Retrieval completeness and conflict scope

Conflict detection is evaluated relative to the evidence supplied to the task.
An answer may say that retrieved sources disagree, but must not imply that the
entire corpus or field agrees or disagrees unless the task explicitly uses an
exhaustive, frozen topic snapshot.

Retrieval completeness is a separate deterministic metric. Search results
should expose how many matching chunks and evidence units were found, how many
were returned, whether the result was truncated by the limit, and which index
version was searched. A high match count does not prove completeness, but it
makes retrieval scope visible.

Future M3 cases should include a paired narrow-evidence variant: the same
question with a strict subset of the evidence. This tests whether the agent
avoids overclaiming when retrieval is incomplete.

## External references

These references informed this method:

- [Your AI Product Needs Evals](https://hamelhusain.substack.com/p/evals)
- [A Field Guide to Rapidly Improving AI Products](https://hamel.dev/blog/posts/field-guide/)
- [Creating a LLM-as-a-Judge That Drives Business Results](https://hamelhusain.substack.com/p/llm-judge)
- [How Engineers and PMs should collaborate on Evals](https://www.youtube.com/watch?v=XueTa4qrMpg)
- [promptfoo](https://github.com/promptfoo/promptfoo)

Promptfoo may be used later as an optional experiment runner or CI/reporting
tool. It does not replace this project's evidence, citation, state,
checkpoint, and escalation contracts.
