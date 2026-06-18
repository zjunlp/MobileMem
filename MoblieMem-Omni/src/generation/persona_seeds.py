"""Persona seed generator (Stage 0): synthesize brand-new personas via LLM.

The CSV pipeline (the ``profile`` node) only covers the personas that have a
folder in ``infotest`` (uuid 0-9, all Chinese). This module seeds additional
personas that have **no CSV source** — by default foreign ones (uuid 10-19) — by
asking the LLM to expand a short spec (nationality, ethnicity, occupation hint)
into a record compatible with ``basic_profiles.jsonl``.

For non-Chinese specs the generated record carries a structured ``appearance``
block (ethnicity / skin / hair / eyes / face / build) that downstream image
stages consume to keep foreign personas visually consistent; Chinese personas
omit it and fall back to the predefined appearance pool instead.

The records are appended after the CSV-derived rows, so the stage1 file ends up
holding both the Chinese (0-9) and the seeded (10-19) personas.
"""
from __future__ import annotations

import time
import traceback
from typing import Dict, List, Optional, Set

from backends.llm import get_text_llm_model, llm_request, set_log_context

# Persona specs — personas without a CSV source, seeded straight from the LLM.
PERSONA_SPECS: List[Dict] = [
    # Foreign personas (uuid 10-19): 6 American + 4 British.
    {"uuid": 10, "nationality": "American", "language": "en",
     "ethnicity": "White Caucasian",
     "hint": "An American software engineer in his early 30s working at a tech startup in San Francisco, male"},
    {"uuid": 11, "nationality": "American", "language": "en",
     "ethnicity": "White Caucasian",
     "hint": "An American high school student aged 17 living in suburban Ohio, female"},
    {"uuid": 12, "nationality": "American", "language": "en",
     "ethnicity": "White Caucasian",
     "hint": "An American nurse practitioner in her mid-40s working in a rural clinic in Texas, female"},
    {"uuid": 13, "nationality": "American", "language": "en",
     "ethnicity": "White Caucasian",
     "hint": "An American small business owner in his late 50s running a hardware store in the Midwest, male"},
    {"uuid": 14, "nationality": "American", "language": "en",
     "ethnicity": "White Caucasian",
     "hint": "An American graduate student in her late 20s studying environmental science in Boston, female"},
    {"uuid": 15, "nationality": "American", "language": "en",
     "ethnicity": "White Caucasian",
     "hint": "An American retired military veteran in his early 60s living in Virginia, male"},
    {"uuid": 16, "nationality": "British", "language": "en",
     "ethnicity": "White British",
     "hint": "A British secondary school teacher in her late 30s teaching English literature in Manchester, female"},
    {"uuid": 17, "nationality": "British", "language": "en",
     "ethnicity": "White British",
     "hint": "A British pub landlord in his early 50s running a traditional pub in a small Yorkshire town, male"},
    {"uuid": 18, "nationality": "British", "language": "en",
     "ethnicity": "White British",
     "hint": "A British junior doctor in his late 20s working in an NHS hospital in London, male"},
    {"uuid": 19, "nationality": "British", "language": "en",
     "ethnicity": "White British",
     "hint": "A British retired librarian in her mid-60s living in a village in the Cotswolds, female"},

    # Extra Chinese personas (uuid 20-24) are available but commented out by
    # default; uncomment to seed more Chinese personas beyond the CSV folders.
    # {"uuid": 20, "nationality": "Chinese", "language": "zh",
    #  "hint": "Chinese female nurse in her late 20s working in a city hospital"},
]

# Chinese prompt (kept in Chinese on purpose: the model writes the persona's
# free-text fields in the persona's own language). No appearance block — Chinese
# personas use the predefined appearance pool downstream.
SYSTEM_PROMPT_ZH = """你是一个专业的人物数据生成器。为合成数据集生成真实、详细的人物档案。
只输出合法的 JSON，不要输出任何多余文字。"""

USER_PROMPT_TEMPLATE_ZH = """请为以下人物生成详细的人物档案：

{hint}

输出一个 JSON 对象，包含以下字段：
{{
  "uuid": {uuid},
  "role_identity": "英文小写下划线角色标识，如 nurse、teacher、restaurant_owner",
  "name": "符合国籍的真实中文全名",
  "gender": "男 或 女",
  "birth_date": "YYYY-MM-DD（与描述中的年龄匹配）",
  "nationality": "{nationality}",
  "language": "{language}",
  "personality_traits": "第一人称描述性格特点（2-3句话，用我/我的）",
  "life_experiences": "第一人称描述人生经历和背景（2-3句话，用我/我的）"
}}

要求：
- name 必须是地道的中文姓名
- personality_traits 和 life_experiences 必须用中文第一人称书写
- role_identity 用英文小写下划线格式
- birth_date 必须与描述中的年龄吻合
"""

# English prompt for non-Chinese personas; emits the structured appearance block.
SYSTEM_PROMPT_EN = """You are a professional persona data generator. Generate realistic, detailed persona profiles for synthetic dataset creation.
Output ONLY valid JSON, no extra text."""

