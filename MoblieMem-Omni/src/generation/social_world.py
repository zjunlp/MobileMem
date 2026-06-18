"""Social-world generator (Life / SocialWorld).

:class:`SocialWorldGenerator` plans each persona's 2025 social graph — converting
stage-2 ``social_relationships`` into an ``inner_circle`` and asking the LLM (in
category batches) for extended_contacts / service_people / professional_network
/ online_contacts / weak_ties / organizations — with a global cross-persona name
registry so no name is reused. It attaches ``Social_Graph`` to the persona record.

``generate_social_graph`` keeps its ``max_workers`` parameter for signature
compatibility (the body runs serially with global name de-dup).
"""

import os
import re
import json
import traceback
import threading
import jsonlines
from typing import Dict, List, Optional, Set, Tuple

from backends.llm import llm_request, calculate_cumulative_cost, get_text_llm_model, set_log_context
from infra.base_generator import Generator

# Default number of parallel workers
DEFAULT_WORKERS = 3
# Maximum number of LLM retries
MAX_RETRIES = 3

# Person categories and their ratios of the total target
CATEGORY_RATIOS = {
    'extended_contacts': 0.25,
    'service_people': 0.15,
    'professional_network': 0.20,
    'online_contacts': 0.15,
    'weak_ties': 0.10,
}
# Organization count ratio (relative to max_events)
ORG_RATIO = 0.08
MIN_ORGS = 5
# Maximum number of people per single LLM call (split into batches if exceeded)
MAX_PEOPLE_PER_CALL = 30

PERSON_CATEGORIES = list(CATEGORY_RATIOS.keys())
ALL_CATEGORIES = PERSON_CATEGORIES + ['organizations']

# Batching strategy: split categories across two rounds of calls
BATCH_1_CATEGORIES = ['extended_contacts', 'professional_network', 'service_people']
BATCH_2_CATEGORIES = ['online_contacts', 'weak_ties']

def _compute_graph_targets(max_events: int, existing_inner_count: int) -> Dict[str, int]:
    """Compute the target count for each category based on max_events."""
    # Total number of new people (excluding inner_circle)
    total_new = max(15, int(max_events * 0.6) - existing_inner_count)
    # Ensure a minimum value
    total_new = max(total_new, 15)

    targets = {}
    allocated = 0
    sorted_cats = sorted(CATEGORY_RATIOS.items(), key=lambda x: x[1], reverse=True)
    for i, (cat, ratio) in enumerate(sorted_cats):
        if i == len(sorted_cats) - 1:
            # The last category takes the remainder
            targets[cat] = max(2, total_new - allocated)
        else:
            count = max(2, int(total_new * ratio))
            targets[cat] = count
            allocated += count

    targets['organizations'] = max(MIN_ORGS, int(max_events * ORG_RATIO))
    return targets

# Pure relationship words: cannot be used as person names
_RELATION_WORDS = {
    '母亲', '父亲', '儿子', '女儿', '妻子', '丈夫', '哥哥', '姐姐', '弟弟', '妹妹',
    '爷爷', '奶奶', '外公', '外婆', '叔叔', '阿姨', '舅舅', '姑姑', '堂兄', '表弟',
    '未婚妻', '未婚夫', '爸爸', '妈妈', '父母', '兄弟', '姐妹', '孙子', '孙女',
    'father', 'mother', 'son', 'daughter', 'wife', 'husband',
    'brother', 'sister', 'grandfather', 'grandmother',
}

_SURNAME_POOL = [
    '宋', '徐', '韩', '冯', '曹', '魏', '程', '苏', '叶', '卢',
    '贺', '龚', '潘', '顾', '史', '方', '邓', '武', '钱', '唐',
]
_GIVEN_POOL = [
    '昊', '晨', '睿', '泽', '皓', '帆', '峰', '洋', '凯', '博',
    '婷', '颖', '琳', '燕', '霞', '洁', '娜', '雯', '莹', '璐',
]
_EN_FIRST_POOL = [
    'James', 'Robert', 'Michael', 'David', 'Richard', 'Joseph', 'Thomas', 'William',
    'Sarah', 'Emily', 'Jessica', 'Hannah', 'Rachel', 'Lauren', 'Megan', 'Olivia',
]
_EN_LAST_POOL = [
    'Smith', 'Johnson', 'Brown', 'Davis', 'Wilson', 'Anderson', 'Taylor', 'Thomas',
    'Harris', 'Clark', 'Lewis', 'Walker', 'Hall', 'Young', 'King', 'Wright',
]

# Relationship words that share the protagonist's surname (immediate blood relatives)
_SAME_SURNAME_RELATIONS = {
    '父亲', '爸爸', '母亲', '妈妈', '哥哥', '姐姐', '弟弟', '妹妹',
    '爷爷', '奶奶', '儿子', '女儿', '兄弟', '姐妹', '孙子', '孙女',
    'father', 'mother', 'brother', 'sister', 'son', 'daughter',
    'grandfather', 'grandmother',
}

