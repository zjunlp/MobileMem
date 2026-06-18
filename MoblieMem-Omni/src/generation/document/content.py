"""Document LLM data layer: event selection + ``*_info`` generation.

The ``INFO_SCHEMAS`` / ``LLM_SELECT_PROMPTS`` tables plus the LLM-backed event
selection and batched ``*_info`` generation. Logs to the shared ``fix_app2``
logger (handlers are attached once in ``generator``).
"""
import json
import logging
import re
import time

from backends.llm import get_text_llm_model, llm_request

logger = logging.getLogger('fix_app2')


INFO_SCHEMAS = {
    "ticket": {
        "fields": "departure_station, arrival_station, departure_time(HH:MM), travel_date(YYYY-MM-DD), train_number, seat_type, seat_number, price(number), passenger_name",
        "example_cn": json.dumps({
            "departure_station": "北京南", "arrival_station": "上海虹桥",
            "departure_time": "08:30", "travel_date": "2025-04-15",
            "train_number": "G1", "seat_type": "二等座",
            "seat_number": "05车12A", "price": 553.0,
            "passenger_name": "张三"
        }, ensure_ascii=False),
        "example_en": json.dumps({
            "departure_station": "London Euston", "arrival_station": "Manchester",
            "departure_time": "09:15", "travel_date": "2025-04-15",
            "train_number": "AVT1234", "seat_type": "Standard",
            "seat_number": "Car 5 Seat 42A", "price": 85.50,
            "passenger_name": "John Smith"
        }, ensure_ascii=False),
        "hint_cn": "中国高铁/动车票（12306 平台）",
        "hint_en": "Train ticket (national rail booking)",
    },
    "money": {
        "fields": "amount(number), recipient_name, description, transfer_time(YYYY-MM-DD HH:MM), status, payment_method",
        "example_cn": json.dumps({
            "amount": 200.00, "recipient_name": "李四",
            "description": "AA晚餐", "transfer_time": "2025-04-10 19:30",
            "status": "已收款", "payment_method": "零钱"
        }, ensure_ascii=False),
        "example_en": json.dumps({
            "amount": 50.00, "recipient_name": "Jane Doe",
            "description": "Dinner split", "transfer_time": "2025-04-10 7:30 PM",
            "status": "Received", "payment_method": "Bank Account"
        }, ensure_ascii=False),
        "hint_cn": "微信转账记录",
        "hint_en": "Payment transfer record (Venmo/PayPal style)",
    },
    "friend": {
        "fields": "post_text, post_time, likes(list of names), comments(list of {name, text})",
        "example_cn": json.dumps({
            "post_text": "周末出出汗，神清气爽！和老友的羽毛球之约雷打不动。🏸",
            "post_time": "2小时前",
            "likes": ["张三", "李四", "王五"],
            "comments": [{"name": "张三", "text": "今天状态不错！"}]
        }, ensure_ascii=False),
        "example_en": json.dumps({
            "post_text": "Great weekend hiking trip! Nature never disappoints 🌄",
            "post_time": "2h ago",
            "likes": ["John", "Jane", "Bob"],
            "comments": [{"name": "John", "text": "Looks amazing!"}]
        }, ensure_ascii=False),
        "hint_cn": "微信朋友圈动态",
        "hint_en": "Social media post (Twitter/X style)",
    },
}

# Event selection (smart LLM filtering)

LLM_SELECT_PROMPTS = {
    "ticket": {
        "cn": "请从以下事件列表中，找出涉及城际出行（坐火车、高铁、动车）的事件。包括：出差、旅行、回家探亲、拜访远方亲友、赶赴外地活动等需要长途交通的场景。",
        "en": "From the event list below, identify events that involve intercity travel (train, rail). This includes: business trips, vacations, visiting family in another city, attending events in another location, etc.",
    },
    "money": {
        "cn": "请从以下事件列表中，找出涉及转账、付款、借还钱的事件。包括：AA制、红包、借款、还钱、代付、报销、打赏、捐款等金钱往来的场景。",
        "en": "From the event list below, identify events that involve money transfers or payments. This includes: splitting bills, sending money, lending/repaying, gifts, reimbursements, donations, etc.",
    },
    "friend": {
        "cn": "请从以下事件列表中，找出适合发朋友圈/社交动态的事件。包括：聚会、旅行、运动、节日庆祝、美食、生日、纪念日、新工作、毕业、购物、户外活动、宠物趣事等生活分享类场景。",
        "en": "From the event list below, identify events suitable for social media posts. This includes: gatherings, travel, sports, celebrations, food, birthdays, milestones, new job, graduation, shopping, outdoor activities, pet moments, etc.",
    },
}

