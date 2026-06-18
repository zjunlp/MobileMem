"""Annual-events name strategy (graph / legacy) + incremental prompt building."""
import hashlib
import json
import logging
import random
import re
from datetime import datetime
from typing import Dict, List, Optional, Set

from backends.llm import calculate_cumulative_cost, llm_request

from .parse import extract_events_from_response, validate_and_normalize_events

logger = logging.getLogger("generation.annual_events")


CHINESE_SURNAMES = [
    "陈", "林", "黄", "周", "吴", "徐", "孙", "胡", "朱", "高", "郭", "何",
    "罗", "郑", "梁", "谢", "宋", "唐", "许", "韩", "冯", "曹", "彭", "曾",
    "程", "潘", "于", "蒋", "蔡", "余", "杜", "叶", "魏", "苏", "丁", "沈"
]
CHINESE_GIVEN_FIRST = {
    'male': ["景", "承", "泽", "昊", "远", "铭", "柏", "川", "奕", "辰", "睿", "航", "谦", "庭", "曜", "峻"],
    'female': ["雨", "欣", "婉", "宁", "可", "心", "妍", "悦", "嘉", "晴", "若", "雯", "伊", "瑶", "诗", "岚"],
    'neutral': ["安", "言", "逸", "希", "凡", "沐", "依", "乐", "知", "然", "清", "禾", "念", "微", "予", "舒"]
}
CHINESE_GIVEN_SECOND = {
    'male': ["安", "川", "明", "成", "舟", "阳", "恒", "钧", "朗", "峰", "诚", "言", "拓", "然", "维", "森"],
    'female': ["宁", "然", "雅", "琪", "柔", "涵", "怡", "彤", "璇", "琪", "童", "菲", "琳", "清", "禾", "月"],
    'neutral': ["宁", "然", "安", "禾", "之", "一", "可", "青", "朗", "言", "舟", "川", "清", "月", "辰", "微"]
}
ENGLISH_FIRST_NAMES = {
    'male': ["Owen", "Ethan", "Julian", "Miles", "Adrian", "Caleb", "Nathan", "Lucas"],
    'female': ["Chloe", "Maya", "Elena", "Nora", "Audrey", "Claire", "Naomi", "Hazel"],
    'neutral': ["Alex", "Jordan", "Taylor", "Avery", "Casey", "Morgan", "Riley", "Quinn"]
}
ENGLISH_LAST_NAMES = ["Turner", "Reed", "Bennett", "Foster", "Hayes", "Carter", "Brooks", "Griffin"]
GENERIC_CN_NAMES = {
    "张三", "李四", "王五", "赵六", "小王", "小李", "小张", "小刘", "小陈",
    "骑手小王", "骑手小李", "骑手小张", "某某", "某人", "路人甲", "路人乙",
    "朋友A", "同事A", "同学A", "老师A", "客户A", "用户A", "群友A"
}
GENERIC_EN_NAMES = {
    "John Doe", "Jane Doe", "Friend A", "Colleague A", "User A", "Tom", "Jerry"
}
ORG_HINTS_CN = [
    "公司", "中心", "医院", "学校", "大学", "学院", "物业", "培训", "门店", "旗舰店",
    "工作室", "餐厅", "饭店", "酒楼", "商店", "超市", "诊所", "银行", "平台", "快修",
    "美容院", "健身房", "俱乐部", "酒店", "公寓", "房东", "物业费", "学费", "保费"
]
ORG_HINTS_EN = [
    "company", "center", "hospital", "school", "university", "store", "studio", "bank",
    "platform", "shop", "club", "hotel", "clinic", "service", "tuition", "insurance"
]
CHINESE_ORG_PREFIXES = ["青禾", "远山", "星澜", "知行", "启明", "云程", "安禾", "晨光", "沐川", "合悦"]
CHINESE_ORG_SUFFIXES = [
    "教育咨询中心", "社区服务中心", "健康管理中心", "母婴生活馆", "摄影工作室", "汽车养护店",
    "数码快修店", "宠物护理中心", "花艺工作室", "运动康复中心", "少儿成长营", "生活服务站"
]
ENGLISH_ORG_PREFIXES = ["North", "Blue", "Cedar", "Harbor", "Maple", "Bright", "River", "Corner"]
ENGLISH_ORG_SUFFIXES = ["Learning Center", "Care Studio", "Community Hub", "Repair Shop", "Health Clinic", "Service Desk"]


