# Digest significance prompts

[Project rules](../../PROJECT_RULES.md)

This family assesses one time-window item per model call. It extracts the
supported change and problem, assigns one of `SIGNIFICANT`, `INCREMENTAL`,
`UNSUPPORTED`, or `PROMOTIONAL`, and returns exact source text for deterministic
grounding checks. The model sees only the current item, not other corpus items.

## Versions

| Version | What it does |
|---|---|
| `significance-v1` | Returns one summary, reason, label, and one verbatim supporting passage. It remains available for interpreting historical reports. |
| `significance-v2` | Current default. Selects one to three distinct passages first, maps each passage to one factual component, and limits the summary to what their union supports. |

## Scripts that use this family

| Script | How it uses the prompt |
|---|---|
| `scripts/agent_run_digest.py` | Loads the current default (`significance-v2`) and applies it independently to each item in a frozen window. Validation failures receive bounded revision feedback from the same prompt record. |

The loader path is `llm_gym/agent/significance.py` →
`llm_gym/agent/digest.py`. `agent_run_digest.py` does not expose a prompt-version
flag; it uses the latest registered digest prompt and includes that version in
checkpoint and report paths. Historical versions remain loadable
programmatically through `SignificanceRequest(prompt_version=...)`.

`scripts/show_digest.py` and `scripts/eval_audit_digest_claims.py` read the
resulting reports but do not load or call this prompt family.
