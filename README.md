# Autonomous AI Research Analyst

[Project rules](PROJECT_RULES.md)

A local, evidence-backed research system built to explore reliable long-running
agent workloads. It incrementally collects public YouTube and X material,
builds a citation-ready evidence index, answers bounded research questions, and
assesses time windows through checkpointed model calls with explicit cost,
retry, validation, and human-escalation boundaries.

The project demonstrates durability, provenance, retrieval adaptation, and safe
failure handling. Deep chains of dependent long-horizon reasoning and
human-validated digest ranking accuracy remain unimplemented.

<a id="readme-index"></a>
## Index

- [How to explore this project](#explore-project)
- [Project at a glance](#project-at-a-glance)
- [What the live artifacts demonstrate](#live-artifacts)
- [Architecture](#architecture)
- [Normal workflows](#normal-workflows)
  - [Update the knowledge base](#update-knowledge-base)
  - [Query the knowledge base](#query-knowledge-base)
  - [Answer a research question](#answer-research-question)
  - [Run a long time-window digest](#run-digest)
  - [Run evaluations](#run-evaluations)
- [How the agentic loops work](#agentic-loops)
- [Reliability and human-review boundary](#reliability-boundary)
- [Setup and configuration](#setup)
- [Repository and data layout](#repository-layout)
- [Testing and validation](#testing)
- [Current limitations and next objective](#current-limitations)
- [Documentation map](#documentation-map)

<a id="explore-project"></a>
## How to explore this project

Start with the evidence produced by the system rather than the repository
layout. These commands are read-only, make no model calls, and cost nothing.
The digest reader intentionally returns a nonzero exit status for an incomplete
or escalated report, even though it still displays the report for inspection.

1. **Inspect adaptive action.** Compare round 1 and round 2 in one retrieval-
   retry trace. The trace shows the thin initial evidence, model-proposed query,
   changed evidence set, and second synthesis.

   ```bash
   .venv/bin/python -m json.tool data/runs/trigger-measurement/agent/what_are_evals-rep-1.json | less
   ```

2. **Inspect durable breadth.** Read the 30-day stress report summary and its
   significant items. The run attempted a 328-item frozen window under
   checkpoints and budgets, retained accepted work, and ended
   `ESCALATED_FOR_REVIEW` rather than presenting incomplete work as success.

   ```bash
   .venv/bin/python scripts/show_digest.py data/digests/2026-07-08-to-2026-08-07-youtube-glm-5.2-open-weight-report.json
   ```

3. **Inspect evidence grounding.** Show significance-v2 summaries with the one
   to three verbatim passages that deterministic code located in each source
   before accepting the judgement.

   ```bash
   .venv/bin/python scripts/show_digest.py data/digests/2026-07-31-to-2026-08-07-youtube-glm-5.2-open-weight-significance-v2-report.json --quotes
   ```

4. **Inspect safe failure.** Show the v2 report's rejected items. Bounded
   retries recovered some invalid responses and escalated the three that still
   could not satisfy the evidence contract.

   ```bash
   .venv/bin/python scripts/show_digest.py data/digests/2026-07-31-to-2026-08-07-youtube-glm-5.2-open-weight-significance-v2-report.json --rejected
   ```

5. **Inspect the human-review boundary.** Open the completed 20-card audit.
   The reviewer—not a second uncalibrated model—found two out-of-scope
   selections and only 11 of 18 in-scope summaries fully supported by their
   mapped passages.

   ```bash
   .venv/bin/python -m json.tool data/human-labels/digest-claim-audit-v1/glm-5.2-audit-report.json | less
   ```

Current status is split across two implemented paths: the digest provides
durable, resumable breadth, while the adaptive retrieval trace provides a
dependent agentic loop of depth two. Deep chains of dependent reasoning remain
outside the demonstrated scope.

[Back to index](#readme-index)

<a id="project-at-a-glance"></a>
## Project at a glance

| Capability | Current state |
|---|---|
| YouTube and X ingestion | Operational: incremental discovery, publication-date storage, transcript/media fallbacks, durable state |
| Evidence index and retrieval | Operational: stable evidence IDs, full-text search, timestamp locators, canonical URLs, corpus signatures |
| Bounded cited-answer task | Run live: draft, deterministic evaluation, targeted retry, checkpoint, cache, budget, escalation |
| Adaptive retrieval loop | Run live: a thin first result can trigger model-proposed queries, deterministic retrieval, and a second synthesis |
| Time-window digest | One-day and seven-day runs completed; the 30-day stress run escalated with unresolved validation failures |
| Provider comparison | Claude Sonnet 5 and GLM-5.2 run against the same small retrieval-loop workload |
| Human semantic calibration | First selected-decision audit complete: 20 cards, 18 in scope, 11 fully supported summaries, six partially supported, one unsupported; independent atomic ground truth remains deferred |
| Scheduling, UI, MCP, autonomous remediation | Deliberately deferred |

Two responsibilities stay separate:

- **Deterministic code** owns discovery, state, indexing, retrieval, citations,
  budgets, checkpoints, cache keys, validation, stop decisions, and exit codes.
- **Models** perform synthesis, semantic extraction, evidence assessment, and
  query expansion behind immutable, versioned prompts.

This boundary matters because a model may suggest what to do next, but ordinary
code decides whether the evidence, budget, and validation contract permit it.

[Back to index](#readme-index)

<a id="live-artifacts"></a>
## What the live artifacts demonstrate

| Artifact | Observed result | What it demonstrates | What it does not demonstrate |
|---|---|---|---|
| [Seven-day GLM-5.2 digest](data/digests/2026-07-31-to-2026-08-07-youtube-glm-5.2-open-weight-report.json) | Provisional single arm: 49/49 items assessed, zero rejected | Dozens of bounded units, per-item grounding, checkpointed long workload | Human-validated significance accuracy or dependent reasoning |
| [Seven-day significance-v2 digest](data/digests/2026-07-31-to-2026-08-07-youtube-glm-5.2-open-weight-significance-v2-report.json) | Provisional single arm: 46/49 accepted after 75 provider calls; three escalated; $0.4217194 | Multi-passage evidence grounding, bounded validation repair, truthful escalation | A complete window or human-validated significance quality |
| [Human audit of selected v2 decisions](data/human-labels/digest-claim-audit-v1/glm-5.2-audit-report.json) | 20 cards: 18 in scope; summary evidence 11 full, 6 partial, 1 unsupported; reason evidence 15 full, 3 partial; exact blind labels 8/18 | The main measured semantic failure is summary-to-evidence completeness; two selections were out of scope | Missed findings, recall, corpus-level ranking quality, or an independent quality benchmark |
| [Thirty-day GLM-5.2 stress report](data/digests/2026-07-08-to-2026-08-07-youtube-glm-5.2-open-weight-report.json) | Provisional single arm: 328 selected, 321 accepted, 10 historical rejection records, escalated | Failures remain visible; incomplete work is not presented as success | A clean 30-day completion; legacy request/token figures are lower bounds |
| [Claude retrieval-trigger summary](data/runs/trigger-measurement/agent/summary.json) and [GLM summary](data/runs/trigger-measurement/open_weight/summary.json) | Two cases × three repetitions per model; both arms exercised retrieval expansion | The loop can observe thin evidence, change the query, and receive a changed evidence state | A general quality ranking between providers |
| [Prompt comparison](data/eval-comparison-synthesis-v5-vs-synthesis-v6.json) | 13 frozen cases × three repetitions per prompt; both arms scored 33/39 | Repeated frozen-input measurement and saturation detection | Semantic equivalence between prompts or evidence about the current latest prompt |

Current project status: a durable long-running breadth workload operates beside
a two-round adaptive retrieval loop. The first provides checkpointing, budget
enforcement, recovery, and inspectability; the second observes weak evidence
and changes its next action.

[Back to index](#readme-index)

<a id="architecture"></a>
## Architecture

```text
YouTube / X
    │
    ▼
incremental ingestion ──► authoritative source registry
    │
    ▼
transcripts, posts, attachments
    │
    ▼
derived evidence index ──► deterministic retrieval ──► evidence checkpoint
                                                     │
                     ┌───────────────────────────────┴─────────────────────┐
                     ▼                                                     ▼
              bounded answer task                                  time-window digest
        draft → evaluate → revise/stop                       one bounded unit per item
                     │                                                     │
                     └──────────► cited result or human review ◄───────────┘
```

The main runtime package is divided by responsibility:

```text
llm_gym/
  sources/   source adapters, ingestion state, storage, discovery
  corpus/    evidence normalization, indexing, retrieval, window freezing
  agent/     synthesis, retrieval retry, task runner, digest, model clients
  shared/    configuration, atomic writes, logging, status and loop utilities
```

Prompt definitions live under `prompts/` as immutable JSON. The highest
version is the default; older versions remain selectable for controlled
comparisons. Answer-task traces retain the full rendered prompt. Digest reports
retain the immutable prompt version and hash plus source-item identity; the
rendering is reproducible locally from that template and source text without
duplicating every transcript into every checkpoint.

[Back to index](#readme-index)

<a id="normal-workflows"></a>
## Normal workflows

You do not normally run every file under `scripts/`. The common paths are
listed below; [scripts/README.md](scripts/README.md) indexes every entry point.

<a id="update-knowledge-base"></a>
### Update the knowledge base

The normal ingestion entry point fetches only new material, refreshes the
derived evidence index, and records a durable update checkpoint:

```bash
.venv/bin/python scripts/ingest_update_library_incrementally.py \
  --browser firefox \
  --max-downloads 3
```

Use `ingest_all_configured_sources.py` for the configured source workflow or a
channel-specific script when diagnosing one source. Source subscriptions are
defined in [config/SOURCES.md](config/SOURCES.md); time and concurrency limits
come from [config/PARAMETERS.json](config/PARAMETERS.json).

<a id="query-knowledge-base"></a>
### Query the knowledge base

Search the local evidence index without a model call or provider cost:

```bash
.venv/bin/python scripts/corpus_search_evidence_index.py \
  "agent memory" \
  --limit 10
```

Each result carries a stable evidence ID, source URL, local artifact path,
and—where available—a transcript timestamp locator. Retrieval finds evidence;
it does not synthesize an answer or establish that a source is true.

<a id="answer-research-question"></a>
### Answer a research question

First retrieve a bounded evidence checkpoint. This step is deterministic and
free:

```bash
.venv/bin/python scripts/agent_retrieve_evidence_for_question.py \
  "How do agents use memory?"
```

Then optionally synthesize and evaluate a cited answer. This step calls the
configured provider and costs money:

```bash
.venv/bin/python scripts/agent_run_task_on_checkpoint.py \
  --model claude-sonnet-5
```

The output includes attempts, evaluation results, citations, complete supplied
evidence, model usage, stop reason, prompt provenance, and any human-review
package. Repeating identical inputs can reuse the cache; `--force` on retrieval
creates a fresh evidence checkpoint.

<a id="run-digest"></a>
### Run a long time-window digest

Use this path for “what changed recently?” rather than a question known in
advance. Freeze the corpus window first so every later comparison uses the same
items and index signature:

```bash
.venv/bin/python scripts/corpus_freeze_digest_window.py \
  --days 7 --platform youtube --dry-run

.venv/bin/python scripts/corpus_freeze_digest_window.py \
  --days 7 --platform youtube
```

Estimate input size without a model call, then run the paid workload:

```bash
.venv/bin/python scripts/agent_run_digest.py \
  --snapshot data/digest-windows/<window>.json \
  --estimate

.venv/bin/python scripts/agent_run_digest.py \
  --snapshot data/digest-windows/<window>.json \
  --model glm-5.2 \
  --provider-prefix OPEN_WEIGHT
```

Each item is one independently checkpointed assessment unit. A rejected model
response uses one retry by default; `--max-item-retries` permits a bounded
override from zero to five. Item count and provider-request count are reported
separately. Kill the process and repeat the same command to resume; accepted
items are not purchased again.

Read the machine-oriented report through the human viewer:

```bash
.venv/bin/python scripts/show_digest.py \
  data/digests/<window>-<model>-<arm>-<prompt-version>-report.json \
  --quotes
```

Add `--label ALL` to inspect every assessment or `--rejected` to inspect failed
validations. A located quote proves provenance, not that the significance label
is semantically correct.

<a id="run-evaluations"></a>
### Run evaluations

The answer suite uses frozen evidence, so it measures synthesis independently
from live retrieval changes:

```bash
.venv/bin/python scripts/eval_validate_suite.py --check-retrieval
.venv/bin/python scripts/eval_run_suite.py --model claude-sonnet-5
```

Run the paid suite after changing prompts or agent behavior. Validate retrieval
expectations after every corpus update. Frozen and live-retrieval outcomes may
legitimately differ because their evidence inputs differ; [EVALS.md](EVALS.md)
defines the triage procedure.

[Back to index](#readme-index)

<a id="agentic-loops"></a>
## How the agentic loops work

The project uses several bounded loops with different purposes. A background
library-update loop is not the same thing as an answer-producing agent.

### Cited-answer revision loop

```text
retrieve evidence → draft structured answer → deterministic evaluation
                         ▲                         │
                         └──── targeted feedback ─┘
                                      │
                              finalize or escalate
```

A retry occurs only after a failed validation or quality criterion. The next
prompt includes targeted failure feedback; deterministic code decides whether
another round is allowed under the time, call, cost, and round budgets.

### Adaptive retrieval loop

```text
retrieve → synthesize and assess evidence sufficiency
                       │
             evidence is thin or incomplete
                       ▼
         model proposes focused search queries
                       ▼
 deterministic controller retrieves and merges new evidence
                       ▼
                  synthesize again
```

This is the clearest agentic example: the model observes that the current state
is inadequate and proposes a different information-gathering action. The
controller executes that action, bounds the merged evidence, and records what
changed. It is currently a two-round loop, not a deep long-horizon chain.

### Digest workload

The digest is a durable breadth workload: it maps the same bounded assessment
contract over every item in a frozen window. That makes checkpoint, resume,
budget, and failure behavior observable over many calls, but the items are
independent. It must not be presented as proof of dependent multi-step
reasoning.

See [LOOPS.md](LOOPS.md) for the full taxonomy and [CONTRACTS.md](CONTRACTS.md)
for persisted schemas and stop semantics.

[Back to index](#readme-index)

<a id="reliability-boundary"></a>
## Reliability and human-review boundary

The runtime treats reliability as a set of explicit contracts rather than a
model personality:

- inputs are frozen or corpus-signature stamped;
- cache keys include task, evidence, prompt, model, and evaluation policy;
- checkpoints persist accepted work and billed failed attempts;
- provider requests, tokens, latency, and cost describe the same work;
- budgets cap rounds, calls, elapsed time, and spend;
- citations must reference supplied evidence IDs;
- digest quotes must occur in the source text after whitespace normalization;
- incomplete or escalated paid runs return nonzero exit codes;
- failures preserve retryability, diagnostics, and artifact paths.

The boundary is equally important:

- **Provenance is not truth.** A quote may accurately represent a source whose
  underlying statement is wrong.
- **Citation validity is not complete semantic support.** Human review checks
  whether the cited passage establishes each material part of the answer.
- **Cache consistency is not model consistency.** A cache intentionally returns
  the prior validated result for identical inputs; repeated uncached runs remain
  a separate evaluation question.
- **Human judgment remains authoritative.** The judge-drafter is advisory, and
  M6.2 audits selected digest decisions without pretending that one transcript
  has one label. Independent atomic ground truth remains future work.

[Back to index](#readme-index)

<a id="setup"></a>
## Setup and configuration

Create a local environment file; secrets are ignored by Git:

```bash
cp .env.example .env
```

Configure only the providers and source adapters you intend to run. For
Anthropic synthesis:

```env
AGENT_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_anthropic_api_key
AGENT_MODEL=claude-sonnet-5
AGENT_INPUT_COST_PER_MILLION=<current provider rate>
AGENT_OUTPUT_COST_PER_MILLION=<current provider rate>
```

For GLM-5.2, configure the complete `OPEN_WEIGHT_*` arm shown in
[.env.example](.env.example). Comparison arms never inherit credentials or
settings from `AGENT_*`; silent fallback would invalidate the comparison.

Validate configuration without printing secret values:

```bash
.venv/bin/python scripts/check_environment_configuration.py
.venv/bin/python scripts/check_youtube_source_manifest.py
```

External binaries such as `yt-dlp`, `ffmpeg`, `ffprobe`, and the local Whisper
script may be configured in `.env` or through the corresponding environment
variables. Configuration precedence and global limits are documented in
[PROJECT_RULES.md](PROJECT_RULES.md).

[Back to index](#readme-index)

<a id="repository-layout"></a>
## Repository and data layout

```text
config/       Parameters, source manifest, state contracts, frozen eval suite
llm_gym/      Agent, corpus, source-adapter, and shared runtime packages
prompts/      Immutable versioned prompt families
scripts/      Human-facing CLIs; names are grouped by agent/eval/corpus/ingest/check
tests/        Network-independent regression tests
data/         Runtime state plus selected committed model-output evidence
source/       Acquired third-party content; never committed
docs/history/ Superseded plans retained for provenance
```

The authoritative source/content status is the central registry. Per-source
SQLite files are worker caches. The evidence index, reports, and checkpoints
are derived artifacts; [config/STATE.md](config/STATE.md) defines their roles.

Version-control policy follows one practical distinction:

- deterministic outputs such as the evidence index, checkpoints, caches, and
  frozen windows are reproducible and remain local;
- selected model outputs such as digest reports, live traces, comparison
  summaries, and verification drafts are committed because recreating them
  costs money and they are evidence of the experiment.

See [data/README.md](data/README.md) and [source/README.md](source/README.md) for
the exact inclusion policy and regeneration commands.

[Back to index](#readme-index)

<a id="testing"></a>
## Testing and validation

Run the complete offline verification surface:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q llm_gym scripts tests
.venv/bin/python scripts/check_markdown_rule_links.py
.venv/bin/python scripts/check_project_rules.py --check-last-commit
.venv/bin/python scripts/eval_validate_suite.py --check-retrieval
```

Offline tests use injected clients, command runners, temporary indexes, and
temporary state. Live ingestion, network smoke tests, and provider evaluations
remain separate because they require credentials, external tools, or paid
calls. Every bug fix requires a regression test and a recorded mutation check.

The evaluation hierarchy is:

1. deterministic structural and provenance checks;
2. human review and calibrated advisory judge drafts;
3. repeated frozen-case and provider/prompt comparisons;
4. live operational stress runs with explicit budgets and stop reasons.

[EVAL_METHOD.md](EVAL_METHOD.md) explains why human labels remain the reference
for semantic criteria.

[Back to index](#readme-index)

<a id="current-limitations"></a>
## Current limitations and next objective

ROADMAP M6.2 is complete. The provisional human audit sampled 20 of the 46
accepted significance-v2 decisions: 18 were in scope and two were selection
failures. Of the 18 in-scope summaries, 11 were fully supported by their mapped
passages, six were partially supported, and one was not supported. Model reasons
were fully supported for 15/18 and partially supported for 3/18. Exact blind
classification agreement was 8/18, while the reviewer considered the model's
label a reasonable alternative in all 18 cases. That combination is evidence
that the class boundary is subjective, not a 100% quality result.

The strict accepted-decision count is 11/18: full summary support, full reason
support, and an acceptable label. The central measured failure is over-broad
model summaries relative to their selected evidence—not fabricated quote text.
The canonical result is the
[human audit report](data/human-labels/digest-claim-audit-v1/glm-5.2-audit-report.json).

Newly frozen windows deterministically exclude empty or bracketed-cue-only
transcripts such as `[MUSIC PLAYING]` before any paid model call. The exclusion
count is recorded in the snapshot and freeze-command output.

The result is a provisional model-decision audit, not precision, recall, or a
gold set. The complete protocol and limitations are in
[data/human-labels/README.md](data/human-labels/README.md) and
[EVAL_METHOD.md](EVAL_METHOD.md#digest-claim-audit).

Known boundaries:

1. Digest significance labels are not calibrated against an independent
   atomic gold set; M6.2 only audits selected decisions.
2. The digest is a parallel map rather than a dependent chain.
3. The historical 30-day report is escalated and carries legacy lower-bound
   provider accounting; current code fixes the accounting for future/resumed
   work without rewriting the historical artifact.
4. There is no period-level spend ledger or notification path for scheduled
   unattended operation.
5. There is no autonomous production action, UI, scheduler, or MCP façade.

The next evaluation objective is to turn the seven incomplete evidence mappings
into a narrow prompt hypothesis, then test it on a fresh holdout rather than
reporting improvement on the 20 examples that motivated the change. Ranked
supersession, deterministic duplicate grouping, and unattended period-level
controls remain sequenced behind that evidence-contract repair. Generic
multi-agent orchestration, embeddings, automatic task decomposition, and
autonomous remediation remain deferred until measured failures justify them.

See [ROADMAP.md](ROADMAP.md) for milestones and acceptance criteria.

[Back to index](#readme-index)

<a id="documentation-map"></a>
## Documentation map

| Document | Purpose |
|---|---|
| [PROJECT_RULES.md](PROJECT_RULES.md) | Project-wide invariants and mechanical enforcement |
| [CONTRACTS.md](CONTRACTS.md) | Stable interfaces, schemas, status and compatibility contracts |
| [ROADMAP.md](ROADMAP.md) | Authoritative current milestones, completed work, and deferred scope |
| [LOOPS.md](LOOPS.md) | Loop taxonomy and separation of deterministic/stochastic responsibilities |
| [EVALS.md](EVALS.md) | Frozen-evidence suite, live-retrieval distinction, review protocol |
| [EVAL_METHOD.md](EVAL_METHOD.md) | Evaluation hierarchy, human labels, comparison and judge calibration |
| [DIGESTS.md](DIGESTS.md) | Time-window digest design and ranking-specific evaluation |
| [scripts/README.md](scripts/README.md) | Complete command index grouped by purpose |
| [config/SOURCES.md](config/SOURCES.md) | Configured source subscriptions |
| [config/STATE.md](config/STATE.md) | Authoritative versus derived state |
| [docs/history/PROJECT_BOOTSTRAP.md](docs/history/PROJECT_BOOTSTRAP.md) | Historical bootstrap plan, retained for provenance only |

[Back to index](#readme-index)
