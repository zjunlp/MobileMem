# Evaluate NaiveRAG on LoCoMo

This folder contains a standard 3-stage pipeline for evaluating **NaiveRAG** on **LoCoMo**.

## Create Environment
```bash
conda create -n membase-rag python=3.12 -y
conda activate membase-rag
pip install -r envs/rag_requirements.txt
```

## Files
- naive_rag_config.json: method config.
- api_config.json: API key and base URL list for QA/judge requests.
- visual_memory_config.json: optional visual memory retriever config.
- run_construction.sh: stage 1 (memory construction).
- run_search.sh: stage 2 (memory retrieval).
- run_evaluation.sh: stage 3 (QA + judge).

## Quick Start
```bash
bash examples/evaluate_naive_rag_on_locomo/run_construction.sh
bash examples/evaluate_naive_rag_on_locomo/run_search.sh
bash examples/evaluate_naive_rag_on_locomo/run_evaluation.sh
```
