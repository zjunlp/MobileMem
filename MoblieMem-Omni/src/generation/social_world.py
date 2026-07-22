"""Social-world generator (Life / SocialWorld).

:func:`generate_social_graph` plans each persona's 2025 social graph — converting
the life_state node's ``social_relationships`` into an ``inner_circle`` and asking the LLM (in
category batches) for extended_contacts / service_people / professional_network
/ online_contacts / weak_ties / organizations — with a global cross-persona name
registry so no name is reused. It attaches ``Social_Graph`` to the persona record.

``generate_social_graph`` keeps its ``max_workers`` parameter for signature
compatibility (the body runs serially with global name de-dup).
"""

import os
import json
import traceback
import threading
from typing import Dict, List, Optional

from backends.llm import llm_request, calculate_cumulative_cost, get_text_llm_model, set_log_context
from core.lang import is_chinese_persona
from generation.name_pools import make_unique_name as _make_unique_name

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

# Relationship words that share the protagonist's surname (immediate blood relatives)
_SAME_SURNAME_RELATIONS = {
    '父亲', '爸爸', '母亲', '妈妈', '哥哥', '姐姐', '弟弟', '妹妹',
    '爷爷', '奶奶', '儿子', '女儿', '兄弟', '姐妹', '孙子', '孙女',
    'father', 'mother', 'brother', 'sister', 'son', 'daughter',
    'grandfather', 'grandmother',
}

def _build_inner_circle(social_relationships: Dict,
                        protagonist_name: str = '',
                        global_occupied: set = None,
                        is_chinese: bool = True) -> List[Dict]:
    """Convert the life_state node's social_relationships into a list of inner_circle nodes."""
    inner = []
    # Merge the globally occupied names as the de-duplication baseline
    used_names: set = set(global_occupied) if global_occupied is not None else set()
    if protagonist_name:
        used_names.add(protagonist_name)
    # Protagonist's surname: Chinese names lead with the surname character;
    # Western names put the family name in the last whitespace token, which is
    # what name_pools.make_unique_name's English branch expects ("{first} {surname}").
    if not protagonist_name:
        protagonist_surname = ''
    elif is_chinese:
        protagonist_surname = protagonist_name[0]
    else:
        protagonist_surname = protagonist_name.split()[-1]

    for key, info in social_relationships.items():
        rel_type = info.get('relationship_type', '朋友' if is_chinese else 'friend')
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
    if global_lock is None:
        global_lock = threading.Lock()
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
        with global_lock:
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
    if global_lock is None:
        global_lock = threading.Lock()
    if 'Social_Graph' in graph:
        graph = graph['Social_Graph']

    # Collect occupied names (within this persona + globally across personas)
    occupied = {protagonist_name}
    for person in inner_circle:
        occupied.add(person.get('name', ''))
    if global_occupied is not None:
        with global_lock:
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
        with global_lock:
            global_occupied.update(new_names)

    return validated

