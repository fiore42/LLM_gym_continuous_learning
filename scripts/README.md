# Script index

[Project rules](../PROJECT_RULES.md)

Script names use `<group>_<verb>_<object>` so the alphabetical listing explains the
project surface: `agent_` runs the agent, `eval_` evaluates it, `corpus_` works with
the evidence index, `ingest_` updates the library, `check_` validates state, and
`maintenance_` contains historical repairs. The two ungrouped scripts are the run
log viewer and the YouTube ingestion smoke test.

## Agent loop

- `agent_retrieve_evidence_for_question.py` — Run the bounded retrieval-and-citation research loop.
- `agent_run_task_on_checkpoint.py` — Synthesize a research checkpoint through the configured model provider.
- `agent_run_retrieval_retry.py` — Live-fire the retrieval-retry loop: draft, expand evidence with a refined query, redraft. Use `--case <id>` or `--question`.
- `agent_measure_retrieval_trigger.py` — Repeat live retrieval-retry runs to measure which signal fires the loop (classification label vs. relevance count). Spends money; has a `--max-cost-usd` cap.
- `agent_run_digest.py` — Assess every item in a frozen window as one bounded unit, checkpointed and resumable. Rejected responses retry once by default; `--max-item-retries` permits a bounded 0–5 override. Reports separate item and provider-request counts. Spends money; run `--estimate` first.
- `show_digest.py` — Read a digest report. Read-only and free. `--quotes` shows the mapped verbatim evidence spans located in each source item, `--label ALL` shows every assessment, `--rejected` shows failed validations.

## Evaluation

- `eval_run_suite.py` — Run the frozen answer cases through one bounded model provider.
- `eval_validate_suite.py` — Validate the reviewable agent evaluation suite without calling a model. Use `--case <id>` for one answer case, or `--case` with no value to list them.
- `eval_review_trajectory_case.py` — Show one trajectory case beside the test that proves it, and run that test. Use `--case <id>`, or `--case` with no value to list them.
- `eval_compare_prompt_arms.py` — Compare repeated evaluation-suite report groups by case and provenance.
- `eval_draft_claim_verification_sheet.py` — Draft claim-to-evidence verification sheets for human confirmation.
- `eval_audit_digest_claims.py` — Build and label a blind digest claim/evidence
  audit, then reveal model reasons and labels. The reveal phase prints exact
  human/model label matches automatically and asks for label judgement only
  when labels differ.
- `eval_compare_model_providers.py` — Run the same benchmark suite against two provider environments.
- `eval_build_benchmark_from_corpus.py` — Create a human-labeled benchmark from the local evidence index.

## Corpus

- `corpus_build_evidence_index.py` — Create/update the unified searchable evidence index.
- `corpus_search_evidence_index.py` — Search the unified evidence index and print citation-ready results.
- `corpus_profile_coverage.py` — Profile downloaded source coverage without reading media or logs.
- `corpus_freeze_digest_window.py` — Freeze the substantive items a digest run will assess, with the index signature and placeholder-exclusion count. Deterministic and free; `--dry-run` sizes a window without writing a snapshot.

## Ingestion

- `ingest_all_configured_sources.py` — Ingest configured YouTube sources with bounded download concurrency.
- `ingest_one_youtube_channel.py` — Discover and ingest recent videos from one YouTube channel.
- `ingest_discover_youtube_channel_videos.py` — Discover recent videos from one YouTube channel without downloading media.
- `ingest_update_library_incrementally.py` — Run the incremental daily ingestion-and-library-update loop.

## Validation & health checks

- `check_environment_configuration.py` — Check required project configuration without printing secret values.
- `check_markdown_rule_links.py` — Verify that every project Markdown file links to PROJECT_RULES.md.
- `check_project_rules.py` — Enforce the rules in PROJECT_RULES.md that a program can decide, and print the ones it cannot so the unenforced remainder stays visible. `--check-last-commit` adds the mutation-record check.
- `check_state_registry_consistency.py` — Check per-source YouTube state against the central source registry.
- `check_youtube_source_manifest.py` — Validate the configured YouTube source manifest.
- `smoke_test_youtube_ingestion.py` — Run a live smoke test for single-video YouTube ingestion.
- `show_recent_run_log.py` — Inspect the shared chronological project run log.

## Maintenance

The `maintenance_` group holds historical one-off tools from the ingestion phase,
retained for provenance and not part of any current workflow.

- `maintenance_backfill_x_post_assets.py` — Backfill X media, linked documents, and article metadata for saved posts.
- `maintenance_repair_short_videos_without_audio.py` — Reprocess previously skipped short YouTube videos with the visual fallback.
- `maintenance_merge_duplicate_registry_source.py` — Merge one equivalent source-registry key into its canonical key.

## Test coverage

Scripts that carry logic export a testable function and are covered offline
with an injected client or runner: `eval_run_suite.py`, `eval_validate_suite.py`,
`eval_compare_prompt_arms.py`, `eval_compare_model_providers.py`,
`eval_build_benchmark_from_corpus.py`, `eval_draft_claim_verification_sheet.py`,
`eval_audit_digest_claims.py`, `eval_review_trajectory_case.py`, `agent_run_task_on_checkpoint.py`,
`agent_run_retrieval_retry.py`, `agent_measure_retrieval_trigger.py`, and
`check_environment_configuration.py`.

The remaining scripts are deliberately uncovered, for two distinct reasons:

- **Pass-through CLIs** — `agent_retrieve_evidence_for_question.py` only wires
  argparse flags to `run_research`, which `tests/test_research.py` covers
  directly. A test here would exercise argparse, not project behaviour.
- **External-dependency scripts** — the `ingest_`, `corpus_`, `maintenance_`,
  `smoke_test_`, and run-log scripts need network access, credentials, or
  external tools. Their underlying modules are tested offline with injected
  boundaries; the scripts themselves are exercised by live smoke runs.
