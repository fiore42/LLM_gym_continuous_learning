# Human digest audits

[Project rules](../../PROJECT_RULES.md)

This directory stores committed human audit decisions and provisional audit
reports. Compact review cards remain local under `data/human-review/`; the
committed decisions retain passage hashes, rubric provenance, and the corpus
`index_signature` needed to detect drift.

## M6.2 model-decision audit

The audit samples 20 existing digest assessments. It does not ask one human to
label a complete multi-claim transcript. Each card shows the explicit
model-generated claim and one to three exact AI-selected evidence passages,
each mapped to a claim component, while showing its YouTube channel or X
account and hiding the model's proposed label and reason. Optional context can
clarify a passage but cannot supply facts missing from the evidence set.

The paid significance-v2 seven-day report, compact packet, human decisions,
model review, and canonical audit report exist. The digest report contains 46
accepted assessments and three visible rejections after bounded retries; the
packet deterministically sampled 20 accepted assessments. Historical
significance-v1 reports are rejected because one selected quote cannot ground a
compound summary.

Decide first whether the claim is substantively about AI or agent systems.
Out-of-scope cards stop there and are counted as selection failures. For
in-scope cards, judge whether the evidence set jointly supports the claim, then classify
what is actually supported. The command saves after every card, so `Ctrl-C` is
safe and the same command resumes:

```bash
.venv/bin/python scripts/eval_audit_digest_claims.py label \
  --reviewer alfonso
```

After all 20 decisions are complete, reveal the model reason and proposed label.
The command displays whether the blind human and model labels match. Exact
matches record `AGREE` automatically; for differing labels, decide whether the
model label is nevertheless a reasonable alternative. Separately check whether
the model reason adds unsupported material:

```bash
.venv/bin/python scripts/eval_audit_digest_claims.py review-model \
  --labels data/human-labels/digest-claim-audit-v1/alfonso-blind-claim-decisions.json
```

Generate the provisional audit report:

```bash
.venv/bin/python scripts/eval_audit_digest_claims.py report \
  --labels data/human-labels/digest-claim-audit-v1/alfonso-blind-claim-decisions.json \
  --model-review data/human-labels/digest-claim-audit-v1/alfonso-model-review.json \
  --output data/human-labels/digest-claim-audit-v1/glm-5.2-audit-report.json
```

This report can measure selected-decision support and human acceptance. It
cannot measure claims the model missed, source-level recall, or corpus-level
ranking quality. A true gold set requires atomic candidate developments and a
separate missed-claim discovery process; that work is deferred.

The generated report is the canonical result. It records 20 cards, 18 in scope,
two out-of-scope selection failures, claim support of 11 full / 6 partial / 1
unsupported, reason support of 15 full / 3 partial, and exact blind label
alignment of 8/18. The reviewer considered all 18 revealed model labels
reasonable alternatives, so that field must not be described as perfect exact
classification. The strict accepted-decision count is 11/18.

These denominators and limitations are mirrored in `ROADMAP.md` M6.2, the
`README.md` live-artifact table, `DIGESTS.md`, and the private local brief.
The report does not measure missed claims or recall.
