# `data/digest-windows/` — empty on GitHub by design

[Project rules](../../PROJECT_RULES.md)

Frozen window snapshots live here: the exact set of corpus items a digest run
will assess, with the `index_signature` of the index they came from.
Window freezing excludes empty or bracketed-cue-only transcript text before
any paid model call and records `excluded_non_substantive`; it does not impose
a minimum transcript length or semantic topic filter.

**Nothing here is committed**, because selection is fully deterministic. The same
window against the same index always yields the same items in the same order, so
a snapshot is reproducible rather than precious:

```
.venv/bin/python scripts/corpus_freeze_digest_window.py \
  --days 7 --platform youtube --dry-run     # size it first, costs nothing
.venv/bin/python scripts/corpus_freeze_digest_window.py \
  --days 7 --platform youtube
```

A snapshot embeds each item's metadata, so a 30-day window is roughly 150 KB —
small individually, pure duplication of the index in aggregate.

What a run *decided* is committed instead, in `../digests/`. Each report carries
the window bounds, day count, platform filter, `index_signature`, and how many
items were considered against how many were selected, so a reader can see what
was assessed without the snapshot being present.