# Per-record LLM parse / validate (folded from the old stage4_lib)


def _stable_seed(*parts: object) -> int:
    raw = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()
    return int(digest[:16], 16)

def _make_rng(*parts: object) -> random.Random:
    return random.Random(_stable_seed(*parts))

def _dedupe_names(names: List[str]) -> List[str]:
    result = []
    seen = set()
    for name in names:
        cleaned = re.sub(r'\s+', '', str(name or ''))
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(str(name))
    return result

def _looks_like_org(name: str, is_chinese: bool) -> bool:
    if not name:
        return False
    hints = ORG_HINTS_CN if is_chinese else ORG_HINTS_EN
    lowered = str(name).lower()
    return any(hint.lower() in lowered for hint in hints)

def _is_simple_placeholder_name(name: str, is_chinese: bool) -> bool:
    cleaned = re.sub(r'\s+', '', str(name or ''))
    if not cleaned:
        return True
    if is_chinese:
        if cleaned in GENERIC_CN_NAMES:
            return True
        if re.fullmatch(r'(小|老)[王李张刘陈杨赵黄周吴徐孙朱胡高郭何罗郑梁谢宋唐许韩冯曹彭曾程潘于蒋蔡余杜叶魏苏丁沈]', cleaned):
            return True
        if re.fullmatch(r'(骑手|配送员)?小[王李张刘陈杨赵黄周吴徐孙朱胡高郭何罗郑梁谢宋唐许韩冯曹彭曾程潘于蒋蔡余杜叶魏苏丁沈]', cleaned):
            return True
        return False
    return cleaned in GENERIC_EN_NAMES

def _infer_gender_from_relationship(name: str, relationship_info: Dict) -> str:
    relationship_text = json.dumps(relationship_info or {}, ensure_ascii=False)
    if any(token in relationship_text for token in ['女性', '女儿', '母亲', '未婚妻', '妻子', '阿姨', '学姐', '闺蜜', '姐姐', '妈妈',
                                                     'female', 'daughter', 'mother', 'fiancée', 'wife', 'aunt', 'sister', 'girlfriend']):
        return 'female'
    if any(token in relationship_text for token in ['男性', '儿子', '父亲', '丈夫', '叔叔', '哥哥', '爸爸',
                                                     'male', 'son', 'father', 'husband', 'uncle', 'brother', 'boyfriend']):
        return 'male'
    if any(token in str(name) for token in ['姐', '姨', '妈']):
        return 'female'
    if any(token in str(name) for token in ['哥', '叔', '爸', '师傅', '主任', '教练']):
        return 'male'
    return 'neutral'

def _build_person_name_pool(persona_uuid: int, tag: str, count: int,
                            forbidden: Set[str], is_chinese: bool,
                            gender: str = 'neutral') -> List[str]:
    rng = _make_rng(persona_uuid, tag, gender)
    candidates = []
    local_forbidden = set(forbidden)

    if is_chinese:
        first_pool = list(CHINESE_GIVEN_FIRST.get(gender, CHINESE_GIVEN_FIRST['neutral']))
        second_pool = list(CHINESE_GIVEN_SECOND.get(gender, CHINESE_GIVEN_SECOND['neutral']))
        if gender == 'neutral':
            first_pool += CHINESE_GIVEN_FIRST['male'][:6] + CHINESE_GIVEN_FIRST['female'][:6]
            second_pool += CHINESE_GIVEN_SECOND['male'][:6] + CHINESE_GIVEN_SECOND['female'][:6]

        for _ in range(count * 12):
            surname = rng.choice(CHINESE_SURNAMES)
            given = rng.choice(first_pool)
            if rng.random() < 0.85:
                given += rng.choice(second_pool)
            candidate = surname + given
            if candidate not in local_forbidden:
                local_forbidden.add(candidate)
                candidates.append(candidate)
                if len(candidates) >= count:
                    break
    else:
        first_pool = list(ENGLISH_FIRST_NAMES.get(gender, ENGLISH_FIRST_NAMES['neutral']))
        if gender == 'neutral':
            first_pool += ENGLISH_FIRST_NAMES['male'][:4] + ENGLISH_FIRST_NAMES['female'][:4]
        for _ in range(count * 12):
            candidate = f"{rng.choice(first_pool)} {rng.choice(ENGLISH_LAST_NAMES)}"
            if candidate not in local_forbidden:
                local_forbidden.add(candidate)
                candidates.append(candidate)
                if len(candidates) >= count:
                    break

    forbidden.update(candidates)
    return candidates

