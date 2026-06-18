"""Event-photo generator (Memories / EventPhoto): portraits + per-event scene images.

Holds the 'fix_event_images' logger + dirs, persona appearance maps, the
identity-anchored portrait build, the per-event face-verified scene image
generation, and ``main`` / ``EventPhotoGenerator``. Data loaders live in
``.data``; prompt building in ``.prompts``; face recognition in ``backends.faces``.
"""
import argparse
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional


import config
from common import read_jsonl, write_jsonl, load_sub_events_index, expand_events_for_imaging
from core import DIR_NAME
from backends.images import generate_event_images, generate_person_images
from backends.llm import set_log_context
from backends.faces import (
    FACE_SIMILARITY_THRESHOLD,
    extract_reference_embeddings,
    get_face_threshold,
    get_reference_embeddings_for_uuid,
    verify_face_match,
    verify_named_identities,
)
from infra.base_generator import Generator

from .data import compute_age, load_init_state_map, load_nationality_map, load_profile_map
from .prompts import (
    build_identity_prompt,
    create_safer_prompt,
    extract_ethnicity_from_description,
    fit_generation_prompt,
    fit_generation_prompt_v2,
    format_attempt_logs,
    generate_scene_prompt,
)

try:
    from fix_face_orientation import auto_orient_face as _auto_orient_portrait
except ImportError:
    _auto_orient_portrait = None


LOG_DIR = config.LOG_DIR
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'fix_event_images_summary.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('fix_event_images')

# Person portrait / prompt directories.
PROMPTS_DIR = config.PROMPTS_DIR
PORTRAITS_DIR = os.path.join(config.OUTPUT_DIR, 'image')  # person images under image/{uuid}/person/


try:
    from appearance_features import get_appearance
except ImportError:
    logger.warning("appearance_features.py not found, using a neutral fallback")

    def get_appearance(uuid, nationality="Chinese", ethnicity_hint="", profile_record=None):
        if nationality == "Chinese":
            return {"face": "鹅蛋脸", "eyes": "双眼皮", "nose": "端正鼻梁", "body": "匀称", "skin": "健康肤色"}
        return {"face": "oval face", "eyes": "almond eyes", "nose": "straight nose", "body": "average build", "skin": "light skin"}


CLOTHING_MAP = {
    'courier': 'courier uniform or casual work clothes',
    'delivery_driver': 'delivery rider uniform or casual work clothes',
    'female_college_student': 'casual student clothes',
    'male_college_student': 'casual student clothes',
    'government_office_worker': 'business formal attire',
    'housewife_mother': 'comfortable casual home clothes',
    'stay_at_home_father': 'comfortable casual clothes',
    'local_entrepreneur': 'casual business clothes',
    'young_manager': 'smart business casual',
    'young_professional': 'smart casual work clothes',
}

CLOTHING_MAP_ZH = {
    'courier': '快递工作服或休闲工装',
    'delivery_driver': '外卖骑手工服或休闲工装',
    'female_college_student': '休闲学生装',
    'male_college_student': '休闲学生装',
    'government_office_worker': '正式商务着装',
    'housewife_mother': '舒适居家休闲装',
    'stay_at_home_father': '舒适休闲装',
    'local_entrepreneur': '休闲商务装',
    'young_manager': '时尚商务休闲装',
    'young_professional': '时尚休闲工作装',
}


