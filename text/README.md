# MobileMem

### KEME: Knowledge-Guided Experience Synthesis for Evolving Memory

[Dataset](https://huggingface.co/datasets/zjunlp/MobileMem) | [MemBase](https://github.com/zjunlp/MemBase) | [License](LICENSE)

---

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Data Preparation](#data-preparation)
- [API Configuration](#api-configuration)
- [KEME Data Synthesis](#keme-data-synthesis)
  - [Trajectory Synthesis](#1-trajectory-synthesis)
  - [Question-Answer Pair Synthesis](#2-question-answer-pair-synthesis)
  - [Postprocessing](#3-postprocessing)
- [Analysis](#analysis)
  - [Profile Schema Ablation Study](#profile-schema-ablation-study)
  - [Hard Distractor Synthesis](#hard-distractor-synthesis)
- [Acknowledgements](#acknowledgements)
- [License](#license)

## Overview

This repository primarily provides the code for **KEME**, our pipeline for synthesizing long, evolving user trajectories and memory-oriented question-answer pairs. KEME constructs hierarchical temporal event graphs, grounds pre-synthesized user-app interaction sessions into compatible events, generates complementary human-assistant conversations, and synthesizes questions at multiple levels of the resulting trajectory.

> [!NOTE]
> Memory-system baselines are maintained separately in [MemBase](https://github.com/zjunlp/MemBase). To run or reproduce a baseline, please follow the corresponding instructions in MemBase. This separation is also why the Python environment used below is named `keme`.

## Installation

KEME requires Python `>=3.12`.

```bash
git clone https://github.com/zjunlp/MobileMem.git
cd MobileMem/text

conda create -n keme python=3.12 -y
conda activate keme
pip install -r requirements.txt
```

## Data Preparation

Installations from `requirements.txt` include the Hugging Face Hub CLI. From the `text/` code directory, download the complete MobileMem dataset into the repository-level `data/` directory:

```bash
hf download zjunlp/MobileMem --repo-type dataset --local-dir ../data
```

The Hugging Face repository separates the text and omni-modal data. The downloaded layout is:

```text
../data/
├── omni/
│   ├── data.jsonl
│   ├── image.zip
│   └── questions.jsonl
└── text/
    ├── mobilemem_data.json      # MobileMem data for baseline evaluation
    └── profiles/
        ├── user_01.json         # Persona input for KEME synthesis
        └── user_02.json         # Persona input for KEME synthesis
```

KEME reads personas from `data/text/profiles/`. Generated intermediate artifacts are kept outside the downloaded dataset under `../outputs/text/`. Override these locations with `DATA_DIR` and `OUTPUT_DIR`, and use `USER_ID` to select a persona:

```bash
export DATA_DIR="../data/text"
export OUTPUT_DIR="../outputs/text"
export USER_ID="user_01"
```

## API Configuration

KEME uses OpenAI-compatible chat and embedding APIs. Export credentials before running any synthesis or analysis script:

```bash
export OPENAI_API_KEY="YOUR_API_KEY"
export OPENAI_API_BASE="https://api.openai.com/v1"
```

Postprocessing and the profile schema ablation study use embeddings for semantic similarity and diversity calculations. By default, the embedding client reuses `OPENAI_API_KEY` and `OPENAI_API_BASE`, so no additional variables are required when the same endpoint serves both chat and embedding models. Set the following variables only when embeddings are provided by a different endpoint:

```bash
export EMBEDDING_API_KEY="${OPENAI_API_KEY}"
export EMBEDDING_BASE_URL="${OPENAI_API_BASE}"
```

Trajectory synthesis can optionally expose its visualization server through ngrok by setting `NGROK_AUTHTOKEN`. The provided launcher disables ngrok by default.

## KEME Data Synthesis

The three stages form the following artifact pipeline:

```text
person.json
    └── trajectory synthesis
          └── trajectory_state.pkl
                └── question-answer pair synthesis
                      └── qa_synthesis_results.json
                            └── postprocessing
                                  └── qa_synthesis_results_post.json
```

> [!NOTE]
> The trajectory launcher reads a persona from `${DATA_DIR}/profiles/${USER_ID}.json`. All three launchers write intermediate artifacts to `${OUTPUT_DIR}/${USER_ID}/`. The model and paths can be overridden through environment variables.

### 1. Trajectory Synthesis

Trajectory synthesis expands a persona into hierarchical temporal event graphs and grounded interaction sessions:

```bash
bash scripts/run_traj_synthesis.sh
```

Input:

```text
${DATA_DIR}/profiles/${USER_ID}.json
```

Output:

```text
${OUTPUT_DIR}/${USER_ID}/trajectory_state.pkl
```

The process starts a local trajectory visualization server. After synthesis finishes, the server remains active for inspection. Press `Ctrl+C` to stop it. 

The launcher accepts additional `run_synthesis.py` options and forwards them after its defaults. For example:

```bash
USER_ID=user_02 MODEL_NAME=gpt-4.1 \
  bash scripts/run_traj_synthesis.sh \
  --temperature 0.7 \
  --max_events 16 \
  --max_iters 80 \
  --studio_url http://localhost:3000
```

Launcher environment variables:

- `DATA_DIR` sets the text dataset directory (launcher default: `../data/text`).
- `OUTPUT_DIR` sets the generated-artifact directory (launcher default: `../outputs/text`).
- `USER_ID` selects `profiles/${USER_ID}.json` and the corresponding output directory (launcher default: `user_01`).
- `MODEL_NAME` selects the OpenAI-compatible chat model (launcher default: `gpt-5.2`).
- `OPENAI_API_KEY` is required. The launcher default for `OPENAI_API_BASE` is `https://api.openai.com/v1`.

Trajectory and agent options:

- `--min_events` and `--max_events` set the event-count range for each temporal event graph (launcher defaults: `2` and `12`).
- `--max_depth` limits the event hierarchy depth (launcher default: `2`).
- `--grounded_session_subgraph_threshold` prevents an event with more than the specified number of grounded sessions from being forced into one leaf session at maximum depth (launcher default: `1`).
- `--compatibility_context_max_tokens` sets the token threshold for summarizing grounding compatibility context (launcher default: `8000`).
- `--temperature` controls model sampling (launcher default: `1.0`).
- `--max_iters` limits synthesis-agent iterations (launcher default: `50`).
- `--parallel_tool_calls` enables parallel tool execution (launcher default: disabled).

Visualization options:

- `--traj_server_host` and `--traj_server_port` configure the trajectory server (launcher defaults: `0.0.0.0` and `5001`).
- `--studio_url` enables AgentScope Studio integration. `--studio_project` sets its project name (launcher default: `keme`).
- `--ngrok_authtoken` supplies an ngrok token, otherwise `NGROK_AUTHTOKEN` is used. The launcher always passes `--disable_ngrok`. To enable a public URL, invoke `run_synthesis.py` directly without that flag.

### 2. Question-Answer Pair Synthesis

This stage traverses the person profile and hierarchical trajectory from the leaf sessions upward. It generates and composes question-answer pairs covering single-hop, multi-hop, temporal reasoning, preference inference and updates,preference-oriented generalization, relationships, query-focused summarization, and adversarial settings:

```bash
bash scripts/run_qa_synthesis.sh
```

Input:

```text
${OUTPUT_DIR}/${USER_ID}/trajectory_state.pkl
```

Output:

```text
${OUTPUT_DIR}/${USER_ID}/qa_synthesis_results.json
```

The launcher accepts additional `run_qa_synthesis.py` options and forwards them after its defaults. For example:

```bash
USER_ID=user_02 MODEL_NAME=gpt-4.1 \
  bash scripts/run_qa_synthesis.sh \
  --temperature 0.7 \
  --max_qa_pairs 12 \
  --propagation_count 16 \
  --studio_url http://localhost:3000
```

Launcher environment variables:

- `OUTPUT_DIR` sets the generated-artifact directory (launcher default: `../outputs/text`).
- `USER_ID` selects the user trajectory and output directory (launcher default: `user_01`).
- `MODEL_NAME` selects the OpenAI-compatible chat model (launcher default: `gpt-5.2`).
- `OPENAI_API_KEY` is required. The launcher default for `OPENAI_API_BASE` is `https://api.openai.com/v1`.

Question-answer pair synthesis options:

- `--min_qa_pairs` and `--max_qa_pairs` define the inclusive target range for each QA-synthesis invocation, including each profile dimension, the overall person profile, and each eligible session- or graph-level event. The actual count may be lower if the maximum number of attempts is reached (launcher defaults: `1` and `8`).
- `--max_attempts` limits synthesis attempts for each target (launcher default: `5`).
- `--propagation_count` controls how many unused child question-answer pairs may be propagated upward for higher-level composition (launcher default: `10`).
- `--temperature` controls model sampling (launcher default: `1.0`).
- `--max_iters` limits synthesis-agent iterations (launcher default: `50`).
- `--parallel_tool_calls` enables parallel tool execution (launcher default: disabled).
- `--random_seed` controls randomized question propagation and reproducibility (launcher default: `42`).

Studio options:

- `--studio_url` enables AgentScope Studio integration.
- `--studio_project` sets the Studio project name (launcher default: `haste_qa_synthesis`).

### 3. Postprocessing

Postprocessing shuffles the synthesized question-answer pairs, retrieves semantically similar previously processed questions from Milvus Lite, and asks an LLM to check question quality and redundancy. Flagged pairs can either be revised or discarded before the final dataset is saved:

```bash
bash scripts/run_postprocess.sh
```

Input:

```text
${OUTPUT_DIR}/${USER_ID}/qa_synthesis_results.json
```

Output:

```text
${OUTPUT_DIR}/${USER_ID}/qa_synthesis_results_post.json
```

The launcher accepts additional `postprocess_qa.py` options and forwards them after its defaults. For example:

```bash
USER_ID=user_02 MODEL_NAME=gpt-5.2 \
  bash scripts/run_postprocess.sh \
  --refine_strategy revise \
  --similarity_threshold 0.85 \
  --top_k 10
```

Launcher environment variables:

- `OUTPUT_DIR` sets the generated-artifact directory (launcher default: `../outputs/text`).
- `USER_ID` selects the synthesized input and postprocessed output directory (launcher default: `user_01`).
- `MODEL_NAME` selects the revision model (launcher default: `gpt-5.2`).
- `OPENAI_API_KEY` is required. The launcher default for `OPENAI_API_BASE` is `https://api.openai.com/v1`.

Revision options:

- `--refine_strategy` controls flagged pairs: `revise` adopts the LLM-revised pair, while `discard` removes it (launcher default: `discard`).
- `--temperature` controls revision-model sampling (launcher default: `1.0`).
- `--max_iters` limits revision-agent iterations (launcher default: `10`).
- `--random_seed` controls the question processing order (launcher default: `42`).

Embedding options:

- `--embedding_model` sets the semantic-similarity model (launcher default: `text-embedding-3-small`).
- `--embedding_dimensions` sets the embedding vector size (launcher default: `1024`).
- `--embedding_api_key` and `--embedding_api_base` configure a separate embedding endpoint. If omitted, the chat API credentials and base URL are reused.

Milvus and retrieval options:

- `--milvus_uri` sets the Milvus Lite database path (launcher default: `${OUTPUT_DIR}/${USER_ID}/qa_postprocess_milvus.db`).
- `--collection_name` sets the collection used for question embeddings (launcher default: `qa_questions`).
- `--distance_metric` controls how Milvus ranks question embeddings (launcher default: `COSINE`)
- `--similarity_threshold` is the minimum score retained by AgentScope: retrieved results with `score < threshold` are discarded. No threshold is applied by default. 
- `--top_k` sets the maximum number of similar questions supplied to the revision agent (launcher default: `5`).

## Analysis

### Profile Schema Ablation Study

This study compares KEME trajectories generated from three profile schemas:

- `PersonFull`: 17 profile dimensions.
- `PersonMedium`: 8 profile dimensions.
- `PersonCompact`: 6 profile dimensions.

The pipeline runs three stages: 

1. `create_profiles.py` samples persona seeds from `./analysis/profile_schema/data/stage1_3_preferences.jsonl`, synthesizes each full 17-dimension profile with an LLM, and derives the matched 8- and  6-dimension variants without additional model calls. 
2. `run_synthesis.py` generates one trajectory for every profile variant. 
3. `run_analysis.py` compares distinct 2-gram diversity, semantic diversity, and profile-field activation across schemas. 

Run all three stages with:

```bash
bash analysis/profile_schema/scripts/run.sh
```

Generated profiles are saved under `./analysis/profile_schema/output/profiles/`, trajectories under `./analysis/profile_schema/output/trajectories/`, and embedding caches under `./analysis/profile_schema/output/.cache/`.

### Hard Distractor Synthesis

This analysis constructs challenging trajectories around existing question-answer pairs while preserving the evidence needed to answer them. The pipeline runs two stages:

1. `prepare_env.py` reads sampled questions and their evidence sessions from `./analysis/hard_distractor/data/sampled_questions.json`. For each sample, it extracts answer-preserving core facts and distractor guidelines, then synthesizes a compatible 8-dimension persona from the evidence sessions.  The enriched samples are saved to  `./analysis/hard_distractor/output/prepared_env.json`.
2. `run_synthesis.py` grounds the original evidence sessions into each synthesized persona and generates additional, non-contradictory trajectory content following the distractor guidelines. Generated trajectories are saved under `./analysis/hard_distractor/output/trajectories/`.

Run both stages with:

```bash
bash analysis/hard_distractor/scripts/run.sh
```

## Acknowledgements

KEME is built with [AgentScope](https://github.com/agentscope-ai/agentscope). Baseline evaluation is supported by [MemBase](https://github.com/zjunlp/MemBase).

## License

This project is released under the [MIT License](LICENSE).