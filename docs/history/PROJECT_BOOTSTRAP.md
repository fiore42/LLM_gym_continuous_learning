# Autonomous AI Research Analyst
## Codex Bootstrap Document

> Historical document. The current sources of truth are the top-level
> [ROADMAP.md](../../ROADMAP.md), [CONTRACTS.md](../../CONTRACTS.md), and
> [EVAL_METHOD.md](../../EVAL_METHOD.md).
> Status statements and next steps below are preserved as they were during the
> bootstrap phase and are not maintained as current project claims.

[Project rules](../../PROJECT_RULES.md)
[Loop architecture](../../LOOPS.md)
[Finite agentic-loop roadmap](../../ROADMAP.md)
[Evaluation method](../../EVAL_METHOD.md)
[Time-windowed significance digests](../../DIGESTS.md)

> Canonical starting point for continuing this project locally in Codex.

## Current implementation status

The project has a working deterministic YouTube/X ingestion worker, durable
incremental state, a daily-style ingestion-to-index update command, and a
searchable evidence index containing 1,645 evidence records and 193,802
timestamp-aware chunks. The query retrieval/checkpoint slice works. Full model
answer synthesis is now behind provider-neutral clients and a bounded runner;
classification and A/B benchmark scaffolding are implemented. Live provider
validation remains the next step. MCP exposure, automatic scheduling, and
automated project improvement are deliberately deferred. The finite execution
order is maintained in [ROADMAP.md](../../ROADMAP.md); future sessions should use
that file as the handoff source of truth.

The deterministic/stochastic boundary is explicit: deterministic software
handles scheduling, ingestion, indexing, retrieval, citations, checkpoints,
budgets, stopping rules, and evaluation; model prompts are reserved for
synthesis and semantic interpretation behind versioned, testable interfaces.

---

## 1. Project Goal

Build a small but convincing experimental platform for exploring the engineering principles behind trustworthy long-running AI agents.

The immediate objective is **not** to build the best research assistant or a production-grade autonomous system.

The immediate objective is to create a functioning, interesting system in approximately **10–14 hours of work** that:

- works end to end,
- is easy to demonstrate,
- supports meaningful evaluation,
- produces useful engineering insights,
- and creates strong technical topics for the next project review.

The AI Research Analyst is the first application used to exercise these ideas. The underlying design should remain transferable to other domains involving evidence collection, reconciliation, prioritization, reporting, and eventually controlled action.

If the initial milestone is completed early, continue with the next release in the roadmap rather than expanding the current release in multiple directions.

---

## 2. Core Problem

Modern language models can solve increasingly complex tasks, but reliability becomes the limiting factor as tasks:

- run for longer,
- use multiple sources,
- require multiple reasoning steps,
- call tools,
- resume after interruption,
- or make autonomous decisions.

This project explores practical techniques for making such systems progressively more reliable through measurement rather than intuition.

The emphasis is on engineering discipline, traceability, and learning velocity rather than feature count.

---

## 3. Current Product Concept

The system should become a continuously updated AI engineering research repository and analyst.

It should ingest material from:

- YouTube videos,
- X posts,
- videos embedded in X posts,
- pdfs embedded or linked in X posts,
- and, later, other trusted public sources.

It should answer AI-related questions using only ingested evidence, with clear citations back to the original source URLs.

The long-term system may also:

- detect novelty,
- identify contradictions,
- estimate confidence,
- surface missing evidence,
- prioritize future research,
- and run continuously with minimal supervision.

These later capabilities must not be introduced before the underlying retrieval, evaluation, and traceability are reliable.

---

## 4. Original Success Criteria for the 10–14 Hour Milestone

This was the original target for the first release. The current code has
completed the ingestion foundation, dual-platform source handling, evidence
normalization, chunked retrieval, deterministic library updates, provider-
neutral synthesis, bounded retries, resumable checkpoints, and initial evals.
Live provider validation, MCP, UI, and installed scheduling remain.

By the end of the first working milestone, the project should:

- ingest both YouTube and X source material,
- preserve the full original URL for every source,
- download audio files directly whenever the platform allows,
- download transcript files directly whenever the platform allows,
- download video files and convert them to audio if necessary,
- extract or generate subtitles/transcripts if not directly available from the platform,
- normalize content into a common evidence format,
- answer questions with source citations,
- expose retrieved evidence with timestamp locators,
- return an explicit insufficient-evidence state,
- return an explicit human-review state for unresolved conflicts,
- run a small reproducible evaluation suite (binary evals),
- and provide a simple UI suitable for demonstration.

