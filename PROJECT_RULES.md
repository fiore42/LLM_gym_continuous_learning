# Project Rules

This document contains the project-wide rules for the Autonomous AI Research Analyst and its ingestion MCP. Every Markdown document in this project must reference this file using a relative link:

```markdown
[Project rules](PROJECT_RULES.md)
```

If a Markdown file is stored in a subdirectory, use the appropriate relative path, for example:

```markdown
[Project rules](../PROJECT_RULES.md)
```

Run `scripts/check_markdown_rule_links.py` to verify that this convention is still satisfied.

Run `scripts/check_project_rules.py` to enforce the rules a program can decide.
It reports violations and exits non-zero, and it also prints the rules it cannot
check, so the unenforced remainder stays visible rather than being mistaken for
compliance. Add `--check-last-commit` to apply the Rule 28 mutation-record check
to `HEAD`. A rule nothing checks becomes decoration: Rule 7 is the only rule here
that never drifted, and it is the only one that had a script behind it.

Run `scripts/check_state_registry_consistency.py` to verify that per-source YouTube
state and the central registry agree. This check is read-only with respect to
media, transcripts, and logs.

Stable interfaces and compatibility requirements are documented in
[CONTRACTS.md](CONTRACTS.md). New adapters and downstream stages must satisfy
those contracts or explicitly version and migrate them.

## Rule 0 — Keep deterministic and stochastic responsibilities separate

Deterministic code owns scheduling, ingestion, state, indexing, retrieval,
citations, checkpoints, and scoring. Prompts/models may perform synthesis,
semantic extraction, query expansion, and nuanced interpretation only. Every
stochastic call must record its model, immutable prompt version and hash, the
full rendered prompt, input evidence IDs, and output, and must remain behind a
tested interface. Prompt definitions live as append-only JSON files under
`prompts/`; never edit a historical prompt in place. The default loader uses
the highest explicit prompt version, while older versions remain selectable
for controlled comparisons.

## Rule 1 — Every testable stage gets a simple test script

For each implementation stage, create a small executable or directly runnable script that makes the relevant test easy to perform.

The script should:

- require minimal arguments;
- use safe, explicit defaults where appropriate;
- exercise the smallest useful slice of behavior;
- report a clear success or failure result;
- return a non-zero exit code on failure;
- avoid requiring users to paste inline Python, shell heredocs, or complex commands;
- document its usage in the relevant Markdown file.

Examples:

```text
scripts/smoke_test_youtube_ingestion.py
scripts/ingest_discover_youtube_channel_videos.py
scripts/check_environment_configuration.py
```

Unit tests remain necessary, but they do not replace a simple human-oriented smoke-test script for behavior that depends on external tools or services.

## Rule 2 — Scripts are interactive and observable by default

Scripts should show what they are doing and report useful progress and status by default.

Unless a script is inherently non-interactive, it should show:

- the operation being attempted;
- the input or item currently being processed;
- important stage transitions;
- success, warning, and failure messages;
- a final summary;
- the exit status implied by the result.

Every script that can reasonably be used by automation should support:

```text
--noout
```

`--noout` suppresses normal human-facing output while preserving correct exit codes and machine-readable result files. Errors may still be emitted to stderr unless a separate quiet/error-suppression option is explicitly designed and documented.

Scripts should not hide useful diagnostics by default. A user must be able to run the same command interactively and understand what is happening without inspecting source code.

## Rule 3 — Preserve machine-readable results

Human-readable output and machine-readable results are separate concerns.

Where a script performs a meaningful operation, it should produce a structured result when practical, such as JSON, JSONL, or a durable database record. `--noout` must not disable durable result recording.

## Rule 4 — Make failures explicit

Do not silently skip failures. Every failed item must include:

- the item identifier or canonical URL;
- the stage that failed;
- an actionable error message;
- whether retrying is safe;
- the relevant output or log path.

Scripts must return a non-zero exit code when the requested operation did not complete successfully.

## Rule 5 — Prefer small, reversible stages

Implement one capability at a time. Each stage should be independently runnable and testable before it becomes a dependency of the next stage.

Do not introduce MCP, scheduling, concurrency, or autonomous behavior before the underlying local operation is deterministic and tested.

## Rule 6 — Never expose secrets

Do not accept, print, persist, or log plaintext passwords, access tokens, browser cookies, or other credentials unless the specific secure storage mechanism requires it. Prefer browser-cookie authentication, environment variables, OS keychains, or protected credential files.

Never include credentials in command output, JSON results, Markdown examples, or error logs.

## Rule 7 — Update this file when the convention changes

