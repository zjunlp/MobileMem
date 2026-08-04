
<div align="center">

# <img src="https://img.icons8.com/fluency/48/iphone.png" alt="iPhone" width="30" height="30" style="vertical-align: middle;"/> MobileMem <img src="https://img.icons8.com/fluency/48/gallery.png" alt="Gallery" width="30" height="30" style="vertical-align: middle;"/>

**MobileMem** : On-Device Memory for Continually Evolving Agents

[![Technical Report](https://img.shields.io/badge/Paper-2026.XXXXX-b31b1b?style=flat-square&logo=arxiv&logoColor=white)](https://arxiv.org/abs/XXXX)
[![Website](https://img.shields.io/badge/Website-MobileMem-blue?style=flat-square&logo=googlechrome&logoColor=white)](https://zjunlp.github.io/MobileMem/)
[![HuggingFace](https://img.shields.io/badge/🤗-Dataset-yellow?style=flat-square)](https://huggingface.co/datasets/yourusername/MobileMem-Omni)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square&logo=opensourceinitiative&logoColor=white)](#license)

**MobileMem** is a comprehensive benchmarking framework for evaluating **on-device memory systems** in realistic mobile environments.
</div>

---

## 🔔 News

- **2025-06-01** — We launch the MobileMem project.

---

## 🚀 Getting Started

MobileMem contains textual and multimodal benchmark tracks. Choose the track and workflow that matches your use case.

### Text

1. **KEME synthesis and analysis**
   See the corresponding [documentation](text/README.md) for environment setup, trajectory and question-answer synthesis, postprocessing, and analysis.

2. **Trace memory lifecycles with MemTrace**
   Follow the [MemTrace example](https://github.com/zjunlp/MemBase/tree/main/examples/trace_memory_lifecycle_with_membase) in MemBase.

   For the best EverMemOS retrieval performance, serve the reranker with:

   ```bash
   CUDA_VISIBLE_DEVICES=0 vllm serve pretrained_models/Qwen3-Reranker-4B \
       --port 8001 \
       --served-model-name Qwen3-Reranker-4B \
       --gpu-memory-utilization 0.4 \
       --hf_overrides '{"architectures": ["Qwen3ForSequenceClassification"], "classifier_from_token": ["no", "yes"], "is_original_qwen3_reranker": true}'
   ```

3. **Evaluate baselines on MobileMem**
   Follow the [MobileMem baseline evaluation example](https://github.com/zjunlp/MemBase/tree/main/examples/evaluate_memory_systems_on_mobilemem) to run supported memory systems.

### Omni

See the [`omni/` documentation](omni/README.md) for the multimodal MobileMem-Omni benchmark.

---

## 📂 Project Structure

```
MobileMem/
├── text/                    # MobileMem (Textual Benchmark)
├── omni/                    # MobileMem-Omni (Multimodal Benchmark)
└── README.md
```

---

## 🚩 Citation

If this paper or datasets is helpful, please kindly cite as this:

```bibtex
```
