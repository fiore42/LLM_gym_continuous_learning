# `data/runs/` — live-run traces

[Project rules](../../PROJECT_RULES.md)

**Committed**, because every trace here is the record of a paid provider call and
is not reproducible without spending again.

=== CODEX comment ===
Not every trace here records a paid provider call. The committed
`manual/*-research.json` files are deterministic retrieval traces and contain no
model call or provider usage.
=== /CODEX comment ===

- `manual/` — single end-to-end task traces from first live contact.
- `retrieval-retry-*.json` — one trace per live retrieval-retry run, named by
  case and provider arm.
- `trigger-measurement/<arm>/` — repeated runs measuring which signal fires the
  evidence-expansion loop. One directory per provider arm, so one arm cannot
  overwrite another's traces.
- `trigger-measurement/archive-mixed/` — **kept deliberately as a negative
  result.** Its `summary.json` merges two different runs and looks complete. Its
  own README explains how, and the checks that now prevent it. Do not quote its
  numbers.

Traces carry model output, prompt version and hash, token usage, per-call
latency, cost, and stop reason. They are the primary evidence behind claims
made in the project's documentation, which is why Rule 33 requires a claim to
cite the artifact a reader can check it against.

=== CODEX comment ===
This field list is not true of all traces here. Manual research traces omit
model, prompt, and usage provenance; older manual answer traces omit prompt hash
and rendered prompt; retrieval-retry and trigger-measurement traces omit prompt
version, prompt hash, and rendered prompt.
=== /CODEX comment ===
