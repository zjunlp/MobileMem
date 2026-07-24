#!/usr/bin/env bash
# Stage 3: Question Answering & Evaluation for Mem0 on LoCoMo.
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

USER_ID="u10"
search_results_path="$ROOT/output/mem0/shared/${USER_ID}/20_0_1.json"  # Adjust based on actual output filename.
dataset_type="LoCoMo"
qa_model="gpt-4.1-mini"
judge_model="gpt-5.4-mini"
qa_batch_size=4
judge_batch_size=4
api_config_path="examples/evaluate_mem0_on_locomo/api_config.json"
prompt_template="examples/evaluate_mem0_on_locomo/qa_prompt.py:get_mem0_qa_prompt"
visual_memory_config_path="examples/evaluate_mem0_on_locomo/visual_memory_config.json"
# ========================================================
set -euo pipefail
cd "$(dirname "$0")/../.."

python memory_evaluation.py \
    --search-results-path "$search_results_path" \
    --dataset-type "$dataset_type" \
    --qa-model "$qa_model" \
    --judge-model "$judge_model" \
    --qa-batch-size "$qa_batch_size" \
    --judge-batch-size "$judge_batch_size" \
    --api-config-path "$api_config_path" \
    --prompt-template "$prompt_template" \
    --visual-memory-config-path "$visual_memory_config_path"
