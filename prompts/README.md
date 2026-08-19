# Prompt registry

[Project rules](../PROJECT_RULES.md)

This directory contains the instructions given to models. The project uses a
different prompt for each kind of model work:

- answer a question from retrieved evidence;
- review one newly collected source for the digest;
- help a person check whether an answer is supported by its evidence.

Keeping those jobs separate makes it possible to improve and measure one
behavior without silently changing the others.

## How the prompt families fit into the project

```text
question + retrieved evidence ──► agent_task ──► cited answer

one video or post from a time window ──► digest ──► one ranked digest entry

existing answer + its evidence ──► verification ──► draft checklist for a human
```

| Folder | Purpose | Current default | Primary entry point |
|---|---|---|---|
| [`agent_task/`](agent_task/) | Answer one question using only the evidence retrieved for that question. Cite the useful sources and ask for another search when important evidence is missing. | `synthesis-v7` | `scripts/agent_run_task_on_checkpoint.py` |
| [`digest/`](digest/) | Read one collected video transcript or post, identify the concrete AI-engineering update it contains, quote the passages that support it, and decide how useful that update is for the digest. | `significance-v2` | `scripts/agent_run_digest.py` |
| [`verification/`](verification/) | Turn an existing answer into a claim-by-claim checklist that helps a person see which statements are supported, unsupported, or unclear. | `verification-v1` | `scripts/eval_draft_claim_verification_sheet.py` |

## Why prompts are stored as versioned JSON

Prompt definitions are immutable JSON records grouped by task. When a prompt
changes, the new text is saved in a new file; an old prompt is never edited.
This preserves the instructions behind historical runs and allows two prompt
versions to be compared on the same evaluation cases.

Each family has its own directory because `load_prompt()` selects the record
with the highest `version_number` in that directory when no version is named.
Answer-task and verification traces retain the full rendered prompt used for
the model call. Digest reports retain the prompt version, source path, and
SHA-256, which identify the immutable template used with that report's source
item.

The folder READMEs describe every version and all script entry points that load
the family directly or through the runtime layer.