def llm_select_events(events, app_type, persona_name, location, nationality="Chinese", n=2):
    """Use the LLM to select events suitable for this type from the 100 events."""
    is_cn = (nationality == "Chinese")

    # Events that already have this type of info are used directly
    already_have = [e for e in events if f"{app_type}_info" in e]
    if len(already_have) >= n:
        return already_have[:n]

    # Build a short event list
    event_list_str = "\n".join(
        f"[{json.dumps(e['event_id'], ensure_ascii=False)}] {e.get('event_name', '')}"
        for e in events
    )

    prompt_hint = LLM_SELECT_PROMPTS[app_type]["cn" if is_cn else "en"]
    if is_cn:
        prompt = f"""{prompt_hint}

人物：{persona_name}，所在地：{location}

事件列表：
{event_list_str}

仅返回 JSON 数组，包含适合的 event_id，按相关度从高到低排序。
event_id 可能是整数（如 5）或字符串（如 "4_1"），请原样返回。
如果没有合适事件，返回空数组 []。
不要有多余文字，仅返回 JSON 数组。"""
    else:
        prompt = f"""{prompt_hint}

Person: {persona_name}, Location: {location}

Event list:
{event_list_str}

Return ONLY a JSON array of suitable event_id values, sorted by relevance (most relevant first).
event_id may be integer (e.g. 5) or string (e.g. "4_1"), return them as-is.
If no events are suitable, return [].
No extra text, ONLY the JSON array."""

    llm_model = get_text_llm_model(is_cn)
    system_prompt = "你是事件分类专家。" if is_cn else "You are an event classification expert."

    for attempt in range(3):
        try:
            content, _ = llm_request(
                system_prompt=system_prompt,
                user_prompt=prompt,
                model=llm_model,
                temperature=0.3,
                max_tokens=500,
                extract_json=False,
            )
            match = re.search(r'\[.*?\]', content, re.DOTALL)
            if match:
                selected_ids = json.loads(match.group())
                # Verify the returned ids actually exist (event_id may be int or str)
                event_map = {e['event_id']: e for e in events}
                # Also build a str->event map as a fallback when the LLM returns a mismatched type
                event_map_str = {str(e['event_id']): e for e in events}
                valid = []
                for eid in selected_ids:
                    if eid in event_map:
                        valid.append(event_map[eid])
                    elif str(eid) in event_map_str:
                        valid.append(event_map_str[str(eid)])
                # Merge events that already have info
                result_ids = set()
                result = []
                for e in already_have:
                    if e['event_id'] not in result_ids:
                        result.append(e)
                        result_ids.add(e['event_id'])
                for e in valid:
                    if e['event_id'] not in result_ids:
                        result.append(e)
                        result_ids.add(e['event_id'])
                logger.info(f"  [LLM-select] {app_type}: selected {len(result)} events (ids: {[e['event_id'] for e in result[:n]]})")
                return result[:n]
            logger.warning(f"[LLM-select] No JSON array in response for {app_type}")
        except Exception as e:
            logger.warning(f"[LLM-select] Attempt {attempt+1}/3 failed: {e}")
            if attempt < 2:
                time.sleep(3 * (2 ** attempt))

    # Fallback: return events that already have info; if not enough, return the first n
    logger.warning(f"[LLM-select] Fallback for {app_type}")
    return (already_have + events)[:n]

def select_friend_events(events):
    """Select events that already have friend_info (generated by stage4 or other steps)."""
    return [e for e in events if e.get('friend_info')]

# LLM data generation

LLM_BATCH_SIZE = 5  # max events per LLM call, to avoid max_tokens truncation

def call_llm_generate_info(persona_name, career, location, personality,
                            events, app_type, nationality="Chinese"):
    """Call the LLM in batches to generate info, avoiding overly long single responses being truncated by max_tokens."""
    all_results = []
    for i in range(0, len(events), LLM_BATCH_SIZE):
        batch = events[i:i + LLM_BATCH_SIZE]
        batch_results = _call_llm_generate_info_single(
            persona_name, career, location, personality,
            batch, app_type, nationality
        )
        if batch_results:
            all_results.extend(batch_results)
    return all_results


