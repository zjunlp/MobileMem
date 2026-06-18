"""Conversation LLM member selection + chat-content generation."""
import json
import logging
import re
from typing import Dict, List

logger = logging.getLogger('stage7')


def _collect_all_social_members(persona: Dict) -> List[Dict]:
    """Collect all social members from persona social_relationships and Social_Graph.
    
    Returns a deduplicated member list; each member has name, relationship,
    gender, brief, and category fields. For vague family relationships, infer
    specific relative keywords from brief; without keywords, classify only as
    elder/child by age and never infer father/mother from age alone.
    """
    bp = persona.get('Basic_Profile', {})
    main_name = bp.get('name', 'Unknown')
    main_birth = bp.get('date_of_birth', '')  # noqa: F841
    init = persona.get('Init_State', {})
    social = init.get('social_relationships', {})
    social_graph = persona.get('Social_Graph', {})
    
    members_by_name: Dict[str, Dict] = {}
    
    # Extract from Stage2 social_relationships.
    for rel_key, rel_info in social.items():
        if isinstance(rel_info, dict):
            rel_name = rel_info.get('name', '') or rel_key
            relationship = rel_info.get('relationship_type', rel_key)
            gender = rel_info.get('gender', '')
            description = rel_info.get('description', '')
        elif isinstance(rel_info, str):
            rel_name = rel_key
            relationship = rel_info
            gender = ''
            description = ''
        else:
            continue
        
        if rel_name and rel_name != main_name:
            members_by_name[rel_name] = {
                'name': rel_name,
                'relationship': relationship,
                'gender': gender,
                'brief': description,
                'category': 'inner_circle',
            }
    
    # Extract from Stage3.9 Social_Graph as supplements or overrides.
    for category in ['inner_circle', 'extended_contacts', 'professional_network', 'online_contacts', 'weak_ties']:
        items = social_graph.get(category, [])
        for item in items:
            if not isinstance(item, dict):
                continue
            rel_name = item.get('name', '')
            if not rel_name or rel_name == main_name:
                continue
            # Prefer Social_Graph data because it is richer.
            if rel_name not in members_by_name:
                members_by_name[rel_name] = {}
            members_by_name[rel_name].update({
                'name': rel_name,
                'relationship': item.get('relationship_to_protagonist', members_by_name.get(rel_name, {}).get('relationship', '')),
                'gender': item.get('gender', members_by_name.get(rel_name, {}).get('gender', '')),
                'brief': item.get('brief', members_by_name.get(rel_name, {}).get('brief', '')),
                'category': category,
            })
    
    # Refine vague family relationships from explicit event terms and brief keywords.
    # Do not infer father/mother by age alone; older relatives are not necessarily parents.
    _SPECIFIC_REL_PATTERNS = [
        # (regex_pattern, assigned_relationship)
        (r'(?:父亲|爸爸|爸(?!妈))', '父亲'),
        (r'(?:母亲|妈妈|妈(?!爸))', '母亲'),
        (r'(?:father|dad\b)', 'father'),
        (r'(?:mother|mom\b)', 'mother'),
        (r'(?:叔叔|伯伯|伯父|叔父)', '叔伯'),
        (r'(?:姑姑|姑妈|姑母)', '姑姑'),
        (r'(?:舅舅|舅父)', '舅舅'),
        (r'(?:阿姨|姨妈|姨母|婶婶)', '阿姨'),
        (r'(?:爷爷|祖父|外公|姥爷)', '祖辈'),
        (r'(?:奶奶|祖母|外婆|姥姥)', '祖辈'),
        (r'(?:uncle)', 'uncle'),
        (r'(?:aunt)', 'aunt'),
        (r'(?:grandpa|grandfather)', 'grandparent'),
        (r'(?:grandma|grandmother)', 'grandparent'),
        (r'(?:兄弟|哥哥|弟弟|brother)', '兄弟'),
        (r'(?:姐姐|妹妹|sister)', '姐妹'),
        (r'(?:表[哥弟姐妹]|堂[哥弟姐妹]|cousin)', '表亲'),
        (r'(?:侄[子女]|nephew|niece)', '侄辈'),
        (r'(?:女儿|儿子|son|daughter)', '子女'),
    ]

    for name, info in members_by_name.items():
        rel = info.get('relationship', '')
        if rel in ('家人', '家庭成员', 'family', 'family member'):
            # Extract specific family relationship keywords from brief/description.
            brief = info.get('brief', '') or ''
            age_range = info.get('age_range', '') or ''
            search_text = f"{brief} {age_range} {rel}"
            
            specific_found = False
            for pattern, specific_rel in _SPECIFIC_REL_PATTERNS:
                if re.search(pattern, search_text, re.IGNORECASE):
                    info['relationship'] = specific_rel
                    specific_found = True
                    break
            
            if specific_found:
                continue
            
            # Without specific keywords, classify roughly by age but never infer father/mother.
            age_match = re.search(r'(\d{2})', brief + ' ' + age_range)
            age = int(age_match.group(1)) if age_match else 0
            
            if age >= 50:
                info['relationship'] = '长辈'
            elif age > 0 and age < 18:
                info['relationship'] = '孩子'
    
    return list(members_by_name.values())

