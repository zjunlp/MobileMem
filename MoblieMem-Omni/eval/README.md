# MemBase Usage Guide

This document explains how to run the complete MemBase workflow in the current repository:

```text
Stage5/Stage6 data
    -> Convert to LoCoMo
    -> Construction (build memory)
    -> Search (retrieve memory)
    -> Evaluation (answer, judge, F1/BLEU)
    -> Review and aggregate results
```

The instructions apply to:

```text
memBase-longcontext/memBase-main/
```

## 1. Main Files

| File | Purpose |
|---|---|
| `data/Jsonl2Locomo.py` | Converts the current Stage5/Stage6 JSONL data into per-user LoCoMo JSON files |
| `data/Raw2Locomo.py` | Implements field conversion and question-type mapping |
| `run_baseline.sh` | Unified entry point for one baseline and one user |
| `memory_construction.py` | Stage 1: memory construction |
| `memory_search.py` | Stage 2: memory retrieval |
| `memory_evaluation.py` | Stage 3: answering, judging, F1/BLEU, and statistics |
| `scripts/run_cons.sh` | Parallel multi-user construction |
| `scripts/run_search.sh` | Parallel multi-user retrieval |
| `scripts/run_evaluation.sh` | Parallel multi-user and multi-model evaluation |
| `examples/evaluate_*_on_locomo/` | Per-baseline configuration and stage scripts |
| `envs/*_requirements.txt` | Per-baseline Python dependencies |

## 2. Supported Baselines

| `--baseline` | Method | Recommended conda environment | Requirements file |
|---|---|---|---|
| `long_context` | Long-Context | `long_context` | `envs/long_context_requirements.txt` |
| `naive_rag` | NaiveRAG | `naive_rag` | `envs/rag_requirements.txt` |
| `amem` | A-MEM | `amem` | `envs/amem_requirements.txt` |
| `mem0` | Mem0 | `mem0` | `envs/mem0_requirements.txt` |
| `langmem` | LangMem | `langmem` | `envs/langmem_requirements.txt` |
| `hipporag` | HippoRAG2 | `hipporag` | `envs/hipporag_requirements.txt` |
| `evermemos` | EverMemOS | `evermemos` | `envs/evermemos_requirements.txt` |
| `memos` | MemOS | `memos` | `envs/memos_requirements.txt` |

Some methods require additional services:

- HippoRAG2, Mem0, EverMemOS, and MemOS may require a local embedding or vLLM service.
- MemOS may also require Neo4j.
- Refer to the corresponding `examples/evaluate_*_on_locomo/README.md` for method-specific setup.

## 3. Environment Setup

### 3.1 Create an Environment

Long-Context example:

```bash
conda create -n long_context python=3.12 -y
conda activate long_context
pip install -r envs/long_context_requirements.txt
```

NaiveRAG example:

```bash
conda create -n naive_rag python=3.12 -y
conda activate naive_rag
pip install -r envs/rag_requirements.txt
```

### 3.2 Verify the Environment

```bash
which python
python --version
python -c "import membase; print('MemBase import OK')"
```

The automatic conda environment setup and activation call in the current `run_baseline.sh` is commented out. You must activate the correct environment before running the pipeline. Do not run experiments directly in the `base` environment.

### 3.3 Bash Requirement

`run_baseline.sh` and `scripts/*.sh` require Bash:

- On Linux, run them directly with Bash.
- On Windows, use Git Bash or WSL. Git Bash paths can use `G:/bench/...`; WSL paths usually use `/mnt/g/bench/...`.
- `data/Jsonl2Locomo.py` can be run directly from PowerShell.

## 4. API Configuration

Evaluation reads the `api_config.json` associated with the selected baseline, for example:

```text
examples/evaluate_long_context_on_locomo/api_config.json
```

Use placeholders in a public repository:

```json
{
  "api_keys": ["YOUR_API_KEY"],
  "base_urls": ["https://YOUR_OPENAI_COMPATIBLE_ENDPOINT/v1"]
}
```

Environment variables can also be configured for compatible components:

```bash
export OPENAI_API_KEY="YOUR_API_KEY"
export OPENAI_BASE_URL="https://YOUR_OPENAI_COMPATIBLE_ENDPOINT/v1"
```

