"""Template base class for per-record generators (L1).

Every generation step in this pipeline used to re-implement the same lifecycle by
hand: iterate the upstream records in order, reuse the ones already produced
(resume), generate the missing ones, save incrementally after each success so a
crash never loses progress, isolate per-record failures, and finally write the file.

:class:`Generator` captures that lifecycle once. A concrete generator only declares
its identity (``stage_label`` / ``index_key`` / I/O paths) and implements the single
:meth:`Generator.produce` method; everything else is inherited and therefore behaves
identically across generators.

This module lives in the infrastructure layer (L1): it imports only
:mod:`infra.store` and the standard library, never a generator, the LLM/backends
layer or the domain model. Concerns that *do* need higher layers (e.g. setting the
LLM log context) are exposed as override hooks the concrete generator fills in.

``process_one`` is kept as a backward-compatible alias of ``produce``.
"""

from __future__ import annotations

import traceback
from typing import Any, Callable, Dict, List, Optional, Sequence

from infra.store import index_by, make_save_callback, read_jsonl, write_jsonl

Record = Dict[str, Any]
SaveCallback = Callable[[Sequence[Record]], None]


class Generator:
    """Resume-safe template that maps one upstream record to one output record.

    Subclasses set the class attributes below and implement :meth:`produce`
    (legacy subclasses may implement :meth:`process_one` instead). They may
    optionally override :meth:`set_context`, :meth:`describe_result`,
    :meth:`format_skip_line`, :meth:`format_generating_line`, and
    :meth:`after_success` to reproduce stage-specific logging / post-processing.
    """

    #: Human-readable tag used in log lines, e.g. ``"Stage3"``.
    stage_label: str = "Stage"
    #: Identifier shown in the incremental-save message (see store.make_save_callback).
    stage_num: Any = ""
    #: Record field used to index / skip already-completed records.
    index_key: str = "uuid"
    #: Upstream and output JSONL paths. Only required when using :meth:`run`;
    #: generators still driven by ``main.py`` leave these unset and call
    #: :meth:`process_all` directly.
    input_file: Optional[str] = None
    output_file: Optional[str] = None

    # ------------------------------------------------------------------ #
    # The only thing a concrete generator MUST implement.
    # ------------------------------------------------------------------ #
    def produce(self, record: Record, ctx: Any = None) -> Record:
        """Produce the output record for a single upstream ``record``.

        Default delegates to the legacy :meth:`process_one` for backward
        compatibility; new generators override ``produce`` directly.
        """
        return self.process_one(record, ctx)

    def process_one(self, record: Record, ctx: Any = None) -> Record:
        """Legacy alias for :meth:`produce`; older stages override this."""
        raise NotImplementedError("override produce() (or the legacy process_one())")

    # ------------------------------------------------------------------ #
    # Optional hooks (sensible defaults; override to match legacy logging).
    # ------------------------------------------------------------------ #
    def set_context(self, record: Record, index: int) -> None:
        """Per-record setup hook (e.g. set the LLM log context). No-op default."""

    def describe_result(self, record: Record, result: Record) -> str:
        """Return an extra line to print after a successful record (``""`` = none)."""
        return ""

    def format_skip_line(self, record: Record, key: Any, index: int, total: int) -> str:
        """Log line for a checkpoint-skipped record. Override to add stage detail."""
        return f"[{self.stage_label}] [{index + 1}/{total}] uid={key}: SKIP (checkpoint)"

    def format_generating_line(self, record: Record, key: Any, index: int, total: int) -> str:
        """Log line printed before generating a record. Override to add stage detail."""
        return f"\n[{self.stage_label}] [{index + 1}/{total}] uid={key}: generating..."

    def after_success(self, record: Record, result: Record) -> None:
        """Post-process hook run after a successful :meth:`produce`, before the
        record is appended/saved. Lets a generator mutate ``result`` (e.g.
        de-duplicate) and update cross-record state. No-op by default."""

    # ------------------------------------------------------------------ #
    # Shared template loop — the heart of the resume-safe behavior.
    # ------------------------------------------------------------------ #
    def process_all(
        self,
        inputs: Sequence[Record],
        existing: Optional[Dict[Any, Record]] = None,
        save_callback: Optional[SaveCallback] = None,
        ctx: Any = None,
    ) -> List[Record]:
        """Process ``inputs`` in order, reusing ``existing`` records by key.

        Returns the output records in upstream order. Already-done records are
        reused in place; newly generated ones trigger ``save_callback`` after
        each success; per-record exceptions are logged and skipped so one bad
        record never aborts the batch.
        """
        existing = existing or {}
        total = len(inputs)

        skipped = sum(1 for r in inputs if r.get(self.index_key) in existing)
        if skipped > 0:
            print(f"[{self.stage_label}] Checkpoint: {skipped} already done, "
                  f"{total - skipped} remaining")

        records: List[Record] = []
        for i, record in enumerate(inputs):
            key = record.get(self.index_key)
            self.set_context(record, i)

            if key in existing:
                records.append(existing[key])
                print(self.format_skip_line(record, key, i, total))
                continue

            print(self.format_generating_line(record, key, i, total))
            try:
                result = self.produce(record, ctx)
                self.after_success(record, result)
                records.append(result)
                detail = self.describe_result(record, result)
                if detail:
                    print(detail)
                if save_callback:
                    save_callback(records)
            except Exception as e:  # isolate per-record failures
                print(f"[{self.stage_label}] ERROR processing uid={key}: {e}")
                traceback.print_exc()

        return records

    # ------------------------------------------------------------------ #
    # Full self-contained lifecycle (used by the future single-CLI / DAG).
    # ------------------------------------------------------------------ #
    def run(self, ctx: Any = None) -> List[Record]:
        """Read ``input_file``, resume from ``output_file``, process, write.

        Equivalent to the per-stage block in ``main.py`` (load upstream, load
        existing by key, process incrementally, final overwrite), but expressed
        once. Requires ``input_file`` and ``output_file`` to be set.
        """
        if not self.input_file or not self.output_file:
            raise ValueError(
                f"{type(self).__name__}.run() requires input_file and output_file"
            )
        inputs = read_jsonl(self.input_file)
        existing = index_by(read_jsonl(self.output_file), self.index_key)
        save = make_save_callback(self.output_file, self.stage_num)
        records = self.process_all(inputs, existing=existing, save_callback=save, ctx=ctx)
        write_jsonl(records, self.output_file)
        return records
