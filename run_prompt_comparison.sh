#!/usr/bin/env bash
# Compare two prompt versions on the same frozen answer cases, one model.
#
# Every run writes to a fresh timestamped directory. That is not tidiness: the
# suite runner resumes from its state file, so reusing paths makes a second run
# skip every case, issue zero model calls, and still report SUITE_COMPLETE with
# a full result set. A replayed run is indistinguishable from a fresh one in the
# report, so the directory is the only thing preventing it.
set -euo pipefail

MODEL="${MODEL:-glm-5.2}"
PROVIDER_PREFIX="${PROVIDER_PREFIX:-OPEN_WEIGHT}"
MAX_COST_USD="${MAX_COST_USD:-1.0}"
REPETITIONS=(1 2 3)
PROMPT_VERSIONS=("${ARM_A:-synthesis-v6}" "${ARM_B:-synthesis-v7}")

# The comparison arms are derived from PROMPT_VERSIONS below, never restated.
# Naming the versions in two places is what previously let the run loop move
# to a new pair while the comparison kept reading a stale one.
if [ "${#PROMPT_VERSIONS[@]}" -ne 2 ]; then
  echo "PROMPT_VERSIONS must contain exactly two versions (got ${#PROMPT_VERSIONS[@]})" >&2
  exit 1
fi
ARM_A="${PROMPT_VERSIONS[0]}"
ARM_B="${PROMPT_VERSIONS[1]}"

RUN_DIR="data/prompt-comparison/run-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "${RUN_DIR}"
echo "RUN_DIR ${RUN_DIR}"
echo "MODEL   ${MODEL} via ${PROVIDER_PREFIX}"

for prompt_version in "${PROMPT_VERSIONS[@]}"; do
  for repetition in "${REPETITIONS[@]}"; do
    prefix="${RUN_DIR}/${prompt_version}-rep-${repetition}"

    echo "RUN ${prompt_version} repetition ${repetition}"
    # One repetition per report: the comparator's trial denominator is
    # cases x reports, so three repetitions inside one report would be counted
    # once. It refuses such a report rather than miscounting it.
    .venv/bin/python scripts/eval_run_suite.py \
      --model "${MODEL}" \
      --provider-prefix "${PROVIDER_PREFIX}" \
      --prompt-version "${prompt_version}" \
      --repetitions 1 \
      --max-cost-usd "${MAX_COST_USD}" \
      --output "${prefix}-report.json" \
      --state "${prefix}-state.json" \
      --cache-dir "${prefix}-cache"
  done
done

.venv/bin/python scripts/eval_compare_prompt_arms.py \
  --arm-a "${RUN_DIR}/${ARM_A}"-rep-*-report.json \
  --arm-b "${RUN_DIR}/${ARM_B}"-rep-*-report.json \
  --output "${RUN_DIR}/comparison-${ARM_A}-vs-${ARM_B}.json"

echo
echo "Comparison written to ${RUN_DIR}/comparison-${ARM_A}-vs-${ARM_B}.json"
