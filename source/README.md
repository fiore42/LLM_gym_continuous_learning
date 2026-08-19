# `source/` — acquired content, never committed

[Project rules](../PROJECT_RULES.md)

This tree holds everything ingestion downloads. **Nothing in it is committed**,
for three reasons: it is third-party media and this project is not its
distributor, it is roughly 700 MB, and it is reproducible by re-running
ingestion against `config/SOURCES.md`.

Recorded here so the structure is reviewable without cloning it.

## Layout

Verified against the local tree rather than assumed:

```
source/
  youtube/
    <channel-key>/                       e.g. claude, IBMTechnology, OpenAI
      channel-ingestion-report.json      per-run ingestion outcome
      ingestion-state.sqlite3            per-source worker cache
      videos/
        YYYYMMDD_<content-id>/           date is the PUBLICATION date, Rule 9
          .ingestion-complete            atomic completion marker, Rule 16
          ingestion-events.jsonl         per-item event record
          platform-subtitles/            captions as published, when available
            <id>.en.srt, <id>.en-orig.srt
          transcripts/                   the transcript actually indexed
            <id>.srt
  x/
    <account-key>/                       e.g. claudeai, gdb, NickADobos
      posts/
        YYYYMMDD_<post-id>/
          .complete                      atomic completion marker
          post.json                      the original post record
          attachments/, images/          present only when the post had them
```

Audio and video files appear during processing and are removed once a transcript
exists, which is why a completed folder can hold only subtitles.

Two invariants worth knowing when reading the code:

- **The date prefix is the publication date, never the download date** (Rule 9).
  An adapter that cannot determine publication date must record a warning rather
  than silently substitute today.
- **A content folder is not complete until its marker exists** (Rule 16). A
  folder without `.complete` is retryable, not corrupt.

## The authoritative record is elsewhere

`data/source-registry.sqlite3` is authoritative for terminal content decisions;
the per-source `ingestion-state.sqlite3` is a worker cache that must agree with
it (Rule 5, checked by `scripts/check_state_registry_consistency.py`).

Searchable text is derived into `data/evidence.sqlite3`, which is also not
committed and is rebuilt with `scripts/corpus_build_evidence_index.py`. What the
project *concluded* from this content is committed, in `data/`.

## Regenerating

```
.venv/bin/python scripts/check_environment_configuration.py   # credentials, tools
.venv/bin/python scripts/ingest_all_configured_sources.py
.venv/bin/python scripts/corpus_build_evidence_index.py
```

Ingestion is windowed and incremental: it resumes from the registry cursor and
will not reprocess terminal items without `--force`.