def _make_unique_name(existing: set, surname: str = '', is_chinese: bool = True) -> str:
    """Generate a name not in `existing`, optionally with a given surname. Supports Chinese and English."""
    import itertools
    if is_chinese:
        # If a surname is specified, prefer combinations with that surname
        if surname:
            for g in _GIVEN_POOL:
                candidate = surname + g
                if candidate not in existing:
                    return candidate
        # Otherwise iterate over the name pool
        for s, g in itertools.product(_SURNAME_POOL, _GIVEN_POOL):
            candidate = s + g
            if candidate not in existing:
                return candidate
        base = _SURNAME_POOL[0] + _GIVEN_POOL[0]
        i = 2
        while f"{base}{i}" in existing:
            i += 1
        return f"{base}{i}"
    else:
        # English name
        if surname:
            for f in _EN_FIRST_POOL:
                candidate = f"{f} {surname}"
                if candidate not in existing:
                    return candidate
        for f, last in itertools.product(_EN_FIRST_POOL, _EN_LAST_POOL):
            candidate = f"{f} {last}"
            if candidate not in existing:
                return candidate
        base = f"{_EN_FIRST_POOL[0]} {_EN_LAST_POOL[0]}"
        i = 2
        while f"{base} {i}" in existing:
            i += 1
        return f"{base} {i}"

def _build_inner_circle(social_relationships: Dict,
                        protagonist_name: str = '',
                        global_occupied: set = None,
                        is_chinese: bool = True) -> List[Dict]:
    """Convert Stage 2's social_relationships into a list of inner_circle nodes."""
    inner = []
    # Merge the globally occupied names as the de-duplication baseline
    used_names: set = set(global_occupied) if global_occupied is not None else set()
    if protagonist_name:
        used_names.add(protagonist_name)
    # Protagonist's surname (first character)
    protagonist_surname = protagonist_name[0] if protagonist_name else ''

    for key, info in social_relationships.items():
        rel_type = info.get('relationship_type', '朋友')
        description = info.get('description', '')

        # If the key is a relationship word rather than a real name, auto-generate a valid name
        if key.strip() in _RELATION_WORDS:
            real_name = info.get('name', '').strip()
            if real_name and real_name not in _RELATION_WORDS and real_name not in used_names:
                name = real_name
            else:
                # Decide whether it must share the protagonist's surname
                need_same_surname = key.strip() in _SAME_SURNAME_RELATIONS
                surname = protagonist_surname if need_same_surname else ''
                name = _make_unique_name(used_names, surname=surname, is_chinese=is_chinese)
                print(f"[inner_circle] relationship word '{key}' has no real name, auto-generated: {name}")
        else:
            name = key
        used_names.add(name)

        # Infer gender
        gender = 'neutral'
        text = json.dumps(info, ensure_ascii=False)
        if any(w in text for w in ['女性', '女儿', '母亲', '妻子', '未婚妻', '阿姨', '闺蜜', '姐姐', '妈妈',
                                    'female', 'daughter', 'mother', 'wife', 'fiancée', 'aunt', 'sister', 'girlfriend']):
            gender = 'female'
        elif any(w in text for w in ['男性', '儿子', '父亲', '丈夫', '叔叔', '哥哥', '爸爸',
                                      'male', 'son', 'father', 'husband', 'uncle', 'brother', 'boyfriend']):
            gender = 'male'
        elif any(w in str(name) for w in ['姐', '姨', '妈', '嫂']):
            gender = 'female'
        elif any(w in str(name) for w in ['哥', '叔', '爸', '师傅']):
            gender = 'male'

        # Infer can_appear_in
        can_appear = ['participants', 'friend_likes']
        if rel_type in ['朋友', '同事', '同学', '室友', '闺蜜', '兄弟',
                        'friend', 'colleague', 'classmate', 'roommate']:
            can_appear = ['participants', 'wechat', 'friend_likes', 'friend_comments']
        elif rel_type in ['父亲', '母亲', '父母', '妻子', '丈夫', '未婚妻', '未婚夫',
                          '儿子', '女儿', '妹妹', '哥哥', '姐姐', '弟弟',
                          'father', 'mother', 'wife', 'husband', 'son', 'daughter',
                          'sister', 'brother', 'fiancée', 'fiancé']:
            can_appear = ['participants', 'wechat', 'friend_likes', 'friend_comments', 'money_recipient']
        elif rel_type in ['领导', '上司', 'boss', 'manager', '站长']:
            can_appear = ['participants', 'wechat', 'friend_likes']

        inner.append({
            'name': name,
            'gender': gender,
            'age_range': '',
            'category': 'inner_circle',
            'relationship_to_protagonist': rel_type,
            'brief': description,
            'can_appear_in': can_appear,
        })
    return inner

