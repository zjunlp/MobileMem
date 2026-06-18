"""App-trace *_info LLM generation (schemas + prompt + JSON parse)."""
import json
import logging
import random
import re
import time
from datetime import datetime, timedelta

from backends.llm import get_text_llm_model, llm_request

logger = logging.getLogger('fix_app_screenshots')


INFO_SCHEMAS = {
    "book": {
        "fields_cn": "title, author, progress, rating(1-5), highlight, reading_time, platform",
        "fields_en": "title, author, progress, rating(1-5), highlight, reading_time, platform",
        "example_cn": json.dumps({
            "title": "活着", "author": "余华", "progress": "已读完",
            "rating": 5, "highlight": "人是为了活着本身而活着，而不是为了活着之外的任何事物而活着",
            "reading_time": "6小时", "platform": "微信读书"
        }, ensure_ascii=False),
        "example_en": json.dumps({
            "title": "Atomic Habits", "author": "James Clear", "progress": "Finished",
            "rating": 5, "highlight": "You do not rise to the level of your goals. You fall to the level of your systems.",
            "reading_time": "6 hours", "platform": "Kindle"
        }, ensure_ascii=False),
        "hint_cn": "中文书籍（微信读书平台）",
        "hint_en": "English book (Kindle/Apple Books)",
    },
    "music": {
        "fields_cn": "song, artist, album, duration(M:SS), current_time(M:SS), playlist, lyric_line, comment, comment_user",
        "fields_en": "song, artist, album, duration(M:SS), current_time(M:SS), playlist, lyric_line, comment, comment_user",
        "example_cn": json.dumps({
            "song": "晴天", "artist": "周杰伦", "album": "叶惠美",
            "duration": "4:29", "current_time": "2:15", "playlist": "我喜欢的音乐",
            "lyric_line": "从前从前有个人爱你很久", "comment": "每次听都会想起那个夏天",
            "comment_user": "晴天少年"
        }, ensure_ascii=False),
        "example_en": json.dumps({
            "song": "Shape of You", "artist": "Ed Sheeran", "album": "Divide",
            "duration": "3:53", "current_time": "1:20", "playlist": "My Favorites",
            "lyric_line": "I'm in love with the shape of you", "comment": "This song always reminds me of that summer",
            "comment_user": "MusicLover"
        }, ensure_ascii=False),
        "hint_cn": "中文歌曲（网易云音乐平台）",
        "hint_en": "English/international song (Spotify)",
    },
    "video": {
        "fields_cn": "title, uploader, duration(M:SS or H:MM:SS), view_count, action(点赞/收藏/投币), danmaku, danmaku_count, fans_count, like_count, fav_count, tags(array), description, hot_comments(array)",
        "fields_en": "title, uploader, duration(M:SS or H:MM:SS), view_count, action(like/save/share), danmaku, danmaku_count, fans_count, like_count, fav_count, tags(array), description, hot_comments(array)",
        "example_cn": json.dumps({
            "title": "AI时代程序员如何自我提升", "uploader": "技术胖",
            "duration": "15:30", "view_count": "23.5万", "action": "点赞",
            "danmaku": "太强了", "danmaku_count": 1568,
            "fans_count": "45.2万", "like_count": 8765, "fav_count": 3421,
            "tags": ["科技", "编程", "AI"],
            "description": "分享程序员在AI时代的学习路线和技能提升方法",
            "hot_comments": [
                {"name": "路人甲", "text": "太棒了！", "time": "昨天", "likes": 328},
                {"name": "小白", "text": "催更！", "time": "3天前", "likes": 156}
            ]
        }, ensure_ascii=False),
        "example_en": json.dumps({
            "title": "How Programmers Can Level Up in the AI Era", "uploader": "TechGuru",
            "duration": "15:30", "view_count": "235K", "action": "like",
            "danmaku": "Amazing!", "danmaku_count": 1568,
            "fans_count": "452K", "like_count": 8765, "fav_count": 3421,
            "tags": ["Tech", "Programming", "AI"],
            "description": "A learning roadmap and skill-building tips for programmers in the AI era",
            "hot_comments": [
                {"name": "John", "text": "Great video!", "time": "Yesterday", "likes": 328},
                {"name": "Mike", "text": "Please upload more!", "time": "3 days ago", "likes": 156}
            ]
        }, ensure_ascii=False),
        "hint_cn": "中文视频（B站平台）",
        "hint_en": "English video (YouTube)",
    },
    "shopping": {
        "fields_cn": "item_name, shop_name, price(number), order_time(YYYY-MM-DD HH:MM:SS), order_status(已完成/待发货/运输中), rating(1-5), review_text",
        "fields_en": "item_name, shop_name, price(number), order_time(YYYY-MM-DD HH:MM:SS), order_status(Delivered/Pending Shipment/In Transit), rating(1-5), review_text",
        "example_cn": json.dumps({
            "item_name": "无线蓝牙耳机降噪版", "shop_name": "数码旗舰店",
            "price": 259.00, "order_time": "2025-03-10 14:30:00",
            "order_status": "已完成", "rating": 5, "review_text": "音质很好，降噪效果不错"
        }, ensure_ascii=False),
        "example_en": json.dumps({
            "item_name": "Wireless Noise-Cancelling Earbuds", "shop_name": "SoundTech Store",
            "price": 259.00, "order_time": "2025-03-10 14:30:00",
            "order_status": "Delivered", "rating": 5, "review_text": "Great sound quality and the noise cancellation works really well"
        }, ensure_ascii=False),
        "hint_cn": "中文商品（淘宝平台）",
        "hint_en": "English product (Amazon)",
    },
}

