#!/usr/bin/env bash
# Stage 3: Question Answering & Evaluation for NaiveRAG on LoCoMo.
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

top_k=20
USER_ID="u10"
search_results_path="$ROOT/output/rag/shared/${USER_ID}/${top_k}_0_1.json"  # Adjust based on actual output filename.
dataset_type="LoCoMo"
qa_model="qwen3-vl-8b-instruct"
judge_model="gpt-5.4-mini"
qa_batch_size=4
judge_batch_size=4
api_config_path="examples/evaluate_naive_rag_on_locomo/api_config.json"
visual_memory_config_path="examples/evaluate_naive_rag_on_locomo/visual_memory_config.json"
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
    --visual-memory-config-path "$visual_memory_config_path" \
