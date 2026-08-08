
<div align="center">

# <img src="https://img.icons8.com/fluency/48/iphone.png" alt="iPhone" width="30" height="30" style="vertical-align: middle;"/> MobileMem <img src="https://img.icons8.com/fluency/48/gallery.png" alt="Gallery" width="30" height="30" style="vertical-align: middle;"/>

**MobileMem** : On-Device Memory for Continually Evolving Agents

[![Technical Report](https://img.shields.io/badge/Paper-2026.XXXXX-b31b1b?style=flat-square&logo=arxiv&logoColor=white)](https://arxiv.org/abs/XXXX)
[![Website](https://img.shields.io/badge/Website-MobileMem-blue?style=flat-square&logo=googlechrome&logoColor=white)](https://zjunlp.github.io/MobileMem/)
[![HuggingFace](https://img.shields.io/badge/🤗-Dataset-yellow?style=flat-square)](https://huggingface.co/datasets/yourusername/MobileMem-Omni)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square&logo=opensourceinitiative&logoColor=white)](#license)

**MobileMem** is a comprehensive benchmarking framework for evaluating **on-device memory systems** in realistic mobile environments.

<img src="omni/asset/fig1.png" style="width:100%; height: auto;" align=center>

</div>

---

## 🔔 News

- **2025-06-01** — We launch the MobileMem project.

---

## 🚀 Getting Started

MobileMem provides two benchmark tracks. Choose the one that fits your needs and navigate to the corresponding resources for data access, evaluation, and construction.

### 📖 Text Track

The textual benchmark for evaluating memory systems on long-term, knowledge-intensive mobile agent trajectories.

| Section | Description | Link |
| :--- | :--- | :--- |
| **Data** | Access the synthesized KEME trajectories and QA pairs. | [Link](https://huggingface.co/datasets/zjunlp/MobileMem) |
| **Evaluation** | Run baseline memory systems and reproduce leaderboard results. | [Link](https://github.com/zjunlp/MemBase/tree/main/examples/evaluate_memory_systems_on_mobilemem) |
| **Construction** | Reproduce the KEME synthesis pipeline from raw traces. | [Link](https://github.com/zjunlp/MobileMem/tree/main/text) |

### 🖼️ Omni Track

The multimodal benchmark for evaluating on-device memory with realistic mobile images and dialogues.

| Section | Description | Link |
| :--- | :--- | :--- |
| **Data** | Download the MobileMem-Omni dataset with images and dialogues. | [Link](https://huggingface.co/datasets/zjunlp/MobileMem) |
| **Evaluation** | Evaluate models on memory task types. | [Link](https://github.com/zjunlp/MobileMem/tree/main/omni/eval) |
| **Construction** | Rebuild the MobileMem-Omni. | [Link](https://github.com/zjunlp/MobileMem/tree/main/omni) |

---

## 🚩 Citation

If this paper or datasets is helpful, please kindly cite as this:

```bibtex
```
