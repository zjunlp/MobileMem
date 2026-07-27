
#!/usr/bin/env bash
# 批量跑 Long-Context evaluation 脚本
#
# 专为 long_context baseline 设计，启动 multi-qa batching 并按模型设定默认批大小：
#   GPT → 每批 20 问，Qwen → 每批 10 问
#
# 用法:
#   bash scripts/run_long_context.sh --qa-model gpt-5.4-mini
#   bash scripts/run_long_context.sh --qa-model all
#   bash scripts/run_long_context.sh --users 0 1 2 --qa-model qwen3-vl-8b-instruct
set -euo pipefail

export HF_ENDPOINT=https://hf-mirror.com
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_DATASETS_OFFLINE=1
export LITELLM_LOCAL_MODEL_COST_MAP=True
export LITELLM_OFFLINE_MODE=1
export PYTHONUNBUFFERED=1

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# ── 默认值 ──
QA_MODEL="all"
TOP_K=15
USERS=(0 1 2 3 4 5 6 7 10 11 12 13 14 15 16 17)
MAX_PARALLEL=2
NO_IMAGE=false
NO_INTERMEDIATE=false
MAX_TOTAL_TOKENS=""
RESERVE_FOR_OUTPUT=""
DEBUG=false
API_CONFIG_PATH="api.json"

# Long-Context 固定参数
BASELINE="long_context"
ENV_NAME="long_context"
MAX_CTX_TOKENS=110000

# ── 解析参数 ──
while [ $# -gt 0 ]; do
    case "$1" in
        --qa-model)         QA_MODEL="$2";         shift 2 ;;
        --top-k)            TOP_K="$2";            shift 2 ;;
        --users)            shift; USERS=(); while [ $# -gt 0 ] && [[ "$1" != --* ]]; do USERS+=("$1"); shift; done ;;
        --max-parallel)     MAX_PARALLEL="$2";     shift 2 ;;
        --no-image)         NO_IMAGE=true;         shift ;;
        --no-intermediate)   NO_INTERMEDIATE=true;  shift ;;
        --max-total-tokens) MAX_TOTAL_TOKENS="$2"; shift 2 ;;
        --reserve-for-output) RESERVE_FOR_OUTPUT="$2"; shift 2 ;;
        --debug)            DEBUG=true;            shift ;;
        --api-config)       API_CONFIG_PATH="$2";  shift 2 ;;
        --help|-h)
            echo "用法: bash $0 [选项]"
            echo "  --qa-model      模型 (默认 all=同时跑 gpt+qwen)"
            echo "  --top-k         top-k (默认 20)"
            echo "  --users         用户列表 (默认 0-19)，如 --users 0 1 2"
            echo "  --max-parallel  最大并行数 (默认 2)"
            echo "  --no-image          不包含 base64 图片"
            echo "  --no-intermediate   不保存中间 predictions 文件"
            echo "  --debug             打印完整 API response"
            echo "  --max-total-tokens Qwen 总 token 预算"
            echo "  --reserve-for-output Qwen 输出预留 token"
            echo "  --api-config    API 配置文件路径 (默认 api.json)"
            exit 0 ;;
        *) echo "❌ 未知参数: $1"; exit 1 ;;
    esac
done

PY="python"

LOG_DIR="$ROOT/logs"
OUTPUT_DIR="$ROOT/output"
SAVE_DIR="${OUTPUT_DIR}/long_context/shared"

mkdir -p "$LOG_DIR"

# ── 解析模型列表 ──
MODELS=()
if [ "$QA_MODEL" = "all" ]; then
    MODELS=("gpt-5.4-mini" "qwen3-vl-8b-instruct")
else
    MODELS=("$QA_MODEL")
fi

echo "=============================================="
echo "  Baseline:   long_context"
echo "  QA Model:   $QA_MODEL"
echo "  Top-k:      $TOP_K"
echo "  Users:      ${USERS[*]}"
echo "  Max para:   $MAX_PARALLEL"
echo "=============================================="

# ── 组装 eval 参数 ──
build_eval_flags() {
    local model="$1"
    local flags=""
    local batch_size

    $NO_IMAGE         && flags="$flags --no-image"
    $NO_INTERMEDIATE  && flags="$flags --no-intermediate"
    $DEBUG            && flags="$flags --debug"

    # 按模型设定多问题批大小
    if [[ "$model" == gpt* ]]; then
        batch_size=200
    elif [[ "$model" == qwen* ]]; then
        batch_size=100
    else
        batch_size=20
    fi
    flags="$flags --multi-qa-batch-size $batch_size"

    # GPT 不使用 max_context_tokens（模型上下文足够大）
    # Qwen 需要 token 预算控制
    if [[ "$model" == qwen* ]]; then
        [ -n "$MAX_TOTAL_TOKENS" ] && flags="$flags --max-total-tokens $MAX_TOTAL_TOKENS"
        [ -n "$RESERVE_FOR_OUTPUT" ] && flags="$flags --reserve-for-output $RESERVE_FOR_OUTPUT"
        # Qwen 显存有限，需要截断到 110K tokens
        flags="$flags --max-context-tokens $MAX_CTX_TOKENS"
    fi

    echo "$flags"
}

# ── 执行 eval（单个 user + 单个 model） ──
run_user_eval() {
    local uid="$1"
    local model="$2"
    local user_dir="${SAVE_DIR}/u${uid}"
    local search_results="${user_dir}/${TOP_K}_0_1.json"
    local model_safe="${model//./-}"

    if [ ! -f "$search_results" ]; then
        echo "[u${uid}] search 结果不存在: $search_results"
        return
    fi

    local eval_flags
    eval_flags=$(build_eval_flags "$model")

    local log_file="$LOG_DIR/evaluation_long_context_u${uid}_${model_safe}.log"

    echo "[u${uid}] Evaluating $model (multi-qa-batch-size: $(echo "$eval_flags" | grep -oP 'multi-qa-batch-size \K\d+')) ..."

    # shellcheck disable=SC2086
    $PY memory_evaluation.py \
        --search-results-path "$search_results" \
        --dataset-type "LoCoMo" \
        --qa-model "$model" \
        --judge-model "gpt-5.4-mini" \
        --qa-batch-size 4 \
        --judge-batch-size 4 \
        --api-config-path "$API_CONFIG_PATH" \
        $eval_flags \
        2>&1 | tee "$log_file"

    local stat_file
    stat_file=$(grep -oP 'res/\S+_evaluation_statistics\.json' "$log_file" 2>/dev/null || true)
    if [ -n "$stat_file" ]; then
        echo "[u${uid}] ✅ $model done, stat: $stat_file"
    else
        echo "[u${uid}] ⚠️  $model 可能未成功, 检查 $log_file"
    fi
}

# ── 遍历 user + model，并行执行 ──
pids=()
for uid in "${USERS[@]}"; do
    for model in "${MODELS[@]}"; do
        while [ ${#pids[@]} -ge $MAX_PARALLEL ]; do
            alive=()
            for pid in "${pids[@]}"; do
                kill -0 "$pid" 2>/dev/null && alive+=("$pid")
            done
            pids=("${alive[@]}")
            sleep 5
        done

        run_user_eval "$uid" "$model" &
        pids+=($!)
    done
done

echo "等待所有 eval 完成..."
for pid in "${pids[@]}"; do
    wait "$pid" 2>/dev/null || true
done
echo "✅ 全部完成"
