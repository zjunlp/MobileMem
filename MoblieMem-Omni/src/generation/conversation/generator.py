"""Conversation generator (Memories / Conversation): group-chat screenshot orchestration.

Holds the ``setup_logging`` factory + module 'stage7' logger, the per-persona
orchestration (``process_persona`` / ``main``) and the thin
``ConversationGenerator``. Chat templates, Chrome screenshotting, chat-UI HTML
rendering, LLM content and avatar generation live in sibling modules.
"""
from __future__ import annotations

import argparse
import logging
import os
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Optional

import config
from common import (
    LOG_DIR,
    PROMPTS_DIR,
    read_jsonl,
    write_jsonl,
    load_sub_events_index,
    expand_events_for_imaging,
)
from core import GroupChat, DIR_NAME
from backends.llm import set_log_context
from generation.event_photo.data import load_init_state_map
from generation.event_photo.generator import ensure_person_portrait
from infra.base_generator import Generator

from .templates import load_prompt, resolve_chat_template
from .screenshot import html_to_multi_png
from .render import (
    normalize_group_chat_messages, render_group_chat_html,
)
from .content import (
    _collect_all_social_members, build_group_specs, generate_group_chat_content,
)
from .avatars import (
    build_persona_source_signature, ensure_member_avatars,
)


def setup_logging():
    summary_handler = logging.FileHandler(os.path.join(LOG_DIR, 'stage7_summary.log'), encoding='utf-8')
    summary_handler.setLevel(logging.INFO)
    detail_handler = logging.FileHandler(os.path.join(LOG_DIR, 'stage7_detail.log'), encoding='utf-8')
    detail_handler.setLevel(logging.DEBUG)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    for h in [summary_handler, detail_handler, console_handler]:
        h.setFormatter(fmt)
    logger = logging.getLogger('stage7')
    logger.setLevel(logging.DEBUG)
    for h in [summary_handler, detail_handler, console_handler]:
        logger.addHandler(h)
    return logger

logger = setup_logging()


