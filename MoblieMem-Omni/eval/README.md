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

This submission does not include full construction/retrieval implementations for every memory method. Use the original [zjunlp/MemBase](https://github.com/zjunlp/MemBase) three-stage workflow, or follow each method's upstream repository.

Text-only methods and references:

| Method | Reference |
|---|---|
| Long-Context | Built-in long-context baseline in the original MemBase examples |
| NaiveRAG | Built-in naive-rag baseline in the original MemBase examples |
| A-MEM | <https://github.com/agiresearch/A-mem> |
| LangMem | <https://github.com/langchain-ai/langmem> |
| Mem0 | <https://github.com/mem0ai/mem0> |
| MemOS | <https://github.com/MemTensor/MemOS> |
| EverMemOS | <https://github.com/EverMind-AI/EverOS> |
| HippoRAG2 | <https://github.com/OSU-NLP-Group/HippoRAG> |

For each method:

1. Read `data/Locomo/locomo_u{uid}.json`.
2. Build user memory with the method's own code.
3. Retrieve memories for each question.
4. Format question, gold answer, retrieved memories, and model answer for `evaluator.py`.

If using the original MemBase project, refer to its `examples/evaluate_*_on_locomo/` construction/search instructions. Those scripts are not duplicated in this submission.

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
