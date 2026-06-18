"""App-trace generator (Memories / AppTrace): orchestration + Playwright render.

Holds the APP_TYPES constants, the shared 'fix_app_screenshots' logger, the
Playwright render (sync + async), the per-persona orchestration (process_persona
/ main) and the thin AppTraceGenerator. Template filling, checkpoint, event
selection, covers and *_info LLM generation live in sibling modules.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

import config
from common import (
    LOG_DIR,
    read_jsonl,
    write_jsonl,
    load_sub_events_index,
    expand_events_for_imaging,
)
from core import DIR_NAME
from backends.llm import set_log_context
from infra.base_generator import Generator

from .checkpoint import clear_checkpoint, load_checkpoint, save_checkpoint
from .content import _call_llm_generate_info_single
from .covers import generate_video_cover_b64
from .events import assign_all_events_to_types, select_events_for_type
from .templates import _load_template, fill_template


# stdout/stderr UTF-8 + Windows asyncio policy, preserved from the standalone script.
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# --- Logging (the 'fix_app_screenshots' logger; the split modules log here too) ---
logger = logging.getLogger('fix_app_screenshots')
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler(os.path.join(LOG_DIR, 'fix_app_screenshots.log'), encoding='utf-8')
fh.setLevel(logging.DEBUG)
fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
sh = logging.StreamHandler()
sh.setLevel(logging.INFO)
sh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
logger.addHandler(fh)
logger.addHandler(sh)


APP_TYPES = ["book", "music", "video", "shopping"]
APP_TYPE_CN = {
    "book": "微信读书",
    "music": "网易云音乐",
    "video": "B站",
    "shopping": "淘宝订单",
    "ticket": "火车票",
    "money": "微信转账",
}
APP_TYPE_EN = {
    "book": "Kindle",
    "music": "Spotify",
    "video": "YouTube",
    "shopping": "Amazon",
    "ticket": "Train Ticket",
    "money": "Payment Transfer",
}


async def render_screenshots(render_tasks, output_dir, resume=True):
    """
    render_tasks: [{"uuid": int, "event_id": int, "app_type": str,
                    "info": dict, "persona_name": str, "location": str,
                    "nationality": str}]
    """
    from playwright.async_api import async_playwright

    os.makedirs(output_dir, exist_ok=True)
    stats = {"done": 0, "skipped": 0, "failed": 0, "files": []}

    # Load templates by app_type and language.
    templates = {}
    for lang in ("cn", "en"):
        for app_type in APP_TYPES:
            try:
                templates[(app_type, lang)] = _load_template(app_type, "Chinese" if lang == "cn" else "English")
            except FileNotFoundError as e:
                logger.error(f"Template load failed: {e}")

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 450, "height": 900})

        for task in render_tasks:
            uid = task["uuid"]
            eid = task["event_id"]
            app_type = task["app_type"]
            info = task["info"]

            # Output under uid{N}/app_type subdirectories.
            type_dir = os.path.join(output_dir, f'uid{uid}', DIR_NAME[app_type])
            os.makedirs(type_dir, exist_ok=True)

            png_name = f"{uid}_{app_type}_{eid}.png"
            png_path = os.path.join(type_dir, png_name)
            html_path = os.path.join(type_dir, f"{uid}_{app_type}_{eid}.html")

            if resume and os.path.exists(png_path):
                stats["skipped"] += 1
                stats["files"].append(png_name)
                logger.debug(f"SKIP: {png_name}")
                continue

            nationality = task.get("nationality", "Chinese")
            lang_key = "cn" if nationality == "Chinese" else "en"
            template = templates.get((app_type, lang_key))
            if not template:
                stats["failed"] += 1
                continue

            try:
                kwargs = {
                    "persona_name": task.get("persona_name", "用户"),
                    "location": task.get("location", ""),
                    "nationality": nationality,
                    "uuid": task.get("uuid", 0),
                }
                # Video cover.
                if app_type == "video":
                    cover_b64 = generate_video_cover_b64(
                        info, task.get("nationality", "Chinese"))
                    kwargs["cover_b64"] = cover_b64

                filled = fill_template(app_type, template, info, **kwargs)
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(filled)

                url = Path(html_path).resolve().as_uri()
                await page.goto(url, wait_until="networkidle", timeout=15000)
                await page.wait_for_timeout(300)
                await page.screenshot(path=png_path, full_page=True)

                stats["done"] += 1
                stats["files"].append(png_name)
                logger.info(f"OK: {type_dir}/{png_name}")
            except Exception as e:
                stats["failed"] += 1
                logger.error(f"FAIL: {png_name}: {e}")

        await browser.close()

    return stats

def render_single_sync(page, task, output_dir, templates, resume=True, keep_html=False):
    """Synchronously render one screenshot for per-item mode; return done/skipped/failed."""
    uid = task["uuid"]
    eid = task["event_id"]
    app_type = task["app_type"]
    info = task["info"]

    type_dir = os.path.join(output_dir, f'uid{uid}', DIR_NAME[app_type])
    os.makedirs(type_dir, exist_ok=True)

    png_name = f"{uid}_{app_type}_{eid}.png"
    png_path = os.path.join(type_dir, png_name)
    html_path = os.path.join(type_dir, f"{uid}_{app_type}_{eid}.html")

    if resume and os.path.exists(png_path):
        logger.debug(f"SKIP: {png_name}")
        return "skipped"

    nationality = task.get("nationality", "Chinese")
    lang_key = "cn" if nationality == "Chinese" else "en"
    template = templates.get((app_type, lang_key))
    if not template:
        logger.error(f"FAIL: {png_name}: template not loaded")
        return "failed"

    try:
        kwargs = {
            "persona_name": task.get("persona_name", "用户"),
            "location": task.get("location", ""),
            "nationality": nationality,
            "uuid": task.get("uuid", 0),
        }
        if app_type == "video":
            cover_b64 = generate_video_cover_b64(info, task.get("nationality", "Chinese"))
            kwargs["cover_b64"] = cover_b64

        filled = fill_template(app_type, template, info, **kwargs)
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(filled)

        url = Path(html_path).resolve().as_uri()
        page.goto(url, wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(300)
        page.screenshot(path=png_path, full_page=True)

        # Delete HTML if PNG succeeded and keep_html is False
        if not keep_html and os.path.exists(html_path):
            os.remove(html_path)

        logger.info(f"OK: {png_name}")
        return "done"
    except Exception as e:
        logger.error(f"FAIL: {png_name}: {e}")
        return "failed"

# ═══════════════════════════════════════════════════════════════════
# Main flow.
# ═══════════════════════════════════════════════════════════════════

def process_persona(persona_record, events_per_type, skip_llm, generate_covers,
                    all_events=False, checkpoint_done=None,
                    on_item_done=None, output_dir=None):
    """Process one persona: select events, generate info, then save and render each item.

    checkpoint_done: Set of completed keys such as '3_book_42'. Newly completed
                     keys are also added to this set; the caller persists it.
    on_item_done:    callback(event_dict, app_type, render_task)
                     Called immediately after each *_info item is generated to
                     write JSONL and render the screenshot.
    """
    if checkpoint_done is None:
        checkpoint_done = set()
    uuid = persona_record.get('uuid', 0)
    bp = persona_record.get('Basic_Profile', {})
    init_state = persona_record.get('Init_State', {})
    nationality = bp.get('nationality', 'Chinese')
    persona_name = bp.get('name', '用户')
    location = init_state.get('location', '')
    events = persona_record.get('Events', [])

    logger.info(f"[uuid={uuid}] {persona_name} ({nationality}), {len(events)} events")

    assigned_ids = set()

    # --all-events mode: preassign all events to types by keyword.
    all_events_assignment = assign_all_events_to_types(events, APP_TYPES) if all_events else None

    for app_type in APP_TYPES:
        # Select events.
        if all_events_assignment is not None:
            selected = all_events_assignment.get(app_type, [])
        else:
            selected = select_events_for_type(events, app_type, n=events_per_type)
        if not selected:
            logger.warning(f"[uuid={uuid}] No events available for {app_type}")
            continue

        info_key = f"{app_type}_info"

        for ev in selected:
            eid = ev.get('event_id')
            ckpt_key = f'{uuid}_{app_type}_{eid}'
            png_exists = False

            # Prefer checking whether the PNG exists; it is more reliable than the checkpoint.
            # Do not skip the callback path: resume still needs to recover the
            # standalone manifest record for downstream stage10.
            if output_dir:
                png_path = os.path.join(output_dir, f'uid{uuid}', DIR_NAME[app_type],
                                        f'{uuid}_{app_type}_{eid}.png')
                if os.path.exists(png_path):
                    png_exists = True
                    logger.debug(f'[uuid={uuid}] event_{eid} {app_type}: SKIP (PNG exists)')
            elif ckpt_key in checkpoint_done and not ev.get(info_key):
                logger.debug(f'[uuid={uuid}] event_{eid} {app_type}: SKIP (checkpoint)')
                continue

            # -- Step 1: LLM generation if *_info is missing.
            if info_key not in ev and not skip_llm:
                logger.info(f"[uuid={uuid}] Generating {app_type}_info for event_{eid} via LLM...")
                try:
                    results = _call_llm_generate_info_single(
                        persona_record, [ev], app_type, nationality)
                    if results:
                        ev[info_key] = results[0].get(info_key, {})
                        if app_type not in ev.get("additional_info", []):
                            ev.setdefault("additional_info", []).append(app_type)
                        logger.info(f"  [uuid={uuid}] event_{eid}: {app_type}_info generated ✓")
                    else:
                        logger.warning(f"  [uuid={uuid}] event_{eid}: LLM returned empty for {app_type}")
                except Exception as e:
                    logger.error(f"[uuid={uuid}] LLM failed for event_{eid} {app_type}: {e}")
            elif info_key not in ev and skip_llm:
                logger.debug(f"[uuid={uuid}] event_{eid} {app_type}: skip-llm, no info")

            # -- Step 2: callback to save JSONL and render the screenshot.
            info = ev.get(info_key)
            render_status = None
            if info and on_item_done:
                assigned_ids.add(eid)
                render_task = {
                    "uuid": uuid,
                    "event_id": eid,
                    "app_type": app_type,
                    "info": info,
                    "persona_name": persona_name,
                    "location": location,
                    "nationality": nationality,
                }
                render_status = on_item_done(ev, app_type, render_task)
            elif png_exists:
                logger.warning(
                    f"[uuid={uuid}] event_{eid} {app_type}: PNG exists but {info_key} is missing; "
                    "manifest record cannot be recovered"
                )

            # -- Step 3: mark checkpoint only after info exists and the PNG is rendered.
            if ev.get(info_key) and render_status in {"done", "skipped", "dry_run"}:
                checkpoint_done.add(ckpt_key)

def main():
    parser = argparse.ArgumentParser(
        description='App-trace screenshots: render the 4 app types from stage4 events')
    parser.add_argument('--events-file', type=str,
                        default=os.path.join(config.OUTPUT_DIR, 'data',
                                             'stage4_annual_events.jsonl'),
                        help='Path to the stage4 events JSONL file')
    parser.add_argument('--output-dir', type=str,
                        default=os.path.join(config.OUTPUT_DIR, 'image'),
                        help='Screenshot output directory')
    parser.add_argument('--uuid-filter', type=int, nargs='+', default=None,
                        help='Only process these uuid(s), e.g. --uuid-filter 0 10')
    parser.add_argument('--events-per-type', type=int, default=30,
                        help='Events per app type per persona')
    parser.add_argument('--skip-llm', action='store_true',
                        help='Skip LLM generation; only render events that already have *_info')
    parser.add_argument('--no-covers', action='store_true',
                        help='Skip video cover generation (faster rendering)')
    parser.add_argument('--resume', action='store_true', default=True,
                        help='Skip already-existing PNGs (default: True)')
    parser.add_argument('--no-resume', dest='resume', action='store_false',
                        help='Force re-render all screenshots')
    parser.add_argument('--dry-run', action='store_true',
                        help='Count only, do not generate')
    parser.add_argument('--save-events', action='store_true', default=True,
                        help='Write generated *_info back to the stage4 JSONL (default: on)')
    parser.add_argument('--no-save-events', dest='save_events', action='store_false',
                        help='Do not write back to the stage4 JSONL')
    parser.add_argument('--reset-checkpoint', action='store_true',
                        help='Clear the checkpoint and start from scratch')
    parser.add_argument('--all-events', action='store_true',
                        help='Process all events (keyword-assigned to the 4 types), clearing old *_info')
    parser.add_argument('--keep-html', action='store_true',
                        help='Keep HTML files after PNG generation (default: delete HTML)')
    parser.add_argument('--types', type=str, default=None,
                        help='Only these comma-separated types, e.g. shopping or book,music')
    parser.add_argument('--force-regen', '--force', dest='force_regen', action='store_true',
                        help='Ignore caches and force-regenerate the *_info, checkpoint and screenshots for the given types')
    parser.add_argument('--sub-events-file', type=str,
                        default=os.path.join(config.OUTPUT_DIR, 'data', 'stage4_5_sub_events.jsonl'),
                        help='stage4.5 sub-events JSONL for expanding mid/long-term events')
    args = parser.parse_args()

    if args.types:
        import sys
        allowed = [t.strip() for t in args.types.split(',')]
        invalid = [t for t in allowed if t not in APP_TYPES]
        if invalid:
            print(f"[ERROR] Invalid type: {invalid}, choices: {APP_TYPES}")
            sys.exit(1)
        APP_TYPES[:] = allowed

    logger.info("=" * 70)
    logger.info("fix_app_screenshots: Start")
    logger.info(f"Events file  : {args.events_file}")
    logger.info(f"Output dir   : {args.output_dir}")
    logger.info(f"All events   : {args.all_events}")
    logger.info(f"Events/type  : {args.events_per_type}")
    logger.info(f"UUID filter  : {args.uuid_filter}")
    logger.info(f"Skip LLM     : {args.skip_llm}")
    logger.info(f"No covers    : {args.no_covers}")
    logger.info(f"Resume       : {args.resume}")
    logger.info(f"Save events  : {args.save_events}")
    logger.info(f"Reset ckpt   : {args.reset_checkpoint}")
    logger.info("=" * 70)

    # -- Resume support.
    if args.reset_checkpoint:
        clear_checkpoint(args.output_dir)
    checkpoint_done = load_checkpoint(args.output_dir)
    if checkpoint_done:
        logger.info(f"[Checkpoint] {len(checkpoint_done)} items done, resumable")

    # Read event data.
    stage4_records = read_jsonl(args.events_file)
    if not stage4_records:
        logger.error(f"No records found in {args.events_file}")
        return

    # Load the sub-events index and expand mid/long-term events.
    sub_index = load_sub_events_index(args.sub_events_file)
    logger.info(f"Sub-events index: {len(sub_index)} parent events loaded")
    for persona in stage4_records:
        uid = persona.get('uuid', 0)
        if args.uuid_filter is not None and uid not in args.uuid_filter:
            continue
        original_events = persona.get('Events', [])
        expanded = []
        for image_id, ev in expand_events_for_imaging(uid, original_events, sub_index):
            # Add event_id to sub-events for downstream compatibility.
            if 'event_id' not in ev:
                ev['event_id'] = image_id
            expanded.append(ev)
        persona['Events'] = expanded
        logger.info(f"[uuid={uid}] Events expanded: {len(original_events)} -> {len(expanded)}")

    # --all-events: clear all old *_info fields and regenerate from scratch.
    if args.all_events:
        logger.info("[all-events] Clearing old *_info fields and removing existing screenshot dirs...")
        for persona in stage4_records:
            if args.uuid_filter is not None and persona.get('uuid') not in args.uuid_filter:
                continue
            for ev in persona.get('Events', []):
                for t in APP_TYPES:
                    ev.pop(f"{t}_info", None)
        # Delete old screenshots.
        import shutil
        out_root = Path(args.output_dir)
        if out_root.exists():
            for uid_dir in out_root.iterdir():
                if uid_dir.is_dir():
                    uid_val = uid_dir.name
                    if args.uuid_filter is None or any(str(u) == uid_val for u in args.uuid_filter):
                        shutil.rmtree(uid_dir)
                        logger.info(f"  Removed {uid_dir}")
        # --all-events implicitly enables save-events.
        args.save_events = True
        args.resume = False  # Force rerendering.

    # -- --force-regen: clear caches for the selected type.
    if args.force_regen:
        logger.info(f"[force-regen] Clearing *_info, checkpoint and PNG for types {APP_TYPES} ...")
        # 1. Clear *_info fields in JSONL.
        for persona in stage4_records:
            if args.uuid_filter is not None and persona.get('uuid') not in args.uuid_filter:
                continue
            for ev in persona.get('Events', []):
                for t in APP_TYPES:
                    ev.pop(f"{t}_info", None)
        write_jsonl(stage4_records, args.events_file)
        logger.info("  *_info fields cleared and written back to JSONL")
        # 2. Clear checkpoint entries for this type.
        before = len(checkpoint_done)
        checkpoint_done = {
            k for k in checkpoint_done
            if not any(f"_{t}_" in k or k.endswith(f"_{t}") for t in APP_TYPES)
        }
        save_checkpoint(args.output_dir, checkpoint_done)
        logger.info(f"  Checkpoint cleared {before - len(checkpoint_done)} entries")
        # 3. Delete old PNG files.
        import shutil
        out_root = Path(args.output_dir)
        for t in APP_TYPES:
            if args.uuid_filter is not None:
                uid_dirs = [out_root / f"uid{u}" for u in args.uuid_filter]
            else:
                uid_dirs = [d for d in out_root.iterdir() if d.is_dir()] if out_root.exists() else []
            for uid_dir in uid_dirs:
                type_dir = uid_dir / DIR_NAME[t]
                if type_dir.exists():
                    shutil.rmtree(type_dir)
                    logger.info(f"  Removed {type_dir}")
        args.resume = False  # Force rerendering.

    # Skip LLM calls during dry-run.
    effective_skip_llm = args.skip_llm or args.dry_run

    total_stats = {"done": 0, "skipped": 0, "failed": 0}
    jsonl_records = []  # Collect standalone JSONL records.

    # -- Load templates and open one Playwright browser for reuse.
    templates = {}
    for lang, nat in [("cn", "Chinese"), ("en", "English")]:
        for t in APP_TYPES:
            try:
                templates[(t, lang)] = _load_template(t, nat)
            except FileNotFoundError as e:
                logger.error(f"Template load failed: {e}")

    pw_ctx = None
    browser = None
    page = None
    if not args.dry_run:
        from playwright.sync_api import sync_playwright
        pw_ctx = sync_playwright().start()
        browser = pw_ctx.chromium.launch()
        page = browser.new_page(viewport={"width": 450, "height": 900})

    try:
        for persona in stage4_records:
            uid = persona.get('uuid', 0)
            if args.uuid_filter is not None and uid not in args.uuid_filter:
                continue
            set_log_context(uuid=uid, stage="fix_app_screenshots")

            def on_item_done(event, app_type, render_task):
                """Save JSONL and render a screenshot immediately for each LLM item."""
                participants_raw = event.get('participants', [])
                participant_names = [
                    p.get('name', '') if isinstance(p, dict) else str(p)
                    for p in participants_raw
                ]
                participant_names = [n.strip() for n in participant_names if n.strip()]
                eid = event.get('event_id', render_task.get('event_id', ''))
                eid_str = str(eid)
                parent_eid = int(eid_str.split('_')[0]) if '_' in eid_str else eid
                image_path = os.path.join(args.output_dir, f'uid{uid}', DIR_NAME[app_type],
                                          f'{uid}_{app_type}_{eid}.png')

                status = "dry_run"
                if not args.dry_run:
                    status = render_single_sync(
                        page, render_task, args.output_dir, templates,
                        resume=args.resume, keep_html=args.keep_html)
                    total_stats[status] = total_stats.get(status, 0) + 1

                success = status in {"done", "skipped"} and os.path.exists(image_path)
                jsonl_records.append({
                    'uuid': uid,
                    'sub_event_id': eid_str,
                    'event_id': parent_eid,
                    'event_name': event.get('event_name', event.get('event', event.get('title', ''))),
                    'participants': participant_names,
                    'app_type': app_type,
                    'image_path': image_path,
                    'info': event.get(f'{app_type}_info', {}),
                    'success': success,
                    'status': status,
                })
                if args.save_events:
                    write_jsonl(stage4_records, args.events_file)
                    logger.info(f"  [uuid={uid}] event_{event['event_id']}: {app_type}_info saved")
                return status

            process_persona(
                persona, args.events_per_type, effective_skip_llm,
                not args.no_covers,
                all_events=args.all_events,
                checkpoint_done=checkpoint_done,
                on_item_done=on_item_done,
                output_dir=args.output_dir)

            # Persist checkpoint after each persona.
            save_checkpoint(args.output_dir, checkpoint_done)

    finally:
        if browser:
            browser.close()
        if pw_ctx:
            pw_ctx.stop()

    logger.info(f"\nFinal render results: done={total_stats.get('done',0)}, "
                f"skipped={total_stats.get('skipped',0)}, "
                f"failed={total_stats.get('failed',0)}")

    # -- Save standalone JSONL, even when empty, so downstream can distinguish
    # "ran and selected no app screenshots" from "node never produced a manifest".
    jsonl_output_path = os.path.join(os.path.dirname(args.events_file),
                                     'stage7_2_app_screenshots.jsonl')
    write_jsonl(jsonl_records, jsonl_output_path)
    logger.info(f"Saved {len(jsonl_records)} records to {jsonl_output_path}")

    logger.info("\n" + "=" * 70)
    logger.info("fix_app_screenshots: Complete")
    logger.info("=" * 70)


# ===================================================================== #
# Domain generator -- thin uniform entry point for the future pipeline DAG.
# ===================================================================== #

class AppTraceGenerator(Generator):
    """Generate per-persona app-trace payloads (book / music / video / shopping).

    App screenshots are rendered to PNG via Playwright and emitted as image files
    plus a standalone JSONL, so the standalone run keeps its own browser
    orchestration in :func:`main`. This class is a thin uniform entry point over
    the *data half* (event selection + ``*_info`` generation) for the future
    pipeline DAG: :meth:`produce` returns ``{app_type: [{event_id, <type>_info},
    ...]}`` for one persona and performs no rendering. Behavior of the underlying
    functions is unchanged.
    """

    stage_label = "Stage7.2"
    stage_num = "7.2"
    index_key = "uuid"
    produces = "app_trace"

    def __init__(self, types=None, events_per_type=30):
        self.types = list(types) if types else list(APP_TYPES)
        self.events_per_type = events_per_type

    def produce(self, record, ctx=None):
        events = record.get('Events', [])
        bp = record.get('Basic_Profile', {})
        nationality = bp.get('nationality', 'Chinese')
        out = {}
        for app_type in self.types:
            selected = select_events_for_type(events, app_type, n=self.events_per_type)
            results = []
            for ev in selected:
                if f"{app_type}_info" in ev:
                    continue
                r = _call_llm_generate_info_single(record, [ev], app_type, nationality)
                if r:
                    results.extend(r)
            out[app_type] = results
        return out


if __name__ == "__main__":
    main()
