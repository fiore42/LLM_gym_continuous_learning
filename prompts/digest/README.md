# Digest significance prompts

[Project rules](../../PROJECT_RULES.md)

## What this prompt is for

The library may collect dozens or hundreds of videos and posts in a time
window. Reading all of them by hand would be slow. This prompt reads one item
at a time and prepares one possible entry for the digest.

For each item, the model must:

1. find one to three passages that describe the concrete AI-engineering update;
2. copy those passages exactly from the source;
3. write a short statement that says no more than those passages support;
4. explain what problem the update addresses, if the source says so;
5. label the item as `SIGNIFICANT`, `INCREMENTAL`, `UNSUPPORTED`, or
   `PROMOTIONAL`.

The labels answer a practical question: should this source appear as a useful
development in the digest, as a smaller update, as an unsupported assertion,
or mainly as promotion? The model judges only the source currently in front of
it. It does not know whether another corpus item reports the same development
or disagrees with it.

## How it fits into the project

`agent_run_digest.py` applies this prompt independently to every item in a
frozen date window. Deterministic code then checks that every selected passage
really occurs in the source text. If the response is malformed or contains a
passage that cannot be found, the item receives bounded retry feedback. Items
that still fail remain visible for human review instead of being silently
accepted.

The resulting entries are ranked and written to a digest report. Exact passage
matching proves where the model got its evidence; it does not prove that the
model chose the best update or assigned the correct significance label. That
semantic judgement is checked separately through human review.

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
