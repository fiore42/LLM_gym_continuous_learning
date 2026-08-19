# Multi-Source Ingestion Worker and MCP Build Tracker

[Project rules](PROJECT_RULES.md)
[Project contracts](CONTRACTS.md)
[Loop architecture](LOOPS.md)
[Finite agentic-loop roadmap](ROADMAP.md)
[Evaluation method](EVAL_METHOD.md)

> Historical implementation checklist. It is retained for ingestion and MCP
> provenance, but unchecked boxes below are not the current execution plan.
> [ROADMAP.md](ROADMAP.md) is authoritative for current milestones and
> [README.md](README.md) is the current project overview.

## Objective

Build a reliable YouTube and X ingestion worker, then use its evidence
repository to demonstrate a resumable research agent. The agent must complete
a multi-step task, assess its own output, retry failed quality checks within
explicit budgets, stop under deterministic rules, and escalate unresolved work
to a human before it is exposed through MCP.

The finite first target is documented in [ROADMAP.md](ROADMAP.md): a single
bounded research task over a fixed local evidence snapshot. MCP, scheduling,
and automated project improvement are deferred until that task has passed
live and repeated-run validation.

The worker accepts the configured source manifest and globally configured maximum time window, discovers YouTube videos and X posts deterministically, downloads configured media/documents, falls back to local Whisper transcription when necessary, and records explicit success, warning, or failure for every content item.

## Current status

- Project state: local YouTube+X evidence library plus bounded answer,
  retrieval-retry, evaluation, provider-comparison, and digest workflows
- Current milestone: M6.2 human audit of selected digest decisions is complete;
  11 of 18 in-scope claims were fully supported by mapped evidence
- Current objective: use the seven incomplete claim mappings to define a narrow
  claim-grounding prompt hypothesis, then evaluate it on a fresh holdout
- MCP status: not started; intentionally deferred until the worker contract is stable

### Execution boundary

- Deterministic: scheduling, ingestion, state, indexing, retrieval, citations,
  checkpoints, and evaluation scoring.
- Stochastic: model-based synthesis, semantic extraction, query expansion,
  and conflict interpretation. These calls must be versioned, logged, and
  validated by deterministic stages.

## Decisions

- Build a local Python worker before building MCP.
- Keep downloading/transcription logic outside the Skill and MCP layer.
- Use subtitle-first processing.
- Treat a content item as complete when all required artifacts succeed; short no-audio/no-speech videos are terminal warnings with retained video and periodic screenshots.
- Preserve the canonical source URL and source-specific content ID.
- Do not pass plaintext account passwords through tool inputs or command-line arguments.
- Prefer browser-cookie authentication or a protected cookie file for authenticated downloads.
- Keep temporary audio only until transcription succeeds; retain it on failure for debugging.
- Use application-owned state rather than relying only on `yt-dlp --download-archive`.
- Maintain one append-only, redacted, machine-readable run log covering scripts, prompts, worker stages, and future MCP calls.
- The ordering policy will be explicit. The default for ingestion will be oldest-first within the cutoff window; newest-first can be added as an option.

## Milestones and acceptance criteria

### 1. Content-item ingestion — complete for the current worker

- [x] Metadata discovery
- [x] Subtitle-first download attempt
- [x] Audio fallback
- [x] WhisperX invocation
- [x] Non-empty, non-whitespace transcript validation
- [x] Completion marker written only after a valid transcript is finalized
- [x] Structured result and JSONL run logging
- [x] Unit tests without network access
- [x] Live smoke test with one permitted YouTube URL (`G2B0YWuJUgI`)
- [x] Live WhisperX fallback test (`Uvl-tRga98g`)
- [x] X post text, media, documents, and caption/transcription fallback
- [x] Short no-audio/no-speech video retention with five-second screenshots

### 2. Multi-source discovery

- [x] YouTube Data API adapter for channel uploads and publication dates
- [x] Enumerate channel videos without downloading media
- [x] Enforce the globally configured maximum ingestion cutoff from `config/PARAMETERS.json`
- [x] Capture stable video IDs, URLs, titles, and publication timestamps
- [x] Enrich flat-playlist entries with per-video metadata when dates are missing
- [x] Normalize channel URLs to the `/videos` tab
- [x] Stop scanning once the newest-first channel listing reaches the cutoff
- [x] Sort deterministically
- [x] Add discovery tests
- [x] Add one live smoke test (`@claude`, 12 videos found)
- [x] Add API live smoke test (`@claude`, 22 videos found)
- [x] Discover configured X accounts through the X API
- [x] Apply incremental since/latest-terminal state to YouTube and X
- [x] Provide one incremental ingestion → index update command

Environment configuration is loaded from the project `.env` file without printing secret values. Run `scripts/check_environment_configuration.py` to verify it.

### 3. Source ingestion

- [x] Combine discovery with `ingest_one_video`
- [x] Add per-video result records
- [x] Add retry behavior
- [x] Produce a channel-level run summary
- [x] Produce source-level reports and a combined multi-source report
- [x] Record estimated X API cost and downloaded X asset counts

### 4. Durable state and consistency