A small, reliable system is preferred over a larger but fragile one.

---

## 5. Engineering Principles

- Evaluation precedes optimization.
- Introduce one meaningful capability per release.
- Aim for one engineering lesson per release.
- Prefer deterministic workflows before autonomous behavior.
- Human review is a design feature, not a failure.
- Every important output must be traceable to evidence.
- Every experiment must be reproducible.
- Every architectural change should be reversible.
- Do not add complexity unless it improves measured performance or learning.
- Preserve raw source metadata even if downstream representations change.
- Never discard the canonical source URL.
- Do not silently resolve conflicting evidence; surface it for review.

---

## 6. Source Ingestion Requirements

### 6.1 Universal source metadata

Every ingested source must retain:

- `source_id`
- `platform`
- `source_type`
- `canonical_url`
- `author_or_channel`
- `title`
- `published_at`, if available
- `ingested_at`
- `language`, if detectable
- `transcript_method`
- `media_origin`
- `content_hash`
- `raw_metadata_path`
- `transcript_path`

`canonical_url` must contain the complete original YouTube or X URL and must be used in citations.

Never cite a local filename instead of the original public URL.

### 6.2 YouTube ingestion

For every YouTube URL:

1. Save the complete original URL and metadata.
2. Attempt to download existing subtitles or captions first.
3. Prefer creator-provided subtitles when available.
4. If only auto-generated YouTube subtitles are available, preserve that fact in metadata.
5. If no usable subtitles are available:
   - download audio when available,
   - transcribe the audio locally,
   - save the generated transcript,
   - record the transcription model and method.
6. If the video is shorter than the configured short-video threshold and has
   no usable audio or produces empty subtitles, retain the video, capture
   screenshots at the configured interval, and record a terminal warning
   instead of treating the missing transcript as a failure.
7. Delete temporary media artifacts that are no longer needed.
8. Retain the audio file only when required for reproducibility or debugging; otherwise allow cleanup after successful transcription.
8. Chunk the transcript while preserving timestamp ranges when available.

Recommended fallback order:

```text
Creator subtitles
→ YouTube auto-captions
→ Audio-only download
→ Local transcription
```

### 6.3 X post ingestion

For every X post URL:

1. Save the complete original post URL.
2. Extract:
   - post text,
   - author,
   - publication timestamp,
   - thread context when accessible,
   - quoted-post context when relevant,
   - links,
   - attached media metadata.
3. If the post contains a video:
   - first attempt to obtain captions or transcript data directly from X or the media metadata,
   - if usable captions are unavailable, download the media in the most storage-efficient way available,
   - extract audio and transcribe it locally,
   - save the transcript and record whether it came from X or local transcription,
   - if the video is shorter than the configured threshold and has no usable audio or produces empty subtitles, retain the video and capture screenshots at the configured interval as a terminal warning.
4. If the post contains a document attachment (like pdf):
   - download the pdf
   - convert to text, including description of tables and images
   - record how the information was extracted from the document 
5. Keep the X post text, optional video transcript, optional attached document as linked but distinct source components.
6. Preserve references to quoted or parent posts where required to understand the source.
7. Do not treat engagement metrics as evidence quality signals unless explicitly added and evaluated later.

Recommended fallback order for X video:

```text
Native X captions/transcript
→ Extract audio and document from media stream
→ Local transcription
```

### 6.4 Storage policy

The project must minimize disk usage.

Rules:

- Do not retain downloaded video by default. The shared exception is a video
  shorter than the configured threshold with no usable audio or speech: retain
  the video and five-second screenshots as a terminal warning for visual
  inspection.
- Prefer subtitle extraction over media download.
- When media is required for transcription, retain audio only after processing;
  retain short no-audio fallback video as described above.
- Store transcripts as text or structured JSON.
- Store source metadata separately from transcript text.
- Use hashes to avoid duplicate downloads.
- Make cleanup idempotent and safe.
- Never delete the canonical URL or source metadata.
- Log temporary-file deletion failures.

### 6.5 Citation policy

Every answer must cite the original full URL.

For transcript-derived evidence, citations should preferably include:

- original URL,
- source title,
- author or channel,
- timestamp or time range when available.

Example internal citation record:

