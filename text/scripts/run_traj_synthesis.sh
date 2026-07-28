#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# ${VAR:-default} uses default when VAR is unset or empty.
DATA_DIR="${DATA_DIR:-${PROJECT_ROOT}/../data/text}"
OUTPUT_DIR="${OUTPUT_DIR:-${PROJECT_ROOT}/../outputs/text}"
USER_ID="${USER_ID:-user_01}"
MODEL_NAME="${MODEL_NAME:-gpt-5.2}"
PERSONA_PATH="${DATA_DIR}/profiles/${USER_ID}.json"
USER_OUTPUT_DIR="${OUTPUT_DIR}/${USER_ID}"

# ${VAR:?message} exits with message when VAR is unset or empty.
: "${OPENAI_API_KEY:?Set OPENAI_API_KEY before running this script.}"
export OPENAI_API_BASE="${OPENAI_API_BASE:-https://api.openai.com/v1}"

mkdir -p "${USER_OUTPUT_DIR}"

python "${PROJECT_ROOT}/run_synthesis.py" \
    --persona_path "${PERSONA_PATH}" \
    --model "${MODEL_NAME}" \
    --max_events 12 \
    --min_events 2 \
    --max_depth 2 \
    --output_path "${USER_OUTPUT_DIR}/trajectory_state.pkl" \
    --traj_server_port 5001 \
    --grounded_session_subgraph_threshold 1 \
    --disable_ngrok \
    "$@"