"""Unified JSONL data-access and checkpoint layer.

The single home for the pipeline's JSONL I/O and checkpointing:

- ``read_jsonl`` / ``write_jsonl`` (jsonlines-based I/O)
- ``load_existing_by_role`` / ``load_existing_by_uuid`` (indexing)
- ``make_save_callback`` (incremental, resume-safe saving)
- ``stage1_save_callback`` (high-uuid preserve merge)

Records are dumped with ``json.dumps(..., ensure_ascii=False)``, one record per
line.

The module depends on the standard library only, has no import-time side
effects, and never imports stages, domain logic or models — it sits at the
bottom of the dependency stack (L1 infrastructure).
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Callable, Dict, Iterable, List, Sequence

Record = Dict[str, Any]


# ---------------------------------------------------------------------------
# Low-level JSONL I/O
# ---------------------------------------------------------------------------

def read_jsonl(path: str) -> List[Record]:
    """Read a JSONL file and return its records.

    Returns an empty list when the file does not exist, and silently skips
    blank lines. Matches the previous ``common.read_jsonl`` behavior.
    """
    if not os.path.exists(path):
        return []
    records: List[Record] = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def write_jsonl(records: Iterable[Record], path: str) -> None:
    """Overwrite ``path`` with ``records``, one JSON object per line.

    Parent directories are created as needed. The output is byte-for-byte
    identical to the previous ``jsonlines``-based writer.
    """
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')


def write_jsonl_atomic(records: Iterable[Record], path: str) -> None:
    """Like :func:`write_jsonl` but crash-safe: write a ``.tmp`` then replace.

    The final file content is identical to :func:`write_jsonl`; only the write
    mechanism differs (a partially written file can never clobber a good one).
    """
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp_path = path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
    os.replace(tmp_path, path)


_APPEND_LOCK = threading.Lock()


def append_jsonl(path: str, record: Record) -> None:
    """Append a single record as one JSONL line (thread-safe).

    Parent dirs are created before appending.
    """
    parent = os.path.dirname(path) or '.'
    os.makedirs(parent, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False)
    with _APPEND_LOCK:
        with open(path, 'a', encoding='utf-8') as f:
            f.write(line + '\n')


# ---------------------------------------------------------------------------
# Indexing (checkpoint / resume helpers)
# ---------------------------------------------------------------------------

def index_by(records: Sequence[Record], key: str) -> Dict[Any, Record]:
    """Index records by ``key``; later records win on duplicate keys.

    Records whose key is ``None`` or an empty string are skipped (so ``uuid``
    values of ``0`` are kept, but blank ``role_identity`` values are not).
    """
    out: Dict[Any, Record] = {}
    for r in records:
        k = r.get(key)
        if k is not None and k != '':
            out[k] = r
    return out


def load_existing_by_role(jsonl_path: str) -> Dict[str, Record]:
    """Load a JSONL file and index it by ``role_identity`` for resume.

    Preserves the original console message and best-effort error handling.
    """
    existing: Dict[str, Record] = {}
    if os.path.exists(jsonl_path):
        try:
            records = read_jsonl(jsonl_path)
            for r in records:
                role = r.get('role_identity', '')
                if role:
                    existing[role] = r
            if existing:
                print(f"[Checkpoint] Loaded {len(existing)} existing records from {jsonl_path}")
        except Exception as e:
            print(f"[Checkpoint] WARNING: Could not read {jsonl_path}: {e}")
    return existing


def load_existing_by_uuid(jsonl_path: str) -> Dict[Any, Record]:
    """Load a JSONL file and index it by ``uuid`` for resume.

    Preserves the original console message and best-effort error handling.
    """
    existing: Dict[Any, Record] = {}
    if os.path.exists(jsonl_path):
        try:
            records = read_jsonl(jsonl_path)
            for r in records:
                uid = r.get('uuid')
                if uid is not None:
                    existing[uid] = r
            if existing:
                print(f"[Checkpoint] Loaded {len(existing)} existing records from {jsonl_path}")
        except Exception as e:
            print(f"[Checkpoint] WARNING: Could not read {jsonl_path}: {e}")
    return existing


# ---------------------------------------------------------------------------
# Incremental save callbacks (used by stage generators)
# ---------------------------------------------------------------------------

def make_save_callback(output_path: str, stage_num: Any) -> Callable[[Sequence[Record]], None]:
    """Build a callback that rewrites ``output_path`` after each batch.

    Equivalent to the previous ``common.make_save_callback``: the caller owns
    the growing record list and we persist the whole list (resume-safe).
    """
    def _save(records: Sequence[Record]) -> None:
        write_jsonl(records, output_path)
        print(f"  [Save] Stage{stage_num}: {len(records)} records saved (checkpoint)")
    return _save


def make_preserving_save_callback(
    output_path: str,
    preserved_records: Sequence[Record],
    stage_num: Any = 1,
    key: str = 'role_identity',
) -> Callable[[Sequence[Record]], None]:
    """Build a save callback that keeps pre-existing out-of-scope records.

    Implements the stage1 "high-uuid preserve" merge: new records are merged with
    previously generated records that are *not* in the current processing scope
    (e.g. high-uuid personas seeded by stage0), de-duplicated by ``key``, sorted
    by ``uuid``, then written.
    """
    preserved = list(preserved_records)

    def _save(new_records: Sequence[Record]) -> None:
        merged = list(new_records) + preserved
        seen: set = set()
        final: List[Record] = []
        for record in merged:
            rid = record.get(key, '')
            if rid and rid not in seen:
                final.append(record)
                seen.add(rid)
        final.sort(key=lambda x: x.get('uuid', 0))
        write_jsonl(final, output_path)
        print(f"  [Save] Stage{stage_num}: {len(final)} records saved (checkpoint)")

    return _save


# ---------------------------------------------------------------------------
# Object-oriented facade
# ---------------------------------------------------------------------------

class JsonlStore:
    """A keyed view over one JSONL file: read, index, append, upsert, save.

    One store instance maps to one file. ``key`` is the field used for indexing
    and upserts (``uuid`` by default; stage1 uses ``role_identity``). This is
    the single abstraction that the upcoming ``Stage`` base class builds on.
    """

    def __init__(self, path: str, key: str = 'uuid') -> None:
        self.path = path
        self.key = key

    def read(self) -> List[Record]:
        """Return all records (``[]`` if the file does not exist)."""
        return read_jsonl(self.path)

    def index(self) -> Dict[Any, Record]:
        """Return ``{key_value: record}`` for checkpoint/resume."""
        return index_by(self.read(), self.key)

    def save_all(self, records: Iterable[Record]) -> None:
        """Overwrite the file with ``records``."""
        write_jsonl(records, self.path)

    def save_all_atomic(self, records: Iterable[Record]) -> None:
        """Overwrite the file atomically (``.tmp`` then replace)."""
        write_jsonl_atomic(records, self.path)

    def append(self, record: Record) -> None:
        """Append a single record (thread-safe)."""
        append_jsonl(self.path, record)

    def upsert(self, record: Record) -> None:
        """Insert or replace ``record`` by ``key`` and rewrite atomically.

        Resume-safe: the on-disk file is always a complete, valid snapshot.
        """
        records = self.read()
        target = record.get(self.key)
        for i, existing in enumerate(records):
            if existing.get(self.key) == target:
                records[i] = record
                break
        else:
            records.append(record)
        write_jsonl_atomic(records, self.path)