def build_person_portrait_prompt(uuid: int, profile_record: Optional[Dict],
                                  init_state_record: Optional[Dict],
                                  nationality: str, prompts_dir: str) -> str:
    """Select the Chinese/English prompt template based on nationality, fill in the persona info, and return the final prompt."""
    basic = profile_record or {}
    init_state = (init_state_record or {}).get('Init_State', {})

    # Basic info
    gender_raw = str(basic.get('gender', '')).strip().lower()
    role_identity = str(basic.get('role_identity', '') or (init_state_record or {}).get('role_identity', '')).replace('_', ' ')  # noqa: F841
    age = compute_age(basic.get('birth_date', ''))
    description = str(init_state.get('description', '')).strip()

    # Appearance features - pick the right feature pool based on nationality
    ethnicity_hint = extract_ethnicity_from_description(description, nationality) if nationality != 'Chinese' else ''
    app = get_appearance(uuid, nationality=nationality, ethnicity_hint=ethnicity_hint, profile_record=basic)
    face = app.get('face', '')
    eyes = app.get('eyes', '')
    face_parts = []
    if face:
        face_parts.append(face)
    if eyes:
        face_parts.append(eyes)
    face_detail = ', '.join(face_parts) + '.' if face_parts else ''

    # Extra appearance details (from the stage0 appearance field, for non-Chinese personas only)
    hair_detail = ''
    skin_emphasis = ''
    if nationality != 'Chinese' and 'appearance' in basic:
        hair_color = app.get('hair_color', '')
        hair_style = app.get('hair_style', '')
        facial_hair = app.get('facial_hair', '')
        skin_color = app.get('skin', '')
        ethnicity_from_app = app.get('ethnicity', '')
        
        hair_parts = []
        if hair_style and hair_color:
            hair_parts.append(f'{hair_style} {hair_color} hair')
        elif hair_color:
            hair_parts.append(f'{hair_color} hair')
        if facial_hair and facial_hair.lower() not in ('none', 'clean-shaven', ''):
            hair_parts.append(facial_hair)
        hair_detail = ', '.join(hair_parts)
        
        if skin_color and ethnicity_from_app:
            skin_emphasis = f'This person is {ethnicity_from_app} with {skin_color}.'

    # Portrait prompt template: Chinese (_zh) for Chinese personas, else English (_en).
    if nationality == 'Chinese':
        template_file = os.path.join(prompts_dir, 'image_person_portrait_zh.txt')
        gender_word = '男性' if gender_raw in ('male', '男') else '女性' if gender_raw in ('female', '女') else '人'
        ethnicity = '中国人'
        clothing = CLOTHING_MAP_ZH.get(basic.get('role_identity', '') or (init_state_record or {}).get('role_identity', ''), '休闲装')
    else:
        template_file = os.path.join(prompts_dir, 'image_person_portrait_en.txt')
        gender_word = 'man' if gender_raw in ('male', '男') else 'woman' if gender_raw in ('female', '女') else 'person'
        # Prefer stage0's appearance.ethnicity, otherwise extract from the description
        if 'appearance' in basic and basic['appearance'].get('ethnicity'):
            ethnicity = basic['appearance']['ethnicity'] + ' ' + nationality + ' person'
        else:
            ethnicity = extract_ethnicity_from_description(description, nationality)
        clothing = CLOTHING_MAP.get(basic.get('role_identity', '') or (init_state_record or {}).get('role_identity', ''), 'casual clothes')

    age_str = str(age) if age else '30'

    # Load the template and fill it in
    try:
        with open(template_file, 'r', encoding='utf-8') as f:
            template = f.read()
        prompt = template.format(
            age=age_str,
            gender=gender_word,
            ethnicity=ethnicity,
            description=description,
            face_detail=face_detail,
            clothing=clothing,
            hair_detail=hair_detail,
            skin_emphasis=skin_emphasis,
        )
    except (FileNotFoundError, KeyError) as e:
        logger.warning(f"[uuid={uuid}] Failed to load prompt template {template_file}: {e}, using fallback")
        if nationality == 'Chinese':
            prompt = (
                f"一张{age_str}岁{gender_word}{ethnicity}的真实人像照片。"
                f"{description} {face_detail} "
                f"穿着{clothing}。"
                f"构图要求：正面半身照，头部位于画面上方居中（头顶靠近画面顶部，而非抬头仰望），头肩构图，面部清晰无遮挡。"
                f"画面中只能有一个人，不能出现第二个人。"
                f"平视镜头，相机与双眼同高（eye level），视线水平直视镜头，头部保持正直、不上扬也不低垂，自然表情，纯色浅色背景，自然影棚灯光，写实风格，高清细节。"
                f"不要添加任何文字、水印或标题。"
            )
        else:
            hair_part = f" {hair_detail}." if hair_detail else ""
            skin_part = f" {skin_emphasis}" if skin_emphasis else ""
            prompt = (
                f"A realistic portrait photo of a single {age_str}-year-old {ethnicity} {gender_word}.{skin_part} "
                f"{description} {face_detail}{hair_part} "
                f"Wearing {clothing}. "
                f"The portrait must be upright with the head at the top of the frame. "
                f"Head-and-shoulders framing, face centered and unobstructed. "
                f"Exactly one person in the image, no other people visible. "
                f"Looking directly at camera, neutral expression, plain light-colored background, "
                f"natural studio lighting, photorealistic, high detail. "
                f"Do NOT add any text, watermarks, or captions."
            )

    # Truncate to the model limit
    from backends.images import get_generation_model_and_limit
    _, max_len = get_generation_model_and_limit(nationality)
    if len(prompt) > max_len:
        prompt = prompt[:max_len]

    return prompt

