"""
Stage 6: Generate 7 types of questions for each persona.

Input: data/10_person/stage5_sessions.jsonl
Output: data/10_person/stage6_questions.jsonl
"""

import argparse
import json
import logging
import os
import re
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional

import jsonlines
from dotenv import load_dotenv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
SRC_DIR = os.path.join(PROJECT_ROOT, 'src')

env_path = os.path.join(SRC_DIR, '.env')
if os.path.exists(env_path):
    load_dotenv(env_path, override=False)

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm_request import llm_request


LOG_DIR = os.path.join(PROJECT_ROOT, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)


def setup_logging():
    summary_handler = logging.FileHandler(
        os.path.join(LOG_DIR, 'stage6_summary.log'),
        encoding='utf-8',
    )
    summary_handler.setLevel(logging.INFO)
    detail_handler = logging.FileHandler(
        os.path.join(LOG_DIR, 'stage6_detail.log'),
        encoding='utf-8',
    )
    detail_handler.setLevel(logging.DEBUG)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    for handler in [summary_handler, detail_handler, console_handler]:
        handler.setFormatter(fmt)
    logger = logging.getLogger('stage6')
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    for handler in [summary_handler, detail_handler, console_handler]:
        logger.addHandler(handler)
    return logger


logger = setup_logging()

QUESTION_TYPES = [
    "single_hop",
    "multi_hop",
    "knowledge_update",
    "temporal_reasoning",
    "visual_reasoning",
    "implicit_preference",
    "abstention",
]

TARGET_PER_TYPE = 200
BATCH_SIZE = 10
SESSION_CHUNK_SIZE = 8
MULTI_VISUAL_MAX_USAGE_PER_IMAGE = 3
MAX_BATCHES_PER_TYPE = None
ENGLISH_CJK_TRANSLATION_MODEL = "gpt-5.4-mini"
ENGLISH_CJK_TRANSLATION_CACHE: Dict[str, str] = {}
ENGLISH_CJK_TRANSLATION_LOCK = threading.Lock()

# Visual reasoning composition controls.
# The stat branch handles same-type questions across sessions (book/music/shopping/video/event_scene/friend/ticket, etc.).
# The detail branch handles same-type questions within a single session (mainly comparisons across multiple group_chat pages).
VISUAL_STAT_RATIO = 0.65                    # Proportion of all visual_reasoning questions allocated to the stat branch
VISUAL_GROUP_CHAT_DETAIL_QUOTA_RATIO = 0.30  # Upper limit for group chat questions in the detail branch (as a proportion of the total)
VISUAL_GROUP_CHAT_TYPES = {'group_chat', 'group_chat_member'}
VISUAL_STAT_EXCLUDE_TYPES = {'group_chat', 'group_chat_member', 'person'}  # The stat branch does not process group chats or person portraits
# Target proportion of each individual type among all visual_reasoning questions; the stat branch allocates per-type quotas accordingly
VISUAL_STAT_PER_TYPE_QUOTA_RATIO = {
    'event_scene': 0.20,
    'book': 0.05,
    'music': 0.05,
    'shopping': 0.05,
    'video': 0.05,
    'friend': 0.05,
    'ticket': 0.05,
}
VISUAL_STAT_DEFAULT_QUOTA_RATIO = 0.03
MULTIPLE_CHOICE_TARGET_RATIOS = {
    'single_hop': 0.30,
    'multi_hop': 0.15,
    'knowledge_update': 0.30,
    'temporal_reasoning': 0.20,
    'visual_reasoning': 0.025,
    'implicit_preference': 0.10,
    'abstention': 0.025,
}


def normalize_image_ref(image_ref: str) -> str:
    image_ref = str(image_ref or '').strip().replace('\\', '/')
    if not image_ref:
        return ''

    lower_ref = image_ref.lower()
    image_idx = lower_ref.find('image/')
    if image_idx >= 0:
        image_ref = image_ref[image_idx:]
    elif lower_ref.startswith('output/'):
        output_idx = lower_ref.find('output/image/')
        if output_idx >= 0:
            image_ref = image_ref[output_idx + len('output/'):]
    elif re.match(r'^uid\d+/', image_ref, flags=re.IGNORECASE):
        image_ref = f'image/{image_ref}'

    image_ref = re.sub(r'/+', '/', image_ref)
    return image_ref.lstrip('/')


def load_image_info_indexes(path: Optional[str]) -> Dict[str, Dict]:
    by_ref = {}
    by_uuid = {}
    if not path or not os.path.exists(path):
        return {"by_ref": by_ref, "by_uuid": by_uuid}

    for record in read_jsonl(path):
        if not isinstance(record, dict):
            continue
        normalized_ref = normalize_image_ref(record.get('image_path', ''))
        if not normalized_ref:
            continue
        cleaned = dict(record)
        cleaned['_normalized_image_ref'] = normalized_ref
        by_ref[normalized_ref] = cleaned
        by_uuid.setdefault(cleaned.get('uuid'), []).append(cleaned)

    return {"by_ref": by_ref, "by_uuid": by_uuid}


def load_image_summary_indexes(path: Optional[str]) -> Dict[str, Dict]:
    by_ref = {}
    if not path or not os.path.exists(path):
        return {"by_ref": by_ref}

    for record in read_jsonl(path):
        if not isinstance(record, dict):
            continue
        normalized_ref = normalize_image_ref(record.get('image_path', ''))
        if not normalized_ref:
            continue
        cleaned = dict(record)
        cleaned['_normalized_image_ref'] = normalized_ref
        by_ref[normalized_ref] = cleaned

    return {"by_ref": by_ref}


def infer_image_type(image_ref: str, image_info_by_ref: Optional[Dict[str, Dict]] = None) -> str:
    normalized_ref = normalize_image_ref(image_ref)
    if image_info_by_ref:
        record = image_info_by_ref.get(normalized_ref)
        if record and record.get('type'):
            return str(record.get('type'))

    parts = normalized_ref.split('/')
    if len(parts) >= 3:
        return parts[-2]
    return ''


def sanitize_image_info(record: Dict) -> Dict:
    return {
        key: value
        for key, value in record.items()
        if key not in {'uuid', 'image_path', '_normalized_image_ref'}
    }


def format_selected_image_metadata(
    selected_images: List[str],
    image_info_by_ref: Optional[Dict[str, Dict]] = None,
) -> str:
    lines = []
    for image_ref in selected_images:
        normalized_ref = normalize_image_ref(image_ref)
        record = (image_info_by_ref or {}).get(normalized_ref)
        if record:
            payload = sanitize_image_info(record)
            lines.append(
                f"- image_ref={normalized_ref} | metadata={json.dumps(payload, ensure_ascii=False)}"
            )
        else:
            lines.append(f"- image_ref={normalized_ref} | metadata={{}}")
    return "\n".join(lines)


def format_selected_image_captions(
    selected_images: List[str],
    image_summary_by_ref: Optional[Dict[str, Dict]] = None,
    output_language: str = 'zh',
) -> str:
    lines = []
    for image_ref in selected_images:
        normalized_ref = normalize_image_ref(image_ref)
        record = (image_summary_by_ref or {}).get(normalized_ref)
        if not record:
            lines.append(f"- image_ref={normalized_ref} | caption=")
            continue

        if output_language == 'en':
            caption = record.get('summary_en') or record.get('summary_zh') or ''
        else:
            caption = record.get('summary_zh') or record.get('summary_en') or ''
        caption = str(caption or '').strip().replace('\r\n', '\n')
        lines.append(f"- image_ref={normalized_ref} | caption={caption}")
    return "\n".join(lines)


def build_image_session_map(sessions: List[Dict]) -> Dict[str, List[Dict]]:
    mapping = {}
    for session in sessions:
        session_id = session.get('session_id', '')
        event_id = session.get('event_id', '')
        refs = set()
        image_refs = session.get('image_refs', {}) or {}
        for key, value in image_refs.items():
            if isinstance(value, str):
                refs.add(normalize_image_ref(value))
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        refs.add(normalize_image_ref(item.get('file', '')))
                    else:
                        refs.add(normalize_image_ref(item))
        for image_ref in session.get('image_candidates') or []:
            refs.add(normalize_image_ref(image_ref))
        for turn in session.get('dialogue', []) or []:
            if turn.get('content_type') == 'image':
                refs.add(normalize_image_ref(turn.get('image_inline', '')))

        for ref in refs:
            if not ref:
                continue
            mapping.setdefault(ref, []).append(
                {
                    'session_id': session_id,
                    'event_id': event_id,
                    'session': session,
                }
            )
    return mapping


def collect_relevant_memory_ids(
    sessions: List[Dict],
    image_refs: List[str],
    fallback_limit: int = 3,
) -> List[str]:
    normalized_refs = {
        normalize_image_ref(image_ref)
        for image_ref in image_refs
        if normalize_image_ref(image_ref)
    }
    matched = []
    fallback = []
    seen = set()

    for session in sessions:
        for memory_point in session.get('memory_points', []):
            if memory_point.get('memory_source') == 'interference':
                continue
            memory_id = str(memory_point.get('memory_id', '')).strip()
            if not memory_id or memory_id in seen:
                continue
            fallback.append(memory_id)
            mp_refs = {
                normalize_image_ref(ref)
                for ref in memory_point.get('image_refs', []) or []
                if normalize_image_ref(ref)
            }
            if normalized_refs and mp_refs.intersection(normalized_refs):
                matched.append(memory_id)
                seen.add(memory_id)

    if matched:
        return matched[:fallback_limit]
    return fallback[:fallback_limit]


def build_session_indexes(sessions: List[Dict]):
    sessions_by_id = {}
    sessions_by_event = {}
    for session in sessions:
        session_id = session.get('session_id')
        event_id = session.get('event_id')
        if session_id:
            sessions_by_id[str(session_id)] = session
        sessions_by_event.setdefault(str(event_id), []).append(session)
    return sessions_by_id, sessions_by_event


