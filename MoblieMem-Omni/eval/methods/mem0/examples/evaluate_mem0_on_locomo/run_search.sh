#!/usr/bin/env bash
# Stage 2: Memory Retrieval for Mem0 on LoCoMo.
# It uses the standardized dataset saved by Stage 1 after sampling.
# Adversarial questions are filtered out via --question-filter-path.
# Please modify the variables below to fit your setup.
# ========================================================
export HF_ENDPOINT=https://hf-mirror.com
export TRANSFORMERS_OFFLINE=1
export HF_HUB_OFFLINE=1
export HF_DATASETS_OFFLINE=1
export LITELLM_LOCAL_MODEL_COST_MAP=True
export LITELLM_OFFLINE_MODE=1
export CUDA_LAUNCH_BLOCKING=1
ROOT="${ROOT:-.}"

memory_type="Mem0"
dataset_type="LoCoMo"
dataset_path="$ROOT/output/mem0/shared/${USER_ID}/LoCoMo_stage_1.json"
config_path="examples/evaluate_mem0_on_locomo/mem0_config.json"
question_filter_path="examples/evaluate_mem0_on_locomo/question_filter.py:filter_adversarial"
num_workers=1
top_k=20
USER_ID="u10"
# ========================================================
set -euo pipefail
cd "$(dirname "$0")/../.."

python memory_search.py \
    --memory-type "$memory_type" \
    --dataset-type "$dataset_type" \
    --dataset-path "$dataset_path" \
    --dataset-standardized \
    --config-path "$config_path" \
    --question-filter-path "$question_filter_path" \
    --num-workers "$num_workers" \
    --top-k "$top_k"
