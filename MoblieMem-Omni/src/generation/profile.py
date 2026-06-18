"""Profile generator (Persona Identity).

:class:`ProfileGenerator` produces each persona's identity profile (name,
gender, birth date, nationality, language, personality, life experiences) from
the persona's CSV data and the LLM, emitting a :class:`core.Persona` record per
person. The standalone batch entry :func:`generate_stage1` keeps its
role-keyed checkpoint + cross-person used-name accumulation.
"""

import os
import traceback
import random
from typing import Dict, List, Optional

from backends.llm import llm_request, calculate_cumulative_cost, get_text_llm_model, set_log_context
from csv_parser import parse_csv, extract_gender, extract_birth_date, build_csv_context, extract_csv_field
from core import Persona
from infra.base_generator import Generator


def build_stage1_system_prompt(nationality: str) -> str:
    """Build stage1 system prompt based on nationality."""
    if nationality == "Chinese":
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
    else:
        return """You are a professional data scientist. Given Chinese user profile data, generate a persona's basic information in English.

Your output must be a valid JSON object with exactly these fields:
- "name": A realistic name appropriate for the persona's nationality:
  * American/British/Canadian/Australian: Western name (given name first, surname last, e.g., "John Smith")
  **IMPORTANT**: Names must be diverse. Avoid repeated names across different personas. Use different surnames and given names.
- "personality_traits": A paragraph (2-4 sentences) describing personality traits in English, faithfully based on the provided profile data. Use first person ("I", "my", "me"). The entire text must be in pure English, NO Chinese characters or pinyin.
- "life_experiences": A paragraph (2-4 sentences) describing key life experiences in English, faithfully based on the provided education, career, and basic info. Use first person ("I", "my", "me"). The entire text must be in pure English, NO Chinese characters or pinyin.

**CRITICAL LANGUAGE RULES FOR NON-CHINESE PERSONAS:**
1. The entire text must be in pure English. DO NOT insert any Chinese characters or pinyin into English sentences.
2. If mentioning Chinese brands, apps, or games, use English translations or descriptions. Example: Use "WeChat" not "微信", "Honor of Kings" not "王者荣耀".
3. Absolutely NO mixing of Chinese and English within the same text field.

The JSON must be wrapped in a ```json``` code block. Only output the JSON, no extra text."""


def generate_stage1_for_person(uuid: int, role_identity: str, info_dir: str,
                               used_names: Optional[List[str]] = None) -> Dict:
    """Generate stage1 Basic_Profile for one person using CSV data + LLM."""
    csv_path = os.path.join(info_dir, role_identity, 'user_profile.csv')
    csv_data = parse_csv(csv_path)

    # Inferred from the basic_info text (not a direct field, but text parsing)
    gender = extract_gender(csv_data)
    birth_date = extract_birth_date(csv_data)

    # Assign nationality: 1/3 Chinese, 2/3 foreign (English-speaking countries)
    # Use uuid as the seed to guarantee a deterministic distribution
    random.seed(uuid)

    # The first 3 uuids (0,1,2) are assigned as Chinese, the rest as English-speaking countries
    if uuid in [0, 1, 2,3,4,5,6,7,8,9]:
        # Chinese
        nationality = "Chinese"
        language = "Chinese"
    else:
        # English-speaking country distribution: USA, UK, Canada, Australia
        english_countries = [
            {"nationality": "American", "language": "English"},
            {"nationality": "British", "language": "English"},
            {"nationality": "Canadian", "language": "English"},
            {"nationality": "Australian", "language": "English"}
        ]
        # Select an English-speaking country based on uuid (deterministic)
        selected = english_countries[uuid % len(english_countries)]
        nationality = selected["nationality"]
        language = selected["language"]

    # Build LLM context from CSV
    csv_context = build_csv_context(csv_data)
    personality_hint = extract_csv_field(csv_data, 'personality')
    education_hint = extract_csv_field(csv_data, 'education')
    career_hint = extract_csv_field(csv_data, 'career')
    basic_hint = extract_csv_field(csv_data, 'basic_info', 'baiscInfo')

    used_names = used_names or []
    already_used_cn = "、".join(used_names) if used_names else "（无）"
    already_used_en = ", ".join(used_names) if used_names else "(none)"

    if nationality == "Chinese":
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
    else:
        user_content = f"""Based on the following Chinese user profile data, generate persona information in English.

Role/Identity: {role_identity.replace('_', ' ')}
Nationality: {nationality}
Language: {language}
Detected Gender: {gender}
Approximate Birth Date: {birth_date}

⚠️ Already used names — MUST NOT reuse any of these: {already_used_en}

Key CSV Fields (Chinese):
- basic_info: {basic_hint}
- personality: {personality_hint if personality_hint else 'N/A'}
- education: {education_hint if education_hint else 'N/A'}
- career: {career_hint if career_hint else 'N/A'}

Full User Profile Data (Chinese):
{csv_context}

Please generate name, personality_traits, and life_experiences based on this data.

IMPORTANT INSTRUCTIONS:
1. NAME: Generate a name appropriate for {nationality} nationality:
   - If {nationality} is American/British/Canadian/Australian: Use Western name (given name first, surname last, e.g., "John Smith")
   - **Name must be diverse**: Ensure different people have different names.
   - **Avoid repeated names**: Among the 10 personas, foreign personas must have different names. Avoid using common repeated names like "James", "Emily", "Michael", "John", "Emma", etc.
   - **[MANDATORY] Already taken names (absolutely forbidden to reuse)**: {already_used_en}
   - **Diverse surnames**: Use different Western surnames such as Smith, Johnson, Williams, Brown, Jones, Davis, Miller, Wilson, Moore, Taylor, Anderson, etc.

2. PERSONALITY_TRAITS: Describe personality traits in English, based on the CSV data. Use first person ("I", "my", "me").
   - **The entire text must be in pure English, DO NOT insert any Chinese characters or pinyin.**
   - **If mentioning Chinese brands, apps, or games, use English translations or descriptions. Example: Use "WeChat" not "微信", "Honor of Kings" not "王者荣耀".**

3. LIFE_EXPERIENCES: Describe key life experiences in English, based on CSV education/career/basic_info.
   - **The entire text must be in pure English, DO NOT insert any Chinese characters or pinyin.**
   - Consider the persona's {nationality} background. For example:
     - If {nationality} is not Chinese but the CSV describes a job in China: the persona could be a foreigner working/living in China
   - Make the experiences realistic for the nationality and cultural background.

**Language Consistency Requirements:**
- All text fields must be in pure English
- Do not insert Chinese words or pinyin into English sentences
- Absolutely NO mixing of Chinese and English"""

    system_prompt = build_stage1_system_prompt(nationality)
    response, cost_info = llm_request(
        system_prompt,
        user_content,
        model=get_text_llm_model(nationality == 'Chinese'),
        return_parsed_json=True,
        json_markers=[]
    )

    cost_info = calculate_cumulative_cost(None, cost_info)
    if cost_info and 'cumulative' in cost_info:
        cum = cost_info['cumulative']
        print(f"  [Cost] Input: {cum.get('input_tokens', 'N/A')}, "
              f"Output: {cum.get('output_tokens', 'N/A')}, "
              f"Cost: ${cum.get('total_cost_usd', 'N/A')}")

    # Emit the record through the Persona contract (P1-2). to_dict() writes the
    # declared fields in their declared order — identical to the previous literal
    # dict — so the serialized record stays byte-for-byte the same, and callers
    # still receive a plain dict.
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


