# Persisted State Contract

[Project rules](../PROJECT_RULES.md)

The central registry at `data/source-registry.sqlite3` is the authoritative
source and content status store. Per-source `ingestion-state.sqlite3` files
are local worker caches used to avoid unnecessary work and must agree with the
central registry for terminal items.

Channel reports, the multi-source report, completion markers, and compact
per-item event files are derived verification artifacts. They may be rebuilt
from the registry and source artifacts and must never be treated as the sole
source of truth.

Schema changes require an explicit SQLite schema version and migration. A
repair must preserve canonical URLs, publication timestamps, content IDs, and
terminal status history.

Run `scripts/check_state_registry_consistency.py` after ingestion or state repairs. It
checks both that every local YouTube item exists centrally and that every
configured central YouTube item exists in its per-source state database.

State transitions are deterministic. Model-generated summaries or semantic
labels must never be used as completion state, source identity, retry state, or
the authoritative record of whether content was downloaded.
