"""Fault-isolated parallel map (L1 infrastructure).

The legacy :mod:`parallel_utils` aborted the *entire* batch the moment one item
raised, which made a parallel stage strictly less robust than its own sequential
fallback (the sequential path already skipped a failing record and carried on).
This module is the canonical replacement: every item runs in isolation, results
are returned in input order, and per-item failures are *collected* rather than
propagated, so a single bad record never kills a whole run.

It depends on nothing in the project (pure stdlib, no import-time side effects),
keeping it at the bottom of the dependency stack alongside the rest of ``infra``.
"""

from __future__ import annotations

import concurrent.futures
import os
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Sequence, Tuple


def get_cpu_count() -> int:
    """Best-effort CPU count, defaulting to 4 when it cannot be determined."""
    try:
        return os.cpu_count() or 4
    except Exception:
        return 4


@dataclass
class ItemError:
    """An input item that failed during a :func:`parallel_map` run."""

    index: int
    item: Any
    error: Exception


# Private sentinel marking an input slot whose item failed. Kept private (rather
# than ``None``) so a callable may legitimately return ``None`` without being
# mistaken for a failure.
_FAILED = object()


def parallel_map(
    items: Sequence[Any],
    func: Callable[[Any], Any],
    *,
    max_workers: Optional[int] = None,
    on_progress: Optional[Callable[[int, int, int, Optional[Exception]], None]] = None,
) -> Tuple[List[Any], List[ItemError]]:
    """Apply ``func`` to every item concurrently, isolating per-item failures.

    Unlike a fail-fast map, a single failing item never aborts the batch.

    Args:
        items: the input sequence.
        func: callable applied to each item.
        max_workers: thread-pool size; defaults to :func:`get_cpu_count`.
        on_progress: optional callback fired once per finished item with
            ``(done_count, total, index, error)``. ``error`` is ``None`` on
            success; ``done_count`` counts every finished item (success or
            failure) in completion order.

    Returns:
        ``(results, errors)`` where ``results`` holds the successful return
        values in *input* order (failed items omitted) and ``errors`` lists the
        failures ordered by input index.
    """
    items = list(items)
    total = len(items)
    if total == 0:
        return [], []

    workers = max_workers or get_cpu_count()
    slots: List[Any] = [_FAILED] * total
    errors_by_index: dict[int, ItemError] = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_index = {
            executor.submit(func, item): index for index, item in enumerate(items)
        }
        done_count = 0
        for future in concurrent.futures.as_completed(future_to_index):
            index = future_to_index[future]
            done_count += 1
            try:
                slots[index] = future.result()
                if on_progress is not None:
                    on_progress(done_count, total, index, None)
            except Exception as exc:  # isolation is the whole point
                errors_by_index[index] = ItemError(index=index, item=items[index], error=exc)
                if on_progress is not None:
                    on_progress(done_count, total, index, exc)

    results = [slot for slot in slots if slot is not _FAILED]
    errors = [errors_by_index[i] for i in sorted(errors_by_index)]
    return results, errors
