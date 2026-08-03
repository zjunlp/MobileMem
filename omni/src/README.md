# `src/` — Data Construction Pipeline

Code that synthesizes the MobileMem-Omni dataset. It turns a small persona
spec (or a CSV profile) into a full year of multimodal mobile memories:
profiles, life states, important dates, events, group chats, app screenshots,
event photos, documents, scenery, and a final memory index.

## Layout

| Path | Layer | Responsibility |
|------|-------|----------------|
| `pipeline/` | orchestration | Declarative DAG of nodes + a single CLI (`python -m pipeline.cli`) |
| `generation/` | L3 generators | One module per memory artifact produced |
| `core/` | L2 domain | Pure data models (lossless JSONL round-trip) |
| `backends/` | L1 capabilities | LLM, image, and face services |
| `infra/` | L1 infrastructure | Resume-safe generator template, parallel helpers, JSONL store |
| top-level `*.py` | shared | `config`, `common` helpers, appearance pool, CSV parsing |

## Architecture

Dependencies only point downward: `generation` → `core` / `backends` / `infra`
→ `config`. A generator never imports another generator, and building or
listing the DAG is import-light so it never pulls in heavy optional
dependencies (image / face models).

## Quick start

```bash
cd src
cp .env.example .env          # then fill in the API keys

python -m pipeline.cli list                      # nodes in topological order
python -m pipeline.cli run                       # run the whole graph
python -m pipeline.cli run --only event_photo --uuid 7
python -m pipeline.cli run --from social_world   # a node + everything downstream
```
