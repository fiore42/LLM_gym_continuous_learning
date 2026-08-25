#!/usr/bin/env bash
# Compare two model/provider arms on the same frozen answer cases, one prompt.
#
# Every run writes to a fresh timestamped directory. That is not tidiness: the
# suite runner resumes from its state file, so reusing paths makes a second run
# skip every case, issue zero model calls, and still report SUITE_COMPLETE with
# a full result set. A replayed run is indistinguishable from a fresh one in the
# report, so the directory is the only thing preventing it.
#
# This is a model/provider-arm comparison, not a model comparison: switching
# from Claude to GLM changes both the model and the service serving it, and
# nothing here separates those two variables.
set -euo pipefail

# One arm is one "label:provider_prefix:model" triple. The label names the
# artifacts AND the comparison globs, so the run loop and the comparison cannot
# drift apart. Naming them separately is what previously let a comparison read
# one pair of arms while the run loop wrote another.
ARM_A="${ARM_A:-sonnet:AGENT:claude-sonnet-5}"
ARM_B="${ARM_B:-glm:OPEN_WEIGHT:glm-5.2}"
ARMS=("${ARM_A}" "${ARM_B}")

SUITE="${SUITE:-config/agent_eval_suite.json}"
PROMPT_VERSION="${PROMPT_VERSION:-synthesis-v7}"
REPETITIONS=(1 2 3)
MAX_COST_USD="${MAX_COST_USD:-1.0}"

labels=()
for arm in "${ARMS[@]}"; do
  IFS=':' read -r label prefix model <<<"${arm}"
  if [ -z "${label}" ] || [ -z "${prefix}" ] || [ -z "${model}" ]; then
    echo "arm must be label:provider_prefix:model (got '${arm}')" >&2
    exit 1
  fi
  labels+=("${label}")
done
if [ "${labels[0]}" = "${labels[1]}" ]; then
  echo "the two arms must have different labels (both are '${labels[0]}')" >&2
  exit 1
fi

RUN_DIR="data/model-comparison/run-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "${RUN_DIR}"
echo "RUN_DIR ${RUN_DIR}"
echo "PROMPT  ${PROMPT_VERSION} (identical in both arms — the moving variable is the arm)"
for arm in "${ARMS[@]}"; do echo "ARM     ${arm}"; done

run() { if [ "${DRY_RUN:-}" = "1" ]; then echo "DRY_RUN: $*"; else "$@"; fi; }

for repetition in "${REPETITIONS[@]}"; do
  for arm in "${ARMS[@]}"; do
    IFS=':' read -r label prefix model <<<"${arm}"
    out="${RUN_DIR}/${label}-rep-${repetition}"

    echo "RUN ${label} (${model} via ${prefix}) repetition ${repetition}"
    # One repetition per report: the comparator's trial denominator is
    # cases x reports, so three repetitions inside one report would be counted
    # once. It refuses such a report rather than miscounting it.
    run .venv/bin/python scripts/eval_run_suite.py \
      --suite "${SUITE}" \
      --provider-prefix "${prefix}" \
      --model "${model}" \
      --prompt-version "${PROMPT_VERSION}" \
      --repetitions 1 \
      --max-cost-usd "${MAX_COST_USD}" \
      --output "${out}-report.json" \
      --state "${out}-state.json" \
      --cache-dir "${out}-cache"
  done
done

COMPARISON="${RUN_DIR}/${labels[0]}-vs-${labels[1]}-${PROMPT_VERSION}.json"
run .venv/bin/python scripts/eval_compare_prompt_arms.py \
  --arm-a "${RUN_DIR}/${labels[0]}"-rep-*-report.json \
  --arm-b "${RUN_DIR}/${labels[1]}"-rep-*-report.json \
  --output "${COMPARISON}"

echo
echo "Comparison written to ${COMPARISON}"