If project-wide behavior changes, update this document first or in the same change. Every new Markdown file must link to this document before it is considered complete.

## Rule 8 — Log every outcome and distinguish warnings from failures

Every meaningful outcome at every level must be logged with the relevant item, stage, timestamp, and result.

Use these categories consistently:

- `INFO`: normal progress or successful completion.
- `WARNING`: an expected or non-actionable condition that does not require a process change, such as a channel having no new videos in the requested time window or a video having no platform subtitles before fallback processing begins.
- `HANDLED_FALLBACK`: an expected recovery path that should be visible for provenance but must not count as a failure, such as platform subtitles being unavailable and local WhisperX successfully generating subtitles.
- `FAILURE`: an unresolved problem that prevented the requested outcome or indicates that the process must change to avoid the problem in the future, such as failure to discover a channel, failure to download audio, failure to create subtitles, invalid output, or an authentication error.

Failure records must include:

- the canonical item identifier or URL;
- the failed stage;
- the failure category;
- the exact or summarized error;
- whether retrying is safe;
- the output and log paths;
- a reference to the next corrective action or process change when known.

A fallback that succeeds must produce a provenance/event record, but the overall operation remains successful. Do not inflate failure metrics with failures that were automatically handled and did not require a process change.

## Rule 9 — Content folders use publication dates

Every source adapter must store one content item under a date-prefixed folder:

```text
<source-root>/videos/YYYYMMDD_<content-id>/
```

`YYYYMMDD` must come from the content's original publication/creation timestamp, never the download timestamp. This convention applies to YouTube videos, X posts, and future source types. Use the shared storage helper rather than constructing content paths ad hoc. If the creation date is unavailable, the adapter must record an explicit warning or failure instead of silently using a download date.

The one-time migration to this convention is complete; preserve its audit report. Future adapters must use the shared storage helper and must update all persisted references when changing a content path.

An empty result is not automatically a failure. For example, “no new videos found” is a warning unless the discovery operation itself failed or the result is inconsistent with the requested inputs.

Short-video no-speech handling is global and applies to YouTube, X, and future video sources. When a video is shorter than `ingestion.short_video_max_seconds` and has no usable audio or produces empty subtitles, record a warning, retain the video, and capture screenshots every `ingestion.screenshot_interval_seconds` seconds. The item is terminal after the visual fallback completes, must not be downloaded again on normal runs, and must remain inspectable even though no transcript exists.

## Rule 10 — Load shared parameters

Operational ingestion and validation scripts must load `config/PARAMETERS.json` through `llm_gym.shared.settings`. Do not duplicate the default or maximum ingestion window, tool paths, or other global parameters in script code. The configured maximum window is enforced by both command-line entry points and library discovery functions.

For X ingestion, API credentials must come from `X_API_BEARER_TOKEN`, optional `X_API_USER_ACCESS_TOKEN`, or an equivalent protected environment/secret store. Never store tokens in source files, reports, logs, SQLite records, or committed configuration. Use the app-only bearer token for public data and retry a resource-authorization failure with the user-context token when configured; the user-context account must be the authorized follower for protected sources. Initial X ingestion must obey the global X parameters and must not add keyword/topic filtering unless explicitly approved as a separate evaluation stage. Ingestion stores the original post record before downstream classification. A post is not content-complete until its text/metadata record is saved and configured attached media, direct linked documents, and article metadata have been attempted; asset failures are explicit non-fatal warnings and must never be silently discarded. X video attachments must be transcribed from downloaded video when no valid caption artifact is available. The post remains retryable without `.complete` or a terminal registry record until transcription exits successfully with a valid non-empty subtitle file; short music-only videos may become terminal warnings under the shared no-speech rule.

Normal incremental ingestion must use the latest terminal publication cursor from the shared registry as an exclusive boundary. Re-running an adapter without new content must produce an empty discovery set and must not reprocess terminal items. A caller may bypass the cursor only with the explicit `--force` option.

## Rule 11 — Warnings never count as failures

Statuses such as `SKIPPED_*`, empty-result conditions, and handled fallbacks are warnings or successful outcomes, not failures. Shared status classification must be used for log categories, counters, and exit codes. Only unresolved `FAILED_*` outcomes or aggregate `COMPLETED_WITH_FAILURES` may produce a failure count or non-zero exit code.

## Rule 12 — Maintain one detailed run log

All scripts, prompts, worker stages, and future MCP tools must write to one project-level chronological run log. The log must make it possible to reconstruct what happened during any run without relying on terminal scrollback.

Each event should include, where applicable:

