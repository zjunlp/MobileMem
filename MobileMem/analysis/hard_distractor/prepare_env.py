"""Prepare environment data for the hard-distractor ablation study.

For each sampled question, this script extracts question-answer anchor 
information including critical facts that ground the question-answer pair and
dimensions along which effective distractors can be constructed.
Then, it synthesizes a person profile from the answer sessions using the KEME profile 
creation pipeline with a custom task template.
"""

import os
import json
import asyncio
from pathlib import Path
from pydantic import BaseModel, Field
from MobileMem.keme.models.persona import PersonBase
from MobileMem.keme.models.persona import (
    BasicInfo,
    Personality,
    Career,
    Diet,
    Health,
    Entertainment,
    Finance,
    SocialCircle,
)
from MobileMem.keme.data import create_profile
from agentscope.model import OpenAIChatModel
from agentscope.formatter import OpenAIChatFormatter
from agentscope.message import Msg
from MobileMem.keme.toolkits.agent import SynthesisAgent


_SCRIPT_DIR = Path(__file__).resolve().parent

INPUT_PATH = str(_SCRIPT_DIR / "data" / "sampled_questions.json")
OUTPUT_PATH = str(_SCRIPT_DIR / "output" / "prepared_env.json")

MODEL_NAME = "gpt-5.2"


# Task template for profile dimension synthesis.
# The persona seed is formatted conversation content (not a direct persona
# description), so the template instructs the LLM to infer the user's
# profile from the conversation evidence.
PROFILE_TASK_TEMPLATE = (
    "You are given conversation sessions between a user and an AI assistant "
    "that naturally reveal aspects of the user's life, personality, and "
    "preferences.\n\n"
    "Your task is to synthesize the required profile dimension(s) by "
    "inferring the user's characteristics from these conversations.\n\n"
    "Key instructions:\n"
    "1. Focus on what the user reveals about themselves, ignore the "
    "assistant's behavior and responses.\n"
    "2. The synthesized profile must be consistent with the conversation "
    "content.\n"
    "3. For aspects not directly mentioned in the conversations, freely "
    "create rich and plausible details to make the person vivid and "
    "well-rounded, as long as they do not contradict the conversation "
    "content.\n"
    "4. Maintain internal consistency across all dimensions.\n\n"
    "Conversation Sessions:\n{persona_seed}\n\n"
    "Already Synthesized Profile Parts:\n{current_profile}\n\n"
    "Generate realistic, coherent, and detailed content for all required fields. "
    "Each content should be concise, and avoid unnecessary details."
)

# System prompt for the question-answer anchor extraction agent.
QA_ANCHORS_SYS_PROMPT = (
    "You are an expert analyst specializing in question-answer grounding "
    "and adversarial evaluation design for memory systems. Your role is to "
    "identify the critical factual anchors that make a question-answer pair "
    "valid, and to produce actionable guidelines for synthesizing "
    "trajectory content that increases the difficulty of correctly answering "
    "the question."
)

# Task template for question-answer anchor extraction.
QA_ANCHORS_TASK_TEMPLATE = (
    "Given the following question-answer pair and the conversation sessions "
    "that serve as evidence, extract the critical anchor information.\n\n"
    "Question-Answer Anchor Information consists of:\n"
    "1. **Core Facts**: Essential factual statements embedded in the "
    "conversations that directly support the answer. These facts MUST NOT "
    "be contradicted during trajectory synthesis, or the question-answer "
    "pair becomes invalid.\n"
    "2. **Distractor Guidelines**: Concrete, actionable guidelines for "
    "synthesizing additional trajectory content (conversations, events, "
    "etc.) that increases the difficulty of correctly answering the "
    "question. Each guideline should describe what kind of distractor "
    "content to introduce and explain why it would confuse a memory system while keeping the "
    "original question-answer pair valid.\n\n"
    "Question: {question}\n"
    "Answer: {answer}\n"
    "Question Date: {question_date}\n\n"
    "Evidence Sessions:\n{sessions_text}\n\n"
    "Extract the question-answer anchor information."
)


class PersonMedium(PersonBase):
    """A medium-complexity person profile schema with 8 dimensions.

    It covers 8 distinct life domains: Identity, Character, Work, Food,
    Wellness, Leisure, Finance, and Relationships.
    """

    basic_info: BasicInfo = Field(
        description="Basic demographic information dimension.",
    )
    personality: Personality = Field(
        description="Personality traits and behavioral characteristics dimension.",
    )
    career: Career = Field(
        description="Professional and work-related information dimension.",
    )
    diet: Diet = Field(
        description="Dietary preferences and eating habits dimension.",
    )
    health: Health = Field(
        description="Health awareness and fitness habits dimension.",
    )
    entertainment: Entertainment = Field(
        description="Entertainment preferences and activities dimension.",
    )
    finance: Finance = Field(
        description="Financial habits and preferences dimension.",
    )
    social_circle: SocialCircle = Field(
        description="Social connections and relationships dimension.",
    )


class QAAnchorInfo(BaseModel):
    """Critical anchor information extracted from a question-answer pair and
    its evidence sessions.

    This structured output captures the essential grounding facts that keep
    the question-answer pair valid and actionable guidelines for synthesizing
    hard-distractor trajectory content.
    """

    core_facts: list[str] = Field(
        description=(
            "Essential factual statements from the conversations that directly "
            "support the answer. These facts must not be contradicted during "
            "trajectory synthesis."
        ),
    )
    distractor_guidelines: list[str] = Field(
        description=(
            "Concrete, actionable guidelines for synthesizing additional "
            "trajectory content that increases the difficulty of correctly "
            "answering the question. Each guideline describes what kind of "
            "distractor content to introduce and why it would confuse a "
            "memory system while keeping the original question-answer pair "
            "valid."
        ),
    )