```json
{
  "canonical_url": "https://www.youtube.com/watch?v=...",
  "title": "Example title",
  "author_or_channel": "Example channel",
  "start_seconds": 312,
  "end_seconds": 346,
  "chunk_id": "yt_example_0007"
}
```

For X:

```json
{
  "canonical_url": "https://x.com/example/status/...",
  "author_or_channel": "@example",
  "published_at": "2026-08-05T...",
  "component": "post_text_or_video_transcript",
  "chunk_id": "x_example_0003"
}
```

If the system cannot support timestamp-level citations in the first milestone, URL-level citations are acceptable, but the data model must preserve room for timestamps later.

---

## 7. MVP Scope

The MVP should be achievable quickly and intentionally contains limited autonomy.

### Deliver

- Local configuration file containing selected YouTube and X URLs.
- YouTube ingestion with subtitle-first and audio-transcription fallback.
- X post text ingestion.
- X-video audio extraction and transcription fallback.
- Canonical metadata model shared across both platforms.
- Simple normalization into a common document schema.
- Basic chunking.
- Basic retrieval.
- Citation-aware question answering.
- Explicit CONFLICTING_EVIDENCE for materially different claims within the
  supplied retrieved evidence.
- Explicit `INSUFFICIENT_EVIDENCE`.
- Explicit `HUMAN_REVIEW_REQUIRED`.
- Five representative evaluation cases.
- Simple Streamlit interface.
- Experiment ledger.
- Git repository with small commits.

### Do not build yet

- autonomous source discovery,
- installing an operating-system scheduler (the update command already exists),
- browser automation beyond what is required for ingestion,
- multi-agent systems,
- self-modifying prompts,
- knowledge graphs,
- autonomous planners,
- production deployment,
- sophisticated vector infrastructure.

The initial source list may be manually curated.

---

## 8. First Milestone Work Plan

Target total: approximately **10–14 hours**.

### Step 1 — Repository and schemas
Estimate: 1 hour

- Initialize repository.
- Create source and transcript schemas.
- Add `.env.example`.
- Add storage folders.
- Add a small manually curated source manifest.

### Step 2 — YouTube ingestion
Estimate: 2–3 hours

- Implement metadata extraction.
- Attempt subtitle download.
- Add audio-only fallback.
- Add transcription fallback.
- Confirm no video is retained.
- Persist canonical URL and transcript provenance.

### Step 3 — X ingestion
Estimate: 2–3 hours

- Extract post text and metadata.
- Detect attached video.
- Attempt native caption extraction where possible.
- Add audio-only extraction and transcription fallback.
- Persist canonical URL and media provenance.

X access can be operationally fragile because of authentication, rate limits, and platform changes. If direct X extraction blocks progress, implement a clean adapter interface and support manually supplied exported post content plus media URL as a temporary human-assisted fallback. Record this limitation transparently.

### Step 4 — Normalization and retrieval
Estimate: 1.5–2 hours

- Normalize both platforms into one internal schema.
- Chunk content.
- Build simple lexical or lightweight semantic retrieval.
- Return source metadata with each retrieved chunk.

### Step 5 — Answering and citations
Estimate: 1–1.5 hours

- Generate answers from retrieved evidence.
- Include canonical source URLs.
- Add insufficient-evidence behavior.
- Add conflict/human-review behavior.

### Step 6 — Eval suite and UI
Estimate: 2–3 hours

- Add five representative eval cases.
- Add repeated-run consistency check.
- Build Streamlit UI:
  - source ingestion status,
  - question input,
  - answer,
  - citations,
  - retrieved chunks,
  - eval results.
- Record baseline results.

If time becomes constrained, prioritize in this order:

1. correct metadata and URLs,
2. YouTube ingestion,
3. X text ingestion,
4. cited Q&A,
5. evals,
6. X-video fallback,
7. UI polish.

---

## 9. Evaluation Suite

The first suite should include at least:

### Control case

A factual question with one clear answer supported by one source.

### Cross-source synthesis

A question requiring evidence from both a YouTube transcript and an X post.

### Missing evidence

A question not answered by the corpus. Expected result: `INSUFFICIENT_EVIDENCE`.

### Conflicting evidence

Two supplied sources make materially different claims. Expected result:
classify the result as CONFLICTING_EVIDENCE, explain the disagreement, and
avoid claiming that the entire corpus or field is in conflict. Unresolved work
may still return HUMAN_REVIEW_REQUIRED.

### Citation integrity

