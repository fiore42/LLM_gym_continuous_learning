#!/usr/bin/env bash
set -euo pipefail

MODEL="claude-sonnet-5"
MAX_COST_USD="1.0"
REPETITIONS=(1 2 3)
PROMPT_VERSIONS=(synthesis-v5 synthesis-v6)

# The comparison arms are derived from PROMPT_VERSIONS below, never restated.
# Naming the versions in two places is what previously let the run loop move
# to a new pair while the comparison kept reading a stale one.
if [ "${#PROMPT_VERSIONS[@]}" -ne 2 ]; then
  echo "PROMPT_VERSIONS must contain exactly two versions (got ${#PROMPT_VERSIONS[@]})" >&2
  exit 1
fi
ARM_A="${PROMPT_VERSIONS[0]}"
ARM_B="${PROMPT_VERSIONS[1]}"

for prompt_version in "${PROMPT_VERSIONS[@]}"; do
  for repetition in "${REPETITIONS[@]}"; do
    prefix="data/eval-${prompt_version}-rep-${repetition}"

    echo "RUN ${prompt_version} repetition ${repetition}"
    .venv/bin/python scripts/eval_run_suite.py \
      --model "${MODEL}" \
      --prompt-version "${prompt_version}" \
      --repetitions 1 \
      --max-cost-usd "${MAX_COST_USD}" \
      --output "${prefix}-report.json" \
      --state "${prefix}-state.json" \
      --cache-dir "${prefix}-cache"
  done
done

.venv/bin/python scripts/eval_compare_prompt_arms.py \
  --arm-a "data/eval-${ARM_A}-rep-*-report.json" \
  --arm-b "data/eval-${ARM_B}-rep-*-report.json" \
  --output "data/eval-comparison-${ARM_A}-vs-${ARM_B}.json"
