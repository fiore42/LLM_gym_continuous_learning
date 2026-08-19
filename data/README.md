# `data/` — what is committed here and what is not

[Project rules](../PROJECT_RULES.md)

This directory holds everything the project produces at runtime. Most of it is
**deliberately absent from GitHub**, and the rule is a single distinction:

| | committed | why |
|---|---|---|
| **Model output** | yes | Reproducing it costs real money. It is the evidence of the work. |
| **Deterministic output** | no | Reproducible by running one command, so storing it would only consume space. |

Locally this directory is around 400 MB. Committed, it is about 1 MB — small
enough to read on GitHub without cloning a corpus.

## Committed

- `digests/*-report.json` — per-item significance judgements from a digest run,
  each carrying a quote that deterministic code located in the source item.
- `runs/**` — live-run traces and measurement summaries, including
  `runs/trigger-measurement/archive-mixed/`, kept as evidence of a
  data-integrity failure rather than deleted.
- `eval-*-report.json` — evaluation suite reports.
- `verification-drafts/**` — proposed claim verifications awaiting human
  confirmation.
- `human-labels/**` — blind scope and evidence-support decisions, human
  classifications, and provisional audit reports. These are manual evidence rather than
  deterministic runtime output.

## Not committed, and how to regenerate it

| absent | regenerate with |
|---|---|
| `evidence.sqlite3` (192 MB) | `scripts/corpus_build_evidence_index.py` |
| `digest-windows/*.json` | `scripts/corpus_freeze_digest_window.py` |
| `*-checkpoint.json` | a by-product of any run; duplicates the report |
| `*-cache/`, `eval-suite/` | per-case answer caches; duplicate the reports |
| `run-log.jsonl` | appended by every run; grows without bound |
| `source-registry.sqlite3` | ingestion state |
| `archive/` (213 MB) | superseded artifacts, kept locally only |
| `smoke-test/` | test fixtures and output |
| `human-review/` | local full-text review packets; committed labels retain hashes and provenance instead |

Acquired source content lives under `source/` and is never committed: it is
third-party media, it is large, and the project is not its distributor.

## Reading a digest report

```
.venv/bin/python scripts/show_digest.py data/digests/<file>-report.json --quotes
```

Current judgements carry one to three mapped `supporting_evidence` quotes, each
validated against the item text before acceptance. Historical v1 reports carry
one `supporting_quote`. Rankings themselves are **unvalidated**. The completed
M6.2 audit sampled 20 of 46 accepted significance-v2 assessments and found only
11 of 18 in-scope claims fully supported by their selected evidence. It does
not provide missed-claim recall.