def _call_llm_generate_info_single(persona_name, career, location, personality,
                                     events, app_type, nationality="Chinese"):
    schema = INFO_SCHEMAS[app_type]
    is_cn = (nationality == "Chinese")
    hint = schema["hint_cn"] if is_cn else schema["hint_en"]
    example = schema["example_cn"] if is_cn else schema["example_en"]

    events_desc = []
    for ev in events:
        eid_repr = json.dumps(ev['event_id'], ensure_ascii=False)
        events_desc.append(
            f"event_id={eid_repr}: \"{ev.get('event_name', '')}\" "
            f"({ev.get('event_start_time', '')}) - {ev.get('description', '')[:120]}"
        )

    if is_cn:
        prompt = f"""你是一个数据生成专家，需要为事件生成 {app_type}_info 数据。

人物设定：{persona_name}（{nationality}），职业：{career}，所在地：{location}，性格：{personality}

为以下每个事件生成真实的 {app_type}_info JSON 对象。
必要字段：{schema['fields']}
平台提示：{hint}

{app_type}_info 示例：
{example}

需要处理的事件：
{chr(10).join(events_desc)}

仅输出 JSON 数组，每个事件一个对象，保持相同顺序。
每个对象必须包含 "event_id"（整数）和 "{app_type}_info"（对象）。
输出格式示例：
[
  {{"event_id": 0, "{app_type}_info": {{...}}}},
  {{"event_id": 5, "{app_type}_info": {{...}}}}
]

重要：
- 内容必须与事件描述和人物背景相匹配。
- event_id 必须**原样输出**：整数就输出整数（如 `5`），字符串就输出带引号的字符串（如 `"35_1"`）。**绝对不能把带下划线的 id 写成无引号的裸字面量**（JSON 不允许 35_1，必须写成 "35_1"）。
- {app_type == 'ticket' and 'departure_station 和 arrival_station 必须是真实存在的地级市及以上的火车站/高铁站（如北京南、上海虹桥、深圳北、广州南、杭州东、南昌西等）。绝对禁止把非车站地名（体育馆/羽毛球馆/景区/酒店/学校/餐厅/公园/商场/写字楼/活动场馆等）作为出发或到达站，即使事件描述里提到了这些地点也不行。车次号格式正确（G/D/K/T/Z 开头）。乘客姓名用人物的名字。' or ''}
- {app_type == 'money' and '金额要合理（日常小额转账几十到几百元）。收款人应与事件参与者相关。' or ''}
- 使用中文内容。
- 仅返回 JSON 数组，不要有多余文字。"""
    else:
        prompt = f"""You are generating {app_type}_info data for events.

Persona: {persona_name} ({nationality}), Career: {career}, Location: {location}, Personality: {personality}

For each event below, generate a realistic {app_type}_info JSON object.
Required fields: {schema['fields']}
Platform hint: {hint}

Example {app_type}_info:
{example}

Events to process:
{chr(10).join(events_desc)}

Output ONLY a JSON array, one object per event, in the same order.
Each object must have "event_id" (int) and "{app_type}_info" (object).

IMPORTANT:
- Content must match the event description and persona background.
- event_id MUST be returned **exactly as given**: integers as integers (e.g. `5`), strings as quoted strings (e.g. `"35_1"`). Never output an unquoted bare literal like `35_1` — JSON does not allow it.
- Use appropriate content for {nationality} context.
- {"For tickets: price MUST be a plain JSON number (e.g. 85.50), NOT a string and NOT containing currency symbols like $/£/€. departure_station and arrival_station MUST be real major railway/train stations (e.g. London Euston, Manchester Piccadilly, New York Penn Station, Tokyo Station, Paris Gare du Nord). NEVER use non-station venues (gymnasiums, badminton courts, parks, hotels, restaurants, schools, malls, event venues, tourist spots) as station names, even if the event description mentions such places." if app_type == 'ticket' else ''}
- {"For money transfers: amount must be a plain JSON number, not a string." if app_type == 'money' else ''}
- Return ONLY the JSON array, no extra text."""

    llm_model = get_text_llm_model(is_cn)
    system_prompt = "你是一个专业的结构化JSON数据生成器。" if is_cn else "You generate structured JSON data."

    for attempt in range(3):
        try:
            content, _ = llm_request(
                system_prompt=system_prompt,
                user_prompt=prompt,
                model=llm_model,
                temperature=0.7,
                max_tokens=2000,
                extract_json=False,
            )
            match = re.search(r'\[.*\]', content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError as je:
                    logger.warning(f"[LLM] JSON decode error for {app_type} (batch of {len(events)}): {je}")
            else:
                logger.warning(f"[LLM] No JSON array for {app_type} (batch of {len(events)}, tail={content[-100:]!r})")
        except Exception as e:
            logger.warning(f"[LLM] Attempt {attempt+1}/3 failed: {e}")
            if attempt < 2:
                time.sleep(3 * (2 ** attempt))
    return []