- a unique `run_id` and `event_id`;
- timestamp with timezone;
- parent event or operation identifier;
- caller, script, prompt, worker, or MCP tool name and version;
- the complete effective parameters after defaults were applied;
- source/item identifiers and canonical URLs;
- stage and event category (`INFO`, `WARNING`, `HANDLED_FALLBACK`, or `FAILURE`);
- start time, end time, and duration when an operation was executed;
- exit status or structured result status;
- captured output, error output, and references to larger output files;
- relevant artifact, report, and log paths.

Use a durable, append-only, machine-readable format such as JSONL or SQLite, with human-readable summaries generated from it when useful. `--noout` may suppress terminal output but must never suppress run-log events. Log prompts and tool parameters sufficiently to reproduce the call, while applying Rule 6: secret values must never be stored in the run log. Passwords, API keys, access tokens, cookies, authorization headers, and equivalent credentials must be omitted or replaced with a non-secret marker before the event is written. It is acceptable to record that a credential was supplied and which secure mechanism or parameter name was used.

Every top-level run must record its start, every attempted call and returned result, every warning or handled fallback, every unresolved failure, and its final summary. If a process exits unexpectedly, the log must retain the last started operation so the interruption is diagnosable.

## Rule 13 — Do not silently omit configured sources

Every configured source must either be handled by a registered source adapter or produce an explicit, actionable unsupported-source result. Scripts must never silently ignore a configured source.

## Rule 14 — Preflight external dependencies

Before starting ingestion, validate required executables, compatible versions, model assets, credentials, and writable directories. Fail early with actionable diagnostics when a prerequisite is unavailable.

External tools must be discovered or configured portably. Do not hard-code developer-specific absolute paths; provide documented environment or parameter overrides where appropriate.

## Rule 15 — Normalize and validate time

All timestamps used for discovery, filtering, storage, and reporting must be timezone-aware and normalized to UTC. Inclusive and exclusive boundary semantics must be documented and covered by tests. Reject invalid ranges such as `since > until` before starting work.

## Rule 16 — Use atomic, verifiable completion

An item may be marked complete only after its required artifacts, completion marker, and persistent state have been committed successfully. Writes must be atomic where interruption could create a false completion, and rerunning an interrupted item must be safe.

## Rule 17 — Use explicit state machines

Statuses must be finite, documented, and have defined retryability and terminal-state semantics. Retry only retryable states. Terminal success and skip states must be independently verifiable, and state updates must be idempotent.

Provider errors must retain sanitized diagnostics and explicit retryability.
Do not spend repeated model calls on non-retryable request errors or label them
as quality failures.

Do not treat terminal failed checkpoints as resumable progress. Resume only
explicitly `RUNNING` work; retrying a terminal failure must create a new run
identity and preserve the prior result as history.

## Rule 18 — Require regression tests for fixes

Every bug fix must add or update a regression test covering the failure. Before considering a change complete, run the full relevant test suite plus compile, configuration, manifest, and applicable smoke tests. Do not ship a change with a known regression.

## Rule 19 — Version persisted schemas

SQLite schemas, persisted JSON structures, and status meanings must be versioned. Changes require explicit, backward-compatible migrations and a documented recovery or rollback path. Never change the meaning of existing data silently.

Derived retrieval indexes and cached answers must also be versioned. When
retrieval SQL, tokenization, ranking, chunking, or snippet semantics change,
increment the retrieval index version, rebuild derived tables, and invalidate
dependent checkpoints automatically. Preserve the collected source and
evidence records.

## Rule 20 — Protect concurrent shared state

Shared databases, logs, reports, and progress output must be safe under concurrent workers. Worker counts must be bounded, aggregation must be deterministic, and one worker's failure must not corrupt or hide another worker's result.

## Rule 21 — Protect immutable source identity

Content identity must be scoped to its source and remain immutable. Detect and record duplicate IDs, changed canonical URLs, publication-date changes, and folder collisions instead of silently overwriting content or metadata.

## Rule 22 — Define configuration precedence

The precedence among command-line arguments, environment variables, global parameters, manifest values, and stored incremental state must be documented and enforced. The effective configuration and time bounds must be recorded for each top-level run. Invalid combinations must be rejected before work begins.

## Rule 23 — Bound operational observability

Operational logs must be structured, redacted, and bounded in size. Detailed diagnostics belong in reports or item artifacts. Already-terminal items must produce compact summaries, and log viewers must filter or stream selected runs instead of loading unbounded history.

## Rule 24 — Separate authoritative and derived data

The project must declare which databases and files are authoritative and which are derived. Derived reports, indexes, and summaries must be reproducible from authoritative state and validated before being used as input to later processing.

