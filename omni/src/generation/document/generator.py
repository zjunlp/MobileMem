"""Document generator (Memories / Document): orchestration + Playwright render.

Holds the APP_TYPES constant, the shared 'document' logger, the HTML->PNG
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
import config
from config import LOG_DIR
from infra.store import (
    load_manifest_index,
    manifest_record_key,
    read_jsonl,
    write_manifest_index_atomic,
)
from generation.event_expansion import load_sub_events_index, expand_events_for_imaging
from core import DIR_NAME
from core.lang import is_chinese_persona
from backends.llm import set_log_context
from infra.base_generator import Generator
from infra.html_screenshot import render_html_to_png

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

logger = logging.getLogger('document')
logger.setLevel(logging.DEBUG)
os.makedirs(LOG_DIR, exist_ok=True)
fh = logging.FileHandler(os.path.join(LOG_DIR, 'document.log'), encoding='utf-8')
fh.setLevel(logging.DEBUG)
fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
sh = logging.StreamHandler()
sh.setLevel(logging.INFO)
sh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
logger.addHandler(fh)
logger.addHandler(sh)

APP_TYPES = ["ticket", "money", "friend"]


def _hydrate_info_from_manifest(personas, manifest, document_types):
    """Attach cached document info to the expanded in-memory event view."""
    for persona in personas:
        uid = persona.get('uuid')
        for event in persona.get('Events', []):
            event_id = str(event.get('event_id'))
            for document_type in document_types:
                cached = manifest.get((uid, event_id, document_type))
                if not cached:
                    continue
                info = cached.get(f'{document_type}_info', cached.get('info'))
                if info:
                    event[f'{document_type}_info'] = info


def _record_is_in_scope(record, uuid_filter, document_types):
    key = manifest_record_key(record, 'type')
    if key is None:
        return False
    uid, _, document_type = key
    return ((uuid_filter is None or uid in uuid_filter)
            and document_type in document_types)


def render_screenshot(page, html_content, png_path, html_path=None, keep_html=False):
    """Render HTML to a PNG screenshot, cropped to content height (to avoid bottom whitespace)."""
    return render_html_to_png(page, html_content, png_path, html_path=html_path,
                              keep_html=keep_html, clip_to_body=True)

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
    parser.add_argument('--manifest-file', type=str,
                        default=os.path.join(config.OUTPUT_DIR, 'data',
                                             'document_records.jsonl'),
                        help='Owned document manifest JSONL')
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
                        help='sub_events JSONL for expanding mid/long-term events')
    parser.add_argument('--force', action='store_true',
                        help='Ignore existing screenshots and regenerate from scratch')
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("document: ticket / money / friend screenshot generator")
    logger.info(f"Types: {args.types}")
    logger.info(f"UUID filter: {args.uuid_filter or 'ALL'}")
    logger.info(f"Events per type: {args.events_per_type}")
    logger.info(f"Output: {args.output_dir}")
    logger.info(f"Manifest: {args.manifest_file}")
    logger.info(f"Sub-events file: {args.sub_events_file}")
    logger.info("=" * 60)

    # Read data
    event_records = read_jsonl(args.events_file)

    # Load the sub-events index and expand mid/long-term events
    sub_index = load_sub_events_index(args.sub_events_file)
    logger.info(f"Sub-events index: {len(sub_index)} parent events loaded")
    for persona in event_records:
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

    manifest = load_manifest_index(args.manifest_file, 'type')
    _hydrate_info_from_manifest(event_records, manifest, args.types)
    if manifest:
        logger.info(f"[Manifest] Loaded {len(manifest)} document records")

    if args.force:
        manifest = {
            key: record for key, record in manifest.items()
            if not _record_is_in_scope(record, args.uuid_filter, args.types)
        }
        for persona in event_records:
            uid = persona.get('uuid')
            if args.uuid_filter is not None and uid not in args.uuid_filter:
                continue
            for event in persona.get('Events', []):
                for document_type in args.types:
                    event.pop(f'{document_type}_info', None)
        if not args.dry_run:
            write_manifest_index_atomic(manifest, args.manifest_file)

        import shutil
        for persona in event_records:
            uid = persona.get('uuid')
            if args.uuid_filter is not None and uid not in args.uuid_filter:
                continue
            for document_type in args.types:
                type_dir = Path(args.output_dir) / f'uid{uid}' / DIR_NAME[document_type]
                if type_dir.exists() and not args.dry_run:
                    shutil.rmtree(type_dir)
                    logger.info(f"  Removed {type_dir}")
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

    def save_manifest_record(uid, ev, app_type, png_path, info, status):
        participants = []
        for p in ev.get('participants', []):
            if isinstance(p, dict):
                participants.append(p.get('name', str(p)))
            else:
                participants.append(str(p))
        eid = ev.get('event_id', '')
        eid_str = str(eid)
        parent_eid = int(eid_str.split('_')[0]) if '_' in eid_str else eid
        record = {
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
        }
        key = manifest_record_key(record, 'type')
        manifest[key] = record
        write_manifest_index_atomic(manifest, args.manifest_file)

    try:
        for persona in event_records:
            uid = persona.get('uuid', 0)
            if args.uuid_filter is not None and uid not in args.uuid_filter:
                continue

            set_log_context(uuid=uid, stage="document")
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
            is_cn = (is_chinese_persona(nationality))
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
                                if not args.dry_run:
                                    type_dir = os.path.join(
                                        args.output_dir, f'uid{uid}', DIR_NAME[app_type])
                                    png_path = os.path.join(
                                        type_dir, f"{uid}_{app_type}_{eid}.png")
                                    save_manifest_record(
                                        uid, e, app_type, png_path, info, 'pending')
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
                        if not args.dry_run:
                            save_manifest_record(uid, ev, app_type, png_path, info, 'skipped')
                        logger.debug(f"  SKIP: {png_name}")
                        continue

                    if args.dry_run:
                        logger.info(f"  [DRY] {png_name}")
                        continue

                    save_manifest_record(uid, ev, app_type, png_path, info, 'pending')
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

                        save_manifest_record(uid, ev, app_type, png_path, info, 'done')
                    except Exception as e:
                        stats['failed'] += 1
                        save_manifest_record(uid, ev, app_type, png_path, info, 'failed')
                        logger.error(f"  FAIL: {png_name}: {e}")

    finally:
        if browser:
            browser.close()
        if pw_ctx:
            pw_ctx.stop()

    # The expanded event view and generated *_info stay in this process only.
    if not args.dry_run:
        write_manifest_index_atomic(manifest, args.manifest_file)
        logger.info(f"Saved standalone JSONL: {args.manifest_file} ({len(manifest)} records)")

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

    label = "document"
    index_key = "uuid"

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
