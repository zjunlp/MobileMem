#!/usr/bin/env python3
"""10-Person Pipeline entry point (thin wrapper over the declarative DAG).

The orchestration now lives in the ``pipeline/`` package. This entry point runs
the record stages
(1 -> 2 -> 2.1 -> 3 -> 3.9 -> 4, plus the post-stage gender fix), preserving the
historical flags:

    python main.py [--start-stage N] [--max-events N] [--max-workers N]
                   [--info-dir DIR] [--output-dir DIR] [--prompts-dir DIR]

``--start-stage`` keeps its cumulative semantics (run every record stage whose
number is >= the given value). The full graph, including the media and recall
nodes, is available through the unified CLI:

    python -m pipeline.cli list
    python -m pipeline.cli run                 # whole graph
    python -m pipeline.cli run --from social_world
"""

from pipeline.cli import run_main

if __name__ == '__main__':
    raise SystemExit(run_main())
