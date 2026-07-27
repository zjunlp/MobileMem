# Evaluate Mem0 on LoCoMo

This example walks through evaluating the **Mem0** memory layer on the **LoCoMo** dataset. It covers how to configure Mem0 (including deploying an embedding model locally with vLLM and enabling the Kuzu graph store), how to use a custom question-answering prompt from the [Mem0 paper](https://arxiv.org/pdf/2504.19413), and how to filter specific question types at the retrieval stage.

---

## Prerequisites

- **Python >= 3.12** with the Mem0 environment (`pip install -r envs/mem0_requirements.txt`).
- **vLLM** installed in the environment (`pip install vllm`).
- **Qwen3-Embedding-4B** downloaded locally. See the [example](../download_models/) for how to download it.

### Create Environment

```bash
conda create -n membase-mem0 python=3.12 -y
conda activate membase-mem0
pip install -r envs/mem0_requirements.txt
```

---

## Step 1: Serve the Embedding Model with vLLM

Start the vLLM embedding server before running the pipeline:

```bash
CUDA_VISIBLE_DEVICES=0 vllm serve pretrained_models/Qwen3-Embedding-4B \
    --port 8008 \
    --served-model-name Qwen3-Embedding-4B \
    --gpu-memory-utilization 0.5 \
    --hf_overrides '{"is_matryoshka": true}'
```

This exposes an OpenAI-compatible embedding endpoint at `http://localhost:8008/v1`. The Mem0 config uses the `openai` embedder provider to connect to it.

> **Note**: The `--hf_overrides '{"is_matryoshka": true}'` flag is required for Qwen3-Embedding models to enable Matryoshka representation support.

---

## Step 2: Download the Dataset

Download the LoCoMo dataset from GitHub:

> https://github.com/snap-research/locomo/tree/main/data

Save it to a local path, e.g., `/path/to/locomo.json`.

---

## Step 3: Configure Mem0

See [`mem0_config.json`](mem0_config.json). The full list of configuration fields can be found in `membase/configs/mem0.py`.

### Embedding Configuration

Mem0 uses the `openai` embedder provider to connect to any OpenAI-compatible embedding API (including vLLM). The `embedding_config` section specifies the vLLM endpoint:

```json
"embedder_provider": "openai",
"embedding_model": "Qwen3-Embedding-4B",
"embedding_model_dims": 2560,
"embedding_config": {
    "openai_base_url": "http://localhost:8008/v1",
    "api_key": "EMPTY"
}
```

`embedding_model` must match the `--served-model-name` in the vLLM command. `api_key` can be `"EMPTY"` for local servers.

Alternatively, you can use a local Sentence Transformer model without vLLM:

```json
"embedder_provider": "huggingface",
"embedding_model": "all-MiniLM-L6-v2",
"embedding_model_dims": 384,
"embedding_config": {
    "model_kwargs": {"device": "cuda"}
}
```

> **Note**: When switching embedding models, remember to update `embedding_model_dims` accordingly.

### LLM Configuration

In this example, `llm_provider` is set to `"openai"`, and the API key and base URL are specified directly in [`mem0_config.json`](mem0_config.json). Replace `YOUR_OPENAI_API_KEY` and `YOUR_OPENAI_API_BASE` with your actual credentials.

### Graph Store

This example enables the **Kuzu** graph store, a local file-based graph database that requires no external server. The database directory is automatically created under the user directory. To disable the graph store, simply remove the `graph_store_provider` field from the config (Mem0 will then operate with a flat memory structure backed only by the vector store).

### Vector Store

Mem0 uses **Qdrant in local mode** (`on_disk=True`) by default, which stores data directly on disk without requiring an external Qdrant server. Each user's memory is stored in its own directory, so multiple processes can safely run in parallel as long as they handle non-overlapping trajectory ranges.

---

## Step 4: Run Memory Construction (Stage 1)

Edit [`run_construction.sh`](run_construction.sh) to set your dataset path and API credentials, then run:

```bash
bash examples/evaluate_mem0_on_locomo/run_construction.sh
```

This samples 2 trajectories from the full LoCoMo dataset via `--sample-size` and processes them with 2 workers in a single process. The sampled dataset is automatically saved to `mem0_output/LoCoMo_stage_1.json` in standardized format for subsequent stages.

---

## Step 5: Run Memory Retrieval (Stage 2)

This stage reads the standardized dataset saved by Stage 1 (with `--dataset-standardized`).

Adversarial questions are excluded via `--question-filter-path`, which points to [`question_filter.py`](question_filter.py). You can modify this filter to target other question types (see `membase/datasets/locomo.py` for all available types).

```bash
bash examples/evaluate_mem0_on_locomo/run_search.sh
```

> **Note**: The `dataset_path` in the search and evaluation scripts must point to the **standardized** dataset produced by Stage 1, not the original raw data file. Because Stage 1 samples a subset of trajectories from the full dataset, memory is only constructed for that subset. The standardized file records exactly which trajectories are sampled, so subsequent stages must use it to stay consistent.

---

## Step 6: Run Evaluation (Stage 3)

Edit [`run_evaluation.sh`](run_evaluation.sh) and run:

```bash
bash examples/evaluate_mem0_on_locomo/run_evaluation.sh
```

This example uses a custom question-anwering prompt from the Mem0 paper via `--prompt-template`, which is defined in [`qa_prompt.py`](qa_prompt.py). The prompt instructs the model to resolve relative time references and leverage knowledge graph relations.

> **Note**: Make sure to set `--dataset-type LoCoMo` so that the correct judge prompt template and response parser are used.