def _build_org_name_pool(persona_uuid: int, count: int, is_chinese: bool) -> List[str]:
    rng = _make_rng(persona_uuid, 'event-org-pool', 'cn' if is_chinese else 'en')
    candidates = []
    seen = set()

    prefixes = CHINESE_ORG_PREFIXES if is_chinese else ENGLISH_ORG_PREFIXES
    suffixes = CHINESE_ORG_SUFFIXES if is_chinese else ENGLISH_ORG_SUFFIXES
    for _ in range(count * 8):
        candidate = f"{rng.choice(prefixes)}{rng.choice(suffixes)}"
        if candidate not in seen:
            seen.add(candidate)
            candidates.append(candidate)
            if len(candidates) >= count:
                break
    return candidates

def _extract_event_side_names(existing_events: List[Dict], is_chinese: bool) -> List[str]:
    names = []
    for event in existing_events:
        names.extend(event.get('participants', []) or [])

        friend_info = event.get('friend_info') or {}
        names.extend(friend_info.get('likes', []) or [])
        for comment in friend_info.get('comments', []) or []:
            if isinstance(comment, dict):
                names.append(comment.get('name', ''))

        wechat_info = event.get('wechat_info') or {}
        chat_partner = wechat_info.get('chat_partner')
        if chat_partner and not _looks_like_org(chat_partner, is_chinese):
            names.append(chat_partner)

        food_info = event.get('food_info') or {}
        rider_name = food_info.get('rider_name')
        if rider_name and not _looks_like_org(rider_name, is_chinese):
            names.append(rider_name)

        money_info = event.get('money_info') or {}
        recipient_name = money_info.get('recipient_name')
        if recipient_name and not _looks_like_org(recipient_name, is_chinese):
            names.append(recipient_name)

    return _dedupe_names(names)

def _names_by_appear(graph_people: List[Dict], tag: str) -> List[str]:
    """Filter names from the Social_Graph people list whose can_appear_in contains `tag`."""
    return [p['name'] for p in graph_people
            if tag in (p.get('can_appear_in') or [])]

