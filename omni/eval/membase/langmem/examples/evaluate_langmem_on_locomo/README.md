# Evaluate LangMem on LoCoMo

This folder contains a standard 3-stage pipeline for evaluating **LangMem** on **LoCoMo**.

## Create Environment
```bash
conda create -n membase-langmem python=3.12 -y
conda activate membase-langmem
pip install -r envs/langmem_requirements.txt
```

## Files
- langmem_config.json: method config.
- api_config.json: API key and base URL list for QA/judge requests.
- visual_memory_config.json: optional visual memory retriever config.
- run_construction.sh: stage 1 (memory construction).
- run_search.sh: stage 2 (memory retrieval).
- run_evaluation.sh: stage 3 (QA + judge).

## Quick Start
```bash
bash examples/evaluate_langmem_on_locomo/run_construction.sh
bash examples/evaluate_langmem_on_locomo/run_search.sh
bash examples/evaluate_langmem_on_locomo/run_evaluation.sh
```
