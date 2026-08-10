# MemBase Evaluation Files

```text
eval/
├── Jsonl2Locomo.py
├── evaluator.py
└── question_answering_and_judge_prompts.txt
```

The workflow has three steps:

```text
Stage5/Stage6 data -> convert to LoCoMo -> build/retrieve memories with external methods -> evaluate with eval code
```

This guide only covers text-only evaluation. Multimodal image input, visual retrieval, and image indexes are not included for now.

## Step 1. Convert to LoCoMo

Use:

```text
eval/Jsonl2Locomo.py
```

Example:

```bash
python eval/Jsonl2Locomo.py \
  --stage5 path/to/stage5_all_users.jsonl \
  --stage6-dir path/to/stage6 \
  --stage10 "" \
  --output-dir data/Locomo \
  --users 0 \
  --no-image
```

Example output:

```text
data/Locomo/locomo_u0.json
```

Notes:

- Change `--users 0` to multiple users, or omit it to convert all users.
- `--stage10 "" --no-image` keeps the data text-only.
- If only these three files are submitted, `Jsonl2Locomo.py` still needs the LoCoMo field conversion helpers. In the full/local MemBase setup, those helpers come from `Raw2Locomo.py`. If that file is not included, merge the required conversion functions into `Jsonl2Locomo.py` or provide the helper file separately.

## Step 2. Build and Retrieve Memories

