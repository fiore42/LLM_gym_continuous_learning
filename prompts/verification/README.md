# Verification-drafter prompts

[Project rules](../../PROJECT_RULES.md)

## What this prompt is for

A cited answer can still say more than its sources establish. Checking every
sentence against every evidence excerpt by hand is slow, so this prompt prepares
the first draft of that review.

It breaks the answer into factual statements and, for each one, proposes:

- `proven`, `not_proven`, or `unclear`;
- the evidence record that should support the statement;
- the exact passage on which the proposed verdict rests.

The result is a checklist for a person, not an automatic quality score. The
reviewer agrees, disagrees, or edits each proposed verdict.

## How it fits into the project

This prompt runs after an answer already exists. It does not retrieve new
evidence, change the answer, or decide whether a run passes. Deterministic code
checks that each proposed passage actually appears in the referenced evidence
snippet. A fabricated passage is downgraded and flagged before the sheet reaches
the reviewer.

Human decisions remain authoritative. Agreement reports can measure how often
the drafter and reviewer agree, but the drafter's proposal is never treated as
a verified label on its own.

## Versions

| Version | What it does |
|---|---|
| `verification-v1` | Current default. Produces the statement, proposed verdict, evidence ID, and verbatim passage used by the propose-and-confirm workflow. |

## Scripts that use this family

| Script | How it uses the prompt |
|---|---|
| `scripts/eval_draft_claim_verification_sheet.py` | Loads the current default when drafting a new verification sheet. Its `--apply-labels` and `--agreement-report` modes are deterministic and do not call the prompt. |
| `run_verification_drafts.sh` | Calls the verification-sheet script for each prepared trace, so each draft uses the current default. |

The script records the full system prompt, rendered user prompt, version, and
SHA-256 in the draft JSON. A proposed verdict is advisory; only the associated
human-labelled file is authoritative.
