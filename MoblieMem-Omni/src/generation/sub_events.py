"""Sub-events generator (Timeline / SubEvents).

Splits each persona's long-term / mid-term annual events into chronologically
ordered short-term sub-event arcs, inserting "reminiscence" intro sub-events the
first time a social person appears, and emits one ``{uuid, sub_events,
cost_info}`` record per persona (the :class:`core.SubEvent` contract).

:class:`SubEventsGenerator` is a thin uniform entry point over
:func:`process_one_uuid`; the standalone run uses :func:`main` with its own
parallel orchestration.
"""

import os
import sys
import json
import argparse
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from common import read_jsonl, write_jsonl, load_existing_by_uuid, OUTPUT_DIR
from backends.llm import llm_request, calculate_cumulative_cost, get_text_llm_model, set_log_context
from core import SubEvent
from infra.base_generator import Generator

DEFAULT_WORKERS = 3

# Prompts

SYSTEM_PROMPT_CN = """你是一个创意写作助手。你需要将一个长期/中期事件拆分为一系列按时间顺序排列的子事件。

拆分原则：
1. 每个子事件是一个具体的、可感知的场景片段（有时间、地点、行动、情绪）
2. 子事件之间有因果递进关系，形成完整的叙事弧线
3. 情绪应有起伏变化（如：期待→犹豫→行动→挫折→调整→释然）
4. 所有子事件必须是 short-term（单次具体行动），不允许出现 mid-term 或 long-term
5. 每个子事件的 description 以第一人称（"我"）叙述，3-5句话，自然生动
6. 子事件的时间必须在父事件的 start_time 和 end_time 范围内
7. participants 只能使用提供的"可用人物列表"中的人，不要编造新角色

输出 JSON 格式：
```json
{
  "children": [
    {
      "sub_event_id": "父事件id_序号",
      "event_name": "简洁描述性标题",
      "event_start_time": "YYYY-MM-DD HH:MM:SS",
      "event_end_time": "YYYY-MM-DD HH:MM:SS",
      "duration_type": "short-term",
      "participants": ["人名"],
      "description": "以第一人称叙述的场景描述...",
      "importance": "high/medium/low"
    }
  ]
}
```

重要：
- long-term 事件拆分为 5-8 个子事件
- mid-term 事件拆分为 3-5 个子事件
- 所有文本必须使用纯中文
- description 不要提及"聊天机器人"
"""

SYSTEM_PROMPT_EN = """You are a creative writing assistant. You need to split a long-term/mid-term event into a series of chronologically ordered sub-events.

Splitting principles:
1. Each sub-event is a concrete, perceivable scene fragment (with time, place, action, emotion)
2. Sub-events have causal progression, forming a complete narrative arc
3. Emotions should fluctuate (e.g.: anticipation → hesitation → action → setback → adjustment → relief)
4. All sub-events must be short-term (single concrete actions), no mid-term or long-term allowed
5. Each sub-event's description should be in first person ("I"), 3-5 sentences, natural and vivid
6. Sub-event times must fall within the parent event's start_time and end_time range
7. Participants can only be from the provided "available people list", do not fabricate new characters

Output JSON format:
```json
{
  "children": [
    {
      "sub_event_id": "parent_event_id_number",
      "event_name": "Concise descriptive title",
      "event_start_time": "YYYY-MM-DD HH:MM:SS",
      "event_end_time": "YYYY-MM-DD HH:MM:SS",
      "duration_type": "short-term",
      "participants": ["person name"],
      "description": "First-person scene description...",
      "importance": "high/medium/low"
    }
  ]
}
```

Important:
- Split long-term events into 5-8 sub-events
- Split mid-term events into 3-5 sub-events
- All text must be in English
- Do not mention "chatbot" in descriptions
"""

# Kept for backward compatibility
SYSTEM_PROMPT = SYSTEM_PROMPT_CN