The experiments include both textual and multimodal memory methods. Most textual baselines can be run through the unified [zjunlp/MemBase](https://github.com/zjunlp/MemBase) construction, retrieval, and evaluation pipeline. Methods with their own evaluation stack can instead be run from their official repositories.

### Textual Memory Methods

| Method | Repository | Brief Description | Recommended Experiment Entry |
|:-------|:-----------|:------------------|:-----------------------------|
| Long Context | [zjunlp/MemBase](https://github.com/zjunlp/MemBase) | Places the complete conversation history in the model context without building an external memory index | [Unified MobileMem-Omni example in MemBase](https://github.com/zjunlp/MemBase/tree/main/examples/evaluate_memory_systems_on_mobilemem_omni) |
| NaiveRAG | [zjunlp/MemBase](https://github.com/zjunlp/MemBase) | Embeds conversation chunks and retrieves the top-k chunks for question answering | [Unified MobileMem-Omni example in MemBase](https://github.com/zjunlp/MemBase/tree/main/examples/evaluate_memory_systems_on_mobilemem_omni) |
| LangMem | [langchain-ai/langmem](https://github.com/langchain-ai/langmem) | Extracts and updates long-term semantic memories for LangGraph agents | [Unified MobileMem-Omni example in MemBase](https://github.com/zjunlp/MemBase/tree/main/examples/evaluate_memory_systems_on_mobilemem_omni) |
| Mem0 | [mem0ai/mem0](https://github.com/mem0ai/mem0) | Maintains extracted user memories with vector or graph-backed retrieval | Use the Mem0 LoCoMo example in MemBase |
| LightMem | [zjunlp/LightMem](https://github.com/zjunlp/LightMem) | A lightweight memory framework with compression, topic segmentation, summarization, and configurable retrieval | Follow LightMem's LoCoMo reproduction scripts under `experiments/` |
| EverMemOS | [EverMind-AI/EverOS](https://github.com/EverMind-AI/EverOS) | A persistent memory system that extracts, organizes, updates, and retrieves long-term user memories | [Unified MobileMem-Omni example in MemBase](https://github.com/zjunlp/MemBase/tree/main/examples/evaluate_memory_systems_on_mobilemem_omni) |
| M²A (w/ Caption) | [Little-Fridge/M2A](https://github.com/Little-Fridge/M2A) | Caption-only M²A setting: visual content is represented by captions and evaluated through the textual memory path | Use the M²A evaluation wrapper with image-caption memories enabled and raw-image retrieval disabled |

### Multimodal Memory Methods

| Method | Repository | Brief Description | Recommended Experiment Entry |
|:-------|:-----------|:------------------|:-----------------------------|
| SigLIP + NaiveRAG | [google-research/big_vision](https://github.com/google-research/big_vision) | Extends NaiveRAG with SigLIP embeddings for text-to-image retrieval | Build separate text and image indexes, retrieve top-k candidates, and pass both to the multimodal QA model |
| UniversalRAG | [wgcyeo/UniversalRAG](https://github.com/wgcyeo/UniversalRAG) | Routes each question to modality- and granularity-specific corpora before retrieval | Adapt the converted MobileMem-Omni corpus to UniversalRAG and run its preprocessing, routing, and evaluation scripts |
| M²A | [Little-Fridge/M2A](https://github.com/Little-Fridge/M2A) | Uses dual-layer raw and semantic memory with text, sparse, and cross-modal retrieval paths | Configure `config.toml` and run the official `M2AEvaluationWrapper` with this evaluator |

### Run Textual Baselines with MemBase

For Long Context, NaiveRAG, LangMem, and EverMemOS, use the complete shared scripts, method-specific entry points, configs, and evaluation instructions in the [unified MobileMem-Omni example in MemBase](https://github.com/zjunlp/MemBase/tree/main/examples/evaluate_memory_systems_on_mobilemem_omni). MobileMem does not duplicate their execution scripts.

For other MemBase-compatible textual methods, the generic pipeline below remains available.

Clone MemBase and create a separate environment for each memory method because their dependencies may conflict:

```bash
git clone https://github.com/zjunlp/MemBase.git
cd MemBase
conda create -n <METHOD>_env python=3.12 -y
conda activate <METHOD>_env
pip install -r envs/<METHOD>_requirements.txt
```

Then run the common three-stage pipeline. Replace `<METHOD>`, `<CONFIG>`, and the generated result paths with the values documented in the corresponding MemBase example:

```bash
# 1. Construct memories from the converted MobileMem-Omni conversations
python memory_construction.py \
  --memory-type <METHOD> \
  --dataset-type locomo \
  --dataset-path /path/to/data/Locomo \
  --config-path <CONFIG>

# 2. Retrieve memories for every evaluation question
python memory_search.py \
  --memory-type <METHOD> \
  --dataset-type locomo \
  --dataset-path /path/to/data/Locomo \
  --config-path <CONFIG> \
  --top-k 10

# 3. Generate answers and calculate the evaluation metrics
python memory_evaluation.py \
  --search-results-path <SEARCH_RESULTS> \
  --dataset-type locomo \
  --qa-model <QA_MODEL> \
  --judge-model <JUDGE_MODEL> \
  --api-config-path <API_CONFIG>
```

Use `python memory_construction.py --help` and `python memory_search.py --help` to list the registered method and dataset names in the checked-out MemBase version.

### Run Methods with Native Repositories

LightMem provides dedicated LoCoMo reproduction scripts:

```bash
git clone https://github.com/zjunlp/LightMem.git
cd LightMem
conda create -n lightmem python=3.11 -y
conda activate lightmem
pip install -e .
cd experiments
python run_lightmem_qwen.py
```

For M²A, install the official repository, configure the language, text-embedding, and multimodal-embedding endpoints, and use its evaluation wrapper:

```bash
git clone https://github.com/Little-Fridge/M2A.git
cd M2A
uv sync
source .venv/bin/activate
# Edit config.toml, then run an evaluation driver based on eval_wrapper.py.
```

For UniversalRAG, follow its native preprocessing → routing → evaluation workflow after adapting MobileMem-Omni's sessions, images, and questions to its corpus format:

```bash
git clone https://github.com/wgcyeo/UniversalRAG.git
cd UniversalRAG
uv sync
source .venv/bin/activate
bash script/1_preprocess.sh
bash script/3_route.sh <ROUTER_MODEL>
bash script/4_eval.sh --model-path <MODEL> --router-model <ROUTER_MODEL> --target <TARGET>
```

The native commands above describe each repository's execution entry. Reproducing the reported MobileMem-Omni numbers additionally requires using the converted MobileMem-Omni data, the same QA backbone and judge model, and the same retrieval settings. Repository-native scripts may therefore require a small dataset adapter rather than running unchanged.

### Common Experiment Options

When adapting an external method to MobileMem-Omni, keep the following experiment settings explicit and consistent:

| Argument | Purpose |
|:---------|:--------|
| `--stage` | Run `construction`, `search`, `evaluation`, or the complete `pipeline` |
| `--method` | Select the memory baseline |
| `--user-id` | Select one converted `locomo_u{ID}.json` file |
| `--top-k` | Set the number of retrieved memories |
| `--qa-model` | Select the model that answers benchmark questions |
| `--judge-model` | Select the model used for LLM-as-a-Judge |
| `--no-image` | Evaluate caption/text memory without sending raw images |
| `--visual-retriever` | Select a visual retriever such as `siglip`, or disable visual retrieval |
| `--output-dir` | Keep generated memories, retrieval results, predictions, metrics, and logs outside the source tree |
| `--resume` | Reuse completed outputs and continue an interrupted run |

The exact flag names depend on the external repository. The table describes the settings that a dataset adapter or experiment launcher should expose; they are not CLI options currently implemented by this directory.

### Output Structure

Keep the artifacts from each method and user separate so that failed stages can be inspected or resumed without repeating the entire experiment:

```text
output/
└── <method>/
    └── <user_id>/
        ├── construction/
        │   └── memory_state.*
        ├── search/
        │   └── top_<k>.json
        ├── evaluation/
        │   ├── predictions.json
        │   └── metrics.json
        └── logs/
```

Construction output is the input to Search, and Search output is the input to Evaluation. When comparing methods, retain the intermediate retrieval results as well as the final scores; this makes it possible to distinguish retrieval failures from answer-generation failures.

### Multimodal Input Modes

Use one of the following input modes consistently across all compared methods:

| Mode | Text Memory | Image Caption | Raw Image |
|:-----|:------------|:--------------|:----------|
| Text-only | Yes | No | No |
| Caption-only | Yes | Yes | No |
| Multimodal | Yes | Yes | Yes |

For multimodal experiments, report the visual retriever and image top-k separately from the text retriever. Do not commit API keys or service credentials; store them in environment variables or an ignored local configuration file.

## Step 3. Evaluate

Use:

```text
eval/evaluator.py
eval/question_answering_and_judge_prompts.txt
```

`evaluator.py`:

- Collects conversations and QA pairs.
- Calls each memory method's `chat()` / `question()` interface.
- Computes F1 and BLEU1.
- Runs LLM-as-a-Judge for `CORRECT` / `WRONG`.
- Aggregates results by the seven question categories.

Prompts are stored in:

```text
eval/question_answering_and_judge_prompts.txt
```

It includes:

- Text-memory QA prompt.
- Multimodal QA prompt text template (not used in the current text-only setup).
- LLM-as-a-Judge prompt.

`evaluator.py` is a class module, not a complete CLI. Your run script should initialize the memory method and judge, for example:

```python
from eval.evaluator import Evaluator

methods = [...]  # memory method instances implementing chat/question/over
judge = ...      # LLMJudge or an equivalent judge object

evaluator = Evaluator(
    methods=methods,
    judge=judge,
    database_root_path=".",
)

result = evaluator.evaluate_file(
    "data/Locomo/locomo_u0.json",
    n_sample_conv=1,
    max_samples=None,
    resume=True,
)
```

Note: `evaluator.py` depends on helper classes such as `LLMJudge` and `RetrievalCache`. If the final package only includes the three files above, provide those helpers as well or import them from the original project environment.
