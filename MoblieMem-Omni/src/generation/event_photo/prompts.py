"""Event-photo prompt building (identity / scene / event / safety)."""
import logging
from typing import Dict, List, Optional

import config
from backends.llm import get_text_llm_model, llm_request

from .data import compute_age

logger = logging.getLogger('fix_event_images')


CHINESE_EDIT_PROMPT_MAX = config.DMX_CHINESE_EDIT_PROMPT_MAX
GPT_PROMPT_MAX = 1000


def extract_ethnicity_from_description(description: str, nationality: str) -> str:
    """Extract specific ethnicity/skin tone from the stage2 description, to avoid generating wrong faces for multi-ethnic countries.

    The stage2 description already contains explicit ethnicity info (e.g. 'White American', 'Black British');
    extract those keywords to build a more precise ethnicity constraint.
    """
    if not description:
        return f'{nationality} person'
    
    desc_lower = description.lower()
    # Match ethnicity/skin-tone keywords by priority (from more specific to more general)
    ethnicity_patterns = [
        ('african american', 'African American'),
        ('african-american', 'African American'),
        ('east asian', 'East Asian'),
        ('southeast asian', 'Southeast Asian'),
        ('south asian', 'South Asian'),
        ('middle eastern', 'Middle Eastern'),
        ('mixed race', 'mixed-race'),
        ('biracial', 'biracial'),
        ('hispanic', 'Hispanic'),
        ('latino', 'Latino'),
        ('latina', 'Latina'),
        ('caucasian', 'Caucasian'),
        ('white', 'White'),
        ('black', 'Black'),
        ('arab', 'Arab'),
        ('european', 'European'),
    ]
    
    for pattern, label in ethnicity_patterns:
        if pattern in desc_lower:
            return f'{label} {nationality} person'
    
    return f'{nationality} person'


def shorten_text(text: str, limit: int = 140) -> str:
    text = str(text or '').strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + '...'

def build_identity_prompt(uuid: int, profile_record: Optional[Dict], init_state_record: Optional[Dict], nationality: str = "Chinese") -> str:
    """Build a compact identity anchor so the generated event image stays close to the reference person."""
    basic_profile = profile_record or {}
    init_state = (init_state_record or {}).get('Init_State', {})

    name = basic_profile.get('name') or (init_state_record or {}).get('name') or f'person {uuid}'
    gender = str(basic_profile.get('gender') or '').strip().lower()
    role_identity = str(basic_profile.get('role_identity') or (init_state_record or {}).get('role_identity') or '').replace('_', ' ')
    age = compute_age(basic_profile.get('birth_date', ''))
    # img2img: the face is anchored by the reference image, so keep a short
    # identity line and a brief appearance fallback instead of listing features.
    appearance = shorten_text(init_state.get('description', ''), 60)

    if nationality == "Chinese":
        gender_cn = '男性' if gender == 'male' else ('女性' if gender == 'female' else '')
        age_text = f"{age}岁" if age is not None else ''
        demo = '、'.join([p for p in [age_text, gender_cn, role_identity] if p])
        prompt_parts = [
            f"主角是{name}（{demo}），与参考图中的人物保持完全一致的面部，脸部清晰无遮挡，不要替换成其他人。",
        ]
        if appearance:
            prompt_parts.append(f"参考特征：{appearance}")
    else:
        stage0_app = basic_profile.get('appearance', {})
        if stage0_app and stage0_app.get('ethnicity'):
            ethnicity = stage0_app['ethnicity']
        else:
            ethnicity = extract_ethnicity_from_description(appearance, nationality)
        gender_en = 'man' if gender == 'male' else ('woman' if gender == 'female' else 'person')
        age_text = f"{age}-year-old" if age is not None else ''
        demo = ' '.join([p for p in [age_text, ethnicity, gender_en] if p])
        prompt_parts = [
            f"The protagonist is {name} ({demo}); keep the exact same face as the reference image, clear and unobstructed, do not replace with anyone else.",
        ]
        if appearance:
            prompt_parts.append(f"Reference: {appearance}")

    return ' '.join(prompt_parts)

def build_event_generation_prompt(scene_prompt: str, identity_prompt: str, nationality: str = "Chinese") -> str:
    """Combine scene description with identity-preservation constraints."""
    if nationality == "Chinese":
        return (
            f"场景：{shorten_text(scene_prompt, 240)} "
            f"{identity_prompt} "
            "所有人物按场景自然着装，忽略参考图中的服装与配饰，保持自然比例。"
            "全图纯净写实，画面任何位置（含屏幕、书本、招牌等）都不出现任何文字、字幕、标识或水印。"
        )
    else:
        return (
            f"Scene: {shorten_text(scene_prompt, 450)} "
            f"{identity_prompt} "
            "Everyone dresses naturally for the scene with natural proportions; ignore clothing and accessories in the reference images. "
            "Clean photorealistic image with no text, captions, logos, or watermarks anywhere (including on screens, books, or signs)."
        )

