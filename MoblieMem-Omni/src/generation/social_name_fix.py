"""Social-name normalizer (split out of ``social_world.py``).

Detects and fixes problematic keys in the life_state node's
``social_relationships`` output (pure relationship words, surname+title,
prefixed nicknames, etc.) and rewrites the init-states JSONL file in place.
Entry points: :func:`fix_social_names` and :class:`SocialNameNormalizer`.
"""

import os
import re
import traceback
from typing import Dict, List, Set, Tuple

from backends.llm import llm_request, get_text_llm_model, set_log_context
from core.lang import is_chinese_persona
from generation.name_pools import make_unique_name as _make_unique_name
from infra.prompts import load_bilingual_prompt
from infra.store import read_jsonl, write_jsonl_atomic

RELATION_KEYWORDS = {
    '母亲', '父亲', '妈妈', '爸爸', '岳母', '岳父', '婆婆', '公公',
    '丈夫', '妻子', '老公', '老婆', '配偶',
    '儿子', '女儿', '大儿子', '小儿子', '大女儿', '小女儿',
    '哥哥', '弟弟', '姐姐', '妹妹',
    '爷爷', '奶奶', '外公', '外婆', '姑姑', '叔叔', '舅舅', '阿姨',
    '侄子', '侄女', '外甥', '外甥女',
}

# English pure relationship words (compared lowercase); conservative on purpose:
# only exact matches count, so real names are never misclassified.
RELATION_KEYWORDS_EN = {
    'mom', 'dad', 'mother', 'father', 'husband', 'wife', 'son', 'daughter',
    'brother', 'sister', 'grandma', 'grandpa', 'grandmother', 'grandfather',
    'aunt', 'uncle', 'cousin', 'roommate', 'neighbor', 'boss', 'coworker',
    'colleague', 'teammate', 'coach', 'doctor', 'teacher', 'landlord',
}

# English title-prefixed forms of address ("Coach Smith", "Dr. Lee")
TITLE_PREFIXES_EN = ('Coach ', 'Dr. ', 'Dr ', 'Mr. ', 'Mrs. ', 'Ms. ', 'Prof. ')

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
    if name.strip().lower() in RELATION_KEYWORDS_EN:
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
    # B1 (English): title + surname, e.g. "Coach Smith", "Dr. Lee"
    if name.startswith(TITLE_PREFIXES_EN):
        return 'B1'
    # B2: prefix + surname + title, such as counselor plus surname plus teacher.
    if len(name) > 4 and any(name.endswith(s) for s in TITLE_SUFFIXES):
        return 'B2'
    # B3: prefix + real name, such as roommate plus a full name.
    for prefix in NAME_PREFIXES:
        if name.startswith(prefix) and len(name) > len(prefix):
            return 'B3'
    # Legit hyphenated Western names ("Anne-Marie Smith-Jones") must be
    # recognized before the B6 hyphen-nickname rule below claims them.
    if re.match(r"^[A-Za-z][A-Za-z\s.'-]{1,40}$", name):
        return 'OK'
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
    return load_bilingual_prompt(prompts_dir, 'fix_relationship_names', is_chinese)


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
        return_parsed_json=True,
        extract_json=True,
    )

    if cost_info:
        print(f"  [Cost] Input: {cost_info.get('input_tokens', 'N/A')}, "
              f"Output: {cost_info.get('output_tokens', 'N/A')}, "
              f"Cost: ${cost_info.get('total_cost_usd', 'N/A')}")

    if isinstance(response, dict):
        return response
    print(f"  [WARN] LLM JSON not a dict: {str(response)[:200]}")
    return {}


def apply_fixes(
    social_rel: dict,
    fixes: Dict[str, str],
    global_names: Set[str],
    is_chinese: bool = True,
) -> Tuple[dict, List[str]]:
    """Apply the fixes and return (fixed_rel, changes_log).

    ``is_chinese`` picks the language of fallback names generated on conflict,
    so an English persona never receives a Chinese fallback name. Kept as the
    last parameter (default True) for positional-call compatibility.
    """
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
                fallback = _make_unique_name(taken, is_chinese=is_chinese)
                changes.append(f'"{name}" -> "{new_name}" (conflict) -> "{fallback}"')
                new_name = fallback
            else:
                changes.append(f'"{name}" -> "{new_name}"')
            global_names.add(new_name)
            fixed[new_name] = info
        else:
            fixed[name] = info

    return fixed, changes


# Main process

def fix_social_names(init_states_path: str, prompts_dir: str) -> int:
    """Read the life_state output -> detect -> regex extraction + LLM fix -> overwrite.

    Returns the total number of fixes. Raises RuntimeError at the end of the
    batch if any persona failed (successful fixes are saved first).
    """

    if not os.path.exists(init_states_path):
        print(f"[social_name_fix] File not found: {init_states_path}")
        return 0

    records = read_jsonl(init_states_path)

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
    failures: List[tuple] = []

    for rec in records:
        uuid = rec.get('uuid', '?')
        set_log_context(uuid=uuid, stage="social_name_fix")
        bp = rec.get('Basic_Profile', {})
        main_name = bp.get('name', '')
        main_gender = bp.get('gender', '')
        nationality = bp.get('nationality', '')
        is_chinese = is_chinese_persona(nationality)
        init_state = rec.get('Init_State', {})
        social_rel = init_state.get('social_relationships', {}) or {}

        problems = collect_problems(social_rel)
        if not problems:
            continue

        print(f"\n[social_name_fix] uuid={uuid} ({main_name}): found {len(problems)} problematic names: "
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
                    fixed_rel, changes = apply_fixes(
                        social_rel, fixes, global_names, is_chinese=is_chinese)
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
                failures.append((uuid, f"{type(e).__name__}: {e}"))

    if modified:
        # In-place overwrite of an upstream artifact: must be atomic so a crash
        # mid-write can never destroy the init-states file.
        write_jsonl_atomic(records, init_states_path)
        print(f"\n[social_name_fix] Saved {len(records)} records to {init_states_path}")

    if failures:
        # Successful fixes are already saved above; report the rest loudly
        # instead of returning a count that hides them.
        summary = "; ".join(f"uuid={uid}: {msg}" for uid, msg in failures)
        raise RuntimeError(
            f"[social_name_fix] social-name fix failed for {len(failures)} persona(s) "
            f"(successful fixes were saved): {summary}")

    return total_fixes


class SocialNameNormalizer:
    """Fix problematic social_relationships keys produced by the life_state node.

    Not a per-record generator (it rewrites the init-states file in place via
    :func:`fix_social_names`), so it does not inherit ``infra.base_generator``.
    The class is kept because ``social_world`` re-exports it as public surface;
    the batch entry is :meth:`run_file`.
    """

    def run_file(self, init_states_path: str, prompts_dir: str) -> int:
        return fix_social_names(init_states_path, prompts_dir)
