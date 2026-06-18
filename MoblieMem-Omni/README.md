<div align="center">

<h1 align="center" style="font-size: 50px;">
  <img src="https://img.icons8.com/fluency/48/iphone.png" alt="iPhone" width="30" height="30" style="vertical-align: middle; pointer-events: none;"/>
  MobileMem-Omni
  <img src="https://img.icons8.com/fluency/48/gallery.png" alt="Gallery" width="30" height="30" style="vertical-align: middle; pointer-events: none;"/>
</h1>

<b>A Benchmark for Long-Term Multimodal Memory on Mobile Devices</b>

[![Paper](https://img.shields.io/badge/Paper-2026.XXXXX-b31b1b?style=flat-square&logo=arxiv&logoColor=white)](https://arxiv.org/abs/XXXX)
[![Website](https://img.shields.io/badge/Website-MobileMem-blue?style=flat-square&logo=googlechrome&logoColor=white)](https://mobilemem.github.io)
[![HuggingFace](https://img.shields.io/badge/🤗-Dataset-yellow?style=flat-square)](https://huggingface.co/datasets/yourusername/MobileMem-Omni)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square&logo=opensourceinitiative&logoColor=white)](#license)

**MobileMem-Omni** is the **first large-scale benchmark** specifically designed for evaluating **long-term multimodal memory** in **mobile scenarios**.

</div>


# 🔔 News

- 2025-06-01, We launched the MobileMem project.

# 📑 Table of Contents

- [🔔 News](#-news)
- [🌟 Overview](#-overview)
- [📚 Datasets](#-datasets)
  - [📊 Benchmark Statistics](#-benchmark-statistics)
  - [🖼️ Image Types](#️-image-types)
  - [🧠 Memory Tasks](#-memory-tasks)
  - [🧱 Benchmark Structure](#-benchmark-structure)
- [🏆 Leaderboard](#-leaderboard)
- [🚀 Quick Start](#-quick-start)
  - [📦 Environment Setup](#-environment-setup)
  - [📥 Dataset Download](#-dataset-download)
  - [🖼️ Data Construction](#️-data-construction)
- [🌻 Acknowledgement](#-acknowledgement)
- [🚩 Citation](#-citation)


---

# 🌟 Overview

| | |
|:---:|:---|
| 🧑 **Real User Personas** | 8 recruited participants + 8 LLM-generated virtual personas |
| 🌏 **Multilingual Dialogues** | Role-based English and Chinese interactions |
| 🖼️ **Personalized Mobile Images** | 19,060 images across 12 categories |
| 🧠 **7 Memory Task Types** | From single-hop retrieval to visual reasoning |


# 📚 Datasets

## 📊 Benchmark Statistics

<div align="center">

| 📊 User Statistics | Count |
|:-------------------|------:|
| Total Users | **16** |
| English Interaction Users | 8 |
| Chinese Interaction Users | 8 |
| Total Events | **1,589** |

| 💬 Interaction Statistics | |
|:---------------------------|------:|
| Avg Context Length (tokens/user) | **1.72M** |
| Avg Sessions per User | 202.6 |
| Avg Dialogue Turns per Session | 48.2 |
| Total Dialogue Turns | **155,670** |
| Avg Images per Session | 5.88 |
| Total Images | **19,060** |

| ❓ Question Distribution | Count |
|:-------------------------|------:|
| Total Questions | **7,415** |
| Single-Hop | 986 |
| Multi-Hop | 1,135 |
| Knowledge Update | 1,010 |
| Temporal Reasoning | 773 |
| Implicit Preference | 1,226 |
| Abstention | 1,208 |
| Visual Reasoning | 1,077 |

</div>


## 🖼️ Image Types

MobileMem-Omni encompasses **12 image types** sourced from diverse mobile applications:

<div align="center">

| Category | Description | Generation Method |
|:--------------------------------|:----------------------------------------------|:------------------|
| 📸 **Persona Reference Photos** | Persona appearances | Text-to-image models |
| 📸 **KG Reference Photos** | Knowledge graph person appearances | Text-to-image models |
| 📷 **Camera Photos** | Event scenes with persona and social contacts | Image editing models |
| 📚 **Book Screenshots** | E-book reading progress and metadata | HTML rendering |
| 🎵 **Music Screenshots** | Music streaming interfaces with song details | HTML rendering |
| 🎬 **Video Screenshots** | Video streaming with covers and stats | HTML rendering + text-to-image |
| 💳 **Transaction Records** | Payment interfaces with amounts and notes | HTML rendering |
| 🎫 **Ticket Records** | Booking confirmations with journey details | HTML rendering |
| 🛍️ **Shopping Records** | Order pages with product information | HTML rendering |
| 💬 **Social Chat Records** | Messaging app conversations | HTML rendering |
| 📱 **Social Media Posts** | Content sharing with likes and comments | HTML rendering |
| 🗺️ **Others** | Scenery, food, maps, weather, etc. | Text-to-image models |

</div>


## 🧠 Memory Tasks

MobileMem-Omni evaluates **7 types** of memory reasoning tasks:

<div align="center">

| Task | Description | Example Question |
|:-----|:------------|:-----------------|
| **Single-Hop** | Retrieve a single factual piece | *"What is the user's occupation?"* |
| **Multi-Hop** | Synthesize information from multiple facts | *"Where did the user go for their anniversary trip, and with whom?"* |
| **Knowledge Update** | Incorporate new info, revise outdated memory | *"What is the user's current location after their recent move?"* |
| **Temporal Reasoning** | Capture and reason about time-related cues | *"When did the user first mention their upcoming exam?"* |
| **Implicit Preference** | Infer latent user attributes or preferences | *"What type of cuisine does the user prefer?"* |
| **Abstention** | Correctly decline to answer when info is absent | *"What did the user eat for breakfast two weeks ago?"* → *"I don't know"* |
| **Visual Reasoning** | Interpret and reason over visual content | *"Based on the screenshot, what is the total transaction amount?"* |

</div>

## 🧱 Benchmark Structure
### Each persona’s data is stored as a JSON:
| Field          | Description                                                  |
| -------------- | ------------------------------------------------------------ |
| `uuid`         | Unique user identifier                                       |



# 🏆 Leaderboard


# 🚀 Quick Start

## 📦 Environment Setup

### Create and activate a dedicated conda environment:

```bash
conda create -n mobilemem python=3.11
conda activate mobilemem
```

### Clone code

```
git clone https://github.com/zjunlp/MobileMem
pip install -r requirements.txt
```


## 📥 Dataset Download

### Option 1: Using HuggingFace CLI

```bash
huggingface-cli download --repo-type dataset --resume-download zjunlp/xxx --local-dir OceanBenchmark
```

### Option 2: Using Python

```python
from datasets import load_dataset

dst = load_dataset("zjunlp/xxx")
```


## 🖼️ Data Construction

The dataset is produced by a declarative pipeline — a DAG of stages that turns a
persona spec (or a CSV profile) into a full year of multimodal mobile memories.

### Navigate to the directory

```bash
cd MoblieMem-Omni/src
cp .env.example .env          # then fill in your API keys
```

### Run the pipeline

```bash
# List all stages in topological order
python -m pipeline.cli list

# Run the whole pipeline for every persona
python -m pipeline.cli run

# Run a single stage, or a stage plus everything downstream
python -m pipeline.cli run --only event_photo
python -m pipeline.cli run --from social_world

# Restrict to specific persona uuid(s) and cap the events per persona
python -m pipeline.cli run --uuid 0 --max-events 15
```

### Stages

Records are written to `output/data/` (JSONL); rendered media to `output/image/`.

| # | Stage (node) | Output |
|--:|--------------|--------|
| 1 | `profile` | `basic_profiles.jsonl` |
| 2 | `persona_seeds` | `basic_profiles.jsonl` (appends LLM-seeded personas) |
| 3 | `life_state` | `init_states.jsonl` |
| 4 | `social_name_fix` | rewrites `init_states.jsonl` |
| 5 | `timeline_dates` | `important_dates.jsonl` |
| 6 | `social_world` | `social_graph.jsonl` |
| 7 | `annual_events` | `annual_events.jsonl` |
| 8 | `sub_events` | `sub_events.jsonl` |
| 9 | `conversation` | `group_chats.jsonl` + chat images |
| 10 | `app_trace` | `app_screenshots.jsonl` + app images |
| 11 | `event_photo` | `event_images.jsonl` + event photos |
| 12 | `document` | `tickets.jsonl` + document images |
| 13 | `scenery` | scenery images |
| 14 | `memory_summary` | `image_summaries.jsonl` + `total_images.jsonl` |

See `src/pipeline/README.md` for the full stage reference.

# 🌻Acknowledgement

This project is based on open-source projects including [xxx](https://xxx). Thanks for their great contributions!

# 🚩 Citation

If this paper or datasets is helpful, please kindly cite as this:

```bibtex

```
