"""Life-state generator (Persona LifeState / Init_State).

:class:`LifeStateGenerator` produces each persona's ``Init_State`` (the life
state as of 2025-01-01: education / location / career / preferences / health /
emotion / finance + a set of social relationships) from the persona's CSV data
and the LLM, repackaging the record as ``{uuid, Basic_Profile, Init_State}``.
It inherits the resume-safe lifecycle from
:class:`infra.base_generator.Generator`; the stage-specific parts are the running
``global_names`` registry (forbidden social names) and the post-generation
social-name de-duplication, expressed via the base-class hooks.
"""

import os
from typing import Dict, List, Optional

from backends.llm import (
    llm_request,
    calculate_cumulative_cost,
    get_text_llm_model,
    set_log_context,
)
from csv_parser import parse_csv, build_csv_context, build_preferences_summary
from core import BasicProfile
from infra.base_generator import Generator


def load_prompt(prompt_path: str) -> str:
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read()


_SURNAME_POOL = [
    '宋', '徐', '韩', '冯', '曹', '魏', '程', '苏', '叶', '卢',
    '贺', '龚', '潘', '顾', '史', '方', '邓', '武', '钱', '唐',
]
_GIVEN_POOL = [
    '昊', '晨', '睿', '泽', '皓', '帆', '峰', '洋', '凯', '博',
    '婷', '颖', '琳', '燕', '霞', '洁', '娜', '雯', '莹', '璐',
]


def _make_unique_name(existing: set) -> str:
    """Generate a unique Chinese name not in existing."""
    import itertools
    for s, g in itertools.product(_SURNAME_POOL, _GIVEN_POOL):
        candidate = s + g
        if candidate not in existing:
            return candidate
    base = _SURNAME_POOL[0] + _GIVEN_POOL[0]
    i = 2
    while f"{base}{i}" in existing:
        i += 1
    return f"{base}{i}"


def _deduplicate_social_relationships(
        social_rel: dict, global_names: set
) -> tuple:
    """Check for name conflicts with global_names, rename if needed."""
    fixed = {}
    renamed = []
    local_seen = set(global_names)
    for name, info in social_rel.items():
        if name in local_seen:
            new_name = _make_unique_name(local_seen)
            renamed.append(f"{name} -> {new_name}")
            local_seen.add(new_name)
            fixed[new_name] = info
        else:
            local_seen.add(name)
            fixed[name] = info
    return fixed, renamed


# Prompt files (relative to prompts/ directory):
#   stage2_init_state_nation.txt    – EN system prompt
#   stage2_init_state_nation_cn.txt – CN system prompt
#   stage2_extra_instruction_en.txt – EN extra instruction (with {csv_context}/{preferences_summary})
#   stage2_extra_instruction_cn.txt – CN extra instruction (with {csv_context}/{preferences_summary})


def _build_life_state_user_content(basic_profile: Dict, role_identity: str,
                                   csv_instruction: str, forbidden_str: str,
                                   is_chinese: bool, appearance: Dict) -> str:
    """Build the user message for the init-state request (pure, no I/O).

    Chinese personas get the all-Chinese template, everyone else gets the
    English template (with the appearance-constraint block when stage0
    appearance features are present).
    """
    if is_chinese:
        return f"""请为以下人物生成截至2025-01-01的初始状态信息。

人物背景：
- 姓名：{basic_profile['name']}
- 性别：{basic_profile['gender']}
- 出生日期：{basic_profile['birth_date']}
- 国籍：{basic_profile['nationality']}
- 角色身份：{role_identity.replace('_', ' ')}
- 性格特点：{basic_profile['personality_traits']}
- 人生经历：{basic_profile['life_experiences']}

{csv_instruction}
【重要】所有输出字段必须使用纯中文（health/emotion/finance的Low/Medium/High除外）。

【禁止使用的名字（已被其他人物占用）】
{forbidden_str}
social_relationships中的所有人名不得与以上名字重复。"""

    # Build appearance constraint block from stage0 data if available
    if appearance:
        appearance_block = f"""
- Appearance (MUST use these exact features in the description field):
  Ethnicity: {appearance.get('ethnicity', '')}
  Skin: {appearance.get('skin_color', '')}
  Hair: {appearance.get('hair_color', '')} {appearance.get('hair_style', '')}
  Eyes: {appearance.get('eye_color', '')}
  Face shape: {appearance.get('face_shape', '')}
  Build: {appearance.get('build', '')}
  Facial hair: {appearance.get('facial_hair', '')}
  CRITICAL: The "description" field MUST describe a {appearance.get('ethnicity', '')} person with {appearance.get('skin_color', '')}. Do NOT change the ethnicity or skin tone."""
    else:
        appearance_block = ""

    return f"""Please generate initial state information for this persona as of 2025-01-01.

Persona Background:
- Name: {basic_profile['name']}
- Gender: {basic_profile['gender']}
- Birth Date: {basic_profile['birth_date']}
- Nationality: {basic_profile['nationality']}
- Role Identity: {role_identity.replace('_', ' ')}
- Personality Traits: {basic_profile['personality_traits']}
- Life Experiences: {basic_profile['life_experiences']}{appearance_block}

{csv_instruction}
ALL output fields must be in pure English. No Chinese characters anywhere.

IMPORTANT: The following names are already used by other personas' social relationships. You MUST NOT use any of these names in social_relationships:
{forbidden_str}"""