def build_user_prompt(protagonist_name: str,
                      protagonist_brief: str,
                      event: Dict,
                      available_people: List[str],
                      is_chinese: bool = True) -> str:
    """Build the user prompt for splitting an event into sub-events."""
    duration = event.get('duration_type', 'long-term')
    if duration == 'long-term':
        count_hint = "5-8"
    else:
        count_hint = "3-5"

    if is_chinese:
        people_list = "、".join(available_people) if available_people else "（无，子事件中只有主人公一人）"

        return f"""## 主人公
- 姓名：{protagonist_name}
- 简介：{protagonist_brief}

## 需要拆分的事件
- event_id：{event.get('event_id')}
- 事件名称：{event.get('event_name')}
- 开始时间：{event.get('event_start_time')}
- 结束时间：{event.get('event_end_time')}
- duration_type：{duration}
- 参与人：{json.dumps(event.get('participants', []), ensure_ascii=False)}
- 事件描述：{event.get('description', '')}
- 重要性：{event.get('importance', 'medium')}

## 可用人物列表（子事件的 participants 只能从这里选）
{people_list}

请将上述{duration}事件拆分为 {count_hint} 个子事件，sub_event_id 格式为 "{event.get('event_id')}_1"、"{event.get('event_id')}_2" 等。"""
    else:
        people_list = ", ".join(available_people) if available_people else "(None — sub-events should only involve the protagonist)"

        return f"""## Protagonist
- Name: {protagonist_name}
- Bio: {protagonist_brief}

## Event to Split
- event_id: {event.get('event_id')}
- Event name: {event.get('event_name')}
- Start time: {event.get('event_start_time')}
- End time: {event.get('event_end_time')}
- duration_type: {duration}
- Participants: {json.dumps(event.get('participants', []), ensure_ascii=False)}
- Description: {event.get('description', '')}
- Importance: {event.get('importance', 'medium')}

## Available People (sub-event participants must come from this list only)
{people_list}

Please split the above {duration} event into {count_hint} sub-events. Use sub_event_id format: "{event.get('event_id')}_1", "{event.get('event_id')}_2", etc."""


def split_one_event(protagonist_name: str,
                    protagonist_brief: str,
                    event: Dict,
                    available_people: List[str],
                    model: str,
                    is_chinese: bool = True) -> Optional[Dict]:
    """Call the LLM to split a single event into sub-events."""
    system_prompt = SYSTEM_PROMPT_CN if is_chinese else SYSTEM_PROMPT_EN
    user_prompt = build_user_prompt(
        protagonist_name=protagonist_name,
        protagonist_brief=protagonist_brief,
        event=event,
        available_people=available_people,
        is_chinese=is_chinese,
    )

    try:
        result, cost = llm_request(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            return_parsed_json=True,
            extract_json=True,
            json_markers=[],
        )
        if isinstance(result, dict) and 'children' in result:
            return result['children'], cost
        elif isinstance(result, list):
            return result, cost
        else:
            print(f"    [WARNING] Unexpected format for event_{event.get('event_id')}: {str(result)[:100]}")
            return None, cost
    except Exception as e:
        print(f"    [ERROR] Failed to split event_{event.get('event_id')}: {e}")
        return None, {"total_cost_usd": 0}


# Person-introduction sub-event generation

INTRO_SYSTEM_PROMPT_CN = """你是一个创意写作助手。你需要以主人公的口吻写一段内心独白/回忆，描述他/她对某个人的印象和关系。

写作原则：
1. 以第一人称（"我"）叙述，自然生动，3-5句话
2. 根据关系类型选择合适的叙述方式：
   - 父母/长辈：温情回忆（不要写"我第一次见到"，用自然的方式提及）
   - 配偶/恋人：甜蜜或日常的相处回忆
   - 朋友/同学：趣事、特点、印象深刻的场景
   - 同事/上司：工作中的初次印象或特点描述
3. 描述像是在路上、等待时、发呆时自然浮现的念头
4. 包含具体细节（习惯、表情、口头禅等），让人物鲜活
5. 不要提及"聊天机器人"

输出 JSON 格式：
```json
{
  "event_name": "回忆：关于XXX",
  "description": "以第一人称叙述的内心独白..."
}
```
"""

