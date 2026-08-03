# `infra/` — Infrastructure (L1)

Cross-cutting plumbing shared by every generator. Imports only the standard
library and `infra.store`; never a generator, the backends layer, or the
domain model.

| Module | Responsibility |
|--------|----------------|
| `base_generator.py` | `Generator`: a resume-safe template — iterate upstream records, reuse finished ones, generate the rest, checkpoint after each success, and isolate per-record failures so one bad record never aborts the batch |
| `store.py` | JSONL read/write, indexing by key, and incremental save callbacks |
| `parallel.py` | Parallel execution helpers (thread pool) |
| `prompts.py` | `load_prompt` / `load_bilingual_prompt`: the single prompt-file loader (UTF-8, `_zh` / `_en` selection) |
| `html_screenshot.py` | Playwright HTML→PNG rendering shared by the `app_trace` and `document` generators |