def _build_user_prompt(persona_record: Dict, targets: Dict[str, int],
                       is_chinese: bool,
                       already_generated: List[Dict] = None,
                       global_occupied: set = None,
                       global_lock: threading.Lock = None) -> str:
    """Build the user prompt sent to the LLM.

    Args:
        targets: target counts per category for this round (only the categories to generate in this batch).
        already_generated: people generated in previous batches (used to avoid duplicate names).
        global_occupied: the global set of names already taken across all personas.
        global_lock: the lock protecting global_occupied.
    """
    basic = persona_record.get('Basic_Profile', {})
    init = persona_record.get('Init_State', {})
    social = init.get('social_relationships', {}) or {}

    # Existing inner_circle names
    inner_names = list(social.keys())
    inner_summary = '\n'.join(
        f"  - {name}（{info.get('relationship_type', '?')}）"
        for name, info in social.items()
    ) if social else '（无）'

    # All existing names (must not be reused)
    forbidden = [basic.get('name', '')] + inner_names
    if already_generated:
        forbidden += [p.get('name', '') for p in already_generated if p.get('name')]
    # Add names already taken globally across personas
    if global_occupied is not None:
        with (global_lock or threading.Lock()):
            global_names = list(global_occupied)
        forbidden += [n for n in global_names if n not in set(forbidden)]

    # Build category descriptions
    cat_labels_cn = {
        'extended_contacts': 'extended_contacts（扩展社交）',
        'service_people': 'service_people（服务人员，全部男性）',
        'professional_network': 'professional_network（职业圈扩展）',
        'online_contacts': 'online_contacts（网络社交）',
        'weak_ties': 'weak_ties（弱关系联系人）',
        'organizations': 'organizations（机构/商户）',
    }
    cat_labels_en = {
        'extended_contacts': 'extended_contacts',
        'service_people': 'service_people (all male)',
        'professional_network': 'professional_network',
        'online_contacts': 'online_contacts',
        'weak_ties': 'weak_ties',
        'organizations': 'organizations',
    }

    if is_chinese:
        target_lines = []
        for cat, count in targets.items():
            label = cat_labels_cn.get(cat, cat)
            unit = '个' if cat == 'organizations' else '人'
            target_lines.append(f"- {label}：{count} {unit}")
        target_text = '\n'.join(target_lines)

        already_text = ''
        if already_generated:
            names = '、'.join(p.get('name', '') for p in already_generated[:30] if p.get('name'))
            already_text = f"\n\n【前面批次已生成的人物（不可重复使用这些名字）】\n{names}"

        return f"""请为以下主角规划2025年的社交图谱。

【主角信息】
- 姓名：{basic.get('name', '未知')}
- 性别：{basic.get('gender', '未知')}
- 出生日期：{basic.get('birth_date', '未知')}
- 国籍：{basic.get('nationality', '未知')}
- 性格：{basic.get('personality_traits', '未知')}
- 人生经历：{basic.get('life_experiences', '未知')}
- 教育：{init.get('education', '未知')}
- 居住地：{init.get('location', '未知')}
- 职业：{init.get('career', '未知')}
- 健康：{init.get('health', '未知')}
- 财务：{init.get('finance', '未知')}

【已有核心社交关系（inner_circle），不可修改】
{inner_summary}

【禁止使用的名字（已占用）】
{'、'.join(forbidden)}{already_text}

【本轮需要生成的类别和数量】
{target_text}

请严格按照上述数量生成。所有人名必须是中文全名，不得重复，不得使用模板化名字。
只输出本轮要求的类别，不要输出其他类别。"""
    else:
        target_lines = []
        for cat, count in targets.items():
            label = cat_labels_en.get(cat, cat)
            target_lines.append(f"- {label}: {count}")
        target_text = '\n'.join(target_lines)

        already_text = ''
        if already_generated:
            names = ', '.join(p.get('name', '') for p in already_generated[:30] if p.get('name'))
            already_text = f"\n\n【Names already generated in previous batches — DO NOT reuse】\n{names}"

        return f"""Please plan a social graph for 2025 for this protagonist.

【Protagonist Info】
- Name: {basic.get('name', 'Unknown')}
- Gender: {basic.get('gender', 'Unknown')}
- Birth Date: {basic.get('birth_date', 'Unknown')}
- Nationality: {basic.get('nationality', 'Unknown')}
- Personality: {basic.get('personality_traits', 'Unknown')}
- Life Experiences: {basic.get('life_experiences', 'Unknown')}
- Education: {init.get('education', 'Unknown')}
- Location: {init.get('location', 'Unknown')}
- Career: {init.get('career', 'Unknown')}
- Health: {init.get('health', 'Unknown')}
- Finance: {init.get('finance', 'Unknown')}

【Existing Core Relationships (inner_circle) — DO NOT modify】
{inner_summary}

【Forbidden Names (already taken)】
{', '.join(forbidden)}{already_text}

【Categories and counts to generate THIS round】
{target_text}

Please generate exactly the specified number for each category. All names must be unique.
Only output the categories requested above, do not include other categories."""

