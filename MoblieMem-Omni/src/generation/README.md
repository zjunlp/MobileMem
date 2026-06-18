# `generation/` — Memory Artifact Generators (L3)

One module per memory component the pipeline produces. Each generator is named
by *what it produces* (a domain concept) rather than by a stage number, and
subclasses `infra.base_generator.Generator`. Shared logic lives in `core` /
`backends` / `infra`; a generator never imports another generator.

This package is import-light: import the specific generator you need (e.g.
`from generation.timeline_dates import ImportantDatesGenerator`) so unrelated
heavy dependencies are not pulled in.

## Record generators (text)

| Module | Produces |
|--------|----------|
| `profile.py` | Persona basic profile from a CSV folder (Chinese personas) |
| `persona_seeds.py` | Brand-new personas synthesized by the LLM (Stage 0; foreign personas with an `appearance` block) |
| `life_state.py` | Per-persona life state |
| `timeline_dates.py` | Important dates on the persona's timeline |
| `social_world.py` | Social graph (relationships and contacts) |
| `annual_events/` | A year of life events |
| `sub_events.py` | Sub-events expanded from the annual events |
| `memory_summary.py` | Per-image memory summaries and the merged memory index |

## Media generators (images / screenshots)

| Module | Produces |
|--------|----------|
| `conversation/` | Group-chat screenshots |
| `app_trace/` | App screenshots (book, music, video, shopping, ticket, payment, …) |
| `event_photo/` | Event scene photos, with face-swap for identity consistency |
| `document/` | Document images |
| `scenery.py` | Ambient / scenery images |