def _build_event_name_strategy_from_graph(persona_record: Dict,
                                          existing_events: List[Dict],
                                          is_chinese: bool) -> Dict:
    """Build the name strategy based on Social_Graph (the new Stage 3.9 path)."""
    basic_profile = persona_record.get('Basic_Profile', {})
    init_state = persona_record.get('Init_State', {})
    social_relationships = init_state.get('social_relationships', {}) or {}
    social_graph = persona_record.get('Social_Graph', {})

    relationship_names = _dedupe_names(list(social_relationships.keys()))
    existing_event_names = _extract_event_side_names(existing_events, is_chinese)

    relationship_by_gender = {'male': [], 'female': [], 'neutral': []}
    for name, info in social_relationships.items():
        relationship_by_gender[_infer_gender_from_relationship(name, info)].append(name)

    # Collect people from each graph category
    all_graph_people = []  # type: List[Dict]
    for category in ['inner_circle', 'extended_contacts', 'service_people',
                     'professional_network', 'online_contacts', 'weak_ties']:
        all_graph_people.extend(social_graph.get(category, []))

    # Filter name pools by scenario
    rider_pool = _names_by_appear(social_graph.get('service_people', []), 'food_rider')
    if not rider_pool:
        rider_pool = [p['name'] for p in social_graph.get('service_people', [])]

    participant_candidates = _names_by_appear(all_graph_people, 'participants')  # noqa: F841
    wechat_candidates = _names_by_appear(all_graph_people, 'wechat')
    liker_candidates = _names_by_appear(all_graph_people, 'friend_likes')
    commenter_candidates = _names_by_appear(all_graph_people, 'friend_comments')
    recipient_candidates = _names_by_appear(all_graph_people, 'money_recipient')

    # Organization name pool
    org_pool = [o['name'] for o in social_graph.get('organizations', [])]

    # General personal name pool (all graph people)
    all_personal_names = _dedupe_names(
        [p['name'] for p in all_graph_people] + existing_event_names)

    # Personal recipient pool = those tagged money_recipient + relationship_names
    personal_recipient_pool = _dedupe_names(relationship_names + recipient_candidates)

    # commenter pool = likers + commenter candidates
    commenter_pool = _dedupe_names(liker_candidates + commenter_candidates)
    if not commenter_pool:
        commenter_pool = all_personal_names

    # chat pool = wechat candidates
    chat_partner_pool = _dedupe_names(wechat_candidates)
    if not chat_partner_pool:
        chat_partner_pool = all_personal_names

    # General contacts pool (for display in the prompt)
    generated_contacts = _dedupe_names(
        [p['name'] for p in social_graph.get('extended_contacts', [])] +
        [p['name'] for p in social_graph.get('professional_network', [])] +
        [p['name'] for p in social_graph.get('online_contacts', [])] +
        [p['name'] for p in social_graph.get('weak_ties', [])]
    )

    return {
        'main_name': basic_profile.get('name', ''),
        'relationship_names': relationship_names,
        'relationship_by_gender': relationship_by_gender,
        'existing_event_names': existing_event_names,
        'generated_contacts': generated_contacts,
        'rider_pool': rider_pool,
        'personal_recipient_pool': personal_recipient_pool,
        'organization_recipient_pool': org_pool,
        'commenter_pool': commenter_pool,
        'chat_partner_pool': chat_partner_pool,
        'all_personal_names': all_personal_names,
        'forbidden_placeholders': sorted(GENERIC_CN_NAMES if is_chinese else GENERIC_EN_NAMES),
        # Extra: keep graph people details for use by _format_name_guidance
        '_graph_people': all_graph_people,
        '_has_graph': True,
    }

def _build_event_name_strategy_legacy(persona_record: Dict,
                                      existing_events: List[Dict],
                                      is_chinese: bool) -> Dict:
    """Legacy version: build names from hardcoded word pools (fallback when there is no Social_Graph)."""
    persona_uuid = persona_record.get('uuid', 0)
    basic_profile = persona_record.get('Basic_Profile', {})
    init_state = persona_record.get('Init_State', {})
    social_relationships = init_state.get('social_relationships', {}) or {}

    relationship_names = _dedupe_names(list(social_relationships.keys()))
    existing_event_names = _extract_event_side_names(existing_events, is_chinese)
    forbidden = set(_dedupe_names([basic_profile.get('name', '')] + relationship_names + existing_event_names))

    generated_contacts = _build_person_name_pool(
        persona_uuid, 'event-contact', 14, forbidden, is_chinese, gender='neutral')
    rider_pool = _build_person_name_pool(
        persona_uuid, 'event-rider', 8, forbidden, is_chinese, gender='male')
    personal_recipients = _build_person_name_pool(
        persona_uuid, 'event-recipient', 10, forbidden, is_chinese, gender='neutral')
    organization_recipients = _build_org_name_pool(persona_uuid, 8, is_chinese)

    relationship_by_gender = {'male': [], 'female': [], 'neutral': []}
    for name, info in social_relationships.items():
        relationship_by_gender[_infer_gender_from_relationship(name, info)].append(name)

    all_personal_names = _dedupe_names(
        relationship_names + existing_event_names + generated_contacts + personal_recipients)

    return {
        'main_name': basic_profile.get('name', ''),
        'relationship_names': relationship_names,
        'relationship_by_gender': relationship_by_gender,
        'existing_event_names': existing_event_names,
        'generated_contacts': generated_contacts,
        'rider_pool': rider_pool,
        'personal_recipient_pool': _dedupe_names(relationship_names + personal_recipients + generated_contacts[:6]),
        'organization_recipient_pool': organization_recipients,
        'commenter_pool': all_personal_names,
        'chat_partner_pool': all_personal_names,
        'all_personal_names': all_personal_names,
        'forbidden_placeholders': sorted(GENERIC_CN_NAMES if is_chinese else GENERIC_EN_NAMES),
        '_has_graph': False,
    }