- [x] Add SQLite state for video status and attempts
- [x] Prevent completed videos from being reprocessed unnecessarily
- [x] Retry failed subtitle/audio/transcription stages on rerun
- [x] Use `video_id` in every media/transcript artifact filename
- [x] Store content under publication-date folders: `videos/YYYYMMDD_<content-id>`
- [x] Complete the one-time migration to the date-prefixed layout; retain the audit report
- [x] Reuse existing artifacts before invoking another download
- [ ] Add channel/run tables and resume interrupted runs
- [x] Add a central SQLite source registry for YouTube channels and X accounts
- [x] Use the latest successful publication timestamp for implicit incremental runs
- [x] Use the globally configured default window for sources with no successful history
- [x] Skip content already marked successfully downloaded, including explicit windows
- [x] Check per-source YouTube state against the central registry in both directions
- [x] Normalize equivalent source URL forms before using them as registry keys

### 5. Multi-source operation

- [x] Read and validate a simple hand-editable Markdown source list
- [x] Derive source folders as `source/youtube/<handle>` and `source/x/<handle>`
- [x] Record subscription metadata
- [x] Process sources concurrently with a configurable download limit
- [x] Enforce a single shared transcription worker
- [x] Isolate failures per source and video
- [x] Add clear operational logs
- [x] Add the shared chronological run log with call parameters, outputs, statuses, and interruption visibility
- [x] Add credential-safe log inspection with `scripts/show_recent_run_log.py`
- [x] Keep warnings separate from failures in reports and exit status

### 6. Long-running agent task — bounded runner wired; finite validation next

- [x] Create a deterministic corpus inventory excluding audio, video, and logs
- [x] Write a versioned corpus profile for reuse by downstream analysis
- [x] Define one common evidence record for YouTube transcripts and X posts
- [x] Preserve canonical URLs plus transcript timestamps for searchable transcript chunks
- [x] Build deterministic full-text retrieval over the normalized evidence
- [ ] Extract supported document formats into evidence records
- [x] Add the bounded retrieval loop: question → retrieve → cite → classify outcome → checkpoint
- [x] Add model synthesis behind an injectable, tested interface with citation validation
- [x] Add an OpenAI-compatible environment-configured provider client
- [x] Route the synthesis CLI through the bounded runner
- [x] Create 13 reviewed frozen-evidence answer fixtures from the local index
- [x] Validate complete live provider tasks against reviewed cases
- [x] Define a task contract, output schema, budgets, and stopping rules
- [x] Add a deterministic boolean quality gate with a non-100% threshold and critical checks
- [x] Add benchmark-level completeness and unsupported-citation evaluators
- [ ] Validate the four initial real-answer evaluators: evidence relevance,
  claim support, citation validity, and answer completeness
- [x] Retry bounded task attempts when quality checks fail
- [x] Cache passing results by task input, corpus snapshot, model, prompt, and evaluator versions
- [x] Escalate unresolved tasks with a human-review package
- [x] Persist task checkpoints and stop after the configured round budget
- [x] Add a deterministic benchmark harness before allowing autonomous repetition
- [x] Add initial benchmark cases for support, insufficient evidence, and conflict
- [x] Add a builder for human-labeled cases grounded in the local evidence index
- [x] Add classification, citation, and completeness checks to benchmark results
- [x] Add repeated-run consistency and stopping-compliance metrics
- [x] Define a provider A/B benchmark: identical evidence, prompts, task limits,
  and boolean evals for one open-weight and one frontier model
- [x] Report critical failures, retries-to-pass, estimated usage cost, and stop validity
- [x] Add a runnable `scripts/eval_compare_model_providers.py` entry point
- [x] Run repeated prompt comparisons and decompose aggregate ties per case
- [x] Make live provider contact with Claude Sonnet 5 and GLM-5.2; broader
  quality conclusions remain gated on human labels

### 7. Stable CLI

- [ ] `discover`
- [ ] `run`
- [ ] `status`
- [ ] `retry`
- [ ] Document configuration and authentication

### 8. MCP façade

- [ ] Add `discover_channel_videos`
- [ ] Add `start_ingestion` returning a job ID
- [ ] Add `get_ingestion_status`
- [ ] Add `get_ingestion_report`
- [ ] Add `retry_failed_items`
- [ ] Keep MCP handlers thin and call the tested worker
- [ ] Test through MCP Inspector

### 9. Codex Skill

- [ ] Document the ingestion workflow
- [ ] Define when each MCP tool should be used
- [ ] Define failure and retry reporting
- [ ] Add explicit safety and authentication instructions

### 10. Scheduled and autonomous operation — deferred

- [x] Add idempotent incremental ingestion
- [x] Add a runnable ingestion → index update worker
- [ ] Install scheduled execution outside the MCP request lifecycle
- [ ] Add regression/evaluation reporting for scheduled runs

### 11. Project improvement loop — deferred

- [ ] Read the machine-readable roadmap and select one bounded objective
- [ ] Implement only the selected objective
- [ ] Add regression tests and run the full suite
- [ ] Run boolean project evaluations and check the overarching objective
- [ ] Optionally perform bounded code/Markdown discrepancy analysis
- [ ] Update status documentation and create a local commit
- [ ] Stop at 80% of configured time/token/cost budget and create a human escalation

## Test strategy

- Unit tests must not depend on YouTube, network access, credentials, or WhisperX runtime.
- Use injected command runners and temporary directories for deterministic tests.
- Keep live tests separate and small.
- A content item is successful only when its required artifacts are finalized; a short video with no usable audio or speech is a terminal warning with retained video/screenshots.
- Every failure must include a stage and a useful error message.
- Every run must be reconstructable from the shared redacted run log without terminal scrollback.

## Session handoff checklist

Before ending a session:

1. Update the current milestone and objective.
2. Record files changed.
3. Run the tests and record their result.
4. Record live-test results separately from unit-test results.
5. Record known failures and the next single objective.