def process_persona(
    persona: Dict, prompts_dir: str, image_base_dir: str,
    template_name: str, existing_gc_ids: Optional[set] = None,
    existing_gc_records: Optional[Dict[str, Dict]] = None,
    gc_save_callback=None,
    rerender_existing: bool = False,
    keep_html: bool = False
) -> Dict:
    """Generate group chats for a single persona — one per event.

    gc_save_callback: callable(group_id, group_chat_record) called after each
                      group chat is generated and rendered.
    """
    uuid = persona.get('uuid')
    set_log_context(uuid=uuid, stage="stage7_group_chats")
    bp = persona.get('Basic_Profile', {})
    name = bp.get('name', 'Unknown')
    nationality = bp.get('nationality', 'Chinese')
    effective_language = 'zh' if nationality == 'Chinese' else 'en'
    is_chinese = (nationality == 'Chinese')
    source_signature = build_persona_source_signature(persona)
    active_model = None
    events = persona.get('Events', [])

    if existing_gc_ids is None:
        existing_gc_ids = set()
    if existing_gc_records is None:
        existing_gc_records = {}

    logger.info(f"[uuid={uuid}] Generating group chats for {name} (nationality={nationality}, "
                f"lang={effective_language}, events={len(events)})")
    prompt_template = None

    template_path = resolve_chat_template(template_name, effective_language, nationality)

    # Remove the old global group_specs; generate them dynamically per event.
    person_image_dir = os.path.join(image_base_dir, f'uid{uuid}', DIR_NAME['person'])
    member_avatar_dir = os.path.join(image_base_dir, f'uid{uuid}', DIR_NAME['group_chat_members'])

    # Ensure the protagonist portrait exists.
    ensure_person_portrait(
        uuid, person_image_dir,
        persona.get('Basic_Profile'),
        persona.get('Init_State'),
        nationality, PROMPTS_DIR,
    )

    # -- Load full social relationship data for avatar generation.
    social_relationships = persona.get('Init_State', {}).get('social_relationships', {})
    social_graph = persona.get('Social_Graph', {})
    
    # Merge Stage2 and Stage3.9 social relationship data for avatar generation.
    all_social_data = {}
    
    # Add Stage2 data.
    for rel_key, info in social_relationships.items():
        if isinstance(info, dict):
            all_social_data[rel_key] = info
        else:
            all_social_data[rel_key] = {'description': str(info)}
    
    # Add Stage3.9 data.
    for category in ['inner_circle', 'extended_contacts', 'service_people', 'professional_network', 'online_contacts', 'weak_ties']:
        items = social_graph.get(category, [])
        for item in items:
            item_name = item.get('name', '')
            if item_name:
                # Convert Stage3.9 format to the compatible format.
                converted_info = {
                    'relationship_type': item.get('relationship_to_protagonist', ''),
                    'description': item.get('brief', ''),
                    'gender': item.get('gender', ''),
                    'age_range': item.get('age_range', '')
                }
                all_social_data[item_name] = converted_info

    # Use uid{N}/group_chat subdirectories.
    uuid_output_dir = os.path.join(image_base_dir, f'uid{uuid}', DIR_NAME['group_chat'])

    group_chats_by_id = {gid: dict(record) for gid, record in existing_gc_records.items()}
    errors = []

    if not events:
        raise ValueError(f"uuid={uuid} has no events for group-chat generation")

    # Precollect all social members for LLM group-member selection.
    all_social_members = _collect_all_social_members(persona)

    # Generate AI avatars only for Stage2 social members; Stage3.9 members use text placeholders.
    stage2_member_names = []
    for rel_key, rel_info in social_relationships.items():
        if isinstance(rel_info, dict):
            rel_name = rel_info.get('name', '') or rel_key
        elif isinstance(rel_info, str):
            rel_name = rel_key
        else:
            continue
        if rel_name and rel_name != name:
            stage2_member_names.append(rel_name)

    if not stage2_member_names:
        stage2_member_names = [
            member.get('name', '')
            for member in all_social_members
            if member.get('name') and member.get('name') != name
        ]
        if stage2_member_names:
            logger.info(
                f"[uuid={uuid}] social_relationships missing; fallback to Social_Graph members ({len(stage2_member_names)})"
            )

    stage2_names_set = set(stage2_member_names)

    # Prefer AI avatars for Stage2 members; fall back to Social_Graph members if missing.
    avatar_spec = [{"members": [name] + stage2_member_names}]
    ensure_member_avatars(uuid, avatar_spec, all_social_data, member_avatar_dir, name, nationality)

    for gc_idx, event in enumerate(events):
        event_id = event.get('event_id', gc_idx)
        # Build group_id from event_id so IDs stay stable after sub-event expansion.
        group_id = f"{uuid}_gc_{event_id}"

        # Resume support: skip completed items.
        if group_id in existing_gc_ids and not rerender_existing:
            logger.debug(f"[uuid={uuid}] {group_id}: SKIP (exists)")
            continue

        # Dynamically generate group-chat specs for this event, including all social members.
        group_specs = build_group_specs(persona, event)

        related_event_id = event.get('event_id', gc_idx)
        existing_gc_record = existing_gc_records.get(group_id)

        if existing_gc_record:
            action = 'Re-rendering' if rerender_existing else 'Restoring'
            logger.info(f"[uuid={uuid}] {group_id}: {action} assets from existing stage7 record")
            try:
                os.makedirs(uuid_output_dir, exist_ok=True)

                existing_html = existing_gc_record.get('html_file')
                html_file = existing_html or os.path.join(uuid_output_dir, f"{group_id}.html")
                existing_png = existing_gc_record.get('png_file')  # noqa: F841
                png_base = os.path.join(uuid_output_dir, f"{group_id}_cropped.png")

                group_spec = {
                    "group_type": existing_gc_record.get('group_type', 'small'),
                    "group_name": existing_gc_record.get('group_name', '群聊'),
                    "members": existing_gc_record.get('members', []),
                    "member_count": len(existing_gc_record.get('members', [])),
                }
                group_data = {
                    "group_name": existing_gc_record.get('group_name', group_spec['group_name']),
                    "messages": existing_gc_record.get('messages', []),
                }
                html_content = render_group_chat_html(
                    group_data, group_spec, template_path, effective_language,
                    person_image_dir, member_avatar_dir, uuid, template_name, nationality
                )
                with open(html_file, 'w', encoding='utf-8') as f:
                    f.write(html_content)

                png_files, msg_ranges = html_to_multi_png(html_content, png_base,
                                              segment_height=800, max_segments=5)
                png_success = len(png_files) > 0

                # Delete HTML if PNG succeeded and keep_html is False
                if png_success and not keep_html and html_file and os.path.exists(html_file):
                    os.remove(html_file)
                    html_file = None

                restored_record = dict(existing_gc_record)
                restored_record['html_file'] = html_file
                restored_record['png_file'] = png_files if png_success else None
                if msg_ranges:
                    restored_record['crop_message_ranges'] = msg_ranges
                group_chats_by_id[group_id] = restored_record

                if gc_save_callback:
                    gc_save_callback(group_id, restored_record)

                if png_success:
                    continue
            except Exception as e:
                logger.warning(f"[uuid={uuid}] {group_id}: Asset restore failed, falling back to regeneration: {e}")

        logger.debug(f"[uuid={uuid}] Group {group_id}: LLM selecting group for event '{event.get('event_name', '')}'")

        try:
            if active_model is None:
                from backends.llm import get_text_llm_model
                active_model = get_text_llm_model(is_chinese)
            if prompt_template is None:
                # Chinese personas use the Chinese prompt; others use the _en one.
                prompt_file = 'stage7_group_chat.txt' if nationality == 'Chinese' else 'stage7_group_chat_en.txt'
                prompt_template = load_prompt(os.path.join(prompts_dir, prompt_file))

            # Generate content via LLM — LLM chooses the best group
            group_data, group_spec = generate_group_chat_content(
                persona, event, group_specs, prompt_template, model=active_model
            )
            group_data['messages'] = normalize_group_chat_messages(
                group_data.get('messages', []),
                group_spec.get('members', []),
                name,
            )

            # Generate missing avatars only for Stage2 members chosen by the LLM;
            # non-Stage2 members use text placeholders.
            selected_stage2 = [m for m in group_spec.get('members', []) if m in stage2_names_set or m == name]
            if selected_stage2:
                selected_avatar_spec = [{"members": selected_stage2}]
                ensure_member_avatars(uuid, selected_avatar_spec, all_social_data,
                                      member_avatar_dir, name, nationality)

            # Render HTML
            html_file = os.path.join(uuid_output_dir, f"{group_id}.html")
            png_base = os.path.join(uuid_output_dir, f"{group_id}_cropped.png")

            os.makedirs(uuid_output_dir, exist_ok=True)

            png_files = []
            if os.path.exists(template_path):
                filled_html = render_group_chat_html(
                    group_data, group_spec, template_path, effective_language, person_image_dir, member_avatar_dir, uuid,
                    template_name, nationality)
                with open(html_file, 'w', encoding='utf-8') as f:
                    f.write(filled_html)

                # Generate multi-segment PNGs
                png_files, msg_ranges = html_to_multi_png(filled_html, png_base,
                                                          segment_height=800, max_segments=5)
                png_success = len(png_files) > 0

                # Delete HTML if PNG succeeded and keep_html is False
                if png_success and not keep_html and html_file and os.path.exists(html_file):
                    os.remove(html_file)
                    html_file = None
            else:
                logger.warning(f"Template not found: {template_path}")
                html_file = None
                png_success = False

            messages = group_data.get('messages', [])
            group_chat_record = {
                "group_id": group_id,
                "group_type": group_spec['group_type'],
                "group_name": group_data.get('group_name', group_spec['group_name']),
                "members": group_spec['members'],
                "member_count": len(group_spec['members']),
                "related_event_id": related_event_id,
                "related_event_name": event.get('event_name', ''),
                "messages": messages,
                "html_file": html_file,
                "png_file": png_files if png_success else None,
                "crop_message_ranges": msg_ranges if (png_success and msg_ranges) else None
            }
            group_chats_by_id[group_id] = group_chat_record
            logger.debug(f"[uuid={uuid}] {group_id}: {len(messages)} messages")

            # -- Immediate callback: save JSONL as soon as each item completes.
            if gc_save_callback:
                gc_save_callback(group_id, group_chat_record)

        except Exception as e:
            logger.error(f"[uuid={uuid}] {group_id} FAILED: {e}")
            logger.debug(traceback.format_exc())
            errors.append({"group_id": group_id, "error": str(e)})

    # Emit through the GroupChat contract (P1-2). The declared fields keep their
    # order and the stage-specific '_errors' rides in extra as the trailing key,
    # so the serialized record stays stable.
    result = GroupChat(
        uuid=uuid,
        source_signature=source_signature,
        nationality=nationality,
        language=effective_language,
        template=template_name,
        group_chats=list(group_chats_by_id.values()),
        extra={"_errors": errors},
    ).to_dict()

    logger.info(f"[uuid={uuid}] Done: {len(group_chats_by_id)} group chats, {len(errors)} errors")
    return result