def _build_event_name_strategy(persona_record: Dict, existing_events: List[Dict], is_chinese: bool) -> Dict:
    """Unified entry: use the graph when a Social_Graph exists, otherwise fall back to the legacy word pools."""
    social_graph = persona_record.get('Social_Graph')
    if social_graph and any(social_graph.get(c) for c in
                            ['extended_contacts', 'service_people', 'professional_network',
                             'online_contacts', 'weak_ties']):
        return _build_event_name_strategy_from_graph(persona_record, existing_events, is_chinese)
    return _build_event_name_strategy_legacy(persona_record, existing_events, is_chinese)

def _format_graph_people_brief(people: List[Dict], limit: int = 20) -> str:
    """Format graph people into a list with short bios for the LLM to reference."""
    lines = []
    for p in people[:limit]:
        name = p.get('name', '')
        rel = p.get('relationship_to_protagonist', '')
        brief = p.get('brief', '')
        desc = f"{name}（{rel}）" if rel else name
        if brief:
            desc += f" — {brief}"
        lines.append(f"  · {desc}")
    return '\n'.join(lines) or '（无）'

def _format_name_guidance(name_strategy: Dict, is_chinese: bool) -> str:
    has_graph = name_strategy.get('_has_graph', False)

    if is_chinese:
        rel_names = '、'.join(name_strategy['relationship_names'][:18]) or '（无）'
        existing_names = '、'.join(name_strategy['existing_event_names'][:12]) or '（暂无）'
        rider_names = '、'.join(name_strategy['rider_pool'][:8]) or '（无）'
        contact_names = '、'.join(name_strategy['generated_contacts'][:14]) or '（无）'
        recipient_names = '、'.join(name_strategy['personal_recipient_pool'][:12]) or '（无）'
        org_names = '、'.join(name_strategy['organization_recipient_pool'][:10]) or '（无）'
        forbidden = '、'.join(name_strategy['forbidden_placeholders'][:12])

        # When a graph exists, append people bios to help the LLM pick people
        people_brief = ''
        if has_graph:
            graph_people = name_strategy.get('_graph_people', [])
            if graph_people:
                people_brief = f"""\n\n【社交图谱人物简介（选择人物时参考）】
{_format_graph_people_brief(graph_people, 30)}"""

        return f"""

【事件侧名字生成规则 — 严格遵守】
- 主角姓名：{name_strategy['main_name']}。不要把主角姓名误用给其他角色。
- social_relationships 中已有姓名（优先复用）：{rel_names}
- 前面已出现过的事件侧姓名（优先保持连续性）：{existing_names}
- 新增外部联系人/评论人/聊天对象候选池：{contact_names}
- food_info.rider_name 必须从以下骑手池中选：{rider_names}
- 个人收款人候选池：{recipient_names}
- 机构/商户收款人候选池：{org_names}
- 严禁使用模板化名字：{forbidden}
- participants 必须优先从 social_relationships 中选。
- friend_info.likes、friend_info.comments.name、wechat_info.chat_partner 优先从 social_relationships、历史已用姓名或候选池中选，不要自行发明新的人名。
- money_info.recipient_name 如果是个人收款，优先使用个人收款人候选池；如果是机构/商户收款，优先使用机构/商户收款人候选池。
- 同一主角全年事件里，新增人物姓名要尽量复用，不要每条事件都创建一个全新的临时名字。
- description 正文中提及任何人名时，也必须使用上述候选池中的名字，不要自创新名。
{people_brief}"""

    rel_names = ', '.join(name_strategy['relationship_names'][:18]) or '(none)'
    existing_names = ', '.join(name_strategy['existing_event_names'][:12]) or '(none yet)'
    contact_names = ', '.join(name_strategy['generated_contacts'][:14]) or '(none)'
    recipient_names = ', '.join(name_strategy['personal_recipient_pool'][:12]) or '(none)'
    org_names = ', '.join(name_strategy['organization_recipient_pool'][:10]) or '(none)'
    forbidden = ', '.join(name_strategy['forbidden_placeholders'][:12])

    people_brief = ''
    if has_graph:
        graph_people = name_strategy.get('_graph_people', [])
        if graph_people:
            people_brief = f"""\n\nSocial Graph People Reference (use these when picking names for events):
{_format_graph_people_brief(graph_people, 30)}"""

    return f"""

Event-side naming rules — STRICTLY follow:
- Main persona name: {name_strategy['main_name']}. Do not reuse it for other characters.
- Prefer names already present in social_relationships: {rel_names}
- Prefer reusing event-side names already used earlier this year: {existing_names}
- New temporary contacts/commenters/chat partners must come from this pool: {contact_names}
- food_info.rider_name must come from this rider pool: {', '.join(name_strategy['rider_pool'][:8])}
- Personal recipient pool: {recipient_names}
- Organization or merchant recipient pool: {org_names}
- Never use placeholder names such as: {forbidden}
- participants should come from social_relationships whenever possible.
- Keep event-side names consistent across the same persona's whole year.
- Names mentioned in description text must also come from the pools above — do not invent new names.
{people_brief}"""

