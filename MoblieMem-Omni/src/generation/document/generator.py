"""Document generator (Memories / Document): orchestration + Playwright render.

Holds the APP_TYPES constant, the shared 'fix_app2' logger, the HTML->PNG
screenshot, the per-persona orchestration (``main``) and the thin
``DocumentGenerator`` (data half) for the pipeline DAG. Template filling and the
*_info LLM layer live in sibling modules.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import random
import sys
from pathlib import Path

import config
from common import (
    LOG_DIR,
    load_sub_events_index,
    expand_events_for_imaging,
    read_jsonl,
    write_jsonl,
)
from core import DIR_NAME
from backends.llm import set_log_context
from infra.base_generator import Generator

from .content import call_llm_generate_info, llm_select_events
from .templates import (
    TEMPLATES_CN,
    TEMPLATES_EN,
    _load_person_avatar_uri,
    fill_money_template,
    fill_ticket_template,
    fill_wechat_friend_template,
    fill_x_feed_template,
    find_event_images,
)

# stdout/stderr + Windows asyncio policy, preserved from the standalone script
# (config also reconfigures the console; this is idempotent).
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

logger = logging.getLogger('fix_app2')
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler(os.path.join(LOG_DIR, 'fix_app2.log'), encoding='utf-8')
fh.setLevel(logging.DEBUG)
fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
sh = logging.StreamHandler()
sh.setLevel(logging.INFO)
sh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
logger.addHandler(fh)
logger.addHandler(sh)

APP_TYPES = ["ticket", "money", "friend"]


def render_screenshot(page, html_content, png_path, html_path=None, keep_html=False):
    """Render HTML to a PNG screenshot, cropped to content height (to avoid bottom whitespace)."""
    if html_path is None:
        html_path = png_path.replace('.png', '.html')

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    url = Path(html_path).resolve().as_uri()
    page.goto(url, wait_until="networkidle", timeout=15000)
    page.wait_for_timeout(300)

    # Crop to the actual content height to avoid large bottom whitespace for short posts
    bbox = page.locator('body').bounding_box()
    if bbox and bbox['height'] > 0:
        clip_height = min(int(bbox['height']) + 2, 4000)
        page.screenshot(path=png_path, clip={"x": 0, "y": 0, "width": 450, "height": clip_height})
    else:
        page.screenshot(path=png_path, full_page=True)

    if not keep_html and os.path.exists(html_path):
        os.remove(html_path)

    return True

# Main process

def main():
    parser = argparse.ArgumentParser(description='Generate ticket/money/friend screenshots (V2)')
    parser.add_argument('--types', nargs='+', default=['ticket', 'money', 'friend'],
                        choices=['ticket', 'money', 'friend'])
    parser.add_argument('--uuid-filter', type=int, nargs='+', default=None)
    parser.add_argument('--events-file', type=str,
                        default=os.path.join(config.OUTPUT_DIR, 'data', 'annual_events.jsonl'))
    parser.add_argument('--output-dir', type=str,
                        default=os.path.join(config.OUTPUT_DIR, 'image'))
    parser.add_argument('--events-per-type', type=int, default=20)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--keep-html', action='store_true')
    parser.add_argument('--save-prompts', type=str, default=None,
                        help='Save LLM prompts/responses to this directory')
    parser.add_argument('--image-dir', type=str,
                        default=os.path.join(config.OUTPUT_DIR, 'image'),
                        help='Base directory for event images (uid0/book, uid0/video, etc.)')
    parser.add_argument('--sub-events-file', type=str,
                        default=os.path.join(config.OUTPUT_DIR, 'data', 'sub_events.jsonl'),
                        help='stage4.5 sub-events JSONL for expanding mid/long-term events')
    parser.add_argument('--force', action='store_true',
                        help='Ignore existing screenshots and regenerate from scratch')
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("fix_app2: ticket / money / friend screenshot generator")
    logger.info(f"Types: {args.types}")
    logger.info(f"UUID filter: {args.uuid_filter or 'ALL'}")
    logger.info(f"Events per type: {args.events_per_type}")
    logger.info(f"Output: {args.output_dir}")
    logger.info(f"Sub-events file: {args.sub_events_file}")
    logger.info("=" * 60)

    # Read data
    stage4_records = read_jsonl(args.events_file)

    # Load the sub-events index and expand mid/long-term events
    sub_index = load_sub_events_index(args.sub_events_file)
    logger.info(f"Sub-events index: {len(sub_index)} parent events loaded")
    for persona in stage4_records:
        _uid = persona.get('uuid', 0)
        if args.uuid_filter is not None and _uid not in args.uuid_filter:
            continue
        original_events = persona.get('Events', [])
        expanded = []
        for image_id, ev in expand_events_for_imaging(_uid, original_events, sub_index):
            if 'event_id' not in ev:
                ev['event_id'] = image_id
            expanded.append(ev)
        persona['Events'] = expanded
        logger.info(f"[uuid={_uid}] Events expanded: {len(original_events)} -> {len(expanded)}")
    # Read base info
    data_dir = os.path.dirname(args.events_file)
    profiles_file = os.path.join(data_dir, 'basic_profiles.jsonl')
    profiles = {r['uuid']: r for r in read_jsonl(profiles_file)} if os.path.exists(profiles_file) else {}
    init_states_file = os.path.join(data_dir, 'init_states.jsonl')
    init_states = {r['uuid']: r for r in read_jsonl(init_states_file)} if os.path.exists(init_states_file) else {}

    # Load templates
    templates = {}
    for lang, tmap in [("cn", TEMPLATES_CN), ("en", TEMPLATES_EN)]:
        for t, path in tmap.items():
            if t not in args.types:
                continue
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    templates[(t, lang)] = f.read()
            else:
                logger.warning(f"Template not found: {path}")

    if args.save_prompts:
        os.makedirs(args.save_prompts, exist_ok=True)

    # Playwright
    page = None
    pw_ctx = None
    browser = None
    if not args.dry_run:
        from playwright.sync_api import sync_playwright
        pw_ctx = sync_playwright().start()
        browser = pw_ctx.chromium.launch()
        page = browser.new_page(viewport={"width": 450, "height": 900})

    stats = {"done": 0, "skipped": 0, "failed": 0}
    jsonl_records = []

    def append_manifest_record(uid, ev, app_type, png_path, info, status):
        participants = []
        for p in ev.get('participants', []):
            if isinstance(p, dict):
                participants.append(p.get('name', str(p)))
            else:
                participants.append(str(p))
        eid = ev.get('event_id', '')
        eid_str = str(eid)
        parent_eid = int(eid_str.split('_')[0]) if '_' in eid_str else eid
        jsonl_records.append({
            'uuid': uid,
            'sub_event_id': eid_str,
            'event_id': parent_eid,
            'event_name': ev.get('event_name', ev.get('event_title', ev.get('title', ''))),
            'participants': participants,
            'type': app_type,
            'image_path': png_path,
            f'{app_type}_info': info,
            'success': status in {'done', 'skipped'} and os.path.exists(png_path),
            'status': status,
        })

    try:
        for persona in stage4_records:
            uid = persona.get('uuid', 0)
            if args.uuid_filter is not None and uid not in args.uuid_filter:
                continue

            set_log_context(uuid=uid, stage="fix_app2")
            events = persona.get('Events', [])

            # Get persona info
            profile = profiles.get(uid, {})
            init_state = init_states.get(uid, {})
            bp = profile.get('Basic_Profile', {})
            ist = init_state.get('Init_State', {}) if init_state else {}
            persona_name = bp.get('name', '') or profile.get('name', '') or ist.get('name', '') or f'User{uid}'
            career = ist.get('career', bp.get('career', ''))
            location = ist.get('location', bp.get('location', ''))
            personality = bp.get('personality_traits', '')
            nationality = bp.get('nationality', '') or profile.get('nationality', '') or 'Chinese'
            is_cn = (nationality == "Chinese")
            lang_key = "cn" if is_cn else "en"

            logger.info(f"[uid={uid}] {persona_name} ({nationality})")
            assigned = set()
            ticket_id_last4 = None  # train tickets for the same persona share the same ID last-4 digits
            # Load the protagonist avatar (used by the social feed)
            person_avatar_uri = _load_person_avatar_uri(uid, args.image_dir)

            for app_type in args.types:
                # Unified flow: LLM selects events -> LLM generates data -> fill template -> screenshot
                selected = llm_select_events(events, app_type,
                                              persona_name=persona_name,
                                              location=location,
                                              nationality=nationality,
                                              n=args.events_per_type)
                if not selected:
                    logger.info(f"  [uid={uid}] {app_type}: no selectable events")
                    continue

                # Check whether *_info already exists; call the LLM to generate the missing ones
                need_llm = [e for e in selected if f"{app_type}_info" not in e]
                if need_llm:
                    logger.info(f"  [uid={uid}] {app_type}: LLM generating {len(need_llm)} records...")
                    results = call_llm_generate_info(
                        persona_name, career, location, personality,
                        need_llm, app_type, nationality
                    )
                    for item in results:
                        eid = item.get("event_id")
                        info = item.get(f"{app_type}_info")
                        if info is None:
                            continue
                        for e in events:
                            if e['event_id'] == eid:
                                e[f"{app_type}_info"] = info
                                break

                    if args.save_prompts:
                        prompt_path = os.path.join(args.save_prompts, f"{uid}_{app_type}_llm.json")
                        with open(prompt_path, 'w', encoding='utf-8') as f:
                            json.dump(results, f, ensure_ascii=False, indent=2)

                template = templates.get((app_type, lang_key))
                if not template:
                    logger.error(f"  [uid={uid}] {app_type}: template not loaded")
                    continue

                for ev in selected:
                    eid = ev['event_id']
                    info = ev.get(f"{app_type}_info")
                    if not info:
                        logger.warning(f"  [uid={uid}] {app_type} event_{eid}: no info data")
                        continue

                    assigned.add(eid)
                    type_dir = os.path.join(args.output_dir, f'uid{uid}', DIR_NAME[app_type])
                    os.makedirs(type_dir, exist_ok=True)
                    png_name = f"{uid}_{app_type}_{eid}.png"
                    png_path = os.path.join(type_dir, png_name)

                    if os.path.exists(png_path) and not args.force:
                        stats['skipped'] += 1
                        append_manifest_record(uid, ev, app_type, png_path, info, 'skipped')
                        logger.debug(f"  SKIP: {png_name}")
                        continue

                    if args.dry_run:
                        logger.info(f"  [DRY] {png_name}")
                        continue

                    try:
                        if app_type == "ticket":
                            if ticket_id_last4 is None:
                                ticket_id_last4 = f"****{random.randint(1000, 9999)}"
                            filled = fill_ticket_template(template, info,
                                                          passenger_name=persona_name, is_cn=is_cn,
                                                          id_last4=ticket_id_last4)
                        elif app_type == "money":
                            filled = fill_money_template(template, info, is_cn=is_cn)
                        elif app_type == "friend":
                            # Find images associated with this event
                            image_uris = find_event_images(uid, eid, args.image_dir)
                            if is_cn:
                                filled = fill_wechat_friend_template(template, info, persona_name, image_uris,
                                                                      avatar_data_uri=person_avatar_uri)
                            else:
                                filled = fill_x_feed_template(template, info, poster_name=persona_name,
                                                               image_data_uris=image_uris, avatar_data_uri=person_avatar_uri)
                        else:
                            filled = template  # fallback

                        render_screenshot(page, filled, png_path, keep_html=args.keep_html)
                        stats['done'] += 1
                        logger.info(f"  OK: {png_name}")

                        append_manifest_record(uid, ev, app_type, png_path, info, 'done')
                    except Exception as e:
                        stats['failed'] += 1
                        append_manifest_record(uid, ev, app_type, png_path, info, 'failed')
                        logger.error(f"  FAIL: {png_name}: {e}")

    finally:
        if browser:
            browser.close()
        if pw_ctx:
            pw_ctx.stop()

    # Save the updated JSONL
    if not args.dry_run:
        write_jsonl(stage4_records, args.events_file)
        logger.info(f"Updated {args.events_file}")

    # Save the standalone JSONL, even when empty.
    jsonl_path = os.path.join(os.path.dirname(args.events_file), 'tickets.jsonl')
    write_jsonl(jsonl_records, jsonl_path)
    logger.info(f"Saved standalone JSONL: {jsonl_path} ({len(jsonl_records)} records)")

    logger.info("=" * 60)
    logger.info(f"DONE: {stats['done']} done, {stats['skipped']} skipped, {stats['failed']} failed")
    logger.info("=" * 60)


# Domain generator -- thin uniform entry point for the future pipeline DAG.

class DocumentGenerator(Generator):
    """Generate per-persona document payloads (ticket / money / social feed).

    Documents are rendered to PNG via Playwright and emitted as image files plus a
    standalone JSONL, so the standalone run keeps its own browser orchestration in
    :func:`main`. This class is a thin uniform entry point over the *data half*
    (LLM event selection + ``*_info`` generation) for the future pipeline DAG:
    :meth:`produce` returns ``{app_type: [{event_id, <type>_info}, ...]}`` for one
    persona and performs no rendering. Behavior of the underlying functions is
    unchanged.
    """

    stage_label = "Stage7.3"
    stage_num = "7.3"
    index_key = "uuid"
    produces = "document"

    def __init__(self, types=None, events_per_type=20):
        self.types = list(types) if types else list(APP_TYPES)
        self.events_per_type = events_per_type

    def produce(self, record, ctx=None):
        events = record.get('Events', [])
        bp = record.get('Basic_Profile', {})
        ist = record.get('Init_State', {})
        uid = record.get('uuid')
        persona_name = bp.get('name', '') or record.get('name', '') or ist.get('name', '') or f'User{uid}'
        career = ist.get('career', bp.get('career', ''))
        location = ist.get('location', bp.get('location', ''))
        personality = bp.get('personality_traits', '')
        nationality = bp.get('nationality', '') or record.get('nationality', '') or 'Chinese'

        out = {}
        for app_type in self.types:
            selected = llm_select_events(
                events, app_type, persona_name=persona_name,
                location=location, nationality=nationality, n=self.events_per_type,
            )
            need_llm = [e for e in selected if f"{app_type}_info" not in e]
            out[app_type] = call_llm_generate_info(
                persona_name, career, location, personality,
                need_llm, app_type, nationality,
            ) if need_llm else []
        return out


if __name__ == '__main__':
    main()
