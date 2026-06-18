"""Scenery image generator (Memories / Scenery).

Generates AI scenery images for each persona across six categories (food,
landscape, indoor, weather_calendar, map_location, news_notification), with
prompts tied to the persona's nationality / location / preferences / events, and
writes ``image/uid{uuid}/scenery/*.png`` plus a ``manifest.json`` (resume-aware,
skipping already-generated images).

:class:`SceneryGenerator` is a thin uniform entry point over
:func:`generate_image_for_persona`; the standalone run uses :func:`main` with its
own manifest-based orchestration.
"""

import os
import json
import argparse
import time
import logging
from typing import Dict, List, Optional

import jsonlines

import config
from core import DIR_NAME
from backends.images import generate_person_images  # doubao image generation
from backends.llm import set_log_context
from infra.base_generator import Generator

LOG_DIR = config.LOG_DIR
os.makedirs(LOG_DIR, exist_ok=True)

# Logging

def setup_logging():
    summary_handler = logging.FileHandler(os.path.join(LOG_DIR, 'stage8_summary.log'), encoding='utf-8')
    summary_handler.setLevel(logging.INFO)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    for h in [summary_handler, console_handler]:
        h.setFormatter(fmt)
    logger = logging.getLogger('stage8')
    logger.setLevel(logging.INFO)
    for h in [summary_handler, console_handler]:
        logger.addHandler(h)
    return logger

logger = setup_logging()

# Constants

CATEGORIES = ['food', 'landscape', 'indoor', 'weather_calendar', 'map_location', 'news_notification']
IMAGES_PER_CATEGORY = 3  # Default: 3 per category per persona

# Prompt builders

def build_image_prompt(category: str, persona: Dict, event: Optional[Dict] = None) -> str:
    """Build an image generation prompt for a given category and persona."""
    bp = persona.get('Basic_Profile', {})
    init = persona.get('Init_State', {})
    nationality = bp.get('nationality', 'Chinese')
    location = init.get('location', 'China')
    prefs = init.get('preferences', {})

    is_chinese = (nationality == 'Chinese')
    lang_suffix = (
        '。图片中所有可见文字（包括界面标签、招牌、菜单、标题等）必须使用简体中文，禁止出现英文。'
        if is_chinese else
        ' All visible text (including UI labels, signs, menus, headlines, etc.) must be in English. Do NOT use any non-English text.'
    )
    ui_lang = '简体中文' if is_chinese else 'English'

    if event:
        if is_chinese:
            event_context = f"，与事件「{event.get('event_name', '')}」相关"
        else:
            event_context = f" related to the event: {event.get('event_name', '')}"
    else:
        event_context = ""

    if category == 'food':
        food_prefs = prefs.get('food', {})
        liked = food_prefs.get('like', ['本地美食'] if is_chinese else ['local cuisine'])
        if isinstance(liked, list):
            liked_str = ', '.join(liked[:3])
        else:
            liked_str = str(liked)
        if is_chinese:
            return (f"一张{liked_str}美食的真实照片，"
                    f"餐厅级摆盘，令人食欲大开，高品质美食摄影，"
                    f"自然光线，中式烹饪风格{event_context}，"
                    f"无文字，无水印，无字幕，无文字标注")
        else:
            return (f"A realistic photo of {liked_str} food dish, "
                    f"restaurant-style presentation, appetizing, high quality food photography, "
                    f"natural lighting, {nationality} cuisine style{event_context}, "
                    f"no text, no watermark, no captions, no words")

    elif category == 'landscape':
        if is_chinese:
            return (f"一张{location}旅游景点或自然风光的美丽风景照片，"
                    f"真实摄影风格，色彩鲜明，"
                    f"无人物，风景视角{event_context}，"
                    f"无文字，无水印，无字幕，无文字标注")
        else:
            return (f"A beautiful landscape photo of a tourist attraction or natural scenery "
                    f"in {location}, realistic photography style, vivid colors, "
                    f"no people, scenic view{event_context}, "
                    f"no text, no watermark, no captions, no words")

    elif category == 'indoor':
        career = init.get('career', '上班族' if is_chinese else 'office worker')
        if is_chinese:
            return (f"一张真实的室内场景照片，{career}的工作场所或家居环境，"
                    f"自然光线，日常生活场景，画面中无人物，"
                    f"干净真实{event_context}，"
                    f"无文字，无水印，无字幕，无文字标注")
        else:
            return (f"A realistic indoor scene photo, {career} workplace or home environment, "
                    f"natural lighting, everyday life setting, no people visible, "
                    f"clean and realistic{event_context}, "
                    f"no text, no watermark, no captions, no words")

    elif category == 'weather_calendar':
        if is_chinese:
            return (f"一张手机上天气预报应用或日历应用的真实截图，"
                    f"显示{location}的天气信息，简洁的界面设计，"
                    f"真实的手机应用界面，{ui_lang}界面{lang_suffix}")
        else:
            return (f"A realistic screenshot of a weather forecast app or calendar app on a smartphone, "
                    f"showing weather in {location}, clean UI design, "
                    f"realistic mobile app interface, {ui_lang} UI{lang_suffix}")

    elif category == 'map_location':
        if is_chinese:
            return (f"一张显示{location}位置的地图导航应用真实截图，"
                    f"街道地图视图，真实的手机地图界面，"
                    f"显示街道和地标，无个人信息，{ui_lang}界面{lang_suffix}")
        else:
            return (f"A realistic screenshot of a map navigation app showing a location in {location}, "
                    f"street map view, realistic mobile map interface, "
                    f"showing streets and landmarks, no personal information, {ui_lang} UI{lang_suffix}")

    elif category == 'news_notification':
        if is_chinese:
            return (f"一张手机上新闻通知或新闻卡片的真实截图，"
                    f"显示与{location}日常生活相关的新闻标题，"
                    f"简洁的通知设计，{ui_lang}界面{lang_suffix}")
        else:
            return (f"A realistic screenshot of a news notification or news card on a smartphone, "
                    f"showing a news headline relevant to daily life in {location}, "
                    f"clean notification design, {ui_lang} UI{lang_suffix}")

    if is_chinese:
        return f"一张与{location}日常生活相关的真实照片"
    return f"A realistic photo related to daily life in {location}"

