"""Declarative pipeline package.

A single declarative DAG over the domain ``generation/`` generators plus one CLI,
replacing the scattered per-stage ``main()`` entry points.

Import-light by default: importing this package (or running ``list``) never pulls
heavy deps (insightface / PaddleOCR). Node adapters import their generators
lazily, inside ``run``.
"""