Do not commit real credentials, personal proxy addresses, or private service endpoints to GitHub.

## 5. Convert Data to LoCoMo

### 5.1 Current Data Layout

```text
Stage5:  G:/bench/memory_dataset/0424/data/stage5/stage5_all_users.jsonl
Stage6:  G:/bench/memory_dataset/0424/data/stage6/
Stage10: G:/bench/memory_dataset/0424/data/stage10_image_summaries.jsonl
Output:  data/Locomo/locomo_u{uid}.json
```

### 5.2 Convert uuid0 from PowerShell

```powershell
Set-Location "G:\bench\memory_dataset\memBase-longcontext\memBase-main"
conda activate long_context

python .\data\Jsonl2Locomo.py `
  --stage5 "G:\bench\memory_dataset\0424\data\stage5\stage5_all_users.jsonl" `
  --stage6-dir "G:\bench\memory_dataset\0424\data\stage6" `
  --stage10 "G:\bench\memory_dataset\0424\data\stage10_image_summaries.jsonl" `
  --output-dir ".\data\Locomo" `
  --users 0
```

### 5.3 Convert Multiple Users from Bash

```bash
python data/Jsonl2Locomo.py \
  --stage5 /path/to/stage5_all_users.jsonl \
  --stage6-dir /path/to/stage6 \
  --stage10 /path/to/stage10_image_summaries.jsonl \
  --output-dir data/Locomo \
  --users 0 1 2
```

Common conversion arguments:

| Argument | Description |
|---|---|
| `--stage5` | Stage5 wrapped JSON, JSON list, or one-persona-per-line JSONL |
| `--stage6-jsonl` | One Stage6 group/all JSONL file |
| `--stage6-dir` | Directory containing `stage6_questions_uuid{uid}.jsonl` |
| `--stage10` | Optional image-caption JSONL; pass an empty string to disable captions |
| `--output-dir` | LoCoMo output directory |
| `--users` | Selected UUIDs; omit to convert all users |
| `--no-image` | Remove image paths and caption fields |
| `--no-caption-in-text` | Do not append image captions to turn text |

### 5.4 Output Format and Type Mapping

Each output file is a JSON array containing one user sample:

```text
data/Locomo/locomo_u0.json
data/Locomo/locomo_u1.json
...
```

Questions use seven categories:

| category | question_type |
|---:|---|
| 1 | `multi_hop` |
| 2 | `temporal_reasoning` |
| 3 | `abstention` |
| 4 | `single_hop` |
| 5 | `implicit_preference` |
| 6 | `visual_reasoning` / `multi_visual_reasoning` |
| 7 | `knowledge_update` |

### 5.5 Validate Converted Data

PowerShell example:

```powershell
$data = Get-Content ".\data\Locomo\locomo_u0.json" -Raw -Encoding utf8 | ConvertFrom-Json
$sample = $data[0]

"QA count: $($sample.qa.Count)"
"Session count: $($sample.conversation.n_session)"
$sample.qa | Group-Object category | Sort-Object Name | Select-Object Name, Count
```

Verify at least the following:

- The file can be read as UTF-8.
- The session count matches Stage5.
- The QA count matches the selected Stage6 data.
- Categories only contain values 1 through 7.
- Referenced image files exist when images are enabled.

## 6. Run a Single-User Pipeline

### 6.1 Long-Context Example

```bash
conda activate long_context

bash run_baseline.sh \
  --stage pipeline \
  --baseline long_context \
  --user-id u0 \
  --root ./runs/long_context_u0 \
  --top-k 20 \
  --qa-model gpt-5.4-mini \
  --judge-model qwen3-14b \
  --multi-qa-batch-size 20 \
  --no-image \
  --eval-output-dir ./runs/long_context_u0/evaluation
```

### 6.2 NaiveRAG Example

```bash
conda activate naive_rag

bash run_baseline.sh \
  --stage pipeline \
  --baseline naive_rag \
  --user-id u0 \
  --root ./runs/naive_rag_u0 \
  --top-k 20 \
  --qa-model gpt-5.4-mini \
  --judge-model qwen3-14b \
  --num-workers 2 \
  --no-image \
  --eval-output-dir ./runs/naive_rag_u0/evaluation