INTRO_SYSTEM_PROMPT_EN = """You are a creative writing assistant. You need to write an inner monologue/reminiscence from the protagonist's perspective, describing their impression of and relationship with a certain person.

Writing principles:
1. Narrate in first person ("I"), natural and vivid, 3-5 sentences
2. Choose appropriate narration style based on relationship type:
   - Parents/elders: warm reminiscence (don't write "I first met...", mention naturally)
   - Spouse/partner: sweet or everyday memories together
   - Friends/classmates: anecdotes, characteristics, memorable scenes
   - Colleagues/superiors: first impressions at work or notable traits
3. Describe like thoughts naturally surfacing while walking, waiting, or daydreaming
4. Include specific details (habits, expressions, catchphrases, etc.) to make the person vivid
5. Do not mention "chatbot"

Output JSON format:
```json
{
  "event_name": "Reminiscence: About XXX",
  "description": "First-person inner monologue..."
}
```
"""

# Kept for backward compatibility
INTRO_SYSTEM_PROMPT = INTRO_SYSTEM_PROMPT_CN


def generate_introduction_sub_event(
    protagonist_name: str,
    protagonist_brief: str,
    person_name: str,
    relationship_type: str,
    person_description: str,
    model: str,
    is_chinese: bool = True,
) -> Optional[Dict]:
    """Generate a "reminiscence/inner monologue" sub-event for a not-yet-introduced person."""
    intro_system = INTRO_SYSTEM_PROMPT_CN if is_chinese else INTRO_SYSTEM_PROMPT_EN

    if is_chinese:
        user_prompt = f"""## 主人公
- 姓名：{protagonist_name}
- 简介：{protagonist_brief}

## 需要回忆的人物
- 姓名：{person_name}
- 与主人公的关系：{relationship_type}
- 人物描述：{person_description}

请以主人公的口吻写一段关于"{person_name}"的内心独白/回忆。根据关系类型（{relationship_type}）选择合适的叙述方式。不需要和任何具体事件挂钩，只需要体现主人公对这个人物的感受和记忆。"""
    else:
        user_prompt = f"""## Protagonist
- Name: {protagonist_name}
- Bio: {protagonist_brief}

## Person to Reminisce About
- Name: {person_name}
- Relationship to protagonist: {relationship_type}
- Description: {person_description}

Write an inner monologue/reminiscence about "{person_name}" from the protagonist's perspective. Choose an appropriate narration style based on the relationship type ({relationship_type}). Do not tie it to any specific event — just reflect the protagonist's feelings and memories about this person."""

    try:
        result, cost = llm_request(
            system_prompt=intro_system,
            user_prompt=user_prompt,
            model=model,
            return_parsed_json=True,
            extract_json=True,
            json_markers=[],
        )
        if isinstance(result, dict):
            return result, cost
        else:
            print(f"    [WARNING] Unexpected intro format for {person_name}: {str(result)[:100]}")
            return None, cost
    except Exception as e:
        print(f"    [ERROR] Failed to generate intro for {person_name}: {e}")
        return None, {"total_cost_usd": 0}


