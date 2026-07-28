#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${OUTPUT_DIR:-${PROJECT_ROOT}/../outputs/text}"
USER_ID="${USER_ID:-user_01}"
MODEL_NAME="${MODEL_NAME:-gpt-5.2}"
USER_OUTPUT_DIR="${OUTPUT_DIR}/${USER_ID}"

: "${OPENAI_API_KEY:?Set OPENAI_API_KEY before running this script.}"
export OPENAI_API_BASE="${OPENAI_API_BASE:-https://api.openai.com/v1}"

mkdir -p "${USER_OUTPUT_DIR}"

python "${PROJECT_ROOT}/run_qa_synthesis.py" \
    --trajectory_path "${USER_OUTPUT_DIR}/trajectory_state.pkl" \
    --model "${MODEL_NAME}" \
    --output_path "${USER_OUTPUT_DIR}/qa_synthesis_results.json" \
    --min_qa_pairs 1 \
    --max_qa_pairs 8 \
    --max_attempts 5 \
    --propagation_count 10 \
    --max_iters 50 \
    --random_seed 42 \
    "$@"