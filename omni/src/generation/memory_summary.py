#!/usr/bin/env python3
"""Memory-summary generator (Recall / MemorySummary).

Two phases: Phase 1 captions every generated image with a vision LLM (emitting
:class:`core.ImageSummary` rows), and Phase 2 (:func:`merge_all_images`) merges
all per-stage image JSONLs into a unified per-sub-event view plus a per-image
``total_images`` index (:class:`core.ImageRecord` rows), joining Phase 1
captions onto each image. Persona scenery is kept only in the per-image index
because it is not associated with a real sub-event.
"""

import os
import re
import json
import argparse
import base64
import logging
import threading
from pathlib import PurePath
from typing import Dict, List, Optional, Tuple, Set
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

# This module moved one level deeper (src/ -> src/generation/); recompute the
# project root so the default paths below still resolve to the submission root.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

import config  # noqa: E402
from backends.llm import get_text_llm_model, set_log_context, log_llm_call, get_client  # noqa: E402
from core import ImageSummary, ImageRecord, DIR_NAME, CATEGORY_BY_DIR  # noqa: E402
from core.lang import is_chinese_persona  # noqa: E402
from infra.base_generator import Generator  # noqa: E402
from infra.prompts import load_bilingual_prompt  # noqa: E402
from infra.store import write_jsonl_atomic  # noqa: E402