def collect_session_image_refs(session: Dict) -> List[str]:
    refs = []
    seen = set()

    def add_ref(value):
        normalized = normalize_image_ref(value)
        if normalized and normalized not in seen:
            refs.append(normalized)
            seen.add(normalized)

    image_refs = session.get('image_refs', {}) or {}
    for value in image_refs.values():
        if isinstance(value, str):
            add_ref(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    add_ref(item.get('file', ''))
                else:
                    add_ref(item)

    for value in session.get('image_candidates') or []:
        add_ref(value)

    for turn in session.get('dialogue', []) or []:
        if turn.get('content_type') == 'image':
            add_ref(turn.get('image_inline', ''))

    return refs


def extract_question_image_refs(question: Dict) -> List[str]:
    refs = []
    seen = set()
    for value in question.get('image_refs') or []:
        normalized = normalize_image_ref(value)
        if normalized and normalized not in seen:
            refs.append(normalized)
            seen.add(normalized)
    return refs


def extract_evidence_explanations(question: Dict) -> List[str]:
    raw_evidence = question.get('evidence', [])
    if isinstance(raw_evidence, str):
        raw_evidence = [raw_evidence] if raw_evidence.strip() else []
    elif not isinstance(raw_evidence, list):
        raw_evidence = []

    explanations = []
    for item in raw_evidence:
        if isinstance(item, dict):
            text = item.get('explanation') or ''
        else:
            text = str(item or '').strip()
            match = re.match(r"memory_id=(.*?)\s*\|\s*content=(.*)", text)
            if match:
                text = match.group(2).strip()
        if text:
            explanations.append(text)
    return explanations


def build_visual_image_explanation(
    image_record: Optional[Dict],
    output_language: str = 'zh',
) -> str:
    """Return all generation information for this image from stage10_total_images in a consistent format as the basis for evidence.

    Strictly remove the four internal fields (uuid / sub_event_id / type / image_path, as well as the internal helper
    `_normalized_image_ref`); return all remaining fields as a JSON string for the explanation.
    """
    if not image_record:
        return ""
    payload = {
        k: v for k, v in image_record.items()
        if k not in {'uuid', 'sub_event_id', 'type', 'image_path', '_normalized_image_ref'}
    }
    if not payload:
        return ""
    return json.dumps(payload, ensure_ascii=False, sort_keys=False)


def extract_short_dialogue_around_image(
    session: Dict,
    image_ref: str,
    window: int = 2,
    max_chars: int = 360,
) -> str:
    """Extract the +/-window "text turns" before and after this image from session.dialogue as the dialogue excerpt."""
    if not session:
        return ""
    norm_ref = normalize_image_ref(image_ref)
    dialogue = session.get('dialogue') or []
    target_idx = -1
    for i, t in enumerate(dialogue):
        if t.get('content_type') != 'image':
            continue
        if normalize_image_ref(t.get('image_inline', '')) == norm_ref:
            target_idx = i
            break
    if target_idx < 0:
        return ""

    # Take window text turns in each direction, both before and after the image
    prev_lines = []
    i = target_idx - 1
    while i >= 0 and len(prev_lines) < window:
        t = dialogue[i]
        if t.get('content_type') == 'text' and t.get('content'):
            prev_lines.append(f"{t.get('role','')}: {t.get('content')}")
        i -= 1
    prev_lines.reverse()

    next_lines = []
    i = target_idx + 1
    while i < len(dialogue) and len(next_lines) < window:
        t = dialogue[i]
        if t.get('content_type') == 'text' and t.get('content'):
            next_lines.append(f"{t.get('role','')}: {t.get('content')}")
        i += 1

    text = "\n".join(prev_lines + next_lines).strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "..."
    return text


def extract_short_memory_for_image(
    session: Dict,
    image_ref: str,
    max_items: int = 3,
    max_chars: int = 360,
) -> str:
    """Select memory_points related to this image (whose image_refs match it), ordered by relevance."""
    if not session:
        return ""
    norm_ref = normalize_image_ref(image_ref)
    lines = []
    seen_ids = set()

    # First priority: non-interference memories whose image_refs match this image
    for mp in session.get('memory_points') or []:
        if mp.get('memory_source') == 'interference':
            continue
        mp_refs = {normalize_image_ref(r) for r in (mp.get('image_refs') or [])}
        if norm_ref not in mp_refs:
            continue
        mid = str(mp.get('memory_id') or '')
        if mid in seen_ids:
            continue
        seen_ids.add(mid)
        content = mp.get('memory_content') or mp.get('content') or ''
        if content:
            lines.append(f"memory_id={mid} | content={content}")
        if len(lines) >= max_items:
            break

    # Fallback: the first few non-interference memories in this session (excluding system memories to avoid generic persona descriptions)
    if not lines:
        for mp in session.get('memory_points') or []:
            src = mp.get('memory_source')
            if src in ('interference', 'system'):
                continue
            mid = str(mp.get('memory_id') or '')
            if mid in seen_ids:
                continue
            seen_ids.add(mid)
            content = mp.get('memory_content') or mp.get('content') or ''
            if content:
                lines.append(f"memory_id={mid} | content={content}")
            if len(lines) >= max_items:
                break

    text = "\n".join(lines).strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "..."
    return text


def ensure_visual_structured_evidence(
    question: Dict,
    selected_images: List[str],
    image_info_by_ref: Optional[Dict[str, Dict]],
    image_session_map: Optional[Dict[str, List[Dict]]] = None,
    output_language: str = 'zh',
):
    if question.get('question_type') != 'visual_reasoning':
        return

    normalized_images = []
    seen = set()
    for image_ref in selected_images or []:
        normalized = normalize_image_ref(image_ref)
        if normalized and normalized not in seen:
            normalized_images.append(normalized)
            seen.add(normalized)

    evidence = []
    seen_dialogue_excerpt = set()  # Multiple group_chat crops share the same session dialogue; deduplicate to avoid repetition
    for image_ref in normalized_images:
        image_record = (image_info_by_ref or {}).get(image_ref)
        event_id = None
        if image_record is not None:
            event_id = image_record.get('event_id')
            if event_id in (None, ''):
                event_id = image_record.get('sub_event_id')

        session_id = None
        session_obj = None
        if image_session_map:
            candidates = image_session_map.get(image_ref) or []
            if candidates:
                session_id = candidates[0].get('session_id')
                session_obj = candidates[0].get('session')

        base_explanation = build_visual_image_explanation(image_record, output_language)

        # Collect related dialogue and related memories for the explanation.context subfield
        dialogue_excerpt = ""
        memory_excerpt = ""
        if session_obj is not None:
            dialogue_excerpt = extract_short_dialogue_around_image(session_obj, image_ref)
            memory_excerpt = extract_short_memory_for_image(session_obj, image_ref)
        # Multiple images in the same session (such as multiple group chat crops) yield the same dialogue excerpt; deduplicate and keep the first occurrence
        if dialogue_excerpt:
            if dialogue_excerpt in seen_dialogue_excerpt:
                dialogue_excerpt = ""
            else:
                seen_dialogue_excerpt.add(dialogue_excerpt)

        context_parts = []
        if dialogue_excerpt:
            context_parts.append("【相关对话】\n" + dialogue_excerpt)
        if memory_excerpt:
            context_parts.append("【相关记忆】\n" + memory_excerpt)
        context_explanation = "\n\n".join(context_parts) if context_parts else ""

        # Split explanation internally into two subfields: image=image generation information, context=related dialogue and memories
        explanation = {
            "image": base_explanation,
            "context": context_explanation,
        }

        evidence.append(
            {
                "event_id": event_id,
                "session_id": session_id,
                "image_path": image_ref,
                "explanation": explanation,
            }
        )

    question['evidence'] = evidence


def extract_bound_image_refs(question: Dict, selected_images: List[str]) -> List[str]:
    allowed_refs = [normalize_image_ref(image_ref) for image_ref in selected_images if normalize_image_ref(image_ref)]
    allowed_ref_set = set(allowed_refs)
    raw_bound_refs = question.get('bound_image_refs')

    bound_refs = []
    if isinstance(raw_bound_refs, list):
        for item in raw_bound_refs:
            normalized = normalize_image_ref(item)
            if normalized and normalized in allowed_ref_set and normalized not in bound_refs:
                bound_refs.append(normalized)

    if bound_refs:
        return bound_refs
    return allowed_refs


def expand_group_chat_cropped_in_refs(
    image_refs: List[str],
    image_info_by_ref: Optional[Dict[str, Dict]],
) -> List[str]:
    """For group_chat images in image_refs, automatically add all cropped images with the same
    (uuid, sub_event_id), so the evidence/explanation covers the entire chat content.

    - Applies only to images with type==group_chat; other types remain unchanged
    - Searches across sessions in the global image_info_by_ref
    - Preserves the original order and removes duplicates
    """
    if not image_info_by_ref or not image_refs:
        return list(image_refs)

    anchor_keys = []
    seen_keys = set()
    for ref in image_refs:
        rec = image_info_by_ref.get(normalize_image_ref(ref))
        if not rec or rec.get('type') != 'group_chat':
            continue
        key = (rec.get('uuid'), str(rec.get('sub_event_id', '')))
        if key not in seen_keys:
            seen_keys.add(key)
            anchor_keys.append(key)

    if not anchor_keys:
        return list(image_refs)

    expanded = []
    seen_refs = set()
    for ref in image_refs:
        norm = normalize_image_ref(ref)
        if norm and norm not in seen_refs:
            seen_refs.add(norm)
            expanded.append(norm)
    for ref, rec in image_info_by_ref.items():
        if rec.get('type') != 'group_chat':
            continue
        key = (rec.get('uuid'), str(rec.get('sub_event_id', '')))
        if key in seen_keys and ref not in seen_refs:
            seen_refs.add(ref)
            expanded.append(ref)
    return expanded


# Visual type terms in the question stem -> image types that must be matched
_VISUAL_TYPE_KEYWORDS_RULES = [
    (re.compile(r"视频(?:页|页面|截图)?|弹幕|播放量|UP主|上传者|video", re.IGNORECASE), {"video"}),
    (re.compile(r"群聊|群里|聊天截图|群消息|群截图"), {"group_chat", "group_chat_member"}),
    (re.compile(r"朋友圈|这条动态|发的动态"), {"friend"}),
    (re.compile(r"购物页|订单页|订单截图|商品页|店铺页"), {"shopping"}),
    (re.compile(r"读书页|阅读页|阅读页面|书页"), {"book"}),
    (re.compile(r"音乐页|这首歌|歌曲页|歌名|歌词"), {"music"}),
    (re.compile(r"头像"), {"group_chat_member"}),
    (re.compile(r"车票|高铁票|登机牌"), {"ticket"}),
    (re.compile(r"转账(?:页|截图)?|收款(?:页|截图)?|付款(?:页|截图)?"), {"money"}),
]


def question_required_image_types(question_text: str) -> set:
    """Infer the image types that must be matched from the question stem. Return an empty set when no type can be inferred (no strict constraint)."""
    if not isinstance(question_text, str) or not question_text:
        return set()
    required = set()
    for pat, types in _VISUAL_TYPE_KEYWORDS_RULES:
        if pat.search(question_text):
            required.update(types)
    return required


def visual_question_image_types_match(
    question: Dict,
    image_info_by_ref: Optional[Dict[str, Dict]],
) -> bool:
    """Check whether the types of the bound images for a visual_reasoning question match the visual types mentioned in the question stem."""
    if not image_info_by_ref:
        return True
    required = question_required_image_types(question.get("question") or "")
    if not required:
        return True
    bound_types = set()
    for ref in (question.get("image_refs") or []):
        rec = image_info_by_ref.get(normalize_image_ref(ref))
        if rec and rec.get("type"):
            bound_types.add(rec.get("type"))
    return bool(required & bound_types)


def collect_visual_sources_for_images(
    image_refs: List[str],
    image_session_map: Dict[str, List[Dict]],
) -> Dict[str, List]:
    session_ids = []
    event_ids = []
    seen_sessions = set()
    seen_events = set()

    for image_ref in image_refs:
        for item in image_session_map.get(normalize_image_ref(image_ref), []) or []:
            session_id = str(item.get('session_id', '')).strip()
            event_id = item.get('event_id')
            if session_id and session_id not in seen_sessions:
                seen_sessions.add(session_id)
                session_ids.append(session_id)
            if event_id not in (None, ''):
                event_key = str(event_id)
                if event_key not in seen_events:
                    seen_events.add(event_key)
                    event_ids.append(event_id)

    return {
        'source_session_ids': session_ids,
        'source_event_ids': event_ids,
    }


def select_evidence_image_path(session: Optional[Dict], question_image_refs: List[str]) -> Optional[str]:
    if not session:
        return question_image_refs[0] if question_image_refs else None

    session_refs = collect_session_image_refs(session)
    session_ref_set = set(session_refs)
    for image_ref in question_image_refs:
        if image_ref in session_ref_set:
            return image_ref

    if question_image_refs:
        return question_image_refs[0]
    if session_refs:
        return session_refs[0]
    return None


def extract_dialogue_turn_ids_for_image(session: Optional[Dict], image_path: Optional[str]) -> List[int]:
    if not session or not image_path:
        return []

    target = normalize_image_ref(image_path)
    turn_ids = []
    for turn in session.get('dialogue', []) or []:
        if turn.get('content_type') != 'image':
            continue
        if normalize_image_ref(turn.get('image_inline', '')) != target:
            continue
        turn_id = turn.get('turn')
        if isinstance(turn_id, int):
            turn_ids.append(turn_id)
    return turn_ids


def ensure_structured_evidence(
    question: Dict,
    sessions_by_id: Dict[str, Dict],
    sessions_by_event: Dict[str, List[Dict]],
):
    if question.get('question_type') == 'abstention':
        question['evidence'] = []
        return

    question_image_refs = extract_question_image_refs(question)
    explanations = extract_evidence_explanations(question)
    source_session_ids = [str(x) for x in (question.get('source_session_ids') or []) if str(x).strip()]
    source_event_ids = list(question.get('source_event_ids') or [])
    requires_image = question.get('question_type') == 'visual_reasoning'

    evidence = []
    seen = set()

    def append_evidence(session: Optional[Dict], event_id_value, explanation: str = ""):
        session_id_value = session.get('session_id') if session else None
        image_path = select_evidence_image_path(session, question_image_refs) if requires_image else None
        key = (str(event_id_value), str(session_id_value), str(image_path), explanation)
        if key in seen:
            return
        seen.add(key)
        evidence.append(
            {
                "event_id": event_id_value,
                "session_id": session_id_value,
                "image_path": image_path,
                "explanation": explanation,
            }
        )

    if explanations:
        if source_session_ids:
            for idx, explanation in enumerate(explanations):
                session_id = source_session_ids[min(idx, len(source_session_ids) - 1)]
                session = sessions_by_id.get(session_id)
                if session:
                    append_evidence(session, session.get('event_id'), explanation)
        elif source_event_ids:
            for idx, explanation in enumerate(explanations):
                event_id = source_event_ids[min(idx, len(source_event_ids) - 1)]
                matched_sessions = sessions_by_event.get(str(event_id), [])
                if matched_sessions:
                    append_evidence(matched_sessions[0], event_id, explanation)
                else:
                    append_evidence(None, event_id, explanation)

    if not evidence and source_session_ids:
        for session_id in source_session_ids:
            session = sessions_by_id.get(session_id)
            if not session:
                continue
            append_evidence(session, session.get('event_id'))

    if not evidence and source_event_ids:
        for event_id in source_event_ids:
            matched_sessions = sessions_by_event.get(str(event_id), [])
            if matched_sessions:
                append_evidence(matched_sessions[0], event_id)
            else:
                append_evidence(None, event_id)

    question['evidence'] = evidence


def count_multiple_choice(questions: List[Dict]) -> int:
    return sum(1 for question in questions if question.get('question_format') == 'multiple_choice')


def build_batch_format_instruction(
    question_type: str,
    total_target_count: int,
    generated_questions: List[Dict],
    batch_size: int,
) -> str:
    ratio = MULTIPLE_CHOICE_TARGET_RATIOS.get(question_type, 0.0)
    if batch_size <= 0:
        return ""

    target_mc_total = int(round(total_target_count * ratio))
    current_mc = count_multiple_choice(generated_questions)
    remaining_slots = max(0, total_target_count - len(generated_questions))
    remaining_mc = max(0, target_mc_total - current_mc)
    batch_mc = min(batch_size, remaining_mc)

    if remaining_slots > 0 and batch_mc == 0 and remaining_mc > 0:
        batch_mc = 1

    batch_oe = max(0, batch_size - batch_mc)
    return (
        "\n## Batch Question-Format Quota\n"
        f"- For this batch of `{question_type}`, generate exactly {batch_mc} `multiple_choice` questions and {batch_oe} `open_ended` questions.\n"
        "- Treat this batch quota as a hard requirement.\n"
    )


def read_jsonl(path: str) -> List[Dict]:
    if not os.path.exists(path):
        return []
    with jsonlines.open(path, 'r') as reader:
        return list(reader)


def write_jsonl(records: List[Dict], path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with jsonlines.open(path, 'w') as writer:
        for record in records:
            writer.write(record)


def load_prompt(path: str) -> str:
    with open(path, 'r', encoding='utf-8') as file:
        return file.read()


def is_chinese_persona(language: str = "", nationality: str = "") -> bool:
    language_normalized = (language or "").strip().lower()
    nationality_normalized = (nationality or "").strip().lower()
    return language_normalized == "zh" or nationality_normalized in {"chinese", "china", "中国", "中国人"}


def load_stage6_prompt(prompts_dir: str, base_name: str, language: str = "", nationality: str = "") -> str:
    suffix = "zh" if is_chinese_persona(language, nationality) else "en"
    localized_path = os.path.join(prompts_dir, f"{base_name}_{suffix}.txt")
    default_path = os.path.join(prompts_dir, f"{base_name}.txt")
    prompt_path = localized_path if os.path.exists(localized_path) else default_path
    return load_prompt(prompt_path)


def get_all_memories(sessions: List[Dict]) -> List[Dict]:
    memories = []
    for session in sessions:
        for memory_point in session.get('memory_points', []):
            if memory_point.get('memory_source') != 'interference':
                memories.append(memory_point)
    return memories


def get_update_memories(sessions: List[Dict]) -> List[Dict]:
    return [
        memory_point
        for session in sessions
        for memory_point in session.get('memory_points', [])
        if memory_point.get('is_update') is True
        and memory_point.get('memory_source') != 'interference'
    ]


def get_visual_sessions(sessions: List[Dict]) -> List[Dict]:
    return [
        session
        for session in sessions
        if extract_multi_visual_context(session) is not None
    ]


def extract_multi_visual_context(session: Dict) -> Optional[Dict]:
    dialogue = session.get('dialogue', []) or []
    visual_items = []

    for idx, turn in enumerate(dialogue):
        if turn.get('content_type') != 'image':
            continue
        image_inline = turn.get('image_inline')
        if not image_inline:
            continue
        # Skip person images (user portraits/full-body images): they are not covered by the upstream stage10 index and are unsuitable as question subjects
        if is_person_avatar_image(image_inline):
            continue

        prev_text = ""
        for prev_idx in range(idx - 1, -1, -1):
            prev_turn = dialogue[prev_idx]
            if prev_turn.get('content_type') == 'text' and prev_turn.get('content'):
                prev_text = prev_turn.get('content', '')
                break

        visual_items.append(
            {
                "image_inline": image_inline,
                "preceding_text": prev_text,
                "turn": turn.get('turn', ''),
                "role": turn.get('role', 'unknown'),
            }
        )

    deduped = []
    seen_images = set()
    for item in visual_items:
        image_inline = item["image_inline"]
        if image_inline in seen_images:
            continue
        seen_images.add(image_inline)
        deduped.append(item)

    # Prefer images that were explicitly sent in dialogue, then backfill from
    # session-level image candidates so more uid images can participate in
    # multi-visual questions.
    image_candidates = session.get('image_candidates') or []
    if isinstance(image_candidates, list):
        for image_inline in image_candidates:
            image_inline = str(image_inline or '').strip().replace('\\', '/')
            if not image_inline or image_inline in seen_images:
                continue
            # Skip person images (same reason as above)
            if is_person_avatar_image(image_inline):
                continue
            seen_images.add(image_inline)
            deduped.append(
                {
                    "image_inline": image_inline,
                    "preceding_text": "",
                    "turn": "",
                    "role": "candidate",
                }
            )

    if len(deduped) < 2:
        return None

    return {
        "selected_visual_turns": deduped[:6],
    }


def format_selected_visual_inputs(
    visual_items: List[Dict],
    image_info_by_ref: Optional[Dict[str, Dict]] = None,
) -> str:
    lines = []
    for idx, item in enumerate(visual_items, start=1):
        image_inline = item.get('image_inline', '')
        image_type = infer_image_type(image_inline, image_info_by_ref)
        lines.append(f"Image {idx}")
        lines.append(f"File: {image_inline}")
        if image_type:
            lines.append(f"Image Type: {image_type}")
        lines.append(
            f"Preceding Text Context: {item.get('preceding_text', '') or '(no preceding text)'}"
        )
        lines.append("")
    return "\n".join(lines).strip()


def is_person_avatar_image(image_inline: str) -> bool:
    image_inline = str(image_inline or '').replace('\\', '/').lower()
    return '/person/' in image_inline


def select_available_visual_bundle(
    visual_items: List[Dict],
    image_usage_count: Dict[str, int],
    max_usage_per_image: int,
    image_info_by_ref: Optional[Dict[str, Dict]] = None,
) -> List[Dict]:
    available_items = [
        item
        for item in visual_items
        if image_usage_count.get(item.get('image_inline', ''), 0) < max_usage_per_image
    ]
    if len(available_items) < 2:
        return []

    type_groups = {}
    for idx, item in enumerate(available_items):
        image_type = infer_image_type(item.get('image_inline', ''), image_info_by_ref)
        type_groups.setdefault(image_type, []).append((idx, item))

    comparable_groups = [
        group
        for group in type_groups.values()
        if len(group) >= 2 and group[0][1].get('image_inline')
    ]
    if comparable_groups:
        best_group = min(
            comparable_groups,
            key=lambda group: sum(
                image_usage_count.get(item.get('image_inline', ''), 0)
                for _idx, item in group[:2]
            ),
        )
        prioritized_group = sorted(
            best_group,
            key=lambda pair: (
                image_usage_count.get(pair[1].get('image_inline', ''), 0),
                pair[0],
            ),
        )
        return [item for _idx, item in prioritized_group[:2]]

    prioritized = sorted(
        enumerate(available_items),
        key=lambda pair: (
            image_usage_count.get(pair[1].get('image_inline', ''), 0),
            is_person_avatar_image(pair[1].get('image_inline', '')),
            pair[0],
        ),
    )
    if not prioritized:
        return []
    return [prioritized[0][1]]


def format_dialogue(dialogue: List[Dict]) -> str:
    lines = []
    for turn in dialogue:
        if turn.get('content_type') == 'image':
            continue
        role = turn.get('role', 'unknown')
        content = turn.get('content', '')
        if content:
            lines.append(f"- {role}: {content}")
    return "\n".join(lines)


def format_visual_turns(dialogue: List[Dict]) -> str:
    lines = []
    for turn in dialogue:
        if turn.get('content_type') != 'image':
            continue
        role = turn.get('role', 'unknown')
        image_inline = turn.get('image_inline')
        if image_inline:
            lines.append(
                f"- turn={turn.get('turn', '')} | role={role} | image_inline={image_inline}"
            )
    return "\n".join(lines)


def format_memory_points(memory_points: List[Dict]) -> str:
    lines = []
    for memory_point in memory_points:
        if memory_point.get('memory_source') == 'interference':
            continue
        lines.append(
            f"- memory_id={memory_point.get('memory_id', '')} | "
            f"source={memory_point.get('memory_source', '')} | "
            f"type={memory_point.get('memory_type', '')} | "
            f"timestamp={memory_point.get('timestamp', '')} | "
            f"is_update={memory_point.get('is_update', False)} | "
            f"content={memory_point.get('memory_content', '')} | "
            f"image_refs={memory_point.get('image_refs', [])}"
        )
    return "\n".join(lines)


def build_sessions_info(sessions: List[Dict]) -> str:
    lines = []
    for session in sessions:
        memory_points = [
            memory_point
            for memory_point in session.get('memory_points', [])
            if memory_point.get('memory_source') != 'interference'
        ]
        lines.append(f"## Session {session.get('session_id', '')}: {session.get('event_name', '')}")
        lines.append(f"Event ID: {session.get('event_id', '')}")
        lines.append(
            f"Time: {session.get('event_start_time', '')} - {session.get('event_end_time', '')}"
        )
        lines.append(f"Summary: {session.get('dialogue_summary', '')}")
        lines.append(
            f"Image Refs: {json.dumps(session.get('image_refs', {}), ensure_ascii=False)}"
        )
        lines.append("Dialogue:")
        lines.append(format_dialogue(session.get('dialogue', [])) or "- None")
        lines.append("Visual Evidence Turns:")
        lines.append(format_visual_turns(session.get('dialogue', [])) or "- None")
        lines.append("Memory Points:")
        lines.append(format_memory_points(memory_points) or "- None")
        lines.append("")
    return "\n".join(lines)


def build_update_memories_info_from_list(update_memories: List[Dict]) -> str:
    if not update_memories:
        return "None"
    return format_memory_points(update_memories)


def get_rotating_session_chunk(
    sessions: List[Dict],
    batch_num: int,
    chunk_size: int = SESSION_CHUNK_SIZE,
) -> List[Dict]:
    if not sessions:
        return []
    if len(sessions) <= chunk_size:
        return sessions
    start = ((batch_num - 1) * chunk_size) % len(sessions)
    end = start + chunk_size
    if end <= len(sessions):
        return sessions[start:end]
    return sessions[start:] + sessions[:end - len(sessions)]


def get_covering_chunk_size(total_sessions: int, target_count: int) -> int:
    if total_sessions <= 0:
        return SESSION_CHUNK_SIZE
    planned_batches = max(1, (target_count + BATCH_SIZE - 1) // BATCH_SIZE)
    return max(1, (total_sessions + planned_batches - 1) // planned_batches)


def resolve_session_chunk_size(
    total_sessions: int,
    target_count: int,
    session_chunk_size: Optional[int] = None,
) -> int:
    if session_chunk_size is not None:
        return max(1, min(session_chunk_size, total_sessions or session_chunk_size))
    return get_covering_chunk_size(total_sessions, target_count)


def get_update_memories_for_sessions(sessions: List[Dict]) -> List[Dict]:
    return [
        memory_point
        for session in sessions
        for memory_point in session.get('memory_points', [])
        if memory_point.get('is_update') is True
        and memory_point.get('memory_source') != 'interference'
    ]


def detect_output_language(nationality: str = "", language: str = "") -> str:
    if is_chinese_persona(language, nationality):
        return "zh"
    return "en"


def normalize_question_language_fields(
    question: Dict,
    output_language: str,
    fallback_answer_zh: str = "",
    fallback_answer_en: str = "",
):
    question_text = question.get('question') or ""
    answer_text = question.get('answer') or ""

    if output_language == "zh":
        question_text = question_text or question.get('question_zh') or question.get('question_en') or ""
        answer_text = answer_text or question.get('answer_zh') or question.get('answer_en') or fallback_answer_zh
    else:
        question_text = question_text or question.get('question_en') or ""
        answer_text = answer_text or question.get('answer_en') or fallback_answer_en

    question['question'] = question_text
    question['answer'] = answer_text
    question.pop('question_zh', None)
    question.pop('question_en', None)
    question.pop('answer_zh', None)
    question.pop('answer_en', None)


def contains_cjk(text: str) -> bool:
    if not isinstance(text, str):
        return False
    return bool(re.search(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]', text))


def strip_translation_wrapper(text: str) -> str:
    text = str(text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:text|json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    if (
        len(text) >= 2
        and ((text[0] == text[-1] == '"') or (text[0] == text[-1] == "'"))
    ):
        text = text[1:-1].strip()
    return text


def translate_cjk_to_english_text(text: str) -> str:
    if not contains_cjk(text):
        return text

    with ENGLISH_CJK_TRANSLATION_LOCK:
        cached = ENGLISH_CJK_TRANSLATION_CACHE.get(text)
    if cached is not None:
        return cached

    prompt = (
        "Translate every Chinese/CJK fragment in the following string into natural English.\n"
        "Preserve existing English text, numbers, timestamps, IDs, image/file paths, JSON-like syntax, punctuation, "
        "speaker names, and all facts. Do not summarize, expand, add facts, delete facts, or change the meaning.\n"
        "Return only the translated string, with zero Chinese/CJK characters and no markdown.\n\n"
        f"String:\n{text}"
    )
    try:
        translated, _cost_info = llm_request(
            system_prompt=(
                "You are a precise bilingual data-cleaning translator. "
                "Only translate Chinese/CJK fragments into English."
            ),
            user_prompt=prompt,
            model=ENGLISH_CJK_TRANSLATION_MODEL,
            max_tokens=max(256, min(8192, len(text) * 3 + 256)),
            temperature=0.0,
            timeout=300,
            extract_json=False,
        )
        translated = strip_translation_wrapper(translated)
        if not translated:
            logger.warning("English CJK translation returned empty text; keeping original.")
            return text
        if contains_cjk(translated):
            logger.warning("English CJK translation still contains CJK; keeping original for final filter.")
            return text
        with ENGLISH_CJK_TRANSLATION_LOCK:
            ENGLISH_CJK_TRANSLATION_CACHE[text] = translated
        return translated
    except Exception as exc:
        logger.warning(f"English CJK translation failed; keeping original. error={exc}")
        return text


def translate_cjk_to_english_in_obj(obj: Any) -> Any:
    if isinstance(obj, str):
        return translate_cjk_to_english_text(obj)
    if isinstance(obj, list):
        return [translate_cjk_to_english_in_obj(item) for item in obj]
    if isinstance(obj, dict):
        return {
            key: translate_cjk_to_english_in_obj(value)
            for key, value in obj.items()
        }
    return obj


def object_contains_cjk(obj: Any) -> bool:
    if isinstance(obj, str):
        return contains_cjk(obj)
    if isinstance(obj, list):
        return any(object_contains_cjk(item) for item in obj)
    if isinstance(obj, dict):
        return any(object_contains_cjk(value) for value in obj.values())
    return False


def is_question_language_clean(question: Dict, output_language: str) -> bool:
    if output_language != 'en':
        return True

    return not object_contains_cjk(question)


def filter_questions_by_output_language(
    questions: List[Dict],
    output_language: str,
    uuid,
    question_type: str,
    batch_num: int,
) -> List[Dict]:
    # First filter out questions marked invalid during normalization (for example, when the LLM mislabels a multiple-choice question as open_ended and the answer contains all six options)
    invalid_dropped = []
    cleaned = []
    for q in questions:
        reason = q.get('_invalid')
        if reason:
            invalid_dropped.append(reason)
            continue
        cleaned.append(q)
    if invalid_dropped:
        from collections import Counter as _Counter
        reason_counter = _Counter(invalid_dropped)
        for reason, n in reason_counter.most_common():
            logger.info(
                f"[uuid={uuid}] [{question_type}] batch {batch_num}: dropped {n} invalid questions ({reason})"
            )
    questions = cleaned

    if output_language != 'en':
        return questions

    translated_questions = []
    translated_count = 0
    for question in questions:
        if object_contains_cjk(question):
            translated_count += 1
            question = translate_cjk_to_english_in_obj(question)
        translated_questions.append(question)
    if translated_count:
        logger.info(
            f"[uuid={uuid}] [{question_type}] batch {batch_num}: translated {translated_count} mixed-language questions"
        )

    kept = [
        question
        for question in translated_questions
        if is_question_language_clean(question, output_language)
    ]
    dropped = len(translated_questions) - len(kept)
    if dropped:
        logger.info(
            f"[uuid={uuid}] [{question_type}] batch {batch_num}: dropped {dropped} still-mixed questions after translation"
        )
    return kept


def normalize_question_format_fields(question: Dict):
    question_format = (question.get('question_format') or 'open_ended').strip().lower()
    if question_format in {'open', 'open-ended', 'open ended'}:
        question_format = 'open_ended'
    elif question_format in {'boolean', 'judgment', 'truefalse', 'true_false'}:
        question_format = 'open_ended'
    elif question_format in {'mcq', 'multiple-choice', 'multiple_choice'}:
        question_format = 'multiple_choice'
    else:
        question_format = 'open_ended'
    question['question_format'] = question_format

    # Whether options is retained is determined by normalize_multiple_choice_fields / normalize_disallowed_question_forms /
    # normalize_abstention_fields; do not forcibly write [] here, to avoid overwriting the LLM's original output.


def normalize_disallowed_question_forms(question: Dict):
    question_text = str(question.get('question') or "").strip()
    if question_text.startswith('判断对错：'):
        question['question'] = question_text[len('判断对错：'):].strip()

    if question.get('question_format') == 'open_ended':
        # Detect cases where the LLM mislabels a multiple-choice question as open_ended:
        # the answer text itself has the form "A. ...\nB. ...\n...\nF. ...", containing >=2 A-F options.
        # Because the position of the correct answer intended by the LLM cannot be determined, mark it invalid so the outer filter discards it.
        ans = str(question.get('answer') or '').strip()
        if ans:
            ans_options = re.findall(r'(?:^|\n)\s*([A-F])[\.\)：:]\s*(.+?)(?=\n\s*[A-F][\.\)：:]|\Z)',
                                     ans, flags=re.S)
            if len(ans_options) >= 2:
                question['_invalid'] = 'open_ended_answer_contains_multiple_choice_options'
        question.pop('options', None)
        rewrite_open_ended_mc_phrasing(question)


# Applies only to open_ended questions: rewrite phrases in the question stem that "look like multiple choice" as neutral questions,
# avoiding cases where question_format=open_ended but the question stem still says "which of the following / which option ...".
# Do not modify answer / options; rewrite only the question text.
_OPEN_ENDED_MC_PHRASE_REWRITES_ZH = [
    ("下面哪一项", "哪个"),
    ("下列哪一项", "哪个"),
    ("以下哪一项", "哪个"),
    ("下面哪一个", "哪个"),
    ("下列哪一个", "哪个"),
    ("以下哪一个", "哪个"),
    ("下面哪个", "哪个"),
    ("下列哪个", "哪个"),
    ("以下哪个", "哪个"),
    ("下面哪些", "哪些"),
    ("下列哪些", "哪些"),
    ("以下哪些", "哪些"),
    ("下面选项", "其中"),
    ("下列选项", "其中"),
    ("以下选项", "其中"),
    ("选项中", "其中"),
    ("下面说法", "说法"),
    ("下列说法", "说法"),
    ("以下说法", "说法"),
    ("下面描述", "描述"),
    ("下列描述", "描述"),
    ("以下描述", "描述"),
    ("下面表述", "表述"),
    ("下列表述", "表述"),
    ("以下表述", "表述"),
    ("选出最符合", "最符合"),
    ("选出最", "最"),
    ("哪一项", "哪个"),
    ("哪一个", "哪个"),
]
_OPEN_ENDED_MC_PHRASE_REWRITES_EN = [
    (re.compile(r"which of the following", re.IGNORECASE), "which"),
    (re.compile(r"which one of\b", re.IGNORECASE), "which"),
    (re.compile(r"which option\b", re.IGNORECASE), "which"),
    (re.compile(r"\bbest matches\b", re.IGNORECASE), "most accurately matches"),
    (re.compile(r"\bbest describes\b", re.IGNORECASE), "most accurately describes"),
    (re.compile(r"\bbest captures\b", re.IGNORECASE), "most accurately captures"),
    (re.compile(r"\bbest fits\b", re.IGNORECASE), "most accurately fits"),
]


def rewrite_open_ended_mc_phrasing(question: Dict):
    text = question.get('question')
    if not isinstance(text, str) or not text:
        return
    new_text = text
    for src, dst in _OPEN_ENDED_MC_PHRASE_REWRITES_ZH:
        if src in new_text:
            new_text = new_text.replace(src, dst)
    for pattern, dst in _OPEN_ENDED_MC_PHRASE_REWRITES_EN:
        new_text = pattern.sub(dst, new_text)
    if new_text != text:
        question['question'] = new_text


def _strip_inline_mc_options_from_stem(stem: str) -> str:
    """Strip A-F option lines/strings already embedded in the question stem to avoid duplicating the options_block appended at the end.

    Supports two embedded forms:
      1. Spread across several separate lines, each starting with `A./B./.../F.`
      2. All compressed into a single line ("A. xxx B. yyy C. zzz ...")
    """
    if not isinstance(stem, str) or not stem:
        return stem or ""

    # Form 1: strip separate lines that start with A-F
    lines = stem.splitlines()
    cleaned = []
    for ln in lines:
        if re.match(r'^[A-F][\.\)：:]\s*\S', ln.strip()):
            continue
        cleaned.append(ln)
    text = "\n".join(cleaned).rstrip()

    # Form 2: strip an embedded sequence of consecutive A-F options on the same line
    # Match an entire segment such as "(any A. ...) (B. ...) (C. ...) (D. ...) (E. ...) (F. ...)"
    inline_pat = re.compile(
        r'\s*A[\.\)：:]\s*[^A-F]+?\s+B[\.\)：:]\s*[^A-F]+?\s+C[\.\)：:]\s*[^A-F]+?\s+'
        r'D[\.\)：:]\s*[^A-F]+?\s+E[\.\)：:]\s*[^A-F]+?\s+F[\.\)：:]\s*.+$'
    )
    text = inline_pat.sub('', text).rstrip()
    return text


def normalize_multiple_choice_fields(question: Dict):
    if question.get('question_format') != 'multiple_choice':
        return
    # Multiple-choice abstention questions are handled separately by normalize_abstention_fields (including "cannot answer" semantic alignment and concatenation logic)
    if question.get('question_type') == 'abstention':
        return

    raw_options = question.get('options')
    if not isinstance(raw_options, list):
        raw_options = []

    labels = ['A', 'B', 'C', 'D', 'E', 'F']
    normalized_options = []
    for idx, option in enumerate(raw_options[:6]):
        text = str(option or "").strip()
        text = re.sub(r'^[A-F][\.\)：:\s]+', '', text)
        normalized_options.append(f"{labels[idx]}. {text}")

    if len(normalized_options) != 6:
        question['question_format'] = 'open_ended'
        question.pop('options', None)
        return

    answer_text = str(question.get('answer') or "").strip()
    answer_text_stripped = re.sub(r'^[A-F][\.\)：:\s]+', '', answer_text)

    matched_option = None
    for option in normalized_options:
        option_body = re.sub(r'^[A-F][\.\)：:\s]+', '', option).strip()
        if answer_text == option or answer_text_stripped == option_body:
            matched_option = option
            break

    if not matched_option:
        question['question_format'] = 'open_ended'
        question.pop('options', None)
        return

    question['answer'] = matched_option

    # Append the six options to the end of the question text and remove the options field
    stem = str(question.get('question') or '').rstrip()
    stem = _strip_inline_mc_options_from_stem(stem)
    options_block = "\n".join(normalized_options)
    if options_block not in stem:
        question['question'] = (stem + "\n" + options_block) if stem else options_block
    question.pop('options', None)


def normalize_abstention_fields(question: Dict, output_language: str):
    if question.get('question_type') != 'abstention':
        return

    abstain_zh = '根据现有对话和记忆，无法回答这个问题。'
    abstain_en = 'This information is not available in the memory.'
    target_label = abstain_zh if output_language == 'zh' else abstain_en

    # Multiple-choice abstention: retain the multiple-choice format, but one option must convey "cannot answer"
    if question.get('question_format') == 'multiple_choice':
        raw_options = question.get('options')
        if not isinstance(raw_options, list):
            raw_options = []
        # Normalize: remove prefixes and add A./B./C./D./E./F. labels
        labels = ['A', 'B', 'C', 'D', 'E', 'F']
        normalized_options = []
        for idx, option in enumerate(raw_options[:6]):
            text = str(option or "").strip()
            text = re.sub(r'^[A-F][\.\)：:\s]+', '', text)
            normalized_options.append(f"{labels[idx]}. {text}")

        if len(normalized_options) != 6:
            # Fewer than six options -> downgrade to open_ended
            question['question_format'] = 'open_ended'
        else:
            opt_bodies = [
                re.sub(r'^[A-F][\.\)：:\s]+', '', opt).strip()
                for opt in normalized_options
            ]
            has_abstain_option = any(
                ('无法回答' in body) or ('not available' in body.lower())
                for body in opt_bodies
            )
            if has_abstain_option:
                # Align answer: it must point to the option containing "cannot answer"
                for opt, body in zip(normalized_options, opt_bodies):
                    if ('无法回答' in body) or ('not available' in body.lower()):
                        question['answer'] = opt
                        break
                # Append the options to the end of question (consistent with the visual multiple-choice format)
                stem = str(question.get('question') or '').rstrip()
                stem = _strip_inline_mc_options_from_stem(stem)
                options_block = "\n".join(normalized_options)
                if options_block not in stem:
                    question['question'] = (stem + "\n" + options_block) if stem else options_block
                # Delete the options field and clear evidence/image
                question.pop('options', None)
                question['evidence'] = []
                question['image_refs'] = []
                question['source_session_ids'] = []
                question['source_event_ids'] = []
                return
            # No "cannot answer" option -> downgrade to open_ended and follow the default logic
            question['question_format'] = 'open_ended'

    question['question_format'] = 'open_ended'
    question.pop('options', None)
    question['evidence'] = []
    question['image_refs'] = []
    question['source_session_ids'] = []
    question['source_event_ids'] = []

    answer_text = str(question.get('answer') or "").strip()
    # The answer to an open_ended abstention question must be the standard abstention text;
    # if the original answer contains an option prefix or other guessed content (after a multiple-choice downgrade), forcibly reset it
    if (
        not answer_text
        or answer_text.startswith(('A.', 'B.', 'C.', 'D.', 'E.', 'F.'))
        or ("无法回答" not in answer_text and "not available" not in answer_text.lower())
    ):
        answer_text = target_label
    question['answer'] = answer_text


def is_true_false_question_text(question_text: str, output_language: str) -> bool:
    text = str(question_text or "").strip().lower()
    if not text:
        return False

    if output_language == 'zh':
        return (
            text.startswith('是否')
            or text.startswith('有没有')
            or text.startswith('是不是')
            or text.startswith('能否')
            or text.startswith('可否')
            or text.startswith('会不会')
            or text.startswith('能不能')
            or '是否' in text
            or '有没有' in text
            or '是不是' in text
            or '能否' in text
            or '可否' in text
            or '会不会' in text
            or '吗？' in text
            or '吗?' in text
        )

    return (
        text.startswith('is ')
        or text.startswith('are ')
        or text.startswith('was ')
        or text.startswith('were ')
        or text.startswith('do ')
        or text.startswith('does ')
        or text.startswith('did ')
        or text.startswith('can ')
        or text.startswith('could ')
        or text.startswith('will ')
        or text.startswith('would ')
        or text.startswith('has ')
        or text.startswith('have ')
        or text.startswith('had ')
        or text.startswith('should ')
        or text.startswith('isn')
        or text.startswith('aren')
        or text.startswith('doesn')
        or text.startswith('didn')
        or text.startswith('hasn')
        or text.startswith('haven')
    )


def normalize_true_false_answer(question: Dict, output_language: str):
    if question.get('question_format') != 'true_false':
        return

    question_text = str(question.get('question') or "").strip()
    if not is_true_false_question_text(question_text, output_language):
        return

    answer_text = str(question.get('answer') or "").strip()
    if not answer_text:
        return

    normalized = re.sub(r'\s+', '', answer_text).casefold()

    negative_markers_zh = [
        '否', '不是', '不', '没有', '無', '无', '未', '不能', '不会', '不喜欢', '不确定',
    ]
    negative_markers_en = [
        'no', 'not', "don't", "doesn't", "didn't", "isn't", "aren't", 'never',
        "can't", 'cannot', 'false', 'without',
    ]

    is_negative = False
    if output_language == 'zh':
        is_negative = any(marker in normalized for marker in negative_markers_zh)
        question['answer'] = '否' if is_negative else '是'
    else:
        is_negative = any(marker in normalized for marker in negative_markers_en)
        question['answer'] = 'No' if is_negative else 'Yes'


def normalize_protagonist_subject(question: Dict, persona_name: str, question_type: str = ""):
    if not persona_name:
        return

    text = question.get('question')
    if not isinstance(text, str):
        return

    if question_type != 'implicit_preference':
        protagonist_you_patterns = [
            ('从你', '从我'),
            ('在你', '在我'),
            ('你在', '我在'),
            ('你和', '我和'),
            ('和你', '和我'),
            ('你的', '我的'),
            ('你自己', '我自己'),
            ('让你', '让我'),
            ('给你', '给我'),
            ('距离你', '距离我'),
            ('你又', '我又'),
            ('你先', '我先'),
            ('你是', '我是'),
            ('你把', '我把'),
            ('你会', '我会'),
            ('你更', '我更'),
        ]
        for old, new in protagonist_you_patterns:
            text = text.replace(old, new)

    subject_prefix_pattern = (
        rf'(^|[，。！？；：、\s(（]|为什么|为何|如果|假如|若|当|在|从|根据|结合|考虑到)'
        rf'{re.escape(persona_name)}(?!的)'
    )
    question['question'] = re.sub(
        subject_prefix_pattern,
        lambda match: f'{match.group(1)}我',
        text,
    )


def normalize_visual_reasoning_first_person(question: Dict):
    if question.get('question_type') != 'visual_reasoning':
        return

    text = question.get('question')
    if not isinstance(text, str) or not text:
        return

    replacements = [
        ('你们', '我们'),
        ('你的', '我的'),
        ('那次你', '那次我'),
        ('那段时间里你', '那段时间里我'),
        ('那段时间你', '那段时间我'),
        ('春节前后那段时间里你', '春节前后那段时间里我'),
        ('春节前后那段时间你', '春节前后那段时间我'),
        ('今年年初那次你', '今年年初那次我'),
        ('上半年有一次你', '上半年有一次我'),
        ('去年夏天某个晚上你', '去年夏天某个晚上我'),
        ('那次周末出门前后你', '那次周末出门前后我'),
        ('周末出门前后你', '周末出门前后我'),
        ('画面中靠近你所在一侧', '画面中靠近我所在一侧'),
        ('你回看', '我回看'),
        ('你顺手', '我顺手'),
        ('你发了一张', '我发了一张'),
        ('你有一张', '我有一张'),
        ('你随手', '我随手'),
        ('你记得', '我记得'),
        ('你看那张', '我看那张'),
        ('你看', '我看'),
        ('你仔细看', '我仔细看'),
        ('请你观察', '请观察'),
        ('请你留意', '请留意'),
        ('请你注意', '请留意'),
        ('你现在看', '现在看'),
        ('你对比一下', '请对比一下'),
    ]
    for old, new in replacements:
        text = text.replace(old, new)

    question['question'] = text


def call_llm_for_questions(prompt: str) -> List[Dict]:
    response, _cost_info = llm_request(
        "",
        prompt,
        return_parsed_json=True,
        extract_json=True,
        json_markers=["```json", "```"],
    )
    if isinstance(response, dict):
        return response.get('questions', [])
    return []


def get_question_dedup_key(question: Dict) -> str:
    text = (
        question.get('question')
        or question.get('question_zh')
        or question.get('question_en')
        or ""
    )
    return re.sub(r'\s+', ' ', text).strip().casefold()


def filter_unique_questions(
    questions: List[Dict],
    seen_question_keys: set,
    uuid: Optional[int] = None,
    question_type: str = "",
    batch_num: int = 0,
) -> List[Dict]:
    unique_questions = []
    duplicate_count = 0

    for question in questions:
        dedup_key = get_question_dedup_key(question)
        if not dedup_key:
            continue
        if dedup_key in seen_question_keys:
            duplicate_count += 1
            continue
        seen_question_keys.add(dedup_key)
        unique_questions.append(question)

    if duplicate_count:
        logger.info(
            f"[uuid={uuid}] [{question_type}] batch {batch_num}: filtered {duplicate_count} duplicate questions"
        )

    return unique_questions


def log_batch_questions(uuid: int, question_type: str, batch_num: int, questions: List[Dict]):
    for idx, question in enumerate(questions, start=1):
        preview = question.get('question') or question.get('question_zh') or question.get('question_en') or ''
        logger.info(
            f"[uuid={uuid}] [{question_type}] batch {batch_num} q{idx}/{len(questions)}: {preview}"
        )


def generate_standard_questions(
    persona: Dict,
    sessions: List[Dict],
    question_type: str,
    target_count: int,
    prompts_dir: str,
    language: str,
    session_chunk_size: Optional[int] = None,
    seen_question_keys: Optional[set] = None,
    on_batch: Optional[Callable[[List[Dict], int], None]] = None,
) -> List[Dict]:
    del language
    basic_profile = persona.get('Basic_Profile', {})
    prompt_template = load_stage6_prompt(
        prompts_dir,
        'stage6_questions',
        persona.get('language') or basic_profile.get('language') or '',
        basic_profile.get('nationality', ''),
    )
    output_language = detect_output_language(
        basic_profile.get('nationality', ''),
        persona.get('language') or basic_profile.get('language') or '',
    )
    persona_info = json.dumps(
        {
            "name": basic_profile.get('name'),
            "gender": basic_profile.get('gender'),
            "nationality": basic_profile.get('nationality'),
            "personality_traits": basic_profile.get('personality_traits', ''),
            "life_experiences": basic_profile.get('life_experiences', ''),
            "career": persona.get('Init_State', {}).get('career'),
            "location": persona.get('Init_State', {}).get('location'),
            "description": persona.get('Init_State', {}).get('description', ''),
            "preferences": persona.get('Init_State', {}).get('preferences', {}),
        },
        ensure_ascii=False,
    )
    all_questions = []
    seen_question_keys = seen_question_keys if seen_question_keys is not None else set()
    batch_num = 0
    chunk_size = resolve_session_chunk_size(len(sessions), target_count, session_chunk_size)
    max_batches = max(20, (target_count + BATCH_SIZE - 1) // BATCH_SIZE + 40)
    if MAX_BATCHES_PER_TYPE is not None:
        max_batches = max(max_batches, MAX_BATCHES_PER_TYPE)

    while len(all_questions) < target_count and batch_num < max_batches:
        remaining = target_count - len(all_questions)
        batch = min(BATCH_SIZE, remaining)
        batch_num += 1
        session_chunk = get_rotating_session_chunk(sessions, batch_num, chunk_size=chunk_size)
        sessions_by_id, sessions_by_event = build_session_indexes(session_chunk)
        sessions_info = build_sessions_info(session_chunk)
        update_memories = get_update_memories_for_sessions(session_chunk)
        if question_type == 'knowledge_update' and not update_memories:
            update_memories = get_update_memories(sessions)
        update_memories_info = build_update_memories_info_from_list(update_memories)

        prompt = prompt_template
        prompt = prompt.replace('{persona_info}', persona_info)
        prompt = prompt.replace('{sessions_info}', sessions_info)
        prompt = prompt.replace('{update_memories}', update_memories_info)
        prompt = prompt.replace('{output_language}', output_language)
        prompt = prompt.replace('{question_type}', question_type)
        prompt = prompt.replace('{question_count}', str(batch))
        prompt += build_batch_format_instruction(question_type, target_count, all_questions, batch)

        try:
            questions = call_llm_for_questions(prompt)
            if questions:
                for question in questions:
                    normalize_question_format_fields(question)
                    normalize_question_language_fields(question, output_language)
                    normalize_true_false_answer(question, output_language)
                    normalize_disallowed_question_forms(question)
                    normalize_multiple_choice_fields(question)
                    normalize_abstention_fields(question, output_language)
                    normalize_protagonist_subject(question, basic_profile.get('name', ''), question_type)
                    ensure_structured_evidence(question, sessions_by_id, sessions_by_event)
                questions = filter_questions_by_output_language(
                    questions,
                    output_language,
                    persona.get('uuid'),
                    question_type,
                    batch_num,
                )
                questions = filter_unique_questions(
                    questions,
                    seen_question_keys,
                    uuid=persona.get('uuid'),
                    question_type=question_type,
                    batch_num=batch_num,
                )
                all_questions.extend(questions)
                if on_batch:
                    on_batch(questions, batch_num)
                logger.debug(
                    f"  [{question_type}] batch {batch_num}: +{len(questions)}, total={len(all_questions)}"
                )
            else:
                logger.warning(f"  [{question_type}] batch {batch_num}: empty response")
                if batch_num > target_count // BATCH_SIZE + 5:
                    break
        except Exception as exc:
            logger.error(f"  [{question_type}] batch {batch_num} error: {exc}")
            if batch_num > target_count // BATCH_SIZE + 5:
                break

    return all_questions[:target_count]


def generate_visual_stat_questions(
    persona: Dict,
    sessions: List[Dict],
    persona_image_records: List[Dict],
    target_count: int,
    prompts_dir: str,
    image_info_by_ref: Optional[Dict[str, Dict]] = None,
    image_summary_by_ref: Optional[Dict[str, Dict]] = None,
    seen_question_keys: Optional[set] = None,
    on_batch: Optional[Callable[[List[Dict], int], None]] = None,
) -> List[Dict]:
    if target_count <= 0:
        return []

    basic_profile = persona.get('Basic_Profile', {})
    prompt_template = load_stage6_prompt(
        prompts_dir,
        'stage6_multi_visual',
        persona.get('language') or basic_profile.get('language') or '',
        basic_profile.get('nationality', ''),
    )
    output_language = detect_output_language(
        basic_profile.get('nationality', ''),
        persona.get('language') or basic_profile.get('language') or '',
    )
    persona_info = json.dumps(
        {
            "name": basic_profile.get('name'),
            "nationality": basic_profile.get('nationality'),
            "personality_traits": basic_profile.get('personality_traits', ''),
            "description": persona.get('Init_State', {}).get('description', ''),
            "preferences": persona.get('Init_State', {}).get('preferences', {}),
        },
        ensure_ascii=False,
    )
    image_session_map = build_image_session_map(sessions)

    groups = {}
    for record in persona_image_records:
        image_ref = normalize_image_ref(record.get('_normalized_image_ref') or record.get('image_path', ''))
        image_type = str(record.get('type') or '')
        if not image_ref or not image_type:
            continue
        groups.setdefault(image_type, []).append(record)

    # Per-type quota: prevent one type from consuming the entire stat quota
    default_quota = max(2, int(round(target_count * VISUAL_STAT_DEFAULT_QUOTA_RATIO)))
    per_type_quota = {
        image_type: max(2, int(round(target_count * ratio)))
        for image_type, ratio in VISUAL_STAT_PER_TYPE_QUOTA_RATIO.items()
    }

    # Exclude group chats (handled by the detail branch); split the rest into multiple groups using a six-image sliding window
    candidate_groups = []  # List[Tuple[image_type, records_chunk]]
    for image_type, records in groups.items():
        if image_type in VISUAL_STAT_EXCLUDE_TYPES:
            continue
        if len(records) < 3:
            continue
        for i in range(0, len(records), 6):
            chunk = records[i:i + 6]
            if len(chunk) >= 3:
                candidate_groups.append((image_type, chunk))
    if not candidate_groups:
        return []

    all_questions = []
    seen_question_keys = seen_question_keys if seen_question_keys is not None else set()
    batch_num = 0
    per_type_count = {}
    stat_image_usage_count = {}
    stat_max_usage_per_image = MULTI_VISUAL_MAX_USAGE_PER_IMAGE

    for image_type, group in candidate_groups:
        if len(all_questions) >= target_count:
            break

        quota_for_type = per_type_quota.get(image_type, default_quota)
        if per_type_count.get(image_type, 0) >= quota_for_type:
            continue

        selected_images = [
            normalize_image_ref(record.get('_normalized_image_ref') or record.get('image_path', ''))
            for record in group
        ]
        selected_images = [image_ref for image_ref in selected_images if image_ref]
        # Skip images that have reached the image reuse limit
        selected_images = [
            image_ref
            for image_ref in selected_images
            if stat_image_usage_count.get(image_ref, 0) < stat_max_usage_per_image
        ]
        if len(selected_images) < 3:
            continue

        selected_visual_turns = [
            {
                "image_inline": image_ref,
                "preceding_text": "",
                "turn": "",
                "role": "candidate",
            }
            for image_ref in selected_images
        ]
        relevant_sessions = []
        relevant_session_ids = []
        relevant_event_ids = []
        for image_ref in selected_images:
            for item in image_session_map.get(normalize_image_ref(image_ref), []):
                session = item['session']
                if session not in relevant_sessions:
                    relevant_sessions.append(session)
                if item['session_id'] not in relevant_session_ids:
                    relevant_session_ids.append(item['session_id'])
                if item['event_id'] not in relevant_event_ids:
                    relevant_event_ids.append(item['event_id'])

        memory_points = [
            memory_point
            for session in relevant_sessions
            for memory_point in session.get('memory_points', [])
            if memory_point.get('memory_source') != 'interference'
        ]
        memory_points_str = format_memory_points(memory_points)
        dialogue_str = "\n\n".join(
            format_dialogue(session.get('dialogue', []))
            for session in relevant_sessions[:3]
            if format_dialogue(session.get('dialogue', []))
        )
        visual_turns_str = "\n".join(
            format_visual_turns(session.get('dialogue', []))
            for session in relevant_sessions[:3]
            if format_visual_turns(session.get('dialogue', []))
        )
        batch_num += 1
        prompt = prompt_template
        prompt = prompt.replace('{persona_info}', persona_info)
        prompt = prompt.replace(
            '{event_info}',
            json.dumps(
                {
                    "mode": "visual_statistical",
                    "image_types": sorted({record.get('type') for record in group if record.get('type')}),
                    "session_ids": relevant_session_ids,
                    "event_ids": relevant_event_ids,
                },
                ensure_ascii=False,
            ),
        )
        prompt = prompt.replace(
            '{selected_images}',
            format_selected_visual_inputs(selected_visual_turns, image_info_by_ref)
        )
        prompt = prompt.replace(
            '{selected_image_metadata}',
            format_selected_image_metadata(selected_images, image_info_by_ref) or "- None"
        )
        prompt = prompt.replace(
            '{selected_image_captions}',
            format_selected_image_captions(selected_images, image_summary_by_ref, output_language) or "- None"
        )
        prompt = prompt.replace('{dialogue}', dialogue_str or "- None")
        prompt = prompt.replace('{visual_evidence}', visual_turns_str or "- None")
        prompt = prompt.replace('{memory_points}', memory_points_str or "- None")
        prompt = prompt.replace('{output_language}', output_language)
        remaining_for_type = quota_for_type - per_type_count.get(image_type, 0)
        stat_batch_size = max(
            1,
            min(BATCH_SIZE, target_count - len(all_questions), remaining_for_type),
        )
        prompt = prompt.replace('{question_count}', str(stat_batch_size))
        prompt = prompt.replace('{session_id}', ",".join(map(str, relevant_session_ids[:3])) or '')
        prompt = prompt.replace('{event_id}', ",".join(map(str, relevant_event_ids[:3])) or '')
        prompt = prompt.replace('{task_mode}', 'statistical')
        prompt += build_batch_format_instruction(
            'visual_reasoning',
            target_count,
            all_questions,
            stat_batch_size,
        )

        try:
            questions = call_llm_for_questions(prompt)
            for question in questions:
                normalize_question_format_fields(question)
                normalize_question_language_fields(question, output_language)
                normalize_true_false_answer(question, output_language)
                normalize_disallowed_question_forms(question)
                normalize_multiple_choice_fields(question)
                normalize_abstention_fields(question, output_language)
                normalize_protagonist_subject(question, basic_profile.get('name', ''), 'visual_reasoning')
                bound_image_refs = extract_bound_image_refs(question, selected_images)
                # Group chat expansion: include all cropped images with the same sub_event_id in bound so the evidence is complete
                bound_image_refs = expand_group_chat_cropped_in_refs(bound_image_refs, image_info_by_ref)
                source_info = collect_visual_sources_for_images(bound_image_refs, image_session_map)
                question['image_refs'] = bound_image_refs
                question['source_session_ids'] = source_info['source_session_ids'] or relevant_session_ids
                question['source_event_ids'] = source_info['source_event_ids'] or relevant_event_ids
                question['question_type'] = 'visual_reasoning'
                ensure_visual_structured_evidence(
                    question,
                    bound_image_refs,
                    image_info_by_ref,
                    image_session_map=image_session_map,
                    output_language=output_language,
                )
                question.pop('bound_image_refs', None)
            questions = filter_questions_by_output_language(
                questions,
                output_language,
                persona.get('uuid'),
                'visual_reasoning',
                batch_num,
            )
            questions = filter_unique_questions(
                questions,
                seen_question_keys,
                uuid=persona.get('uuid'),
                question_type='visual_reasoning',
                batch_num=batch_num,
            )
            # Question-image type consistency check: visual types mentioned in the question stem must be present among the bound images
            type_matched = []
            for q in questions:
                if visual_question_image_types_match(q, image_info_by_ref):
                    type_matched.append(q)
                else:
                    logger.warning(
                        f"  [visual_reasoning/stat] drop type-mismatched: "
                        f"q={(q.get('question') or '')[:60]} | refs={q.get('image_refs')}"
                    )
            questions = type_matched
            allowed_questions = []
            for question in questions:
                question_image_refs = [
                    normalize_image_ref(image_ref)
                    for image_ref in (question.get('image_refs') or [])
                    if normalize_image_ref(image_ref)
                ]
                if any(
                    stat_image_usage_count.get(image_ref, 0) >= stat_max_usage_per_image
                    for image_ref in question_image_refs
                ):
                    continue
                allowed_questions.append(question)
                for image_ref in question_image_refs:
                    stat_image_usage_count[image_ref] = (
                        stat_image_usage_count.get(image_ref, 0) + 1
                    )
            slot_left = max(0, target_count - len(all_questions))
            type_left = max(0, quota_for_type - per_type_count.get(image_type, 0))
            added_questions = allowed_questions[: min(slot_left, type_left)]
            all_questions.extend(added_questions)
            per_type_count[image_type] = (
                per_type_count.get(image_type, 0) + len(added_questions)
            )
            if added_questions and on_batch:
                on_batch(added_questions, batch_num)
        except Exception as exc:
            logger.error(f"  [visual_reasoning/stat] batch {batch_num} error: {exc}")

    return all_questions[:target_count]


def generate_multi_visual_questions(
    persona: Dict,
    sessions: List[Dict],
    persona_image_records: List[Dict],
    target_count: int,
    prompts_dir: str,
    image_info_by_ref: Optional[Dict[str, Dict]] = None,
    image_summary_by_ref: Optional[Dict[str, Dict]] = None,
    seen_question_keys: Optional[set] = None,
    on_batch: Optional[Callable[[List[Dict], int], None]] = None,
) -> List[Dict]:
    basic_profile = persona.get('Basic_Profile', {})
    prompt_template = load_stage6_prompt(
        prompts_dir,
        'stage6_multi_visual',
        persona.get('language') or basic_profile.get('language') or '',
        basic_profile.get('nationality', ''),
    )
    visual_sessions = get_visual_sessions(sessions)

    if not visual_sessions:
        logger.warning("  [visual_reasoning] No sessions with usable image candidates")

    output_language = detect_output_language(
        basic_profile.get('nationality', ''),
        persona.get('language') or basic_profile.get('language') or '',
    )
    persona_info = json.dumps(
        {
            "name": basic_profile.get('name'),
            "nationality": basic_profile.get('nationality'),
            "personality_traits": basic_profile.get('personality_traits', ''),
            "description": persona.get('Init_State', {}).get('description', ''),
            "preferences": persona.get('Init_State', {}).get('preferences', {}),
        },
        ensure_ascii=False,
    )

    seen_question_keys = seen_question_keys if seen_question_keys is not None else set()

    # Build an image_session_map for the entire persona to look up session_id across sessions (needed for group chat expansion)
    persona_image_session_map = build_image_session_map(sessions)

    target_stat_count = max(1, int(round(target_count * VISUAL_STAT_RATIO)))
    stat_questions = generate_visual_stat_questions(
        persona,
        sessions,
        persona_image_records,
        target_stat_count,
        prompts_dir,
        image_info_by_ref=image_info_by_ref,
        image_summary_by_ref=image_summary_by_ref,
        seen_question_keys=seen_question_keys,
        on_batch=on_batch,
    )

    all_questions = list(stat_questions)
    if not visual_sessions:
        return all_questions[:target_count]
    batch_num = 0
    session_idx = 0
    max_attempts = max(len(visual_sessions) * 6, target_count * 2)
    image_usage_count = {}
    max_usage_per_image = MULTI_VISUAL_MAX_USAGE_PER_IMAGE

    # Group chat quota for the detail branch: after reaching the limit, skip groups containing only group chats so other types/single-image fallbacks can fill the quota
    group_chat_quota = max(0, int(round(target_count * VISUAL_GROUP_CHAT_DETAIL_QUOTA_RATIO)))
    group_chat_used = sum(
        1
        for q in all_questions
        if (q.get('image_refs') or [])
        and all(
            infer_image_type(r, image_info_by_ref) in VISUAL_GROUP_CHAT_TYPES
            for r in (q.get('image_refs') or [])
        )
    )

    while len(all_questions) < target_count and session_idx < max_attempts:
        session = visual_sessions[session_idx % len(visual_sessions)]
        session_idx += 1

        image_refs = session.get('image_refs', {})
        visual_context = extract_multi_visual_context(session)
        if visual_context is None:
            continue
        selected_visual_turns = select_available_visual_bundle(
            visual_context['selected_visual_turns'],
            image_usage_count,
            max_usage_per_image,
            image_info_by_ref=image_info_by_ref,
        )
        selected_images = [item.get('image_inline') for item in selected_visual_turns if item.get('image_inline')]
        if len(selected_images) < 1:
            continue

        # Group chat quota limit: if this group consists entirely of group chats and the limit has been reached, skip this session
        selected_types = {
            infer_image_type(image_ref, image_info_by_ref)
            for image_ref in selected_images
        }
        is_pure_group_chat = bool(selected_types) and selected_types.issubset(
            VISUAL_GROUP_CHAT_TYPES
        )
        if is_pure_group_chat and group_chat_used >= group_chat_quota:
            continue

        remaining_capacity = min(
            max_usage_per_image - image_usage_count.get(image_ref, 0)
            for image_ref in selected_images
        )
        if remaining_capacity <= 0:
            continue

        batch_num += 1
        event_id = session.get('event_id', 0)

        memory_points = [
            memory_point
            for memory_point in session.get('memory_points', [])
            if memory_point.get('memory_source') != 'interference'
        ]
        memory_points_str = format_memory_points(memory_points)
        dialogue_str = format_dialogue(session.get('dialogue', []))
        visual_turns_str = format_visual_turns(session.get('dialogue', []))
        event_info = json.dumps(
            {
                "event_name": session.get('event_name'),
                "event_start_time": session.get('event_start_time'),
                "event_end_time": session.get('event_end_time'),
                "description": session.get('dialogue_summary', ''),
                "image_refs": image_refs,
            },
            ensure_ascii=False,
        )

        prompt = prompt_template
        prompt = prompt.replace('{persona_info}', persona_info)
        prompt = prompt.replace('{event_info}', event_info)
        prompt = prompt.replace(
            '{selected_images}',
            format_selected_visual_inputs(selected_visual_turns, image_info_by_ref)
        )
        prompt = prompt.replace(
            '{selected_image_metadata}',
            format_selected_image_metadata(selected_images, image_info_by_ref) or "- None"
        )
        prompt = prompt.replace(
            '{selected_image_captions}',
            format_selected_image_captions(selected_images, image_summary_by_ref, output_language) or "- None"
        )
        prompt = prompt.replace('{dialogue}', dialogue_str or "- None")
        prompt = prompt.replace('{visual_evidence}', visual_turns_str or "- None")
        prompt = prompt.replace('{memory_points}', memory_points_str or "- None")
        prompt = prompt.replace('{output_language}', output_language)
        prompt = prompt.replace(
            '{question_count}',
            str(min(BATCH_SIZE, target_count - len(all_questions), remaining_capacity))
        )
        prompt = prompt.replace('{session_id}', session.get('session_id', ''))
        prompt = prompt.replace('{event_id}', str(event_id))
        prompt = prompt.replace('{task_mode}', 'detail')
        prompt += build_batch_format_instruction(
            'visual_reasoning',
            target_count,
            all_questions,
            min(BATCH_SIZE, target_count - len(all_questions), remaining_capacity),
        )

        try:
            questions = call_llm_for_questions(prompt)
            session_image_session_map = build_image_session_map([session])
            for question in questions:
                normalize_question_format_fields(question)
                normalize_question_language_fields(question, output_language)
                normalize_true_false_answer(question, output_language)
                normalize_disallowed_question_forms(question)
                normalize_multiple_choice_fields(question)
                normalize_abstention_fields(question, output_language)
                normalize_protagonist_subject(question, basic_profile.get('name', ''), 'visual_reasoning')
                bound_image_refs = extract_bound_image_refs(question, selected_images)
                # Group chat expansion: include all cropped images with the same sub_event_id in bound (possibly across sessions)
                bound_image_refs = expand_group_chat_cropped_in_refs(bound_image_refs, image_info_by_ref)
                # Use the persona-level map rather than the single-session map, so session_id can still be found for images from other sessions after expansion
                source_info = collect_visual_sources_for_images(bound_image_refs, persona_image_session_map)
                question['image_refs'] = bound_image_refs
                question['source_session_ids'] = source_info['source_session_ids'] or [session.get('session_id', '')]
                question['source_event_ids'] = source_info['source_event_ids'] or [event_id]
                question['question_type'] = 'visual_reasoning'
                ensure_visual_structured_evidence(
                    question,
                    bound_image_refs,
                    image_info_by_ref,
                    image_session_map=persona_image_session_map,
                    output_language=output_language,
                )
                question.pop('bound_image_refs', None)
            questions = filter_questions_by_output_language(
                questions,
                output_language,
                persona.get('uuid'),
                'visual_reasoning',
                batch_num,
            )
            questions = filter_unique_questions(
                questions,
                seen_question_keys,
                uuid=persona.get('uuid'),
                question_type='visual_reasoning',
                batch_num=batch_num,
            )
            # Question-image type consistency check: visual types mentioned in the question stem must be present among the bound images
            type_matched = []
            for q in questions:
                if visual_question_image_types_match(q, image_info_by_ref):
                    type_matched.append(q)
                else:
                    logger.warning(
                        f"  [visual_reasoning] drop type-mismatched: "
                        f"q={(q.get('question') or '')[:60]} | refs={q.get('image_refs')}"
                    )
            questions = type_matched
            allowed_questions = []
            for question in questions:
                question_image_refs = [normalize_image_ref(image_ref) for image_ref in (question.get('image_refs') or []) if normalize_image_ref(image_ref)]
                if any(
                    image_usage_count.get(image_ref, 0) >= max_usage_per_image
                    for image_ref in question_image_refs
                ):
                    break
                allowed_questions.append(question)
                for image_ref in question_image_refs:
                    image_usage_count[image_ref] = image_usage_count.get(image_ref, 0) + 1
            # Accumulate the group chat quota (count once only when all images are group chat types)
            for question in allowed_questions:
                question_image_refs = [
                    normalize_image_ref(image_ref)
                    for image_ref in (question.get('image_refs') or [])
                    if normalize_image_ref(image_ref)
                ]
                if question_image_refs and all(
                    infer_image_type(r, image_info_by_ref) in VISUAL_GROUP_CHAT_TYPES
                    for r in question_image_refs
                ):
                    group_chat_used += 1
            all_questions.extend(allowed_questions)
            if allowed_questions and on_batch:
                on_batch(allowed_questions, batch_num)
        except Exception as exc:
            logger.error(f"  [visual_reasoning] session {session.get('session_id')} error: {exc}")

    if len(all_questions) < target_count:
        logger.warning(
            f"  [visual_reasoning] strict image reuse cap hit: generated {len(all_questions)} / {target_count} questions "
            f"with max {max_usage_per_image} uses per image"
        )

    return all_questions[:target_count]


def generate_abstention_questions(
    persona: Dict,
    sessions: List[Dict],
    target_count: int,
    prompts_dir: str,
    session_chunk_size: Optional[int] = None,
    seen_question_keys: Optional[set] = None,
    on_batch: Optional[Callable[[List[Dict], int], None]] = None,
) -> List[Dict]:
    basic_profile = persona.get('Basic_Profile', {})
    prompt_template = load_stage6_prompt(
        prompts_dir,
        'stage6_abstention',
        persona.get('language') or basic_profile.get('language') or '',
        basic_profile.get('nationality', ''),
    )
    output_language = detect_output_language(
        basic_profile.get('nationality', ''),
        persona.get('language') or basic_profile.get('language') or '',
    )
    persona_info = json.dumps(
        {
            "name": basic_profile.get('name'),
            "gender": basic_profile.get('gender'),
            "nationality": basic_profile.get('nationality'),
            "career": persona.get('Init_State', {}).get('career'),
            "location": persona.get('Init_State', {}).get('location'),
            "personality_traits": basic_profile.get('personality_traits', ''),
            "preferences": persona.get('Init_State', {}).get('preferences', {}),
        },
        ensure_ascii=False,
    )

    all_questions = []
    seen_question_keys = seen_question_keys if seen_question_keys is not None else set()
    batch_num = 0
    chunk_size = resolve_session_chunk_size(len(sessions), target_count, session_chunk_size)
    max_batches = max(20, (target_count + BATCH_SIZE - 1) // BATCH_SIZE + 40)
    if MAX_BATCHES_PER_TYPE is not None:
        max_batches = max(max_batches, MAX_BATCHES_PER_TYPE)

    while len(all_questions) < target_count and batch_num < max_batches:
        remaining = target_count - len(all_questions)
        batch = min(BATCH_SIZE, remaining)
        batch_num += 1
        session_chunk = get_rotating_session_chunk(sessions, batch_num, chunk_size=chunk_size)
        all_memories_str = format_memory_points(get_all_memories(session_chunk))
        sessions_info = build_sessions_info(session_chunk)

        prompt = prompt_template
        prompt = prompt.replace('{persona_info}', persona_info)
        prompt = prompt.replace('{all_memories}', all_memories_str or "- None")
        prompt = prompt.replace('{sessions_info}', sessions_info or "- None")
        prompt = prompt.replace('{output_language}', output_language)
        prompt = prompt.replace('{question_count}', str(batch))
        prompt += build_batch_format_instruction(
            'abstention', target_count, all_questions, batch
        )

        try:
            questions = call_llm_for_questions(prompt)
            valid_questions = []
            for question in questions:
                question['question_type'] = 'abstention'
                question['evidence'] = []
                question['image_refs'] = []
                question['source_session_ids'] = []
                question['source_event_ids'] = []
                normalize_question_format_fields(question)
                normalize_question_language_fields(
                    question,
                    output_language,
                    fallback_answer_zh="根据现有对话和记忆，无法回答这个问题。",
                    fallback_answer_en="This information is not available in the memory.",
                )
                normalize_true_false_answer(question, output_language)
                normalize_disallowed_question_forms(question)
                normalize_multiple_choice_fields(question)
                normalize_abstention_fields(question, output_language)
                normalize_protagonist_subject(question, basic_profile.get('name', ''), 'abstention')
                valid_questions.append(question)
            valid_questions = filter_questions_by_output_language(
                valid_questions,
                output_language,
                persona.get('uuid'),
                'abstention',
                batch_num,
            )
            valid_questions = filter_unique_questions(
                valid_questions,
                seen_question_keys,
                uuid=persona.get('uuid'),
                question_type='abstention',
                batch_num=batch_num,
            )
            all_questions.extend(valid_questions)
            if valid_questions and on_batch:
                on_batch(valid_questions, batch_num)
            logger.debug(
                f"  [abstention] batch {batch_num}: +{len(valid_questions)}, total={len(all_questions)}"
            )
        except Exception as exc:
            logger.error(f"  [abstention] batch {batch_num} error: {exc}")
            if batch_num > target_count // BATCH_SIZE + 5:
                break

    return all_questions[:target_count]


def process_persona(
    persona: Dict,
    prompts_dir: str,
    image_info_by_ref: Optional[Dict[str, Dict]] = None,
    image_summary_by_ref: Optional[Dict[str, Dict]] = None,
    persona_image_records: Optional[List[Dict]] = None,
    session_chunk_size: Optional[int] = None,
    on_update: Optional[Callable[[Dict], None]] = None,
    existing_record: Optional[Dict] = None,
    question_types: Optional[List[str]] = None,
) -> Dict:
    uuid = persona.get('uuid')
    basic_profile = persona.get('Basic_Profile', {})
    name = basic_profile.get('name', 'Unknown')
    language = persona.get('language', 'zh')
    sessions = persona.get('sessions', [])
    sessions_by_id, sessions_by_event = build_session_indexes(sessions)

    logger.info(f"[uuid={uuid}] Generating questions for {name}, {len(sessions)} sessions")

    active_question_types = question_types or QUESTION_TYPES

    if existing_record:
        result = {
            "uuid": existing_record.get("uuid", uuid),
            "language": existing_record.get("language", language),
            "questions": list(existing_record.get("questions") or []),
            "question_count": len(existing_record.get("questions") or []),
            "question_type_distribution": {},
        }
        if 'visual_reasoning' in active_question_types:
            result["questions"] = [
                question
                for question in result["questions"]
                if question.get('question_type') not in {'multi_visual_reasoning', 'visual_reasoning'}
            ]
            result["question_count"] = len(result["questions"])
        for question in result["questions"]:
            normalize_protagonist_subject(question, name, question.get("question_type", ""))
            normalize_visual_reasoning_first_person(question)
            ensure_structured_evidence(question, sessions_by_id, sessions_by_event)
        for question in result["questions"]:
            question_type = question.get("question_type")
            if question_type:
                result["question_type_distribution"][question_type] = (
                    result["question_type_distribution"].get(question_type, 0) + 1
                )
    else:
        result = {
            "uuid": uuid,
            "language": language,
            "questions": [],
            "question_count": 0,
            "question_type_distribution": {},
        }

    question_counter = len(result['questions'])
    for question in result['questions']:
        question_id = str(question.get('question_id') or '')
        match = re.match(rf'^{re.escape(str(uuid))}_q_(\d+)$', question_id)
        if match:
            question_counter = max(question_counter, int(match.group(1)) + 1)

    seen_question_keys = set()
    for question in result['questions']:
        dedup_key = get_question_dedup_key(question)
        if dedup_key:
            seen_question_keys.add(dedup_key)

    def handle_batch(question_type: str, batch_num: int, questions: List[Dict]):
        nonlocal question_counter
        if not questions:
            return
        for question in questions:
            normalize_protagonist_subject(question, name, question_type)
            question['question_id'] = f"{uuid}_q_{question_counter}"
            question['question_type'] = question_type
            normalize_visual_reasoning_first_person(question)
            question_counter += 1
        result['questions'].extend(questions)
        result['question_count'] = len(result['questions'])
        result['question_type_distribution'][question_type] = (
            result['question_type_distribution'].get(question_type, 0) + len(questions)
        )
        log_batch_questions(uuid, question_type, batch_num, questions)
        if on_update:
            on_update(dict(result))

    for question_type in active_question_types:
        existing_count = result['question_type_distribution'].get(question_type, 0)
        if existing_count >= TARGET_PER_TYPE:
            logger.info(
                f"[uuid={uuid}] {question_type}: SKIP existing {existing_count}/{TARGET_PER_TYPE}"
            )
            result['question_type_distribution'][question_type] = existing_count
            continue

        target_count = TARGET_PER_TYPE - existing_count
        logger.info(
            f"[uuid={uuid}] Generating {target_count} {question_type} questions "
            f"(existing {existing_count}/{TARGET_PER_TYPE})..."
        )
        result['question_type_distribution'].setdefault(question_type, 0)

        try:
            if question_type == 'visual_reasoning':
                questions = generate_multi_visual_questions(
                    persona,
                    sessions,
                    persona_image_records or [],
                    target_count,
                    prompts_dir,
                    image_info_by_ref=image_info_by_ref,
                    image_summary_by_ref=image_summary_by_ref,
                    seen_question_keys=seen_question_keys,
                    on_batch=lambda batch, batch_num, qt=question_type: handle_batch(qt, batch_num, batch),
                )
            elif question_type == 'abstention':
                questions = generate_abstention_questions(
                    persona,
                    sessions,
                    target_count,
                    prompts_dir,
                    session_chunk_size=session_chunk_size,
                    seen_question_keys=seen_question_keys,
                    on_batch=lambda batch, batch_num, qt=question_type: handle_batch(qt, batch_num, batch),
                )
            else:
                questions = generate_standard_questions(
                    persona,
                    sessions,
                    question_type,
                    target_count,
                    prompts_dir,
                    language,
                    session_chunk_size=session_chunk_size,
                    seen_question_keys=seen_question_keys,
                    on_batch=lambda batch, batch_num, qt=question_type: handle_batch(qt, batch_num, batch),
                )

            result['question_type_distribution'][question_type] = existing_count + len(questions)
            logger.info(
                f"[uuid={uuid}] {question_type}: +{len(questions)}, "
                f"total={result['question_type_distribution'][question_type]}/{TARGET_PER_TYPE}"
            )
            if on_update:
                on_update(dict(result))
        except Exception as exc:
            logger.error(f"[uuid={uuid}] {question_type} FAILED: {exc}")
            logger.debug(traceback.format_exc())
            result['question_type_distribution'][question_type] = 0
            if on_update:
                on_update(dict(result))

    logger.info(f"[uuid={uuid}] Done: {result['question_count']} total questions")
    return result


def main():
    parser = argparse.ArgumentParser(description='Stage 6: Generate 7 types of questions')
    parser.add_argument(
        '--input-file',
        type=str,
        default=os.path.join(PROJECT_ROOT, 'data', '10_person', 'stage5_sessions.jsonl'),
        help='Input stage5 JSONL file',
    )
    parser.add_argument(
        '--output-file',
        type=str,
        default=os.path.join(PROJECT_ROOT, 'data', '10_person', 'stage6_questions.jsonl'),
        help='Output stage6 JSONL file',
    )
    parser.add_argument(
        '--prompts-dir',
        type=str,
        default=os.path.join(PROJECT_ROOT, 'prompts'),
        help='Prompts directory',
    )
    parser.add_argument(
        '--image-info-file',
        type=str,
        default='',
        help='Optional stage10 total image info JSONL file for visual_reasoning generation',
    )
    parser.add_argument(
        '--image-summary-file',
        type=str,
        default='',
        help='Optional stage10 image caption JSONL file for visual_reasoning generation',
    )
    parser.add_argument(
        '--target-per-type',
        type=int,
        default=200,
        help='Target questions per type per persona (default: 200)',
    )
    parser.add_argument(
        '--max-workers',
        type=int,
        default=2,
        help='Number of parallel workers (default: 2)',
    )
    parser.add_argument(
        '--session-chunk-size',
        type=int,
        default=10,
        help='Max sessions included per batch prompt for standard and abstention questions (default: 10)',
    )
    parser.add_argument(
        '--uuid-filter',
        type=int,
        nargs='+',
        default=None,
        help='Only process these UUIDs',
    )
    parser.add_argument(
        '--resume-incomplete',
        action='store_true',
        help='Resume existing UUID records and only generate missing questions per type',
    )
    parser.add_argument(
        '--question-types',
        nargs='+',
        choices=QUESTION_TYPES,
        default=None,
        help='Only generate these question types',
    )
    parser.add_argument(
        '--multi-visual-max-usage-per-image',
        type=int,
        default=3,
        help='Max reuse count per image for visual_reasoning (default: 3)',
    )
    parser.add_argument(
        '--max-batches-per-type',
        type=int,
        default=None,
        help='Minimum max LLM batches attempted for each generated question type',
    )
    parser.add_argument(
        '--per-uuid-flat-dir',
        type=str,
        default=None,
        help='Optional flat dir; writes <dir>/stage6_questions_uuid{k}.jsonl per persona',
    )
    args = parser.parse_args()

    global TARGET_PER_TYPE
    global MULTI_VISUAL_MAX_USAGE_PER_IMAGE
    global MAX_BATCHES_PER_TYPE
    TARGET_PER_TYPE = args.target_per_type
    MULTI_VISUAL_MAX_USAGE_PER_IMAGE = max(1, args.multi_visual_max_usage_per_image)
    MAX_BATCHES_PER_TYPE = args.max_batches_per_type

    os.makedirs(os.path.dirname(args.output_file), exist_ok=True)

    logger.info(f"{'=' * 70}")
    logger.info("STAGE 6: Question Generation")
    logger.info(f"Input:  {args.input_file}")
    logger.info(f"Output: {args.output_file}")
    logger.info(f"Image Info: {args.image_info_file or '(disabled)'}")
    logger.info(f"Image Summary: {args.image_summary_file or '(disabled)'}")
    logger.info(f"Target: {TARGET_PER_TYPE} questions/type/persona")
    logger.info(f"Workers: {args.max_workers}")
    logger.info(f"Session Chunk Size: {args.session_chunk_size}")
    logger.info(f"Resume Incomplete: {args.resume_incomplete}")
    logger.info(f"Question Types: {args.question_types or QUESTION_TYPES}")
    logger.info(f"Multi-visual max usage/image: {MULTI_VISUAL_MAX_USAGE_PER_IMAGE}")
    logger.info(f"Max batches/type override: {MAX_BATCHES_PER_TYPE}")
    logger.info(f"{'=' * 70}")

    personas = read_jsonl(args.input_file)
    if not personas:
        logger.error(f"No data in {args.input_file}")
        return

    image_info_indexes = load_image_info_indexes(args.image_info_file)
    image_info_by_ref = image_info_indexes['by_ref']
    image_info_by_uuid = image_info_indexes['by_uuid']
    image_summary_indexes = load_image_summary_indexes(args.image_summary_file)
    image_summary_by_ref = image_summary_indexes['by_ref']

    existing = {}
    for record in read_jsonl(args.output_file):
        if isinstance(record, dict) and 'uuid' in record:
            existing[record['uuid']] = record

    logger.info(f"Loaded {len(personas)} personas, {len(existing)} already processed")

    to_process = []
    for persona in personas:
        uuid = persona.get('uuid')
        if args.uuid_filter and uuid not in args.uuid_filter:
            continue
        if uuid in existing and not args.resume_incomplete:
            logger.info(f"[uuid={uuid}] SKIP")
            continue
        if uuid in existing and args.resume_incomplete:
            existing_record = existing[uuid]
            questions = existing_record.get('questions') or []
            distribution = {}
            for question in questions:
                question_type = question.get('question_type')
                if question_type:
                    distribution[question_type] = distribution.get(question_type, 0) + 1
            active_types = args.question_types or QUESTION_TYPES
            if 'visual_reasoning' in active_types:
                distribution['visual_reasoning'] = 0
                distribution['multi_visual_reasoning'] = 0
            if all(distribution.get(question_type, 0) >= TARGET_PER_TYPE for question_type in active_types):
                logger.info(f"[uuid={uuid}] SKIP complete {distribution}")
                continue
            logger.info(f"[uuid={uuid}] RESUME incomplete {distribution}")
        to_process.append(persona)

    if not to_process:
        logger.info("Nothing to process.")
        return

    lock = threading.Lock()
    results = dict(existing)

    def process_and_save(persona: Dict):
        uuid = persona.get('uuid')

        def save_progress(record: Dict):
            with lock:
                results[uuid] = record
                ordered = [results[p.get('uuid')] for p in personas if p.get('uuid') in results]
                write_jsonl(ordered, args.output_file)
                if args.per_uuid_flat_dir:
                    os.makedirs(args.per_uuid_flat_dir, exist_ok=True)
                    flat_path = os.path.join(
                        args.per_uuid_flat_dir,
                        f'stage6_questions_uuid{uuid}.jsonl',
                    )
                    write_jsonl([record], flat_path)
                logger.info(
                    f"[uuid={uuid}] Saved checkpoint: {record.get('question_count', 0)} questions"
                )

        try:
            record = process_persona(
                persona,
                args.prompts_dir,
                image_info_by_ref=image_info_by_ref,
                image_summary_by_ref=image_summary_by_ref,
                persona_image_records=image_info_by_uuid.get(uuid, []),
                session_chunk_size=args.session_chunk_size,
                on_update=save_progress,
                existing_record=existing.get(uuid) if args.resume_incomplete else None,
                question_types=args.question_types,
            )
            with lock:
                results[uuid] = record
                ordered = [results[p.get('uuid')] for p in personas if p.get('uuid') in results]
                write_jsonl(ordered, args.output_file)
                if args.per_uuid_flat_dir:
                    os.makedirs(args.per_uuid_flat_dir, exist_ok=True)
                    flat_path = os.path.join(
                        args.per_uuid_flat_dir,
                        f'stage6_questions_uuid{uuid}.jsonl',
                    )
                    write_jsonl([record], flat_path)
                logger.info(f"[uuid={uuid}] Saved checkpoint")
            return record
        except Exception as exc:
            logger.error(f"[uuid={uuid}] FATAL: {exc}")
            return None

    actual_workers = min(args.max_workers, len(to_process))
    with ThreadPoolExecutor(max_workers=actual_workers) as executor:
        futures = {
            executor.submit(process_and_save, persona): persona.get('uuid')
            for persona in to_process
        }
        for future in as_completed(futures):
            uuid = futures[future]
            try:
                future.result()
            except Exception as exc:
                logger.error(f"[uuid={uuid}] Thread error: {exc}")

    ordered = [results[p.get('uuid')] for p in personas if p.get('uuid') in results]
    write_jsonl(ordered, args.output_file)

    logger.info(f"{'=' * 70}")
    logger.info(f"STAGE 6 COMPLETE: {len(results)} records saved")
    logger.info(f"{'=' * 70}")


if __name__ == '__main__':
    main()