## Rule 25 — Respect external platform constraints

Source adapters must respect authentication requirements, provider terms, rate limits, and bounded retry/backoff policies. Access-control or authentication failures must be reported explicitly and must not be bypassed silently.

## Rule 26 — Preserve reproducibility and documentation consistency

Given the same inputs, state, time bounds, tool versions, and model assets, discovery and ingestion decisions should be reproducible. Record relevant tool and model versions. Documentation must match the current commands, paths, schemas, statuses, and configuration; aspirational material must be clearly labeled.

## Rule 27 — Tests assert rules, never the value configuration currently holds

A test must not hardcode a value such that changing that value elsewhere fails the test while nothing is wrong. Assert `PROMPT_VERSION` rather than the current version string; compute a budget boundary as `spec.max_model_calls * spec.stop_at_budget_fraction` rather than the product; pin a time window by passing both `since` and `until` rather than relying on the current date.

A literal is fine where nothing can move underneath it. A model name handed to a fake client, or a version deliberately pinned to prove a non-default is honored, breaks nothing when the default advances. The test is whether a legitimate change elsewhere turns the suite red, not whether a literal appears.

## Rule 28 — Mutation-check every new or changed test before committing

Edit the implementation to break exactly one behavior, run the test, confirm it fails, then restore. Do this for each behavior the change claims to cover, and name the mutations in the commit message. If no test fails, do not commit until you have determined which of three cases applies and stated it: the behavior is untested, it is dead code, or it is guarded elsewhere.

## Rule 29 — Every entry point needs a test, not just the functions it calls

An entry point that makes a decision requires at least one test over the entry point itself, not only over the helpers it calls. Decisions include ordering with consequences, resolving one argument from another, assembling inputs, selecting a provider or arm, and choosing an output path. A `main` that parses arguments and delegates to a covered function makes no decision and needs no separate test.

Where call order carries meaning, assert the order with a recorded call sequence rather than trusting a reading of the code: `load_dotenv` before `tool_parameters`, argument resolution before input assembly.

## Rule 30 — A comparison guards every field that can change its result

Comparison and benchmark runs must record and compare prompt version, model identity, `index_signature`, `suite_version`, and every configured limit that can stop a run. Adding an input that varies means adding it to the guard in the same change. Arms that differ in any guarded field must refuse to report rather than report the difference as a result. Never hardcode an arm's identity where the run derives it.

## Rule 31 — One arm, one output path

Each provider, model, or measurement arm writes to a path that identifies it, as `measurement_output_dir` and `default_output_path` do. Two arms must never share an output path. A summary records the arm and run that produced it, and is assembled only from artifacts of that single run; artifacts mixed across runs are archived with a written reason, not corrected in place. Counters describing one run must count the same work: if a billed call appears in cost, it appears in latency and token totals too.

## Rule 32 — Loops that share a failure share its handling

Before adding checkpointing, budget enforcement, resume, retry, or usage accounting to a loop, check whether `llm_gym/agent/bounded_loop.py` already provides it and use it. Where two loops handle the same failure differently, the reason must be commented at both sites. Extract shared machinery rather than copying it, and cover the extraction with a test driving a workload shape it was not written for.

## Rule 33 — Measured claims carry their sample and cite their artifact

Any statement derived from runs — in a commit message, a Markdown document, a report field, or a code comment — must contain all three of the following, or it is not a finding and must not be written as one:

1. **The counts**: runs, cases, and models. A count of zero is written as a count, never converted into a general negative. "Fired in 0 of 33 runs" is a finding; "does not fire" is not.
2. **The artifact path** a reader can verify it against, such as `data/runs/trigger-measurement/<arm>/summary.json`.
3. **The word "provisional"** if the claim rests on a single arm, where an arm is one provider prefix, one model, and one prompt version. A single arm cannot distinguish a property of the system from a property of that arm.

When a later run contradicts a recorded claim, insert `[SUPERSEDED BY §N]` at the original and leave the original in place. Do not delete or silently edit it; the correction is part of the record.

Insufficient — this was written down, and the next arm falsified it:

> The relevance trigger never fires, so it is not load-bearing.

Sufficient:

> The relevance trigger fired in 1 of 6 runs on claude-sonnet-5 and 2 of 6 on glm-5.2, 2 cases × 3 repetitions per arm, prompt synthesis-v7, identical evidence sets — `data/runs/trigger-measurement/{agent,open_weight}/summary.json`.

The second survives new data because it describes what was observed rather than what is true. The first had to be retracted twice.