def generate_image_for_persona(
    persona: Dict, category: str, idx: int, output_dir: str, force: bool = False
) -> Optional[str]:
    """Generate a single scenery image for a persona."""
    uuid = persona.get('uuid')
    filename = f"{category}_{idx}.png"
    uuid_scenery_dir = os.path.join(output_dir, f"uid{uuid}", DIR_NAME["scenery"])
    os.makedirs(uuid_scenery_dir, exist_ok=True)
    output_path = os.path.join(uuid_scenery_dir, filename)

    # Skip if already exists
    if os.path.exists(output_path) and not force:
        logger.debug(f"[uuid={uuid}] {filename} already exists, skipping")
        return output_path

    # Pick a relevant event for context
    events = persona.get('Events', [])
    event = events[idx % len(events)] if events else None

    prompt = build_image_prompt(category, persona, event)
    logger.debug(f"[uuid={uuid}] Generating {filename}: {prompt[:80]}...")

    try:
        # Use generate_person_images from utils.py (same API)
        temp_dir = os.path.join(uuid_scenery_dir, '_temp')
        os.makedirs(temp_dir, exist_ok=True)
        filepaths = generate_person_images(prompt, output_dir=temp_dir, nationality=persona.get('nationality', 'Chinese'))

        if filepaths:
            # Rename to our naming convention
            import shutil
            shutil.move(filepaths[0], output_path)
            logger.info(f"[uuid={uuid}] Generated {filename}")
            return output_path
        else:
            logger.warning(f"[uuid={uuid}] No image returned for {filename}")
            return None

    except Exception as e:
        logger.error(f"[uuid={uuid}] Failed to generate {filename}: {e}")
        return None


