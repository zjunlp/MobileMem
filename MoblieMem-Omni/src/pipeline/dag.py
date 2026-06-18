"""The pipeline DAG: node registry + topological ordering + selection.

The record sub-graph (``profile`` .. ``annual_events``) mirrors ``main.py``.
Media/index nodes delegate to each generator's ``main()`` entry, with
``RunContext`` threading both data JSONL and image-output paths through the
argparse adapters.

Adapters import their generators **lazily** (inside ``run``) so importing this
module, listing nodes, or running the record sub-graph never pulls heavy
optional deps (insightface / PaddleOCR).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from pipeline.spec import Node, RunContext

# ---------------------------------------------------------------------------
# Stage output filenames (mirror main.py)
# ---------------------------------------------------------------------------
STAGE1_FILE = "stage1_basic_profiles.jsonl"
STAGE2_FILE = "stage2_init_states.jsonl"
STAGE3_FILE = "stage3_important_dates.jsonl"
STAGE3_9_FILE = "stage3_9_social_graph.jsonl"
STAGE4_FILE = "stage4_annual_events.jsonl"


# ---------------------------------------------------------------------------
# Gender fix (applied after the annual_events record stage)
# ---------------------------------------------------------------------------
def fix_gender(value: str) -> str:
    v = value.strip()
    if v in ("Female", "\u5973"):
        return "Female"
    return "Male"


def fix_gender_in_stage4(stage4_path: str) -> None:
    """Normalize ``Basic_Profile.gender`` in the stage-4 file to Female/Male.

    Writes to a temp file first, then atomically replaces the original.
    """
    INPUT_FILE = Path(stage4_path)
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
            if old != new:
                bp["gender"] = new
                changed += 1
            fout.write(json.dumps(person, ensure_ascii=False) + "\n")

    TMP_FILE.replace(INPUT_FILE)
    print(f"Done: {total} records total, {changed} gender fields modified.")


# ---------------------------------------------------------------------------
# Record adapters — mirror main.py's per-stage logic exactly (byte-faithful I/O)
# ---------------------------------------------------------------------------
def _uuid_keep_set(ctx: RunContext):
    """Record-stage uuid filter as a set (None = all personas).

    Lets ``--uuid`` restrict the record stages too, not just media nodes. A
    persona's uuid is its 0-based index in the sorted info-dir folder list.
    """
    return set(ctx.uuid_filter) if ctx.uuid_filter else None


def _select_by_uuid(records, keep):
    """Keep only records whose uuid is in ``keep`` (no-op when ``keep`` is None)."""
    if keep is None:
        return records
    return [r for r in records if r.get("uuid") in keep]


def _kept_records(out_path, keep):
    """Records already on disk whose uuid is outside ``keep`` (to be preserved)."""
    from common import load_existing_by_uuid
    if keep is None:
        return []
    return [rec for uid, rec in load_existing_by_uuid(out_path).items() if uid not in keep]


def _finalize(new_records, kept):
    """Merge filtered new records with preserved ones, ordered by uuid."""
    merged = list(new_records) + list(kept)
    merged.sort(key=lambda r: r.get("uuid", 0))
    return merged


def _run_profile(ctx: RunContext) -> None:
    from common import load_existing_by_role, read_jsonl
    from csv_parser import get_all_person_folders
    from generation.profile import generate_stage1
    from infra.store import make_preserving_save_callback

    stage1_path = ctx.data_path(STAGE1_FILE)
    person_folders = get_all_person_folders(ctx.info_dir)
    keep = _uuid_keep_set(ctx)

    all_existing_records = read_jsonl(stage1_path)
    existing_by_role = {} if ctx.force else load_existing_by_role(stage1_path)
    roles_to_process = {
        f for i, f in enumerate(person_folders) if keep is None or i in keep
    }
    preserved_records = [
        r for r in all_existing_records
        if r.get("role_identity") and r.get("role_identity") not in roles_to_process
    ]
    save_callback = make_preserving_save_callback(
        stage1_path, preserved_records, stage_num=1)
    new_records = generate_stage1(
        person_folders, ctx.info_dir, ctx.prompts_dir,
        existing_by_role, save_callback=save_callback, uuid_filter=keep)
    save_callback(new_records)
    print(f"[profile] {len(new_records) + len(preserved_records)} records -> {stage1_path}")


def _run_persona_seeds(ctx: RunContext) -> None:
    """Append LLM-seeded personas (no CSV source, e.g. foreign) to the stage1 file.

    Runs after ``profile`` has written the CSV-derived rows (uuid 0-9) and adds
    the spec-driven seeds (uuid 10-19) carrying their own ``appearance`` block,
    so downstream stages see the full persona set.
    """
    from common import read_jsonl, write_jsonl
    from generation.persona_seeds import generate_persona_seeds

    stage1_path = ctx.data_path(STAGE1_FILE)
    existing = read_jsonl(stage1_path) if os.path.exists(stage1_path) else []
    existing_uuids = {r.get("uuid") for r in existing if isinstance(r, dict)}
    keep = _uuid_keep_set(ctx)
    new_records = generate_persona_seeds(existing_uuids, keep=keep, force=ctx.force)
    if new_records:
        new_uuids = {r.get("uuid") for r in new_records}
        merged = [r for r in existing if r.get("uuid") not in new_uuids] + new_records
        merged.sort(key=lambda r: r.get("uuid", 0))
        write_jsonl(merged, stage1_path)
    print(f"[persona_seeds] +{len(new_records)} seeded personas -> {stage1_path}")


def _run_life_state(ctx: RunContext) -> None:
    from common import load_existing_by_uuid, make_save_callback, read_jsonl, write_jsonl
    from infra.store import make_preserving_save_callback
    from generation.life_state import generate_life_states

    stage1_path = ctx.data_path(STAGE1_FILE)
    stage2_path = ctx.data_path(STAGE2_FILE)
    keep = _uuid_keep_set(ctx)
    stage1_records = _select_by_uuid(read_jsonl(stage1_path), keep)
    existing = {} if ctx.force else load_existing_by_uuid(stage2_path)
    kept = _kept_records(stage2_path, keep)
    save_callback = (make_preserving_save_callback(stage2_path, kept, 2, key="uuid")
                     if keep is not None else make_save_callback(stage2_path, 2))
    records = generate_life_states(
        stage1_records, ctx.info_dir, ctx.prompts_dir,
        existing, save_callback=save_callback)
    write_jsonl(_finalize(records, kept) if keep is not None else records, stage2_path)
    print(f"[life_state] {len(records)} records -> {stage2_path}")


def _run_social_name_fix(ctx: RunContext) -> None:
    from generation.social_world import fix_social_names

    stage2_path = ctx.data_path(STAGE2_FILE)
    fixes_count = fix_social_names(stage2_path, ctx.prompts_dir)
    print(f"[social_name_fix] {fixes_count} names fixed (rewrote {stage2_path})")


def _run_timeline_dates(ctx: RunContext) -> None:
    from common import load_existing_by_uuid, make_save_callback, read_jsonl, write_jsonl
    from infra.store import make_preserving_save_callback
    from generation.timeline_dates import generate_important_dates

    stage2_path = ctx.data_path(STAGE2_FILE)
    stage3_path = ctx.data_path(STAGE3_FILE)
    keep = _uuid_keep_set(ctx)
    stage2_records = _select_by_uuid(read_jsonl(stage2_path), keep)
    existing = {} if ctx.force else load_existing_by_uuid(stage3_path)
    kept = _kept_records(stage3_path, keep)
    save_callback = (make_preserving_save_callback(stage3_path, kept, 3, key="uuid")
                     if keep is not None else make_save_callback(stage3_path, 3))
    records = generate_important_dates(
        stage2_records, ctx.prompts_dir,
        existing, save_callback=save_callback)
    write_jsonl(_finalize(records, kept) if keep is not None else records, stage3_path)
    print(f"[timeline_dates] {len(records)} records -> {stage3_path}")


def _run_social_world(ctx: RunContext) -> None:
    from common import load_existing_by_uuid, make_save_callback, read_jsonl, write_jsonl
    from infra.store import make_preserving_save_callback
    from generation.social_world import generate_social_graph

    stage3_path = ctx.data_path(STAGE3_FILE)
    stage3_9_path = ctx.data_path(STAGE3_9_FILE)
    keep = _uuid_keep_set(ctx)
    stage3_records = _select_by_uuid(read_jsonl(stage3_path), keep)
    existing = {} if ctx.force else load_existing_by_uuid(stage3_9_path)
    kept = _kept_records(stage3_9_path, keep)
    save_callback = (make_preserving_save_callback(stage3_9_path, kept, "3.9", key="uuid")
                     if keep is not None else make_save_callback(stage3_9_path, "3.9"))
    records = generate_social_graph(
        stage3_records, ctx.prompts_dir, ctx.max_events,
        existing, save_callback=save_callback,
        max_workers=ctx.max_workers)
    write_jsonl(_finalize(records, kept) if keep is not None else records, stage3_9_path)
    print(f"[social_world] {len(records)} records -> {stage3_9_path}")


def _run_annual_events(ctx: RunContext) -> None:
    from common import load_existing_by_uuid, make_save_callback, read_jsonl, write_jsonl
    from generation.annual_events import generate_annual_events
    from infra.store import make_preserving_save_callback

    stage3_path = ctx.data_path(STAGE3_FILE)
    stage3_9_path = ctx.data_path(STAGE3_9_FILE)
    stage4_path = ctx.data_path(STAGE4_FILE)
    keep = _uuid_keep_set(ctx)

    # Prefer stage3.9 output (with Social_Graph); fall back to stage3 (legacy).
    if os.path.exists(stage3_9_path):
        stage3_records = read_jsonl(stage3_9_path)
    else:
        stage3_records = read_jsonl(stage3_path)
    stage3_records = _select_by_uuid(stage3_records, keep)

    existing = {} if ctx.force else load_existing_by_uuid(stage4_path)
    kept = _kept_records(stage4_path, keep)
    save_callback = (make_preserving_save_callback(stage4_path, kept, 4, key="uuid")
                     if keep is not None else make_save_callback(stage4_path, 4))
    records = generate_annual_events(
        stage3_records, ctx.prompts_dir, ctx.max_events,
        existing, save_callback=save_callback,
        max_workers=ctx.max_workers)
    write_jsonl(_finalize(records, kept) if keep is not None else records, stage4_path)

    # Always run the post-stage gender fix (kept inside this node, per design).
    if os.path.exists(stage4_path):
        fix_gender_in_stage4(stage4_path)
    print(f"[annual_events] {len(records)} records -> {stage4_path}")


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


# Data-file names under output_dir (mirror each generator's argparse defaults,
# which are OUTPUT_DIR/data/<name>; these map cleanly to RunContext.output_dir).
SUB_EVENTS_FILE = "stage4_5_sub_events.jsonl"
GROUP_CHATS_FILE = "stage7_group_chats.jsonl"
S10_SUMMARY_FILE = "stage10_image_summaries.jsonl"
S10_MERGED_FILE = "stage10_merged.jsonl"
APP_TRACE_FILE = "stage7_2_app_screenshots.jsonl"
EVENT_PHOTO_FILE = "stage7_1_event_images.jsonl"
DOCUMENT_FILE = "stage7_3_tickets.jsonl"


# --- Per-generator argv builders -------------------------------------------
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


_ALLOW_EMPTY_JSONL_NODES = {"sub_events", "app_trace", "document"}


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


def verify_node_outputs(ctx: RunContext, node: Node) -> None:
    """Enforce the DAG-level output contract for a completed node.

    Delegated generator mains may log and return after per-record failures. The
    DAG treats a node as successful only after its declared artifacts exist and
    non-optional JSONL outputs contain records.
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

    expected_input = _data(ctx, STAGE4_FILE)
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
    argv = ["--input", _data(ctx, STAGE4_FILE),
            "--output", _data(ctx, SUB_EVENTS_FILE),
            "--max-workers", str(ctx.max_workers)]
    if ctx.model:
        argv += ["--model", ctx.model]
    if ctx.uuid_filter and len(ctx.uuid_filter) == 1:  # this flag is single-int
        argv += ["--uuid-filter", str(ctx.uuid_filter[0])]
    argv += _force(ctx)
    return argv


