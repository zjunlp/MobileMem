"""Conversation member avatar generation (faces + image backends) + persona signature."""
import hashlib
import json
import logging
import os
from typing import Dict, List

from common import PROMPTS_DIR
from backends.faces import _imread_safe, _imwrite_safe, maybe_auto_orient_avatar
from backends.images import generate_person_images
from .render import (
    sanitize_filename_component,
)

logger = logging.getLogger('stage7')


def build_persona_source_signature(persona: Dict) -> str:
    """Build a stable signature for the stage4 persona content used by stage7."""
    bp = persona.get('Basic_Profile', {}) or {}
    events = persona.get('Events', []) or []
    payload = {
        "uuid": persona.get('uuid'),
        "name": bp.get('name', ''),
        "nationality": bp.get('nationality', ''),
        "event_count": len(events),
        "events": [
            {
                "event_id": event.get('event_id'),
                "event_name": event.get('event_name', ''),
                "event_start_time": event.get('event_start_time', ''),
                "event_end_time": event.get('event_end_time', ''),
            }
            for event in events
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def build_member_avatar_filename(uuid: int, member_name: str) -> str:
    """Return the sanitized filename for a member avatar."""
    return f"{uuid}_{sanitize_filename_component(member_name)}_avatar.png"


def _cleanup_member_avatar_dir(member_avatar_dir: str, uuid: int) -> int:
    """Remove stale temp files and malformed legacy filenames in a member avatar directory."""
    if not os.path.isdir(member_avatar_dir):
        return 0

    removed = 0
    prefix = f"{uuid}_"
    for name in os.listdir(member_avatar_dir):
        path = os.path.join(member_avatar_dir, name)
        if not os.path.isfile(path) or not name.startswith(prefix):
            continue

        lower_name = name.lower()
        stem, ext = os.path.splitext(name)
        if ext.lower() != '.png':
            continue

        should_remove = False
        if lower_name.endswith('.normalized.png'):
            should_remove = True
        elif stem.endswith('avatar') and not stem.endswith('_avatar'):
            should_remove = True

        if should_remove:
            try:
                os.remove(path)
                removed += 1
            except OSError:
                pass
    return removed


def build_member_avatar_prompt(description: str, nationality: str, gender: str = '') -> str:
    """Wrap a social member's appearance description in the avatar prompt template.
    
    Enforce nationality and gender so Chinese people are not rendered with
    foreign-looking faces, and so female/male avatars do not swap gender.
    Also extract ethnicity from description for more precise constraints in
    multi-ethnic countries such as the United States or United Kingdom.
    """
    # Extract ethnicity from description for more precise ethnicity constraints.
    from generation.event_photo.prompts import extract_ethnicity_from_description
    extracted_ethnicity = extract_ethnicity_from_description(description, nationality)
    
    # Build mandatory ethnicity/appearance constraints from nationality.
    nationality_appearance_map = {
        'Chinese': '这是一个中国人，必须是东亚面孔、黄皮肤、黑头发的中国人外貌特征。',
        'Japanese': '这是一个日本人，必须是东亚面孔、日本人外貌特征。',
        'Korean': '这是一个韩国人，必须是东亚面孔、韩国人外貌特征。',
        'Indian': 'This is an Indian person, must have South Asian facial features and skin tone.',
    }
    
    if nationality in nationality_appearance_map:
        nationality_constraint = nationality_appearance_map[nationality]
    elif extracted_ethnicity != f'{nationality} person':
        # A concrete ethnicity was extracted from description; use precise constraints.
        nationality_constraint = (
            f'[ETHNICITY CONSTRAINT] This person is a {extracted_ethnicity}. '
            f'Their facial features, skin tone, and overall appearance MUST match {extracted_ethnicity} characteristics. '
            f'Do NOT generate a person of a different race or ethnicity.'
        )
    else:
        nationality_constraint = (
            f'This person is of {nationality} nationality, their appearance must match {nationality} ethnic features.'
        )
    
    # Build mandatory gender constraints; this is the most important fix.
    gender_constraint = ''
    if gender.lower() in ('male', '男', 'm'):
        if nationality == 'Chinese':
            gender_constraint = '【性别强制约束】这个人是男性，必须生成男性外貌，禁止生成女性形象。'
        else:
            gender_constraint = '[GENDER CONSTRAINT] This person is MALE. You MUST generate a male appearance. Do NOT generate a female.'
    elif gender.lower() in ('female', '女', 'f'):
        if nationality == 'Chinese':
            gender_constraint = '【性别强制约束】这个人是女性，必须生成女性外貌，禁止生成男性形象。'
        else:
            gender_constraint = '[GENDER CONSTRAINT] This person is FEMALE. You MUST generate a female appearance. Do NOT generate a male.'
    
    # Inject constraints before the description, with gender first for highest priority.
    if gender_constraint:
        description = f"{gender_constraint} {nationality_constraint} {description}"
    else:
        description = f"{nationality_constraint} {description}"

    # Avatar prompt template: Chinese (_zh) for Chinese personas, else English (_en).
    if nationality == 'Chinese':
        template_file = os.path.join(PROMPTS_DIR, 'image_member_avatar_zh.txt')
    else:
        template_file = os.path.join(PROMPTS_DIR, 'image_member_avatar_en.txt')

    try:
        with open(template_file, 'r', encoding='utf-8') as f:
            template = f.read()
        prompt = template.format(description=description)
    except (FileNotFoundError, KeyError):
        if nationality == 'Chinese':
            prompt = (
                f"{description} "
                f"构图要求：肩部以上的近距离头像照，类似证件照或社交媒体头像。"
                f"只展示头部和肩部，不要展示身体其他部分。"
                f"【图片方向】图片必须是标准竖版胖像方向，头在上肩在下，不要旋转90度或颠倒。"
                f"【目光要求】人物目光平视前方，视线与地面平行，自然地平视前方。严禁抬头看天、严禁仰视、严禁低头。"
                f"必须穿着得体的日常服装（如衬衫、T恤、外套等），严禁裸露。"
                f"面部清晰无遮挡，五官可辨，面部占画面主体。"
                f"画面中只能有一个人，不能出现第二个人。"
                f"自然表情，纯色浅色背景，自然灯光，写实风格。"
                f"不要添加任何文字、水印或标题。"
            )
        else:
            prompt = (
                f"{description} "
                f"Composition: close-up headshot from shoulders up, similar to an ID photo or social media avatar. "
                f"Only show the head and shoulders, do NOT show the rest of the body. "
                f"[IMAGE ORIENTATION] Standard upright portrait orientation with head on top and shoulders below. Do NOT rotate 90 degrees or flip. "
                f"[GAZE DIRECTION] The person must look straight ahead at eye level, line of sight parallel to the ground. Do NOT look up at the sky. Do NOT tilt head back. Do NOT look down. "
                f"The person MUST be wearing proper everyday clothing (e.g. shirt, blouse, jacket). "
                f"Absolutely NO nudity, NO bare skin exposure. "
                f"Face clearly visible and unobstructed, face should be the main focus of the image. "
                f"Exactly one person in the image, no other people visible. "
                f"Natural expression, plain light-colored background, natural lighting, photorealistic. "
                f"Do NOT add any text, watermarks, or captions."
            )

    # Truncate to the model limit.
    from backends.images import get_generation_model_and_limit
    _, max_len = get_generation_model_and_limit(nationality)
    if len(prompt) > max_len:
        prompt = prompt[:max_len]
    return prompt


def ensure_member_avatars(uuid: int, group_specs: List[Dict], social_relationships: Dict,
                           member_avatar_dir: str, main_person_name: str, nationality: str):
    """Collect unique non-protagonist members across groups and generate missing avatars."""
    # Collect all non-protagonist members, deduplicated.
    all_members = set()
    for spec in group_specs:
        for member in spec.get('members', []):
            if member != main_person_name:
                all_members.add(member)

    if not all_members:
        return

    uuid_avatar_dir = member_avatar_dir
    os.makedirs(uuid_avatar_dir, exist_ok=True)
    cleaned = _cleanup_member_avatar_dir(uuid_avatar_dir, uuid)
    if cleaned:
        logger.info(f"[uuid={uuid}] Removed {cleaned} malformed member avatar file(s)")
    generated = 0
    skipped = 0

    for member_name in sorted(all_members):
        target_path = os.path.join(uuid_avatar_dir, build_member_avatar_filename(uuid, member_name))
        if os.path.exists(target_path):
            maybe_auto_orient_avatar(target_path, uuid, member_name)
            skipped += 1
            continue

        # Get appearance descriptions from social relationships; support both
        # Stage2 (description) and Stage3.9 (brief) formats.
        rel_info = social_relationships.get(member_name, {})
        if isinstance(rel_info, dict):
            # Check both description and brief fields.
            description = rel_info.get('description', '') or rel_info.get('brief', '')
        else:
            description = str(rel_info)

        # Extract gender, preferring the gender field and then inferring from description.
        gender = ''
        if isinstance(rel_info, dict):
            gender = rel_info.get('gender', '')
        
        # If gender is empty, try to infer it from the description text.
        if not gender and description:
            desc_lower = description.lower()
            if any(kw in desc_lower for kw in ['女性', '女孩', '女生', '女士', '阿姨', '大姐', '大妈', '她']):
                gender = 'female'
            elif any(kw in desc_lower for kw in ['男性', '男孩', '男生', '先生', '大叔', '小伙', '他']):
                gender = 'male'
            elif 'female' in desc_lower or 'woman' in desc_lower or 'girl' in desc_lower:
                gender = 'female'
            elif 'male' in desc_lower or ' man' in desc_lower or ' boy' in desc_lower:
                gender = 'male'

        if not description:
            # If no appearance description exists, build a generic one from nationality, gender, and relationship.
            relationship = ''
            if isinstance(rel_info, dict):
                if not gender:
                    gender = rel_info.get('gender', '')
                relationship = rel_info.get('relationship_type', '') or rel_info.get('relationship', '')  # noqa: F841
            if nationality == 'Chinese':
                gender_desc = '男性' if gender.lower() in ('male', '男') else ('女性' if gender.lower() in ('female', '女') else '成年人')
                description = f"一位中国{gender_desc}，面部清晰，自然表情。"
            else:
                gender_desc = 'man' if gender.lower() in ('male', '男') else ('woman' if gender.lower() in ('female', '女') else 'adult')
                description = f"A {nationality} {gender_desc}, clear face, natural expression."
            logger.info(f"[uuid={uuid}] No description for '{member_name}', using generated fallback")

        prompt = build_member_avatar_prompt(description, nationality, gender)
        logger.info(f"[uuid={uuid}] Generating avatar for '{member_name}' (gender={gender}, {len(prompt)} chars)...")

        try:
            paths = generate_person_images(prompt, output_dir=uuid_avatar_dir, nationality=nationality)
            if paths and os.path.exists(paths[0]):
                generated_path = paths[0]
                # Decode and re-encode as a real PNG to avoid JPEG content with a PNG suffix.
                generated_img = _imread_safe(generated_path)
                if generated_img is None or not _imwrite_safe(target_path, generated_img):
                    logger.error(f"[uuid={uuid}] Avatar FAILED for '{member_name}' — cannot normalize generated image")
                    for p in paths:
                        try:
                            if os.path.exists(p):
                                os.remove(p)
                        except OSError:
                            pass
                    continue
                # Clean up extra generated files.
                for p in paths:
                    try:
                        if os.path.exists(p) and os.path.abspath(p) != os.path.abspath(target_path):
                            os.remove(p)
                    except OSError:
                        pass
                # Automatically correct portrait orientation when upside down or sideways.
                maybe_auto_orient_avatar(target_path, uuid, member_name)
                logger.info(f"[uuid={uuid}] Avatar OK: {member_name} -> {os.path.basename(target_path)}")
                generated += 1
            else:
                logger.error(f"[uuid={uuid}] Avatar FAILED for '{member_name}' — API returned no image")
        except Exception as e:
            logger.error(f"[uuid={uuid}] Avatar generation error for '{member_name}': {e}")

    logger.info(f"[uuid={uuid}] Member avatars: {generated} generated, {skipped} skipped (existing)")

def _load_uuid_member_avatars(member_avatar_dir: str, uuid: int) -> List[str]:
    """Load all avatar file paths for a given uuid from the member avatar dir."""
    if not os.path.exists(member_avatar_dir):
        return []
    prefix = f"{uuid}_"
    paths = []
    for fname in sorted(os.listdir(member_avatar_dir)):
        if fname.startswith(prefix) and fname.endswith('_avatar.png'):
            paths.append(os.path.join(member_avatar_dir, fname))
    return paths

# ============================================================================
# Process single persona
# ============================================================================
# (_find_chrome / html_to_png / html_to_multi_png are imported from the
#  screenshot module at the top of this file.)
