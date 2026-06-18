"""Pipeline spec primitives: :class:`Node` and :class:`RunContext`.

This module is intentionally import-light (stdlib only) so that building the
graph, listing nodes, and topological sorting never trigger generator imports or
heavy optional dependencies.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple


@dataclass
class RunContext:
    """Resolved paths + knobs every node adapter needs.

    Mirrors the ``main.py`` flags so adapters can call the generator entry points
    with identical arguments.
    """

    info_dir: str
    output_dir: str          # the output/data directory holding the stage JSONLs
    image_dir: str           # the output/image directory holding rendered media
    prompts_dir: str
    max_events: int = 10
    max_workers: int = 3
    uuid_filter: Optional[List[int]] = None
    model: Optional[str] = None
    force: bool = False       # --force: ignore caches/existing outputs, regenerate

    def data_path(self, filename: str) -> str:
        """Absolute path of a stage output file under ``output_dir``."""
        return os.path.join(self.output_dir, filename)

    def image_path(self, *parts: str) -> str:
        """Absolute path under ``image_dir``."""
        return os.path.join(self.image_dir, *parts)


@dataclass(frozen=True)
class Node:
    """A single declarative pipeline node.

    ``run`` is a thin adapter ``Callable[[RunContext], None]`` that delegates to
    the generator's existing public entry point. ``outputs`` are data-dir
    artifacts expected after the run. ``verify`` may enforce node-specific
    output contracts after ``run`` returns.
    """

    name: str
    depends_on: Tuple[str, ...]
    outputs: Tuple[str, ...]
    run: Callable[["RunContext"], None]
    kind: str = "record"          # record | normalizer | media | index
    description: str = ""
    verify: Optional[Callable[["RunContext", "Node"], None]] = None