def _argv_conversation(ctx: RunContext):
    return ["--input-file", _data(ctx, STAGE4_FILE),
            "--output-file", _data(ctx, GROUP_CHATS_FILE),
            "--sub-events-file", _data(ctx, SUB_EVENTS_FILE),
            "--prompts-dir", ctx.prompts_dir,
            "--image-dir", ctx.image_dir,
            "--max-workers", str(ctx.max_workers),
            *_uuid_multi(ctx),
            *_force(ctx)]


def _argv_app_trace(ctx: RunContext):
    return ["--events-file", _data(ctx, STAGE4_FILE),
            "--output-dir", ctx.image_dir,
            "--sub-events-file", _data(ctx, SUB_EVENTS_FILE),
            *_uuid_multi(ctx),
            *_force(ctx)]


def _argv_event_photo(ctx: RunContext):
    return ["--events-file", _data(ctx, STAGE4_FILE),
            "--sub-events-file", _data(ctx, SUB_EVENTS_FILE),
            "--image-base-dir", ctx.image_dir,
            "--max-workers", str(ctx.max_workers),
            *_uuid_multi(ctx),
            *_force(ctx)]


def _argv_document(ctx: RunContext):
    return ["--events-file", _data(ctx, STAGE4_FILE),
            "--output-dir", ctx.image_dir,
            "--image-dir", ctx.image_dir,
            "--sub-events-file", _data(ctx, SUB_EVENTS_FILE),
            *_uuid_multi(ctx),
            *_force(ctx)]