A question whose answer must contain only URLs actually retrieved and used.

### Optional consistency test

Run the same test multiple times and measure:

- answer agreement,
- citation agreement,
- decision-state agreement.

Track:

- retrieval quality,
- citation correctness,
- unsupported-claim rate,
- insufficient-evidence accuracy,
- human-review accuracy,
- consistency across runs,
- latency,
- cost,
- ingestion success rate,
- transcription fallback rate.

---

## 10. Release Roadmap

Each release should add one discrete capability.

The following sequence is authoritative for the current project. Older release
labels below are retained as historical context and must not override it.
Targeted retries, budget accounting, resumable checkpoints, and matched
provider decoding settings, offline regression coverage, and corpus-benchmark
construction are implemented; live corpus-grounded provider validation is the
next open step:

1. Create and review 5–10 benchmark cases, including a small holdout, from the
   local evidence index.
2. Run one complete bounded synthesis task against a configured provider and
   inspect its trace.
3. Validate four essential boolean evaluations: evidence relevance, claim
   support, citation validity, and answer completeness.
4. Categorize failures, label a representative sample, then run every case
   three times and record retries, costs, stopping, and escalation behavior.
5. Fix issues revealed by live runs and rerun all regression tests.
6. Optionally A/B test an open-weight model against a frontier model on
   identical tasks and evidence using `scripts/eval_compare_model_providers.py`.
7. Install scheduling for the deterministic library-update worker.
8. Add evidence pre-filtering or extraction only when measured failures justify
   it.
9. Implement the roadmap-driven project-improvement loop only after the agent
   task passes repeated-run validation.
10. Add MCP only after the task loop is evaluated and resumable.

### v0.1 — Working dual-platform ingestion foundation — achieved
Feasibility: 100%
Estimate: 10–14 hours total

- manually curated YouTube and X sources,
- subtitle-first ingestion,
- audio transcription fallback,
- task synthesis, MCP, UI, and installed scheduling remain future work for
  this historical v0.1 release; the current task harness and initial eval
  harness are documented above and in EVALS.md.

### v0.2 — Evidence foundation — achieved
Feasibility: 100%
Estimate: 2–4 hours

- common evidence records linked to YouTube/X source items,
- timestamp-aware retrieval and citations,
- the evidence index and timestamp-aware retrieval foundation.

### v0.3 — Reliable bounded agentic task — next
Feasibility: 100%
Estimate: 3–5 hours

- one evidence-backed technology-brief task,
- explicit task stages, quality gates, budgets, and stopping rules,
- targeted retries when evaluation criteria fail,
- cache reuse for unchanged inputs and versions,
- human escalation when quality cannot be reached,
- 5–10 human-labelled cases from a frozen local evidence snapshot,
- four essential boolean evaluations,
- one live task followed by three repeated runs,
- explicit revision, stopping, and escalation evidence.

### v0.4 — Optional measured model/retrieval improvement
Feasibility: 100%
Estimate: 3–6 hours

- semantic or hybrid retrieval only where evals show a need,
- chunking and citation-boundary experiments,
- context budgeting and caching.

### v0.5 — Optional provider comparison and autonomous repetition
Feasibility: 100%
Estimate: 4–8 hours

- expose the tested loop through MCP,
- schedule incremental ingestion and research runs,
- persist run checkpoints and human-review queues.

### Deferred improvements

UI, cross-platform deduplication, advanced document extraction, source
prioritization, and ingestion performance tuning should be postponed unless a
measured evaluation or operational failure makes one of them necessary for the
agentic loop.

### v0.6 — Scheduled incremental ingestion
Feasibility: 90%
Estimate: 6–12 hours

- check selected YouTube channels and X accounts,
- ingest only new material,
- retry safely,
- avoid duplicate processing,
- produce a run report.

The lower feasibility reflects possible X access restrictions, not uncertainty about the general architecture.

### v0.7 — Durable execution
Feasibility: 100%
Estimate: 1–3 days

- persisted task state,
- pause and resume,
- idempotent steps,
- retries,
- failure isolation,
- run traces.

### v0.8 — Novelty and contradiction detection
Feasibility: 85%
Estimate: 3–6 days

- compare new content with existing knowledge,
- detect potential contradictions,
- surface uncertain findings,
- evaluate precision.

### v0.9 — Bounded research planning
Feasibility: 75%
Estimate: 1–2 weeks

