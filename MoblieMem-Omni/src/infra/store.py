"""Unified JSONL data-access and checkpoint layer.

The single home for the pipeline's JSONL I/O and checkpointing:

- ``read_jsonl`` / ``write_jsonl`` (jsonlines-based I/O)
- ``load_existing_by_role`` / ``load_existing_by_uuid`` (indexing)
- ``make_save_callback`` (incremental, resume-safe saving)
- ``make_preserving_save_callback`` (high-uuid preserve merge)

Records are dumped with ``json.dumps(..., ensure_ascii=False)``, one record per
line.

The module depends on the standard library only, has no import-time side
effects, and never imports generators, domain logic or models — it sits at the
bottom of the dependency stack (L1 infrastructure).
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

Record = Dict[str, Any]
ManifestKey = Tuple[Any, str, str]


# Low-level JSONL I/O

def read_jsonl(path: str) -> List[Record]:
    """Read a JSONL file and return its records.

    Returns an empty list when the file does not exist, and silently skips
    blank lines.
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

    Parent directories are created as needed.
    """
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')


def write_jsonl_atomic(records: Iterable[Record], path: str) -> None:
    """Like :func:`write_jsonl` but crash-safe: write a ``.tmp`` then replace.

    A partially written file can never clobber a good one. On Windows, virus
    scanners and editors can briefly hold the destination without sharing
    delete access, so retry that transient ``PermissionError`` before failing.
    """
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp_path = path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
    for attempt in range(5):
        try:
            os.replace(tmp_path, path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.1 * (2 ** attempt))


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


# Indexing (checkpoint / resume helpers)

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


def manifest_record_key(record: Record, type_field: str) -> Optional[ManifestKey]:
    """Return the canonical ``(uuid, sub_event_id, type)`` manifest key."""
    uid = record.get('uuid')
    event_id = record.get('sub_event_id')
    if event_id is None:
        event_id = record.get('event_id')
    record_type = record.get(type_field)
    if uid is None or event_id is None or record_type in (None, ''):
        return None
    return uid, str(event_id), str(record_type)


def load_manifest_index(path: str, type_field: str) -> Dict[ManifestKey, Record]:
    """Load a per-image manifest; later duplicate keys win."""
    indexed: Dict[ManifestKey, Record] = {}
    for record in read_jsonl(path):
        key = manifest_record_key(record, type_field)
        if key is not None:
            indexed[key] = record
    return indexed


def write_manifest_index_atomic(
    records: Dict[ManifestKey, Record], path: str
) -> None:
    """Persist a complete composite-key manifest in deterministic order."""
    def sort_key(item: Tuple[ManifestKey, Record]):
        uid, event_id, record_type = item[0]
        try:
            uid_key = (0, int(uid))
        except (TypeError, ValueError):
            uid_key = (1, str(uid))
        return uid_key, event_id, record_type

    ordered = [record for _, record in sorted(records.items(), key=sort_key)]
    write_jsonl_atomic(ordered, path)


def load_existing_by_role(jsonl_path: str) -> Dict[str, Record]:
    """Load a JSONL file and index it by ``role_identity`` for resume.

    Raises ``RuntimeError`` when the file exists but cannot be read/parsed:
    silently returning an empty index would rerun every record (and re-spend
    the LLM budget) instead of surfacing the corruption.
    """
    existing: Dict[str, Record] = {}
    if os.path.exists(jsonl_path):
        try:
            records = read_jsonl(jsonl_path)
        except Exception as e:
            raise RuntimeError(f"Corrupt checkpoint file {jsonl_path}: {e}") from e
        for r in records:
            role = r.get('role_identity', '')
            if role:
                existing[role] = r
        if existing:
            print(f"[Checkpoint] Loaded {len(existing)} existing records from {jsonl_path}")
    return existing


def load_existing_by_uuid(jsonl_path: str) -> Dict[Any, Record]:
    """Load a JSONL file and index it by ``uuid`` for resume.

    Raises ``RuntimeError`` when the file exists but cannot be read/parsed:
    silently returning an empty index would rerun every record (and re-spend
    the LLM budget) instead of surfacing the corruption.
    """
    existing: Dict[Any, Record] = {}
    if os.path.exists(jsonl_path):
        try:
            records = read_jsonl(jsonl_path)
        except Exception as e:
            raise RuntimeError(f"Corrupt checkpoint file {jsonl_path}: {e}") from e
        for r in records:
            uid = r.get('uuid')
            if uid is not None:
                existing[uid] = r
        if existing:
            print(f"[Checkpoint] Loaded {len(existing)} existing records from {jsonl_path}")
    return existing


# Incremental save callbacks (used by the record generators)

def make_save_callback(output_path: str, label: Any) -> Callable[[Sequence[Record]], None]:
    """Build a callback that rewrites ``output_path`` after each batch.

    ``label`` is the pipeline node name shown in the save message. The caller
    owns the growing record list and we persist the whole list atomically, so a
    crash mid-write never corrupts the checkpoint.
    """
    def _save(records: Sequence[Record]) -> None:
        write_jsonl_atomic(records, output_path)
        print(f"  [{label}] {len(records)} records saved (checkpoint)")
    return _save


def make_preserving_save_callback(
    output_path: str,
    preserved_records: Sequence[Record],
    label: Any = 'profile',
    key: str = 'role_identity',
) -> Callable[[Sequence[Record]], None]:
    """Build a save callback that keeps pre-existing out-of-scope records.

    Implements the profile node's "high-uuid preserve" merge: new records are
    merged with previously generated records that are *not* in the current
    processing scope (e.g. high-uuid personas seeded by persona_seeds),
    de-duplicated by ``key``, sorted by ``uuid``, then written.
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
        write_jsonl_atomic(final, output_path)
        print(f"  [{label}] {len(final)} records saved (checkpoint)")

    return _save
