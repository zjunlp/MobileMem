"""Important-dates generator (Timeline / ImportantDates).

:class:`ImportantDatesGenerator` produces the ``Important_Dates`` block
(festivals / memorial_dates / event_milestones for 2025) for each persona:
one upstream record in, the same record plus ``Important_Dates`` out. It
inherits the resume-safe iterate / skip-done / save-incrementally /
isolate-errors lifecycle from :class:`infra.base_generator.Generator`.
"""

import json
import logging
import os
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import config
from backends.llm import (
    llm_request,
    calculate_cumulative_cost,
    get_text_llm_model,
    set_log_context,
)
from infra.base_generator import Generator
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
    before_sleep_log,
)

logger = logging.getLogger(__name__)

# Retry configuration (centralized in config)
RETRY_TIMES = config.RETRY_TIMES
WAIT_TIME_LOWER = config.WAIT_TIME_LOWER
WAIT_TIME_UPPER = config.WAIT_TIME_UPPER

# The Chinese system prompt is loaded from an external file (prompts/important_dates_zh.txt)


def load_prompt(prompt_path: str) -> str:
    """Load prompt file from specified path"""
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        raise FileNotFoundError(f"Failed to load prompt file {prompt_path}: {e}:{traceback.format_exc()}")


def _build_dates_user_content(basic_profile: Dict, init_state: Dict, is_chinese: bool) -> str:
    """Build the user message for the important-dates request (pure, no I/O).

    Chinese personas get the all-Chinese template (to prevent language drift),
    everyone else gets the English template.
    """
    nationality = basic_profile.get('nationality', 'Unknown')

    if is_chinese:
        return f"""请为以下人物生成2025年度的重要日期。

【输出语言要求】所有 day 字段必须使用纯中文，严禁出现任何英文单词。节日用中文名（如"春节""清明节"），人名用中文，里程碑描述也必须全中文。

人物背景：
- 姓名：{basic_profile.get('name', '未知')}
- 性别：{basic_profile.get('gender', '未知')}
- 出生日期：{basic_profile.get('birth_date', '未知')}
- 国籍：{nationality}
- 性格特点：{basic_profile.get('personality_traits', '未知')}
- 生活经历：{basic_profile.get('life_experiences', '未知')}

初始状态（2025-01-01）：
- 描述：{init_state.get('description', '未知')}
- 教育背景：{init_state.get('education', '未知')}
- 所在地：{init_state.get('location', '未知')}
- 职业：{init_state.get('career', '未知')}
- 偏好：{json.dumps(init_state.get('preferences', {}), ensure_ascii=False)}
- 社交关系：{json.dumps(init_state.get('social_relationships', {}), ensure_ascii=False)}
- 健康：{init_state.get('health', '未知')}
- 情绪：{init_state.get('emotion', '未知')}
- 经济：{init_state.get('finance', '未知')}

请根据以上信息生成完整的2025年重要日期。再次强调：所有 day 字段必须是纯中文，不允许出现任何英文。
"""

    return f"""Please generate important dates for this persona for the year 2025.

**Language requirement**: ALL `day` values must be in pure English. Do NOT use any Chinese characters.

Persona Background:
- Name: {basic_profile.get('name', 'Unknown')}
- Gender: {basic_profile.get('gender', 'Unknown')}
- Birth Date: {basic_profile.get('birth_date', 'Unknown')}
- Nationality: {nationality}
- Preferred Output Language: English
- Personality Traits: {basic_profile.get('personality_traits', 'Unknown')}
- Life Experiences: {basic_profile.get('life_experiences', 'Unknown')}

Initial State (as of 2025-01-01):
- Description: {init_state.get('description', 'Unknown')}
- Education: {init_state.get('education', 'Unknown')}
- Location: {init_state.get('location', 'Unknown')}
- Career: {init_state.get('career', 'Unknown')}
- Preferences: {json.dumps(init_state.get('preferences', {}), ensure_ascii=False)}
- Social Relationships: {json.dumps(init_state.get('social_relationships', {}), ensure_ascii=False)}
- Health: {init_state.get('health', 'Unknown')}
- Emotion: {init_state.get('emotion', 'Unknown')}
- Finance: {init_state.get('finance', 'Unknown')}

Please generate comprehensive important dates for the year 2025 based on this information.
Reminder: ALL `day` values must be pure English, no Chinese characters.
"""


@retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_random_exponential(min=WAIT_TIME_LOWER, max=WAIT_TIME_UPPER),
    stop=stop_after_attempt(RETRY_TIMES),
    reraise=True,
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
def generate_important_dates_with_llm(persona_record: Dict, prompt: str, cn_prompt: str = "") -> Tuple[Dict, Dict]:
    """
    Generate important dates for a persona using LLM

    Args:
        persona_record: Complete persona record from stage2 (with Basic_Profile and Init_State)
        prompt: The system prompt to use

    Returns:
        Tuple of (important_dates_dict, cost_info)
    """
    api_key = config.OPENAI_API_KEY

    if not api_key:
        print("[ERROR] OpenAI API key not set in environment variables")
        raise ValueError("OpenAI API key is required")

    try:
        persona_uuid = persona_record.get('uuid', 'unknown')
        print(f"[INFO] Generating important dates for persona {persona_uuid}...")

        # Extract background and initial state
        basic_profile = persona_record.get('Basic_Profile', {})
        init_state = persona_record.get('Init_State', {})
        persona_language = basic_profile.get('language', 'Unknown')
        nationality = basic_profile.get('nationality', 'Unknown')

        is_chinese = (persona_language == 'Chinese' or nationality == 'Chinese')

        # Chinese personas use the pure-Chinese system prompt; non-Chinese personas use the English prompt passed in
        system_prompt = cn_prompt if (is_chinese and cn_prompt) else prompt

        # Build the user message (all-Chinese for Chinese personas to prevent language drift)
        user_content = _build_dates_user_content(basic_profile, init_state, is_chinese)

        print(f"[INFO] Sending request for persona {persona_uuid}")
        response, cost_info = llm_request(
            system_prompt,
            user_content,
            model=get_text_llm_model(is_chinese),
            return_parsed_json=True,
            extract_json=True,
            json_markers=[]
        )

        cost_info = calculate_cumulative_cost(None, cost_info)

        print(f"[INFO] Successfully generated important dates for persona {persona_uuid}")

        if cost_info and 'cumulative' in cost_info:
            cum_cost = cost_info['cumulative']
            print(
                f"[INFO] Token usage - Input: {cum_cost.get('input_tokens', 'N/A')}, "
                f"Output: {cum_cost.get('output_tokens', 'N/A')}, "
                f"Cost: ${cum_cost.get('total_cost_usd', 'N/A')}"
            )

        # Extract important dates from response
        important_dates = extract_important_dates_from_response(response)

        if not important_dates:
            raise ValueError(f"Failed to extract important dates from response for persona {persona_uuid}")

        # Validate and normalize important dates
        normalized_dates = validate_and_normalize_dates(important_dates, persona_uuid)

        return normalized_dates, cost_info

    except Exception as e:
        print(f"[ERROR] Important dates generation failed for persona {persona_record.get('uuid', 'unknown')}: {e}")
        print("[ERROR] Full traceback:")
        traceback.print_exc()
        raise


def extract_important_dates_from_response(parsed_data) -> Dict:
    """
    Extract important dates from LLM response

    Args:
        parsed_data: Parsed data from LLM

    Returns:
        Dictionary containing important dates
    """
    try:
        # Check if response has "Important_Dates" key
        if isinstance(parsed_data, dict) and 'Important_Dates' in parsed_data:
            important_dates = parsed_data['Important_Dates']

            # Ensure it has the required structure
            if not isinstance(important_dates, dict):
                print("[WARNING] Important_Dates is not a dictionary")
                return {}

            # Check for required categories
            required_categories = ['festivals', 'memorial_dates', 'event_milestones']
            for category in required_categories:
                if category not in important_dates:
                    print(f"[WARNING] Missing category in Important_Dates: {category}")
                    important_dates[category] = []
                elif not isinstance(important_dates[category], list):
                    print(f"[WARNING] {category} is not a list, converting")
                    important_dates[category] = []

            return important_dates
        else:
            print("[WARNING] No 'Important_Dates' found in response")
            # Return empty structure
            return {
                'festivals': [],
                'memorial_dates': [],
                'event_milestones': []
            }

    except Exception as e:
        print(f"[WARNING] Error extracting important dates from response: {e}")
        # Return empty structure
        return {
            'festivals': [],
            'memorial_dates': [],
            'event_milestones': []
        }


