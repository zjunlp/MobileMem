"""
Stage 5: Generate Dialogue + Memory Points (combined).

Input: data/10_person/stage4_annual_events.jsonl
Output: data/10_person/stage5_sessions.jsonl

Generate one session for each event of each persona, containing:
  - Dialogue (15-30 turns)
  - Memory points (system/primary/secondary/interference)
  - Image references (image_refs)

Supports checkpoint resumption: skip processed UUIDs.
"""

import os
import sys
import json
import argparse
import time
import traceback
import threading
import logging
import re
import hashlib
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
SRC_DIR = os.path.join(PROJECT_ROOT, 'src')

from dotenv import load_dotenv
env_path = os.path.join(SRC_DIR, '.env')
if os.path.exists(env_path):
    load_dotenv(env_path, override=False)

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import jsonlines
from llm_request import llm_request, _extract_json_from_content

# ============================================================================
# Logging setup
# ============================================================================

LOG_DIR = os.path.join(PROJECT_ROOT, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

def setup_logging():
    summary_handler = logging.FileHandler(os.path.join(LOG_DIR, 'stage5_summary.log'), encoding='utf-8')
    summary_handler.setLevel(logging.INFO)
    detail_handler = logging.FileHandler(os.path.join(LOG_DIR, 'stage5_detail.log'), encoding='utf-8')
    detail_handler.setLevel(logging.DEBUG)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    for h in [summary_handler, detail_handler, console_handler]:
        h.setFormatter(fmt)

    logger = logging.getLogger('stage5')
    logger.setLevel(logging.DEBUG)
    logger.addHandler(summary_handler)
    logger.addHandler(detail_handler)
    logger.addHandler(console_handler)
    return logger

logger = setup_logging()

# ============================================================================
# Helpers
# ============================================================================

FORBIDDEN_DIALOGUE_BRACKETS = "【】"
LEADING_FULLWIDTH_PAREN_PREFIX_RE = re.compile(r'^\s*(?:`?\s*（[^）]{1,30}）\s*`?\s*)+')


def sanitize_dialogue_text(text: str) -> str:
    """Remove forbidden generated chat wrappers from dialogue text."""
    if not isinstance(text, str):
        return ''

    cleaned = text.strip()
    cleaned = LEADING_FULLWIDTH_PAREN_PREFIX_RE.sub('', cleaned).strip()
    for bracket in FORBIDDEN_DIALOGUE_BRACKETS:
        cleaned = cleaned.replace(bracket, '')
    return cleaned

def read_jsonl(path: str) -> List[Dict]:
    if not os.path.exists(path):
        return []
    with jsonlines.open(path, 'r') as reader:
        return list(reader)


def write_jsonl(records: List[Dict], path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with jsonlines.open(path, 'w') as writer:
        for r in records:
            writer.write(r)


def write_per_uuid_record(record: Dict, base_dir: str):
    """Write one persona stage5 record to data_10person/uuid_{uuid}/stage5 sessions files."""
    uuid = record.get('uuid')
    if uuid is None:
        return
    persona_dir = os.path.join(base_dir, f'uuid_{uuid}')
    os.makedirs(persona_dir, exist_ok=True)

    for filename in ['stage5_sessions.jsonl', 'stage5_sessions_rerun.jsonl']:
        out_path = os.path.join(persona_dir, filename)
        write_jsonl([record], out_path)


def safe_filename(text: str) -> str:
    text = str(text)
    text = re.sub(r'[\\/:*?"<>|]+', '_', text)
    text = re.sub(r'\s+', '_', text).strip('_')
    return text or 'unknown'


def write_json(path: str, payload: Dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def write_stage5_session_artifacts(
    base_dir: Optional[str],
    uuid: int,
    session_index: int,
    session: Dict,
    parent_memory_payload: Optional[Dict] = None
):
    if not base_dir:
        return

    persona_dir = os.path.join(base_dir, f'uuid_{uuid}')
    sessions_dir = os.path.join(persona_dir, 'sessions')
    parent_mem_dir = os.path.join(persona_dir, 'parent_memories')
    os.makedirs(sessions_dir, exist_ok=True)
    os.makedirs(parent_mem_dir, exist_ok=True)

    session_name = safe_filename(session.get('session_id', f'session_{session_index:04d}'))
    session_path = os.path.join(sessions_dir, f'{session_index:04d}_{session_name}.json')
    write_json(session_path, session)

    if parent_memory_payload:
        parent_key = safe_filename(parent_memory_payload.get('parent_memory_key', 'unknown'))
        parent_path = os.path.join(parent_mem_dir, f'parent_{parent_key}.json')
        if not os.path.exists(parent_path):
            write_json(parent_path, parent_memory_payload)


def sync_data10person_record(record: Dict, base_dir: str):
    """Sync regenerated sessions back into data_10person/uuid_{uuid}/data.jsonl."""
    uuid = record.get('uuid')
    if uuid is None:
        return

    data_path = os.path.join(base_dir, f'uuid_{uuid}', 'data.jsonl')
    if not os.path.exists(data_path):
        return

    rows = read_jsonl(data_path)
    if not rows:
        return

    row = rows[0]
    sessions = record.get('sessions', [])
    row['sessions'] = sessions
    row['Sessions'] = sessions
    if 'session_stats_summary' in record:
        row['session_stats_summary'] = record['session_stats_summary']

    stats = row.get('Stats', {})
    stats['session_count'] = len(sessions)
    stats['memory_point_count'] = sum(len(s.get('memory_points', [])) for s in sessions)
    stats['total_dialogue_turns'] = sum(len(s.get('dialogue', [])) for s in sessions)
    stats['total_dialogue_output_tokens'] = (record.get('session_stats_summary') or {}).get('total_dialogue_output_tokens', 0)
    row['Stats'] = stats

    write_jsonl([row], data_path)


def load_prompt(path: str) -> str:
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def format_timestamp(dt_str: str) -> str:
    """Convert common date formats or unix timestamps to '2025-01-01 10:00:00'."""
    try:
        if isinstance(dt_str, (int, float)) or (isinstance(dt_str, str) and str(dt_str).isdigit()):
            return datetime.fromtimestamp(int(dt_str)).strftime('%Y-%m-%d %H:%M:%S')
        text = str(dt_str).strip()
        for fmt in (
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d',
            '%b %d, %Y, %H:%M:%S',
            '%b %d, %Y',
            '%B %d, %Y, %H:%M:%S',
            '%B %d, %Y',
        ):
            try:
                dt = datetime.strptime(text, fmt)
                if fmt in {'%Y-%m-%d', '%b %d, %Y', '%B %d, %Y'}:
                    dt = dt.replace(hour=0, minute=0, second=0)
                return dt.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                continue
    except Exception:
        pass
    return dt_str


def parse_event_datetime(value) -> datetime:
    if value is None:
        return datetime.max

    if isinstance(value, (int, float)) or (isinstance(value, str) and str(value).isdigit()):
        try:
            return datetime.fromtimestamp(int(value))
        except Exception:
            return datetime.max

    text = str(value).strip()
    if not text:
        return datetime.max

    for fmt in (
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d',
        '%b %d, %Y, %H:%M:%S',
        '%b %d, %Y',
        '%B %d, %Y, %H:%M:%S',
        '%B %d, %Y',
    ):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            continue

    normalized = format_timestamp(text)
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(normalized, fmt)
        except Exception:
            continue

    return datetime.max


def event_sort_key(event: Dict):
    return (
        parse_event_datetime(event.get('event_start_time', '')),
        str(event.get('parent_event_id', '')),
        str(event.get('sub_event_id', event.get('event_id', '')))
    )


def infer_parent_event_id(event: Dict):
    """Infer parent id for sub-events like 17_2 when upstream omitted it."""
    parent_event_id = event.get('parent_event_id')
    if parent_event_id not in (None, '', -1, '-1'):
        return parent_event_id

    event_id = event.get('sub_event_id', event.get('event_id'))
    if not isinstance(event_id, str) or '_' not in event_id:
        return parent_event_id

    parent_part = event_id.split('_', 1)[0]
    if parent_part.isdigit():
        return int(parent_part)
    return parent_event_id


def normalize_event_parent_ids(events: List[Dict]) -> Tuple[List[Dict], int]:
    """Copy events and fill missing parent_event_id for encoded sub-event ids."""
    normalized = []
    fixed_count = 0
    for event in events:
        item = dict(event)
        inferred_parent_id = infer_parent_event_id(item)
        if item.get('parent_event_id') in (None, '', -1, '-1') and inferred_parent_id not in (None, '', -1, '-1'):
            item['parent_event_id'] = inferred_parent_id
            fixed_count += 1
        normalized.append(item)
    return normalized, fixed_count


def clamp_importance(value, default: float) -> float:
    """Normalize importance to a float in [0.0, 1.0]."""
    try:
        parsed = float(value)
    except Exception:
        return default
    return max(0.0, min(1.0, parsed))


def normalize_relpath(path: str) -> str:
    return path.replace('\\', '/')


def canonicalize_image_path(path: str) -> str:
    """Normalize image paths to the project-relative image/... form."""
    if not path:
        return ''

    norm = normalize_relpath(str(path).strip())
    image_idx = norm.find('image/')
    if image_idx != -1:
        return norm[image_idx:]

    output_idx = norm.find('output/image/')
    if output_idx != -1:
        return norm[output_idx + len('output/'):]

    return norm


def normalize_image_summary_ref(image_ref: str) -> str:
    """Normalize image summary paths to the same image/... form used in stage5."""
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

    return image_ref.lstrip('/')


def repair_possible_caption_mojibake(text: str) -> str:
    """Repair UTF-8 text that was accidentally decoded as GBK, only when obvious."""
    text = str(text or '').strip()
    if not text:
        return ''

    mojibake_markers = ('鍥', '鐨', '涓', '鏄', '闈', '€', '鈥', '銆')
    if not any(marker in text for marker in mojibake_markers):
        return text

    def score(value: str) -> int:
        cjk = sum(1 for ch in value if '\u4e00' <= ch <= '\u9fff')
        bad = sum(value.count(marker) for marker in mojibake_markers)
        return cjk - bad * 3

    best = text
    best_score = score(text)
    for encoding in ('gbk', 'cp936'):
        try:
            candidate = text.encode(encoding).decode('utf-8')
        except Exception:
            continue
        candidate_score = score(candidate)
        if candidate_score > best_score:
            best = candidate
            best_score = candidate_score
    return best.strip()


def shorten_image_caption_for_reply(caption: str, max_len: int = 32) -> str:
    """Keep image captions concise enough for a natural assistant reply."""
    text = repair_possible_caption_mojibake(caption)
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return ''

    text = re.sub(r'^(?:\u56fe\u7247\u4e3a|\u8fd9\u662f|\u8fd9\u5f20\u56fe\u662f|\u753b\u9762\u662f|\u753b\u9762\u4e2d\u662f|\u56fe\u4e2d\u662f|\u8be5\u56fe\u7247\u4e3a)\s*(?:\u4e00\u5f20)?', '', text)
    text = text.strip(' ，,。.')
    parts = re.split(r'(?<=[。！？!?])\s+', text)
    if parts and parts[0]:
        text = parts[0].strip()
        if len(text) < 35 and len(parts) > 1:
            text = f"{text}{parts[1].strip()}"

        if len(text) > max_len:
            text = text[:max_len].rstrip('，,；;、。.!?！？ ') + '...'
    return text


def join_caption_hints_for_reply(captions: List[str], max_items: int = 2, max_len: int = 70) -> str:
    seen = set()
    selected = []
    for caption in captions:
        text = shorten_image_caption_for_reply(caption, max_len=32)
        if not text or text in seen:
            continue
        seen.add(text)
        selected.append(text)
        if len(selected) >= max_items:
            break
    joined = '；'.join(selected)
    if len(joined) > max_len:
        joined = joined[:max_len].rstrip('，,；;、。.!?！？ ') + '...'
    return joined


def load_image_summary_index(path: Optional[str]) -> Dict[str, Dict]:
    """Load stage10 image summaries and index them by normalized path and filename."""
    if not path or not os.path.exists(path):
        return {}

    by_ref: Dict[str, Dict] = {}
    for record in read_jsonl(path):
        if not isinstance(record, dict):
            continue
        normalized_ref = normalize_image_summary_ref(record.get('image_path', ''))
        filename = str(record.get('filename') or os.path.basename(normalized_ref)).strip()
        if not normalized_ref and not filename:
            continue
        cleaned = dict(record)
        cleaned['_normalized_image_ref'] = normalized_ref
        if normalized_ref:
            by_ref[normalized_ref] = cleaned
        if filename:
            by_ref.setdefault(filename, cleaned)
    return by_ref


def get_image_summary_caption(
    image_summary_index: Optional[Dict[str, Dict]],
    image_file: str,
    chinese: bool = True,
) -> str:
    if not image_summary_index:
        return ''

    normalized_ref = normalize_image_summary_ref(image_file)
    record = image_summary_index.get(normalized_ref) or image_summary_index.get(os.path.basename(normalized_ref))
    if not record:
        return ''

    if chinese:
        caption = record.get('summary_brief') or record.get('summary_zh') or record.get('summary_en') or ''
    else:
        caption = record.get('summary_brief') or record.get('summary_en') or record.get('summary_zh') or ''
    return shorten_image_caption_for_reply(caption)


def get_scenery_variant_index(event_id) -> int:
    """Return a stable scenery variant index in [0, 2] for int or string event ids."""
    try:
        return int(event_id) % 3
    except Exception:
        text = str(event_id or '')
        return sum(ord(ch) for ch in text) % 3


def find_first_existing_file(directory: str, candidates: List[str]) -> Optional[str]:
    for candidate in candidates:
        full_path = os.path.join(directory, candidate)
        if os.path.exists(full_path):
            return candidate
    return None


# ============================================================================
# Image reference scanning
# ============================================================================

SCENERY_KEYWORDS = {
    'food': ['吃', '饭', '餐', '外卖', '火锅', '早餐', '午餐', '晚餐', '咖啡', '美食', '聚餐'],
    'landscape': ['旅游', '旅行', '景点', '公园', '散步', '爬山', '海边', '风景', '露营'],
    'indoor': ['在家', '家里', '宿舍', '办公室', '会议', '学习', '看书', '复盘', '整理', '休息'],
    'weather_calendar': ['天气', '下雨', '暴雨', '降温', '台风', '节日', '日程', '安排', '计划', '日期'],
    'map_location': ['导航', '地图', '出发', '路线', '地址', '到达', '定位', '出行', '通勤', '打车'],
    'news_notification': ['新闻', '通知', '提醒', '公告', '政策', '消息', '热搜', '资讯']
}

IMAGE_TYPE_LABELS_ZH = {
    'person_avatar': '人物头像',
    'event_scene': '事件场景图',
    'social_image': '社交截图',
    'friend': '好友相关图片',
    'book': '阅读应用截图',
    'music': '音乐应用截图',
    'video': '视频应用截图',
    'shopping': '购物应用截图',
    'money': '收支记录截图',
    'ticket': '票据行程截图',
    'group_chat': '群聊截图',
    'group_chat_member_avatar': '群聊成员头像',
    'scenery_food': '餐饮相关场景图',
    'scenery_landscape': '风景相关场景图',
    'scenery_indoor': '室内相关场景图',
    'scenery_weather_calendar': '天气日程相关场景图',
    'scenery_map_location': '地图定位相关场景图',
    'scenery_news_notification': '通知资讯相关场景图',
}

IMAGE_TYPE_LABELS_EN = {
    'person_avatar': 'person portrait',
    'event_scene': 'event scene image',
    'friend': 'friend-related image',
    'book': 'reading app screenshot',
    'music': 'music app screenshot',
    'video': 'video app screenshot',
    'shopping': 'shopping app screenshot',
    'money': 'payment or money screenshot',
    'ticket': 'ticket or itinerary screenshot',
    'group_chat': 'group chat screenshot',
    'group_chat_member_avatar': 'group chat member avatar',
    'scenery_food': 'food-related scene image',
    'scenery_landscape': 'landscape scene image',
    'scenery_indoor': 'indoor scene image',
    'scenery_weather_calendar': 'weather or calendar scene image',
    'scenery_map_location': 'map or location scene image',
    'scenery_news_notification': 'news or notification scene image',
}


def is_chinese_persona(language: Optional[str] = None, nationality: Optional[str] = None) -> bool:
    language_text = str(language or '').strip().lower()
    nationality_text = str(nationality or '').strip().lower()
    return language_text == 'zh' or nationality_text == 'chinese'


def join_names_en(names: List[str]) -> str:
    cleaned = [str(name).strip() for name in names if str(name).strip()]
    if not cleaned:
        return ''
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return f"{', '.join(cleaned[:-1])}, and {cleaned[-1]}"


def resolve_persona_image_layout(uuid: int, image_base_dir: str) -> Dict[str, Optional[str]]:
    """Support both legacy image/ and 328/image/uidX layouts."""
    persona_dir = os.path.join(image_base_dir, f'uid{uuid}')
    use_persona_subdir = os.path.isdir(persona_dir)
    root_dir = persona_dir if use_persona_subdir else image_base_dir
    root_rel = canonicalize_image_path(os.path.relpath(root_dir, PROJECT_ROOT))

    def subdir(name: str) -> str:
        return os.path.join(root_dir, name)

    return {
        'root_dir': root_dir,
        'root_rel': root_rel,
        'persona_dir': persona_dir if use_persona_subdir else None,
        'person_dir': subdir('person'),
        'event_dir': subdir('event'),
        'friend_dir': subdir('friend'),
        'group_chat_dir': subdir('group_chat'),
        'group_chat_members_dir': subdir('group_chat_members'),
        'scenery_dir': subdir('scenery'),
        'book_dir': subdir('book'),
        'music_dir': subdir('music'),
        'video_dir': subdir('video'),
        'shopping_dir': subdir('shopping'),
        'money_dir': subdir('money'),
        'ticket_dir': subdir('ticket'),
    }


def choose_scenery_categories(event: Dict) -> List[str]:
    text = ' '.join([
        str(event.get('event_name', '')),
        str(event.get('description', '')),
        ' '.join(str(x) for x in event.get('additional_info', [])),
    ])

    matched = []
    for category, keywords in SCENERY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            matched.append(category)

    # Keep scenery auxiliary: one strongly matched + one fallback at most.
    if not matched:
        return ['indoor']
    if len(matched) == 1:
        return matched
    return matched[:2]


def parse_image_event_anchor(folder: str, filename: str) -> Optional[str]:
    """Infer the target event/sub-event id from an image filename when possible."""
    base = os.path.splitext(os.path.basename(filename))[0]
    if folder == 'event':
        match = re.match(r'^\d+_event_(.+)$', base)
        return match.group(1) if match else None

    if folder in {'book', 'music', 'video', 'shopping', 'money', 'ticket', 'friend'}:
        match = re.match(r'^\d+_' + re.escape(folder) + r'_(.+)$', base)
        return match.group(1) if match else None

    if folder == 'group_chat':
        match = re.match(r'^\d+_gc_(.+?)_cropped\d+$', base)
        return match.group(1) if match else None

    return None


def parse_group_chat_page_index(filename: str) -> Optional[int]:
    base = os.path.splitext(os.path.basename(filename))[0]
    match = re.match(r'^\d+_gc_.+?_cropped(\d+)$', base)
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def scan_persona_image_coverage_map(
    uuid: int,
    image_base_dir: str,
    events: List[Dict]
) -> Dict[str, List[Dict[str, str]]]:
    """Assign every persona image to a target event/session whenever possible."""
    layout = resolve_persona_image_layout(uuid, image_base_dir)
    root_dir = layout['root_dir']
    root_rel = layout['root_rel']
    event_keys = [str(event.get('event_id')) for event in events if event.get('event_id') not in (None, '')]
    event_key_set = set(event_keys)
    coverage_map: Dict[str, List[Dict[str, str]]] = {event_key: [] for event_key in event_keys}

    folder_type_map = {
        'person': 'person_avatar',
        'event': 'event_scene',
        'friend': 'friend',
        'group_chat': 'group_chat',
        'group_chat_members': 'group_chat_member_avatar',
        'money': 'money',
        'music': 'music',
        'shopping': 'shopping',
        'ticket': 'ticket',
        'video': 'video',
        'book': 'book',
    }

    fallback_queue: List[Dict[str, str]] = []
    seen_paths: Set[str] = set()

    grouped_group_chat_items: Dict[str, List[Tuple[int, Dict[str, str]]]] = defaultdict(list)

    for folder in sorted(list(folder_type_map.keys()) + ['scenery']):
        directory = layout.get(f'{folder}_dir')
        if not directory or not os.path.isdir(directory):
            continue
        for fname in sorted(os.listdir(directory)):
            if not fname.lower().endswith('.png'):
                continue
            rel_path = canonicalize_image_path(os.path.join(root_rel, folder, fname))
            if rel_path in seen_paths:
                continue
            seen_paths.add(rel_path)

            if folder == 'scenery':
                image_type = f"scenery_{os.path.splitext(fname)[0].rsplit('_', 1)[0]}"
            else:
                image_type = folder_type_map[folder]

            item = {"type": image_type, "file": rel_path, "description": ""}
            anchor = parse_image_event_anchor(folder, fname)
            if folder == 'group_chat' and anchor:
                page_index = parse_group_chat_page_index(fname) or 0
                grouped_group_chat_items[anchor].append((page_index, item))
                continue
            if folder == 'group_chat_members' and not anchor:
                member_name = extract_avatar_display_name(rel_path)
                member_name_lower = member_name.lower()
                for event in events:
                    event_key = str(event.get('event_id'))
                    if event_key not in event_key_set:
                        continue
                    event_text = json.dumps(event, ensure_ascii=False).lower()
                    if member_name and (
                        member_name_lower in event_text
                        or member_name_lower.replace(' ', '_') in event_text
                    ):
                        coverage_map[event_key].append(item)
                        break
                else:
                    fallback_queue.append(item)
                continue
            if anchor and anchor in event_key_set:
                coverage_map[anchor].append(item)
            else:
                fallback_queue.append(item)

    for anchor, page_items in grouped_group_chat_items.items():
        ordered_pages = sorted(page_items, key=lambda pair: pair[0])
        total_pages = len(ordered_pages)
        for page_index, item in ordered_pages:
            item["description"] = f"同一段长群聊截图的连续第{page_index}页，共{total_pages}页。"
            if anchor in event_key_set:
                coverage_map[anchor].append(item)
            else:
                fallback_queue.append(item)

    if not event_keys:
        return coverage_map

    for idx, item in enumerate(fallback_queue):
        target_key = event_keys[idx % len(event_keys)]
        coverage_map[target_key].append(item)

    return coverage_map


def augment_image_refs_for_coverage(image_refs: Dict, assigned_images: Optional[List[Dict[str, str]]]) -> Dict:
    """Merge pre-assigned coverage images into a session's candidate image set."""
    if not assigned_images:
        return image_refs

    merged = {
        "person_avatar": image_refs.get("person_avatar"),
        "person_avatar_description": image_refs.get("person_avatar_description"),
        "event_scene": image_refs.get("event_scene"),
        "event_scene_description": image_refs.get("event_scene_description"),
        "extra_images": list(image_refs.get("extra_images", [])),
    }
    existing_paths = set(flatten_allowed_images(merged))

    def add_extra(image_type: str, rel_path: str, description: str = ""):
        rel_path = canonicalize_image_path(rel_path)
        if not rel_path or rel_path in existing_paths:
            return
        merged["extra_images"].append({
            "type": image_type,
            "file": rel_path,
            "description": description or ""
        })
        existing_paths.add(rel_path)

    for item in assigned_images:
        image_type = str(item.get("type") or "").strip()
        rel_path = canonicalize_image_path(item.get("file", ""))
        description = str(item.get("description") or "").strip()
        if not image_type or not rel_path or rel_path in existing_paths:
            continue

        if image_type == 'person_avatar' and not merged.get("person_avatar"):
            merged["person_avatar"] = rel_path
            if description and not merged.get("person_avatar_description"):
                merged["person_avatar_description"] = description
            existing_paths.add(rel_path)
            continue

        if image_type == 'event_scene' and not merged.get("event_scene"):
            merged["event_scene"] = rel_path
            if description and not merged.get("event_scene_description"):
                merged["event_scene_description"] = description
            existing_paths.add(rel_path)
            continue

        add_extra(image_type, rel_path, description)

    return merged


def collect_typed_image_refs(image_refs: Dict) -> List[Dict[str, str]]:
    """Flatten image refs while preserving image type for deterministic memories."""
    typed_images = []
    seen = set()

    def add_item(image_type: str, path: Optional[str], description: Optional[str] = None):
        if not path:
            return
        norm = canonicalize_image_path(path)
        if norm in seen:
            return
        seen.add(norm)
        typed_images.append({
            "type": image_type,
            "file": norm,
            "description": str(description or "").strip(),
        })

    add_item('person_avatar', image_refs.get('person_avatar'), image_refs.get('person_avatar_description'))
    add_item('event_scene', image_refs.get('event_scene'), image_refs.get('event_scene_description'))
    for item in image_refs.get('extra_images', []):
        if not isinstance(item, dict):
            continue
        add_item(
            str(item.get('type', '')).strip() or 'extra_image',
            item.get('file'),
            item.get('description'),
        )

    return typed_images


def infer_image_event_anchor(image_type: str, image_file: str) -> Optional[str]:
    """Infer an event/sub-event anchor from an image path when the filename encodes one."""
    norm_file = canonicalize_image_path(image_file)
    if not norm_file:
        return None
    folder = os.path.basename(os.path.dirname(norm_file))
    filename = os.path.basename(norm_file)
    if folder in {'event', 'book', 'music', 'video', 'shopping', 'money', 'ticket', 'friend', 'group_chat'}:
        return parse_image_event_anchor(folder, filename)
    if image_type == 'event_scene':
        return parse_image_event_anchor('event', filename)
    return None


def build_session_image_usage_plan(
    image_refs: Dict,
    event_id: object,
    introduce_person_avatar: bool = False,
    event_name: str = "",
    image_summary_index: Optional[Dict[str, Dict]] = None,
    chinese: bool = True,
) -> Dict[str, List[Dict[str, str]]]:
    """Split session images into dialogue-required vs memory-only buckets."""
    dialogue_required = []
    memory_only = []
    event_key = str(event_id).strip()

    for item in collect_typed_image_refs(image_refs):
        image_type = str(item.get("type", "")).strip()
        image_file = canonicalize_image_path(item.get("file", ""))
        if not image_file:
            continue
        image_caption = get_image_summary_caption(image_summary_index, image_file, chinese=chinese)
        bucket_item = {
            "type": image_type,
            "file": image_file,
            "description": image_caption or str(item.get("description") or "").strip(),
            "image_caption": image_caption,
            "event_name": str(event_name or "").strip(),
        }
        folder = os.path.basename(os.path.dirname(image_file))

        if image_type == "person_avatar" or folder == "person":
            if introduce_person_avatar:
                dialogue_required.append(bucket_item)
            else:
                memory_only.append(bucket_item)
            continue

        if image_type == "group_chat_member_avatar" or folder == "group_chat_members":
            dialogue_required.append(bucket_item)
            continue

        if image_type.startswith("scenery_") or folder == "scenery":
            continue

        anchor = infer_image_event_anchor(image_type, image_file)
        if anchor and anchor == event_key:
            dialogue_required.append(bucket_item)
        else:
            memory_only.append(bucket_item)

    def sort_key(item: Dict[str, str]):
        image_type = item.get("type", "")
        image_file = item.get("file", "")
        if image_type == "group_chat":
            anchor = parse_image_event_anchor("group_chat", os.path.basename(image_file)) or ""
            page = parse_group_chat_page_index(os.path.basename(image_file)) or 0
            return (image_type, anchor, page, image_file)
        return (image_type, image_file)

    dialogue_required = sorted(dialogue_required, key=sort_key)
    memory_only = sorted(memory_only, key=sort_key)
    return {
        "dialogue_required_images": dialogue_required,
        "memory_only_images": memory_only,
    }


def collect_dialogue_image_refs(dialogue: List[Dict]) -> Set[str]:
    used = set()
    for turn in dialogue:
        if not isinstance(turn, dict):
            continue
        image_inline = turn.get("image_inline")
        if image_inline:
            used.add(canonicalize_image_path(str(image_inline)))
    return used


def build_dialogue_allowed_image_refs(usage_plan: Dict[str, List[Dict[str, str]]]) -> Set[str]:
    """Only these images are allowed to appear in dialogue turns."""
    allowed = set()
    for item in usage_plan.get("dialogue_required_images", []):
        image_file = canonicalize_image_path(item.get("file", ""))
        if image_file:
            allowed.add(image_file)
    return allowed


def extract_avatar_display_name(image_file: str) -> str:
    base = os.path.splitext(os.path.basename(canonicalize_image_path(image_file)))[0]
    base = re.sub(r'^\d+_', '', base)
    base = re.sub(r'_avatar$', '', base)
    base = re.sub(r'_person_\d+$', '', base)
    return base.replace('_', ' ').strip()


def build_required_image_intro_text(
    image_type: str,
    image_file: str = "",
    page_index: Optional[int] = None,
    total_pages: Optional[int] = None,
    chinese: bool = True,
) -> str:
    avatar_name = extract_avatar_display_name(image_file)
    if chinese:
        if image_type == "person_avatar":
            return "\u6211\u5148\u628a\u6211\u7684\u5934\u50cf\u53d1\u7ed9\u4f60\u770b\u4e00\u4e0b\uff0c\u540e\u9762\u8fd9\u4e9b\u7ecf\u5386\u90fd\u56f4\u7ed5\u6211\u6765\u6574\u7406\u3002"
        if image_type == "group_chat_member_avatar":
            if avatar_name:
                return f"\u8fd9\u662f{avatar_name}\u7684\u5934\u50cf\uff0c\u6211\u4e5f\u53d1\u7ed9\u4f60\uff0c\u65b9\u4fbf\u540e\u9762\u5bf9\u5e94\u8fd9\u4e2a\u4eba\u3002"
            return "\u8fd9\u662f\u8fd9\u4f4d\u7fa4\u804a\u6210\u5458\u7684\u5934\u50cf\uff0c\u6211\u4e5f\u53d1\u7ed9\u4f60\uff0c\u65b9\u4fbf\u540e\u9762\u5bf9\u5e94\u8fd9\u4e2a\u4eba\u3002"
        if image_type == "event_scene":
            return "我把当时那个现场画面也发你看一下。"
        if image_type == "friend":
            return "我把那条朋友圈截图也发你看一下。"
        if image_type == "group_chat":
            if page_index and total_pages:
                return f"我把那段群聊往后翻到第{page_index}页也发你看看。"
            return "我把那段群聊截图也发你看一下。"
        if image_type == "shopping":
            return "我把当时的购物页面也发你看一下。"
        if image_type == "money":
            return "我把那笔收支记录页面也发你看一下。"
        if image_type == "book":
            return "我把当时的读书页面也发你看一下。"
        if image_type == "video":
            return "我把当时刷到的那个视频页面也发你看一下。"
        if image_type == "music":
            return "我把那时听歌的页面也发你看一下。"
        if image_type == "ticket":
            return "我把那张票据或行程页面也发你看一下。"
        if image_type.startswith("scenery_"):
            return "我把当时的环境截图也发你看一下。"
        return "我把那张图也发你看一下。"

    if image_type == "person_avatar":
        return "I will send my profile photo first, so the later experiences can stay tied to me as the main person."
    if image_type == "group_chat_member_avatar":
        if avatar_name:
            return f"This is {avatar_name}'s avatar. I am sending it too so we can match this person later."
        return "This is that group chat member's avatar. I am sending it too so we can match this person later."
    if image_type == "event_scene":
        return "I also sent over the scene photo from that moment."
    if image_type == "friend":
        return "I also sent that friend-post screenshot."
    if image_type == "group_chat":
        if page_index and total_pages:
            return f"I also sent page {page_index} from that chat thread."
        return "I also sent that chat screenshot."
    if image_type == "shopping":
        return "I also sent that shopping page."
    if image_type == "money":
        return "I also sent that payment or transfer page."
    if image_type == "book":
        return "I also sent that reading page."
    if image_type == "video":
        return "I also sent that video page."
    if image_type == "music":
        return "I also sent that music page."
    if image_type == "ticket":
        return "I also sent that ticket or itinerary page."
    if image_type.startswith("scenery_"):
        return "I also sent that environment screenshot."
    return "I also sent that image."


def build_required_image_assistant_reply_text(
    image_type: str,
    image_file: str = "",
    image_description: str = "",
    event_name: str = "",
    page_index: Optional[int] = None,
    total_pages: Optional[int] = None,
    chinese: bool = True,
) -> str:
    avatar_name = extract_avatar_display_name(image_file)
    caption_text = shorten_image_caption_for_reply(image_description, max_len=32)
    event_text = str(event_name or "").strip()
    context_text = caption_text or event_text

    def choose(options: List[str]) -> str:
        if not options:
            return ""
        digest = hashlib.sha256(f"{image_type}|{image_file}|{context_text}".encode("utf-8")).hexdigest()
        return options[int(digest[:8], 16) % len(options)]

    if chinese:
        if image_type == "person_avatar":
            return "\u770b\u5230\u4e86\uff0c\u6211\u4f1a\u628a\u8fd9\u5f20\u5934\u50cf\u4f5c\u4e3a\u4f60\u7684\u4e3b\u89d2\u8eab\u4efd\u53c2\u8003\uff0c\u540e\u9762\u518d\u628a\u5177\u4f53\u4e8b\u60c5\u548c\u4f60\u5bf9\u5e94\u8d77\u6765\u3002"
        if image_type == "group_chat_member_avatar":
            if avatar_name:
                return f"\u770b\u5230\u4e86\uff0c\u540e\u9762\u63d0\u5230{avatar_name}\u65f6\uff0c\u6211\u4f1a\u628a\u8fd9\u5f20\u5934\u50cf\u548c\u76f8\u5173\u5bf9\u8bdd\u5bf9\u5e94\u8d77\u6765\u3002"
            return "\u770b\u5230\u4e86\uff0c\u540e\u9762\u63d0\u5230\u8fd9\u4f4d\u7fa4\u804a\u6210\u5458\u65f6\uff0c\u6211\u4f1a\u628a\u8fd9\u5f20\u5934\u50cf\u548c\u76f8\u5173\u5bf9\u8bdd\u5bf9\u5e94\u8d77\u6765\u3002"
        label = IMAGE_TYPE_LABELS_ZH.get(image_type, image_type.replace("_", ""))
        if caption_text:
            return choose([
                f"\u770b\u5230\u4e86\uff0c\u56fe\u91cc\u4e3b\u8981\u662f{caption_text}\uff0c\u8fd9\u80fd\u628a\u521a\u624d\u90a3\u6bb5\u7ecf\u5386\u8865\u5f97\u66f4\u5177\u4f53\u3002",
                f"\u6536\u5230\uff0c\u8fd9\u5f20{label}\u91cc\u80fd\u770b\u5230{caption_text}\uff0c\u540e\u9762\u6574\u7406\u65f6\u6211\u4f1a\u548c\u524d\u9762\u7684\u5185\u5bb9\u5bf9\u4e0a\u3002",
                f"\u660e\u767d\uff0c\u56fe\u91cc\u8fd9\u4e9b\u5173\u4e8e{caption_text}\u7684\u753b\u9762\u4fe1\u606f\uff0c\u53ef\u4ee5\u4f5c\u4e3a\u8fd9\u6bb5\u8bb0\u5f55\u7684\u56fe\u50cf\u8865\u5145\u3002",
                f"\u770b\u5230\u4e86\uff0c\u8fd9\u5f20\u56fe\u8865\u5145\u4e86{caption_text}\uff0c\u6211\u4f1a\u8fde\u7740\u524d\u9762\u7684\u7ecf\u8fc7\u4e00\u8d77\u7406\u89e3\u3002",
            ])
        if event_text:
            return choose([
                f"\u770b\u5230\u4e86\uff0c\u8fd9\u5f20{label}\u548c\u201c{event_text}\u201d\u80fd\u5bf9\u5e94\u8d77\u6765\uff0c\u6211\u4f1a\u628a\u5b83\u5f53\u4f5c\u8fd9\u6bb5\u7ecf\u5386\u7684\u56fe\u50cf\u8865\u5145\u3002",
                f"\u6536\u5230\uff0c\u8fd9\u4e2a{label}\u628a\u201c{event_text}\u201d\u91cc\u7684\u4e00\u4e2a\u5177\u4f53\u753b\u9762\u8865\u4e0a\u4e86\uff0c\u540e\u9762\u6574\u7406\u65f6\u6211\u4f1a\u4e00\u8d77\u53c2\u8003\u3002",
                f"\u660e\u767d\uff0c\u8fd9\u5f20{label}\u53ef\u4ee5\u5e2e\u6211\u628a\u201c{event_text}\u201d\u7684\u65f6\u95f4\u70b9\u548c\u5f53\u65f6\u72b6\u6001\u8bb0\u5f97\u66f4\u51c6\u3002",
                f"\u770b\u5230\u4e86\uff0c\u5b83\u8865\u5145\u7684\u4fe1\u606f\u548c\u201c{event_text}\u201d\u662f\u540c\u4e00\u6bb5\u4e8b\uff0c\u6211\u4f1a\u628a\u6587\u672c\u548c\u56fe\u7247\u653e\u5728\u4e00\u8d77\u7406\u89e3\u3002",
            ])
        label = IMAGE_TYPE_LABELS_ZH.get(image_type, "\u56fe\u7247")
        return choose([
            f"\u770b\u5230\u4e86\uff0c\u8fd9\u5f20{label}\u80fd\u628a\u521a\u624d\u8bf4\u7684\u7ec6\u8282\u8865\u5145\u5f97\u66f4\u76f4\u89c2\u3002",
            f"\u6536\u5230\uff0c\u8fd9\u4e2a{label}\u53ef\u4ee5\u4f5c\u4e3a\u8fd9\u6bb5\u8bb0\u5f55\u7684\u56fe\u50cf\u4f9d\u636e\u3002",
            f"\u660e\u767d\uff0c\u8fd9\u5f20{label}\u80fd\u5e2e\u6211\u628a\u5f53\u65f6\u7684\u60c5\u5883\u548c\u540e\u7eed\u6574\u7406\u5bf9\u4e0a\u3002",
        ])
        if image_type == "event_scene":
            return "\u770b\u5230\u4e86\uff0c\u8fd9\u5f20\u56fe\u80fd\u628a\u5f53\u65f6\u7684\u73b0\u573a\u72b6\u6001\u8865\u5f97\u66f4\u76f4\u89c2\uff0c\u6211\u4f1a\u548c\u524d\u9762\u7684\u7ecf\u8fc7\u4e00\u8d77\u8bb0\u4f4f\u3002"
        if image_type == "friend":
            return "\u770b\u5230\u4e86\uff0c\u8fd9\u6761\u622a\u56fe\u628a\u5f53\u65f6\u7684\u4e92\u52a8\u548c\u53cd\u9988\u8865\u5145\u5f97\u5f88\u6e05\u695a\u3002"
        if image_type == "group_chat":
            if page_index and total_pages:
                return "\u770b\u5230\u4e86\uff0c\u8fd9\u4e00\u9875\u80fd\u8865\u4e0a\u7fa4\u804a\u91cc\u540e\u7eed\u7684\u5206\u5de5\u548c\u53cd\u9988\u3002"
            return "\u770b\u5230\u4e86\uff0c\u8fd9\u5f20\u7fa4\u804a\u622a\u56fe\u80fd\u628a\u5f53\u65f6\u7684\u6c9f\u901a\u7ec6\u8282\u8865\u5145\u5b8c\u6574\u3002"
        if image_type == "shopping":
            return "\u770b\u5230\u4e86\uff0c\u8fd9\u4e2a\u9875\u9762\u80fd\u5bf9\u5e94\u4e0a\u5f53\u65f6\u7684\u9009\u62e9\u548c\u4e0b\u5355\u7ec6\u8282\u3002"
        if image_type == "money":
            return "\u770b\u5230\u4e86\uff0c\u8fd9\u7b14\u8bb0\u5f55\u53ef\u4ee5\u4f5c\u4e3a\u5f53\u65f6\u6536\u652f\u53d8\u5316\u7684\u4f9d\u636e\u3002"
        if image_type == "book":
            return "\u770b\u5230\u4e86\uff0c\u8fd9\u9875\u80fd\u8865\u5145\u5f53\u65f6\u7684\u9605\u8bfb\u5185\u5bb9\u548c\u5173\u6ce8\u70b9\u3002"
        if image_type == "video":
            return "\u770b\u5230\u4e86\uff0c\u8fd9\u4e2a\u89c6\u9891\u9875\u9762\u80fd\u8bf4\u660e\u5f53\u65f6\u4f60\u5237\u5230\u7684\u5185\u5bb9\u548c\u89e6\u53d1\u7684\u60f3\u6cd5\u3002"
        if image_type == "music":
            return "\u770b\u5230\u4e86\uff0c\u8fd9\u4e2a\u542c\u6b4c\u9875\u9762\u4e5f\u80fd\u8865\u5145\u5f53\u65f6\u7684\u72b6\u6001\u548c\u6c1b\u56f4\u3002"
        if image_type == "ticket":
            return "\u770b\u5230\u4e86\uff0c\u8fd9\u5f20\u7968\u636e\u6216\u884c\u7a0b\u4fe1\u606f\u80fd\u628a\u65f6\u95f4\u548c\u5b89\u6392\u5bf9\u5e94\u8d77\u6765\u3002"
        if image_type.startswith("scenery_"):
            return "\u770b\u5230\u4e86\uff0c\u8fd9\u5f20\u73af\u5883\u622a\u56fe\u80fd\u8865\u5145\u5f53\u65f6\u6240\u5728\u7684\u573a\u666f\u3002"
        return "\u770b\u5230\u4e86\uff0c\u8fd9\u5f20\u56fe\u80fd\u628a\u521a\u624d\u8bf4\u7684\u7ec6\u8282\u8865\u5145\u5f97\u66f4\u76f4\u89c2\u3002"

    if image_type == "person_avatar":
        return "Got it. I will use this profile photo as the identity reference for you and connect the later events back to you."
    if image_type == "group_chat_member_avatar":
        if avatar_name:
            return f"Got it. When {avatar_name} comes up later, I will connect this avatar with the related conversation."
        return "Got it. When this group chat member comes up later, I will connect this avatar with the related conversation."
    label = IMAGE_TYPE_LABELS_EN.get(image_type, image_type.replace("_", " "))
    if caption_text:
        return choose([
            f"Got it. The image mainly shows {caption_text}, so it makes that part of the experience more concrete.",
            f"Received. I can see {caption_text} in this {label}, and I will connect it with the surrounding context.",
            f"Understood. The visual detail here is {caption_text}, which helps anchor this part of the record.",
            f"Got it. This image adds the detail of {caption_text}, so I will read it together with the earlier context.",
        ])
    if event_text:
        return choose([
            f"Got it. This {label} lines up with \"{event_text}\", so I will treat it as visual support for that part of the experience.",
            f"Received. This {label} adds a concrete visual detail for \"{event_text}\", and I will keep it with the related context.",
            f"Understood. This {label} helps anchor the timing and state around \"{event_text}\" more clearly.",
            f"Got it. I will connect this image with the same episode described as \"{event_text}\" instead of treating it as a separate item.",
        ])
    return choose([
        f"Got it. This {label} makes the detail you mentioned more concrete.",
        f"Received. This {label} can serve as visual evidence for this part of the record.",
        f"Understood. This {label} helps connect the situation with the later summary.",
    ])
    if image_type == "event_scene":
        return "Got it. This image makes the scene from that moment much clearer, so I will connect it with the earlier details."
    if image_type == "friend":
        return "Got it. This screenshot adds useful context about the interaction and feedback at that time."
    if image_type == "group_chat":
        if page_index and total_pages:
            return "Got it. This page fills in more of the later chat details and follow-up."
        return "Got it. This chat screenshot helps make the communication details more complete."
    if image_type == "shopping":
        return "Got it. This page lines up with the choice and purchase details from that moment."
    if image_type == "money":
        return "Got it. This record helps confirm the payment or spending detail from that time."
    if image_type == "book":
        return "Got it. This page adds context about what you were reading and paying attention to."
    if image_type == "video":
        return "Got it. This video page helps explain what you saw and what it brought to mind."
    if image_type == "music":
        return "Got it. This music page also helps capture the mood and state from that moment."
    if image_type == "ticket":
        return "Got it. This ticket or itinerary page helps anchor the time and arrangement."
    if image_type.startswith("scenery_"):
        return "Got it. This environment screenshot adds useful scene context."
    return "Got it. This image makes the details you mentioned more concrete."


def build_group_chat_bundle_intro_text(total_pages: int, chinese: bool = True) -> str:
    if chinese:
        return f"\u8fd9\u6bb5\u7fa4\u804a\u4e00\u5171{total_pages}\u9875\uff0c\u6211\u4e00\u6b21\u90fd\u53d1\u7ed9\u4f60\uff0c\u4f60\u770b\u5b8c\u518d\u5e2e\u6211\u6574\u7406\u3002"
    return f"This chat thread has {total_pages} pages. I will send all of them together, and you can respond after seeing the full set."


def build_group_chat_bundle_assistant_reply_text(
    total_pages: int,
    chinese: bool = True,
    caption_hint: str = "",
) -> str:
    caption_hint = str(caption_hint or "").strip()
    caption_hint = caption_hint.rstrip('，,；;、。.!?！？ ')
    if chinese:
        if caption_hint:
            return f"\u770b\u5b8c\u4e86\uff0c\u8fd9{total_pages}\u9875\u7fa4\u804a\u91cc\u80fd\u770b\u5230{caption_hint}\uff0c\u6211\u4f1a\u628a\u5b83\u4eec\u4f5c\u4e3a\u540c\u4e00\u6bb5\u5bf9\u8bdd\u6765\u6574\u7406\u3002"
        return f"\u770b\u5b8c\u4e86\uff0c\u8fd9{total_pages}\u9875\u7fa4\u804a\u80fd\u8fde\u8d77\u6765\u770b\u51fa\u5f53\u65f6\u7684\u6c9f\u901a\u987a\u5e8f\u548c\u91cd\u70b9\uff0c\u6211\u4f1a\u628a\u5b83\u4eec\u4f5c\u4e3a\u540c\u4e00\u6bb5\u5bf9\u8bdd\u6765\u6574\u7406\u3002"
    if caption_hint:
        return f"Got it. Across these {total_pages} chat pages, I can see {caption_hint}, so I will treat them as one continuous conversation."
    return f"Got it. These {total_pages} chat pages work as one continuous thread, so I will treat them as one conversation when organizing the details."


def fix_assistant_self_sending_image_text(dialogue: List[Dict]) -> List[Dict]:
    """Correct assistant text that wrongly says the assistant is sending a user image."""
    if not dialogue:
        return dialogue

    def has_following_user_image(index: int) -> bool:
        for offset in (1, 2):
            next_index = index + offset
            if next_index >= len(dialogue):
                continue
            next_turn = dialogue[next_index]
            if next_turn.get("role") == "user" and (next_turn.get("image_inline") or next_turn.get("content_type") == "image"):
                return True
        return False

    def rewrite(text: str) -> str:
        updated = str(text or "")
        for old, new in [
            ("\u6211\u5148\u628a", "\u4f60\u5148\u628a"),
            ("\u6211\u4e5f\u628a", "\u4f60\u4e5f\u628a"),
            ("\u6211\u518d\u628a", "\u4f60\u518d\u628a"),
            ("\u6211\u628a", "\u4f60\u628a"),
            ("\u6211\u4e5f\u53d1", "\u4f60\u4e5f\u53d1"),
            ("\u6211\u5148\u53d1", "\u4f60\u5148\u53d1"),
            ("\u6211\u53d1", "\u4f60\u53d1"),
        ]:
            if old in updated:
                updated = updated.replace(old, new, 1)
                break
        for old, new in [
            ("\u53d1\u7ed9\u4f60\u770b\u770b", "\u53d1\u7ed9\u6211\u770b\u770b"),
            ("\u53d1\u7ed9\u4f60\u770b\u4e00\u4e0b", "\u53d1\u7ed9\u6211\u770b\u4e00\u4e0b"),
            ("\u53d1\u7ed9\u4f60\u770b", "\u53d1\u7ed9\u6211\u770b"),
            ("\u53d1\u4f60\u770b\u770b", "\u53d1\u6211\u770b\u770b"),
            ("\u53d1\u4f60\u770b\u4e00\u4e0b", "\u53d1\u6211\u770b\u4e00\u4e0b"),
            ("\u53d1\u4f60\u770b", "\u53d1\u6211\u770b"),
            ("\u53d1\u4f60", "\u53d1\u6211"),
        ]:
            updated = updated.replace(old, new)
        updated = updated.replace("\u4f60\u786e\u8ba4\u4e0b\u6211\u7406\u89e3\u5f97\u5bf9\u4e0d\u5bf9", "\u6211\u6765\u786e\u8ba4\u4e0b\u7406\u89e3\u5f97\u5bf9\u4e0d\u5bf9")
        updated = updated.replace("\u4f60\u786e\u8ba4\u4e0b", "\u6211\u6765\u786e\u8ba4\u4e0b")
        return updated

    fixed = []
    for index, turn in enumerate(dialogue):
        updated_turn = dict(turn)
        content = updated_turn.get("content")
        if updated_turn.get("role") == "assistant" and isinstance(content, str) and has_following_user_image(index):
            rewritten = rewrite(content)
            if rewritten != content:
                updated_turn["content"] = rewritten
        fixed.append(updated_turn)
    return fixed


def enforce_required_dialogue_images(
    dialogue: List[Dict],
    usage_plan: Dict[str, List[Dict[str, str]]],
    persona_language: Optional[str] = None,
    persona_nationality: Optional[str] = None,
) -> Tuple[List[Dict], Dict[str, List[int]], int]:
    """Append missing dialogue-required images as natural user image turns with assistant replies."""
    if not dialogue:
        dialogue = []

    chinese = is_chinese_persona(persona_language, persona_nationality)
    used_images = collect_dialogue_image_refs(dialogue)
    required_images = usage_plan.get("dialogue_required_images", [])

    group_chat_totals = defaultdict(int)
    for item in required_images:
        if item.get("type") != "group_chat":
            continue
        anchor = parse_image_event_anchor("group_chat", os.path.basename(item.get("file", "")))
        if anchor:
            group_chat_totals[anchor] += 1

    normalized = [dict(turn) for turn in dialogue]
    normalized = fix_assistant_self_sending_image_text(normalized)
    inserted_turn_map: Dict[str, List[int]] = {}
    missing_items = []

    for item in required_images:
        image_file = canonicalize_image_path(item.get("file", ""))
        image_type = str(item.get("type", "")).strip()
        if not image_file or image_file in used_images:
            continue
        page_index = None
        total_pages = None
        if image_type == "group_chat":
            filename = os.path.basename(image_file)
            page_index = parse_group_chat_page_index(filename)
            anchor = parse_image_event_anchor("group_chat", filename)
            if anchor:
                total_pages = group_chat_totals.get(anchor)
        missing_items.append((
            image_type,
            image_file,
            page_index,
            total_pages,
            str(item.get("description") or "").strip(),
            str(item.get("event_name") or "").strip(),
        ))

    def make_image_exchange(
        image_type: str,
        image_file: str,
        page_index: Optional[int],
        total_pages: Optional[int],
        image_description: str,
        event_name: str,
        start_turn: int,
    ) -> Tuple[List[Dict], List[int]]:
        intro_turn = start_turn
        image_turn = start_turn + 1
        assistant_turn = start_turn + 2
        turns = [
            {
                "turn": intro_turn,
                "role": "user",
                "content": build_required_image_intro_text(
                    image_type,
                    image_file=image_file,
                    page_index=page_index,
                    total_pages=total_pages,
                    chinese=chinese,
                ),
                "content_type": "text",
            },
            {
                "turn": image_turn,
                "role": "user",
                "image_inline": image_file,
                "content_type": "image",
            },
            {
                "turn": assistant_turn,
                "role": "assistant",
                "content": build_required_image_assistant_reply_text(
                    image_type,
                    image_file=image_file,
                    image_description=image_description,
                    event_name=event_name,
                    page_index=page_index,
                    total_pages=total_pages,
                    chinese=chinese,
                ),
                "content_type": "text",
            },
        ]
        return turns, [intro_turn, image_turn, assistant_turn]

    def group_chat_bundle_key(item: Tuple) -> Optional[str]:
        image_type, image_file, _page_index, _total_pages = item[:4]
        if image_type != "group_chat":
            return None
        return parse_image_event_anchor("group_chat", os.path.basename(image_file))

    def make_group_chat_bundle_exchange(
        items: List[Tuple],
        start_turn: int,
    ) -> Tuple[List[Dict], Dict[str, List[int]]]:
        ordered = sorted(items, key=lambda item: item[2] or 0)
        total_pages = ordered[0][3] or len(ordered)
        turns = [{
            "turn": start_turn,
            "role": "user",
            "content": build_group_chat_bundle_intro_text(total_pages, chinese=chinese),
            "content_type": "text",
        }]
        turn_map: Dict[str, List[int]] = {}
        current = start_turn + 1
        image_turns = []
        for item in ordered:
            _image_type, image_file, _page_index, _total_pages = item[:4]
            turns.append({
                "turn": current,
                "role": "user",
                "image_inline": image_file,
                "content_type": "image",
            })
            image_turns.append(current)
            current += 1
        assistant_turn = current
        caption_hint = join_caption_hints_for_reply([item[4] for item in ordered])
        turns.append({
            "turn": assistant_turn,
            "role": "assistant",
            "content": build_group_chat_bundle_assistant_reply_text(
                total_pages,
                chinese=chinese,
                caption_hint=caption_hint,
            ),
            "content_type": "text",
        })
        intro_turn = start_turn
        for item, image_turn in zip(ordered, image_turns):
            _image_type, image_file, _page_index, _total_pages = item[:4]
            turn_map[image_file] = [intro_turn, image_turn, assistant_turn]
        return turns, turn_map

    prepend_items = [
        item for item in missing_items
        if item[0] == "person_avatar" or os.path.basename(os.path.dirname(item[1])) == "person"
    ]
    append_items = [item for item in missing_items if item not in prepend_items]
    prepended_turn_count = len(prepend_items) * 3

    if prepend_items:
        prepended_turns = []
        current_turn = 1
        for image_type, image_file, page_index, total_pages, image_description, event_name in prepend_items:
            exchange_turns, turn_ids = make_image_exchange(
                image_type, image_file, page_index, total_pages, image_description, event_name, current_turn
            )
            prepended_turns.extend(exchange_turns)
            inserted_turn_map[image_file] = turn_ids
            current_turn += 3
            used_images.add(image_file)

        for turn in normalized:
            turn["turn"] = int(turn.get("turn", 0) or 0) + prepended_turn_count
        normalized = prepended_turns + normalized
        current_turn = max([int(turn.get("turn", 0)) for turn in normalized if isinstance(turn, dict)] or [0]) + 1
    else:
        current_turn = max([int(turn.get("turn", 0)) for turn in normalized if isinstance(turn, dict)] or [0]) + 1

    grouped_append_items: List[List[Tuple]] = []
    consumed_append_indexes: Set[int] = set()
    group_chat_indexes: Dict[str, List[int]] = defaultdict(list)
    for idx, item in enumerate(append_items):
        key = group_chat_bundle_key(item)
        if key:
            group_chat_indexes[key].append(idx)

    for idx, item in enumerate(append_items):
        if idx in consumed_append_indexes:
            continue
        key = group_chat_bundle_key(item)
        if key and len(group_chat_indexes.get(key, [])) > 1:
            indexes = group_chat_indexes[key]
            grouped_append_items.append([append_items[i] for i in indexes])
            consumed_append_indexes.update(indexes)
        else:
            grouped_append_items.append([item])
            consumed_append_indexes.add(idx)

    for item_group in grouped_append_items:
        intro_turn = current_turn
        if len(item_group) > 1 and group_chat_bundle_key(item_group[0]):
            exchange_turns, turn_ids_by_image = make_group_chat_bundle_exchange(item_group, intro_turn)
            normalized.extend(exchange_turns)
            inserted_turn_map.update(turn_ids_by_image)
            current_turn += len(exchange_turns)
            for item in item_group:
                _image_type, image_file, _page_index, _total_pages = item[:4]
                used_images.add(image_file)
        else:
            image_type, image_file, page_index, total_pages, image_description, event_name = item_group[0]
            exchange_turns, turn_ids = make_image_exchange(
                image_type, image_file, page_index, total_pages, image_description, event_name, intro_turn
            )
            normalized.extend(exchange_turns)
            inserted_turn_map[image_file] = turn_ids
            current_turn += 3
            used_images.add(image_file)

    if normalized:
        last_turn = normalized[-1]
        if isinstance(last_turn, dict) and (last_turn.get("content_type") == "image" or last_turn.get("image_inline")):
            image_file = canonicalize_image_path(str(last_turn.get("image_inline") or ""))
            image_type = ""
            page_index = None
            total_pages = None
            image_description = ""
            event_name = ""
            for item in required_images:
                if canonicalize_image_path(item.get("file", "")) == image_file:
                    image_type = str(item.get("type", "")).strip()
                    image_description = str(item.get("description") or item.get("image_caption") or "").strip()
                    event_name = str(item.get("event_name") or "").strip()
                    if image_type == "group_chat":
                        filename = os.path.basename(image_file)
                        page_index = parse_group_chat_page_index(filename)
                        anchor = parse_image_event_anchor("group_chat", filename)
                        if anchor:
                            total_pages = group_chat_totals.get(anchor)
                    break
            normalized.append({
                "turn": current_turn,
                "role": "assistant",
                "content": build_required_image_assistant_reply_text(
                    image_type,
                    image_file=image_file,
                    image_description=image_description,
                    event_name=event_name,
                    page_index=page_index,
                    total_pages=total_pages,
                    chinese=chinese,
                ),
                "content_type": "text",
            })

    return normalized, inserted_turn_map, prepended_turn_count


def merge_image_memory_turn_ids(
    memory_points: List[Dict],
    image_turn_map: Dict[str, List[int]],
) -> List[Dict]:
    """Attach appended dialogue turns back onto deterministic image memories."""
    if not memory_points or not image_turn_map:
        return memory_points

    merged = []
    for memory in memory_points:
        updated = dict(memory)
        existing_turns = normalize_stage5_turn_ids(updated.get("dialogue_turn_ids"))
        image_refs = updated.get("image_refs", []) or []
        extra_turns: List[int] = []
        for image_ref in image_refs:
            norm_ref = canonicalize_image_path(str(image_ref))
            extra_turns.extend(image_turn_map.get(norm_ref, []))
        updated["dialogue_turn_ids"] = sorted(set(existing_turns + [turn for turn in extra_turns if turn > 0]))
        merged.append(updated)
    return merged


def get_event_participants(event: Dict, persona_name: Optional[str] = None) -> List[str]:
    participants = event.get('participants', [])
    if isinstance(participants, str):
        participants = [participants] if participants.strip() else []
    elif not isinstance(participants, list):
        participants = []

    cleaned = []
    if persona_name:
        persona_text = str(persona_name).strip()
        if persona_text:
            cleaned.append(persona_text)

    for item in participants:
        text = str(item).strip()
        if text and text not in cleaned:
            cleaned.append(text)

    return cleaned


def format_participants_text(event: Dict, persona_name: Optional[str] = None) -> str:
    return '、'.join(get_event_participants(event, persona_name))


def extract_event_action_summary(description: str, event_name: str, max_len: int = 28) -> str:
    name_text = re.sub(r'\s+', '', str(event_name or '').strip())
    desc_text = re.sub(r'\s+', '', str(description or '').strip())

    if name_text:
        if '工作规划' in name_text:
            name_text = "讨论工作规划"
        elif '车票' in name_text:
            name_text = f"购买{name_text}"
        else:
            action_keywords = [
                '商讨', '讨论', '沟通', '处理', '购买', '整理', '提交', '汇报', '安排',
                '咨询', '确认', '规划', '制作', '分享', '发布', '预约', '复盘', '申请', '采购',
                '挑选', '研究', '尝试', '设计', '加班', '准备'
            ]
            for keyword in action_keywords:
                idx = name_text.find(keyword)
                if idx != -1:
                    name_text = name_text[idx:]
                    break
            else:
                name_text = f"处理{name_text}"
        if len(name_text) > max_len:
            name_text = name_text[:max_len].rstrip('，,、 ')
        if name_text:
            return name_text

    if not desc_text:
        return ''

    for sep in ['。', '；', ';', '！', '？', '\n', '，', ',']:
        if sep in desc_text:
            desc_text = desc_text.split(sep, 1)[0].strip()
            break

    desc_text = re.sub(r'^(当时|当天|那天|这次|本次|此次)', '', desc_text).strip()
    desc_text = re.sub(r'^(我和|我们)', '', desc_text).strip()
    if any(token in desc_text for token in ['我叫', '出生', '安徽人']):
        return ''
    if len(desc_text) > max_len:
        desc_text = desc_text[:max_len].rstrip('，,、 ')
    return desc_text


def summarize_participants(event: Dict, persona_name: Optional[str] = None, max_people: int = 3) -> str:
    people = get_event_participants(event, persona_name)[:max_people]
    return '、'.join(people)


def count_participants(event: Dict, persona_name: Optional[str] = None, max_people: int = 3) -> int:
    return len(get_event_participants(event, persona_name)[:max_people])


def build_event_intent_summary(event_name: str, action_summary: str, persona_name: Optional[str] = None) -> str:
    actor = str(persona_name or '').strip() or '他'
    event_name = str(event_name or '').strip()
    action_summary = str(action_summary or '').strip()
    text = f"{event_name}{action_summary}"

    if any(keyword in text for keyword in ['求助', '帮忙', '代收快递']):
        return f"这说明{actor}愿意顺手帮身边的人分担事情。"

    intent_rules = [
        (['准备', '筹备'], f"这反映出{actor}正在为相关事项做具体准备。"),
        (['商讨', '讨论', '沟通'], f"这反映出{actor}正在就关键细节做沟通和确认。"),
        (['购买', '下单', '挑选'], f"这反映出{actor}正在为后续安排做实际准备。"),
        (['处理', '整理', '提交', '汇报'], f"这说明{actor}想尽快推进当前任务。"),
        (['分享', '回复', '发布'], f"这表达了{actor}希望把相关信息及时传达出去。"),
        (['预约', '咨询', '确认'], f"这说明{actor}正在落实下一步安排。"),
        (['规划', '安排'], f"这反映出{actor}希望把后续节奏提前安排清楚。"),
    ]
    for keywords, summary in intent_rules:
        if any(keyword in text for keyword in keywords):
            return summary
    return ''


def build_natural_event_scene_action(
    event: Dict,
    action_summary: str,
    persona_name: Optional[str] = None
) -> str:
    event_name = str(event.get('event_name', '')).strip()
    participants = get_event_participants(event, persona_name)
    others = [p for p in participants if p != (persona_name or '').strip()]

    if '求助代收快递' in event_name:
        target = others[0] if others else '对方'
        return f"在{target}求助后帮忙代收快递"
    if '求助' in event_name and '快递' in event_name:
        target = others[0] if others else '对方'
        return f"在{target}求助后处理快递相关事务"
    if '工作规划' in event_name:
        return "讨论工作规划"
    if '车票' in event_name:
        return "查看并购买相关车票"
    if '采购食材' in event_name:
        return "采购聚会要用的食材"
    if '请柬设计' in event_name:
        return "商量请柬设计细节"
    if '数据报表' in event_name:
        return "加班整理数据报表"
    if '紧急文件' in event_name:
        return "加班处理紧急文件"
    if '遗留文件' in event_name:
        return "加班处理遗留文件"

    return action_summary


def build_image_grounded_memory_content(
    image_type: str,
    event: Dict,
    image_refs: Dict,
    persona_name: Optional[str] = None,
    persona_language: Optional[str] = None,
    persona_nationality: Optional[str] = None
) -> str:
    event_name = str(event.get('event_name', '')).strip() or '该事件'
    if not is_chinese_persona(persona_language, persona_nationality):
        event_name_en = str(event.get('event_name', '')).strip() or 'this event'
        participants_en = join_names_en(get_event_participants(event, persona_name))
        image_label_en = IMAGE_TYPE_LABELS_EN.get(image_type, image_type.replace('_', ' '))
        if image_type == 'event_scene':
            if participants_en:
                return f"This {image_label_en} captures {participants_en} during \"{event_name_en}\"."
            return f"This {image_label_en} captures a key moment from \"{event_name_en}\"."
        if image_type == 'person_avatar':
            if participants_en:
                return f"This {image_label_en} corresponds to {participants_en}, showing the main people involved in \"{event_name_en}\"."
            return f"This {image_label_en} identifies one of the main people involved in \"{event_name_en}\"."
        if image_type == 'group_chat':
            if participants_en:
                return f"This {image_label_en} records discussion among {participants_en} about \"{event_name_en}\"."
            return f"This {image_label_en} reflects discussion related to \"{event_name_en}\"."
        if image_type in {'book', 'music', 'video', 'shopping'}:
            if participants_en:
                return f"This {image_label_en} records app activity by {participants_en} related to \"{event_name_en}\"."
            return f"This {image_label_en} preserves app activity related to \"{event_name_en}\"."
        if image_type.startswith('scenery_'):
            return f"This {image_label_en} supplements the place, time, or surrounding context of \"{event_name_en}\"."
        if participants_en:
            return f"This image records clues about {participants_en} in \"{event_name_en}\"."
        return f"This image preserves clues related to \"{event_name_en}\"."

    description = str(event.get('description', '')).strip()
    participants_text = summarize_participants(event, persona_name)
    participant_count = count_participants(event, persona_name)
    image_label = IMAGE_TYPE_LABELS_ZH.get(image_type, image_type)
    action_summary = extract_event_action_summary(description, event_name)
    scene_action = build_natural_event_scene_action(event, action_summary, persona_name)
    intent_summary = build_event_intent_summary(event_name, action_summary, persona_name)

    if image_type == 'event_scene':
        if participants_text and scene_action:
            lead_actor = str(persona_name or '').strip() or participants_text.split('、')[0]
            text = f"这张{image_label}记录了{lead_actor}{scene_action}。"
            if intent_summary:
                text += intent_summary
            return text
        if participants_text:
            return f"这张{image_label}记录了{participants_text}在“{event_name}”中的核心场景。"
        if scene_action:
            text = f"这张{image_label}记录了{scene_action}的场景。"
            if intent_summary:
                text += intent_summary
            return text
        return f"这张{image_label}记录了“{event_name}”的核心场景。"
    if image_type == 'person_avatar':
        if participants_text:
            subject_text = '他是' if participant_count == 1 else '他们是'
            text = f"这张{image_label}对应{participants_text}，说明{subject_text}“{event_name}”中的主要人物。"
            if action_summary:
                text += f"{str(persona_name or '').strip() or participants_text}正在围绕{action_summary}推进这件事。"
            return text
        return f"这张{image_label}用于标识“{event_name}”中的主角形象。"
    if image_type == 'group_chat':
        if participants_text:
            text = f"这张{image_label}记录了{participants_text}围绕“{event_name}”展开的讨论。"
            if intent_summary:
                text += intent_summary
            else:
                text += "大家主要在沟通具体安排或交换意见。"
            return text
        return f"这张{image_label}反映了围绕“{event_name}”的讨论内容。"
    if image_type in {'book', 'music', 'video', 'shopping'}:
        if participants_text:
            app_action = action_summary or "查看相关内容"
            text = f"这张{image_label}记录了{participants_text}在“{event_name}”中通过应用{app_action}。"
            if intent_summary:
                text += intent_summary
            return text
        return f"这张{image_label}保留了“{event_name}”相关的应用使用或浏览记录。"
    if image_type.startswith('scenery_'):
        return f"这张{image_label}补充了“{event_name}”发生时的地点、天气或时间背景。"
    if participants_text:
        text = f"这张图片记录了{participants_text}在“{event_name}”中的相关线索。"
        if intent_summary:
            text += intent_summary
        return text
    return f"这张图片保留了“{event_name}”的相关线索。"


def build_image_grounded_memories(
    uuid: int,
    event_id: int,
    event: Dict,
    image_refs: Dict,
    persona_name: Optional[str] = None,
    persona_language: Optional[str] = None,
    persona_nationality: Optional[str] = None
) -> List[Dict]:
    """Generate one deterministic event-grounded memory per candidate image."""
    timestamp = format_timestamp(event.get('event_start_time', ''))
    typed_images = collect_typed_image_refs(image_refs)
    memories = []
    seen_image_files: Set[str] = set()

    for idx, item in enumerate(typed_images):
        image_type = item['type']
        image_file = canonicalize_image_path(item['file'])
        if not image_file or image_file in seen_image_files:
            continue
        if image_type.startswith('scenery_') or os.path.basename(os.path.dirname(image_file)) == 'scenery':
            continue
        seen_image_files.add(image_file)
        memories.append({
            "memory_id": f"{uuid}_{event_id}_img_{idx}",
            "memory_source": "primary",
            "memory_type": "Image Memory",
            "memory_content": build_image_grounded_memory_content(
                image_type,
                event,
                image_refs,
                persona_name,
                persona_language,
                persona_nationality
            ),
            "timestamp": timestamp,
            "importance": 0.7 if image_type.startswith('scenery_') else 0.8,
            "is_update": False,
            "original_memories": [],
            "image_refs": [image_file]
        })

    return memories


def build_session_memory_fields(
    system_memories: List[Dict],
    shared_parent_memories: List[Dict],
    child_event_memories: Optional[List[Dict]] = None
) -> Dict[str, List[Dict]]:
    """Keep backward-compatible full memories while exposing true session-local memories."""
    own_memory_points = list(system_memories) + list(child_event_memories or [])
    all_memory_points = own_memory_points + list(shared_parent_memories)
    return {
        "own_memory_points": own_memory_points,
        "memory_points": all_memory_points,
    }


def build_candidate_image_refs(uuid: int, event: Dict, image_base_dir: str) -> Dict:
    """Collect all image candidates for a given uuid/event_id from either layout."""
    event_id = event.get('event_id', 0)
    layout = resolve_persona_image_layout(uuid, image_base_dir)

    refs = {
        "person_avatar": None,
        "person_avatar_description": None,
        "event_scene": None,
        "event_scene_description": None,
        "extra_images": []
    }

    def add_extra(image_type: str, rel_path: str, description: Optional[str] = None):
        rel_path = canonicalize_image_path(rel_path)
        existing = {item['file'] for item in refs["extra_images"]}
        if rel_path in existing:
            return
        refs["extra_images"].append({
            "type": image_type,
            "file": rel_path,
            "description": description or ""
        })

    direct_images = event.get('images', [])
    if isinstance(direct_images, list) and direct_images:
        for item in direct_images:
            if not isinstance(item, dict):
                continue
            image_type = str(item.get('type', '')).strip()
            image_path = canonicalize_image_path(item.get('image_path', ''))
            image_desc = str(item.get('description', '') or '').strip()
            if not image_type or not image_path:
                continue

            if image_type in {'person', 'person_avatar'} and not refs["person_avatar"]:
                refs["person_avatar"] = image_path
                refs["person_avatar_description"] = image_desc
                continue

            if image_type == 'event_scene' and not refs["event_scene"]:
                refs["event_scene"] = image_path
                refs["event_scene_description"] = image_desc
                continue

            add_extra(image_type, image_path, image_desc)

        if refs["person_avatar"] or refs["event_scene"] or refs["extra_images"]:
            return refs

    person_dir = layout['person_dir']
    if os.path.exists(person_dir):
        for fname in sorted(os.listdir(person_dir)):
            if not fname.endswith('.png'):
                continue
            if fname.startswith(f"{uuid}_person_") or fname.startswith(f"{event_id}_person_"):
                refs["person_avatar"] = canonicalize_image_path(os.path.join(layout['root_rel'], 'person', fname))
                break

    event_dir = layout['event_dir']
    if os.path.exists(event_dir):
        event_candidates = [
            f"{uuid}_event_{event_id}.png",
            f"{event_id}_event.png",
            f"{uuid}_event.png",
        ]
        found = find_first_existing_file(event_dir, event_candidates)
        if found:
            refs["event_scene"] = canonicalize_image_path(os.path.join(layout['root_rel'], 'event', found))

    app_dirs = {
        'book': layout['book_dir'],
        'music': layout['music_dir'],
        'video': layout['video_dir'],
        'shopping': layout['shopping_dir'],
    }
    for image_type, directory in app_dirs.items():
        if not os.path.exists(directory):
            continue
        candidates = [
            f"{uuid}_{image_type}_{event_id}.png",
            f"{event_id}_{image_type}.png",
        ]
        found = find_first_existing_file(directory, candidates)
        if found:
            add_extra(image_type, os.path.join(layout['root_rel'], image_type, found))

    group_chat_dir = layout['group_chat_dir']
    if os.path.exists(group_chat_dir):
        group_candidates = [
            f"{uuid}_gc_{event_id}_cropped.png",
            f"{uuid}_gc_{event_id}.png",
        ]
        found = find_first_existing_file(group_chat_dir, group_candidates)
        if found:
            add_extra('group_chat', os.path.join(layout['root_rel'], 'group_chat', found))

    scenery_dir = layout['scenery_dir']
    if os.path.exists(scenery_dir):
        scenery_variant_idx = get_scenery_variant_index(event_id)
        for category in choose_scenery_categories(event):
            candidates = [
                f"scenery_{uuid}_{category}_{scenery_variant_idx}.png",
                f"scenery_{uuid}_{category}_0.png",
            ]
            found = find_first_existing_file(scenery_dir, candidates)
            if found:
                add_extra(f"scenery_{category}", os.path.join(layout['root_rel'], 'scenery', found))

    return refs


def flatten_allowed_images(image_refs: Dict) -> List[str]:
    allowed = []
    for key in ['person_avatar', 'event_scene']:
        if image_refs.get(key):
            allowed.append(image_refs[key])
    for item in image_refs.get('extra_images', []):
        if isinstance(item, dict) and item.get('file'):
            allowed.append(item['file'])
    seen = []
    for path in allowed:
        if path not in seen:
            seen.append(path)
    return seen


def collect_session_image_stats(image_refs: Dict, dialogue: List[Dict], memory_points: List[Dict]) -> Dict:
    """Collect lightweight image and turn statistics for one session."""
    candidate_images = flatten_allowed_images(image_refs)
    inline_images = []
    for turn in dialogue:
        image_inline = turn.get('image_inline')
        if image_inline:
            inline_images.append(normalize_relpath(str(image_inline)))

    memory_images = []
    for memory in memory_points:
        for ref in memory.get('image_refs', []) or []:
            memory_images.append(normalize_relpath(str(ref)))

    used_unique = []
    for path in inline_images + memory_images:
        if path and path not in used_unique:
            used_unique.append(path)

    return {
        "dialogue_turn_count": len(dialogue),
        "image_candidate_count": len(candidate_images),
        "image_inline_count": len(inline_images),
        "memory_image_ref_count": len(memory_images),
        "unique_image_count": len(used_unique),
        "dialogue_output_tokens": 0,
    }


# ============================================================================
# System memory generation (no LLM)
# ============================================================================

def generate_system_memories(persona: Dict, uuid: int, event_id: int) -> List[Dict]:
    """Generate system memories from Basic_Profile and Init_State (no LLM)."""
    bp = persona.get('Basic_Profile', {})
    init = persona.get('Init_State', {})
    memories = []

    ts = format_timestamp("2025-01-01 00:00:00")

    # Core identity memory
    name = bp.get('name', 'Unknown')
    gender = bp.get('gender', 'Unknown')
    birth_date = bp.get('birth_date', 'Unknown')
    nationality = bp.get('nationality', 'Unknown')
    language = persona.get('language') or bp.get('language')
    chinese_persona = is_chinese_persona(language, nationality)
    description = init.get('description', '')
    career = init.get('career', '')
    location = init.get('location', '')

    memories.append({
        "memory_id": f"{uuid}_{event_id}_sys_0",
        "memory_source": "system",
        "memory_type": "Persona Memory",
        "memory_content": description if description else (
            f"{name}是一位{nationality}人物。" if chinese_persona else f"{name} is a {nationality} person."
        ),
        "timestamp": ts,
        "importance": 1.0,
        "is_update": False,
        "original_memories": [],
        "image_refs": []
    })

    # Career memory
    if career:
        memories.append({
            "memory_id": f"{uuid}_{event_id}_sys_1",
            "memory_source": "system",
            "memory_type": "Persona Memory",
            "memory_content": f"{name}的职业信息：{career}。" if chinese_persona else f"{name}'s career: {career}.",
            "timestamp": ts,
            "importance": 0.9,
            "is_update": False,
            "original_memories": [],
            "image_refs": []
        })

    # Location memory
    if location:
        memories.append({
            "memory_id": f"{uuid}_{event_id}_sys_2",
            "memory_source": "system",
            "memory_type": "Persona Memory",
            "memory_content": f"{name}的常住和工作地点：{location}。" if chinese_persona else f"{name} lives and works in {location}.",
            "timestamp": ts,
            "importance": 0.85,
            "is_update": False,
            "original_memories": [],
            "image_refs": []
        })

    # Social relationships
    social = init.get('social_relationships', {})
    if social:
        rel_summary = "; ".join([f"{k}: {v}" for k, v in list(social.items())[:3]])
        memories.append({
            "memory_id": f"{uuid}_{event_id}_sys_3",
            "memory_source": "system",
            "memory_type": "Persona Memory",
            "memory_content": f"{name}的关键社会关系：{rel_summary}。" if chinese_persona else f"{name}'s key relationships: {rel_summary}.",
            "timestamp": ts,
            "importance": 0.8,
            "is_update": False,
            "original_memories": [],
            "image_refs": []
        })

    return memories


# ============================================================================
# LLM memory-first generation
# ============================================================================

def build_memory_generation_prompt(
    persona: Dict, event: Dict, system_memories: List[Dict],
    image_refs: Dict, prompt_template: str
) -> str:
    """Build the prompt for event memory generation."""
    bp = persona.get('Basic_Profile', {})
    init = persona.get('Init_State', {})

    persona_info = json.dumps({
        "name": bp.get('name'),
        "gender": bp.get('gender'),
        "birth_date": bp.get('birth_date'),
        "nationality": bp.get('nationality'),
        "description": init.get('description'),
        "career": init.get('career'),
        "location": init.get('location'),
        "preferences": init.get('preferences', {}),
        "social_relationships": init.get('social_relationships', {})
    }, ensure_ascii=False, indent=2)

    event_info = json.dumps({
        "event_id": event.get('event_id'),
        "parent_event_id": event.get('parent_event_id'),
        "sub_event_id": event.get('sub_event_id'),
        "event_source": event.get('event_source'),
        "event_name": event.get('event_name'),
        "event_start_time": event.get('event_start_time'),
        "event_end_time": event.get('event_end_time'),
        "description": event.get('description'),
        "importance": event.get('importance'),
        "participants": event.get('participants', []),
        "additional_info": event.get('additional_info', []),
        "group_chat_messages": event.get('group_chat_messages', []),
    }, ensure_ascii=False, indent=2)

    sys_mem_str = json.dumps([
        {"memory_id": m["memory_id"], "memory_content": m["memory_content"]}
        for m in system_memories
    ], ensure_ascii=False, indent=2)

    available_images = []
    if image_refs.get("person_avatar"):
        line = f"person_avatar: {canonicalize_image_path(image_refs['person_avatar'])}"
        if image_refs.get("person_avatar_description"):
            line += f" | description: {image_refs['person_avatar_description']}"
        available_images.append(line)
    if image_refs.get("event_scene"):
        line = f"event_scene: {canonicalize_image_path(image_refs['event_scene'])}"
        if image_refs.get("event_scene_description"):
            line += f" | description: {image_refs['event_scene_description']}"
        available_images.append(line)
    for extra in image_refs.get("extra_images", []):
        if isinstance(extra, dict) and extra.get('file'):
            line = f"{extra.get('type', 'extra_image')}: {canonicalize_image_path(extra['file'])}"
            if extra.get('description'):
                line += f" | description: {extra['description']}"
            available_images.append(line)
    images_str = "\n".join(available_images) if available_images else "(none)"

    uuid = persona.get('uuid', 0)
    event_id = event.get('event_id', 0)

    # Use simple string replacement to avoid conflicts with JSON braces in template
    result = prompt_template
    result = result.replace('{persona_info}', persona_info)
    result = result.replace('{event_info}', event_info)
    result = result.replace('{system_memories}', sys_mem_str)
    result = result.replace('{available_images}', images_str)
    result = result.replace('{uuid}', str(uuid))
    result = result.replace('{event_id}', str(event_id))
    return result


def build_dialogue_generation_prompt(
    persona: Dict,
    event: Dict,
    system_memories: List[Dict],
    image_refs: Dict,
    shared_parent_memories: List[Dict],
    child_event_memories: Optional[List[Dict]],
    prompt_template: str
) -> str:
    """Build the prompt for dialogue generation from memory points."""
    base_prompt = build_memory_generation_prompt(
        persona, event, system_memories, image_refs, prompt_template
    )
    child_event_memories = child_event_memories or []
    memory_points = list(shared_parent_memories) + list(child_event_memories)
    memory_points_str = json.dumps(memory_points, ensure_ascii=False, indent=2)
    result = base_prompt.replace('{event_memory_points}', memory_points_str)

    if child_event_memories:
        shared_parent_str = json.dumps(shared_parent_memories, ensure_ascii=False, indent=2)
        child_memory_str = json.dumps(child_event_memories, ensure_ascii=False, indent=2)
        staged_constraints = """

## 对话覆盖顺序要求
当前事件同时包含父级共享记忆和子事件新增记忆。生成对话时必须遵守以下顺序：

### 第一阶段：先覆盖父级共享记忆
{shared_parent_memories}
- 对话前半段优先自然覆盖这些父级共享记忆，先把主事件背景、共同上下文、关键事实交代清楚
- 不要求逐条机械复述，但必须让读者能从对话里感受到主事件共享信息已被覆盖

### 第二阶段：再覆盖子事件新增记忆
{child_event_memories}
- 在完成主事件共享信息铺垫后，再围绕这个子事件特有的新增动作、交流、决定、变化、纠正或结果展开几轮对话
- 子事件新增记忆至少要在后续若干轮对话中得到明确覆盖，不能只轻描淡写一带而过
- 子事件对话内容应明显区别于父级共享背景，体现这个 session 的独特性

### 额外要求
- 不要把整段对话都停留在父级共享背景，后半段必须推进到子事件新增信息
- 如果 child_event_memories 非空，dialogue_summary 里也要体现“先铺垫主事件，再展开子事件新增内容”的结构
""".strip()
        result += "\n\n" + staged_constraints.replace(
            '{shared_parent_memories}', shared_parent_str
        ).replace(
            '{child_event_memories}', child_memory_str
        )

    return result


def build_child_memory_generation_prompt(
    persona: Dict,
    event: Dict,
    system_memories: List[Dict],
    shared_parent_memories: List[Dict],
    prompt_template: str
) -> str:
    """Build a constrained prompt for child-only memories."""
    base_prompt = build_memory_generation_prompt(
        persona,
        event,
        system_memories,
        {},
        prompt_template
    )
    shared_parent_str = json.dumps([
        {
            "memory_id": memory.get("memory_id", ""),
            "memory_source": memory.get("memory_source", ""),
            "memory_type": memory.get("memory_type", ""),
            "memory_content": memory.get("memory_content", ""),
            "timestamp": memory.get("timestamp", ""),
            "image_refs": memory.get("image_refs", []),
        }
        for memory in shared_parent_memories
        if memory.get("memory_source") != "interference"
    ], ensure_ascii=False, indent=2)

    child_constraints = """

## 父级共享记忆（禁止重复）
{shared_parent_memories}

## 额外约束：当前只生成 child_event_memories
- 这些记忆必须是“相对父级共享记忆新增”的子事件信息，不能重复父级共享记忆里已经出现的事实、结论、偏好或总结
- 不要生成任何图片说明、截图说明、场景图说明、这张图片/截图显示了什么之类的表述
- 不要仅复述事件标题或父事件背景，要写这个子事件自己新增的动作、交流、决定、变化、纠正或结果
- 如果该事件没有明显新增信息，宁可少写，只输出 1-3 条高质量 memory_points
- 优先输出 primary / secondary 记忆，不要输出 interference 记忆
- `image_refs` 必须为空列表
""".strip()

    return (
        base_prompt
        + "\n\n"
        + child_constraints.replace('{shared_parent_memories}', shared_parent_str)
    )


def should_generate_child_event_memories(
    event: Dict,
    parent_payload: Optional[Dict]
) -> bool:
    """Only generate child-only memories when a parent group actually has multiple child sessions."""
    parent_event_id = event.get('parent_event_id')
    if parent_event_id in (None, '', -1, '-1'):
        return False
    if not parent_payload:
        return False
    child_event_ids = parent_payload.get('parent_memory_event', {}).get('child_event_ids', [])
    return len(child_event_ids) > 1


def call_llm_json(prompt: str, system_prompt: str = "") -> tuple[Dict, Dict]:
    """Call LLM and parse JSON response, returning parsed JSON and token/cost info."""
    response, cost_info = llm_request(
        system_prompt,
        prompt,
        return_parsed_json=True,
        extract_json=True,
        json_markers=["```json", "```"]
    )
    if isinstance(response, dict):
        return response, (cost_info or {})
    raise ValueError(f"LLM returned non-dict: {str(response)[:200]}")


def normalize_memory_points(
    memory_points: List[Dict], uuid: int, event_id: int, event: Dict,
    allowed_image_refs: Optional[Set[str]] = None
) -> List[Dict]:
    """Fill missing memory fields and keep stage6-compatible structure."""
    normalized = []
    counters = {"primary": 0, "secondary": 0, "interference": 0}

    start_ts = format_timestamp(event.get('event_start_time', ''))
    end_ts = format_timestamp(event.get('event_end_time', '')) or start_ts

    for idx, memory in enumerate(memory_points):
        if not isinstance(memory, dict):
            continue

        source = str(memory.get('memory_source', 'secondary')).strip().lower()
        if source not in {"primary", "secondary", "interference"}:
            source = "secondary"

        source_prefix = {
            "primary": "pri",
            "secondary": "sec",
            "interference": "int"
        }[source]
        local_idx = counters[source]
        counters[source] += 1

        default_type = "Event Memory" if source != "secondary" else "Dialogue Memory"
        timestamp = memory.get('timestamp')
        if not timestamp:
            timestamp = start_ts if source == "primary" else end_ts
        timestamp = format_timestamp(timestamp)

        original_memories = memory.get('original_memories', [])
        if not isinstance(original_memories, list):
            original_memories = []

        image_refs = memory.get('image_refs', [])
        if isinstance(image_refs, str):
            image_refs = [image_refs] if image_refs else []
        elif not isinstance(image_refs, list):
            image_refs = []
        if allowed_image_refs is not None:
            image_refs = [normalize_relpath(p) for p in image_refs if normalize_relpath(str(p)) in allowed_image_refs]

        normalized.append({
            "memory_id": memory.get('memory_id') or f"{uuid}_{event_id}_{source_prefix}_{local_idx}",
            "memory_source": source,
            "memory_type": memory.get('memory_type') or default_type,
            "memory_content": memory.get('memory_content', '').strip(),
            "timestamp": timestamp,
            "importance": clamp_importance(
                memory.get('importance'),
                0.75 if source == "primary" else (0.55 if source == "secondary" else 0.4)
            ),
            "is_update": bool(memory.get('is_update', False)),
            "original_memories": original_memories,
            "image_refs": image_refs,
            "dialogue_turn_ids": normalize_stage5_turn_ids(memory.get('dialogue_turn_ids'))
        })

    return [m for m in normalized if m.get('memory_content')]


def normalize_stage5_turn_ids(value) -> List[int]:
    """Normalize any Stage5 turn-id field into a stable integer list."""
    if isinstance(value, list):
        turn_ids = []
        for item in value:
            try:
                turn_id = int(item)
            except (TypeError, ValueError):
                continue
            if turn_id > 0:
                turn_ids.append(turn_id)
        return sorted(set(turn_ids))

    if isinstance(value, int) and value > 0:
        return [value]

    return []


def normalize_dialogue_with_turn_map(
    dialogue: List[Dict], allowed_image_refs: Optional[Set[str]] = None
) -> Tuple[List[Dict], Dict[int, List[int]]]:
    """Normalize dialogue turns and keep a raw-turn to normalized-turn mapping."""
    normalized = []
    raw_to_normalized_turns = {}
    turn_num = 1

    for item in dialogue:
        if not isinstance(item, dict):
            continue

        role = str(item.get('role', '')).strip().lower()
        if role not in {"user", "assistant"}:
            continue

        raw_turn = item.get('turn')
        try:
            raw_turn = int(raw_turn)
        except (TypeError, ValueError):
            raw_turn = None
        produced_turns = []

        raw_content = item.get('content', '')
        content = sanitize_dialogue_text(str(raw_content)) if raw_content is not None else ''

        image_inline = item.get('image_inline')
        if isinstance(image_inline, str):
            image_inline = canonicalize_image_path(image_inline.strip())
        else:
            image_inline = None

        # Only allow the user side to send images in final Stage5 dialogue.
        if role != "user":
            image_inline = None

        image_refs = []

        if allowed_image_refs is not None:
            if image_inline not in allowed_image_refs:
                image_inline = None

            tag_match = re.findall(r'\[image:([^\]]+)\]', content)
            content_refs = [canonicalize_image_path(match.strip()) for match in tag_match if match.strip()]
            valid_content_refs = [ref for ref in content_refs if ref in allowed_image_refs]

            if image_inline:
                image_refs.append(image_inline)
            for ref in valid_content_refs:
                if ref not in image_refs:
                    image_refs.append(ref)
        elif image_inline:
            image_refs.append(image_inline)

        text_content = re.sub(r'\s*\[image:[^\]]+\]\s*', ' ', content).strip()
        text_content = re.sub(r'\s{2,}', ' ', text_content)
        text_content = sanitize_dialogue_text(text_content)

        if text_content:
            normalized.append({
                "turn": turn_num,
                "role": role,
                "content": text_content,
                "content_type": "text"
            })
            produced_turns.append(turn_num)
            turn_num += 1

        for ref in image_refs:
            normalized.append({
                "turn": turn_num,
                "role": role,
                "image_inline": ref,
                "content_type": "image"
            })
            produced_turns.append(turn_num)
            turn_num += 1

        if raw_turn is not None and produced_turns:
            raw_to_normalized_turns[raw_turn] = produced_turns

    return normalized, raw_to_normalized_turns


def normalize_dialogue(dialogue: List[Dict], allowed_image_refs: Optional[Set[str]] = None) -> List[Dict]:
    """Normalize dialogue turns into the existing stage5 schema."""
    normalized, _raw_to_normalized_turns = normalize_dialogue_with_turn_map(dialogue, allowed_image_refs)
    return normalized


def attach_dialogue_turn_ids(
    memory_points: List[Dict],
    memory_turn_links: List[Dict],
    raw_to_normalized_turns: Dict[int, List[int]],
) -> List[Dict]:
    """Merge dialogue-turn grounding from the dialogue-generation output into memory points."""
    if not memory_points:
        return memory_points

    link_map = {}
    for item in memory_turn_links:
        if not isinstance(item, dict):
            continue
        memory_id = str(item.get("memory_id", "")).strip()
        if not memory_id:
            continue
        normalized_turn_ids = []
        for raw_turn_id in normalize_stage5_turn_ids(item.get("dialogue_turn_ids")):
            normalized_turn_ids.extend(raw_to_normalized_turns.get(raw_turn_id, []))
        link_map[memory_id] = sorted(set(turn_id for turn_id in normalized_turn_ids if turn_id > 0))

    merged = []
    for memory in memory_points:
        updated = dict(memory)
        memory_id = updated.get("memory_id")
        updated["dialogue_turn_ids"] = link_map.get(
            memory_id,
            normalize_stage5_turn_ids(updated.get("dialogue_turn_ids"))
        )
        merged.append(updated)
    return merged


def normalize_child_event_memories(
    memory_points: List[Dict],
    uuid: int,
    event_id: int,
    event: Dict,
    shared_parent_memories: List[Dict]
) -> List[Dict]:
    """Normalize child-only memories and filter parent-duplicate / image-grounded items."""
    normalized = normalize_memory_points(
        memory_points,
        uuid,
        event_id,
        event,
        allowed_image_refs=set()
    )
    parent_contents = {
        re.sub(r'\s+', '', str(memory.get('memory_content', '')))
        for memory in shared_parent_memories
        if memory.get('memory_source') != 'interference'
    }
    filtered = []
    for memory in normalized:
        if memory.get('memory_source') == 'interference':
            continue
        if memory.get('image_refs'):
            continue
        content = str(memory.get('memory_content', '')).strip()
        if not content:
            continue
        lowered = content.lower()
        if ('这张图片' in content or '这张截图' in content or '场景图' in content or
                '群聊截图' in content or '图片记录了' in content or '截图记录了' in content or
                'image' in lowered or 'screenshot' in lowered):
            continue
        normalized_content = re.sub(r'\s+', '', content)
        if normalized_content in parent_contents:
            continue
        filtered.append(memory)
    return filtered[:3]


# ============================================================================
# Parent-event shared memories
# ============================================================================

def build_parent_event_groups(events: List[Dict]) -> Dict[str, List[Dict]]:
    grouped = defaultdict(list)
    for event in events:
        parent_event_id = event.get('parent_event_id')
        parent_key = str(parent_event_id) if parent_event_id not in (None, '', -1, '-1') else str(event.get('event_id'))
        grouped[parent_key].append(event)

    for key in grouped:
        grouped[key] = sorted(grouped[key], key=event_sort_key)
    return grouped


def build_parent_memory_event(parent_key: str, parent_events: List[Dict]) -> Dict:
    ordered = sorted(parent_events, key=event_sort_key)
    first_event = ordered[0]
    event_name = first_event.get('event_name', '')
    descriptions = []
    participants = []
    additional_info = []
    images = []
    seen_images = set()

    for idx, event in enumerate(ordered, start=1):
        start_time = event.get('event_start_time', '')
        event_label = event.get('event_name', '') or event.get('event_id', '')
        desc = event.get('description', '')
        descriptions.append(f"{idx}. [{start_time}] {event_label}: {desc}")

        for participant in event.get('participants', []) or []:
            if participant and participant not in participants:
                participants.append(participant)

        for info in event.get('additional_info', []) or []:
            if info and info not in additional_info:
                additional_info.append(info)

        for image in event.get('images', []) or []:
            if not isinstance(image, dict):
                continue
            image_path = canonicalize_image_path(image.get('image_path', ''))
            if not image_path or image_path in seen_images:
                continue
            seen_images.add(image_path)
            images.append({
                "type": image.get('type', ''),
                "image_path": image_path,
                "description": image.get('description', '')
            })

    return {
        "event_id": f"parent_{parent_key}",
        "parent_event_id": first_event.get('parent_event_id', parent_key),
        "sub_event_id": f"parent_{parent_key}",
        "event_name": event_name,
        "event_start_time": format_timestamp(ordered[0].get('event_start_time', '')),
        "event_end_time": format_timestamp(ordered[-1].get('event_end_time', ordered[-1].get('event_start_time', ''))),
        "description": "\n".join(descriptions),
        "importance": first_event.get('importance', 0.5),
        "participants": participants,
        "additional_info": additional_info,
        "images": images,
        "event_source": "parent_event_memory",
        "child_event_ids": [event.get('event_id') for event in ordered],
    }


# ============================================================================
# Process single persona
# ============================================================================

def build_parent_memory_payload(
    persona: Dict,
    uuid: int,
    parent_memory_key: str,
    parent_event_id,
    parent_events: List[Dict],
    image_base_dir: str,
    memory_prompt_template: str,
) -> Dict:
    """Generate shared parent memories once for a parent event group."""
    bp = persona.get('Basic_Profile', {})
    parent_memory_event = build_parent_memory_event(parent_memory_key, parent_events)
    parent_image_refs = build_candidate_image_refs(uuid, parent_memory_event, image_base_dir)
    parent_allowed_image_refs = {
        image_path for image_path in flatten_allowed_images(parent_image_refs)
        if os.path.basename(os.path.dirname(canonicalize_image_path(image_path))) != 'scenery'
    }
    parent_system_memories = generate_system_memories(persona, uuid, f"parent_{parent_memory_key}")

    memory_prompt = build_memory_generation_prompt(
        persona, parent_memory_event, parent_system_memories, parent_image_refs, memory_prompt_template
    )
    memory_result, _memory_cost_info = call_llm_json(memory_prompt)
    parent_llm_memories = normalize_memory_points(
        memory_result.get('memory_points', []),
        uuid,
        f"parent_{parent_memory_key}",
        parent_memory_event,
        parent_allowed_image_refs
    )
    if not parent_llm_memories:
        raise ValueError(f"parent memory generation returned no valid memory_points for {parent_memory_key}")

    parent_image_memories = build_image_grounded_memories(
        uuid,
        f"parent_{parent_memory_key}",
        parent_memory_event,
        parent_image_refs,
        bp.get('name'),
        persona.get('language') or bp.get('language'),
        bp.get('nationality')
    )
    shared_parent_memories = parent_llm_memories + parent_image_memories
    return {
        "parent_memory_event": parent_memory_event,
        "parent_image_refs": parent_image_refs,
        "shared_parent_memory_points": shared_parent_memories,
        "parent_memory_payload": {
            "uuid": uuid,
            "parent_memory_key": parent_memory_key,
            "parent_event_id": parent_event_id,
            "event_name": parent_memory_event.get('event_name', ''),
            "event_start_time": format_timestamp(parent_memory_event.get('event_start_time', '')),
            "event_end_time": format_timestamp(parent_memory_event.get('event_end_time', '')),
            "child_event_ids": parent_memory_event.get('child_event_ids', []),
            "memory_points": parent_system_memories + shared_parent_memories,
            "image_refs": parent_image_refs,
        }
    }


def generate_event_session(
    persona: Dict,
    event: Dict,
    event_index: int,
    prompts_dir: str,
    image_base_dir: str,
    dialogue_prompt_template: str,
    parent_memory_cache: Dict[str, Dict],
    coverage_images_by_event: Optional[Dict[str, List[Dict[str, str]]]] = None,
    image_summary_index: Optional[Dict[str, Dict]] = None,
) -> Tuple[int, Dict, Optional[Dict], Optional[str]]:
    """Generate one session from one event."""
    uuid = persona.get('uuid')
    bp = persona.get('Basic_Profile', {})
    chinese = is_chinese_persona(persona.get('language') or bp.get('language'), bp.get('nationality'))
    event_id = event.get('event_id', event_index)
    session_id = f"{uuid}_{event_id}"
    parent_event_id = event.get('parent_event_id')
    parent_memory_key = str(parent_event_id) if parent_event_id not in (None, '', -1, '-1') else str(event_id)

    logger.debug(f"[uuid={uuid}] Event {event_id}: {event.get('event_name', 'Unknown')}")

    image_refs = build_candidate_image_refs(uuid, event, image_base_dir)
    image_refs = augment_image_refs_for_coverage(
        image_refs,
        (coverage_images_by_event or {}).get(str(event_id))
    )
    usage_plan = build_session_image_usage_plan(
        image_refs,
        event_id,
        introduce_person_avatar=(event_index == 0),
        event_name=event.get('event_name', ''),
        image_summary_index=image_summary_index,
        chinese=chinese,
    )
    allowed_image_refs = build_dialogue_allowed_image_refs(usage_plan)
    system_memories = generate_system_memories(persona, uuid, event_id)
    parent_payload = parent_memory_cache[parent_memory_key]
    shared_parent_memories = parent_payload["shared_parent_memory_points"]
    child_event_memories: List[Dict] = []

    if should_generate_child_event_memories(event, parent_payload):
        try:
            child_memory_prompt = build_child_memory_generation_prompt(
                persona,
                event,
                system_memories,
                shared_parent_memories,
                load_prompt(os.path.join(prompts_dir, 'stage5_memories_zh.txt'))
                if ((persona.get('language') or bp.get('language') or 'zh') == 'zh' or bp.get('nationality', 'Chinese') == 'Chinese')
                else load_prompt(os.path.join(prompts_dir, 'stage5_memories_en.txt'))
            )
            child_memory_result, _child_memory_cost_info = call_llm_json(child_memory_prompt)
            child_event_memories = normalize_child_event_memories(
                child_memory_result.get('memory_points', []),
                uuid,
                event_id,
                event,
                shared_parent_memories
            )
        except Exception as e:
            logger.warning(
                f"[uuid={uuid}] Event {event_id} child_event_memories generation failed, fallback to empty: {e}"
            )

    dialogue_prompt = build_dialogue_generation_prompt(
        persona,
        event,
        system_memories,
        image_refs,
        shared_parent_memories,
        child_event_memories,
        dialogue_prompt_template
    )
    dialogue_result, dialogue_cost_info = call_llm_json(dialogue_prompt)
    dialogue, raw_to_normalized_turns = normalize_dialogue_with_turn_map(
        dialogue_result.get('dialogue', []),
        allowed_image_refs
    )
    dialogue, appended_image_turns, prepended_turn_count = enforce_required_dialogue_images(
        dialogue,
        usage_plan,
        persona.get('language') or bp.get('language'),
        bp.get('nationality'),
    )
    if prepended_turn_count:
        raw_to_normalized_turns = {
            raw_turn: [turn_id + prepended_turn_count for turn_id in turn_ids]
            for raw_turn, turn_ids in raw_to_normalized_turns.items()
        }
    if not dialogue:
        raise ValueError("dialogue generation returned no valid dialogue turns")

    shared_parent_memories = [dict(memory) for memory in shared_parent_memories]
    child_event_memories = [dict(memory) for memory in child_event_memories]
    memory_fields = build_session_memory_fields(system_memories, shared_parent_memories, child_event_memories)
    session_image_memories = build_image_grounded_memories(
        uuid,
        event_id,
        event,
        image_refs,
        bp.get('name'),
        persona.get('language') or bp.get('language'),
        bp.get('nationality')
    )
    own_memory_points_seed = list(memory_fields["own_memory_points"]) + list(session_image_memories)
    all_memory_points_seed = list(memory_fields["memory_points"]) + list(session_image_memories)
    all_memories = attach_dialogue_turn_ids(
        all_memory_points_seed,
        dialogue_result.get("memory_turn_links", []),
        raw_to_normalized_turns,
    )
    all_memories = merge_image_memory_turn_ids(all_memories, appended_image_turns)
    own_memory_ids = {memory.get("memory_id") for memory in own_memory_points_seed}
    own_memory_points = [memory for memory in all_memories if memory.get("memory_id") in own_memory_ids]
    shared_parent_memory_ids = {memory.get("memory_id") for memory in shared_parent_memories}
    shared_parent_memory_points = [
        memory for memory in all_memories if memory.get("memory_id") in shared_parent_memory_ids
    ]
    child_event_memory_ids = {memory.get("memory_id") for memory in child_event_memories}
    child_event_memory_points = [
        memory for memory in all_memories if memory.get("memory_id") in child_event_memory_ids
    ]
    session_stats = collect_session_image_stats(image_refs, dialogue, all_memories)
    session_stats["dialogue_output_tokens"] = dialogue_cost_info.get("output_tokens", 0) or 0

    session = {
        "session_id": session_id,
        "event_id": event_id,
        "parent_event_id": parent_event_id,
        "event_name": event.get('event_name', ''),
        "event_start_time": format_timestamp(event.get('event_start_time', '')),
        "event_end_time": format_timestamp(event.get('event_end_time', '')),
        "image_refs": image_refs,
        "image_candidates": flatten_allowed_images(image_refs),
        "dialogue_goal": sanitize_dialogue_text(dialogue_result.get('dialogue_goal', '')),
        "dialogue_summary": sanitize_dialogue_text(dialogue_result.get('dialogue_summary', '')),
        "dialogue": dialogue,
        "child_event_memories": child_event_memory_points,
        "own_memory_points": own_memory_points,
        "memory_points": all_memories,
        "shared_parent_memory_points": shared_parent_memory_points,
        "parent_memory_key": parent_memory_key,
        "session_stats": session_stats
    }
    return event_index, session, parent_payload.get("parent_memory_payload"), None


def process_persona(
    persona: Dict,
    prompts_dir: str,
    image_base_dir: str,
    session_output_dir: Optional[str] = None,
    session_workers: int = 1,
    parent_memory_workers: int = 1,
    image_summary_index: Optional[Dict[str, Dict]] = None,
) -> Dict:
    """Process all events for a single persona, generating sessions."""
    uuid = persona.get('uuid')
    bp = persona.get('Basic_Profile', {})
    name = bp.get('name', 'Unknown')
    nationality = bp.get('nationality', 'Chinese')
    language = persona.get('language') or bp.get('language') or 'zh'
    chinese = is_chinese_persona(language, nationality)

    logger.info(
        f"[uuid={uuid}] Processing {name} ({nationality}), {len(persona.get('Events', []))} events, "
        f"session_workers={session_workers}, parent_memory_workers={parent_memory_workers}"
    )

    if language == 'zh' or nationality == 'Chinese':
        memory_prompt_file = os.path.join(prompts_dir, 'stage5_memories_zh.txt')
        dialogue_prompt_file = os.path.join(prompts_dir, 'stage5_dialogue_zh.txt')
    else:
        memory_prompt_file = os.path.join(prompts_dir, 'stage5_memories_en.txt')
        dialogue_prompt_file = os.path.join(prompts_dir, 'stage5_dialogue_en.txt')

    memory_prompt_template = load_prompt(memory_prompt_file)
    dialogue_prompt_template = load_prompt(dialogue_prompt_file)

    raw_events = persona.get('Events', [])
    normalized_events, fixed_parent_count = normalize_event_parent_ids(raw_events)
    if fixed_parent_count:
        logger.info(f"[uuid={uuid}] Filled parent_event_id for {fixed_parent_count} sub-events")

    events = sorted(normalized_events, key=event_sort_key)
    coverage_images_by_event = scan_persona_image_coverage_map(uuid, image_base_dir, events)
    errors = []
    parent_groups = build_parent_event_groups(events)
    parent_memory_cache = {}

    parent_tasks = []
    for parent_memory_key, parent_events in parent_groups.items():
        first_event = parent_events[0] if parent_events else {}
        parent_tasks.append((
            parent_memory_key,
            first_event.get('parent_event_id'),
            parent_events
        ))

    actual_parent_workers = max(1, min(parent_memory_workers, len(parent_tasks)))
    if actual_parent_workers == 1:
        for parent_memory_key, parent_event_id, parent_events in parent_tasks:
            parent_memory_cache[parent_memory_key] = build_parent_memory_payload(
                persona,
                uuid,
                parent_memory_key,
                parent_event_id,
                parent_events,
                image_base_dir,
                memory_prompt_template,
            )
    else:
        with ThreadPoolExecutor(max_workers=actual_parent_workers) as executor:
            futures = {
                executor.submit(
                    build_parent_memory_payload,
                    persona,
                    uuid,
                    parent_memory_key,
                    parent_event_id,
                    parent_events,
                    image_base_dir,
                    memory_prompt_template,
                ): parent_memory_key
                for parent_memory_key, parent_event_id, parent_events in parent_tasks
            }
            for future in as_completed(futures):
                parent_memory_key = futures[future]
                parent_memory_cache[parent_memory_key] = future.result()

    session_results = [None] * len(events)
    actual_session_workers = max(1, min(session_workers, len(events)))

    def persist_session(event_index: int, session: Dict, parent_memory_payload: Optional[Dict]):
        session_results[event_index] = session
        write_stage5_session_artifacts(
            session_output_dir,
            uuid,
            event_index + 1,
            session,
            parent_memory_payload
        )

    if actual_session_workers == 1:
        for event_index, event in enumerate(events):
            event_id = event.get('event_id', event_index)
            try:
                _, session, parent_memory_payload, _ = generate_event_session(
                    persona,
                    event,
                    event_index,
                    prompts_dir,
                    image_base_dir,
                    dialogue_prompt_template,
                    parent_memory_cache,
                    coverage_images_by_event,
                    image_summary_index,
                )
                persist_session(event_index, session, parent_memory_payload)
            except Exception as e:
                logger.error(f"[uuid={uuid}] Event {event_id} FAILED: {e}")
                logger.debug(traceback.format_exc())
                errors.append({"event_id": event_id, "error": str(e)})
                image_refs = build_candidate_image_refs(uuid, event, image_base_dir)
                image_refs = augment_image_refs_for_coverage(
                    image_refs,
                    coverage_images_by_event.get(str(event_id))
                )
                usage_plan = build_session_image_usage_plan(
                    image_refs,
                    event_id,
                    introduce_person_avatar=(event_index == 0),
                    event_name=event.get('event_name', ''),
                    image_summary_index=image_summary_index,
                    chinese=chinese,
                )
                system_memories = generate_system_memories(persona, uuid, event_id)
                parent_event_id = event.get('parent_event_id')
                parent_memory_key = str(parent_event_id) if parent_event_id not in (None, '', -1, '-1') else str(event_id)
                shared_parent_memories = parent_memory_cache.get(parent_memory_key, {}).get("shared_parent_memory_points", [])
                memory_fields = build_session_memory_fields(system_memories, shared_parent_memories)
                dialogue, appended_image_turns, _prepended_turn_count = enforce_required_dialogue_images(
                    [],
                    usage_plan,
                    persona.get('language') or bp.get('language'),
                    bp.get('nationality'),
                )
                session_image_memories = build_image_grounded_memories(
                    uuid,
                    event_id,
                    event,
                    image_refs,
                    bp.get('name'),
                    persona.get('language') or bp.get('language'),
                    bp.get('nationality')
                )
                session_image_memories = merge_image_memory_turn_ids(session_image_memories, appended_image_turns)
                own_memory_points = list(memory_fields["own_memory_points"]) + list(session_image_memories)
                all_memory_points = list(memory_fields["memory_points"]) + list(session_image_memories)
                session = {
                    "session_id": f"{uuid}_{event_id}",
                    "event_id": event_id,
                    "parent_event_id": parent_event_id,
                    "event_name": event.get('event_name', ''),
                    "event_start_time": format_timestamp(event.get('event_start_time', '')),
                    "event_end_time": format_timestamp(event.get('event_end_time', '')),
                    "image_refs": image_refs,
                    "image_candidates": flatten_allowed_images(image_refs),
                    "dialogue_goal": "",
                    "dialogue_summary": "",
                    "dialogue": dialogue,
                    "child_event_memories": [],
                    "own_memory_points": own_memory_points,
                    "memory_points": all_memory_points,
                    "shared_parent_memory_points": shared_parent_memories,
                    "parent_memory_key": parent_memory_key,
                    "session_stats": {
                        "dialogue_turn_count": len(dialogue),
                        "image_candidate_count": len(flatten_allowed_images(image_refs)),
                        "image_inline_count": len([turn for turn in dialogue if turn.get("image_inline")]),
                        "memory_image_ref_count": len([ref for memory in all_memory_points for ref in (memory.get("image_refs", []) or [])]),
                        "unique_image_count": len(flatten_allowed_images(image_refs)),
                        "dialogue_output_tokens": 0,
                    },
                    "_error": str(e)
                }
                persist_session(
                    event_index,
                    session,
                    parent_memory_cache.get(parent_memory_key, {}).get("parent_memory_payload")
                )
    else:
        with ThreadPoolExecutor(max_workers=actual_session_workers) as executor:
            futures = {
                executor.submit(
                    generate_event_session,
                    persona,
                    event,
                    event_index,
                    prompts_dir,
                    image_base_dir,
                    dialogue_prompt_template,
                    parent_memory_cache,
                    coverage_images_by_event,
                    image_summary_index,
                ): (event_index, event)
                for event_index, event in enumerate(events)
            }
            for future in as_completed(futures):
                event_index, event = futures[future]
                event_id = event.get('event_id', event_index)
                try:
                    _, session, parent_memory_payload, _ = future.result()
                    persist_session(event_index, session, parent_memory_payload)
                except Exception as e:
                    logger.error(f"[uuid={uuid}] Event {event_id} FAILED: {e}")
                    logger.debug(traceback.format_exc())
                    errors.append({"event_id": event_id, "error": str(e)})
                    image_refs = build_candidate_image_refs(uuid, event, image_base_dir)
                    image_refs = augment_image_refs_for_coverage(
                        image_refs,
                        coverage_images_by_event.get(str(event_id))
                    )
                    usage_plan = build_session_image_usage_plan(
                        image_refs,
                        event_id,
                        introduce_person_avatar=(event_index == 0),
                        event_name=event.get('event_name', ''),
                        image_summary_index=image_summary_index,
                        chinese=chinese,
                    )
                    system_memories = generate_system_memories(persona, uuid, event_id)
                    parent_event_id = event.get('parent_event_id')
                    parent_memory_key = str(parent_event_id) if parent_event_id not in (None, '', -1, '-1') else str(event_id)
                    shared_parent_memories = parent_memory_cache.get(parent_memory_key, {}).get("shared_parent_memory_points", [])
                    memory_fields = build_session_memory_fields(system_memories, shared_parent_memories)
                    dialogue, appended_image_turns, _prepended_turn_count = enforce_required_dialogue_images(
                        [],
                        usage_plan,
                        persona.get('language') or bp.get('language'),
                        bp.get('nationality'),
                    )
                    session_image_memories = build_image_grounded_memories(
                        uuid,
                        event_id,
                        event,
                        image_refs,
                        bp.get('name'),
                        persona.get('language') or bp.get('language'),
                        bp.get('nationality')
                    )
                    session_image_memories = merge_image_memory_turn_ids(session_image_memories, appended_image_turns)
                    own_memory_points = list(memory_fields["own_memory_points"]) + list(session_image_memories)
                    all_memory_points = list(memory_fields["memory_points"]) + list(session_image_memories)
                    session = {
                        "session_id": f"{uuid}_{event_id}",
                        "event_id": event_id,
                        "parent_event_id": parent_event_id,
                        "event_name": event.get('event_name', ''),
                        "event_start_time": format_timestamp(event.get('event_start_time', '')),
                        "event_end_time": format_timestamp(event.get('event_end_time', '')),
                        "image_refs": image_refs,
                        "image_candidates": flatten_allowed_images(image_refs),
                        "dialogue_goal": "",
                        "dialogue_summary": "",
                        "dialogue": dialogue,
                        "child_event_memories": [],
                        "own_memory_points": own_memory_points,
                        "memory_points": all_memory_points,
                        "shared_parent_memory_points": shared_parent_memories,
                        "parent_memory_key": parent_memory_key,
                        "session_stats": {
                            "dialogue_turn_count": len(dialogue),
                            "image_candidate_count": len(flatten_allowed_images(image_refs)),
                            "image_inline_count": len([turn for turn in dialogue if turn.get("image_inline")]),
                            "memory_image_ref_count": len([ref for memory in all_memory_points for ref in (memory.get("image_refs", []) or [])]),
                            "unique_image_count": len(flatten_allowed_images(image_refs)),
                            "dialogue_output_tokens": 0,
                        },
                        "_error": str(e)
                    }
                    persist_session(
                        event_index,
                        session,
                        parent_memory_cache.get(parent_memory_key, {}).get("parent_memory_payload")
                    )

    sessions = [session for session in session_results if session is not None]

    if len(sessions) >= 3:
        early_session = sessions[2]
        n_turns = len(early_session.get('dialogue', []))
        n_mem = len(early_session.get('memory_points', []))
        logger.info(
            f"[uuid={uuid}] Early check event {early_session.get('event_id')}: "
            f"{n_turns} dialogue turns, {n_mem} memory points"
        )
        if n_turns < 4:
            logger.warning(f"[uuid={uuid}] WARNING: Only {n_turns} dialogue turns, expected 15-30")

    total_turns = sum(len(s.get('dialogue', [])) for s in sessions)
    total_dialogue_output_tokens = sum((s.get('session_stats') or {}).get('dialogue_output_tokens', 0) or 0 for s in sessions)
    total_image_candidates = sum((s.get('session_stats') or {}).get('image_candidate_count', 0) or 0 for s in sessions)
    total_unique_images = sum((s.get('session_stats') or {}).get('unique_image_count', 0) or 0 for s in sessions)

    result_record = {
        "uuid": uuid,
        "language": language,
        "Basic_Profile": bp,
        "Init_State": persona.get('Init_State', {}),
        "Important_Dates": persona.get('Important_Dates', {}),
        "sessions": sessions,
        "session_stats_summary": {
            "session_count": len(sessions),
            "total_dialogue_turn_count": total_turns,
            "total_dialogue_output_tokens": total_dialogue_output_tokens,
            "total_image_candidate_count": total_image_candidates,
            "total_unique_image_count": total_unique_images,
        },
        "_errors": errors
    }

    logger.info(f"[uuid={uuid}] Done: {len(sessions)} sessions, {len(errors)} errors")
    return result_record


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='Stage 5: Generate Dialogue + Memory Points')
    # ---- Key hyperparameters (modify here) ----
    parser.add_argument('--input-file', type=str,
                        default=os.path.join(PROJECT_ROOT, 'data', '10_person', 'stage4_annual_events.jsonl'),
                        help='Input stage4 JSONL file')
    parser.add_argument('--output-file', type=str,
                        default=os.path.join(PROJECT_ROOT, 'data', '10_person', 'stage5_sessions.jsonl'),
                        help='Output stage5 JSONL file')
    parser.add_argument('--prompts-dir', type=str,
                        default=os.path.join(PROJECT_ROOT, 'prompts'),
                        help='Prompts directory')
    parser.add_argument('--image-dir', type=str,
                        default=os.path.join(PROJECT_ROOT, 'image'),
                        help='Image base directory (contains person/, event/, social/ subdirs)')
    parser.add_argument('--max-workers', type=int, default=3,
                        help='Number of parallel persona workers (default: 3)')
    parser.add_argument('--session-workers', type=int, default=10,
                        help='Number of parallel event/session workers per persona (default: 10)')
    parser.add_argument('--parent-memory-workers', type=int, default=2,
                        help='Number of parallel parent-memory workers per persona (default: 2)')
    parser.add_argument('--uuid-filter', type=int, nargs='+', default=None,
                        help='Only process these UUIDs (default: all)')
    parser.add_argument('--per-uuid-output-dir', type=str, default=None,
                        help='Optional base dir for per-uuid outputs, e.g. data_10person')
    parser.add_argument('--per-uuid-flat-dir', type=str, default=None,
                        help='Optional flat dir; writes <dir>/stage5_sessions_uuid{k}.jsonl per persona')
    parser.add_argument('--session-output-dir', type=str, default=None,
                        help='Optional directory for incremental stage5 session outputs')
    parser.add_argument('--image-summary-file', type=str, default=None,
                        help='Optional stage10 image summaries JSONL for caption-based image replies')
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output_file), exist_ok=True)

    logger.info(f"{'=' * 70}")
    logger.info(f"STAGE 5: Dialogue + Memory Points Generation")
    logger.info(f"Input:  {args.input_file}")
    logger.info(f"Output: {args.output_file}")
    if args.per_uuid_output_dir:
        logger.info(f"Per-UUID Output Dir: {args.per_uuid_output_dir}")
    if args.session_output_dir:
        logger.info(f"Session Output Dir: {args.session_output_dir}")
    if args.image_summary_file:
        logger.info(f"Image Summary File: {args.image_summary_file}")
    logger.info(f"Persona Workers: {args.max_workers}")
    logger.info(f"Session Workers / Persona: {args.session_workers}")
    logger.info(f"Parent Memory Workers / Persona: {args.parent_memory_workers}")
    logger.info(f"{'=' * 70}")

    # Load input
    personas = read_jsonl(args.input_file)
    if not personas:
        logger.error(f"No data in {args.input_file}")
        return

    image_summary_index = load_image_summary_index(args.image_summary_file)
    if args.image_summary_file:
        logger.info(f"Loaded {len(image_summary_index)} image summary index entries")

    # Load existing output (checkpoint)
    existing = {}
    for r in read_jsonl(args.output_file):
        if isinstance(r, dict) and 'uuid' in r:
            existing[r['uuid']] = r

    logger.info(f"Loaded {len(personas)} personas, {len(existing)} already processed")

    # Filter
    to_process = []
    for p in personas:
        uuid = p.get('uuid')
        if args.uuid_filter and uuid not in args.uuid_filter:
            continue
        if uuid in existing:
            logger.info(f"[uuid={uuid}] SKIP (already done)")
            continue
        to_process.append(p)

    logger.info(f"To process: {len(to_process)} personas")

    if not to_process:
        logger.info("Nothing to process.")
        return

    lock = threading.Lock()
    results = dict(existing)

    def process_and_save(persona):
        uuid = persona.get('uuid')
        try:
            record = process_persona(
                persona,
                args.prompts_dir,
                args.image_dir,
                args.session_output_dir,
                session_workers=args.session_workers,
                parent_memory_workers=args.parent_memory_workers,
                image_summary_index=image_summary_index,
            )
            with lock:
                results[uuid] = record
                ordered = [results[p.get('uuid')] for p in personas if p.get('uuid') in results]
                write_jsonl(ordered, args.output_file)
                if args.per_uuid_output_dir:
                    write_per_uuid_record(record, args.per_uuid_output_dir)
                    sync_data10person_record(record, args.per_uuid_output_dir)
                if args.per_uuid_flat_dir:
                    os.makedirs(args.per_uuid_flat_dir, exist_ok=True)
                    flat_path = os.path.join(
                        args.per_uuid_flat_dir,
                        f'stage5_sessions_uuid{uuid}.jsonl',
                    )
                    write_jsonl([record], flat_path)
                logger.info(f"[uuid={uuid}] Saved checkpoint ({len(results)} total)")
            return record
        except Exception as e:
            logger.error(f"[uuid={uuid}] FATAL: {e}")
            logger.debug(traceback.format_exc())
            return None

    actual_workers = min(args.max_workers, len(to_process))
    logger.info(f"Starting {actual_workers} parallel workers...")

    with ThreadPoolExecutor(max_workers=actual_workers) as executor:
        futures = {executor.submit(process_and_save, p): p.get('uuid') for p in to_process}
        for future in as_completed(futures):
            uuid = futures[future]
            try:
                future.result()
            except Exception as e:
                logger.error(f"[uuid={uuid}] Thread error: {e}")

    # Final save
    ordered = [results[p.get('uuid')] for p in personas if p.get('uuid') in results]
    write_jsonl(ordered, args.output_file)

    logger.info(f"{'=' * 70}")
    logger.info(f"STAGE 5 COMPLETE: {len(results)} records saved to {args.output_file}")
    logger.info(f"{'=' * 70}")


if __name__ == '__main__':
    main()
