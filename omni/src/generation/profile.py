"""Profile generator (Persona Identity) — the legacy CSV path.

:func:`generate_profiles` produces each persona's identity profile (name,
gender, birth date, nationality, language, personality, life experiences) from
the persona's CSV data and the LLM, emitting a :class:`core.Persona` record per
person, with a role-keyed checkpoint and cross-person used-name accumulation.

This path only serves personas that have a CSV folder under ``info_dir`` —
historically uuid 0-9, all Chinese (the CSV profiles are Chinese-language
data). New personas are seeded from specs in :mod:`generation.persona_seeds`,
which is the primary generation path going forward; this module is retained
for the existing CSV-sourced personas.
"""

import os
import traceback
from typing import Dict, List, Optional

from backends.llm import llm_request, calculate_cumulative_cost, get_text_llm_model, set_log_context
from csv_parser import parse_csv, extract_gender, extract_birth_date, build_csv_context, extract_csv_field
from core import Persona


def build_profile_system_prompt() -> str:
    """Build the profile-node system prompt (CSV personas are Chinese-only)."""
    return """You are a professional data scientist. Given Chinese user profile data, generate a persona's basic information in Chinese.

Your output must be a valid JSON object with exactly these fields:
- "name": A realistic Chinese name in Chinese characters (surname first, given name last, e.g., "张明远"). DO NOT use Pinyin, use Chinese characters only. **IMPORTANT**: Names must be diverse. Use different Chinese surnames across different personas.
- "personality_traits": A paragraph (2-4 sentences) describing personality traits in Chinese, faithfully based on the provided profile data. Use first person ("我", "我的", "我"). The entire text must be in pure Chinese, NO English words or sentences.
- "life_experiences": A paragraph (2-4 sentences) describing key life experiences in Chinese, faithfully based on the provided education, career, and basic info. Use first person ("我", "我的", "我"). The entire text must be in pure Chinese, NO English words or sentences.

**CRITICAL LANGUAGE RULES FOR CHINESE PERSONAS:**
1. The entire text must be in pure Chinese. DO NOT write any English words or sentences.
2. If mentioning game names like "王者荣耀", write the entire sentence in Chinese, e.g., "我喜欢玩王者荣耀" NOT "I enjoy playing 王者荣耀".
3. If mentioning brand names like "WeChat", use the Chinese translation "微信" or describe it in Chinese without using English words.
4. Absolutely NO mixing of Chinese and English within the same text field.

The JSON must be wrapped in a ```json``` code block. Only output the JSON, no extra text."""