def ensure_person_portrait(uuid: int, person_dir: str,
                            profile_record: Optional[Dict],
                            init_state_record: Optional[Dict],
                            nationality: str, prompts_dir: str) -> Optional[str]:
    """Check whether the person reference image exists; generate it if not. Returns the image path or None."""
    target_path = os.path.join(person_dir, f'{uuid}_person_0.png')

    if os.path.exists(target_path):
        logger.info(f"[uuid={uuid}] Person portrait exists: {target_path}")
        return target_path

    logger.info(f"[uuid={uuid}] Person portrait missing, generating...")
    os.makedirs(person_dir, exist_ok=True)

    prompt = build_person_portrait_prompt(uuid, profile_record, init_state_record, nationality, prompts_dir)
    logger.info(f"[uuid={uuid}] Portrait prompt ({len(prompt)} chars): {prompt[:120]}...")

    try:
        paths = generate_person_images(prompt, output_dir=person_dir, nationality=nationality)
    except Exception as e:
        logger.error(f"[uuid={uuid}] generate_person_images failed: {e}")
        return None

    if paths and os.path.exists(paths[0]):
        # Auto-orient person portrait if face is upside down/sideways
        if _auto_orient_portrait is not None:
            rot, ok = _auto_orient_portrait(paths[0])
            if rot > 0:
                logger.info(f"[uuid={uuid}] Person portrait auto-oriented {rot} degrees")
        if paths[0] != target_path:
            os.replace(paths[0], target_path)
            for p in paths[1:]:
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except OSError:
                    pass
        logger.info(f"[uuid={uuid}] Person portrait generated: {target_path}")
        return target_path
    else:
        logger.error(f"[uuid={uuid}] Person portrait generation failed — API returned no image")
        return None

def resolve_companion_data_file(base_file: str, filename: str) -> str:
    """Resolve a companion data file near the active input, with fallback to the default dataset."""
    candidate = os.path.join(os.path.dirname(base_file), filename)
    if os.path.exists(candidate):
        return candidate
    return os.path.join(config.OUTPUT_DIR, 'data', filename)


def cleanup_generated_images(image_paths: List[str], keep_path: Optional[str] = None):
    """Delete generated temporary images that should not be kept."""
    for path in image_paths or []:
        if not path or path == keep_path:
            continue
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError as e:
            logger.warning(f"Failed to remove temporary image {path}: {e}")

_PARTICIPANT_EMB_CACHE: Dict[str, List] = {}
_PARTICIPANT_EMB_LOCK = threading.Lock()


def get_participant_embeddings(avatar_map: Dict[str, str]) -> Dict[str, List]:
    """Embeddings for each participant avatar (cached by avatar path)."""
    out: Dict[str, List] = {}
    for name, path in avatar_map.items():
        with _PARTICIPANT_EMB_LOCK:
            cached = _PARTICIPANT_EMB_CACHE.get(path)
        if cached is None:
            cached = extract_reference_embeddings([path])
            with _PARTICIPANT_EMB_LOCK:
                _PARTICIPANT_EMB_CACHE[path] = cached
        if cached:
            out[name] = cached
    return out


def find_participant_avatars(uuid: int, participant_names: List[str],
                             member_avatar_base: str) -> Dict[str, str]:
    """Locate participant avatars in ``image/uid{uuid}/group_chat_members/``.

    Avatars are produced by the conversation stage with the naming convention
    ``{uuid}_{member_name}_avatar.png``. Returns ``{name: path}`` for matches only.
    """
    if not member_avatar_base:
        return {}
    avatar_dir = os.path.join(member_avatar_base, f'uid{uuid}', DIR_NAME['group_chat_members'])
    if not os.path.exists(avatar_dir):
        return {}
    prefix = f'{uuid}_'
    suffix = '_avatar.png'
    available = {}
    for fname in os.listdir(avatar_dir):
        if fname.endswith(suffix) and fname.startswith(prefix):
            name = fname[len(prefix):-len(suffix)]
            available[name] = os.path.join(avatar_dir, fname)
    found = {}
    for pname in participant_names:
        pname_clean = pname.strip()
        if pname_clean and pname_clean in available:
            found[pname_clean] = available[pname_clean]
    return found