def insert_introduction_sub_events(
    children: List[Dict],
    new_people: List[Dict],
    parent_event: Dict,
    protagonist_name: str,
    protagonist_brief: str,
    model: str,
    is_chinese: bool = True,
) -> tuple:
    """Generate reminiscence sub-events for newly appearing people and insert them at the front of children.

    Args:
        children: the original sub-event list generated by the LLM
        new_people: [{name, relationship_type, description}, ...]
        parent_event: the parent event
        protagonist_name: protagonist's name
        protagonist_brief: protagonist's short bio
        model: LLM model name

    Returns:
        (updated_children, cumulative_cost)
    """
    if not new_people or not children:
        return children, None

    # Find the earliest start_time among children
    earliest_time = None
    for c in children:
        t = c.get('event_start_time', '')
        if t:
            try:
                dt = datetime.strptime(t, '%Y-%m-%d %H:%M:%S')
                if earliest_time is None or dt < earliest_time:
                    earliest_time = dt
            except ValueError:
                pass

    if earliest_time is None:
        # fallback: use the parent event's start_time
        try:
            earliest_time = datetime.strptime(parent_event.get('event_start_time', ''), '%Y-%m-%d %H:%M:%S')
        except ValueError:
            earliest_time = datetime(2025, 1, 1, 12, 0, 0)

    parent_event_id = parent_event.get('event_id')
    intro_events = []
    cumulative_cost = None

    for i, person_info in enumerate(new_people):
        print(f"      Generating intro for {person_info['name']} ({person_info['relationship_type']})")

        intro_result, cost = generate_introduction_sub_event(
            protagonist_name=protagonist_name,
            protagonist_brief=protagonist_brief,
            person_name=person_info['name'],
            relationship_type=person_info['relationship_type'],
            person_description=person_info.get('description', ''),
            model=model,
            is_chinese=is_chinese,
        )
        cumulative_cost = calculate_cumulative_cost(cumulative_cost, cost)

        if intro_result:
            # Time: place them before earliest_time, 3 minutes apart each
            offset = len(new_people) - i  # the first person comes earliest
            end_time = earliest_time - timedelta(minutes=3 * (offset - 1))
            start_time = end_time - timedelta(minutes=3)

            default_name = f'回忆：关于{person_info["name"]}' if is_chinese else f'Reminiscence: About {person_info["name"]}'
            intro_event = {
                "sub_event_id": f"{parent_event_id}_{i + 1}",
                "event_name": intro_result.get('event_name', default_name),
                "event_start_time": start_time.strftime('%Y-%m-%d %H:%M:%S'),
                "event_end_time": end_time.strftime('%Y-%m-%d %H:%M:%S'),
                "duration_type": "short-term",
                "participants": [person_info['name']],
                "description": intro_result.get('description', ''),
                "importance": "medium",
                "is_intro": True,
            }
            intro_events.append(intro_event)
        else:
            print(f"      [FAIL] Could not generate intro for {person_info['name']}")

    # Renumber: intros first, then the original children
    all_children = intro_events + children
    for idx, child in enumerate(all_children):
        child['sub_event_id'] = f"{parent_event_id}_{idx + 1}"

    return all_children, cumulative_cost