class ProfileGenerator(Generator):
    """Generate each persona's identity ``Persona`` profile from CSV + LLM.

    Domain generator for the old stage 1. The standalone batch run uses
    :func:`generate_stage1` (role-keyed checkpoint + cross-person used-name
    accumulation); this class is a thin uniform per-person entry point for the
    future pipeline DAG, where ``ctx`` carries the running ``used_names`` list.
    """

    stage_label = "Stage1"
    stage_num = 1
    index_key = "role_identity"
    produces = "profile"

    def __init__(self, info_dir: str) -> None:
        self.info_dir = info_dir

    def produce(self, record: Dict, ctx=None) -> Dict:
        used_names = ctx if ctx is not None else []
        return generate_stage1_for_person(
            record["uuid"], record["role_identity"], self.info_dir, used_names=used_names)


def generate_stage1(person_folders: List[str], info_dir: str, prompts_dir: str,
                    existing: Optional[Dict[str, Dict]] = None,
                    save_callback=None, uuid_filter: Optional[set] = None) -> List[Dict]:
    """
    Generate stage1 profiles for all persons, with checkpoint support.

    Args:
        person_folders: List of subfolder names under information/
        info_dir: Path to information/ directory
        prompts_dir: Path to prompts/ directory
        existing: Dict of role_identity -> existing record (for checkpoint/resume)
        save_callback: Optional function(records) called after each person for incremental save
        uuid_filter: Optional set of uuids (folder indices) to restrict generation to

    Returns:
        List of stage1 profile dicts (complete, including existing + new)
    """
    existing = existing or {}
    records = []

    skipped = sum(1 for f in person_folders if f in existing)
    if skipped > 0:
        print(f"[Stage1] Checkpoint: {skipped} already done, "
              f"{len(person_folders) - skipped} remaining")

    used_names: List[str] = [r["name"] for r in existing.values() if "name" in r]

    for i, folder_name in enumerate(person_folders):
        if uuid_filter is not None and i not in uuid_filter:
            continue
        if folder_name in existing:
            records.append(existing[folder_name])
            print(f"[Stage1] [{i + 1}/{len(person_folders)}] {folder_name}: SKIP (checkpoint)")
            continue

        set_log_context(uuid=i, stage="stage1_profiles")
        print(f"\n[Stage1] [{i + 1}/{len(person_folders)}] {folder_name}: generating...")
        try:
            record = generate_stage1_for_person(i, folder_name, info_dir, used_names=used_names)
            used_names.append(record["name"])  # accumulate for next iteration
            records.append(record)
            print(f"[Stage1] OK: {folder_name} -> name={record['name']}, "
                  f"gender={record['gender']}, birth={record['birth_date']}")
            # Incremental save after each successful generation
            if save_callback:
                save_callback(records)
        except Exception as e:
            print(f"[Stage1] ERROR processing {folder_name}: {e}")
            traceback.print_exc()

    return records
