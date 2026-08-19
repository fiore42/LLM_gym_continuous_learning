# Time-windowed significance digests

[Project rules](PROJECT_RULES.md)
[Project contracts](CONTRACTS.md)
[Loop architecture](LOOPS.md)
[Finite agentic-loop roadmap](ROADMAP.md)
[Evaluation suite](EVALS.md)
[Evaluation method](EVAL_METHOD.md)

## Purpose

The project has a second use case beyond answering evergreen questions: after
each ingestion run, identify what was published since the previous run that
may materially improve the way agent systems are built or operated.

Example objectives include improvements in reliability, predictability, speed,
cost, evaluation practice, tooling, or long-running execution.

This is a separate task from corpus-grounded question answering. It operates
on a time window and ranks candidate items; it must not be hidden inside the
`answer_cases` classification model.

## Pipeline

1. Select new items using publication time and the persisted ingestion checkpoint.
2. Group duplicates and near-duplicates describing the same development.
3. Extract the claimed change, affected problem, evidence quality, and source diversity.
4. Estimate significance using novelty, expected impact, credibility, and practical relevance.
5. Produce a short ranked digest with citations and calibrated uncertainty.
6. Escalate borderline or high-impact claims for human review instead of presenting hype as fact.

## Evaluation design

Digest evaluation requires a separate frozen case type containing a cutoff,
candidate items, duplicate groups, and human labels such as significant,
incremental, unsupported, promotional, or missed significant item. `DUPLICATE`
is stored as a separate relationship between items, never forced into the
single-item significance label.

The main metrics are precision and recall for significant items, duplicate
suppression, citation validity, justification grounding, and uncertainty
calibration. A digest should not be judged only by the answer-case labels
`SUPPORTED`, `INSUFFICIENT_EVIDENCE`, and `CONFLICTING_EVIDENCE`.

M6.2 audits compact model-selected passages because a full source transcript
can contain multiple claims with different significance. The reviewer labels
the claim's AI/agent scope first, with the originating YouTube channel or X
account visible. Out-of-scope items are selection failures and do not enter
significance results. For in-scope items, the reviewer audits whether one to
three exact, mapped model-selected evidence passages jointly support the claim
while the proposed model label and reason are hidden. Context is optional and
can clarify a passage but cannot add missing evidence. The reviewer then
reveals and audits the model judgements. This is
a selected-decision audit, not a gold set or recall measurement. See
[EVAL_METHOD.md](EVAL_METHOD.md).

### Supersession

A claim in a previously validated answer is superseded when a newer
authoritative source materially contradicts it. The primitives already exist:
`CONFLICTING_EVIDENCE` classification, `published_at` on every evidence
record, and the `temporal_calibration` evaluation. Supersession detection is
temporal conflict detection between new-window material and previously
validated answers. Marking entries as “new insight from [source]” or “outdated
per [source]” is a digest-layer responsibility—never edit golden cases to
reflect it, because golden cases are frozen test fixtures.

## Current status

Steps 1, 3, 4 and 5 of the pipeline are implemented. Historical one-day and
seven-day GLM-5.2 significance-v1 runs completed; a 30-day stress run attempted
all 328 selected items, retained 321 accepted assessments, and escalated. A
seven-day significance-v2 run then accepted 46 of the original 49 items after
75 provider calls and escalated three. These remain runs from one provider arm,
so performance findings are provisional. Reports are in `data/digests/`.
Significance-v2 requires one to three mapped evidence passages and narrows the
summary to their union. Its deterministic 20-card human audit is complete.
Two cards were out-of-scope selection failures. Of 18 in-scope claims, 11 were
fully supported by their mapped passages, six were partially supported, and
one was not supported. The canonical report is
`data/human-labels/digest-claim-audit-v1/glm-5.2-audit-report.json`.

| Pipeline step | State |
|---|---|
| 1. Select new items by publication time | Implemented — `llm_gym/corpus/window.py`, frozen to a snapshot with its `index_signature`; placeholder-only transcript cues are counted and excluded before paid calls |
| 2. Group duplicates and near-duplicates | **Not implemented** (ROADMAP M6.3). Deterministic, so it precedes any model involvement |
| 3. Extract claimed change, problem, evidence | Implemented — `llm_gym/agent/significance.py`, one bounded item unit; validation/provider failures use one retry by default and a bounded configurable override when explicitly requested |
| 4. Estimate significance | Implemented, as a label from `SIGNIFICANT`, `INCREMENTAL`, `UNSUPPORTED`, `PROMOTIONAL` |
| 5. Produce a ranked digest with citations | Implemented — deterministic ranking by label then publication date |
| 6. Escalate borderline or high-impact claims | **Not implemented** (ROADMAP M6.5) |

`DUPLICATE` is deliberately absent from the model's label set: duplication is a
deterministic property of a group, decided by code, not a judgement about one
item seen alone. That is what step 2 owns.

**What is still missing, and why the reports say so themselves.** No independent
atomic-claim significance set or missed-claim discovery pass exists, so
precision and recall on significant developments are unmeasured and every report carries an
`evaluation_note` stating that its ranking is unvalidated. Individual judgements
*are* checkable: significance-v2 requires one to three mapped verbatim passages,
each of which deterministic code located in the source item before accepting
the response. Historical significance-v1 reports retain their single quote.

The 30-day report is a historical stress artifact, not a clean completion:
`data/digests/2026-07-08-to-2026-08-07-youtube-glm-5.2-open-weight-report.json`
contains 321 accepted assessments and 10 rejection records, with three item IDs
present in both lists. Current resume logic treats an accepted assessment as
terminal, removes those three stale rejection rows, and retries only the seven
unresolved items. It also reports provider requests separately from items and
marks usage recovered from legacy checkpoints as a lower bound rather than
inventing precision.

The v2 report is also intentionally incomplete rather than silently repaired:
`data/digests/2026-07-31-to-2026-08-07-youtube-glm-5.2-open-weight-significance-v2-report.json`
records 46 accepted assessments, three rejections, 75 exact provider calls, and
$0.4217194. Two persistent rejections were `[MUSIC PLAYING]`-only sources;
future window freezing excludes that deterministic source-quality condition.
The remaining long-transcript rejection is preserved as a human-escalation
example rather than weakening exact-quote validation.

**What the first human audit changed.** Exact quote location was necessary but
not sufficient: seven of 18 in-scope summaries were broader than the union of
their selected passages. By comparison, 15/18 model reasons were fully
supported. Exact blind class agreement was 8/18, although the reviewer judged
all 18 model labels reasonable after reveal. Treat that divergence as evidence
that the label boundary is subjective; do not report the latter as perfect
classification quality. The next prompt experiment should target claim
narrowing and use a fresh holdout, because these 20 cards are now development
examples.

**One architectural caveat worth stating plainly.** As built, the digest is an
embarrassingly parallel map, not a dependent chain — the prompt forbids an item
from seeing the others, so reliability is additive rather than compounding. It
demonstrates duration, checkpointing, resume and budget enforcement, not error
compounding across dependent steps. Supersession detection is what would change
that: assessing each item against accumulated state makes item N depend on items
1..N-1, and turns the run into a genuine chain.