LOG_DIR = os.path.join(PROJECT_ROOT, 'output', 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# Logging setup

def setup_logging():
    logger = logging.getLogger('memory_summary')
    logger.setLevel(logging.INFO)
    
    # File handler
    file_handler = logging.FileHandler(os.path.join(LOG_DIR, 'memory_summary_summary.log'), encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    # Console handler  
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # Formatter
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

logger = setup_logging()

def encode_image(image_path: str) -> str:
    """Encode image to base64 string for vision API."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def build_prompt(image_type: str, nationality: str = "Chinese") -> str:
    """Build prompt for image summarization based on nationality.
    
    Reads from prompts/image_summary_zh.txt or image_summary_en.txt.
    Same prompt for all image types.
    """
    is_cn = is_chinese_persona(nationality)
    # Respect config.PROMPTS_DIR (previously hardcoded to PROJECT_ROOT/prompts,
    # which silently ignored a custom prompts directory).
    try:
        return load_bilingual_prompt(config.PROMPTS_DIR, "image_summary", is_cn).strip()
    except FileNotFoundError:
        logger.warning(f"Prompt file image_summary_{'zh' if is_cn else 'en'}.txt not found in {config.PROMPTS_DIR}, using fallback")
        if is_cn:
            return "你是一位专业的视觉描述专家。请仔细观察所给的图片，并生成一段详尽、准确且客观的图片描述，描述内容需能够全面概括图片信息。"
        else:
            return "You are a professional visual description expert. Please carefully observe the given image and generate a detailed, accurate, and objective image description that can comprehensively summarize the information in the image."

def _repair_mojibake(text: str) -> str:
    """Defensively repair UTF-8 text misdecoded as GBK (mojibake).

    Some OpenAI-compatible proxies (OneAPI/new-api, etc.) set
    Content-Type: ...; charset=GBK in HTTP response headers, so the SDK
    (httpx) decodes UTF-8 bytes as GBK. This turns smart punctuation and
    adjacent ASCII bytes into mojibake.

    Detection: encode the text as GBK, then decode it as UTF-8.
    - If both steps succeed, the text is likely UTF-8 bytes misdecoded as GBK,
      so return the repaired result.
    - Otherwise, for example real Chinese text whose GBK bytes are not valid
      UTF-8, return the original text.
    """
    if not text:
        return text
    try:
        return text.encode("gbk").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def call_vision_llm(messages: List[Dict], model: str = None) -> str:
    """Call vision LLM API with the given messages."""
    if model is None:
        model = get_text_llm_model(True)
    try:
        response = get_client().chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=16384,
            temperature=0.7
        )
        content = response.choices[0].message.content
        content = content.strip() if content else ""
        # Repair UTF-8 text if an upstream proxy misdecoded it as GBK.
        content = _repair_mojibake(content)
        # Record the LLM call log.
        input_parts = []
        for msg in messages:
            role = msg.get('role', 'unknown')
            if isinstance(msg.get('content'), str):
                input_parts.append(f"[{role}]\n{msg['content']}")
            elif isinstance(msg.get('content'), list):
                text_parts = [p.get('text', '[image]') if p.get('type') == 'text' else '[image]' for p in msg['content']]
                input_parts.append(f"[{role}]\n{''.join(text_parts)}")
        input_text = '\n\n'.join(input_parts)
        usage = getattr(response, 'usage', None)
        input_tokens = getattr(usage, 'prompt_tokens', None) if usage else None
        output_tokens = getattr(usage, 'completion_tokens', None) if usage else None
        log_llm_call(model, input_text, content, input_tokens, output_tokens)
        return content
    except Exception as e:
        logger.error(f"Vision API call failed: {e}")
        raise

def determine_image_type(image_path: str) -> str:
    """Determine the coarse summary type of an image from its path.

    Resolves the published folder under image/uid{N}/ first (CATEGORY_BY_DIR),
    so renamed dataset folders (e.g. ``others`` for scenery, ``camera_photos``
    for event) still classify; the legacy path/filename heuristics below remain
    as a fallback for older layouts.
    """
    path_str = str(image_path).lower()

    # Resolve by the published directory name first (single source of truth).
    for segment in path_str.replace('\\', '/').split('/'):
        category = CATEGORY_BY_DIR.get(segment)
        if category in ('book', 'music', 'video', 'shopping'):
            return 'app'
        if category in ('event', 'group_chat', 'scenery'):
            return category
    
    # Check for event images
    if 'event' in path_str and '_event_' in path_str:
        return 'event'
    
    # Check for group chat images  
    if 'group_chat' in path_str or ('group' in path_str and 'chat' in path_str):
        return 'group_chat'
        
    # Check for scenery images
    if 'scenery' in path_str:
        return 'scenery'
        
    # Check for app screenshots
    if any(app_type in path_str for app_type in ['book', 'music', 'video', 'shopping']):
        return 'app'
        
    # Default classification based on filename patterns
    filename = os.path.basename(path_str)
    if '_event_' in filename:
        return 'event'
    elif 'group' in filename:
        return 'group_chat'
    elif 'scenery' in filename:
        return 'scenery'
    elif any(app_type in filename for app_type in ['book', 'music', 'video', 'shopping']):
        return 'app'
        
    return 'unknown'

def get_nationality_from_uuid(uuid: int, profiles_data: Dict) -> str:
    """Get nationality for a given UUID from profiles data."""
    profile = profiles_data.get(uuid, {})
    basic_profile = profile.get('Basic_Profile', {}) if isinstance(profile, dict) else {}
    nationality = basic_profile.get('nationality', '')
    # Support a top-level nationality field for foreign personas from persona_seeds.
    if not nationality and isinstance(profile, dict):
        nationality = profile.get('nationality', 'Chinese')
    return nationality or 'Chinese'

def load_profiles_data(profiles_file: str) -> Dict[int, Dict]:
    """Load profile rows to get nationality information."""
    profiles_data = {}
    try:
        if os.path.exists(profiles_file):
            with open(profiles_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        record = json.loads(line)
                        uuid = record.get('uuid')
                        if uuid is not None:
                            profiles_data[uuid] = record
    except Exception as e:
        logger.warning(f"Failed to load profiles data from {profiles_file}: {e}")
    
    return profiles_data

def extract_uuid_from_path(image_path: str) -> Optional[int]:
    """Extract the persona UUID from an image path.

    Primary signal: images live under a ``uid{N}/<category>/`` directory, so
    look for a ``uid{N}`` segment anywhere in the path (works with both
    Windows and POSIX separators via PurePath). Secondary signal: some
    filenames start with ``{uuid}_`` (e.g. ``20_event_0_1.png``).
    """
    parts = PurePath(str(image_path).replace('\\', '/')).parts
    for part in parts:
        match = re.match(r'^uid(\d+)$', part)
        if match:
            return int(match.group(1))
    # Fallback: filename patterns like {uuid}_event_{idx}.png
    filename = parts[-1] if parts else ''
    match = re.match(r'^(\d+)_', filename)
    if match:
        return int(match.group(1))
    return None


def find_image_files(image_base_dir: str, uuid_filter: Optional[List[int]] = None) -> List[Tuple[str, int, str]]:
    """Find all relevant image files to process."""
    image_files = []
    
    # Directories to skip
    SKIP_DIRS = {DIR_NAME['group_chat_members']}
    
    # Walk through the image directory
    for root, dirs, files in os.walk(image_base_dir):
        # Skip excluded directories
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for file in files:
            if file.endswith('.png'):
                full_path = os.path.join(root, file)
                filename = os.path.basename(file)
                
                # UUID comes from the uid{N} directory segment (all published
                # images live under uid{N}/<category>/), with the {uuid}_
                # filename prefix as a fallback signal.
                uuid = extract_uuid_from_path(full_path)
                
                # Apply UUID filter if specified
                if uuid_filter is not None and uuid not in uuid_filter:
                    continue
                    
                image_files.append((full_path, uuid, filename))
    
    return image_files

def generate_image_summary(image_path: str, image_type: str, nationality: str) -> Dict:
    """Generate summary for a single image using vision LLM.
    
    Chinese nationality → Chinese summary only (summary_zh)
    Foreign nationality → English summary only (summary_en)
    """
    try:
        # Encode image
        base64_image = encode_image(image_path)
        
        # Build prompt based on nationality
        prompt = build_prompt(image_type, nationality)
        
        # Create messages for vision LLM
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}"
                        }
                    }
                ]
            }
        ]
        
        # Call vision LLM once
        response = call_vision_llm(messages)
        summary = response.strip() if response else ""
        logger.info(f"  Vision LLM response (len={len(summary)}): {summary[:100]}...")
        
        if is_chinese_persona(nationality):
            return {
                "success": True,
                "summary_zh": summary,
                "summary_en": "",
                "error": None
            }
        else:
            return {
                "success": True,
                "summary_zh": "",
                "summary_en": summary,
                "error": None
            }
        
    except Exception as e:
        error_msg = f"Error processing {image_path}: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "summary_zh": "",
            "summary_en": "",
            "error": error_msg
        }

# Phase 2: Merge all stage JSONL files into one unified file

def _read_jsonl(path, *, required: bool = False):
    """Read a JSONL file.

    Missing required manifests are hard failures in DAG/merge mode. Optional
    files remain tolerated for ad-hoc historical runs.
    """
    if not os.path.exists(path):
        message = f"JSONL not found: {path}"
        if required:
            raise FileNotFoundError(message)
        logger.warning(message)
        return []
    records = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _resolve_existing_image_path(path_str: str, data_dir: str) -> Optional[str]:
    """Return an existing filesystem path for a manifest image path, if any."""
    if not path_str:
        return None
    normalized = str(path_str).replace('\\', os.sep).replace('/', os.sep)
    image_root = os.path.join(os.path.dirname(os.path.abspath(data_dir)), 'image')
    candidates = []
    if os.path.isabs(normalized):
        candidates.append(normalized)
    if normalized.startswith("uid"):
        candidates.append(os.path.join(image_root, normalized))
    candidates.append(os.path.join(PROJECT_ROOT, normalized))
    candidates.append(os.path.abspath(normalized))
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return None


def _manifest_image_exists(rec: Dict, data_dir: str) -> bool:
    """True when a manifest row points at a generated image that exists."""
    if rec.get('success') is False:
        return False
    return _resolve_existing_image_path(rec.get('image_path', ''), data_dir) is not None


def _get_parent_event_id(event_id):
    """Parse the parent event_id from sub_event_id."""
    eid_str = str(event_id)
    if '_' in eid_str:
        return int(eid_str.split('_')[0])
    try:
        return int(eid_str)
    except ValueError:
        return eid_str


def _normalize_image_path(path_str):
    """Normalize any inbound image path to a project-root-relative POSIX path.

    Across stages the same image is referenced three different ways, which made
    merged_memories mix formats (and leak an absolute, machine-specific prefix):
    absolute, full-relative (output/image/...), and half-relative (uid{N}/...).
    All collapse to a single portable form: output/image/uid{N}/...
    """
    if not path_str:
        return path_str
    import re
    p = str(path_str).replace(chr(92), '/')
    marker = 'output/image/'
    idx = p.rfind(marker)
    if idx != -1:
        return p[idx:]
    if re.match(r'^uid\d+/', p):
        return marker + p
    return p


def _resolve_document_manifest(data_dir: str, document_file: str = None) -> str:
    """Prefer the owned document manifest, with read-only legacy fallback."""
    preferred = document_file or os.path.join(data_dir, 'document_records.jsonl')
    if os.path.exists(preferred):
        return preferred
    legacy_path = os.path.join(data_dir, 'tickets.jsonl')
    if os.path.exists(legacy_path):
        logger.warning(
            "Using legacy tickets.jsonl; rerun document to create document_records.jsonl"
        )
        return legacy_path
    return preferred


def _load_summary_index(summaries_file: str) -> Dict[str, Dict[str, str]]:
    """Index Phase 1 captions by normalized path and basename for join."""
    index: Dict[str, Dict[str, str]] = {}
    for rec in _read_jsonl(summaries_file, required=False):
        if rec.get('success') is False:
            continue
        entry = {
            'summary_zh': rec.get('summary_zh') or '',
            'summary_en': rec.get('summary_en') or '',
        }
        raw = rec.get('image_path', '') or ''
        norm = _normalize_image_path(raw)
        for key in (norm, os.path.basename(norm) if norm else '',
                    os.path.basename(raw) if raw else ''):
            if key:
                index[key] = entry
    return index


def _lookup_summary(index: Dict[str, Dict[str, str]], image_path: str) -> Dict[str, str]:
    """Return summary_zh/summary_en for an image path, or empty strings."""
    empty = {'summary_zh': '', 'summary_en': ''}
    if not image_path:
        return empty
    norm = _normalize_image_path(image_path)
    hit = index.get(norm) or index.get(os.path.basename(norm or image_path))
    return dict(hit) if hit else empty


def _load_scenery_into_grouped(grouped: dict, data_dir: str, image_dir: Optional[str]) -> int:
    """Append scenery PNGs from image/manifest.json under synthetic sub_event_id ``scenery``.

    Scenery is persona-level (not tied to a calendar event), so it lands in its
    own merged_memories row per uuid rather than being duplicated onto every
    real sub-event.
    """
    if not image_dir:
        image_dir = os.path.join(os.path.dirname(os.path.abspath(data_dir)), 'image')
    manifest_path = os.path.join(image_dir, 'manifest.json')
    if not os.path.exists(manifest_path):
        logger.info("scenery: no manifest.json, skip")
        return 0

    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)

    scenery_folder = DIR_NAME['scenery']
    count = 0
    for uid_str, categories in (manifest or {}).items():
        try:
            uid = int(uid_str)
        except (TypeError, ValueError):
            continue
        if not isinstance(categories, dict):
            continue
        for category, files in categories.items():
            for filename in files or []:
                abs_path = os.path.join(image_dir, f'uid{uid}', scenery_folder, filename)
                if not os.path.exists(abs_path):
                    continue
                grouped[(uid, 'scenery')].append({
                    'type': 'scenery',
                    'category': category,
                    'image_path': abs_path,
                })
                count += 1
    logger.info(f"scenery: {count} images loaded from {manifest_path}")
    return count


def merge_all_images(data_dir: str, summaries_file: str, merged_output: str,
                     sub_events_file: str, events_file: str,
                     image_dir: Optional[str] = None,
                     document_file: Optional[str] = None):
    """Merge all stage image JSONL files into a unified per-sub-event format.

    Output files:
    1. merged_memories.jsonl: one sub-event per line; each ``images`` entry is
       ``{image_path, summary_zh, summary_en}`` (Phase 1 captions joined in).
    2. total_images.jsonl: one image per line, keyed by path and carrying
       type-specific structured information plus the same caption fields;
       persona scenery is included here with ``sub_event_id=null``.
    """
    logger.info("=" * 70)
    logger.info("Phase 2: Merge all image JSONL files")
    logger.info(f"Data directory: {data_dir}")
    logger.info(f"Summaries file: {summaries_file}")
    logger.info(f"Output: {merged_output}")
    logger.info("=" * 70)

    # -- 1. Phase 1 captions (joined onto every image row below).
    summary_index = _load_summary_index(summaries_file)
    logger.info(f"Loaded {len(summary_index)} caption index keys from {summaries_file}")

    # -- 2. Load event metadata.
    # sub_events: (uuid, sub_event_id) -> {event_name, event_time, participants, importance, parent_event_id}
    event_metadata = {}

    # 2a. Load sub-event metadata from sub_events.jsonl.
    sub_events_records = _read_jsonl(sub_events_file, required=True)
    for rec in sub_events_records:
        uid = rec['uuid']
        for group in rec.get('sub_events', []):
            parent_id = group['parent_event_id']
            for child in group.get('children', []):
                if child.get('is_intro'):
                    continue
                seid = str(child['sub_event_id'])
                event_metadata[(uid, seid)] = {
                    'event_name': child.get('event_name', ''),
                    'event_time': child.get('event_start_time', ''),
                    'participants': [
                        p.get('name', str(p)) if isinstance(p, dict) else str(p)
                        for p in child.get('participants', [])
                    ],
                    'importance': child.get('importance', ''),
                    'event_id': parent_id,
                }
    logger.info(f"Loaded metadata for {len(event_metadata)} sub-events")

    # 2b. Load short-term event metadata from annual_events.jsonl.
    events_records = _read_jsonl(events_file, required=True)
    for rec in events_records:
        if 'uuid' not in rec:
            continue
        uid = rec['uuid']
        for ev in rec.get('Events', []):
            if ev.get('duration_type') == 'short-term':
                eid_str = str(ev['event_id'])
                if (uid, eid_str) not in event_metadata:
                    event_metadata[(uid, eid_str)] = {
                        'event_name': ev.get('event_name', ev.get('event', '')),
                        'event_time': ev.get('event_start_time', ''),
                        'participants': [
                            p.get('name', str(p)) if isinstance(p, dict) else str(p)
                            for p in ev.get('participants', [])
                        ],
                        'importance': ev.get('importance', ''),
                        'event_id': ev['event_id'],
                    }
    logger.info(f"Total event metadata entries: {len(event_metadata)}")

    # -- 3. Collect all images grouped by (uuid, sub_event_id).
    # key: (uuid, sub_event_id_str) -> list of image dicts
    grouped = defaultdict(list)

    # 3a. event_photo event scene images.
    event_photo_path = os.path.join(data_dir, 'event_images.jsonl')
    event_photo_records = _read_jsonl(event_photo_path, required=True)
    for rec in event_photo_records:
        if not _manifest_image_exists(rec, data_dir):
            continue
        uid = rec['uuid']
        seid = str(rec.get('sub_event_id', rec.get('event_idx', '')))
        img_path = rec.get('image_path', '')
        grouped[(uid, seid)].append({
            'type': 'event_scene',
            'image_path': img_path,
            'participants': rec.get('participants', []),
            'scene_prompt': rec.get('scene_prompt', ''),
        })
    logger.info(f"event_photo: {len(event_photo_records)} records loaded")

    # 3b. app_trace app screenshots.
    app_trace_path = os.path.join(data_dir, 'app_screenshots.jsonl')
    app_trace_records = _read_jsonl(app_trace_path, required=True)
    for rec in app_trace_records:
        if not _manifest_image_exists(rec, data_dir):
            continue
        uid = rec['uuid']
        # Support both old and new formats.
        seid = str(rec.get('sub_event_id', rec.get('event_id', '')))
        img_path = rec.get('image_path', '')
        app_type = rec.get('app_type', 'app')
        info = rec.get('info', {})
        img_record = {
            'type': app_type,
            'image_path': img_path,
        }
        if app_type == 'shopping':
            for k in ('item_name', 'shop_name', 'price', 'order_time', 'order_status'):
                if k in info:
                    img_record[k] = info[k]
        elif app_type == 'book':
            for k in ('title', 'author', 'progress'):
                if k in info:
                    img_record[k] = info[k]
        elif app_type == 'music':
            for k in ('song', 'artist', 'album', 'lyric_line', 'comment', 'comment_user'):
                if k in info:
                    img_record[k] = info[k]
        elif app_type == 'video':
            for k in ('title', 'uploader', 'duration', 'view_count', 'danmaku', 'danmaku_count'):
                if k in info:
                    img_record[k] = info[k]
        grouped[(uid, seid)].append(img_record)
    logger.info(f"app_trace: {len(app_trace_records)} records loaded")

    # 3c. document tickets, transfers, and social-feed screenshots.
    document_path = _resolve_document_manifest(data_dir, document_file)
    document_records = _read_jsonl(document_path, required=True)
    for rec in document_records:
        if not _manifest_image_exists(rec, data_dir):
            continue
        uid = rec['uuid']
        seid = str(rec.get('sub_event_id', rec.get('event_id', '')))
        img_path = rec.get('image_path', '')
        img_type = rec.get('type', 'ticket')
        img_record = {
            'type': img_type,
            'image_path': img_path,
        }
        if img_type == 'ticket':
            img_record['ticket_info'] = rec.get('ticket_info', {})
        elif img_type == 'money':
            img_record['money_info'] = rec.get('money_info', {})
        elif img_type == 'friend':
            img_record['friend_info'] = rec.get('friend_info', {})
            img_record['participants'] = rec.get('participants', [])
        grouped[(uid, seid)].append(img_record)
    logger.info(f"document: {len(document_records)} records loaded")

    # 3d. conversation group-chat screenshots.
    gc_path = os.path.join(data_dir, 'group_chats.jsonl')
    gc_image_count = 0
    gc_records = _read_jsonl(gc_path, required=True)

    def _estimate_gc_crop_ranges(messages, n_crops, segment_height=800):
        """Estimate which messages each cropped screenshot contains from CSS layout.

        CSS parameters come from templates/wechat_group.html:
        - status-bar: 44px, nav-bar: 44px, chat padding-top: 10px
        - message gap: 16px, avatar: 40x40px
        - sender-name: font 12px * line-height 1.2 + margin-bottom 2 = 16px
        - bubble: padding 9+9=18px, font 16px, line-height 1.5=24px/line
        - bubble text width ≈ 253px (max-width 65% of 426px - 24px padding)
        - Approximate CJK characters per line: 15 (253/16)
        """
        if not messages or n_crops <= 0:
            return [[] for _ in range(n_crops)]

        HEADER_H = 98       # 44 + 44 + 10 (status + nav + chat pad)
        MSG_GAP = 16
        SENDER_NAME_H = 16
        BUBBLE_PAD_V = 18   # 9 + 9
        LINE_H = 24         # 16 * 1.5
        CHARS_PER_LINE = 15
        AVATAR_H = 40

        y = HEADER_H
        msg_spans = []       # (y_start, y_end)
        for msg in messages:
            text = msg.get('text', '') or msg.get('content', '')
            side = msg.get('side', 'left')
            text_lines = max(1, -(-len(text) // CHARS_PER_LINE))
            content_h = BUBBLE_PAD_V + text_lines * LINE_H
            if side == 'left':
                content_h += SENDER_NAME_H
            msg_h = max(AVATAR_H, content_h)
            msg_spans.append((y, y + msg_h))
            y += msg_h + MSG_GAP

        result = []
        for ci in range(n_crops):
            y0 = ci * segment_height
            y1 = (ci + 1) * segment_height
            crop_indices = [i for i, (ms, me) in enumerate(msg_spans)
                           if me > y0 and ms < y1]
            result.append(crop_indices)
        return result

    for rec in gc_records:
        uid = rec.get('uuid')
        if uid is None:
            continue
        for gc in rec.get('group_chats', []):
            eid = str(gc.get('related_event_id', ''))
            png_files = gc.get('png_file', [])
            if isinstance(png_files, str):
                png_files = [png_files]
            all_messages = gc.get('messages', [])
            valid_pngs = [p for p in png_files if p and os.path.exists(p)]
            n_crops = len(valid_pngs)

            # Prefer the actual message range recorded during conversation rendering.
            stored_ranges = gc.get('crop_message_ranges')
            if stored_ranges and len(stored_ranges) == n_crops:
                crop_ranges = stored_ranges
            else:
                # Fall back to the CSS-based estimate.
                crop_ranges = _estimate_gc_crop_ranges(all_messages, n_crops)

            for crop_idx, img_path in enumerate(valid_pngs):
                indices = crop_ranges[crop_idx] if crop_idx < len(crop_ranges) else []
                crop_messages = [all_messages[i] for i in indices if i < len(all_messages)]
                grouped[(uid, eid)].append({
                    'type': 'group_chat',
                    'image_path': img_path,
                    'group_name': gc.get('group_name', ''),
                    'member_count': gc.get('member_count', 0),
                    'messages': crop_messages,
                })
                gc_image_count += 1
    logger.info(f"conversation: {gc_image_count} group_chat images loaded")

    # 3e. scenery images (persona-level; synthetic sub_event_id="scenery").
    _load_scenery_into_grouped(grouped, data_dir, image_dir)

    # -- 4. Assemble final merged records.
    merged_records = []
    total_images_records = []
    caption_hits = 0
    caption_misses = 0
    for (uid, seid) in sorted(grouped.keys(), key=lambda x: (x[0], str(x[1]))):
        meta = event_metadata.get((uid, seid), {})
        parent_eid = meta.get('event_id', _get_parent_event_id(seid) if seid != 'scenery' else None)
        images_list = grouped[(uid, seid)]
        merged_images = []
        for img in images_list:
            norm_path = _normalize_image_path(img.get('image_path', ''))
            caps = _lookup_summary(summary_index, norm_path or img.get('image_path', ''))
            if caps['summary_zh'] or caps['summary_en']:
                caption_hits += 1
            else:
                caption_misses += 1
            merged_images.append({
                'image_path': norm_path,
                'summary_zh': caps['summary_zh'],
                'summary_en': caps['summary_en'],
            })
        if seid != 'scenery':
            record = {
                'uuid': uid,
                'sub_event_id': seid,
                'event_id': parent_eid,
                'event_name': meta.get('event_name', ''),
                'event_time': meta.get('event_time', ''),
                'participants': meta.get('participants', []),
                'importance': meta.get('importance', ''),
                'images': merged_images,
            }
            merged_records.append(record)
        for img in images_list:
            # Route the per-image row through the ImageRecord contract.
            # ImageRecord declares the common keys (uuid / sub_event_id / type /
            # image_path) and carries the type-specific fields in 'extra'.
            # from_dict (not kwargs) avoids inventing absent keys.
            norm_path = _normalize_image_path(img.get('image_path', ''))
            caps = _lookup_summary(summary_index, norm_path or img.get('image_path', ''))
            img = {**img, 'image_path': norm_path, **caps}
            img_record = ImageRecord.from_dict(
                {
                    'uuid': uid,
                    'sub_event_id': None if seid == 'scenery' else seid,
                    **img,
                }
            ).to_dict()
            total_images_records.append(img_record)

    write_jsonl_atomic(merged_records, merged_output)
    total_images_output = merged_output.replace('merged_memories', 'total_images')
    write_jsonl_atomic(total_images_records, total_images_output)
    logger.info(f"Merged {len(merged_records)} sub-events with "
                f"{sum(len(r['images']) for r in merged_records)} total images")
    logger.info(f"Caption join: hit={caption_hits}, miss={caption_misses}")
    logger.info(f"Output: {merged_output}")
    logger.info(f"Total images index: {total_images_output} ({len(total_images_records)} records)")

    # Statistics.
    uuids = set(r['uuid'] for r in merged_records)
    for uid in sorted(uuids):
        uid_records = [r for r in merged_records if r['uuid'] == uid]
        uid_images = sum(len(r['images']) for r in uid_records)
        logger.info(f"  uuid={uid}: {len(uid_records)} sub-events, {uid_images} images")

    return merged_records


class MemorySummaryGenerator(Generator):
    """Caption generated images with a vision LLM (Recall MemorySummary).

    Domain generator for the memory_summary node. The standalone batch run is
    :func:`main` (Phase 1 parallel captioning + Phase 2 :func:`merge_all_images`);
    this class is a thin uniform per-image entry point for the future pipeline
    DAG over a ``{image_path, uuid, image_type, nationality}`` record.
    """

    label = "memory_summary"
    index_key = "image_path"

    def produce(self, record: Dict, ctx=None) -> Dict:
        image_path = record["image_path"]
        image_type = record.get("image_type") or determine_image_type(image_path)
        nationality = record.get("nationality", "Chinese")
        result = generate_image_summary(image_path, image_type, nationality)
        out = ImageSummary(
            image_path=image_path,
            filename=record.get("filename", os.path.basename(image_path)),
            uuid=record.get("uuid"),
            image_type=image_type,
            nationality=nationality,
            summary_zh=result["summary_zh"],
            summary_en=result["summary_en"],
            success=result["success"],
        ).to_dict()
        if not result["success"]:
            out["error"] = result["error"]
        return out


def main():
    parser = argparse.ArgumentParser(description='memory_summary: Generate image summaries using vision LLM')
    
    parser.add_argument('--image-base-dir', type=str,
                        default=os.path.join(PROJECT_ROOT, 'output', 'image'),
                        help='Base directory containing images (default: image/)')
    
    parser.add_argument('--output-file', type=str,
                        default=os.path.join(PROJECT_ROOT, 'output', 'data', 'image_summaries.jsonl'),
                        help='Output JSONL file path')
    
    parser.add_argument('--profiles-file', type=str,
                        default=os.path.join(PROJECT_ROOT, 'output', 'data', 'basic_profiles.jsonl'),
                        help='Profiles file for nationality info')
    
    parser.add_argument('--uuid-filter', type=int, nargs='+', default=None,
                        help='Only process images for these UUIDs')
    
    parser.add_argument('--max-images', type=int, default=None,
                        help='Maximum number of images to process (for testing)')
    
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be processed without actually calling vision LLM')
    
    parser.add_argument('--merge-only', action='store_true',
                        help='Skip Phase 1 (summary generation), only run Phase 2 (merge)')
    
    parser.add_argument('--skip-merge', action='store_true',
                        help='Skip Phase 2 (merge), only run Phase 1 (summary generation)')
    
    parser.add_argument('--merged-output', type=str,
                        default=os.path.join(PROJECT_ROOT, 'output', 'data', 'merged_memories.jsonl'),
                        help='Merged output JSONL file path')
    
    parser.add_argument('--sub-events-file', type=str,
                        default=os.path.join(PROJECT_ROOT, 'output', 'data', 'sub_events.jsonl'),
                        help='Sub-events JSONL for event metadata')
    
    parser.add_argument('--events-file', type=str,
                        default=os.path.join(PROJECT_ROOT, 'output', 'data', 'annual_events.jsonl'),
                        help='Annual events JSONL for short-term event metadata')

    parser.add_argument('--document-file', type=str,
                        default=os.path.join(PROJECT_ROOT, 'output', 'data',
                                             'document_records.jsonl'),
                        help='Document records JSONL (ticket, money, and friend)')
    
    parser.add_argument('--workers', type=int, default=4,
                        help='Number of parallel workers for Vision LLM calls (default: 4)')
    
    parser.add_argument('--reset', '--force', dest='reset', action='store_true',
                        help='Delete existing memory_summary output files and start from scratch')
    
    args = parser.parse_args()
    
    if args.merge_only:
        data_dir = os.path.dirname(args.output_file)
        merge_all_images(
            data_dir=data_dir,
            summaries_file=args.output_file,
            merged_output=args.merged_output,
            sub_events_file=args.sub_events_file,
            events_file=args.events_file,
            image_dir=args.image_base_dir,
            document_file=args.document_file,
        )
        return
    
    logger.info("=" * 70)
    logger.info("memory_summary: image summary generation with vision LLM")
    logger.info(f"Image base directory: {args.image_base_dir}")
    logger.info(f"Output file: {args.output_file}")
    logger.info(f"Profiles file: {args.profiles_file}")
    logger.info(f"UUID filter: {args.uuid_filter}")
    logger.info(f"Dry run mode: {args.dry_run}")
    logger.info(f"Workers: {args.workers}")
    logger.info("=" * 70)
    
    # --reset: delete memory_summary output files and start fresh
    if args.reset:
        for fpath in [args.output_file, args.merged_output]:
            if os.path.exists(fpath):
                os.remove(fpath)
                logger.info(f"[reset] Deleted {fpath}")
    
    # Load profiles data for nationality information
    profiles_data = load_profiles_data(args.profiles_file)
    logger.info(f"Loaded {len(profiles_data)} profiles")
    
    # Find all image files to process
    image_files = find_image_files(args.image_base_dir, args.uuid_filter)
    logger.info(f"Found {len(image_files)} images to process")
    
    if args.max_images:
        image_files = image_files[:args.max_images]
        logger.info(f"Limited to {len(image_files)} images for testing")
    
    if args.dry_run:
        logger.info("DRY RUN - showing files that would be processed:")
        for image_path, uuid, filename in image_files:
            image_type = determine_image_type(image_path)
            nationality = get_nationality_from_uuid(uuid, profiles_data) if uuid is not None else "Chinese"
            logger.info(f"  {filename} (uuid={uuid}, type={image_type}, nationality={nationality})")
        return
    
    # Resume: load already-processed image paths
    done_set: Set[str] = set()
    if os.path.exists(args.output_file) and not args.reset:
        with open(args.output_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line:
                    try:
                        rec = json.loads(line)
                        # Only successful captions count as done: rows with
                        # success=false are retried on resume. A retried image
                        # appends a new row, so a path may appear as an older
                        # failed row plus a newer successful one; membership in
                        # done_set only requires some successful row to exist.
                        if rec.get('success') is True:
                            done_set.add(rec.get('image_path', ''))
                    except json.JSONDecodeError:
                        # A corrupt resume line means that image will be re-processed.
                        logger.warning(f"[WARN] Skipping corrupt JSONL line {line_num} in {args.output_file}")
        if done_set:
            logger.info(f"Resume: {len(done_set)} images already processed, skipping them")
    
    # Filter out already-processed images
    pending_files = [(p, u, fn) for p, u, fn in image_files if p not in done_set]
    skipped_count = len(image_files) - len(pending_files)
    if skipped_count > 0:
        logger.info(f"Skipped {skipped_count} already-processed images, {len(pending_files)} remaining")
    
    if not pending_files:
        logger.info("All images already processed, nothing to do in Phase 1")
    else:
        # Process images with thread pool
        os.makedirs(os.path.dirname(args.output_file), exist_ok=True)
        write_lock = threading.Lock()
        processed_count = 0
        error_count = 0
        total = len(pending_files)
        counter_lock = threading.Lock()
        
        def process_one(item):
            nonlocal processed_count, error_count
            image_path, uuid, filename = item
            set_log_context(uuid=uuid, stage="memory_summary")
            image_type = determine_image_type(image_path)
            nationality = get_nationality_from_uuid(uuid, profiles_data) if uuid is not None else "Chinese"
            
            result = generate_image_summary(image_path, image_type, nationality)
            
            # Declared field order on ImageSummary is the serialized field
            # order; 'error' is appended only on failure.
            output_record = ImageSummary(
                image_path=image_path,
                filename=filename,
                uuid=uuid,
                image_type=image_type,
                nationality=nationality,
                summary_zh=result["summary_zh"],
                summary_en=result["summary_en"],
                success=result["success"],
            ).to_dict()
            if not result["success"]:
                output_record["error"] = result["error"]
            
            with write_lock:
                with open(args.output_file, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(output_record, ensure_ascii=False) + '\n')
            
            with counter_lock:
                if result["success"]:
                    processed_count += 1
                else:
                    error_count += 1
                done = processed_count + error_count
                if done % 10 == 0 or done == total:
                    logger.info(f"  Progress: {done}/{total} ({processed_count} ok, {error_count} err)")
            
            return output_record
        
        logger.info(f"Starting Phase 1 with {args.workers} workers, {total} images to process")
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(process_one, item): item for item in pending_files}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    item = futures[future]
                    logger.error(f"Unexpected error processing {item[2]}: {e}")
    
    logger.info("=" * 70)
    logger.info("memory_summary Phase 1 COMPLETE")
    logger.info(f"Output: {args.output_file}")
    logger.info("=" * 70)

    if not args.skip_merge:
        data_dir = os.path.dirname(args.output_file)
        merge_all_images(
            data_dir=data_dir,
            summaries_file=args.output_file,
            merged_output=args.merged_output,
            sub_events_file=args.sub_events_file,
            events_file=args.events_file,
            image_dir=args.image_base_dir,
            document_file=args.document_file,
        )

if __name__ == '__main__':
    main()