def _validate_social_graph(graph: Dict, inner_circle: List[Dict],
                           protagonist_name: str,
                           global_occupied: set = None,
                           global_lock: threading.Lock = None) -> Dict:
    """Validate and normalize the social graph returned by the LLM."""
    if 'Social_Graph' in graph:
        graph = graph['Social_Graph']

    # Collect occupied names (within this persona + globally across personas)
    occupied = {protagonist_name}
    for person in inner_circle:
        occupied.add(person.get('name', ''))
    if global_occupied is not None:
        with (global_lock or threading.Lock()):
            occupied |= set(global_occupied)

    validated = {}
    for category in PERSON_CATEGORIES:
        items = graph.get(category, [])
        if not isinstance(items, list):
            items = []
        clean = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get('name', '').strip()
            if not name or name in occupied:
                continue
            # Ensure required fields exist
            item.setdefault('gender', 'neutral')
            item.setdefault('age_range', '')
            item.setdefault('relationship_to_protagonist', '')
            item.setdefault('brief', '')
            item.setdefault('can_appear_in', ['friend_likes'])
            item['category'] = category
            occupied.add(name)
            clean.append(item)
        validated[category] = clean

    # Organizations
    orgs = graph.get('organizations', [])
    if not isinstance(orgs, list):
        orgs = []
    clean_orgs = []
    org_names = set()
    for org in orgs:
        if not isinstance(org, dict):
            continue
        name = org.get('name', '').strip()
        if not name or name in org_names:
            continue
        org.setdefault('type', '')
        org.setdefault('relationship_to_protagonist', '')
        org_names.add(name)
        clean_orgs.append(org)
    validated['organizations'] = clean_orgs

    # Register the people added this round into the global set
    if global_occupied is not None:
        new_names = occupied - {protagonist_name} - {p.get('name', '') for p in inner_circle}
        with (global_lock or threading.Lock()):
            global_occupied.update(new_names)

    return validated