def generate_event_image_for_uuid(uuid: int, event_idx: int, event: Dict,
                                   person_image_dir: str, output_dir: str,
                                   profile_record: Optional[Dict] = None,
                                   init_state_record: Optional[Dict] = None,
                                   nationality: str = "Chinese",
                                   verify_face: bool = True,
                                   face_threshold: float = FACE_SIMILARITY_THRESHOLD,
                                   member_avatar_base: str = "",
                                   social_relationships: Optional[Dict] = None,
                                   force: bool = False) -> Dict:
    """Generate one event scene image for a specific uuid and event index."""
    set_log_context(uuid=uuid, stage="fix_event_images", event_idx=event_idx)
    target_name = f"{uuid}_event_{event_idx}.png"
    target_path = os.path.join(output_dir, target_name)
    result = {
        'uuid': uuid,
        'event_idx': event_idx,
        'filename': None,
        'success': False,
        'best_similarity': None,
        'verify_reason': None,
        'attempt_logs': [],
        'participant_refs': 0,
    }

    if os.path.exists(target_path) and not force:
        logger.info(f"[uuid={uuid}] event_{event_idx}: SKIP (exists)")
        result['filename'] = target_name
        result['success'] = True
        result['verify_reason'] = 'existing file'
        result['attempt_logs'] = [{'status': 'existing'}]
        return result

    logger.info(f"[uuid={uuid}] event_{event_idx}: generating scene prompt...")
    try:
        scene_prompt = generate_scene_prompt(event, nationality=nationality)
        identity_prompt = build_identity_prompt(uuid, profile_record, init_state_record, nationality=nationality)
    except Exception as e:
        logger.error(f"[uuid={uuid}] event_{event_idx}: LLM prompt failed: {e}")
        result['verify_reason'] = f'llm prompt failed: {e}'
        return result

    # Get person images for this uuid (protagonist reference portraits, up to 3)
    person_image_paths = []
    if os.path.exists(person_image_dir):
        for fname in sorted(os.listdir(person_image_dir)):
            if fname.startswith(f"{uuid}_person_") and fname.endswith('.png'):
                person_image_paths.append(os.path.join(person_image_dir, fname))
    person_image_paths = person_image_paths[:3]

    # Participant reference avatars (from group_chat_members). No cap: every matched
    # participant avatar is attached so non-protagonist faces stay consistent too.
    participant_names = [
        p.get('name', '') if isinstance(p, dict) else str(p)
        for p in event.get('participants', [])
    ]
    participant_names = [n.strip() for n in participant_names if n and n.strip()]
    participant_avatar_map = find_participant_avatars(uuid, participant_names, member_avatar_base)
    participant_image_paths = list(participant_avatar_map.values())
    matched_names = list(participant_avatar_map.keys())
    result['participant_refs'] = len(matched_names)
    if matched_names:
        logger.info(f"[uuid={uuid}] event_{event_idx}: found {len(matched_names)} participant avatars: {matched_names}")

    # Protagonist refs first, participants after.
    all_image_paths = person_image_paths + participant_image_paths

    try:
        protagonist_name = (profile_record or {}).get('name', '')
        generation_prompt = fit_generation_prompt_v2(
            scene_prompt, identity_prompt, matched_names, nationality, social_relationships,
            protagonist_name, len(person_image_paths)
        )
        result['scene_prompt'] = scene_prompt
        logger.info(f"[uuid={uuid}] event_{event_idx}: scene_prompt={scene_prompt[:100]}...")
        logger.info(f"[uuid={uuid}] event_{event_idx}: identity_anchor={identity_prompt[:160]}...")
        logger.info(f"[uuid={uuid}] event_{event_idx}: generation_prompt_len={len(generation_prompt)}, "
                    f"total_refs={len(all_image_paths)} (person={len(person_image_paths)}, participant={len(participant_image_paths)})")
    except Exception as e:
        logger.error(f"[uuid={uuid}] event_{event_idx}: prompt construction failed: {e}")
        result['verify_reason'] = f'prompt construction failed: {e}'
        return result

    reference_embeddings = []
    participant_embeddings: Dict[str, List] = {}
    if verify_face:
        reference_embeddings = get_reference_embeddings_for_uuid(uuid, person_image_paths)
        if reference_embeddings:
            logger.info(f"[uuid={uuid}] event_{event_idx}: loaded {len(reference_embeddings)} reference face embeddings")
        else:
            logger.warning(f"[uuid={uuid}] event_{event_idx}: face verification unavailable for this uuid, continuing without verification")
            verify_face = False
        if verify_face and participant_avatar_map:
            participant_embeddings = get_participant_embeddings(participant_avatar_map)
            if participant_embeddings:
                logger.info(f"[uuid={uuid}] event_{event_idx}: loaded participant embeddings for {list(participant_embeddings.keys())}")

    logger.info(f"[uuid={uuid}] event_{event_idx}: generating image (person_imgs={len(person_image_paths)})...")

    # Retry logic for API errors
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if all_image_paths:
                image_paths = generate_event_images(generation_prompt, all_image_paths, output_dir=output_dir, nationality=nationality)
            else:
                image_paths = generate_person_images(generation_prompt, output_dir=output_dir, nationality=nationality)

            if image_paths and os.path.exists(image_paths[0]):
                generated_path = image_paths[0]

                # Post-generation identity fix: swap the protagonist + matched
                # participants to their reference faces before verification, so
                # identity is pinned regardless of what the generator drew.
                # No-op when the inswapper model / insightface is unavailable.
                try:
                    from .face_swapper import apply_face_swap
                    swapped = apply_face_swap(generated_path, person_image_paths, participant_avatar_map)
                    if swapped:
                        logger.info(f"[uuid={uuid}] event_{event_idx}: face-swap applied {swapped}")
                except Exception as e:
                    logger.warning(f"[uuid={uuid}] event_{event_idx}: face-swap skipped ({e})")

                if verify_face:
                    is_match, best_similarity, verify_reason = verify_face_match(generated_path, reference_embeddings, face_threshold)
                    result['best_similarity'] = best_similarity
                    result['verify_reason'] = verify_reason
                    result['attempt_logs'].append({
                        'attempt': attempt + 1,
                        'similarity': best_similarity,
                        'passed': is_match,
                        'reason': verify_reason,
                    })
                    if not is_match:
                        logger.warning(
                            f"[uuid={uuid}] event_{event_idx}: face verification failed "
                            f"(attempt {attempt+1}/{max_retries}): {verify_reason}"
                        )
                        cleanup_generated_images(image_paths)
                        if attempt < max_retries - 1:
                            time.sleep(2)
                            continue
                        logger.error(f"[uuid={uuid}] event_{event_idx}: all attempts failed face verification")
                        return result

                    logger.info(
                        f"[uuid={uuid}] event_{event_idx}: face verification passed "
                        f"(attempt {attempt+1}/{max_retries}): {verify_reason}"
                    )

                # Participant face verification: each matched participant must also
                # appear in the scene. Retry on mismatch; after the last attempt keep
                # the best image but record which participants did not verify.
                if verify_face and participant_embeddings:
                    pv = verify_named_identities(generated_path, participant_embeddings, face_threshold)
                    result['participant_verify'] = {n: s for n, (_ok, s) in pv.items()}
                    failed = [n for n, (ok, _s) in pv.items() if not ok]
                    pv_summary = ', '.join(
                        f"{n}={s:.4f}" if s is not None else f"{n}=NA" for n, (_ok, s) in pv.items()
                    )
                    if failed and attempt < max_retries - 1:
                        logger.warning(
                            f"[uuid={uuid}] event_{event_idx}: participant verification failed "
                            f"(attempt {attempt+1}/{max_retries}) for {failed} [{pv_summary}], retrying"
                        )
                        cleanup_generated_images(image_paths)
                        time.sleep(2)
                        continue
                    if failed:
                        result['participants_failed'] = failed
                        logger.warning(
                            f"[uuid={uuid}] event_{event_idx}: participant verification still failing for "
                            f"{failed} after {max_retries} attempts [{pv_summary}], keeping best image"
                        )
                    else:
                        logger.info(
                            f"[uuid={uuid}] event_{event_idx}: participant verification passed [{pv_summary}]"
                        )

                os.replace(generated_path, target_path)
                cleanup_generated_images(image_paths, keep_path=generated_path)
                logger.info(f"[uuid={uuid}] event_{event_idx}: OK -> {target_name} (attempt {attempt+1}/{max_retries})")
                result['filename'] = target_name
                result['success'] = True
                return result
            else:
                logger.warning(f"[uuid={uuid}] event_{event_idx}: API returned no image (attempt {attempt+1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                else:
                    logger.error(f"[uuid={uuid}] event_{event_idx}: All attempts failed")
                    result['verify_reason'] = 'api returned no image'
                    return result
        except Exception as e:
            logger.warning(f"[uuid={uuid}] event_{event_idx}: image generation failed (attempt {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                error_str = str(e)
                # If error contains "content parameter's length invalid", try shortening the prompt
                if "content parameter's length invalid" in error_str and len(generation_prompt) > 200:
                    # Shorten prompt for next attempt
                    new_length = max(160, len(generation_prompt) // 2)
                    generation_prompt = generation_prompt[:new_length]
                    logger.info(f"[uuid={uuid}] event_{event_idx}: shortened prompt to {len(generation_prompt)} chars")
                # If error contains "moderation_blocked" or "safety system", try to sanitize the prompt
                elif "moderation_blocked" in error_str or "safety system" in error_str:
                    # Create a safer, simplified prompt for next attempt
                    logger.info(f"[uuid={uuid}] event_{event_idx}: safety system blocked, creating safer prompt")
                    generation_prompt = fit_generation_prompt(create_safer_prompt(event, nationality=nationality), identity_prompt, nationality)
                time.sleep(5)
                continue
            else:
                logger.error(f"[uuid={uuid}] event_{event_idx}: All attempts failed with exception: {e}")
                result['verify_reason'] = str(e)
                return result

    # Should not reach here
    return result

def main():
    parser = argparse.ArgumentParser(description='Generate all event scene images per uuid (100 events × 10 persons)')
    parser.add_argument('--max-workers', type=int, default=2,
                        help='Parallel API calls (default: 2)')
    parser.add_argument('--events-file', type=str,
                        default=os.path.join(config.OUTPUT_DIR, 'data', 'annual_events.jsonl'))
    parser.add_argument('--sessions-file', type=str,
                        default=None,
                        help='Deprecated compatibility flag; stage7.1 no longer reads or rewrites stage5 sessions')
    parser.add_argument('--image-base-dir', type=str,
                        default=os.path.join(config.OUTPUT_DIR, 'image'),
                        help='Base image directory (uid subfolders will be created automatically)')
    parser.add_argument('--uuid-filter', type=int, nargs='+', default=None,
                        help='Only process these UUIDs')
    parser.add_argument('--disable-face-verify', action='store_true',
                        help='Disable face verification and regeneration')
    parser.add_argument('--face-threshold', type=float, default=FACE_SIMILARITY_THRESHOLD,
                        help='Cosine similarity threshold for face verification')
    parser.add_argument('--sub-events-file', type=str,
                        default=os.path.join(config.OUTPUT_DIR, 'data', 'sub_events.jsonl'),
                        help='stage4.5 sub-events JSONL for expanding mid/long-term events')
    parser.add_argument('--force', action='store_true',
                        help='Ignore existing images and regenerate from scratch')
    args = parser.parse_args()

    image_base = args.image_base_dir

    def person_dir_for(uid):
        d = os.path.join(image_base, f'uid{uid}', DIR_NAME['person'])
        os.makedirs(d, exist_ok=True)
        return d

    def event_dir_for(uid):
        d = os.path.join(image_base, f'uid{uid}', DIR_NAME['event'])
        os.makedirs(d, exist_ok=True)
        return d

    logger.info(f"{'='*60}")
    logger.info("Fix: Generate Independent Event Scene Images")
    logger.info(f"Events file: {args.events_file}")
    logger.info(f"Output: {image_base}/uid{{N}}/event/")
    logger.info(f"Max workers: {args.max_workers}")
    logger.info(f"UUID filter: {args.uuid_filter if args.uuid_filter else 'ALL'}")
    logger.info(f"Face verify: {not args.disable_face_verify}")
    logger.info(f"Face threshold: {args.face_threshold}")
    logger.info(f"Sub-events file: {args.sub_events_file}")
    logger.info(f"{'='*60}")

    # Load sub-events index for expanding mid/long-term events
    sub_index = load_sub_events_index(args.sub_events_file)
    logger.info(f"Sub-events index: {len(sub_index)} parent events loaded")

    # Load data
    events_records = read_jsonl(args.events_file)
    events_by_uuid = {r['uuid']: r for r in events_records}

    # Load nationality map from basic_profiles.jsonl
    profiles_file = resolve_companion_data_file(args.events_file, 'basic_profiles.jsonl')
    nationality_map = load_nationality_map(profiles_file)
    profile_map = load_profile_map(profiles_file)
    init_states_file = resolve_companion_data_file(args.events_file, 'init_states.jsonl')
    init_state_map = load_init_state_map(init_states_file)
    if not nationality_map:
        logger.warning("Nationality map is empty, using default 'Chinese' for all uuids")
        nationality_map = {i: "Chinese" for i in events_by_uuid.keys()}

    # Per-uuid social_relationships (name -> {relationship_type, description}) for
    # annotating participant reference avatars in the generation prompt.
    social_rel_map = {}
    for uid, rec in events_by_uuid.items():
        init_state = rec.get('Init_State')
        if isinstance(init_state, dict):
            sr = init_state.get('social_relationships')
            if isinstance(sr, dict):
                social_rel_map[uid] = sr

    # Build task list: (uuid, image_id, event)
    tasks = []
    expanded_events_map = {}  # (uuid, image_id) -> event, for the stage7_1 manifest
    for uuid in sorted(events_by_uuid.keys()):
        if args.uuid_filter and uuid not in args.uuid_filter:
            continue
        event_record = events_by_uuid.get(uuid)
        if not event_record:
            logger.warning(f"[uuid={uuid}] No events data, skip")
            continue
        events = event_record.get('Events', [])
        for image_id, event in expand_events_for_imaging(uuid, events, sub_index):
            tasks.append((uuid, image_id, event))
            expanded_events_map[(uuid, image_id)] = event

    logger.info(f"Total tasks: {len(tasks)}")

    processed_uuids = sorted({uuid for uuid, _, _ in tasks})
    logger.info(f"{'='*60}")
    logger.info(f"Phase 0: Ensure person portraits exist for {len(processed_uuids)} uuids")
    logger.info(f"{'='*60}")
    portrait_ok = 0
    portrait_fail = 0
    for uid in processed_uuids:
        result_path = ensure_person_portrait(
            uid, person_dir_for(uid),
            profile_map.get(uid),
            init_state_map.get(uid),
            nationality_map.get(uid, "Chinese"),
            PROMPTS_DIR,
        )
        if result_path:
            portrait_ok += 1
        else:
            portrait_fail += 1
    logger.info(f"Phase 0 done: {portrait_ok} portraits ready, {portrait_fail} failed")
    logger.info(f"{'='*60}")

    # Generate images in parallel
    results = {}  # (uuid, event_idx) -> result dict
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        future_to_task = {
            executor.submit(
                generate_event_image_for_uuid,
                uuid, event_idx, event,
                person_dir_for(uuid), event_dir_for(uuid),
                profile_map.get(uuid),
                init_state_map.get(uuid),
                nationality_map.get(uuid, "Chinese"),
                not args.disable_face_verify,
                get_face_threshold(nationality_map.get(uuid, "Chinese")),
                image_base,
                social_rel_map.get(uuid),
                args.force,
            ): (uuid, event_idx)
            for uuid, event_idx, event in tasks
        }
        for future in as_completed(future_to_task):
            uuid, event_idx = future_to_task[future]
            try:
                result = future.result()
                results[(uuid, event_idx)] = result
            except Exception as e:
                logger.error(f"[uuid={uuid}] event_{event_idx}: unexpected error: {e}")
                results[(uuid, event_idx)] = {
                    'uuid': uuid,
                    'event_idx': event_idx,
                    'filename': None,
                    'success': False,
                    'best_similarity': None,
                    'verify_reason': str(e),
                    'attempt_logs': [],
                }

    # Check early results (first 5) for anomalies. Sort by a string-coerced key
    # because event_idx mixes ints (main events) and strings (sub-events like
    # "6_2"), which are not directly comparable.
    logger.info("Checking first 5 results for anomalies...")
    early_results = sorted(results.items(), key=lambda kv: (kv[0][0], str(kv[0][1])))[:5]
    for (uuid, event_idx), info in early_results:
        if info and info.get('success') and info.get('filename'):
            fpath = os.path.join(event_dir_for(uuid), info['filename'])
            size = os.path.getsize(fpath) if os.path.exists(fpath) else 0
            similarity = info.get('best_similarity')
            similarity_str = f", similarity={similarity:.4f}" if similarity is not None else ""
            attempts_str = format_attempt_logs(info.get('attempt_logs', []))
            logger.info(f"  [uuid={uuid}] event_{event_idx}: {info['filename']} ({size//1024}KB{similarity_str}, attempts={attempts_str})")
        else:
            similarity = info.get('best_similarity') if info else None
            similarity_str = f", similarity={similarity:.4f}" if similarity is not None else ""
            reason = info.get('verify_reason') if info else 'unknown error'
            attempts_str = format_attempt_logs(info.get('attempt_logs', [])) if info else 'N/A'
            logger.warning(f"  [uuid={uuid}] event_{event_idx}: FAILED{similarity_str}, attempts={attempts_str}, reason={reason}")

    if args.sessions_file:
        logger.info("--sessions-file is deprecated and ignored; stage7.1 writes only its event-image manifest")

    # The DAG declares this node's output as ``event_images.jsonl`` and
    # ``memory_summary``'s merge consumes it to fold event images into the stage10
    # index. Emit it next to the events file (honors the DAG data directory).
    jsonl_records = []
    for (uuid_key, event_idx_key), info in sorted(results.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        event_data = expanded_events_map.get((uuid_key, event_idx_key), {})
        participants_raw = event_data.get('participants', [])
        participant_names = [
            p.get('name', '') if isinstance(p, dict) else str(p)
            for p in participants_raw
        ]
        participant_names = [n.strip() for n in participant_names if n.strip()]
        eid_str = str(event_idx_key)
        parent_eid = int(eid_str.split('_')[0]) if '_' in eid_str else event_idx_key
        filename = info.get('filename', '') if info else ''
        image_path = os.path.join(event_dir_for(uuid_key), filename) if filename else ''
        jsonl_records.append({
            'uuid': uuid_key,
            'sub_event_id': eid_str,
            'event_id': parent_eid,
            'event_name': event_data.get('event_name', event_data.get('event', event_data.get('title', ''))),
            'participants': participant_names,
            'filename': filename,
            'image_path': image_path,
            'success': bool(info.get('success')) if info else False,
            'best_similarity': info.get('best_similarity') if info else None,
            'scene_prompt': info.get('scene_prompt', '') if info else '',
        })
    jsonl_output_path = os.path.join(os.path.dirname(args.events_file), 'event_images.jsonl')
    write_jsonl(jsonl_records, jsonl_output_path)
    logger.info(f"Saved {len(jsonl_records)} records to {jsonl_output_path}")

    # Summary
    success = sum(1 for v in results.values() if v and v.get('success'))
    failed = sum(1 for v in results.values() if not v or not v.get('success'))
    logger.info(f"{'='*60}")
    logger.info(f"DONE: {success} success, {failed} failed out of {len(tasks)} tasks")
    processed_uuids = sorted({uuid for uuid, _, _ in tasks})
    for uuid in processed_uuids:
        uuid_results = [info for (task_uuid, _), info in results.items() if task_uuid == uuid]
        ok = sum(1 for info in uuid_results if info and info.get('success'))
        total = len(uuid_results)
        logger.info(f"  uuid={uuid}: {ok}/{total} images generated")
        failed_infos = [info for info in uuid_results if not info or not info.get('success')]
        for info in failed_infos:
            if not info:
                logger.warning("    event=unknown, similarity=N/A, reason=unknown error")
                continue
            similarity = info.get('best_similarity')
            similarity_str = f"{similarity:.4f}" if similarity is not None else 'N/A'
            attempts_str = format_attempt_logs(info.get('attempt_logs', []))
            logger.warning(
                f"    event_{info['event_idx']}: similarity={similarity_str}, "
                f"threshold={args.face_threshold}, attempts={attempts_str}, "
                f"reason={info.get('verify_reason') or 'unknown'}"
            )
    logger.info(f"{'='*60}")


# Domain generator -- thin uniform entry point for the future pipeline DAG.

class EventPhotoGenerator(Generator):
    """Generate per-persona event scene images (one per event, face-verified).

    Event photos are PNG files written under ``image/uid{N}/event/`` (not JSONL
    records), and the standalone run keeps its own parallel orchestration in
    :func:`main`. This class is a thin uniform entry point for the future
    pipeline DAG: :meth:`produce` generates the event images for one persona's
    events (using ``ctx`` for the profile / init-state / nationality) and returns
    the per-event result dicts. Behavior of the underlying functions is unchanged.
    """

    stage_label = "Stage7.1"
    stage_num = "7.1"
    index_key = "uuid"
    produces = "event_photo"

    def __init__(self, image_base_dir=None, verify_face=True):
        self.image_base_dir = image_base_dir or PORTRAITS_DIR
        self.verify_face = verify_face

    def produce(self, record, ctx=None):
        ctx = ctx or {}
        uuid = record.get('uuid')
        events = record.get('Events', [])
        nationality = ctx.get('nationality', 'Chinese')
        person_dir = os.path.join(self.image_base_dir, f'uid{uuid}', DIR_NAME['person'])
        event_dir = os.path.join(self.image_base_dir, f'uid{uuid}', DIR_NAME['event'])
        os.makedirs(event_dir, exist_ok=True)
        results = []
        for event_idx, event in enumerate(events):
            results.append(generate_event_image_for_uuid(
                uuid, event_idx, event, person_dir, event_dir,
                profile_record=ctx.get('profile'),
                init_state_record=ctx.get('init_state'),
                nationality=nationality,
                verify_face=self.verify_face,
                face_threshold=get_face_threshold(nationality),
            ))
        return results


if __name__ == '__main__':
    main()
