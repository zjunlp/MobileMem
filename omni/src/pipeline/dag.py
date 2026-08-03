"""The pipeline DAG: node registry + topological ordering + selection.

The record sub-graph (``profile`` .. ``annual_events``) writes the record JSONL
files. Media/index nodes delegate to each generator's ``main()`` entry, with
``RunContext`` threading both data JSONL and image-output paths through the
argparse adapters.

Adapters import their generators **lazily** (inside ``run``) so importing this
module, listing nodes, or running the record sub-graph never pulls heavy
optional deps (insightface / PaddleOCR).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from pipeline.spec import Node, RunContext

# Record-node output filenames
BASIC_PROFILES_FILE = "basic_profiles.jsonl"
INIT_STATES_FILE = "init_states.jsonl"
IMPORTANT_DATES_FILE = "important_dates.jsonl"
SOCIAL_GRAPH_FILE = "social_graph.jsonl"
ANNUAL_EVENTS_FILE = "annual_events.jsonl"

STAGE1_FILE = BASIC_PROFILES_FILE  # legacy alias, used by tests
STAGE2_FILE = INIT_STATES_FILE  # legacy alias, used by tests


# Gender fix (applied after the annual_events record node)
def fix_gender(value: str) -> str:
    v = value.strip()
    if v in ("Female", "\u5973"):
        return "Female"
    return "Male"


def fix_gender_in_annual_events(events_path: str) -> None:
    """Normalize ``Basic_Profile.gender`` in the annual_events file to Female/Male.

    Writes to a temp file first, then atomically replaces the original.
    """
    INPUT_FILE = Path(events_path)
    TMP_FILE = INPUT_FILE.with_suffix(".jsonl.tmp")

    changed = 0
    total = 0

    with open(INPUT_FILE, encoding="utf-8") as fin, \
            open(TMP_FILE, encoding="utf-8", mode="w") as fout:
        for line in fin:
            stripped = line.strip()
            if not stripped:
                fout.write(line)
                continue
            person = json.loads(stripped)
            total += 1
            bp = person.get("Basic_Profile", {})
            old = bp.get("gender", "")
            new = fix_gender(old)
            if old.strip() not in ("Female", "\u5973", "Male", "\u7537"):
                print(f"[WARN] uuid={person.get('uuid')}: unrecognized gender "
                      f"{old!r} forced to Male")
            if old != new:
                bp["gender"] = new
                changed += 1
            fout.write(json.dumps(person, ensure_ascii=False) + "\n")

    TMP_FILE.replace(INPUT_FILE)
    print(f"Done: {total} records total, {changed} gender fields modified.")


# Record adapters
def _uuid_keep_set(ctx: RunContext):
    """Record-node uuid filter as a set (None = all personas).

    Lets ``--uuid`` restrict the record nodes too, not just media nodes. A
    persona's uuid is its 0-based index in the sorted info-dir folder list.
    """
    return set(ctx.uuid_filter) if ctx.uuid_filter else None


def _select_by_uuid(records, uuid_keep):
    """Keep only records whose uuid is in ``uuid_keep`` (no-op when it is None)."""
    if uuid_keep is None:
        return records
    return [r for r in records if r.get("uuid") in uuid_keep]


def _kept_records(out_path, uuid_keep):
    """Records already on disk whose uuid is outside ``uuid_keep`` (to be preserved)."""
    from infra.store import load_existing_by_uuid
    if uuid_keep is None:
        return []
    return [rec for uid, rec in load_existing_by_uuid(out_path).items()
            if uid not in uuid_keep]


def _finalize(new_records, kept):
    """Merge filtered new records with preserved ones, ordered by uuid."""
    merged = list(new_records) + list(kept)
    merged.sort(key=lambda r: r.get("uuid", 0))
    return merged


def _run_profile(ctx: RunContext) -> None:
    from csv_parser import get_all_person_folders
    from generation.profile import generate_profiles
    from infra.store import (load_existing_by_role, make_preserving_save_callback,
                             read_jsonl)

    profiles_path = ctx.data_path(BASIC_PROFILES_FILE)
    # The CSV path is legacy (Chinese personas, uuid 0-9). Without an info dir
    # the node is a no-op and personas come solely from persona_seeds.
    if os.path.isdir(ctx.info_dir):
        person_folders = get_all_person_folders(ctx.info_dir)
    else:
        person_folders = []
        print(f"[profile] info dir not found ({ctx.info_dir}); "
              "skipping CSV personas (persona_seeds is the primary source)")
    uuid_keep = _uuid_keep_set(ctx)

    all_existing_records = read_jsonl(profiles_path)
    existing_by_role = {} if ctx.force else load_existing_by_role(profiles_path)
    roles_to_process = {
        f for i, f in enumerate(person_folders) if uuid_keep is None or i in uuid_keep
    }
    preserved_records = [
        r for r in all_existing_records
        if r.get("role_identity") and r.get("role_identity") not in roles_to_process
    ]
    save_callback = make_preserving_save_callback(
        profiles_path, preserved_records, label="profile")
    new_records = generate_profiles(
        person_folders, ctx.info_dir,
        existing_by_role, save_callback=save_callback, uuid_filter=uuid_keep)
    save_callback(new_records)
    print(f"[profile] {len(new_records) + len(preserved_records)} records -> {profiles_path}")


def _run_persona_seeds(ctx: RunContext) -> None:
    """Append LLM-seeded personas (no CSV source, e.g. foreign) to the profiles file.

    Runs after ``profile`` has written the CSV-derived rows (uuid 0-9) and adds
    the spec-driven seeds (uuid 10-19) carrying their own ``appearance`` block,
    so downstream nodes see the full persona set.
    """
    from generation.persona_seeds import generate_persona_seeds
    from infra.store import read_jsonl, write_jsonl_atomic

    profiles_path = ctx.data_path(BASIC_PROFILES_FILE)
    existing = read_jsonl(profiles_path) if os.path.exists(profiles_path) else []
    existing_uuids = {r.get("uuid") for r in existing if isinstance(r, dict)}
    uuid_keep = _uuid_keep_set(ctx)

    def _save(records):
        """Merge the seeds generated so far into the profiles file (checkpoint)."""
        new_uuids = {r.get("uuid") for r in records}
        merged = [r for r in existing if r.get("uuid") not in new_uuids] + list(records)
        merged.sort(key=lambda r: r.get("uuid", 0))
        write_jsonl_atomic(merged, profiles_path)

    new_records = generate_persona_seeds(
        existing_uuids, keep=uuid_keep, force=ctx.force, save_callback=_save)
    print(f"[persona_seeds] +{len(new_records)} seeded personas -> {profiles_path}")


def _run_life_state(ctx: RunContext) -> None:
    from generation.life_state import generate_life_states
    from infra.store import (load_existing_by_uuid, make_preserving_save_callback,
                             make_save_callback, read_jsonl, write_jsonl_atomic)

    profiles_path = ctx.data_path(BASIC_PROFILES_FILE)
    init_states_path = ctx.data_path(INIT_STATES_FILE)
    uuid_keep = _uuid_keep_set(ctx)
    profile_records = _select_by_uuid(read_jsonl(profiles_path), uuid_keep)
    existing = {} if ctx.force else load_existing_by_uuid(init_states_path)
    kept = _kept_records(init_states_path, uuid_keep)
    save_callback = (make_preserving_save_callback(init_states_path, kept, "life_state", key="uuid")
                     if uuid_keep is not None else make_save_callback(init_states_path, "life_state"))
    records = generate_life_states(
        profile_records, ctx.info_dir, ctx.prompts_dir,
        existing, save_callback=save_callback)
    write_jsonl_atomic(_finalize(records, kept) if uuid_keep is not None else records, init_states_path)
    print(f"[life_state] {len(records)} records -> {init_states_path}")


def _run_social_name_fix(ctx: RunContext) -> None:
    from generation.social_name_fix import fix_social_names

    init_states_path = ctx.data_path(INIT_STATES_FILE)
    fixes_count = fix_social_names(init_states_path, ctx.prompts_dir)
    print(f"[social_name_fix] {fixes_count} names fixed (rewrote {init_states_path})")


def _run_timeline_dates(ctx: RunContext) -> None:
    from generation.timeline_dates import generate_important_dates
    from infra.store import (load_existing_by_uuid, make_preserving_save_callback,
                             make_save_callback, read_jsonl, write_jsonl_atomic)

    init_states_path = ctx.data_path(INIT_STATES_FILE)
    dates_path = ctx.data_path(IMPORTANT_DATES_FILE)
    uuid_keep = _uuid_keep_set(ctx)
    init_state_records = _select_by_uuid(read_jsonl(init_states_path), uuid_keep)
    existing = {} if ctx.force else load_existing_by_uuid(dates_path)
    kept = _kept_records(dates_path, uuid_keep)
    save_callback = (make_preserving_save_callback(dates_path, kept, "timeline_dates", key="uuid")
                     if uuid_keep is not None else make_save_callback(dates_path, "timeline_dates"))
    records = generate_important_dates(
        init_state_records, ctx.prompts_dir,
        existing, save_callback=save_callback)
    write_jsonl_atomic(_finalize(records, kept) if uuid_keep is not None else records, dates_path)
    print(f"[timeline_dates] {len(records)} records -> {dates_path}")


def _run_social_world(ctx: RunContext) -> None:
    from generation.social_world import generate_social_graph
    from infra.store import (load_existing_by_uuid, make_preserving_save_callback,
                             make_save_callback, read_jsonl, write_jsonl_atomic)

    dates_path = ctx.data_path(IMPORTANT_DATES_FILE)
    social_graph_path = ctx.data_path(SOCIAL_GRAPH_FILE)
    uuid_keep = _uuid_keep_set(ctx)
    dates_records = _select_by_uuid(read_jsonl(dates_path), uuid_keep)
    existing = {} if ctx.force else load_existing_by_uuid(social_graph_path)
    kept = _kept_records(social_graph_path, uuid_keep)
    save_callback = (make_preserving_save_callback(social_graph_path, kept, "social_world", key="uuid")
                     if uuid_keep is not None else make_save_callback(social_graph_path, "social_world"))
    records = generate_social_graph(
        dates_records, ctx.prompts_dir, ctx.max_events,
        existing, save_callback=save_callback,
        max_workers=ctx.max_workers)
    write_jsonl_atomic(_finalize(records, kept) if uuid_keep is not None else records, social_graph_path)
    print(f"[social_world] {len(records)} records -> {social_graph_path}")


def _run_annual_events(ctx: RunContext) -> None:
    from generation.annual_events import generate_annual_events
    from infra.store import (load_existing_by_uuid, make_preserving_save_callback,
                             make_save_callback, read_jsonl, write_jsonl_atomic)

    dates_path = ctx.data_path(IMPORTANT_DATES_FILE)
    social_graph_path = ctx.data_path(SOCIAL_GRAPH_FILE)
    events_path = ctx.data_path(ANNUAL_EVENTS_FILE)
    uuid_keep = _uuid_keep_set(ctx)

    # Prefer the social_world output (with Social_Graph); fall back to the
    # timeline_dates output (legacy).
    if os.path.exists(social_graph_path):
        upstream_records = read_jsonl(social_graph_path)
    else:
        upstream_records = read_jsonl(dates_path)
    upstream_records = _select_by_uuid(upstream_records, uuid_keep)

    existing = {} if ctx.force else load_existing_by_uuid(events_path)
    kept = _kept_records(events_path, uuid_keep)
    save_callback = (make_preserving_save_callback(events_path, kept, "annual_events", key="uuid")
                     if uuid_keep is not None else make_save_callback(events_path, "annual_events"))
    records = generate_annual_events(
        upstream_records, ctx.prompts_dir, ctx.max_events,
        existing, save_callback=save_callback,
        max_workers=ctx.max_workers)
    write_jsonl_atomic(_finalize(records, kept) if uuid_keep is not None else records, events_path)

    # Always run the post-node gender fix (kept inside this node, per design).
    if os.path.exists(events_path):
        fix_gender_in_annual_events(events_path)
    print(f"[annual_events] {len(records)} records -> {events_path}")


def _delegate(module_name: str, argv_builder=None):
    """Build a run adapter that delegates to a generator module's ``main()``.

    Media / index generators still own an argparse ``main()``. ``argv_builder``
    (``Callable[[RunContext], list[str]]``) threads the supported ``RunContext``
    flags through; it must emit **only flags the target generator declares**.
    Path flags that have no clean RunContext mapping are left to the generator's
    own defaults (which equal the pipeline defaults via ``config``). The adapter
    resets ``sys.argv`` and swallows a clean ``SystemExit(0)``.
    """

    def run(ctx: RunContext) -> None:
        import importlib
        import sys

        module = importlib.import_module(module_name)
        main_fn = getattr(module, "main", None)
        if main_fn is None:
            raise NotImplementedError(
                f"{module_name} has no main() to delegate to; wire a programmatic "
                f"entry before running this node from the DAG.")
        extra = list(argv_builder(ctx)) if argv_builder is not None else []
        argv_backup = sys.argv
        sys.argv = [module_name.rsplit(".", 1)[-1], *extra]
        try:
            main_fn()
        except SystemExit as exc:  # generators may call sys.exit(0)
            if exc.code not in (0, None):
                raise
        finally:
            sys.argv = argv_backup

    return run


# Data-file names under output_dir. Each generator's argparse default is
# OUTPUT_DIR/data/<name>, so these map cleanly to RunContext.output_dir.
SUB_EVENTS_FILE = "sub_events.jsonl"
GROUP_CHATS_FILE = "group_chats.jsonl"
S10_SUMMARY_FILE = "image_summaries.jsonl"
S10_MERGED_FILE = "merged_memories.jsonl"
APP_TRACE_FILE = "app_screenshots.jsonl"
EVENT_PHOTO_FILE = "event_images.jsonl"
DOCUMENT_FILE = "document_records.jsonl"

OUTPUT_OWNERS = {
    ANNUAL_EVENTS_FILE: "annual_events",
    SUB_EVENTS_FILE: "sub_events",
    GROUP_CHATS_FILE: "conversation",
    APP_TRACE_FILE: "app_trace",
    DOCUMENT_FILE: "document",
    EVENT_PHOTO_FILE: "event_photo",
}


# Emit only flags the generator declares. Data-file paths are threaded from
# ctx.output_dir, and rendered media paths from ctx.image_dir, so a custom DAG
# run stays self-contained.
def _uuid_multi(ctx: RunContext):
    if ctx.uuid_filter:
        return ["--uuid-filter", *[str(u) for u in ctx.uuid_filter]]
    return []


def _force(ctx: RunContext):
    """Unified regenerate switch -> every generator's ``--force`` flag.

    ``RunContext.force`` (from ``--force``) maps to the single ``--force`` flag
    that every media/index generator now accepts; resume (the default) emits
    nothing, so generators keep their resume-by-default behavior.
    """
    return ["--force"] if ctx.force else []


def _data(ctx: RunContext, name: str) -> str:
    return os.path.join(ctx.output_dir, name)


# "profile" may legitimately write an empty file on a seeds-only run (no CSV
# info dir); persona_seeds then fills the profiles file.
_ALLOW_EMPTY_JSONL_NODES = {"profile", "sub_events", "app_trace", "document"}


# Record nodes whose output must cover every uuid present in their input file
# (a missing uuid means a persona failed mid-node and downstream nodes would
# silently run on incomplete data). "annual_events" reads the social_world
# output when it exists and falls back to the timeline_dates output, matching
# _run_annual_events. Not applied to profile (row count set by the CSV dir),
# persona_seeds (set by built-in specs), sub_events (may be empty), or media
# nodes.
_RECORD_INPUT_FILE = {
    "life_state": BASIC_PROFILES_FILE,
    "timeline_dates": INIT_STATES_FILE,
    "social_world": IMPORTANT_DATES_FILE,
    "annual_events": SOCIAL_GRAPH_FILE,
}


def _count_jsonl(path: str) -> int:
    count = 0
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Invalid JSONL in {path} at line {line_no}: {exc}") from exc
            count += 1
    return count


def _jsonl_uuid_set(path: str) -> set:
    """The set of uuids present in a JSONL file (empty when the file is absent)."""
    if not os.path.exists(path):
        return set()
    with open(path, "r", encoding="utf-8") as f:
        return {
            record["uuid"]
            for record in (json.loads(line) for line in f if line.strip())
            if isinstance(record, dict) and record.get("uuid") is not None
        }


def _file_fingerprint(path: str):
    if not os.path.exists(path):
        return None
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_non_owned_outputs(ctx: RunContext, node_name: str):
    """Capture protected output state before a node runs."""
    return {
        filename: _file_fingerprint(_data(ctx, filename))
        for filename, owner in OUTPUT_OWNERS.items()
        if owner != node_name
    }


def assert_non_owned_outputs_unchanged(ctx: RunContext, node_name: str, before) -> None:
    """Fail when a node creates, removes, or rewrites another node's output."""
    changed = [
        filename for filename, fingerprint in before.items()
        if _file_fingerprint(_data(ctx, filename)) != fingerprint
    ]
    if changed:
        details = ', '.join(
            f"{filename} (owner={OUTPUT_OWNERS[filename]})" for filename in changed
        )
        raise RuntimeError(f"Node {node_name!r} modified non-owned output(s): {details}")