USER_PROMPT_TEMPLATE_EN = """Generate a detailed persona profile for the following person:

{hint}

This person's ethnicity is: {ethnicity}

Output a JSON object with these exact fields:
{{
  "uuid": {uuid},
  "role_identity": "short_role_slug_in_english_lowercase_with_underscores",
  "name": "Realistic full name appropriate for nationality and ethnicity",
  "gender": "Male or Female",
  "birth_date": "YYYY-MM-DD (age-appropriate for the description)",
  "nationality": "{nationality}",
  "language": "{language}",
  "personality_traits": "First-person description of personality (2-3 sentences, use I/my/me)",
  "life_experiences": "First-person description of background and experiences (2-3 sentences, use I/my/me)",
  "appearance": {{
    "ethnicity": "{ethnicity}",
    "skin_color": "One of: fair skin, light skin, olive skin, tan skin, brown skin, dark skin (must match ethnicity)",
    "hair_color": "e.g. brown, black, blonde, auburn, red, gray",
    "hair_style": "e.g. short straight, long wavy, curly shoulder-length",
    "eye_color": "e.g. blue, green, brown, hazel, gray",
    "facial_hair": "e.g. clean-shaven, light stubble, full beard, none (use none for females)",
    "face_shape": "e.g. oval, round, square, heart-shaped, oblong, diamond",
    "build": "e.g. slim, athletic, average, muscular, lean, sturdy, petite"
  }}
}}

Requirements:
- name must be culturally appropriate for {nationality} and {ethnicity}
- personality_traits and life_experiences must be in first person
- role_identity should be a simple English slug like "nurse", "teacher", "restaurant_owner"
- birth_date must match the age described
- appearance.skin_color MUST be consistent with the ethnicity "{ethnicity}"
- appearance fields must describe a realistic person of this ethnicity, age, and gender
"""


def generate_persona(spec: Dict) -> Dict:
    """Expand a single persona spec into a stage1-compatible record via the LLM."""
    uuid = spec["uuid"]
    is_chinese = spec["nationality"] == "Chinese"
    system_prompt = SYSTEM_PROMPT_ZH if spec["language"] == "zh" else SYSTEM_PROMPT_EN
    user_template = USER_PROMPT_TEMPLATE_ZH if spec["language"] == "zh" else USER_PROMPT_TEMPLATE_EN

    prompt = user_template.format(
        hint=spec["hint"],
        uuid=uuid,
        nationality=spec["nationality"],
        language=spec["language"],
        ethnicity=spec.get("ethnicity", ""),
    )

    response, _cost = llm_request(
        system_prompt,
        prompt,
        model=get_text_llm_model(is_chinese),
        return_parsed_json=True,
        extract_json=True,
        json_markers=[],
    )

    if not isinstance(response, dict):
        raise ValueError(f"LLM returned non-dict for uuid={uuid}: {response}")
    # Pin the spec-controlled fields regardless of what the model echoed back.
    response["uuid"] = uuid
    response["nationality"] = spec["nationality"]
    response["language"] = spec["language"]
    return response


def generate_persona_seeds(
    existing_uuids: Set[int],
    keep: Optional[Set[int]] = None,
    force: bool = False,
    start_uuid: int = 10,
    end_uuid: int = 24,
    save_callback=None,
) -> List[Dict]:
    """Generate the seed personas missing from the stage1 file.

    Args:
        existing_uuids: uuids already present in stage1 (skipped unless ``force``).
        keep: optional uuid filter (``None`` = every spec in the range).
        force: regenerate even if the uuid already exists.
        start_uuid / end_uuid: inclusive uuid range of specs to consider.
        save_callback: optional ``Callable[[List[Dict]], None]`` invoked with the
            growing record list after each persona (checkpointing).

    Returns the newly generated records (one per processed spec).
    """
    specs = [
        s for s in PERSONA_SPECS
        if start_uuid <= s["uuid"] <= end_uuid
        and (keep is None or s["uuid"] in keep)
        and (force or s["uuid"] not in existing_uuids)
    ]
    new_records: List[Dict] = []
    for i, spec in enumerate(specs):
        uuid = spec["uuid"]
        set_log_context(uuid=uuid, stage="persona_seeds")
        print(f"[persona_seeds] [{i + 1}/{len(specs)}] uuid={uuid}: {spec['hint'][:60]}...")
        try:
            record = generate_persona(spec)
            new_records.append(record)
            if save_callback is not None:
                save_callback(list(new_records))
            print(f"  -> name={record.get('name')}, role={record.get('role_identity')}")
        except Exception as exc:  # one bad persona must not abort the batch
            print(f"  -> ERROR uuid={uuid}: {exc}")
            traceback.print_exc()
            time.sleep(2)
    return new_records


def main() -> None:
    """Stand-alone entry: append seed personas to a stage1 JSONL file."""
    import argparse
    import os

    from common import read_jsonl, write_jsonl

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    parser = argparse.ArgumentParser(description="Stage 0: generate persona seeds via LLM")
    parser.add_argument("--output-dir", default=os.path.join(project_root, "output", "data"),
                        help="Directory holding basic_profiles.jsonl")
    parser.add_argument("--start-uuid", type=int, default=10)
    parser.add_argument("--end-uuid", type=int, default=24)
    parser.add_argument("--force", action="store_true", help="Regenerate even if the uuid exists")
    args = parser.parse_args()

    out_path = os.path.join(args.output_dir, "basic_profiles.jsonl")
    os.makedirs(args.output_dir, exist_ok=True)

    existing = read_jsonl(out_path) if os.path.exists(out_path) else []
    existing_uuids = {r.get("uuid") for r in existing if isinstance(r, dict)}
    print(f"Existing profiles: {sorted(u for u in existing_uuids if u is not None)}")

    new_records = generate_persona_seeds(
        existing_uuids, force=args.force,
        start_uuid=args.start_uuid, end_uuid=args.end_uuid)

    new_uuids = {r.get("uuid") for r in new_records}
    merged = [r for r in existing if r.get("uuid") not in new_uuids] + new_records
    merged.sort(key=lambda r: r.get("uuid", 0))
    write_jsonl(merged, out_path)
    print(f"[persona_seeds] +{len(new_records)} personas -> {out_path}")


if __name__ == "__main__":
    main()