def generate_life_state_for_person(
        persona: Dict, info_dir: str,
        base_prompt: str, cn_system_prompt: str,
        extra_instruction_en: str, extra_instruction_cn: str,
        forbidden_names: list = None) -> Dict:
    """Generate Init_State for one person using CSV data + LLM."""
    role_identity = persona.get('role_identity', '')
    csv_path = os.path.join(info_dir, role_identity, 'user_profile.csv')
    has_csv = os.path.exists(csv_path)

    if has_csv:
        csv_data = parse_csv(csv_path)
        csv_context = build_csv_context(csv_data)
        preferences_summary = build_preferences_summary(csv_data)
    else:
        csv_data = {}
        csv_context = '（无CSV数据，请根据人物背景合理生成）'
        preferences_summary = '（无CSV数据，请根据人物背景合理生成）'

    # Build the profile sub-object through the BasicProfile contract (P1-2). The
    # declared field order matches the previous literal dict, and the optional
    # 'appearance' is still appended afterward, so the record stays stable.
    basic_profile = BasicProfile(
        name=persona.get("name", ""),
        uuid=persona.get("uuid", 0),
        gender=persona.get("gender", ""),
        birth_date=persona.get("birth_date", ""),
        nationality=persona.get("nationality", ""),
        language=persona.get("language", ""),
        personality_traits=persona.get("personality_traits", ""),
        life_experiences=persona.get("life_experiences", ""),
    ).to_dict()
    # Keep the appearance field from stage0/stage1 (appearance features for foreign personas)
    if persona.get("appearance"):
        basic_profile["appearance"] = persona["appearance"]

    # ── Switch between Chinese and English prompts based on nationality ──
    nationality = basic_profile.get('nationality', '')
    is_chinese = '中国' in nationality or 'China' in nationality or 'Chinese' in nationality

    forbidden_str = '、'.join(forbidden_names) if forbidden_names else '（无）'

    if is_chinese:
        system_prompt = cn_system_prompt + "\n\n" + extra_instruction_cn.format(
            csv_context=csv_context,
            preferences_summary=preferences_summary
        )
        csv_instruction = ("请根据以上背景和系统提示词中的真实CSV数据生成初始状态信息。\n"
                           "education、career、location、preferences必须基于CSV数据。") if has_csv else \
                          "请根据以上人物背景合理生成初始状态信息（无CSV数据，所有字段由你合理推断）。"
    else:
        system_prompt = base_prompt + "\n\n" + extra_instruction_en.format(
            csv_context=csv_context,
            preferences_summary=preferences_summary
        )
        csv_instruction = ("Please generate realistic initial state information based on this background and the real CSV data provided in the system prompt.\n"
                           "Make sure education, career, location, preferences are grounded in the CSV data.") if has_csv else \
                          "Please generate realistic initial state information based on this persona background (no CSV data available, infer all fields reasonably)."

    # Build the user message (all-Chinese for Chinese personas; English otherwise).
    user_content = _build_life_state_user_content(
        basic_profile, role_identity, csv_instruction, forbidden_str,
        is_chinese, persona.get('appearance', {}))

    response, cost_info = llm_request(
        system_prompt,
        user_content,
        model=get_text_llm_model(is_chinese),
        return_parsed_json=True,
        json_markers=[]
    )

    cost_info = calculate_cumulative_cost(None, cost_info)
    if cost_info and 'cumulative' in cost_info:
        cum = cost_info['cumulative']
        print(f"  [Cost] Input: {cum.get('input_tokens', 'N/A')}, "
              f"Output: {cum.get('output_tokens', 'N/A')}, "
              f"Cost: ${cum.get('total_cost_usd', 'N/A')}")

    if 'Init_State' in response:
        init_state = response['Init_State']
    else:
        init_state = response

    return {
        "uuid": persona.get("uuid", 0),
        "Basic_Profile": basic_profile,
        "Init_State": init_state,
    }