def _call_llm_for_graph(system_prompt: str, user_content: str,
                        model: str, inner_circle: List[Dict],
                        protagonist_name: str,
                        global_occupied: set = None,
                        global_lock: threading.Lock = None) -> Dict:
    """Single LLM call to obtain (part of) the social graph."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
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

            if isinstance(response, dict):
                return _validate_social_graph(
                    response, inner_circle, protagonist_name,
                    global_occupied, global_lock)
        except Exception as e:
            print(f"    [Attempt {attempt}/{MAX_RETRIES}] LLM call failed: {e}")
    return {}

def _plan_batches(targets: Dict[str, int]) -> List[Dict[str, int]]:
    """Split the targets into multiple batches according to MAX_PEOPLE_PER_CALL.

    Strategy:
      - Batch 1: extended_contacts + professional_network + service_people
      - Batch 2: online_contacts + weak_ties + organizations
    If the number of people in a batch still exceeds the limit, the categories in that batch are split further.
    """
    batch_specs = [
        {c: targets[c] for c in BATCH_1_CATEGORIES if c in targets},
        {c: targets[c] for c in BATCH_2_CATEGORIES if c in targets},
    ]
    # organizations go into the second batch
    if 'organizations' in targets:
        batch_specs[1]['organizations'] = targets['organizations']

    # Check whether each batch's people count exceeds the limit; split further if so
    final_batches = []
    for spec in batch_specs:
        if not spec:
            continue
        people_count = sum(v for k, v in spec.items() if k != 'organizations')
        if people_count <= MAX_PEOPLE_PER_CALL:
            final_batches.append(spec)
        else:
            # Split each category into its own batch
            for cat, count in spec.items():
                final_batches.append({cat: count})

    return final_batches

def _process_single_persona(persona_record: Dict, system_prompt: str,
                            system_prompt_cn: str, max_events: int,
                            global_occupied: set = None,
                            global_lock: threading.Lock = None) -> Dict:
    """Generate the social graph for a single persona in batches."""
    basic = persona_record.get('Basic_Profile', {})
    init = persona_record.get('Init_State', {})
    social = init.get('social_relationships', {}) or {}
    nationality = basic.get('nationality', '')

    is_chinese = any(w in nationality for w in ['中国', 'China', 'Chinese'])
    active_prompt = system_prompt_cn if is_chinese else system_prompt
    active_model = get_text_llm_model(is_chinese)

    # Build inner_circle
    protagonist_name = basic.get('name', '')
    inner_circle = _build_inner_circle(social, protagonist_name=protagonist_name, global_occupied=global_occupied, is_chinese=is_chinese)

    # Register the protagonist name + inner_circle names into the global de-dup pool
    if global_occupied is not None:
        with (global_lock or threading.Lock()):
            global_occupied.add(protagonist_name)
            for p in inner_circle:
                n = p.get('name', '').strip()
                if n:
                    global_occupied.add(n)

    # Compute target counts and plan the batches
    targets = _compute_graph_targets(max_events, len(inner_circle))
    batches = _plan_batches(targets)

    total_people = sum(targets.get(c, 0) for c in PERSON_CATEGORIES)
    total_orgs = targets.get('organizations', 0)
    print(f"    Target: {total_people} people + {total_orgs} orgs in {len(batches)} batch(es)")

    # Call the LLM batch by batch
    all_generated_people = []  # accumulated generated people (for cross-batch de-dup)
    merged_graph = {cat: [] for cat in ALL_CATEGORIES}

    for batch_idx, batch_targets in enumerate(batches):
        batch_cats = list(batch_targets.keys())
        batch_people_n = sum(v for k, v in batch_targets.items() if k != 'organizations')
        batch_org_n = batch_targets.get('organizations', 0)
        print(f"    Batch {batch_idx + 1}/{len(batches)}: "
              f"{batch_cats} ({batch_people_n} people, {batch_org_n} orgs)")

        user_content = _build_user_prompt(
            persona_record, batch_targets, is_chinese,
            already_generated=all_generated_people,
            global_occupied=global_occupied,
            global_lock=global_lock)

        result = _call_llm_for_graph(
            active_prompt, user_content, active_model,
            inner_circle, protagonist_name,
            global_occupied, global_lock)

        # Merge this batch's results
        for cat in batch_cats:
            items = result.get(cat, [])
            merged_graph[cat].extend(items)
            if cat != 'organizations':
                all_generated_people.extend(items)

        batch_got = sum(len(result.get(c, [])) for c in batch_cats)
        print(f"    Batch {batch_idx + 1}: got {batch_got} items")

    # Assemble the final Social_Graph
    social_graph = {'inner_circle': inner_circle}
    social_graph.update(merged_graph)

    # Print statistics
    total_people = sum(len(social_graph.get(c, [])) for c in ['inner_circle'] + PERSON_CATEGORIES)
    total_orgs = len(social_graph.get('organizations', []))
    print(f"    Graph: {total_people} people ({len(inner_circle)} inner + "
          f"{total_people - len(inner_circle)} extended), {total_orgs} organizations")

    # Return the complete record with Social_Graph
    record = persona_record.copy()
    record['Social_Graph'] = social_graph
    return record

class SocialWorldGenerator(Generator):
    """Plan each persona's 2025 social graph (inner_circle + extended categories).

    Domain generator for the old stage 3.9. The batch run uses
    :func:`generate_social_graph` (serial, with a cross-persona global name registry);
    this class is a thin uniform per-persona entry point for the future pipeline
    DAG, holding the prompts / ``max_events`` / shared global de-dup state.
    """

    stage_label = "Stage3.9"
    stage_num = "3.9"
    index_key = "uuid"
    produces = "social_world"

    def __init__(self, system_prompt: str, system_prompt_cn: str, max_events: int,
                 global_occupied: set = None, global_lock: threading.Lock = None) -> None:
        self.system_prompt = system_prompt
        self.system_prompt_cn = system_prompt_cn
        self.max_events = max_events
        self.global_occupied = global_occupied if global_occupied is not None else set()
        self.global_lock = global_lock or threading.Lock()

    def produce(self, record: Dict, ctx=None) -> Dict:
        return _process_single_persona(
            record, self.system_prompt, self.system_prompt_cn, self.max_events,
            global_occupied=self.global_occupied, global_lock=self.global_lock)

def generate_social_graph(stage3_records: List[Dict], prompts_dir: str,
                      max_events: int = 100,
                      existing: Optional[Dict[str, Dict]] = None,
                      save_callback=None,
                      max_workers: int = DEFAULT_WORKERS) -> List[Dict]:
    """
    Generate social graphs in parallel, with checkpoint/resume support.

    Args:
        stage3_records: list of Stage 3 output records
        prompts_dir: path to the prompts/ directory
        max_events: target total events per persona (used to size the graph)
        existing: uuid -> existing stage3.9 record (checkpoint data)
        save_callback: save callback fn(records_list)
        max_workers: number of parallel workers

    Returns:
        The complete records list (in the original persona order)
    """
    existing = existing or {}

    # Load both prompt variants: English (base) and the Chinese (_cn) instructions.
    prompt_path = os.path.join(prompts_dir, 'stage3_9_social_graph.txt')
    cn_prompt_path = os.path.join(prompts_dir, 'stage3_9_social_graph_cn.txt')

    with open(prompt_path, 'r', encoding='utf-8') as f:
        system_prompt = f.read()
    with open(cn_prompt_path, 'r', encoding='utf-8') as f:
        system_prompt_cn = f.read()

    print(f"[Stage3.9] Target graph size based on max_events={max_events}")

    # Classify: skip / needs processing
    ordered_uuids = [p.get('uuid') for p in stage3_records]
    to_process = []
    records_by_uuid = {}

    for persona in stage3_records:
        uid = persona.get('uuid')
        if uid in existing and existing[uid].get('Social_Graph'):
            records_by_uuid[uid] = existing[uid]
            print(f"[Stage3.9] uid={uid}: SKIP (checkpoint)")
        else:
            to_process.append(persona)
            print(f"[Stage3.9] uid={uid}: PENDING")

    if not to_process:
        print("[Stage3.9] All personas already have social graphs!")
        return [records_by_uuid[u] for u in ordered_uuids if u in records_by_uuid]

    # Global name registry (de-dup across protagonists)
    global_occupied: set = set()
    global_lock = threading.Lock()
    # Pre-fill all person names from already-skipped personas into the global set (including inner_circle)
    for uid, rec in records_by_uuid.items():
        # Protagonist name
        proto_name = rec.get('Basic_Profile', {}).get('name', '').strip()
        if proto_name:
            global_occupied.add(proto_name)
        sg = rec.get('Social_Graph', {})
        for cat in ['inner_circle'] + list(ALL_CATEGORIES):
            for person in sg.get(cat, []):
                name = person.get('name', '').strip()
                if name:
                    global_occupied.add(name)

    # ★ Key: also pre-register the inner_circle (from Stage 2) of the personas to be processed into the global set
    #   otherwise, during serial processing, an earlier persona would not know the inner_circle names of later personas
    for persona in to_process:
        proto_name = persona.get('Basic_Profile', {}).get('name', '').strip()
        if proto_name:
            global_occupied.add(proto_name)
        social = (persona.get('Init_State', {}).get('social_relationships', {}) or {})
        for name in social.keys():
            if name and name.strip():
                global_occupied.add(name.strip())

    def _get_ordered():
        return [records_by_uuid[u] for u in ordered_uuids if u in records_by_uuid]

    print(f"\n[Stage3.9] Processing {len(to_process)} personas serially "
          f"(global name dedup enabled)...\n")

    for persona in to_process:
        uid = persona.get('uuid')
        set_log_context(uuid=uid, stage="stage3_9_social_graph")
        print(f"\n  [uid={uid}] Generating social graph...")
        try:
            record = _process_single_persona(
                persona, system_prompt, system_prompt_cn, max_events,
                global_occupied=global_occupied,
                global_lock=global_lock)
            records_by_uuid[uid] = record
            if save_callback:
                save_callback(_get_ordered())
            print(f"  [uid={uid}] COMPLETE  (global pool: {len(global_occupied)} names)")
        except Exception as e:
            print(f"  [uid={uid}] ERROR: {e}")
            traceback.print_exc()
            records_by_uuid[uid] = persona.copy()

    # Final save
    result = _get_ordered()
    if save_callback:
        save_callback(result)

    return result


# ============================================================================
# Social-name normalizer (folded from the old stage2_fix_names / Stage 2.1)
#
# Detects and fixes problematic keys in stage2 social_relationships (pure
# relationship words, surname+title, prefixed nicknames, etc.). Reuses the
# ``_make_unique_name`` / name-pool helpers above for fallback de-duplication.
# ============================================================================

RELATION_KEYWORDS = {
    '母亲', '父亲', '妈妈', '爸爸', '岳母', '岳父', '婆婆', '公公',
    '丈夫', '妻子', '老公', '老婆', '配偶',
    '儿子', '女儿', '大儿子', '小儿子', '大女儿', '小女儿',
    '哥哥', '弟弟', '姐姐', '妹妹',
    '爷爷', '奶奶', '外公', '外婆', '姑姑', '叔叔', '舅舅', '阿姨',
    '侄子', '侄女', '外甥', '外甥女',
}

# Surname + relationship abbreviation pattern, for example surname plus mother/father/sister.
_SURNAME_REL_PATTERN = re.compile(
    r'^[\u4e00-\u9fff]{1,2}(母|父|姐|哥|弟|妹|叔|姑|舅|婆|公|嫂)$'
)

# Title / form-of-address suffixes
TITLE_SUFFIXES = ['老师', '医生', '律师', '教练', '经理', '编辑', '师傅', '阿姨', '美容师', '团长']

# Prefix word list (used by B3 to extract the real name)
NAME_PREFIXES = sorted([
    '辅导员', '室友', '表哥', '表姐', '表弟', '表妹',
    '高中好友', '大学同学', '社团学姐', '社团学长',
    '外卖店老板', '考研自习室邻座', '图书馆管理员',
    '游戏队友', '小红书美妆博主', '拼多多客服',
], key=len, reverse=True)


def classify_name(name: str, rel_type: str) -> str:
    """Classify a social_relationships key and return its category label."""
    # A1: pure relationship word
    if name in RELATION_KEYWORDS:
        return 'A1'
    # A2: surname + relationship abbreviation
    if _SURNAME_REL_PATTERN.match(name):
        return 'A2'
    # A3: key == relationship_type
    if name == rel_type:
        return 'A3'
    # B4: nickname(real name), for example a nickname followed by a real name in parentheses.
    if '（' in name or '(' in name:
        return 'B4'
    # B5: online name in quotes, for example a game teammate nickname.
    if '"' in name or '\u201c' in name or '\u201d' in name:
        return 'B5'
    # B1: surname + title, short forms such as surname plus lawyer/doctor.
    for suffix in TITLE_SUFFIXES:
        if name.endswith(suffix) and len(name) <= len(suffix) + 2:
            return 'B1'
    # B2: prefix + surname + title, such as counselor plus surname plus teacher.
    if len(name) > 4 and any(name.endswith(s) for s in TITLE_SUFFIXES):
        return 'B2'
    # B3: prefix + real name, such as roommate plus a full name.
    for prefix in NAME_PREFIXES:
        if name.startswith(prefix) and len(name) > len(prefix):
            return 'B3'
    # B6: hyphenated nickname
    if '-' in name or '—' in name:
        return 'B6'
    # Normal Chinese name, 2-4 characters
    if re.match(r'^[\u4e00-\u9fff]{2,4}$', name):
        return 'OK'
    # Normal English name (e.g. "James Carter", "Emily Grace Thompson")
    if re.match(r'^[A-Za-z][A-Za-z\s.\'-]{1,40}$', name) and any(c.isalpha() for c in name):
        return 'OK'
    # A long string may contain a real name.
    return 'UNKNOWN'

def is_problematic_name(name: str, rel_type: str) -> bool:
    """Decide whether a social_relationships key needs fixing."""
    return classify_name(name, rel_type) != 'OK'

# ---------------------------------------------------------------------------
# Regex extraction (disabled; everything is handled by the LLM)
# ---------------------------------------------------------------------------
def extract_name_from_key(key: str, category: str) -> Optional[str]:
    return None

def collect_problems(social_rel: dict) -> Dict[str, Tuple[str, str]]:
    """Collect all problematic names in a single persona.

    Returns:
        {old_key: (relationship_type, category)}
    """
    problems = {}
    for name, info in social_rel.items():
        rel_type = info.get('relationship_type', '') if isinstance(info, dict) else ''
        cat = classify_name(name, rel_type)
        if cat != 'OK':
            problems[name] = (rel_type, cat)
    return problems

def _load_prompt(prompts_dir: str, is_chinese: bool = True) -> str:
    # Chinese personas use the _zh prompt; others use the _en one.
    filename = 'fix_relationship_names_zh.txt' if is_chinese else 'fix_relationship_names_en.txt'
    path = os.path.join(prompts_dir, filename)
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def fix_names_with_llm(
    main_name: str,
    main_gender: str,
    problems: Dict[str, str],
    forbidden_names: Set[str],
    prompts_dir: str,
    is_chinese: bool = True,
) -> Dict[str, str]:
    """Call the LLM to generate replacement names in bulk.

    Returns:
        {old_key: new_name}
    """
    # Build the problem list text
    problem_lines = []
    for old_key, rel_type in problems.items():
        problem_lines.append(f'- "{old_key}"（关系：{rel_type}）')
    problem_list = '\n'.join(problem_lines)

    forbidden_str = '、'.join(sorted(forbidden_names)) if forbidden_names else '（无）'

    prompt_template = _load_prompt(prompts_dir, is_chinese=is_chinese)
    user_prompt = prompt_template.format(
        main_name=main_name,
        main_gender=main_gender,
        problem_list=problem_list,
        forbidden_names=forbidden_str,
    )

    response, cost_info = llm_request(
        system_prompt='',
        user_prompt=user_prompt,
        model=get_text_llm_model(is_chinese),
        return_parsed_json=False,
        extract_json=False,
    )

    if cost_info:
        print(f"  [Cost] Input: {cost_info.get('input_tokens', 'N/A')}, "
              f"Output: {cost_info.get('output_tokens', 'N/A')}, "
              f"Cost: ${cost_info.get('total_cost_usd', 'N/A')}")

    # Parse manually: strip // comments, then json.loads
    import json as _json
    # When llm_request uses return_parsed_json=True it may return a dict (success) or the raw string (failure)
    if isinstance(response, dict):
        return response
    if not isinstance(response, str):
        print(f"  [WARN] LLM returned unexpected type: {type(response)}: {str(response)[:200]}")
        return {}
    # Extract the JSON block
    raw = response
    m = re.search(r'\{[^{}]*\}', raw, re.DOTALL)
    if m:
        raw = m.group(0)
    # Remove inline // comments
    raw = re.sub(r'//[^\n]*', '', raw)
    # Remove trailing commas
    raw = re.sub(r',\s*}', '}', raw)
    try:
        result = _json.loads(raw)
        if isinstance(result, dict):
            return result
        print(f"  [WARN] LLM JSON not a dict: {str(result)[:200]}")
        return {}
    except Exception as e:
        print(f"  [WARN] LLM JSON parse error: {e}\nRaw: {raw[:300]}")
        return {}

def apply_fixes(
    social_rel: dict,
    fixes: Dict[str, str],
    global_names: Set[str],
) -> Tuple[dict, List[str]]:
    """Apply the fixes and return (fixed_rel, changes_log)."""
    fixed = {}
    changes = []
    # Include all original keys (including problematic ones) to prevent new names from colliding with not-yet-processed original keys
    original_keys = set(social_rel.keys())

    for name, info in social_rel.items():
        if name in fixes:
            new_name = fixes[name]
            # De-duplication check: global name pool + already-written new keys + all original keys
            taken = global_names | set(fixed.keys()) | original_keys
            if new_name in taken:
                fallback = _make_unique_name(taken)
                changes.append(f'"{name}" -> "{new_name}" (conflict) -> "{fallback}"')
                new_name = fallback
            else:
                changes.append(f'"{name}" -> "{new_name}"')
            global_names.add(new_name)
            fixed[new_name] = info
        else:
            fixed[name] = info

    return fixed, changes

# ---------------------------------------------------------------------------
# Main process
# ---------------------------------------------------------------------------

def fix_social_names(stage2_path: str, prompts_dir: str) -> int:
    """Read stage2 output -> detect -> regex extraction + LLM fix -> overwrite. Returns the total number of fixes."""

    if not os.path.exists(stage2_path):
        print(f"[Stage2.1] File not found: {stage2_path}")
        return 0

    with jsonlines.open(stage2_path, 'r') as reader:
        records = list(reader)

    # Build the global name set (main persona name + all valid social_relationships names)
    global_names: Set[str] = set()
    for rec in records:
        main_name = rec.get('Basic_Profile', {}).get('name', '')
        if main_name:
            global_names.add(main_name)
        social_rel = rec.get('Init_State', {}).get('social_relationships', {}) or {}
        for name, info in social_rel.items():
            rel_type = info.get('relationship_type', '') if isinstance(info, dict) else ''
            if not is_problematic_name(name, rel_type):
                global_names.add(name)

    total_fixes = 0
    modified = False

    for rec in records:
        uuid = rec.get('uuid', '?')
        set_log_context(uuid=uuid, stage="stage2_1_fix_names")
        bp = rec.get('Basic_Profile', {})
        main_name = bp.get('name', '')
        main_gender = bp.get('gender', '')
        nationality = bp.get('nationality', '')
        is_chinese = '中国' in nationality or 'China' in nationality or 'Chinese' in nationality
        init_state = rec.get('Init_State', {})
        social_rel = init_state.get('social_relationships', {}) or {}

        problems = collect_problems(social_rel)
        if not problems:
            continue

        print(f"\n[Stage2.1] uuid={uuid} ({main_name}): found {len(problems)} problematic names: "
              f"{list(problems.keys())}")

        # Phase 1: send all problematic names to the LLM
        llm_problems: Dict[str, str] = {old_key: rel_type for old_key, (rel_type, cat) in problems.items()}

        # Phase 2: LLM fix
        if llm_problems:
            try:
                fixes = fix_names_with_llm(
                    main_name, main_gender, llm_problems,
                    global_names | set(social_rel.keys()), prompts_dir,
                    is_chinese=is_chinese,
                )

                if fixes:
                    fixed_rel, changes = apply_fixes(social_rel, fixes, global_names)
                    init_state['social_relationships'] = fixed_rel
                    for c in changes:
                        print(f"  [LLM] {c}")
                    total_fixes += len(changes)
                    modified = True
                else:
                    print(f"  [WARN] LLM returned no fixes for uuid={uuid}")

                # Record the unfixed ones
                unfixed = set(llm_problems.keys()) - set(fixes.keys()) if fixes else set(llm_problems.keys())
                for key in unfixed:
                    print(f"  [UNFIXED] '{key}' (rel_type='{llm_problems[key]}')")

            except Exception as e:
                print(f"  [ERROR] uuid={uuid}: {e}")
                traceback.print_exc()

    if modified:
        os.makedirs(os.path.dirname(stage2_path), exist_ok=True)
        with jsonlines.open(stage2_path, 'w') as writer:
            for rec in records:
                writer.write(rec)
        print(f"\n[Stage2.1] Saved {len(records)} records to {stage2_path}")

    return total_fixes


class SocialNameNormalizer(Generator):
    """Fix problematic social_relationships keys produced by stage 2 (was Stage 2.1).

    Not a per-record :meth:`produce` generator: it rewrites the stage2 file
    in place via :func:`fix_social_names`. Exposed as a domain class for the
    pipeline DAG; the batch entry is :meth:`run_file`.
    """

    stage_label = "Stage2.1"
    stage_num = "2.1"
    produces = "social_name_fix"

    def run_file(self, stage2_path: str, prompts_dir: str) -> int:
        return fix_social_names(stage2_path, prompts_dir)