def _argv_scenery(ctx: RunContext):
    return ["--input-file", _data(ctx, STAGE4_FILE),
            "--output-dir", ctx.image_dir,
            *_uuid_multi(ctx),
            *_force(ctx)]


def _argv_memory_summary(ctx: RunContext):
    # memory_summary uses --workers (not --max-workers)
    return ["--image-base-dir", ctx.image_dir,
            "--output-file", _data(ctx, S10_SUMMARY_FILE),
            "--merged-output", _data(ctx, S10_MERGED_FILE),
            "--profiles-file", _data(ctx, STAGE1_FILE),
            "--events-file", _data(ctx, STAGE4_FILE),
            "--sub-events-file", _data(ctx, SUB_EVENTS_FILE),
            "--workers", str(ctx.max_workers),
            *_uuid_multi(ctx),
            *_force(ctx)]


# ---------------------------------------------------------------------------
# Node registry (see the Quickstart node table in README.md)
# ---------------------------------------------------------------------------
NODES: Dict[str, Node] = {
    "profile": Node(
        "profile", (), (STAGE1_FILE,), _run_profile,
        "record", "Basic profiles (CSV + LLM) [stage1]"),
    "persona_seeds": Node(
        "persona_seeds", ("profile",), (STAGE1_FILE,), _run_persona_seeds,
        "record", "Seed extra (foreign) personas via LLM [stage0]"),
    "life_state": Node(
        "life_state", ("persona_seeds",), (STAGE2_FILE,), _run_life_state,
        "record", "Init states (CSV + LLM) [stage2]"),
    "social_name_fix": Node(
        "social_name_fix", ("life_state",), (STAGE2_FILE,), _run_social_name_fix,
        "normalizer", "Fix social relationship names; rewrites stage2 [stage2.1]"),
    "timeline_dates": Node(
        "timeline_dates", ("social_name_fix",), (STAGE3_FILE,), _run_timeline_dates,
        "record", "Important dates (LLM) [stage3]"),
    "social_world": Node(
        "social_world", ("timeline_dates",), (STAGE3_9_FILE,), _run_social_world,
        "record", "Social graph (LLM) [stage3.9]"),
    "annual_events": Node(
        "annual_events", ("social_world",), (STAGE4_FILE,), _run_annual_events,
        "record", "Annual events (LLM) + gender fix [stage4]"),
    "sub_events": Node(
        "sub_events", ("annual_events",), ("stage4_5_sub_events.jsonl",),
        _delegate("generation.sub_events", _argv_sub_events),
        "record", "Sub-events (LLM) [stage4.5]"),
    "conversation": Node(
        "conversation", ("annual_events", "social_world", "sub_events"),
        ("stage7_group_chats.jsonl",),
        _delegate("generation.conversation", _argv_conversation),
        "media", "Group chats + images [stage7]"),
    "app_trace": Node(
        "app_trace", ("annual_events", "sub_events"),
        (APP_TRACE_FILE,),
        _delegate("generation.app_trace", _argv_app_trace),
        "media", "App screenshots + images [stage7.2]"),
    "event_photo": Node(
        "event_photo", ("conversation", "annual_events", "sub_events"),
        (EVENT_PHOTO_FILE,),
        _delegate("generation.event_photo", _argv_event_photo),
        "media", "Event images + images [stage7.1]"),
    "document": Node(
        "document", ("event_photo", "annual_events"),
        (DOCUMENT_FILE,),
        _delegate("generation.document", _argv_document),
        "media", "Tickets / transfers / moments + images [stage7.3]"),
    "scenery": Node(
        "scenery", ("annual_events",), (),
        _delegate("generation.scenery", _argv_scenery),
        "media", "Scenery images [stage8]", verify=_verify_scenery),
    "memory_summary": Node(
        "memory_summary",
        ("conversation", "app_trace", "document", "event_photo", "scenery", "sub_events"),
        ("stage10_total_images.jsonl",),
        _delegate("generation.memory_summary", _argv_memory_summary),
        "index", "Image summaries + merge [stage10]"),
}


# ---------------------------------------------------------------------------
# Graph algorithms
# ---------------------------------------------------------------------------
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