class SceneryGenerator(Generator):
    """Generate per-persona scenery images across the six categories.

    Scenery emits image files + a ``manifest.json`` rather than a JSONL record, and
    the standalone run keeps its own manifest-based resume in :func:`main`, so this
    class is a thin uniform entry point over :func:`generate_image_for_persona`.
    ``produce`` generates one persona's scenery and returns the per-uuid manifest
    fragment (``{category: [filename, ...]}``).
    """

    stage_label = "Stage8"
    stage_num = "8"
    index_key = "uuid"
    produces = "scenery"

    def __init__(self, output_dir: str, categories: Optional[List[str]] = None,
                 images_per_category: int = IMAGES_PER_CATEGORY) -> None:
        self.output_dir = output_dir
        self.categories = list(categories) if categories else list(CATEGORIES)
        self.images_per_category = images_per_category

    def produce(self, record: Dict, ctx=None) -> Dict[str, List[str]]:
        generated: Dict[str, List[str]] = {}
        for category in self.categories:
            files: List[str] = []
            for idx in range(self.images_per_category):
                result = generate_image_for_persona(record, category, idx, self.output_dir)
                if result:
                    files.append(os.path.basename(result))
            generated[category] = files
        return generated


# Main

def main():
    parser = argparse.ArgumentParser(description='Stage 8: Generate scenery images')
    parser.add_argument('--input-file', type=str,
                        default=os.path.join(config.OUTPUT_DIR, 'data', 'annual_events.jsonl'),
                        help='Input stage4 JSONL file')
    parser.add_argument('--output-dir', type=str,
                        default=os.path.join(config.OUTPUT_DIR, 'image'),
                        help='Output directory for scenery images')
    parser.add_argument('--images-per-category', type=int, default=3,
                        help='Number of images per category per persona (default: 3)')
    parser.add_argument('--categories', type=str, nargs='+', default=CATEGORIES,
                        choices=CATEGORIES,
                        help='Categories to generate (default: all)')
    parser.add_argument('--uuid-filter', type=int, nargs='+', default=None,
                        help='Only process these UUIDs')
    parser.add_argument('--force', action='store_true',
                        help='Ignore existing manifest/images and regenerate from scratch')
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    manifest_path = os.path.join(args.output_dir, 'manifest.json')

    logger.info(f"{'=' * 70}")
    logger.info("STAGE 8: Scenery Image Generation")
    logger.info(f"Output: {args.output_dir}")
    logger.info(f"Categories: {args.categories}")
    logger.info(f"Images per category: {args.images_per_category}")
    logger.info(f"{'=' * 70}")

    # Load input
    personas = []
    if os.path.exists(args.input_file):
        with jsonlines.open(args.input_file, 'r') as reader:
            personas = list(reader)

    if not personas:
        logger.error(f"No data in {args.input_file}")
        return

    # Load existing manifest
    manifest = {}
    if os.path.exists(manifest_path) and not args.force:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)

    total_generated = 0
    total_errors = 0

    for persona in personas:
        uuid = persona.get('uuid')
        if args.uuid_filter and uuid not in args.uuid_filter:
            continue

        set_log_context(uuid=uuid, stage="stage8_scenery")
        bp = persona.get('Basic_Profile', {})
        name = bp.get('name', 'Unknown')
        logger.info(f"[uuid={uuid}] Processing {name}")

        if str(uuid) not in manifest:
            manifest[str(uuid)] = {}

        for category in args.categories:
            if category not in manifest[str(uuid)]:
                manifest[str(uuid)][category] = []

            existing_count = len(manifest[str(uuid)][category])
            if existing_count >= args.images_per_category:
                logger.info(f"[uuid={uuid}] {category}: already have {existing_count} images, skipping")
                continue

            for idx in range(existing_count, args.images_per_category):
                result = generate_image_for_persona(persona, category, idx, args.output_dir, force=args.force)
                if result:
                    filename = os.path.basename(result)
                    manifest[str(uuid)][category].append(filename)
                    total_generated += 1
                    # Save manifest after each image
                    with open(manifest_path, 'w', encoding='utf-8') as f:
                        json.dump(manifest, f, ensure_ascii=False, indent=2)
                else:
                    total_errors += 1

                # Small delay to avoid rate limiting
                time.sleep(1)

    # Final manifest save
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    logger.info(f"{'=' * 70}")
    logger.info("STAGE 8 COMPLETE")
    logger.info(f"  Generated: {total_generated} images")
    logger.info(f"  Errors: {total_errors}")
    logger.info(f"  Manifest: {manifest_path}")
    logger.info(f"{'=' * 70}")

if __name__ == '__main__':
    main()
