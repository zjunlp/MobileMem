"""Single CLI for the generation pipeline DAG.

    python -m pipeline.cli list
    python -m pipeline.cli run                       # whole graph
    python -m pipeline.cli run --only annual_events  # one node
    python -m pipeline.cli run --from social_world   # node + everything downstream

Run from the ``src/`` directory so that ``config`` / ``common`` / ``generation``
are importable.
"""
from __future__ import annotations

import argparse
import os
import time
from typing import List, Optional

import config

from pipeline import dag
from pipeline.spec import RunContext

# Map the legacy ``--start-stage`` float to its node (backward compatibility).
START_STAGE_TO_NODE = {
    1: "profile",
    2: "life_state",
    2.1: "social_name_fix",
    3: "timeline_dates",
    3.9: "social_world",
    4: "annual_events",
}

# The record sub-graph that main.py historically runs, with its stage float.
RECORD_STAGES = [
    ("profile", 1.0),
    ("life_state", 2.0),
    ("social_name_fix", 2.1),
    ("timeline_dates", 3.0),
    ("social_world", 3.9),
    ("annual_events", 4.0),
]


def _default_info_dir() -> str:
    return os.path.join(config.PROJECT_ROOT, "infotest")


def _default_output_dir() -> str:
    return os.path.join(config.PROJECT_ROOT, "output", "data")


def _default_image_dir(output_dir: str) -> str:
    parent = os.path.dirname(os.path.abspath(output_dir))
    return os.path.join(parent, "image")


def _add_context_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--info-dir", default=_default_info_dir(),
                        help="Directory containing person subfolders")
    parser.add_argument("--output-dir", default=_default_output_dir(),
                        help="Output directory for stage JSONL files")
    parser.add_argument("--image-dir", default=None,
                        help="Output directory for rendered images "
                             "(default: sibling 'image' directory next to --output-dir)")
    parser.add_argument("--prompts-dir", default=config.PROMPTS_DIR,
                        help="Path to prompts/ directory")
    parser.add_argument("--max-events", type=int, default=10,
                        help="Total events per person (stage4 / social graph sizing)")
    parser.add_argument("--max-workers", type=int, default=3,
                        help="Parallel workers for stage3.9 / stage4")
    parser.add_argument("--uuid", type=int, action="append", default=None,
                        help="Restrict to these uuid(s); repeatable (media nodes)")
    parser.add_argument("--model", default=None, help="Override text model (optional)")
    resume_grp = parser.add_mutually_exclusive_group()
    resume_grp.add_argument(
        "--resume", dest="force", action="store_false", default=False,
        help="Reuse already-finished work and continue (default)")
    resume_grp.add_argument(
        "--force", dest="force", action="store_true",
        help="Ignore caches/existing outputs and regenerate everything")


def _build_context(args: argparse.Namespace) -> RunContext:
    image_dir = args.image_dir or _default_image_dir(args.output_dir)
    return RunContext(
        info_dir=args.info_dir,
        output_dir=args.output_dir,
        image_dir=image_dir,
        prompts_dir=args.prompts_dir,
        max_events=args.max_events,
        max_workers=args.max_workers,
        uuid_filter=args.uuid,
        model=args.model,
        force=args.force,
    )


def _run_nodes(selected: List[str], ctx: RunContext) -> None:
    os.makedirs(ctx.output_dir, exist_ok=True)
    os.makedirs(ctx.image_dir, exist_ok=True)
    bar = "=" * 70
    print(f"\n{bar}\nPipeline run: {len(selected)} node(s)\n{bar}")
    print(f"Nodes:        {' -> '.join(selected)}")
    print(f"Info dir:     {ctx.info_dir}")
    print(f"Data dir:     {ctx.output_dir}")
    print(f"Image dir:    {ctx.image_dir}")
    print(f"Max events:   {ctx.max_events}   Max workers: {ctx.max_workers}")
    total_start = time.time()
    for name in selected:
        node = dag.NODES[name]
        print(f"\n{bar}\nNODE: {name}  [{node.kind}]  {node.description}\n{bar}")
        t0 = time.time()
        node.run(ctx)
        dag.verify_node_outputs(ctx, node)
        print(f"[{name}] done in {time.time() - t0:.1f}s")
    print(f"\n{bar}\nALL NODES COMPLETE  ({time.time() - total_start:.1f}s)\n{bar}")


def _cmd_list(_args: argparse.Namespace) -> int:
    dag.validate()
    order = dag.topo_order()
    print("Pipeline nodes (topological order):")
    for i, name in enumerate(order, 1):
        node = dag.NODES[name]
        deps = ", ".join(node.depends_on) or "-"
        print(f"  {i:2d}. {name:<16} [{node.kind:<10}] deps: {deps}")
        if node.description:
            print(f"        {node.description}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    dag.validate()
    if args.only and args.from_node:
        raise SystemExit("error: use at most one of --only / --from")
    if args.start_stage is not None and (args.only or args.from_node):
        raise SystemExit("error: --start-stage cannot be combined with --only/--from")

    if args.start_stage is not None:
        node = START_STAGE_TO_NODE.get(args.start_stage)
        if node is None:
            raise SystemExit(
                f"error: --start-stage {args.start_stage} unknown; "
                f"valid: {sorted(START_STAGE_TO_NODE)}")
        selected = dag.select(from_=node)
    else:
        selected = dag.select(only=args.only, from_=args.from_node)

    _run_nodes(selected, _build_context(args))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pipeline.cli",
        description="Declarative DAG runner for the persona-memory generation pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List nodes in topological order")
    p_list.set_defaults(func=_cmd_list)

    p_run = sub.add_parser("run", help="Run the graph (or a selection)")
    p_run.add_argument("--only", default=None, help="Run only this node")
    p_run.add_argument("--from", dest="from_node", default=None,
                       help="Run this node and everything downstream")
    p_run.add_argument("--start-stage", type=float, default=None,
                       help="Legacy: map a stage float (1/2/2.1/3/3.9/4) to --from")
    _add_context_args(p_run)
    p_run.set_defaults(func=_cmd_run)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


def run_main(argv: Optional[List[str]] = None) -> int:
    """main.py-compatible entry: run the record sub-graph (stages 1..4 + gender fix).

    Mirrors ``main.py`` flags and its ``--start-stage`` cumulative semantics (run
    every record node whose stage float >= start_stage).
    """
    parser = argparse.ArgumentParser(
        description="Persona pipeline (record stages 1..4)")
    parser.add_argument("--start-stage", type=float, default=1)
    _add_context_args(parser)
    args = parser.parse_args(argv)

    selected = [name for name, sf in RECORD_STAGES if args.start_stage <= sf]
    if not selected:
        raise SystemExit(
            f"error: --start-stage {args.start_stage} runs no record stage; "
            f"valid floats: {[sf for _, sf in RECORD_STAGES]}")
    _run_nodes(selected, _build_context(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
