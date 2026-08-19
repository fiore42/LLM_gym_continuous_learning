# `data/digests/` — digest run output

[Project rules](../../PROJECT_RULES.md)

One `*-report.json` per (window, model, provider arm, prompt version). Named so
two arms, prompts, or windows cannot overwrite each other.

**Committed**, because every assessment cost a model call. A report contains,
per item: the claimed change, the problem it addresses, a significance label,
the reason, and one to three mapped verbatim evidence quotes that deterministic
code located in the item text. Historical v1 reports carry one
`supporting_quote`. At run level it carries the window, `index_signature`, model,
prompt version and hash, invocation time separately from total run wall time and
provider time, item attempts separately from provider requests, token totals,
and spend. Legacy reports may lack the newer split fields; the viewer labels
recovered call counts as lower bounds rather than presenting them as exact.

**Not committed:** `*-checkpoint.json`. That is transient resume state and
duplicates the report.

The current significance-v2 seven-day report is
`2026-07-31-to-2026-08-07-youtube-glm-5.2-open-weight-significance-v2-report.json`.
It is a provisional single-provider result: 46 accepted assessments, three
rejections, 75 provider calls, and $0.4217194. Its incomplete status is part of
the evidence; do not describe it as a clean 49-item completion.

The associated human audit is
`../human-labels/digest-claim-audit-v1/glm-5.2-audit-report.json`: two of 20
sampled decisions were out of scope, and 11 of 18 in-scope claims were fully
supported by their mapped evidence. It is a selected-decision audit, not a
recall or ranking benchmark.

Reports do not embed the rendered prompt. It is a pure function of the item and
the versioned template, so storing it per assessment duplicated every transcript
into the report — 48 items produced 1.24 MB before this changed, and about
186 KB after.

```
.venv/bin/python scripts/show_digest.py <report.json> --quotes
.venv/bin/python scripts/show_digest.py <report.json> --label ALL
.venv/bin/python scripts/show_digest.py <report.json> --rejected
```
