#!/usr/bin/env bash
# Stage 1: Memory Construction for Mem0 on LoCoMo.
# It samples 2 trajectories from the full dataset and processes them
# with a single process and 2 workers.
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

memory_type="Mem0"
dataset_type="LoCoMo"
dataset_path="data/Locomo/locomo_${USER_ID}.json"
# dataset_path="/root/MemBase-main/data/data_locomo/locomo_img.json" 
#dataset_path="/root/MemBase-main/data/data_locomo/locomo10.json"# 原 locomo
config_path="examples/evaluate_mem0_on_locomo/mem0_config.json"
num_workers=1
sample_size=1
log_dir="$ROOT/logs"
token_cost_file="$ROOT/logs/token_cost"
# ========================================================
set -euo pipefail
cd "$(dirname "$0")/../.."

[ ! -d "$log_dir" ] && mkdir -p "$log_dir"

log_file="${log_dir}/process_1.log"
[ ! -f "$log_file" ] && touch "$log_file"

nohup python memory_construction.py \
    --memory-type "$memory_type" \
    --dataset-type "$dataset_type" \
    --dataset-path "$dataset_path" \
    --config-path "$config_path" \
    --num-workers "$num_workers" \
    --sample-size "$sample_size" \
    --token-cost-save-filename "$token_cost_file" \
> "$log_file" 2>&1 &
echo $! > "${log_dir}/process_1.pid"
