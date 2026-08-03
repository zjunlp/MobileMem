"""Infrastructure layer (L1).

Cross-cutting foundations shared by every stage so they are written once,
in one place, instead of being re-implemented per script:

- :mod:`infra.store` — unified JSONL I/O, indexing and checkpoint/resume.
- :mod:`infra.parallel` — fault-isolated parallel map (one bad item never
  aborts the whole batch).

This package never imports stages, domain logic or models (it is the bottom
of the dependency stack), and it has no import-time side effects.
"""