def format_attempt_logs(attempt_logs: List[Dict]) -> str:
    if not attempt_logs:
        return 'N/A'
    parts = []
    for item in attempt_logs:
        if item.get('status') == 'existing':
            parts.append('existing')
            continue
        similarity = item.get('similarity')
        similarity_text = f"{similarity:.4f}" if similarity is not None else 'N/A'
        status = 'pass' if item.get('passed') else 'fail'
        parts.append(f"{item.get('attempt')}:{similarity_text}:{status}")
    return '[' + '; '.join(parts) + ']'

def get_prompt_limit(nationality: str) -> int:
    return CHINESE_EDIT_PROMPT_MAX if nationality == 'Chinese' else GPT_PROMPT_MAX

def fit_generation_prompt(scene_prompt: str, identity_prompt: str, nationality: str) -> str:
    """Compose the generation prompt within the model limit, scene-first.

    Budget favors the scene (the only thing the reference image does not provide);
    identity stays short because the face is anchored by the reference image.
    """
    limit = get_prompt_limit(nationality)
    scene_limit = 220 if nationality == 'Chinese' else 420
    identity_limit = 120 if nationality == 'Chinese' else 200
    compact_scene = shorten_text(scene_prompt, scene_limit)
    compact_identity = shorten_text(identity_prompt, identity_limit)
    prompt = build_event_generation_prompt(compact_scene, compact_identity, nationality)
    return shorten_text(prompt, limit)

def build_participant_prompt_line(participant_names: List[str],
                                   nationality: str = "Chinese",
                                   social_relationships: Optional[Dict] = None,
                                   protagonist_name: str = "",
                                   protagonist_img_count: int = 1) -> str:
    """Build an explicit image-order -> person mapping for multi-reference face preservation.

    seedream needs to know which reference image maps to whom; being explicit
    keeps each face from drifting or swapping between people.
    """
    if not participant_names:
        return ""
    is_zh = nationality == 'Chinese'
    start = max(1, protagonist_img_count) + 1
    items = []
    for i, name in enumerate(participant_names):
        idx = start + i
        info = (social_relationships or {}).get(name) or {}
        rel = info.get('relationship_type', '')
        if is_zh:
            items.append(f"第{idx}张是{name}（{rel}）" if rel else f"第{idx}张是{name}")
        else:
            items.append(f"image {idx} is {name} ({rel})" if rel else f"image {idx} is {name}")
    mapping = ('、' if is_zh else ', ').join(items)

    if is_zh:
        head = f"参考图对应：第1张是主角{protagonist_name}；{mapping}。" if protagonist_name else f"参考图对应：{mapping}。"
        return head + "每个人严格使用各自参考图的面部，各用各脸，不得混用、替换或改变长相；主角置于前景中心、最突出，配角在背景或两侧。"
    head = (f"Reference mapping: image 1 is the protagonist {protagonist_name}; {mapping}."
            if protagonist_name else f"Reference mapping: {mapping}.")
    return head + (" Each person must strictly use the face from their own reference image — never mix, swap, or alter faces. "
                   "The protagonist is centered and most prominent; supporting characters stay in the background.")


def fit_generation_prompt_v2(scene_prompt: str, identity_prompt: str,
                              participant_names: List[str],
                              nationality: str,
                              social_relationships: Optional[Dict] = None,
                              protagonist_name: str = "",
                              protagonist_img_count: int = 1) -> str:
    """Like ``fit_generation_prompt`` but keeps an explicit reference-image mapping.

    The image-order mapping is face-preservation-critical, so it is appended in
    full (not truncated) within the model hard limit.
    """
    participant_line = build_participant_prompt_line(
        participant_names, nationality, social_relationships,
        protagonist_name, protagonist_img_count)
    limit = get_prompt_limit(nationality)
    scene_limit = 180 if nationality == 'Chinese' else 360
    identity_limit = 90 if nationality == 'Chinese' else 160
    compact_scene = shorten_text(scene_prompt, scene_limit)
    compact_identity = shorten_text(identity_prompt, identity_limit)
    main_prompt = build_event_generation_prompt(compact_scene, compact_identity, nationality)
    full_prompt = f"{main_prompt} {participant_line}" if participant_line else main_prompt
    return shorten_text(full_prompt, limit)


