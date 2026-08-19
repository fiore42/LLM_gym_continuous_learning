# Archived: do not quote these numbers

These traces are kept as evidence of a data-integrity failure, not as a
measurement. `summary.json` here describes **no single run**.

## What happened

Traces were named `{case}-rep-{n}.json` in one shared directory, so a re-run
overwrote only the files it actually reached.

1. A measurement of `what_are_evals` + `independent_evaluation` × 5 completed.
2. A second measurement started. It overwrote `what_are_evals` reps 1–5, then
   hit an Anthropic spend cap (`HTTP 400: You have reached your specified API
   usage limits`) and crashed formatting the missing classification of a run
   that had no first round. It never reached `independent_evaluation`.
3. `summary.json` was then regenerated from every trace on disk — merging 5
   fresh `what_are_evals` traces with 5 stale `independent_evaluation` traces
   from run 1, and reporting them as one clean 10-run measurement.

The merged summary looked complete and was internally consistent. Nothing in
it indicated that half its rows came from a different run.

## What changed because of it

- Each provider arm now measures into its own directory
  (`measurement_output_dir`), so two arms cannot overwrite each other.
- The measurement stops entirely on a provider refusal (spend cap, quota)
  rather than issuing further doomed requests.
- The report is written from a `finally` block, so a crash no longer discards
  the aggregate for runs already paid for.
- A run with no completed first round formats a placeholder instead of raising
  `TypeError` and killing every repetition still queued.

## The lesson

An artifact that looks complete is not evidence that it is. The mixture was
only detectable by file modification time — nothing in the data itself.
Measurement output needs provenance for the same reason model output does.

See `.fieldnotes.md` §33.