def _pick_name_from_pool(pool: List[str], names_in_event: Set[str]) -> str:
    for candidate in pool:
        cleaned = re.sub(r'\s+', '', str(candidate or ''))
        if cleaned and cleaned not in names_in_event:
            names_in_event.add(cleaned)
            return candidate
    return pool[0] if pool else ''

def _apply_event_name_strategy(events: List[Dict], name_strategy: Dict, is_chinese: bool) -> List[Dict]:
    for event in events:
        names_in_event = set()

        participants = event.get('participants', []) or []
        normalized_participants = []
        participant_pool = name_strategy['relationship_names'] or name_strategy['all_personal_names']
        for participant in participants:
            candidate = participant
            if _is_simple_placeholder_name(candidate, is_chinese):
                replacement = _pick_name_from_pool(participant_pool, names_in_event)
                candidate = replacement or candidate
            names_in_event.add(re.sub(r'\s+', '', str(candidate or '')))
            normalized_participants.append(candidate)
        event['participants'] = normalized_participants[:2]

        food_info = event.get('food_info') or {}
        rider_name = food_info.get('rider_name', '')
        if rider_name and _is_simple_placeholder_name(rider_name, is_chinese):
            replacement = _pick_name_from_pool(name_strategy['rider_pool'], names_in_event)
            if replacement:
                food_info['rider_name'] = replacement

        money_info = event.get('money_info') or {}
        recipient_name = money_info.get('recipient_name', '')
        if recipient_name and _is_simple_placeholder_name(recipient_name, is_chinese):
            description = money_info.get('description', '')
            if _looks_like_org(description, is_chinese):
                replacement = _pick_name_from_pool(name_strategy['organization_recipient_pool'], names_in_event)
            else:
                replacement = _pick_name_from_pool(name_strategy['personal_recipient_pool'], names_in_event)
            if replacement:
                money_info['recipient_name'] = replacement

        friend_info = event.get('friend_info') or {}
        likes = friend_info.get('likes', []) or []
        normalized_likes = []
        like_scope = set()
        for like_name in likes:
            candidate = like_name
            if _is_simple_placeholder_name(candidate, is_chinese) or candidate not in name_strategy['all_personal_names']:
                replacement = _pick_name_from_pool(name_strategy['commenter_pool'], like_scope)
                candidate = replacement or candidate
            normalized_likes.append(candidate)
        if normalized_likes:
            friend_info['likes'] = _dedupe_names(normalized_likes)

        comments = friend_info.get('comments', []) or []
        for comment in comments:
            if not isinstance(comment, dict):
                continue
            comment_name = comment.get('name', '')
            if comment_name and (_is_simple_placeholder_name(comment_name, is_chinese) or comment_name not in name_strategy['all_personal_names']):
                replacement = _pick_name_from_pool(name_strategy['commenter_pool'], like_scope)
                if replacement:
                    comment['name'] = replacement

        wechat_info = event.get('wechat_info') or {}
        chat_partner = wechat_info.get('chat_partner', '')
        if chat_partner and _is_simple_placeholder_name(chat_partner, is_chinese):
            replacement = _pick_name_from_pool(name_strategy['chat_partner_pool'], names_in_event)
            if replacement:
                wechat_info['chat_partner'] = replacement

    return events