def create_safer_prompt(event: Dict, identity_prompt: str = "", nationality: str = "Chinese") -> str:
    """Create a shorter, safer fallback prompt when moderation blocks the original one."""
    event_name = event.get('event_name', 'daily activity')
    description = str(event.get('description', '')).strip()

    if nationality == "Chinese":
        short_desc = description[:120] if description else '人们在平静的日常环境中互动'
        scene_prompt = (
            f"一个真实的、光线充足的日常场景，关于{event_name}，"
            f"展示{short_desc}，自然表情，简洁构图，平和的氛围。"
        )[:280]
    else:
        short_desc = description[:120] if description else 'people interacting in a calm everyday setting'
        scene_prompt = (
            f"A realistic, well-lit everyday scene about {event_name}, "
            f"showing {short_desc}, natural expressions, clean composition, and a neutral atmosphere."
        )[:280]

    if identity_prompt:
        return build_event_generation_prompt(scene_prompt, identity_prompt, nationality)
    return scene_prompt


def generate_scene_prompt(event: Dict, nationality: str = "Chinese") -> str:
    """Use LLM to generate a scene description prompt for image generation."""
    from datetime import datetime
    event_name = event.get('event_name', 'Event')
    event_start = event.get('event_start_time', '')
    description = event.get('description', '')
    participants = event.get('participants', [])

    # Match the persona's language so the open-source English build stays Chinese-free.
    # (The backend is now Gemini, which is multilingual; only legacy doubao-seedream was Chinese-only.)
    is_chinese = (nationality == "Chinese")

    names = [p.get('name', 'person') if isinstance(p, dict) else str(p) for p in participants]
    if not names:
        participant_desc = ""
    elif is_chinese:
        participant_desc = f"参与者：{'、'.join(names)}"
    else:
        participant_desc = f"Participants: {', '.join(names)}"

    time_desc = ""
    if event_start:
        try:
            dt = datetime.strptime(event_start, "%Y-%m-%d %H:%M:%S")
            time_desc = dt.strftime('%Y年%m月%d日 %H:%M') if is_chinese else dt.strftime('%Y-%m-%d %H:%M')
        except Exception:
            time_desc = str(event_start)

    if is_chinese:
        prompt = f"""根据以下事件信息，生成一句简洁的中文描述，适合用于文生图模型生成真实场景图片。重点描述场景布置、氛围、人物动作和环境。

事件：{event_name}
时间：{time_desc}
{participant_desc}
描述：{description[:500]}

请用一句话生成生动的场景描述，用于图片生成。重点描述视觉元素：场所、光线、人物的动作和表情、物品和氛围。要真实、细致。

重要：使用中性、积极的语言。避免暗示负面情绪、紧张、压力或不适的词语。客观描述场景，专注于活动和环境。

重要：场景描述中不要包含任何会导致图片中出现文字的元素。不要提及屏幕上显示的具体内容、书本封面文字、招牌文字、标题等。只描述物体的视觉外观（如"笔记本电脑"而非"打开理财页面的笔记本电脑"）。

重要：生成的描述必须在300个字符以内，以符合API长度限制。"""
    else:
        prompt = f"""Based on the following event information, generate ONE concise English sentence suitable for a text-to-image model to create a realistic scene image. Focus on the setting, atmosphere, actions, and environment.

Event: {event_name}
Time: {time_desc}
{participant_desc}
Description: {description[:500]}

Generate a vivid scene description in one sentence for image generation. Focus on visual elements like location, lighting, people's actions and expressions, objects, and atmosphere. Make it realistic and detailed.

IMPORTANT: Use neutral, positive language. Avoid words that suggest negative emotions, tension, stress, or discomfort. Instead, describe scenes objectively with focus on activities and settings.

IMPORTANT: The generated sentence must be under 300 characters to meet API length constraints."""

    is_cn = is_chinese  # pick the model matching the scene-description language
    scene_prompt, _ = llm_request(
        system_prompt="You are a helpful assistant",
        user_prompt=prompt,
        model=get_text_llm_model(is_cn),
        extract_json=False,
    )
    scene_prompt = scene_prompt.strip()

    # Limit prompt length to 500 characters for API safety
    if len(scene_prompt) > 500:
        logger.warning(f"Scene prompt too long ({len(scene_prompt)} chars), truncating to 500")
        scene_prompt = scene_prompt[:500]

    logger.info(f"Generated scene prompt length: {len(scene_prompt)} chars")
    return scene_prompt
