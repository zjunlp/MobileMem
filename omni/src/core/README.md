# `core/` — Domain Models (L2)

Pure data types for the memory domain: no I/O, no LLM calls, no import-time
side effects.

| Module | Responsibility |
|--------|----------------|
| `base.py` | `JsonlModel`: lossless `dict ↔ model` round-trip (`from_dict(x).to_dict() == x`); unknown keys are preserved in `extra` |
| `persona.py` | `Persona` (profile top-level record) and `BasicProfile` (life_state+ nested profile) |
| `life.py` | `Event`, `SocialGraph`, `SubEvent` |
| `memories.py` | `GroupChat` (chat documents) and `ImageRecord` (image index rows) |
| `recall.py` | `ImageSummary` (image summary rows) |
| `lang.py` | `is_chinese_persona` — the single "is this persona Chinese?" check used by every node |
| `image_dirs.py` | Single source of truth for the image output directory names (rename a category here only) |
