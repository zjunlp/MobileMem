"""Generators (L3): one module per memory component the pipeline produces.

Each generator is named by *what it produces* (a domain concept) rather than by
a stage number, and subclasses :class:`infra.base_generator.Generator`. Shared
logic lives in ``core`` / ``backends`` / ``infra``; a generator never imports
another generator.

See ``docs/REFACTOR_PLAN.md`` (section 5) for the stage -> generator rename map.
This package is intentionally import-light: import the specific generator module
you need (e.g. ``from generation.timeline_dates import ImportantDatesGenerator``)
so unrelated heavy dependencies are not pulled in.
"""
