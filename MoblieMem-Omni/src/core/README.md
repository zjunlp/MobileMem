# `core/` — Domain Models (L2)

Pure data types for the memory domain: no I/O, no LLM calls, no import-time
side effects.

| Module | Responsibility |
|--------|----------------|
| `base.py` | `JsonlModel`: lossless `dict ↔ model` round-trip (`from_dict(x).to_dict() == x`); unknown keys are preserved in `extra` |
| `persona.py` | Persona / basic-profile model |
| `life.py` | Life-state model |
| `memories.py` | Event and memory models |
| `recall.py` | Recall / question models |
| `image_dirs.py` | Single source of truth for the image output directory names (rename a category here only) |