def process_one_uuid(record: Dict, existing_result: Optional[Dict],
                     model: str) -> Optional[Dict]:
    """Process all long-term/mid-term events for a single uuid."""
    uuid = record['uuid']
    set_log_context(uuid=uuid, stage="stage4_5_sub_events")

    basic = record.get('Basic_Profile', {})
    protagonist_name = basic.get('name', f'uid{uuid}')
    nationality = basic.get('nationality', 'Chinese')
    is_chinese = (nationality == 'Chinese')
    init_state = record.get('Init_State', {})
    protagonist_brief = (
        f"{basic.get('gender', '')}，{basic.get('birth_date', '')}，"
        if is_chinese else
        f"{basic.get('gender', '')}, {basic.get('birth_date', '')}, "
    ) + (
        f"{init_state.get('career', '')}，{init_state.get('location', '')}"
        if is_chinese else
        f"{init_state.get('career', '')}, {init_state.get('location', '')}"
    )

    # Available people: all names from social_relationships + Social_Graph
    social_rels = init_state.get('social_relationships', {})
    social_graph = record.get('Social_Graph', {})
    available_people = set(social_rels.keys())
    for category in social_graph.values():
        if isinstance(category, list):
            for person in category:
                if isinstance(person, dict) and 'name' in person:
                    available_people.add(person['name'])
    available_people = sorted(available_people)

    events = record.get('Events', [])
    target_events = [
        e for e in events
        if e.get('duration_type') in ('long-term', 'mid-term')
    ]
    # Sort by start time so the "already introduced" tracking advances along the timeline
    target_events.sort(key=lambda e: e.get('event_start_time', ''))

    print(f"  uuid={uuid}: {len(target_events)} events to split "
          f"({sum(1 for e in target_events if e.get('duration_type')=='long-term')} long + "
          f"{sum(1 for e in target_events if e.get('duration_type')=='mid-term')} mid)")

    # Check existing results
    existing_ids = set()
    if existing_result and 'sub_events' in existing_result:
        existing_ids = {se['parent_event_id'] for se in existing_result['sub_events']}

    sub_events = list(existing_result.get('sub_events', [])) if existing_result else []
    cumulative_cost = None

    # Track already-introduced people (only tracked across mid/long events)
    introduced_people = set()

    for event in target_events:
        eid = event['event_id']
        if eid in existing_ids:
            print(f"    [Skip] event_{eid}: already split")
            # Already-existing events still need their participants tracked
            for se in sub_events:
                if se['parent_event_id'] == eid:
                    for child in se.get('children', []):
                        for p in child.get('participants', []):
                            introduced_people.add(p)
            continue

        print(f"    Splitting event_{eid}: {event.get('event_name')} ({event.get('duration_type')})")

        children, cost = split_one_event(
            protagonist_name=protagonist_name,
            protagonist_brief=protagonist_brief,
            event=event,
            available_people=available_people,
            model=model,
            is_chinese=is_chinese,
        )
        cumulative_cost = calculate_cumulative_cost(cumulative_cost, cost)

        if children:
            # Check for newly appearing people (in social_relationships but not yet introduced)
            event_participants = set()
            for p in event.get('participants', []):
                name = p if isinstance(p, str) else p.get('name', '')
                if name:
                    event_participants.add(name)
            # Also collect participants from the sub-events
            for child in children:
                for p in child.get('participants', []):
                    event_participants.add(p)

            new_people = []
            for name in event_participants:
                if name in social_rels and name not in introduced_people:
                    rel_info = social_rels[name]
                    new_people.append({
                        'name': name,
                        'relationship_type': rel_info.get('relationship_type', '认识的人'),
                        'description': rel_info.get('description', ''),
                    })

            if new_people:
                print(f"    [Intro] {len(new_people)} new people: {[p['name'] for p in new_people]}")
                children, intro_cost = insert_introduction_sub_events(
                    children=children,
                    new_people=new_people,
                    parent_event=event,
                    protagonist_name=protagonist_name,
                    protagonist_brief=protagonist_brief,
                    model=model,
                    is_chinese=is_chinese,
                )
                cumulative_cost = calculate_cumulative_cost(cumulative_cost, intro_cost)

            # Mark all participants as introduced
            introduced_people.update(event_participants)

            sub_event_entry = {
                "parent_event_id": eid,
                "parent_event_name": event.get('event_name', ''),
                "parent_duration_type": event.get('duration_type', ''),
                "parent_time_range": f"{event.get('event_start_time', '')} ~ {event.get('event_end_time', '')}",
                "children": children,
            }
            sub_events.append(sub_event_entry)
            print(f"    [OK] event_{eid}: {len(children)} sub-events"
                  f" (incl. {len(new_people)} intros)" if new_people else
                  f"    [OK] event_{eid}: {len(children)} sub-events")
        else:
            print(f"    [FAIL] event_{eid}: no sub-events generated")

    # Emit through the SubEvent contract (P1-2): the declared field order matches
    # the prior literal dict, so the serialized record stays stable.
    output_record = SubEvent(
        uuid=uuid,
        sub_events=sub_events,
        cost_info=cumulative_cost,
    ).to_dict()
    return output_record


