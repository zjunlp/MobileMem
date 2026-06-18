# `backends/` — Capability Layer (L1)

Thin wrappers over external services. Generators import capabilities from
here; this layer depends only on `config` and never imports a generator or the
domain model. Heavy dependencies are imported lazily, so importing the package
has no side effects.

| Module | Provides |
|--------|----------|
| `llm/` | Text LLM client and request helpers (chat, JSON extraction, call logging) |
| `images.py` | Person and event image generation / editing (OpenRouter and DMX backends, with retries and fallback models) |
| `faces.py` | Face detection and embedding (InsightFace `buffalo_l`), shared across stages and safe for concurrent use |