- identify knowledge gaps,
- propose sources or questions,
- operate within explicit budget and stop conditions,
- require human approval for source expansion.

### v1.0 — Continuously improving research analyst
Feasibility: 65–70%
Estimate: 4–8 additional weeks

- long-running scheduled operation,
- durable memory,
- measured self-improvement,
- strict eval gates,
- auditable decisions,
- controlled human intervention.

---

## 11. Suggested Repository Structure

This is a long-term target structure, not the current implementation layout.
The current ingestion implementation uses `config/SOURCES.md`,
`config/PARAMETERS.json`, `llm_gym/**/*.py`, `scripts/*.py`, and SQLite state
under `data/` and each source directory. Do not create the YAML, retrieval, or
UI paths below unless the corresponding roadmap milestone is approved.

```text
ai-research-agent/
├── README.md
├── PROJECT_SPEC.md
├── CHECKPOINT.md
├── CHANGELOG.md
├── pyproject.toml
├── .env.example
├── config/
│   ├── sources.yaml
│   └── settings.yaml
├── data/
│   ├── raw_metadata/
│   ├── audio/
│   ├── transcripts/
│   ├── normalized/
│   └── indexes/
├── llm_gym/
│   ├── base.py
│   ├── youtube.py
│   ├── x_posts.py
│   ├── media.py
│   ├── transcription.py
│   └── cleanup.py
├── retrieval/
│   ├── chunking.py
│   ├── index.py
│   └── search.py
├── answering/
│   ├── prompts.py
│   ├── answer.py
│   └── citations.py
├── evals/
│   ├── cases.yaml
│   ├── graders.py
│   └── run.py
├── ui/
│   └── app.py
├── experiments/
│   └── ledger.md
├── scripts/
│   ├── ingest.py
│   ├── ask.py
│   └── eval.py
└── tests/
```

---

## 12. Git Workflow

- Keep `main` green.
- Use one branch per capability.
- Use one objective per pull request.
- Avoid mixing ingestion, retrieval, prompting, and UI changes in the same commit.
- Tag every release.

Commit template:

```text
feat(v0.x): short description

Hypothesis:
Change:
Eval before:
Eval after:
Trade-offs:
Next question:
```

---

## 13. Context Window Management

Treat every Codex conversation as temporary.

Avoid using the same conversation beyond approximately **50–60% of its available context window**.

Do not wait until the context is nearly full. Long contexts can reduce focus, make earlier decisions harder to locate, and increase the chance of contradictory implementation choices.

### Before starting a fresh conversation

Update the current-state section in `README.md` and the milestone tracker in
`BUILD_MCP.md` with:

1. current milestone,
2. current architecture,
3. decisions made,
4. unresolved questions,
5. files changed,
6. commands to run,
7. latest eval results,
8. known failures,
9. current Git commit or tag,
10. next single objective.

Then:

- commit the documentation checkpoint,
- start a new Codex conversation,
- ask Codex to read `README.md`, `BUILD_MCP.md`, `PROJECT_RULES.md`, and `config/STATE.md`,
- continue exactly one objective.

### Working rhythm

1. Define one hypothesis.
2. Implement one capability.
3. Run tests and evals.
4. Compare with baseline.
5. Record the learning.
6. Commit.
7. Update checkpoint.
8. Start a new chat when context utilization approaches 50–60%.

### Codex session header

```text
You are continuing the Autonomous AI Research Analyst project.

Read README.md, BUILD_MCP.md, and config/STATE.md first.

Work only on the current milestone and the next single objective.

Do not redesign the architecture unless the current objective requires it.

Preserve canonical YouTube and X URLs for every source.

Use subtitles first and audio-only transcription as fallback. Retain short
no-audio/no-speech videos with five-second screenshots under the shared
terminal-warning rule.

Run tests and evals before declaring completion.

If evals regress, stop and explain the regression.

Prefer small, reversible commits.

Do not implement future roadmap items unless the current milestone is complete and documented.
```

---

## 14. Definition of Success

Success is not measured by the number of sources or features.

The first milestone is successful if it produces:

- a working dual-platform ingestion pipeline,
- storage-efficient media handling,
- trustworthy source provenance,
- cited answers,
- reproducible evaluations,
- at least one meaningful engineering insight,
- and several informed next-step questions for discussion.

The long-term project succeeds if the system can execute progressively longer and more complex workflows while remaining measurable, resumable, explainable, and trustworthy.