def build_model() -> OpenAIChatModel:
    """Build the chat model from environment variables."""
    api_key = os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_API_BASE")
    client_args = {"base_url": base_url} if base_url else None
    return OpenAIChatModel(
        model_name=MODEL_NAME,
        api_key=api_key,
        client_args=client_args,
    )


def format_sessions_as_text(
    sessions: list[list[dict]],
    session_ids: list[str],
    dates: list[str],
) -> str:
    """Format answer sessions into readable plain text for large language model consumption.

    Args:
        sessions (`list[list[dict]]`):
            List of sessions, each being a list of message dicts with
            ``role`` and ``content`` keys.
        session_ids (`list[str]`):
            Parallel list of session identifiers.
        dates (`list[str]`):
            Parallel list of session dates in ISO 8601 format.

    Returns:
        `str`:
            A human-readable text representation of all sessions.
    """
    parts = []
    for i, (session, sid, date) in enumerate(
        zip(sessions, session_ids, dates)
    ):
        parts.append(f'<session index="{i + 1}" id="{sid}" date="{date}">')
        for msg in session:
            role = msg["role"]
            content = msg["content"]
            parts.append(f"  <message role=\"{role}\">{content}</message>")
        parts.append("</session>")
    return "\n".join(parts)


async def extract_qa_anchors(
    question: str,
    answer: str,
    question_date: str,
    sessions_text: str,
    agent_kwargs: dict,
) -> QAAnchorInfo:
    """Extract question-answer anchor information using the large language model agent.

    Args:
        question (`str`):
            The question text.
        answer (`str`):
            The ground-truth answer.
        question_date (`str`):
            The question date in ISO 8601 format.
        sessions_text (`str`):
            Formatted text of the evidence sessions.
        agent_kwargs (`dict`):
            Keyword arguments forwarded to the agent constructor. 

    Returns:
        `QAAnchorInfo`:
            The extracted anchor information.
    """
    agent = SynthesisAgent(
        name="qa_anchor_extractor",
        sys_prompt=QA_ANCHORS_SYS_PROMPT,
        **agent_kwargs,
    )

    task = QA_ANCHORS_TASK_TEMPLATE.format(
        question=question,
        answer=answer,
        question_date=question_date,
        sessions_text=sessions_text,
    )

    response = await agent(
        msg=Msg("user", task, "user"),
        structured_model=QAAnchorInfo,
    )

    if response.metadata is None:
        raise RuntimeError(
            f"Failed to extract QA anchor information for question: "
            f"{question!r}"
        )

    return QAAnchorInfo.model_validate(response.metadata)


async def main():
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        samples = json.load(f)

    model = build_model()
    formatter = OpenAIChatFormatter()

    agent_kwargs = {
        "model": model,
        "formatter": formatter,
    }

    print(f"Loaded {len(samples)} samples from {INPUT_PATH}")
    print("=" * 60)

    results = []
    for i, sample in enumerate(samples):
        qid = sample["question_id"]
        n_sessions = len(sample["haystack_session_ids"])
        print(
            f"\n[{i + 1}/{len(samples)}] question_id={qid} "
            f"(answer_sessions={n_sessions})"
        )

        # Format sessions as text (shared by both steps).
        sessions_text = format_sessions_as_text(
            sample["haystack_sessions"],
            sample["haystack_session_ids"],
            sample["haystack_dates"],
        )
        traj_start = sample["trajectory_start"]
        traj_end = sample["trajectory_end"]

        # Step 1: Extract question-answer anchor information.
        qa_anchors = await extract_qa_anchors(
            question=sample["question"],
            answer=sample["answer"],
            question_date=sample["question_date"],
            sessions_text=sessions_text,
            agent_kwargs=agent_kwargs,
        )

        # Step 2: Synthesize person profile.
        profile = await create_profile(
            profile_schema=PersonMedium,
            persona_seed=sessions_text,
            agent_kwargs=agent_kwargs,
            task_template=PROFILE_TASK_TEMPLATE,
            trajectory_start=traj_start,
            trajectory_end=traj_end,
            use_simplified_schema=True,
        )

        # Build enriched sample.
        result = {
            "question_id": sample["question_id"],
            "question_type": sample["question_type"],
            "question": sample["question"],
            "question_date": sample["question_date"],
            "answer": sample["answer"],
            "answer_session_ids": sample["answer_session_ids"],
            "haystack_dates": sample["haystack_dates"],
            "haystack_session_ids": sample["haystack_session_ids"],
            "haystack_sessions": sample["haystack_sessions"],
            "persona": profile.model_dump(mode="json"),
            "qa_anchors": qa_anchors.model_dump(mode="json"),
        }
        results.append(result)
        print(f"  Done. Profile name: {profile.name}")

    # Save enriched data.
    Path(OUTPUT_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(
            results, 
            f, 
            ensure_ascii=False, 
            indent=4,
        )
    print("\n" + "=" * 60)
    
    
if __name__ == "__main__":
    asyncio.run(main())
