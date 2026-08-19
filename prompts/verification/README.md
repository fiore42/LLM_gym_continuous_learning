# Verification-drafter prompts

[Project rules](../../PROJECT_RULES.md)

This family drafts an advisory review sheet from an existing answer and its
supplied evidence. It breaks the answer into material statements and proposes
`proven`, `not_proven`, or `unclear` for each statement, with one evidence ID
and one exact snippet passage per row. Deterministic code verifies that every
proposed passage occurs in the referenced snippet; human decisions remain
authoritative.

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