def generate_profile_for_person(uuid: int, role_identity: str, info_dir: str,
                                used_names: Optional[List[str]] = None) -> Dict:
    """Generate the Basic_Profile for one person using CSV data + LLM."""
    csv_path = os.path.join(info_dir, role_identity, 'user_profile.csv')
    csv_data = parse_csv(csv_path)

    # Inferred from the basic_info text (not a direct field, but text parsing)
    gender = extract_gender(csv_data)
    birth_date = extract_birth_date(csv_data)

    # CSV-sourced personas are all Chinese: the CSV profiles are Chinese-language
    # data. Foreign / new personas never take this path — they are seeded from
    # specs in generation.persona_seeds instead.
    nationality = "Chinese"
    language = "Chinese"

    # Build LLM context from CSV
    csv_context = build_csv_context(csv_data)
    personality_hint = extract_csv_field(csv_data, 'personality')
    education_hint = extract_csv_field(csv_data, 'education')
    career_hint = extract_csv_field(csv_data, 'career')
    basic_hint = extract_csv_field(csv_data, 'basic_info', 'baiscInfo')

    used_names = used_names or []
    already_used_cn = "、".join(used_names) if used_names else "（无）"

    user_content = f"""基于以下中文用户资料数据，生成人物信息，全部使用中文。

角色/身份: {role_identity.replace('_', ' ')}
国籍: {nationality}
语言: {language}
检测到的性别: {gender}
大致出生日期: {birth_date}

⚠️ 已使用的姓名（绝对禁止重复）: {already_used_cn}

关键CSV字段（中文）:
- basic_info: {basic_hint}
- personality: {personality_hint if personality_hint else 'N/A'}
- education: {education_hint if education_hint else 'N/A'}
- career: {career_hint if career_hint else 'N/A'}

完整的用户资料数据（中文）:
{csv_context}

请根据这些数据生成姓名、personality_traits（性格特点）和life_experiences（生活经历）。

重要指令:
1. 姓名: 为{nationality}国籍生成合适的姓名:
   - 如果是中国人: 使用中文汉字姓名（姓在前名在后，例如："张明远"）。不要使用拼音，只使用汉字。
   - **姓名必须多样化**: 确保不同人物的姓氏不同。使用常见的中国姓氏如张、王、李、刘、陈、杨、赵、黄、周、吴等。
   - **避免重复姓氏**: 10个人物中，中国人的姓氏必须各不相同。
   - **【强制】已被占用的姓名列表（绝对不能使用）**: {already_used_cn}

2. PERSONALITY_TRAITS（性格特点）: 基于CSV数据描述性格特点，使用中文。使用第一人称（"我"、"我的"、"我"）。
   - **整个文本必须使用纯中文，不要使用任何英文单词或句子。**
   - **如果提到游戏名如"王者荣耀"，整个句子用中文写，例如："我喜欢玩王者荣耀"，不要写"I enjoy playing 王者荣耀"。**
   - **如果提到品牌名如"WeChat"，使用中文翻译"微信"或用中文描述，不要使用英文单词。**

3. LIFE_EXPERIENCES（生活经历）: 基于CSV的education/career/basic_info描述关键生活经历，使用中文。
   - **整个文本必须使用纯中文，不要使用任何英文单词或句子。**
   - 考虑人物的{nationality}背景。例如:
     - 如果是中国人: 描述在中国的经历
   - 使经历符合国籍和文化背景的真实性。

**语言一致性要求：**
- 所有文本字段必须使用纯中文
- 禁止在中文句子中插入英文单词或拼音
- 绝对不要中英混合"""

    system_prompt = build_profile_system_prompt()
    response, cost_info = llm_request(
        system_prompt,
        user_content,
        model=get_text_llm_model(is_chinese=True),
        return_parsed_json=True,
    )

    cost_info = calculate_cumulative_cost(None, cost_info)
    if cost_info and 'cumulative' in cost_info:
        cum = cost_info['cumulative']
        print(f"  [Cost] Input: {cum.get('input_tokens', 'N/A')}, "
              f"Output: {cum.get('output_tokens', 'N/A')}, "
              f"Cost: ${cum.get('total_cost_usd', 'N/A')}")

    # Persona.to_dict() writes the declared fields in declared order, which is
    # the on-disk field order of the record.
    return Persona(
        uuid=uuid,
        role_identity=role_identity,
        name=response.get("name", ""),
        gender=gender,
        birth_date=birth_date,
        nationality=nationality,
        language=language,
        personality_traits=response.get("personality_traits", ""),
        life_experiences=response.get("life_experiences", ""),
    ).to_dict()


def generate_profiles(person_folders: List[str], info_dir: str,
                      existing: Optional[Dict[str, Dict]] = None,
                      save_callback=None, uuid_filter: Optional[set] = None) -> List[Dict]:
    """
    Generate identity profiles for all persons, with checkpoint support.

    Args:
        person_folders: List of subfolder names under information/
        info_dir: Path to information/ directory
        existing: Dict of role_identity -> existing record (for checkpoint/resume)
        save_callback: Optional function(records) called after each person for incremental save
        uuid_filter: Optional set of uuids (folder indices) to restrict generation to

    Returns:
        List of profile dicts (complete, including existing + new)

    Raises:
        RuntimeError: if any folder failed, after the whole batch was attempted.
            Successful records were already persisted via ``save_callback``, so
            rerunning resumes from the checkpoint.
    """
    existing = existing or {}
    records = []
    failures = []

    skipped = sum(1 for f in person_folders if f in existing)
    if skipped > 0:
        print(f"[profile] Checkpoint: {skipped} already done, "
              f"{len(person_folders) - skipped} remaining")

    used_names: List[str] = [r["name"] for r in existing.values() if "name" in r]

    for i, folder_name in enumerate(person_folders):
        if uuid_filter is not None and i not in uuid_filter:
            continue
        if folder_name in existing:
            records.append(existing[folder_name])
            print(f"[profile] [{i + 1}/{len(person_folders)}] {folder_name}: SKIP (checkpoint)")
            continue

        set_log_context(uuid=i, stage="profile")
        print(f"\n[profile] [{i + 1}/{len(person_folders)}] {folder_name}: generating...")
        try:
            record = generate_profile_for_person(i, folder_name, info_dir, used_names=used_names)
            used_names.append(record["name"])  # accumulate for next iteration
            records.append(record)
            print(f"[profile] OK: {folder_name} -> name={record['name']}, "
                  f"gender={record['gender']}, birth={record['birth_date']}")
            # Incremental save after each successful generation
            if save_callback:
                save_callback(records)
        except Exception as e:  # keep processing; reported after the loop
            print(f"[profile] ERROR processing {folder_name}: {e}")
            traceback.print_exc()
            failures.append((folder_name, f"{type(e).__name__}: {e}"))

    if failures:
        summary = "; ".join(f"{folder}: {msg}" for folder, msg in failures)
        raise RuntimeError(f"[profile] {len(failures)} folder(s) failed: {summary}")
    return records