def _call_llm_for_graph(system_prompt: str, user_content: str,
                        model: str, inner_circle: List[Dict],
                        protagonist_name: str,
                        global_occupied: set = None,
                        global_lock: threading.Lock = None) -> Dict:
    """Single LLM call to obtain (part of) the social graph.

    Raises:
        RuntimeError: if all MAX_RETRIES attempts fail — a silently empty
            category batch would leave a hole in the graph, so failure must
            surface to the per-persona failure collection instead.
    """
    last_error = 'response was not a JSON object'
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response, cost_info = llm_request(
                system_prompt,
                user_content,
                model=model,
                return_parsed_json=True,
                extract_json=True,
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
            last_error = f"{type(e).__name__}: {e}"
            print(f"    [Attempt {attempt}/{MAX_RETRIES}] LLM call failed: {e}")
    raise RuntimeError(
        f"social graph LLM call failed after {MAX_RETRIES} attempts "
        f"for protagonist '{protagonist_name}': {last_error}")

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
    """Generate the social graph for a single persona in batches.

    Raises:
        RuntimeError: when an LLM batch exhausts its retries (propagated from
            :func:`_call_llm_for_graph`); the caller collects it per persona.
    """
    if global_lock is None:
        global_lock = threading.Lock()
    basic = persona_record.get('Basic_Profile', {})
    init = persona_record.get('Init_State', {})
    social = init.get('social_relationships', {}) or {}
    nationality = basic.get('nationality', '')

    is_chinese = is_chinese_persona(nationality)
    active_prompt = system_prompt_cn if is_chinese else system_prompt
    active_model = get_text_llm_model(is_chinese)

    # Build inner_circle
    protagonist_name = basic.get('name', '')
    inner_circle = _build_inner_circle(social, protagonist_name=protagonist_name, global_occupied=global_occupied, is_chinese=is_chinese)

    # Register the protagonist name + inner_circle names into the global de-dup pool
    if global_occupied is not None:
        with global_lock:
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

def generate_social_graph(dates_records: List[Dict], prompts_dir: str,
                      max_events: int = 100,
                      existing: Optional[Dict[str, Dict]] = None,
                      save_callback=None,
                      max_workers: int = DEFAULT_WORKERS) -> List[Dict]:
    """
    Generate social graphs serially (global cross-persona name de-dup requires
    processing one persona at a time), with checkpoint/resume support.

    Args:
        dates_records: list of timeline_dates node output records
        prompts_dir: path to the prompts/ directory
        max_events: target total events per persona (used to size the graph)
        existing: uuid -> existing social_world record (checkpoint data)
        save_callback: save callback fn(records_list)
        max_workers: unused; kept only for signature compatibility

    Returns:
        The complete records list (in the original persona order); personas
        that failed are absent so a rerun retries them from the checkpoint.

    Raises:
        RuntimeError: after the final save, if any persona failed — lists the
            failed uuids and reasons (successful records were already saved).
    """
    existing = existing or {}

    # Load both prompt variants: English (base) and the Chinese (_cn) instructions.
    prompt_path = os.path.join(prompts_dir, 'social_graph_en.txt')
    cn_prompt_path = os.path.join(prompts_dir, 'social_graph_zh.txt')

    with open(prompt_path, 'r', encoding='utf-8') as f:
        system_prompt = f.read()
    with open(cn_prompt_path, 'r', encoding='utf-8') as f:
        system_prompt_cn = f.read()

    print(f"[social_world] Target graph size based on max_events={max_events}")

    # Classify: skip / needs processing
    ordered_uuids = [p.get('uuid') for p in dates_records]
    to_process = []
    records_by_uuid = {}

    for persona in dates_records:
        uid = persona.get('uuid')
        if uid in existing and existing[uid].get('Social_Graph'):
            records_by_uuid[uid] = existing[uid]
            print(f"[social_world] uid={uid}: SKIP (checkpoint)")
        else:
            to_process.append(persona)
            print(f"[social_world] uid={uid}: PENDING")

    if not to_process:
        print("[social_world] All personas already have social graphs!")
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

    # ★ Key: also pre-register the inner_circle (from the life_state node) of the personas to be processed into the global set
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

    print(f"\n[social_world] Processing {len(to_process)} personas serially "
          f"(global name dedup enabled)...\n")

    failures: List[tuple] = []
    for persona in to_process:
        uid = persona.get('uuid')
        set_log_context(uuid=uid, stage="social_world")
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
        except Exception as e:  # keep processing; reported after the loop
            print(f"  [uid={uid}] ERROR: {e}")
            traceback.print_exc()
            failures.append((uid, f"{type(e).__name__}: {e}"))

    # Final save (failed personas are absent, so a rerun retries them)
    result = _get_ordered()
    if save_callback:
        save_callback(result)

    if failures:
        summary = "; ".join(f"uid={uid}: {msg}" for uid, msg in failures)
        raise RuntimeError(
            f"[social_world] {len(failures)}/{len(to_process)} personas failed "
            f"(successful records were saved): {summary}")

    return result