# ============================================================================
# Main
# ============================================================================


def main():
    parser = argparse.ArgumentParser(description='Stage 7: Generate group chats + screenshots')
    # ---- Key hyperparameters ----
    parser.add_argument('--input-file', type=str,
                        default=os.path.join(config.OUTPUT_DIR, 'data', 'stage4_annual_events.jsonl'),
                        help='Input stage4 JSONL file')
    parser.add_argument('--output-file', type=str,
                        default=os.path.join(config.OUTPUT_DIR, 'data', 'stage7_group_chats.jsonl'),
                        help='Output stage7 JSONL file')
    parser.add_argument('--prompts-dir', type=str,
                        default=config.PROMPTS_DIR,
                        help='Prompts directory')
    parser.add_argument('--image-dir', type=str,
                        default=os.path.join(config.OUTPUT_DIR, 'image'),
                        help='Image base directory')
    parser.add_argument('--max-workers', type=int, default=5,
                        help='Number of parallel workers (default: 3)')
    parser.add_argument('--uuid-filter', type=int, nargs='+', default=None,
                        help='Only process these UUIDs')
    parser.add_argument('--template', type=str,
                        choices=['auto', 'wechat', 'telegram', 'discord', 'x'],
                        default='auto',
                        help='Chat UI template to use')
    parser.add_argument('--rerender-existing', action='store_true',
                        help='Rebuild HTML/PNG for existing stage7 records using current avatar assets')
    parser.add_argument('--keep-html', action='store_true',
                        help='Keep HTML files after PNG generation (default: delete HTML)')
    parser.add_argument('--force-regenerate', '--force', dest='force_regenerate', action='store_true',
                        help='Delete cache for each uid and regenerate all group chats from scratch')
    parser.add_argument('--sub-events-file', type=str,
                        default=os.path.join(config.OUTPUT_DIR, 'data', 'stage4_5_sub_events.jsonl'),
                        help='stage4.5 sub-events JSONL for expanding mid/long-term events')
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output_file), exist_ok=True)

    logger.info(f"{'=' * 70}")
    logger.info("STAGE 7: Group Chat Generation")
    logger.info(f"Input:  {args.input_file}")
    logger.info(f"Output: {args.output_file}")
    logger.info(f"Image dir: {args.image_dir}")
    logger.info(f"Template: {args.template}")
    logger.info(f"Re-render existing: {args.rerender_existing}")
    logger.info(f"Force regenerate: {args.force_regenerate}")
    logger.info(f"{'=' * 70}")

    personas = read_jsonl(args.input_file)
    if not personas:
        logger.error(f"No data in {args.input_file}")
        return

    init_states_file = os.path.join(config.OUTPUT_DIR, 'data', 'stage2_init_states.jsonl')
    init_state_map = load_init_state_map(init_states_file)
    for persona in personas:
        uid = persona.get('uuid')
        init_state = persona.get('Init_State')
        social_relationships = init_state.get('social_relationships') if isinstance(init_state, dict) else None
        if social_relationships:
            continue

        fallback_record = init_state_map.get(uid)
        if fallback_record is None:
            fallback_record = init_state_map.get(str(uid), {})
        fallback_init_state = fallback_record.get('Init_State', {}) if isinstance(fallback_record, dict) else {}
        fallback_relationships = fallback_init_state.get('social_relationships') if isinstance(fallback_init_state, dict) else None
        if not fallback_relationships:
            continue

        merged_init_state = dict(fallback_init_state)
        if isinstance(init_state, dict):
            merged_init_state.update(init_state)
        merged_init_state['social_relationships'] = fallback_relationships
        persona['Init_State'] = merged_init_state
        logger.info(f"[uuid={uid}] Restored missing social_relationships from stage2_init_states")

    # Sub-event expansion: replace mid/long-term events with stage4.5 sub-events.
    sub_index = load_sub_events_index(args.sub_events_file)
    logger.info(f"Sub-events index: {len(sub_index)} parent events loaded")
    for persona in personas:
        uid = persona.get('uuid', 0)
        original_events = persona.get('Events', [])
        expanded = []
        for image_id, ev in expand_events_for_imaging(uid, original_events, sub_index):
            if 'event_id' not in ev:
                ev['event_id'] = image_id
            expanded.append(ev)
        persona['Events'] = expanded
        logger.info(f"[uuid={uid}] Events expanded: {len(original_events)} -> {len(expanded)}")

    persona_signature_by_uuid = {
        p.get('uuid'): build_persona_source_signature(p)
        for p in personas if isinstance(p, dict) and 'uuid' in p
    }

    existing = {}
    for r in read_jsonl(args.output_file):
        if not (isinstance(r, dict) and 'uuid' in r):
            continue
        uid = r['uuid']
        expected_signature = persona_signature_by_uuid.get(uid)
        cached_signature = r.get('source_signature')
        if expected_signature and cached_signature == expected_signature:
            existing[uid] = r
            continue
        logger.info(
            f"[uuid={uid}] Ignoring stale stage7 cache: "
            f"cached signature {'missing' if not cached_signature else 'mismatch'}"
        )

    # Collect existing group_chat group_ids for resume support.
    existing_gc_ids_by_uuid: Dict[int, set] = {}
    existing_gc_records_by_uuid: Dict[int, Dict[str, Dict]] = {}
    for uid, rec in existing.items():
        gc_ids = set()
        gc_records = {}
        for gc in rec.get('group_chats', []):
            gid = gc.get('group_id')
            if gid:
                gc_records[gid] = gc
                gc_ids.add(gid)
            # Also check whether the PNG exists.
            png = gc.get('png_file')
            if isinstance(png, list):
                # Multi-segment screenshots: at least one segment counts as valid.
                if not png or not any(os.path.exists(p) for p in png):
                    gc_ids.discard(gid)
            elif not png or not os.path.exists(png):
                gc_ids.discard(gid)  # Regenerate when the PNG is missing.
        existing_gc_ids_by_uuid[uid] = gc_ids
        existing_gc_records_by_uuid[uid] = gc_records

    # --force-regenerate: clear all caches for pending uids.
    if args.force_regenerate:
        import shutil
        uids_to_clear = [p.get('uuid') for p in personas
                         if not args.uuid_filter or p.get('uuid') in args.uuid_filter]
        for uid in uids_to_clear:
            # Clear in-memory cache records.
            existing_gc_ids_by_uuid.pop(uid, None)
            existing_gc_records_by_uuid.pop(uid, None)
            existing.pop(uid, None)
            # Delete group-chat screenshot directories on disk.
            gc_dir = os.path.join(args.image_dir, f'uid{uid}', DIR_NAME['group_chat'])
            if os.path.isdir(gc_dir):
                shutil.rmtree(gc_dir)
                logger.info(f"[uuid={uid}] Force-regenerate: deleted {gc_dir}")
            else:
                logger.info(f"[uuid={uid}] Force-regenerate: no cache to delete")
        # Immediately write cleaned JSONL after removing records for cleared uids.
        ordered = [existing[p.get('uuid')] for p in personas if p.get('uuid') in existing]
        write_jsonl(ordered, args.output_file)
        logger.info(f"Force-regenerate: cleared cache for {len(uids_to_clear)} uid(s), JSONL updated")

    to_process = []
    for p in personas:
        uuid = p.get('uuid')
        if args.uuid_filter and uuid not in args.uuid_filter:
            continue
        n_events = len(p.get('Events', []))
        n_existing = 0 if args.rerender_existing else len(existing_gc_ids_by_uuid.get(uuid, set()))
        if n_existing >= n_events and n_events > 0:
            logger.info(f"[uuid={uuid}] SKIP (all {n_existing} group chats exist)")
            continue
        to_process.append(p)

    if not to_process:
        logger.info("Nothing to process.")
        return

    lock = threading.Lock()
    results = dict(existing)

    def process_and_save(persona):
        uuid = persona.get('uuid')
        ex_gc_ids = existing_gc_ids_by_uuid.get(uuid, set())
        ex_gc_records = existing_gc_records_by_uuid.get(uuid, {})

        def gc_save_callback(new_group_id, new_gc_record):
            with lock:
                # Append the new record directly to results without rebuilding the tree.
                if uuid not in results:
                    results[uuid] = {
                        "uuid": uuid,
                        "source_signature": build_persona_source_signature(persona),
                        "nationality": persona.get('Basic_Profile', {}).get('nationality', 'Chinese'),
                        "language": 'zh' if persona.get('Basic_Profile', {}).get('nationality') == 'Chinese' else 'en',
                        "template": args.template,
                        "group_chats": [],
                        "_errors": [],
                        "_partial": True,
                    }
                # Append or update this record.
                existing_gcs = {gc['group_id']: gc for gc in results[uuid].get('group_chats', [])}
                existing_gcs[new_group_id] = new_gc_record
                results[uuid]['group_chats'] = list(existing_gcs.values())
                results[uuid]['_partial'] = True
                ordered = [results[p.get('uuid')] for p in personas if p.get('uuid') in results]
                write_jsonl(ordered, args.output_file)
                total_now = len(results[uuid]['group_chats'])
                logger.info(f"[uuid={uuid}] Saved {new_group_id} ({total_now} total)")

        try:
            record = process_persona(persona, args.prompts_dir, args.image_dir, args.template,
                                     existing_gc_ids=ex_gc_ids, existing_gc_records=ex_gc_records,
                                     gc_save_callback=gc_save_callback,
                                     rerender_existing=args.rerender_existing,
                                     keep_html=args.keep_html)
            with lock:
                # Merge existing records while preserving previously completed group_chats.
                if uuid in results:
                    old_gcs = {gc['group_id']: gc for gc in results[uuid].get('group_chats', [])}
                    for gc in record.get('group_chats', []):
                        old_gcs[gc['group_id']] = gc
                    record['group_chats'] = list(old_gcs.values())
                record.pop('_partial', None)
                results[uuid] = record
                ordered = [results[p.get('uuid')] for p in personas if p.get('uuid') in results]
                write_jsonl(ordered, args.output_file)
                logger.info(f"[uuid={uuid}] Saved checkpoint ({len(record.get('group_chats', []))} chats)")
            return record
        except Exception as e:
            logger.error(f"[uuid={uuid}] FATAL: {e}")
            return None

    actual_workers = min(args.max_workers, len(to_process))
    failed_uids = []
    with ThreadPoolExecutor(max_workers=actual_workers) as executor:
        futures = {executor.submit(process_and_save, p): p.get('uuid') for p in to_process}
        for future in as_completed(futures):
            uuid = futures[future]
            try:
                if future.result() is None:
                    failed_uids.append(uuid)
            except Exception as e:
                logger.error(f"[uuid={uuid}] Thread error: {e}")
                failed_uids.append(uuid)

    if failed_uids:
        raise RuntimeError(f"Stage7 failed for uuid(s): {sorted(set(failed_uids))}")

    ordered = [results[p.get('uuid')] for p in personas if p.get('uuid') in results]
    write_jsonl(ordered, args.output_file)

    logger.info(f"{'=' * 70}")
    logger.info(f"STAGE 7 COMPLETE: {len(results)} records saved")
    logger.info(f"{'=' * 70}")


# ===================================================================== #
# Domain generator -- thin uniform entry point for the future pipeline DAG.
# ===================================================================== #

class ConversationGenerator(Generator):
    """Generate per-persona group-chat conversations + screenshots.

    Group chats are LLM-generated, rendered to chat-UI HTML and screenshotted to
    segmented PNGs, and emitted via the ``GroupChat`` contract. The standalone run
    keeps its own parallel orchestration in :func:`main`; this class is a thin
    uniform entry point for the future pipeline DAG: :meth:`produce` generates the
    group chats for one persona (delegating to the unchanged
    :func:`process_persona`). Behavior of the underlying functions is unchanged.
    """

    stage_label = "Stage7"
    stage_num = "7"
    index_key = "uuid"
    produces = "conversation"

    def __init__(self, template_name="auto", image_base_dir=None):
        self.template_name = template_name
        self.image_base_dir = image_base_dir or os.path.join(config.OUTPUT_DIR, 'image')

    def produce(self, record, ctx=None):
        return process_persona(
            record, PROMPTS_DIR, self.image_base_dir, self.template_name,
        )


if __name__ == '__main__':
    main()
