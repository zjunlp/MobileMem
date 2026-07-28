#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

: "${OPENAI_API_KEY:?Set OPENAI_API_KEY before running this script.}"
export OPENAI_API_BASE="${OPENAI_API_BASE:-https://api.openai.com/v1}"
export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH:-}"

python "${PROJECT_ROOT}/analysis/hard_distractor/prepare_env.py"
python "${PROJECT_ROOT}/analysis/hard_distractor/run_synthesis.py"