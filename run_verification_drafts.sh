#!/usr/bin/env bash
set -euo pipefail

TRACE_DIR="${TRACE_DIR:-data/runs/manual}"
OUTPUT_DIR="${OUTPUT_DIR:-data/verification-drafts}"

mkdir -p "${OUTPUT_DIR}"

found=0
for trace in "${TRACE_DIR}"/*-answer.json; do
  [ -f "${trace}" ] || continue
  found=1
  name="$(basename "${trace}" .json)"
  echo "DRAFT ${trace}"
  .venv/bin/python scripts/eval_draft_claim_verification_sheet.py \
    --trace "${trace}" \
    --output "${OUTPUT_DIR}/${name}.json" \
    --markdown "${OUTPUT_DIR}/${name}.md"
done

if [ "${found}" -eq 0 ]; then
  echo "No answer traces found in ${TRACE_DIR}" >&2
  exit 1
fi