def _verify_uuid_coverage(ctx: RunContext, node: Node) -> None:
    """Fail when a record node's output misses uuids its input file provides."""
    input_path = _data(ctx, _RECORD_INPUT_FILE[node.name])
    if node.name == "annual_events" and not os.path.exists(input_path):
        input_path = _data(ctx, IMPORTANT_DATES_FILE)

    expected = _jsonl_uuid_set(input_path)
    if ctx.uuid_filter:
        expected &= set(ctx.uuid_filter)
    actual = _jsonl_uuid_set(_data(ctx, node.outputs[0]))
    missing = expected - actual
    if missing:
        raise RuntimeError(
            f"Node {node.name!r} output is missing uuid(s) {sorted(missing)}: "
            f"{_data(ctx, node.outputs[0])} does not cover the personas in {input_path}")


def verify_node_outputs(ctx: RunContext, node: Node) -> None:
    """Enforce the DAG-level output contract for a completed node.

    Delegated generator mains may log and return after per-record failures. The
    DAG treats a node as successful only after its declared artifacts exist,
    non-optional JSONL outputs contain records, and (for record nodes with a
    per-persona input) every expected uuid is covered.
    """
    if node.verify is not None:
        node.verify(ctx, node)
        return

    for name in node.outputs:
        path = _data(ctx, name)
        if not os.path.exists(path):
            raise RuntimeError(f"Node {node.name!r} did not create required output: {path}")
        if name.endswith(".jsonl"):
            records = _count_jsonl(path)
            if records == 0 and node.name not in _ALLOW_EMPTY_JSONL_NODES:
                raise RuntimeError(f"Node {node.name!r} wrote no records to required output: {path}")

    if node.name in _RECORD_INPUT_FILE:
        _verify_uuid_coverage(ctx, node)