def validate_and_normalize_dates(important_dates: Dict, persona_uuid: int) -> Dict:
    """
    Validate the important dates structure

    Args:
        important_dates: Dictionary containing important dates
        persona_uuid: UUID of the persona for error reporting

    Returns:
        Validated and normalized important dates dictionary
    """
    try:
        normalized_dates = {
            'festivals': [],
            'memorial_dates': [],
            'event_milestones': []
        }

        # Validate festivals
        if 'festivals' in important_dates and isinstance(important_dates['festivals'], list):
            for i, festival in enumerate(important_dates['festivals']):
                if isinstance(festival, dict) and 'day' in festival and 'date' in festival:
                    # Validate date format
                    try:
                        datetime.strptime(festival['date'], '%Y-%m-%d')
                        normalized_dates['festivals'].append(festival)
                    except ValueError:
                        print(
                            f"[WARNING] Persona {persona_uuid}: Festival {i} has invalid date format: {festival.get('date')}")
                else:
                    print(f"[WARNING] Persona {persona_uuid}: Festival {i} missing required fields or not a dictionary")

        # Validate memorial_dates
        if 'memorial_dates' in important_dates and isinstance(important_dates['memorial_dates'], list):
            for i, memorial in enumerate(important_dates['memorial_dates']):
                if isinstance(memorial, dict) and 'day' in memorial and 'date' in memorial:
                    # Validate date format
                    try:
                        datetime.strptime(memorial['date'], '%Y-%m-%d')
                        normalized_dates['memorial_dates'].append(memorial)
                    except ValueError:
                        print(
                            f"[WARNING] Persona {persona_uuid}: Memorial date {i} has invalid date format: {memorial.get('date')}")
                else:
                    print(
                        f"[WARNING] Persona {persona_uuid}: Memorial date {i} missing required fields or not a dictionary")

        # Validate event_milestones
        if 'event_milestones' in important_dates and isinstance(important_dates['event_milestones'], list):
            for i, milestone in enumerate(important_dates['event_milestones']):
                if isinstance(milestone,
                              dict) and 'day' in milestone and 'date' in milestone:
                    # Validate date format
                    try:
                        datetime.strptime(milestone['date'], '%Y-%m-%d')
                        normalized_dates['event_milestones'].append(milestone)
                    except ValueError:
                        print(
                            f"[WARNING] Persona {persona_uuid}: Event milestone {i} has invalid date format: {milestone.get('date')}")
                else:
                    print(
                        f"[WARNING] Persona {persona_uuid}: Event milestone {i} missing required fields or not a dictionary")

        # Log summary
        print(f"[INFO] Persona {persona_uuid}: Validated dates - {len(normalized_dates['festivals'])} festivals, "
              f"{len(normalized_dates['memorial_dates'])} memorial dates, "
              f"{len(normalized_dates['event_milestones'])} event milestones")

        return normalized_dates

    except Exception as e:
        print(f"[ERROR] Persona {persona_uuid}: Validation error for important dates: {e}")
        # Return empty structure
        return {
            'festivals': [],
            'memorial_dates': [],
            'event_milestones': []
        }


def process_single_persona(persona_record: Dict, prompt: str, cn_prompt: str = "") -> Dict:
    """Process single persona to generate important dates"""
    try:
        # Generate important dates using LLM (includes validation)
        important_dates, cost_info = generate_important_dates_with_llm(persona_record, prompt, cn_prompt)

        # Create output record with UUID and Important_Dates
        output_record = persona_record.copy()
        output_record["Important_Dates"] = important_dates

        return output_record

    except Exception as e:
        print(f"[ERROR] Failed to process persona {persona_record.get('uuid', 0)}: {e}")
        raise


class ImportantDatesGenerator(Generator):
    """Generate ``Important_Dates`` for each persona (one upstream record in,
    one enriched record out)."""

    stage_label = "Stage3"
    stage_num = 3
    index_key = "uuid"
    produces = "important_dates"

    def __init__(self, prompt: str, cn_prompt: str = "") -> None:
        self.prompt = prompt
        self.cn_prompt = cn_prompt

    def set_context(self, record: Dict, index: int) -> None:
        uid = record.get('uuid')
        set_log_context(uuid=uid if uid is not None else index, stage="stage3_dates")

    def produce(self, record: Dict, ctx: Any = None) -> Dict:
        return process_single_persona(record, self.prompt, self.cn_prompt)

    def describe_result(self, record: Dict, result: Dict) -> str:
        uid = record.get('uuid')
        dates = result.get('Important_Dates', {})
        return (f"[Stage3] OK: uid={uid} -> {len(dates.get('festivals', []))} festivals, "
                f"{len(dates.get('memorial_dates', []))} memorials, "
                f"{len(dates.get('event_milestones', []))} milestones")


# Backward-compatible alias for the old class name in ``stage3_dates``.
Stage3Dates = ImportantDatesGenerator


def generate_important_dates(stage2_records: List[Dict], prompts_dir: str,
                    existing: Optional[Dict[str, Dict]] = None,
                    save_callback=None) -> List[Dict]:
    """
    Generate important dates for all persons, with checkpoint support.

    A stable public adapter used by the record pipeline (``main.py``).

    Args:
        existing: Dict of uuid -> existing record (for checkpoint/resume)
        save_callback: Optional function(records) called after each person for incremental save
    """
    # English (base) prompt + the Chinese (_cn) prompt kept for Chinese personas.
    prompt = load_prompt(os.path.join(prompts_dir, 'important_dates_en.txt'))
    cn_prompt = load_prompt(os.path.join(prompts_dir, 'important_dates_zh.txt'))
    generator = ImportantDatesGenerator(prompt, cn_prompt)
    return generator.process_all(stage2_records, existing=existing, save_callback=save_callback)
