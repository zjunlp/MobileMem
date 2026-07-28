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

python "${PROJECT_ROOT}/postprocess_qa.py" \
    --input_path "${USER_OUTPUT_DIR}/qa_synthesis_results.json" \
    --model "${MODEL_NAME}" \
    --output_path "${USER_OUTPUT_DIR}/qa_synthesis_results_post.json" \
    --max_iters 10 \
    --random_seed 42 \
    --refine_strategy discard \
    --milvus_uri "${USER_OUTPUT_DIR}/qa_postprocess_milvus.db" \
    "$@"