def _verify_scenery(ctx: RunContext, node: Node) -> None:
    manifest_path = os.path.join(ctx.image_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        raise RuntimeError(f"Node {node.name!r} did not create required output: {manifest_path}")
    with open(manifest_path, "r", encoding="utf-8") as f:
        try:
            manifest = json.load(f)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid scenery manifest: {manifest_path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise RuntimeError(f"Invalid scenery manifest shape: {manifest_path}")

    expected_input = _data(ctx, ANNUAL_EVENTS_FILE)
    upstream_records = _count_jsonl(expected_input) if os.path.exists(expected_input) else 0
    generated_files = [
        filename
        for by_category in manifest.values()
        if isinstance(by_category, dict)
        for files in by_category.values()
        if isinstance(files, list)
        for filename in files
    ]
    if upstream_records > 0 and not generated_files:
        raise RuntimeError(f"Node {node.name!r} wrote an empty scenery manifest: {manifest_path}")


def _argv_sub_events(ctx: RunContext):
    argv = ["--input", _data(ctx, ANNUAL_EVENTS_FILE),
            "--output", _data(ctx, SUB_EVENTS_FILE),
            "--max-workers", str(ctx.max_workers)]
    if ctx.model:
        argv += ["--model", ctx.model]
    argv += _uuid_multi(ctx)
    argv += _force(ctx)
    return argv


def _argv_conversation(ctx: RunContext):
    return ["--input-file", _data(ctx, ANNUAL_EVENTS_FILE),
            "--output-file", _data(ctx, GROUP_CHATS_FILE),
            "--sub-events-file", _data(ctx, SUB_EVENTS_FILE),
            "--prompts-dir", ctx.prompts_dir,
            "--image-dir", ctx.image_dir,
            "--max-workers", str(ctx.max_workers),
            *_uuid_multi(ctx),
            *_force(ctx)]


def _argv_app_trace(ctx: RunContext):
    return ["--events-file", _data(ctx, ANNUAL_EVENTS_FILE),
            "--output-dir", ctx.image_dir,
            "--manifest-file", _data(ctx, APP_TRACE_FILE),
            "--sub-events-file", _data(ctx, SUB_EVENTS_FILE),
            *_uuid_multi(ctx),
            *_force(ctx)]


def _argv_event_photo(ctx: RunContext):
    return ["--events-file", _data(ctx, ANNUAL_EVENTS_FILE),
            "--sub-events-file", _data(ctx, SUB_EVENTS_FILE),
            "--image-base-dir", ctx.image_dir,
            "--max-workers", str(ctx.max_workers),
            *_uuid_multi(ctx),
            *_force(ctx)]


def _argv_document(ctx: RunContext):
    return ["--events-file", _data(ctx, ANNUAL_EVENTS_FILE),
            "--output-dir", ctx.image_dir,
            "--image-dir", ctx.image_dir,
            "--manifest-file", _data(ctx, DOCUMENT_FILE),
            "--sub-events-file", _data(ctx, SUB_EVENTS_FILE),
            *_uuid_multi(ctx),
            *_force(ctx)]


def _argv_scenery(ctx: RunContext):
    return ["--input-file", _data(ctx, ANNUAL_EVENTS_FILE),
            "--output-dir", ctx.image_dir,
            *_uuid_multi(ctx),
            *_force(ctx)]


def _argv_memory_summary(ctx: RunContext):
    # memory_summary uses --workers (not --max-workers)
    return ["--image-base-dir", ctx.image_dir,
            "--output-file", _data(ctx, S10_SUMMARY_FILE),
            "--merged-output", _data(ctx, S10_MERGED_FILE),
            "--profiles-file", _data(ctx, BASIC_PROFILES_FILE),
            "--events-file", _data(ctx, ANNUAL_EVENTS_FILE),
            "--sub-events-file", _data(ctx, SUB_EVENTS_FILE),
            "--document-file", _data(ctx, DOCUMENT_FILE),
            "--workers", str(ctx.max_workers),
            *_uuid_multi(ctx),
            *_force(ctx)]


# Node registry (see the Quickstart node table in README.md)
NODES: Dict[str, Node] = {
    "profile": Node(
        "profile", (), (BASIC_PROFILES_FILE,), _run_profile,
        "record", "Basic profiles from CSV (legacy path, uuid 0-9)"),
    "persona_seeds": Node(
        "persona_seeds", ("profile",), (BASIC_PROFILES_FILE,), _run_persona_seeds,
        "record", "Seed personas from specs via LLM (primary path)"),
    "life_state": Node(
        "life_state", ("persona_seeds",), (INIT_STATES_FILE,), _run_life_state,
        "record", "Init states (CSV + LLM)"),
    "social_name_fix": Node(
        "social_name_fix", ("life_state",), (INIT_STATES_FILE,), _run_social_name_fix,
        "normalizer", "Fix social relationship names; rewrites the init-states file"),
    "timeline_dates": Node(
        "timeline_dates", ("social_name_fix",), (IMPORTANT_DATES_FILE,), _run_timeline_dates,
        "record", "Important dates (LLM)"),
    "social_world": Node(
        "social_world", ("timeline_dates",), (SOCIAL_GRAPH_FILE,), _run_social_world,
        "record", "Social graph (LLM)"),
    "annual_events": Node(
        "annual_events", ("social_world",), (ANNUAL_EVENTS_FILE,), _run_annual_events,
        "record", "Annual events (LLM) + gender fix"),
    "sub_events": Node(
        "sub_events", ("annual_events",), ("sub_events.jsonl",),
        _delegate("generation.sub_events", _argv_sub_events),
        "record", "Sub-events (LLM)"),
    "conversation": Node(
        "conversation", ("annual_events", "social_world", "sub_events"),
        ("group_chats.jsonl",),
        _delegate("generation.conversation", _argv_conversation),
        "media", "Group chats + images"),
    "app_trace": Node(
        "app_trace", ("annual_events", "sub_events"),
        (APP_TRACE_FILE,),
        _delegate("generation.app_trace", _argv_app_trace),
        "media", "App screenshots + images"),
    "event_photo": Node(
        "event_photo", ("conversation", "annual_events", "sub_events"),
        (EVENT_PHOTO_FILE,),
        _delegate("generation.event_photo", _argv_event_photo),
        "media", "Event images + images"),
    "document": Node(
        "document", ("event_photo", "annual_events"),
        (DOCUMENT_FILE,),
        _delegate("generation.document", _argv_document),
        "media", "Tickets / transfers / moments + images"),
    "scenery": Node(
        "scenery", ("annual_events",), (),
        _delegate("generation.scenery", _argv_scenery),
        "media", "Scenery images", verify=_verify_scenery),
    "memory_summary": Node(
        "memory_summary",
        ("conversation", "app_trace", "document", "event_photo", "scenery", "sub_events"),
        ("total_images.jsonl",),
        _delegate("generation.memory_summary", _argv_memory_summary),
        "index", "Image summaries + merge"),
}


# Graph algorithms
def _declaration_index() -> Dict[str, int]:
    return {name: i for i, name in enumerate(NODES)}


def topo_order(names: Optional[Iterable[str]] = None) -> List[str]:
    """Kahn topological sort over ``names`` (default: all nodes).

    Stable tie-break by declaration order, so runs are reproducible. Raises
    ``ValueError`` on a cycle or an unknown name.
    """
    selected = list(NODES.keys()) if names is None else list(dict.fromkeys(names))
    sel = set(selected)
    for n in selected:
        if n not in NODES:
            raise ValueError(f"Unknown node: {n!r}")

    order_index = _declaration_index()
    indeg = {n: 0 for n in selected}
    for n in selected:
        for dep in NODES[n].depends_on:
            if dep in sel:
                indeg[n] += 1

    ready = sorted([n for n in selected if indeg[n] == 0], key=lambda x: order_index[x])
    out: List[str] = []
    while ready:
        n = ready.pop(0)
        out.append(n)
        for m in selected:
            if n in NODES[m].depends_on and m not in out and m not in ready:
                indeg[m] -= 1
                if indeg[m] == 0:
                    ready.append(m)
        ready.sort(key=lambda x: order_index[x])

    if len(out) != len(selected):
        raise ValueError(f"Cycle detected among nodes: {sel - set(out)}")
    return out


def _dependents() -> Dict[str, List[str]]:
    rev: Dict[str, List[str]] = {n: [] for n in NODES}
    for n, node in NODES.items():
        for dep in node.depends_on:
            rev[dep].append(n)
    return rev


def _descendants(name: str) -> set:
    rev = _dependents()
    seen: set = set()
    stack = [name]
    while stack:
        cur = stack.pop()
        for child in rev.get(cur, ()):  # noqa: B007
            if child not in seen:
                seen.add(child)
                stack.append(child)
    return seen


def select(only: Optional[str] = None, from_: Optional[str] = None) -> List[str]:
    """Return the topo-ordered nodes to run for the given selection.

    ``only`` = just that node; ``from_`` = that node plus every descendant;
    neither = the whole graph.
    """
    if only is not None:
        if only not in NODES:
            raise ValueError(f"Unknown node: {only!r}")
        return topo_order([only])
    if from_ is not None:
        if from_ not in NODES:
            raise ValueError(f"Unknown node: {from_!r}")
        return topo_order({from_, *_descendants(from_)})
    return topo_order()


def validate() -> None:
    """Sanity-check the graph: known deps + acyclic."""
    for n, node in NODES.items():
        for dep in node.depends_on:
            if dep not in NODES:
                raise ValueError(f"Node {n!r} depends on unknown node {dep!r}")
    topo_order()  # raises on cycle