# Prompt & LLM helpers (stateless, thread-safe)

def _build_incremental_prompt(
    persona_record: Dict,
    existing_events: List[Dict],
    events_to_generate: int,
    is_chinese: bool = False,
    name_strategy: Optional[Dict] = None
) -> str:
    """Build the user prompt for incrementally generating events."""
    basic_profile = persona_record.get('Basic_Profile', {})
    init_state = persona_record.get('Init_State', {})
    important_dates = persona_record.get('Important_Dates', {})

    existing_summary = "\n".join([
        f"  - event_id={e.get('event_id', '?')}: "
        f"{e.get('event_name', 'Unknown')} "
        f"({e.get('event_start_time', '?')} ~ {e.get('event_end_time', '?')}, "
        f"{e.get('duration_type', '?')}, {e.get('importance', '?')}, "
        f"additional_info={e.get('additional_info', [])})"
        for e in existing_events
    ]) if existing_events else "(none)"

    start_event_id = len(existing_events)

    # Persona data section (shared by Chinese/English; the data itself is already in the right language)
    persona_data = f"""- Name: {basic_profile.get('name', 'Unknown')}
- Gender: {basic_profile.get('gender', 'Unknown')}
- Birth Date: {basic_profile.get('birth_date', 'Unknown')}
- Nationality: {basic_profile.get('nationality', 'Unknown')}
- Personality Traits: {basic_profile.get('personality_traits', 'Unknown')}
- Life Experiences: {basic_profile.get('life_experiences', 'Unknown')}

Initial State (as of 2025-01-01):
- Description: {init_state.get('description', 'Unknown')}
- Education: {init_state.get('education', 'Unknown')}
- Location: {init_state.get('location', 'Unknown')}
- Career: {init_state.get('career', 'Unknown')}
- Preferences: {json.dumps(init_state.get('preferences', {}), ensure_ascii=False, indent=2)}
- Social Relationships: {json.dumps(init_state.get('social_relationships', {}), ensure_ascii=False, indent=2)}
- Health: {init_state.get('health', 'Unknown')}
- Emotion: {init_state.get('emotion', 'Unknown')}
- Finance: {init_state.get('finance', 'Unknown')}

Important Dates:
- Festivals: {json.dumps(important_dates.get('festivals', []), ensure_ascii=False, indent=2)}
- Memorial Dates: {json.dumps(important_dates.get('memorial_dates', []), ensure_ascii=False, indent=2)}
- Event Milestones: {json.dumps(important_dates.get('event_milestones', []), ensure_ascii=False, indent=2)}"""

    name_guidance = _format_name_guidance(name_strategy or {}, is_chinese) if name_strategy else ""

    if is_chinese:
        return f"""请为以下人物生成2025年的额外年度事件。

人物背景：
{persona_data}
{name_guidance}

=== 已生成的事件（不要重复） ===
{existing_summary}
=== 已有事件结束 ===

请生成恰好 {events_to_generate} 个与上述 {len(existing_events)} 个已有事件不同的新事件。
- event_id 从 {start_event_id} 开始（即 {start_event_id}, {start_event_id + 1}, ...）。
- 覆盖与已有事件不同的时间段和主题。
- 每个事件都必须包含对应的 info 字段（ticket_info/food_info/money_info/friend_info/wechat_info）。

【强制要求 - duration_type 分布】本批 {events_to_generate} 个事件中，必须严格包含：
- {max(1, events_to_generate // 15)} 个 long-term 事件（持续数月，如健康管理计划、长期职业发展、健身塑形、长期学习课程等）
- {max(1, events_to_generate * 3 // 15)} 个 mid-term 事件（持续数天到数周，如度假旅行、出差、短期培训、装修、搬家等）
- {events_to_generate - max(1, events_to_generate // 15) - max(1, events_to_generate * 3 // 15)} 个 short-term 事件（持续数小时，如会议、就餐、外出等）
请务必遵守以上数量要求，不要全部生成 short-term 事件！

【重要】所有文本字段（event_name、description、各info中的文本）必须使用纯中文。"""
    else:
        return f"""Please generate ADDITIONAL annual events for this persona in 2025.

Persona Background:
{persona_data}
{name_guidance}

=== ALREADY GENERATED EVENTS (DO NOT repeat or duplicate these) ===
{existing_summary}
=== END OF EXISTING EVENTS ===

Please generate exactly {events_to_generate} NEW events that are DIFFERENT from the {len(existing_events)} existing events listed above.
- Start event_id from {start_event_id} (i.e., {start_event_id}, {start_event_id + 1}, ...).
- Cover different time periods and topics than the existing events.
- Each event should represent a plausible situation where the persona might seek guidance from a chatbot.

MANDATORY DURATION TYPE DISTRIBUTION FOR THIS BATCH:
- Exactly {max(1, events_to_generate // 15)} long-term events (lasting months: health plans, career goals, fitness journeys, education programs)
- Exactly {max(1, events_to_generate * 3 // 15)} mid-term events (lasting days/weeks: vacations, business trips, short courses, moving)
- Exactly {events_to_generate - max(1, events_to_generate // 15) - max(1, events_to_generate * 3 // 15)} short-term events (lasting hours: meetings, meals, outings)
You MUST strictly follow this distribution. Do NOT generate all short-term events!

IMPORTANT EVENT TYPE DISTRIBUTION REQUIREMENTS:
- Ensure at least 25% of events involve travel or shopping scenarios
- Travel scenarios include: train tickets, flight tickets, hotel bookings, attraction tickets, car rentals, travel insurance, etc.
- Shopping scenarios include: online shopping (Taobao, JD, Amazon, etc.), offline shopping, large purchases, refund disputes, etc.
- ticket-type events should account for 15-20% of total events, covering various transportation tickets
- money-type events should account for 10-15% of total events, covering various payment and transfer scenarios

IMPORTANT: For EVERY event, you MUST include ONE of the following info fields based on the additional_info type:
- If additional_info contains 'ticket': include complete ticket_info with all required fields
- If additional_info contains 'food': include complete food_info with all required fields  
- If additional_info contains 'money': include complete money_info with all required fields
- If additional_info contains 'friend': include complete friend_info with all required fields
- If additional_info contains 'wechat': include complete wechat_info with all required fields

Do NOT generate events that are missing their corresponding info fields!
ALL output text fields must be in pure English. No Chinese characters in event_name or description."""