```

For the first run:

1. Run only uuid0.
2. Inspect the first few constructed memories and retrieval results.
3. Verify answer and judge formats before starting a batch.
4. Do not increase both user-level parallelism and internal workers aggressively.

## 7. Run Individual Stages

### 7.1 Stage 1: Construction

```bash
bash run_baseline.sh \
  --stage construction \
  --baseline naive_rag \
  --user-id u0 \
  --root ./runs/naive_rag_u0 \
  --num-workers 2
```

Primary output:

```text
runs/naive_rag_u0/output/rag/shared/u0/LoCoMo_stage_1.json
```

The selected baseline also saves its own persistent memory files.

### 7.2 Stage 2: Search

```bash
bash run_baseline.sh \
  --stage search \
  --baseline naive_rag \
  --user-id u0 \
  --root ./runs/naive_rag_u0 \
  --top-k 20 \
  --num-workers 2
```

Primary output:

```text
runs/naive_rag_u0/output/rag/shared/u0/20_0_1.json
```

Inspect a sample and verify:

- Every question has retrieval results.
- Retrieved memories belong to the correct user.
- The number of memories follows the expected top-k limit.
- Image paths and timestamps are correct when visual retrieval is enabled.

### 7.3 Stage 3: Evaluation

```bash
bash run_baseline.sh \
  --stage evaluation \
  --baseline naive_rag \
  --user-id u0 \
  --root ./runs/naive_rag_u0 \
  --top-k 20 \
  --qa-model gpt-5.4-mini \
  --judge-model qwen3-14b \
  --no-image \
  --eval-output-dir ./runs/naive_rag_u0/evaluation
```

Evaluation performs the following steps:

1. Builds answer context from retrieved memories.
2. Calls the QA model.
3. Saves an intermediate prediction file.
4. Calls the judge model.
5. Computes F1 and BLEU.
6. Aggregates metrics by question type.

## 8. Common Arguments

| Argument | Default | Description |
|---|---:|---|
| `--stage` | `pipeline` | `construction`, `search`, `evaluation`, or `pipeline` |
| `--baseline` | required | Memory method |
| `--user-id` | `u10` | User ID, including the `u` prefix |
| `--root` | `.` | Root directory for logs and outputs |
| `--top-k` | 20 | Number of memories retrieved per question |
| `--qa-model` | `gpt-5.4-mini` | Answer model |
| `--judge-model` | `qwen3-14b` | Judge model |
| `--num-workers` | 1 | Construction/Search worker count |
| `--sample-size` | 1 | Number of dataset samples; per-user LoCoMo normally uses 1 |
| `--no-caption` | false | Exclude image captions |
| `--no-image` | false | Do not send base64 images |
| `--visual-retriever` | `off` | `off`, `siglip2`, or `internvideo2` |
| `--multi-qa-batch-size` | 1 | Group multiple questions in one call; useful for Long-Context |
| `--max-total-tokens` | unset | Total token budget for Qwen VL |
| `--reserve-for-output` | unset | Tokens reserved for model output |
| `--eval-output-dir` | machine-specific | Pass explicitly to avoid writing to an unexpected directory |

## 9. Multimodal and Visual Retrieval

### 9.1 Text/Caption-Only Evaluation

Do not send original images; use text and merged captions:

```bash
bash run_baseline.sh \
  --stage evaluation \
  --baseline naive_rag \
  --user-id u0 \
  --no-image
```

Remove both captions and images:

```bash
bash run_baseline.sh \
  --stage pipeline \
  --baseline naive_rag \
  --user-id u0 \
  --no-caption \
  --no-image
```

### 9.2 SigLIP2 Retrieval

```bash
bash run_baseline.sh \
  --stage evaluation \
  --baseline naive_rag \
  --user-id u0 \
  --visual-retriever siglip2
```

### 9.3 InternVideo2 Retrieval

```bash
bash run_baseline.sh \
  --stage evaluation \
  --baseline naive_rag \
  --user-id u0 \
  --visual-retriever internvideo2