def build_group_specs(persona: Dict, event: Dict = None) -> List[Dict]:
    """Collect social members and return one llm_selected spec for dynamic LLM selection."""
    bp = persona.get('Basic_Profile', {})
    name = bp.get('name', 'Unknown')
    
    all_members = _collect_all_social_members(persona)
    
    # Return one spec carrying all social members for later LLM selection.
    return [{
        "group_type": "dynamic",
        "category": "llm_selected",
        "group_name": "",  # Decided by the LLM.
        "members": [name],  # Protagonist is always included.
        "member_count": 0,  # Decided by the LLM.
        "all_social_members": all_members,
    }]

# LLM group chat generation

def _format_social_members_for_prompt(members: List[Dict], is_cn: bool) -> str:
    """Format social members as readable text for LLM selection."""
    if not members:
        return "（无社交成员数据）" if is_cn else "(No social members data)"
    
    lines = []
    for i, m in enumerate(members):
        name = m.get('name', '')
        rel = m.get('relationship', '')
        gender = m.get('gender', '')
        brief = m.get('brief', '')
        cat = m.get('category', '')
        if is_cn:
            line = f"{i+1}. {name}（关系：{rel}，性别：{gender}，类别：{cat}）"
            if brief:
                line += f" — {brief[:80]}"
        else:
            line = f"{i+1}. {name} (relationship: {rel}, gender: {gender}, category: {cat})"
            if brief:
                line += f" — {brief[:80]}"
        lines.append(line)
    return "\n".join(lines)