class SubEventsGenerator(Generator):
    """Split each persona's long/mid-term events into chronological sub-event arcs.

    Domain generator for the old stage 4.5. The resume model here is per *event*
    (not per record), and the standalone run uses its own parallel orchestration
    in :func:`main`, so this class is a thin uniform entry point over
    :func:`process_one_uuid` for the future pipeline DAG: ``ctx`` carries the
    existing per-uuid result (for resume).
    """

    stage_label = "Stage4.5"
    stage_num = "4.5"
    index_key = "uuid"
    produces = "sub_events"

    def __init__(self, model: str) -> None:
        self.model = model

    def produce(self, record: Dict, ctx=None) -> Optional[Dict]:
        return process_one_uuid(record, ctx, self.model)


# Main

def main():
    parser = argparse.ArgumentParser(description="Stage 4.5: Split long/mid-term events into sub-events")
    parser.add_argument('--input', type=str,
                        default=os.path.join(OUTPUT_DIR, 'data', 'annual_events.jsonl'),
                        help='Input file (stage4 output)')
    parser.add_argument('--output', type=str,
                        default=os.path.join(OUTPUT_DIR, 'data', 'sub_events.jsonl'),
                        help='Output file')
    parser.add_argument('--max-workers', type=int, default=DEFAULT_WORKERS)
    parser.add_argument('--uuid-filter', type=int, default=None)
    parser.add_argument('--model', type=str, default=None)
    parser.add_argument('--force', action='store_true',
                        help='Ignore existing output and regenerate from scratch')
    args = parser.parse_args()

    print(f"[Stage 4.5] Loading input from {args.input}")
    records = read_jsonl(args.input)
    if not records:
        print("[ERROR] No records found")
        sys.exit(1)
    print(f"  Loaded {len(records)} records")

    if args.uuid_filter is not None:
        records = [r for r in records if r.get('uuid') == args.uuid_filter]
        if not records:
            print(f"[ERROR] No record for uuid={args.uuid_filter}")
            sys.exit(1)

    existing = {} if args.force else load_existing_by_uuid(args.output)
    model = args.model or get_text_llm_model(is_chinese=True)
    print(f"  Using model: {model}")

    all_results = list(existing.values())

    if args.max_workers <= 1:
        for record in records:
            uuid = record.get('uuid')
            result = process_one_uuid(record, existing.get(uuid), model)
            if result:
                found = False
                for i, r in enumerate(all_results):
                    if r['uuid'] == uuid:
                        all_results[i] = result
                        found = True
                        break
                if not found:
                    all_results.append(result)
                write_jsonl(all_results, args.output)
                print(f"  [Save] {len(all_results)} records saved")
    else:
        lock = threading.Lock()

        def _worker(record):
            uuid = record.get('uuid')
            return process_one_uuid(record, existing.get(uuid), model)

        with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            futures = {executor.submit(_worker, r): r for r in records}
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        with lock:
                            found = False
                            for i, r in enumerate(all_results):
                                if r['uuid'] == result['uuid']:
                                    all_results[i] = result
                                    found = True
                                    break
                            if not found:
                                all_results.append(result)
                            write_jsonl(all_results, args.output)
                            print(f"  [Save] {len(all_results)} records saved")
                except Exception as e:
                    record = futures[future]
                    print(f"  [ERROR] uuid={record.get('uuid')}: {e}")

    total_subs = sum(
        len(se.get('children', []))
        for r in all_results
        for se in r.get('sub_events', [])
    )
    total_parents = sum(len(r.get('sub_events', [])) for r in all_results)
    print(f"\n[Stage 4.5] Done! {len(all_results)} uuids, "
          f"{total_parents} parent events -> {total_subs} sub-events")
    print(f"  Output: {args.output}")


if __name__ == '__main__':
    main()