def _call_llm_for_events(system_prompt: str, user_content: str, persona_uuid, model: str = None) -> List[Dict]:
    """Make one LLM call, then extract and validate the event list. Thread-safe (no shared state)."""
    response, cost_info = llm_request(
        system_prompt,
        user_content,
        model=model,
        return_parsed_json=True,
        extract_json=True,
        json_markers=[]
    )

    cost_info = calculate_cumulative_cost(None, cost_info)
    if cost_info and 'cumulative' in cost_info:
        cum = cost_info['cumulative']
        print(f"    [Cost] Input: {cum.get('input_tokens', 'N/A')}, "
              f"Output: {cum.get('output_tokens', 'N/A')}, "
              f"Cost: ${cum.get('total_cost_usd', 'N/A')}")

    new_events = extract_events_from_response(response)
    if not new_events:
        return []

    new_events = validate_and_normalize_events(new_events, persona_uuid)
    return new_events

def _merge_and_sort_events(existing_events: List[Dict], new_events: List[Dict],
                           total_desired: int) -> List[Dict]:
    """Merge, sort by time, renumber, and truncate."""
    merged = list(existing_events) + list(new_events)

    try:
        merged.sort(key=lambda x: datetime.strptime(
            x['event_start_time'], '%Y-%m-%d %H:%M:%S'))
    except Exception as e:
        print(f"    [WARNING] Could not sort events by time: {e}")

    for idx, evt in enumerate(merged):
        evt['event_id'] = idx

    if len(merged) > total_desired:
        merged = merged[:total_desired]
        for idx, evt in enumerate(merged):
            evt['event_id'] = idx

    return merged

# Parallel Runner
