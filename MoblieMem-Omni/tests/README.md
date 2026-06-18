# `tests/`

Lightweight tests that run without any API keys, models, or network access.

| Test | Covers |
|------|--------|
| `test_pipeline_smoke.py` | DAG validity, required dependency edges, media path routing, and import compatibility |
| `test_face_swapper.py` | The pure two-stage face-match assignment (`_optimal_pairs`): optimal vs greedy, rectangular and empty matrices |

```bash
cd src && python -m pytest ../tests
# or
cd src && python -m unittest discover -s ../tests
```
