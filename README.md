
<div align="center">

# <img src="https://img.icons8.com/fluency/48/iphone.png" alt="iPhone" width="34" height="34" style="vertical-align: middle;"/> MobileMem <img src="https://img.icons8.com/fluency/48/gallery.png" alt="Gallery" width="34" height="34" style="vertical-align: middle;"/>
## *Learning from a Year of Mobile Experiences*

<img src="omni/asset/logo.jpg" style="width:45%; height: auto; border-radius: 20px; box-shadow: 0 8px 28px rgba(0,0,0,0.12);" align=center>

[![Paper](https://img.shields.io/badge/📄_Paper-2026.XXXXX-b31b1b?style=flat-square&logo=arxiv&logoColor=white)](https://arxiv.org/abs/XXXX)
[![Website](https://img.shields.io/badge/🌐_Website-MobileMem-1e7bbf?style=flat-square&logo=googlechrome&logoColor=white)](https://zjunlp.github.io/MobileMem/)
[![HuggingFace](https://img.shields.io/badge/🤗_Dataset-MobileMem-fcd022?style=flat-square)](https://huggingface.co/datasets/zjunlp/MobileMem)
[![License](https://img.shields.io/badge/📜_License-MIT-2ea44f?style=flat-square&logo=opensourceinitiative&logoColor=white)](#license)

---

<img src="omni/asset/fig1.png" style="width:100%; height: auto; border-radius: 14px; box-shadow: 0 4px 18px rgba(0,0,0,0.06);" align=center>

**MobileMem** is a comprehensive benchmarking framework for evaluating **on-device memory systems** in realistic mobile environments.

---

<img src="omni/asset/fig2.png" style="width:100%; height: auto; border-radius: 14px; box-shadow: 0 4px 18px rgba(0,0,0,0.06);" align=center>

**MobileMem** is built from **multiple heterogeneous sources** to enable comprehensive on-device memory modeling.
</div>

---

## 🔔 News
- **2025-08-01** — We publicly release the MobileMem dataset.
- **2025-06-01** — We launch the MobileMem project.

---

## 🚀 Getting Started

MobileMem offers two benchmark tracks. Choose the path that fits your needs and navigate to the corresponding resources.

### 📖 Text Track
The textual benchmark for evaluating memory systems on long-term, knowledge-intensive mobile agent trajectories.

| Section | Description | Quick Link |
| :--- | :--- | :--- |
| **📥 Data Access** | Download the synthesized KEME trajectories and QA pairs from HuggingFace. | [Link](https://huggingface.co/datasets/zjunlp/MobileMem) |
| **⚙️ How to Evaluate** | **Detailed evaluation guide for reproducing leaderboard results is available in the [MemBase](https://github.com/zjunlp/MemBase/tree/main/examples/evaluate_memory_systems_on_mobilemem) repository.** | [Link](https://github.com/zjunlp/MemBase/tree/main/examples/evaluate_memory_systems_on_mobilemem) |
| **🛠️ Data Construction** | Reproduce the KEME synthesis pipeline from scratch. | [Link](https://github.com/zjunlp/MobileMem/tree/main/text) |

### 🖼️ Omni Track
The multimodal benchmark for evaluating on-device memory with realistic mobile images and dialogues.

| Section | Description | Quick Link |
| :--- | :--- | :--- |
| **📥 Data Access** | Download the MobileMem-Omni dataset, including images and dialogues. | [Link](https://huggingface.co/datasets/zjunlp/MobileMem) |
| **⚙️ How to Evaluate** | Evaluate your models on various memory task types using our provided scripts. | [Link](https://github.com/zjunlp/MobileMem/tree/main/omni/eval) |
| **🛠️ Data Construction** | Rebuild the entire MobileMem-Omni dataset with the provided pipeline. | [Link](https://github.com/zjunlp/MobileMem/tree/main/omni) |

---

## 🔍 Analyzing Failures with MemTrace
We recommend using **[MemTrace](https://github.com/zjunlp/MemTrace)** to perform an in-depth error analysis. MemTrace helps you visualize and diagnose where and why your memory system fails, making it easier to pinpoint areas for improvement.

---

## 🚩 Citation

If this work or datasets is helpful, please kindly cite as this:

```bibtex
```