```

Visual retrieval configuration is stored at:

```text
examples/evaluate_{baseline}_on_locomo/visual_memory_config.json
```

Important fields include `enabled`, `retriever_type`, `image_root`, `top_k`, `batch_size`, `device`, and `rebuild_index`.

## 10. Multi-User Parallel Runs

Validate one user before starting parallel jobs:

```bash
# Construction
bash scripts/run_cons.sh \
  --baseline naive_rag \
  --users 0 1 2 \
  --max-parallel 2 \
  --num-workers 1

# Search
bash scripts/run_search.sh \
  --baseline naive_rag \
  --users 0 1 2 \
  --max-parallel 2 \
  --num-workers 1 \
  --top-k 20

# Evaluation
bash scripts/run_evaluation.sh \
  --baseline naive_rag \
  --users 0 1 2 \
  --max-parallel 2 \
  --top-k 20 \
  --qa-model gpt-5.4-mini \
  --judge-model qwen3-14b \
  --no-image \
  --eval-output-dir ./runs/batch_evaluation
```

Parallelism recommendations:

- Start Construction/Search with `--max-parallel 2 --num-workers 1`.
- Monitor CPU, memory, GPU memory, API rate limits, and vector-store locks.
- Increase concurrency gradually. Avoid increasing user parallelism and internal workers at the same time.

## 11. Output Layout

A typical single-user output structure is:

```text
{ROOT}/
├── logs/
│   ├── construction_{env}.log
│   ├── search_{env}.log
│   └── evaluation_{env}_{model}.log
├── output/
│   └── {baseline_output}/
│       └── shared/
│           └── u0/
│               ├── LoCoMo_stage_1.json
│               ├── 20_0_1.json
│               ├── 20_0_1_{model}_predictions.json
│               └── 20_0_1_{model}_evaluation.json
└── res/
    └── u0/
        └── u0_{model}_{baseline}_evaluation_statistics.json
```

When `--eval-output-dir` is set, final evaluation results and statistics are also copied to that directory.

## 12. Validate Results

Check at least the following:

1. `LoCoMo_stage_1.json` exists and is not empty.
2. The number of search results matches the QA count.
3. Every evaluation item contains `qa_pair`, `prediction`, `metrics`, and `retrieved_memories`.
4. `metrics` includes the judge metric, F1, and BLEU.
5. `total_questions` in the statistics file matches the result count.
6. `per_question_type` covers the expected seven question types.

PowerShell example:

```powershell
$result = Get-Content ".\runs\naive_rag_u0\output\rag\shared\u0\20_0_1_gpt-5-4-mini_evaluation.json" -Raw -Encoding utf8 | ConvertFrom-Json
"Result count: $($result.Count)"
$result | Select-Object -First 3 | ForEach-Object {
    [pscustomobject]@{
        Question = $_.qa_pair.question
        Prediction = $_.prediction
        F1 = $_.metrics.f1.value
    }
}
```

## 13. Resume and Rerun Behavior

### 13.1 Current Behavior

- Construction loads existing memory and skips rebuilding when possible. `run_baseline.sh` also checks for `LoCoMo_stage_1.json`.
- Search is skipped by `run_baseline.sh` when `{top_k}_0_1.json` already exists.
- Evaluation first completes all QA predictions, saves the prediction file, and then runs the judge. It does not currently checkpoint every question.

Therefore:

- The Construction and Search entry points are safe to rerun.
- Long Evaluation jobs should run inside tmux to survive terminal disconnections.
- If Evaluation is interrupted before its output is saved, the current Evaluation stage may need to be rerun.

### 13.2 Force a Rerun

Delete only the output of the stage that must be rerun:

```bash
# Rerun Search
rm output/rag/shared/u0/20_0_1.json

# Rerun Evaluation
rm output/rag/shared/u0/20_0_1_gpt-5-4-mini_evaluation.json
rm output/rag/shared/u0/20_0_1_gpt-5-4-mini_predictions.json
```

Confirm the path, baseline, and user ID before deleting files.

## 14. Run Long Jobs with tmux

```bash
tmux new -s membase_u0
conda activate long_context
cd /path/to/memBase-main