def _compute_publish_date(event_start_time_str):
    """Generate a video publish date 2 days to 2 months before the event time."""
    try:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                event_dt = datetime.strptime(event_start_time_str, fmt)
                days_before = random.randint(2, 60)
                return (event_dt - timedelta(days=days_before)).strftime("%Y-%m-%d")
            except ValueError:
                continue
    except Exception:
        pass
    return "2025-06-01"

def _call_llm_generate_info(persona_record, events, app_type, nationality="Chinese"):
    """Call the LLM to generate *_info fields for each event."""
    all_results = []
    for i, ev in enumerate(events):
        logger.info(f"  LLM event {i+1}/{len(events)} (event_id={ev.get('event_id')})...")
        result = _call_llm_generate_info_single(persona_record, [ev], app_type, nationality)
        all_results.extend(result)
    return all_results

def _call_llm_generate_info_single(persona_record, events, app_type, nationality="Chinese"):
    """Call the LLM to generate a *_info field for one event."""
    bp = persona_record.get('Basic_Profile', {})
    init_state = persona_record.get('Init_State', {})
    name = bp.get('name', '用户')
    career = init_state.get('career', '')
    location = init_state.get('location', '')
    personality = bp.get('personality_traits', '')

    schema = INFO_SCHEMAS[app_type]
    is_cn = (nationality == "Chinese")
    hint = schema["hint_cn"] if is_cn else schema["hint_en"]
    fields = schema["fields_cn"] if is_cn else schema["fields_en"]
    example = schema["example_cn"] if is_cn else schema["example_en"]

    events_desc = []
    for ev in events:
        events_desc.append(
            f"event_id={ev['event_id']}: \"{ev.get('event_name','')}\" "
            f"({ev.get('event_start_time','')}) - {ev.get('description','')[:100]}"
        )

    if is_cn:
        prompt = f"""你是一个数据生成专家，需要为事件生成 {app_type}_info 数据。

人物设定：{name}（{nationality}），职业：{career}，所在地：{location}，性格：{personality}

为以下每个事件生成真实的 {app_type}_info JSON 对象。
必要字段：{fields}
平台提示：{hint}

{app_type}_info 示例：
{example}

需要处理的事件：
{chr(10).join(events_desc)}

仅输出 JSON 数组，每个事件一个对象，保持相同顺序。
每个对象必须包含 "event_id" 和 "{app_type}_info"（对象）。
event_id 的值必须与输入中的 event_id 完全一致（可能是整数如 0, 5，也可能是字符串如 "76_2"）。
输出格式示例：
[
  {{"event_id": 0, "{app_type}_info": {{...}}}},
  {{"event_id": "76_2", "{app_type}_info": {{...}}}}
]

重要：
- 内容必须与事件描述和人物背景相匹配。
- 使用中文内容。
- 仅返回 JSON 数组，不要有多余文字。"""
    else:
        prompt = f"""You are generating {app_type}_info data for events.

Persona: {name} ({nationality}), Career: {career}, Location: {location}, Personality: {personality}

For each event below, generate a realistic {app_type}_info JSON object.
Required fields: {fields}
Platform hint: {hint}

Example {app_type}_info:
{example}

Events to process:
{chr(10).join(events_desc)}

Output ONLY a JSON array, one object per event, in the same order.
Each object must have "event_id" and "{app_type}_info" (object).
event_id must match the input exactly (could be int like 0, 5 or string like "76_2").
Example output format:
[
  {{"event_id": 0, "{app_type}_info": {{...}}}},
  {{"event_id": "76_2", "{app_type}_info": {{...}}}}
]

IMPORTANT:
- Content must match the event description and persona background.
- Use English/international content.
- Return ONLY the JSON array, no extra text."""
    
    # Add extra constraints specifically for video items.
    if app_type == "video":
        if is_cn:
            prompt += f"""
- 关键：人物'{name}'是观看视频的观众，不是视频创作者/上传者。
- 根据事件内容，生成'{name}'会真实搜索并在B站(Bilibili)上观看的视频。
- 'uploader'必须是相关领域的内容创作者（不能是'{name}'）。上传者的专业领域需与事件主题匹配：
  例如：科技 → 科技UP主；美食 → 美食博主；旅行 → 旅行博主；健身 → 健身教练等。
- 使用真实的UP主名称，如：技术胖、科技小明、数码老王、美食达人小李、旅行博主阿强等。
- 上传者名称绝对不能与'{name}'相同或相似。
- 视频标题、描述、标签都必须与所描述的具体事件直接相关。
- 输出中不要包含 publish_date，它会自动计算。
"""
        else:
            prompt += f"""
- CRITICAL: The persona '{name}' is the VIEWER watching this video, NOT the video creator/uploader.
- Based on the event content, generate a video that '{name}' would realistically search for and watch on YouTube.
- The 'uploader' must be a relevant content creator (NOT '{name}'). Match the uploader expertise to the event topic:
  e.g. technology → tech UP主; food → food bloggers; travel → travel vloggers; fitness → fitness coaches, etc.
- English content: use realistic creator names like TechGuru, CodeMaster, FoodieExpert, TravelVlogger etc.
- The uploader name must NEVER be the same as or similar to '{name}'.
- Video title, description, tags must all be directly related to the specific event described.
- Do NOT include publish_date in your output — it will be computed automatically.
"""
    
    is_cn = (nationality == "Chinese")
    llm_model = get_text_llm_model(is_cn)
    system_prompt = "你是一个专业的结构化JSON数据生成器，用于应用截图渲染。" if is_cn else "You generate structured JSON data for app screenshot rendering."

    for attempt in range(5):
        try:
            content, cost_info = llm_request(
                system_prompt=system_prompt,
                user_prompt=prompt,
                model=llm_model,
                temperature=0.7,
                max_tokens=1000,
                extract_json=False,
            )
            # Extract JSON array
            match = re.search(r'\[.*\]', content, re.DOTALL)
            if match:
                raw_json = match.group()
                # Fix unquoted sub-event IDs like 76_2 -> "76_2"
                raw_json = re.sub(r'"event_id"\s*:\s*(\d+_\d+)', r'"event_id": "\1"', raw_json)
                result = json.loads(raw_json)
                # For videos, compute publish_date from the event time without relying on the LLM.
                if app_type == "video":
                    for item in result:
                        eid = item.get("event_id")
                        ev_match = next((e for e in events if e.get("event_id") == eid), None)
                        if ev_match and "video_info" in item:
                            item["video_info"]["publish_date"] = _compute_publish_date(
                                ev_match.get("event_start_time", ""))
                return result
            logger.warning(f"[LLM] No JSON array found in response for {app_type}")
        except Exception as e:
            wait = min(3 * (2 ** attempt), 60)  # 3s, 6s, 12s, 24s, 48s
            logger.warning(f"[LLM] Attempt {attempt+1}/5 failed for {app_type}: {e}")
            if attempt < 4:
                logger.info(f"[LLM] Waiting {wait}s before retry...")
                time.sleep(wait)
    return []