class LifeStateGenerator(Generator):
    """Generate ``Init_State`` per persona, with cross-record social-name dedup.

    The resume-safe iterate / skip-done / save-incrementally / isolate-errors
    lifecycle is inherited from :class:`infra.base_generator.Generator`. The
    stage-specific parts are the running ``global_names`` registry (forbidden
    names shown in the log line, passed into generation, and grown after each
    record) and the post-generation de-duplication — all expressed via the
    base-class hooks.
    """

    stage_label = "Stage2"
    stage_num = 2
    index_key = "uuid"
    produces = "life_state"

    def __init__(self, info_dir: str, base_prompt: str, cn_system_prompt: str,
                 extra_instruction_en: str, extra_instruction_cn: str) -> None:
        self.info_dir = info_dir
        self.base_prompt = base_prompt
        self.cn_system_prompt = cn_system_prompt
        self.extra_instruction_en = extra_instruction_en
        self.extra_instruction_cn = extra_instruction_cn
        self.global_names: set = set()  # social_relationships names across all personas

    def set_context(self, record: Dict, index: int) -> None:
        uid = record.get('uuid')
        set_log_context(uuid=uid if uid is not None else index, stage="stage2_init_states")

    def format_skip_line(self, record: Dict, key, index: int, total: int) -> str:
        role = record.get('role_identity', 'unknown')
        return f"[Stage2] [{index + 1}/{total}] uid={key} ({role}): SKIP (checkpoint)"

    def format_generating_line(self, record: Dict, key, index: int, total: int) -> str:
        role = record.get('role_identity', 'unknown')
        return (f"\n[Stage2] [{index + 1}/{total}] uid={key} ({role}): generating... "
                f"(forbidden: {len(self.global_names)} names)")

    def produce(self, record: Dict, ctx=None) -> Dict:
        return generate_life_state_for_person(
            record, self.info_dir, self.base_prompt, self.cn_system_prompt,
            self.extra_instruction_en, self.extra_instruction_cn,
            forbidden_names=sorted(self.global_names))

    def after_success(self, record: Dict, result: Dict) -> None:
        role = record.get('role_identity', 'unknown')
        init_state = result.get('Init_State', {})
        social_rel = init_state.get('social_relationships', {}) or {}
        fixed_rel, renamed = _deduplicate_social_relationships(social_rel, self.global_names)
        if renamed:
            print(f"[Stage2] DEDUP {role}: renamed {renamed}")
            init_state['social_relationships'] = fixed_rel
        for name in (init_state.get('social_relationships', {}) or {}).keys():
            if name:
                self.global_names.add(name)

    def describe_result(self, record: Dict, result: Dict) -> str:
        role = record.get('role_identity', 'unknown')
        init_state = result.get('Init_State', {})
        return (f"[Stage2] OK: {role} -> edu={init_state.get('education', 'N/A')}, "
                f"career={init_state.get('career', 'N/A')}")


# Backward-compatible alias for the old class name in ``stage2_init_states``.
Stage2InitStates = LifeStateGenerator


def generate_life_states(stage1_records: List[Dict], info_dir: str, prompts_dir: str,
                    existing: Optional[Dict[str, Dict]] = None,
                    save_callback=None) -> List[Dict]:
    """
    Generate stage2 Init_States for all persons, with checkpoint support.

    Thin adapter over :class:`LifeStateGenerator`: load prompts, seed the
    social-name registry from already-done records, then run the shared
    lifecycle. Public signature unchanged, so ``main.py`` is untouched.

    Args:
        existing: Dict of uuid -> existing record (for checkpoint/resume)
        save_callback: Optional function(records) called after each person for incremental save
    """
    existing = existing or {}
    # Prompt variants: the base/_en files drive non-Chinese personas; the _cn
    # files keep the original Chinese instructions for Chinese personas.
    base_prompt = load_prompt(os.path.join(prompts_dir, 'stage2_init_state_nation.txt'))
    cn_system_prompt = load_prompt(os.path.join(prompts_dir, 'stage2_init_state_nation_cn.txt'))
    extra_instruction_en = load_prompt(os.path.join(prompts_dir, 'stage2_extra_instruction_en.txt'))
    extra_instruction_cn = load_prompt(os.path.join(prompts_dir, 'stage2_extra_instruction_cn.txt'))

    generator = LifeStateGenerator(info_dir, base_prompt, cn_system_prompt,
                                   extra_instruction_en, extra_instruction_cn)
    # Pre-fill names from already-done roles so the first new record sees them.
    for rec in existing.values():
        for name in (rec.get('Init_State', {}).get('social_relationships', {}) or {}).keys():
            if name:
                generator.global_names.add(name)

    return generator.process_all(stage1_records, existing=existing, save_callback=save_callback)
