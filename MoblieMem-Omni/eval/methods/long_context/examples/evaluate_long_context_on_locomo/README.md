# Evaluate Long-Context on LoCoMo

This folder contains a standard 3-stage pipeline for evaluating **Long-Context** on **LoCoMo**.

## Create Environment
```bash
conda create -n membase-long-context python=3.12 -y
conda activate membase-long-context
pip install -r envs/long_context_requirements.txt
```

## Files
- long_context_config.json: method config.
- api_config.json: API key and base URL list for QA/judge requests.
- visual_memory_config.json: optional visual memory retriever config.
- run_construction.sh: stage 1 (memory construction).
- run_search.sh: stage 2 (memory retrieval).
- run_evaluation.sh: stage 3 (QA + judge).

## Quick Start
```bash
bash examples/evaluate_long_context_on_locomo/run_construction.sh
bash examples/evaluate_long_context_on_locomo/run_search.sh
bash examples/evaluate_long_context_on_locomo/run_evaluation.sh
```