bash run_baseline.sh \
  --stage pipeline \
  --baseline long_context \
  --user-id u0 \
  --root ./runs/long_context_u0 \
  --qa-model gpt-5.4-mini \
  --judge-model qwen3-14b \
  --no-image \
  --eval-output-dir ./runs/long_context_u0/evaluation
```

Detach with `Ctrl+B`, then `D`.

Reattach with:

```bash
tmux attach -t membase_u0
```

## 15. Logging

MemBase writes stage logs to `{ROOT}/logs/`. Use a separate root directory for each experiment:

```text
runs/{baseline}_{user}_{date}/
```

It is useful to maintain two additional files:

- `summary.log`: command, parameters, timestamps, stage status, and final metrics.
- `detail.log`: complete terminal output and stack traces.

Example:

```bash
RUN_DIR="./runs/long_context_u0_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RUN_DIR/logs"

echo "baseline=long_context user=u0 top_k=20" > "$RUN_DIR/logs/summary.log"

bash run_baseline.sh \
  --stage pipeline \
  --baseline long_context \
  --user-id u0 \
  --root "$RUN_DIR" \
  --top-k 20 \
  --qa-model gpt-5.4-mini \
  --judge-model qwen3-14b \
  --no-image \
  --eval-output-dir "$RUN_DIR/evaluation" \
  2>&1 | tee "$RUN_DIR/logs/detail.log"

echo "exit_code=${PIPESTATUS[0]} end=$(date -Iseconds)" >> "$RUN_DIR/logs/summary.log"
```

Archive or trim detail logs after they grow beyond approximately 3 MB, keeping the most recent log needed for debugging.

## 16. Troubleshooting

### 16.1 Incorrect Conda Environment

Symptoms include missing dependencies, incompatible package versions, or unavailable CUDA.

```bash
conda activate {baseline_env}
which python
python -c "import membase; print('OK')"
```

### 16.2 LoCoMo File Not Found

The filename must include the `u` prefix:

```text
data/Locomo/locomo_u0.json
```

The command must also use:

```bash
--user-id u0
```

### 16.3 Construction or Search Is Skipped

This is the idempotent behavior of the entry script. Check whether the expected output already exists. Delete only that stage output when a rerun is required.

### 16.4 Evaluation Was Written to an Unexpected Directory

The current shell scripts contain a machine-specific default `EVAL_OUTPUT_DIR`. Always pass an explicit value:

```bash
--eval-output-dir ./runs/current/evaluation
```

### 16.5 API Failure or Rate Limiting

- Reduce `--max-parallel` and `--num-workers`.
- Validate one user and a small question set first.
- Check the endpoint, model name, and quota.
- Record rare failures in the detailed log and review them after the batch.

### 16.6 Qwen Output Parsing Failure

- Run `memory_evaluation.py --debug` to inspect raw responses.
- Confirm that the model name matches the OpenAI-compatible endpoint.
- Long-Context can use `--multi-qa-batch-size`, but validate JSON stability with a small batch first.

### 16.7 Missing Images or Invalid Paths

- Sample-check `image_path` after conversion.
- Use `--no-image` for text-only experiments.
- Confirm `image_root` and index paths before enabling visual retrieval.

## 17. Recommended Execution Order

```text
1. Activate the correct conda environment
2. Configure the API without committing credentials
3. Convert uuid0 to data/Locomo/locomo_u0.json
4. Validate sessions, QA count, categories, and image paths
5. Run uuid0 Construction
6. Inspect LoCoMo_stage_1.json
7. Run uuid0 Search
8. Inspect a retrieval sample
9. Run uuid0 Evaluation
10. Validate predictions, judge results, F1/BLEU, and statistics
11. Start multi-user jobs only after quality checks pass
12. Preserve summary/detail logs and final configuration
```

## 18. Minimal Checklist

```text
[ ] The active environment is not base
[ ] data/Locomo/locomo_u0.json exists
[ ] Public configuration files do not contain real credentials
[ ] --root and --eval-output-dir are explicitly set
[ ] The first run only uses u0
[ ] Construction output exists
[ ] Search count and content are reasonable
[ ] Evaluation result count is correct
[ ] Judge, F1, and BLEU fields exist
[ ] per_question_type covers the expected types
[ ] Long jobs run inside tmux
[ ] summary.log and detail.log are preserved
```