def select_group_members_by_llm(
    persona: Dict, event: Dict, all_social_members: List[Dict],
    prompt_template: str, model: str = None
) -> Dict:
    """Let the LLM choose group topic, group name, and members from event context.
    
    Returns: dict with keys: group_name, group_type, members, member_count
    """
    from backends.llm import llm_request
    
    bp = persona.get('Basic_Profile', {})
    name = bp.get('name', 'Unknown')
    nationality = bp.get('nationality', 'Chinese')
    is_cn = (nationality == 'Chinese')
    
    # Detect events that involve parents when no definite parent relationship exists.
    _PARENT_KEYWORDS_CN = r'(?:父[亲母]|爸[爸妈]|妈[妈爸]|母亲|爹|娘|父母|爸妈|双亲)'
    _PARENT_KEYWORDS_EN = r'(?:father|mother|dad|mom|parent|mum)'
    _CONFIRMED_PARENT_RELS = {'父亲', '母亲', 'father', 'mother', '爸爸', '妈妈'}
    
    event_desc = (event.get('description', '') or '') + ' ' + (event.get('event_name', '') or '')
    event_mentions_parents = bool(
        re.search(_PARENT_KEYWORDS_CN, event_desc) or re.search(_PARENT_KEYWORDS_EN, event_desc, re.IGNORECASE)
    )
    has_confirmed_parents = any(
        m.get('relationship', '') in _CONFIRMED_PARENT_RELS for m in all_social_members
    )
    
    # Add a constraint forbidding other people from posing as parents in that case.
    no_parent_constraint_cn = ""
    no_parent_constraint_en = ""
    if event_mentions_parents and not has_confirmed_parents:
        no_parent_constraint_cn = (
            "\n## ⚠️ 重要约束\n"
            "此事件虽然涉及父母相关话题，但主角的社交关系中**没有确定的父亲或母亲**。"
            "请**不要**把年长亲戚（长辈、叔伯、阿姨等）当作父母放入群聊。"
            "正确做法：选择好友、同事或其他关系人组建群聊，在聊天中自然地**谈论**父母这个话题即可"
            '（例如朋友之间聊"最近回家看了父母"、同事之间聊"父母身体还好吗"等）。\n'
        )
        no_parent_constraint_en = (
            "\n## ⚠️ IMPORTANT CONSTRAINT\n"
            "This event involves a parent-related topic, but the protagonist does NOT have confirmed "
            "father or mother in their social contacts. Do NOT assign elderly relatives (elders, uncles, "
            "aunts, etc.) as parents in the group chat. Instead, select friends, colleagues, or other "
            "contacts and let them DISCUSS the parent topic naturally in conversation "
            "(e.g., friends chatting about 'visiting parents recently').\n"
        )
    
    members_text = _format_social_members_for_prompt(all_social_members, is_cn)
    
    event_info = json.dumps({
        "event_name": event.get('event_name', ''),
        "event_start_time": event.get('event_start_time', ''),
        "description": event.get('description', '')[:500],
        "importance": event.get('importance', ''),
        "participants": event.get('participants', []),
    }, ensure_ascii=False)
    
    if is_cn:
        select_prompt = f"""你是一个群聊策划专家。根据以下人物信息和事件，为主角选择最合适的群聊成员。

## 主角信息
- 姓名：{name}
- 国籍：{nationality}
- 职业：{persona.get('Init_State', {}).get('career', '')}
- 人设：{bp.get('personality_traits', '')}

## 当前事件
{event_info}

## 主角的所有社交关系人
{members_text}

## 任务
根据事件内容，请你：
1. **确定群聊主题**：这个事件最适合在什么样的群里讨论？（家人群/好友群/工作群/同学群/兴趣群等）
2. **选择参与成员**：从上面的社交关系人中选择3-8位最适合参与这个话题的成员（必须使用上面列表中的真实姓名）
3. **起群名**：起一个真实、有创意的群名（像真实微信群名，例如"一家人❤️""摸鱼小分队""XX项目组"等）

## 选择原则
- 事件参与者（participants）如果在社交关系列表中，必须优先选择
- 根据事件性质选择合适类别的关系人（工作事件选同事/上司，家庭事件选家人等）
- 成员数量：小群3-5人，中群5-8人
- 不要选择与事件毫无关系的人
{no_parent_constraint_cn}
## 输出格式
```json
{{
  "group_name": "有创意的真实群名",
  "group_type": "small或medium",
  "selected_members": ["成员1姓名", "成员2姓名", "..."]
}}
```
注意：selected_members 不包含主角 {name}，主角会自动加入。"""
    else:
        select_prompt = f"""You are a group chat planning expert. Based on the following persona and event, select the most appropriate group chat members for the main character.

## Main Character
- Name: {name}
- Nationality: {nationality}
- Career: {persona.get('Init_State', {}).get('career', '')}
- Personality: {bp.get('personality_traits', '')}

## Current Event
{event_info}

## All Social Contacts
{members_text}

## Task
Based on the event content:
1. **Determine group theme**: What kind of group is best for discussing this event? (family/friends/work/classmates/hobby etc.)
2. **Select members**: Choose 3-8 most appropriate members from the contacts above (must use exact names from the list)
3. **Name the group**: Create a realistic, creative group name

## Selection Principles
- Event participants must be prioritized if they appear in the contacts list
- Match contact categories to event type (work events → colleagues, family events → family members)
- Group sizes: small 3-5, medium 5-8
- Don't select people irrelevant to the event
{no_parent_constraint_en}
## Output Format
```json
{{
  "group_name": "Creative Group Name",
  "group_type": "small or medium",
  "selected_members": ["Member1", "Member2", "..."]
}}
```
Note: selected_members should NOT include the main character {name}, who is automatically added."""

    response, _ = llm_request(
        "",
        select_prompt,
        model=model,
        return_parsed_json=True,
        extract_json=True,
        json_markers=["```json", "```"]
    )
    
    # Extract the valid member-name set for checking LLM output.
    valid_names = {m['name'] for m in all_social_members}
    
    if isinstance(response, dict):
        selected = response.get('selected_members', [])
        # Filter out names invented by the LLM.
        validated = [m for m in selected if m in valid_names]
        if not validated:
            # Fallback: choose from event participants or all members.
            participants = event.get('participants', [])
            validated = [p for p in participants if p in valid_names][:4]
            if not validated and all_social_members:
                validated = [m['name'] for m in all_social_members[:3]]
        
        # Ensure at least 3 people including the protagonist; group chats should not have only 2.
        if len(validated) < 2 and all_social_members:
            # Add members until there are at least 2 others plus the protagonist.
            existing_names = set(validated)
            for m in all_social_members:
                if m['name'] not in existing_names and m['name'] != name:
                    validated.append(m['name'])
                    existing_names.add(m['name'])
                    if len(validated) >= 2:
                        break
        
        group_type = response.get('group_type', 'small')
        if group_type not in ('small', 'medium'):
            group_type = 'small' if len(validated) <= 5 else 'medium'
        
        members = [name] + validated
        return {
            "group_type": group_type,
            "category": "llm_selected",
            "group_name": response.get('group_name', '群聊' if is_cn else 'Group Chat'),
            "members": members,
            "member_count": len(members),
        }
    
    # Fallback when the LLM fails; ensure at least 3 people.
    fallback_members = [m['name'] for m in all_social_members[:max(2, 3)]] if all_social_members else []
    members = [name] + fallback_members
    return {
        "group_type": "small",
        "category": "llm_selected",
        "group_name": "群聊" if is_cn else "Group Chat",
        "members": members,
        "member_count": len(members),
    }

