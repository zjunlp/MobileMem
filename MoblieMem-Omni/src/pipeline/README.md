# `pipeline/` — DAG Orchestration

Declares the generation pipeline as a directed acyclic graph of nodes and runs
it from a single CLI.

| Module | Responsibility |
|--------|----------------|
| `dag.py` | Node definitions, dependency edges, topological ordering, and post-run output verification |
| `spec.py` | `Node` and `RunContext` (import-light: standard library only) |
| `cli.py` | `python -m pipeline.cli list / run` with `--only`, `--from`, `--uuid`, `--max-events`, `--force` |

## Usage

```bash
python -m pipeline.cli list                       # nodes in topological order
python -m pipeline.cli run                         # the whole graph
python -m pipeline.cli run --only annual_events    # a single node
python -m pipeline.cli run --from social_world     # a node + everything downstream
```

Each node is a thin adapter over a generator's public entry point. After a node
runs, its expected output artifacts are verified before the next node starts.

## Pipeline stages

Output filenames are **content-based** (no stage numbers). The execution order
is defined by the DAG below; the historical stage number is kept only as a
label. Run `python -m pipeline.cli list` to print the live topological order.

| Order | Node | Stage | Output under `output/data/` |
|------:|------|:-----:|------------------------------|
| 1 | `profile` | 1 | `basic_profiles.jsonl` |
| 2 | `persona_seeds` | 0 | `basic_profiles.jsonl` (appends LLM-seeded personas) |
| 3 | `life_state` | 2 | `init_states.jsonl` |
| 4 | `social_name_fix` | 2.1 | rewrites `init_states.jsonl` |
| 5 | `timeline_dates` | 3 | `important_dates.jsonl` |
| 6 | `social_world` | 3.9 | `social_graph.jsonl` |
| 7 | `annual_events` | 4 | `annual_events.jsonl` |
| 8 | `sub_events` | 4.5 | `sub_events.jsonl` |
| 9 | `conversation` | 7 | `group_chats.jsonl` + chat images |
| 10 | `app_trace` | 7.2 | `app_screenshots.jsonl` + app images |
| 11 | `event_photo` | 7.1 | `event_images.jsonl` + event photos |
| 12 | `document` | 7.3 | `tickets.jsonl` + document images |
| 13 | `scenery` | 8 | scenery images |
| 14 | `memory_summary` | 10 | `image_summaries.jsonl` + `total_images.jsonl` |