def _build_member_persona_text(selected_members: List[str], all_social_members: List[Dict], is_cn: bool) -> str:
    """Build persona description text for selected group-chat members."""
    member_map = {m['name']: m for m in all_social_members}
    lines = []
    for name in selected_members:
        info = member_map.get(name, {})
        rel = info.get('relationship', '')
        brief = info.get('brief', '')
        gender = info.get('gender', '')
        if is_cn:
            line = f"- {name}（{rel}，{gender}）"
            if brief:
                line += f"：{brief[:100]}"
        else:
            line = f"- {name} ({rel}, {gender})"
            if brief:
                line += f": {brief[:100]}"
        lines.append(line)
    return "\n".join(lines) if lines else ("（无成员信息）" if is_cn else "(No member info)")

def generate_group_chat_content(
    persona: Dict, event: Dict, group_specs: List[Dict], prompt_template: str, model: str = None
) -> tuple:
    """Generate group chat messages via LLM. Returns (group_data, chosen_spec).
    
    Flow: first ask the LLM to choose members and topic, then generate dialogue.
    """
    from backends.llm import llm_request

    bp = persona.get('Basic_Profile', {})
    name = bp.get('name', 'Unknown')
    nationality = bp.get('nationality', 'Chinese')
    is_cn = (nationality == 'Chinese')

    spec = group_specs[0]
    all_social_members = spec.get('all_social_members', [])
    
    # Step 1: let the LLM choose members and the group-chat topic.
    selected_spec = select_group_members_by_llm(persona, event, all_social_members, prompt_template, model)
    
    # Step 2: build rich persona information for dialogue generation.
    # Protagonist details.
    init_state = persona.get('Init_State', {})
    persona_info = json.dumps({
        "name": name,
        "nationality": bp.get('nationality'),
        "career": init_state.get('career'),
        "personality_traits": bp.get('personality_traits', ''),
        "life_experiences": bp.get('life_experiences', ''),
    }, ensure_ascii=False)

    event_info = json.dumps({
        "event_name": event.get('event_name'),
        "event_start_time": event.get('event_start_time'),
        "description": event.get('description', '')[:500],
        "importance": event.get('importance'),
        "participants": event.get('participants', []),
    }, ensure_ascii=False)

    # Group-member persona descriptions, excluding the protagonist.
    other_members = [m for m in selected_spec['members'] if m != name]
    member_personas_text = _build_member_persona_text(other_members, all_social_members, is_cn)

    # Format group-chat information.
    members_text = ", ".join(selected_spec['members'])
    group_info = f"群名：{selected_spec['group_name']}，成员：{members_text}" if is_cn else f"Group: {selected_spec['group_name']}, Members: {members_text}"

    prompt = prompt_template
    prompt = prompt.replace('{persona_info}', persona_info)
    prompt = prompt.replace('{event_info}', event_info)
    prompt = prompt.replace('{all_group_specs}', group_info)
    prompt = prompt.replace('{main_person_name}', name)
    prompt = prompt.replace('{member_personas}', member_personas_text)

    response, _ = llm_request(
        "",
        prompt,
        model=model,
        return_parsed_json=True,
        extract_json=True,
        json_markers=["```json", "```"]
    )

    if isinstance(response, dict):
        response['group_name'] = selected_spec['group_name']
        return response, selected_spec
    
    return {"group_name": selected_spec['group_name'], "messages": []}, selected_spec
