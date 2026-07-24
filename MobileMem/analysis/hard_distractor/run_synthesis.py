"""Run trajectory synthesis for the hard-distractor ablation study.

For every prepared sample in the previous stage, this script builds 
a per-person system prompt that injects the target question-answer
pair, core facts, and distractor guidelines into the global context so that
every agent in the synthesis pipeline is aware of the constraints.
Then, it runs the KEME trajectory synthesis pipeline and saves the result.
"""

import os
import json
import asyncio
import traceback
from pathlib import Path
import shortuuid
from agentscope.formatter import OpenAIChatFormatter
from agentscope.message import Msg
from agentscope.model import OpenAIChatModel
from keme.models import TrajectorySynthesisState
from keme.models.session import Message, Session
from keme.data import merge_parallel_sessions, unify_message_names
from keme.toolkits import (
    SynthesisAgent,
    TemporalEventGraphNotebook,
    SessionNotebook,
    SessionGroundingNotebook,
    GraphRefinementNotebook,
    DefaultTemporalEventGraphToHint,
    DefaultSessionToHint,
    DefaultSessionGroundingToHint,
    DefaultGraphRefinementToHint,
)
from keme.schedulers import ConstantGraphNotebookStateScheduler
from prepare_env import PersonMedium
from typing import Any


_SCRIPT_DIR = Path(__file__).resolve().parent

INPUT_PATH = str(_SCRIPT_DIR / "output" / "prepared_env.json")
OUTPUT_DIR = str(_SCRIPT_DIR / "output" / "trajectories")

MODEL_NAME = "gpt-5.1"
TEMPERATURE = 1.0

API_KEYS = [
    os.environ.get("OPENAI_API_KEY"),
]
BASE_URLS = [
    os.environ.get("OPENAI_API_BASE"),
]

MAX_ITERS = 50
PARALLEL_TOOL_CALLS = False
COMPATIBILITY_CONTEXT_MAX_TOKENS = 8000

MIN_EVENTS = 2
MAX_EVENTS = 10
MAX_DEPTH = 2
IS_AGENT_CONTROL = True


# We only change the system prompt of KEME. 
HARD_DISTRACTOR_SYSTEM_PROMPT = (
    "You are an **intelligent synthesis agent (ID NUMBER: {agent_id})** participating in a scientific research project "
    "to construct a **memory evaluation dataset** for AI memory systems.\n\n"
    "Your role is to build a **long, realistic, and coherent interaction trajectory** "
    "around a given **question-answer pair** and its **core facts**. "
    "The trajectory captures a person's life experiences over time, structured hierarchically "
    "from high-level life events down to fine-grained human-assistant interaction sessions. "
    "The core facts have already been embedded in pre-synthesized sessions. "
    "Your task is to synthesize additional interaction content that, without contradicting the core facts, "
    "increases the difficulty for AI memory systems to correctly answer the question. "
    "Below we provide distractor guidelines that you can follow to increase the difficulty.\n\n"
    "**Target Question-Answer Pair**:\n{qa_pair}\n\n"
    "**Core Facts**:\n{core_facts}\n\n"
    "**Distractor Guidelines**:\n{guidelines}\n\n"
    "Note:\n"
    "**<span style=\"color:red;\">1. The AI assistant in human-AI interactions is a conversational-only assistant. "
    "It can answer questions, offer suggestions, and engage in discussions, but it CANNOT write files, execute code, "
    "access external systems, or perform any operations on behalf of the user.</span>**\n"
    "**<span style=\"color:red;\">2. In the person profile, `Mentioned: True` indicates that an attribute has been disclosed or reflected "
    "in the user's interactions with the AI assistant so far (either explicitly or implicitly).</span>**\n"
    "**<span style=\"color:red;\">3. The question-answer pair above is already defined. In the side note, you are encouraged to share "
    "your ideas on how to further increase the difficulty of correctly answering this question for memory systems. "
    "These notes will be visible to other agents in the synthesis pipeline.</span>**\n"
    "**<span style=\"color:red;\">4. The answer and all core facts listed above are ALREADY "
    "embedded in the pre-synthesized (grounded) sessions. You MUST NOT repeat, rephrase, paraphrase, "
    "or allude to the answer or any core fact in the sessions you synthesize. "
    "If a core fact states that the user is 'Premier Silver on United Airlines', no newly synthesized "
    "session may mention 'Premier Silver', nor convey the same information in different words. "
    "The grounded sessions are the ONLY place where the answer should be discoverable.</span>**\n"
)

# Two default extra guidelines appended to every sample's distractor guidelines.
DEFAULT_EXTRA_GUIDELINES = [
    (
        "Introduce conversations and events that are entirely unrelated to the "
        "question-answer pair and the core facts. This enriches the person's "
        "trajectory with diverse content, makes the person feel well-rounded, "
        "and increases the size of the memory store, which naturally reduces "
        "retrieval accuracy."
    ),
    (
        "Use your own creativity to devise additional strategies for increasing "
        "the difficulty of the question-answer pair beyond the guidelines above."
    ),
]



def build_model(slot_index: int) -> OpenAIChatModel:
    """Build an OpenAI chat model for the given batch slot."""
    api_key = API_KEYS[slot_index]
    base_url = BASE_URLS[slot_index]
    client_args = {"base_url": base_url} if base_url else None
    return OpenAIChatModel(
        model_name=MODEL_NAME,
        stream=False, 
        api_key=api_key,
        client_args=client_args,
        generate_kwargs={"temperature": TEMPERATURE},
    )


def build_agent_kwargs(model: OpenAIChatModel) -> dict[str, Any]:
    """Build shared keyword arguments for the synthesis agent."""
    return {
        "model": model,
        "formatter": OpenAIChatFormatter(),
        "max_iters": MAX_ITERS,
        "parallel_tool_calls": PARALLEL_TOOL_CALLS,
    }


def build_person_system_prompt(sample: dict) -> str:
    """Build a per-person system prompt template.

    The returned string still contains the ``{agent_id}`` slot so the
    framework can fill it at runtime for each sub-agent.

    Args:
        sample (`dict`):
            One element of ``prepared_env.json``.

    Returns:
        `str`:
            A system prompt template with only the ``{agent_id}`` slot remaining.
    """
    qa_anchors = sample["qa_anchors"]
    qa_pair = (
        f"- Question: {sample['question']}\n"
        f"- Question Date: {sample['question_date']}"
        f"- Answer: {sample['answer']}\n"
    )
    core_facts = "\n".join(
        f"{i + 1}. {fact}" for i, fact in enumerate(qa_anchors["core_facts"])
    )
    all_guidelines = list(qa_anchors["distractor_guidelines"]) + DEFAULT_EXTRA_GUIDELINES 
    guidelines = "\n".join(
        f"{i + 1}. {g}" for i, g in enumerate(all_guidelines)
    )

    return HARD_DISTRACTOR_SYSTEM_PROMPT.replace(
        "{qa_pair}", qa_pair
    ).replace(
        "{core_facts}", core_facts
    ).replace(
        "{guidelines}", guidelines
    )


_HOOK_NOTEBOOK_CLASSES = [
    (SessionNotebook, "session"),
    (TemporalEventGraphNotebook, "graph"),
    (GraphRefinementNotebook, "refinement"),
    (SessionGroundingNotebook, "grounding"),
]


def _hook_name(base: str, person_id: str) -> str:
    """Build a person-scoped hook name."""
    return f"{base}_{person_id}"


def _register_hooks(
    person_id: str,
    global_state: TrajectorySynthesisState,
) -> None:
    """Register class-level hooks scoped to a specific person ID.
    
    Every hook checks the person ID of current notebook before acting, so concurrent
    syntheses with different person IDs do not interfere with each other.
    """

    def session_notebook_hook(notebook: SessionNotebook) -> None:
        if notebook.person.id != person_id:
            return
        if notebook.current_session is not None:
            session = notebook.current_session
            if session.id not in global_state.sessions:
                global_state.add_session(session)

    def graph_notebook_hook(notebook: TemporalEventGraphNotebook) -> None:
        if notebook.person.id != person_id:
            return
        graph = notebook.current_graph
        if graph is not None:
            if graph.id not in global_state.graphs:
                global_state.add_graph(graph)
            else:
                global_state.refresh_graph(graph.id)

    def graph_refinement_notebook_hook(notebook: GraphRefinementNotebook) -> None:
        if notebook.person.id != person_id:
            return
        graph = notebook.current_state.graph
        if graph.id not in global_state.graphs:
            global_state.add_graph(graph)
        else:
            global_state.refresh_graph(graph.id)

    def session_grounding_notebook_hook(notebook: SessionGroundingNotebook) -> None:
        if notebook.person.id != person_id:
            return
        graph = notebook.current_graph
        if graph.id not in global_state.graphs:
            global_state.add_graph(graph)
        else:
            global_state.refresh_graph(graph.id)

    hook_fns = {
        "session": session_notebook_hook,
        "graph": graph_notebook_hook,
        "refinement": graph_refinement_notebook_hook,
        "grounding": session_grounding_notebook_hook,
    }
    for cls, base in _HOOK_NOTEBOOK_CLASSES:
        cls.register_class_hook(_hook_name(base, person_id), hook_fns[base])


def _unregister_hooks(person_id: str) -> None:
    """Remove all class-level hooks for the given person ID."""
    for cls, base in _HOOK_NOTEBOOK_CLASSES:
        cls.remove_class_hook(_hook_name(base, person_id))


async def synthesize_trajectory(
    person: PersonMedium,
    sys_prompt_template: str,
    agent_kwargs: dict[str, Any],
) -> TrajectorySynthesisState:
    """Run the full trajectory synthesis pipeline for a single person.

    Args:
        person (`PersonMedium`):
            The person profile (with grounded sessions attached).
        sys_prompt_template (`str`):
            A per-person system prompt template that still contains the
            ``{agent_id}`` slot.
        agent_kwargs (`dict[str, Any]`):
            Shared keyword arguments for the synthesis agent.

    Returns:
        `TrajectorySynthesisState`:
            The completed trajectory synthesis state.
    """
    global_state = TrajectorySynthesisState(person=person)

    scheduler = ConstantGraphNotebookStateScheduler(
        min_events=MIN_EVENTS,
        max_events=MAX_EVENTS,
        max_depth=MAX_DEPTH,
        is_agent_control=IS_AGENT_CONTROL,
    )

    _register_hooks(person.id, global_state)

    # Include `sys_prompt` in `agent_kwargs` so the framework propagates it to every sub-agent.
    kwargs_with_prompt = {**agent_kwargs, "sys_prompt": sys_prompt_template}

    try:
        root_agent_name = f"agent_{shortuuid.uuid()}"
        graph_notebook = TemporalEventGraphNotebook(
            person,
            root_agent_name,
            level=0,
            scheduler=scheduler,
            graph_to_hint=DefaultTemporalEventGraphToHint(),
            session_to_hint=DefaultSessionToHint(),
            graph_refinement_to_hint=DefaultGraphRefinementToHint(),
            session_grounding_to_hint=DefaultSessionGroundingToHint(),
            compatibility_context_max_tokens=COMPATIBILITY_CONTEXT_MAX_TOKENS,
            **kwargs_with_prompt,
        )
        root_agent = SynthesisAgent(
            name=root_agent_name,
            sys_prompt=sys_prompt_template.format(agent_id=root_agent_name),
            notebook=graph_notebook,
            **agent_kwargs,
        )

        task_instruction = scheduler.get_task_instruction(
            person,
            level=0,
            instruction_type="temporal_event_graph",
        )
        await root_agent(msg=Msg("user", task_instruction, "user"))
    finally:
        _unregister_hooks(person.id)

    return global_state


def save_trajectory(
    state: TrajectorySynthesisState,
    sample: dict,
    output_dir: str,
) -> str:
    """Save the synthesized trajectory as JSON.

    Args:
        state (`TrajectorySynthesisState`):
            The completed trajectory synthesis state.
        sample (`dict`):
            The original prepared sample (for metadata).
        output_dir (`str`):
            The directory to write the output file to.

    Returns:
        `str`: 
            The path of the saved file.
    """
    os.makedirs(output_dir, exist_ok=True)

    person = state.person
    sessions = state.get_sessions()
    sessions = merge_parallel_sessions(sessions, check_messages=True)
    sessions = unify_message_names(
        sessions, 
        name=person.name, 
        role="user", 
        in_place=False,
    )
    sessions = unify_message_names(
        sessions, 
        name="assistant", 
        role="assistant", 
        in_place=False,
    )
    sessions_data = [s.model_dump(mode="json") for s in sessions]

    result = {
        "question_id": sample["question_id"],
        "question_type": sample["question_type"],
        "question": sample["question"],
        "question_date": sample["question_date"],
        "answer": sample["answer"],
        "person": person.model_dump(mode="json"),
        "sessions": sessions_data,
        "num_sessions": len(sessions_data),
    }

    qid = sample["question_id"]
    safe_name = person.name.replace(" ", "_")
    filename = f"{qid}_{safe_name}_trajectory.json"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(
            result, 
            f, 
            ensure_ascii=False, 
            indent=4,
        )

    print(f"  Saved: {filepath}  ({len(sessions_data)} sessions)")
    return filepath


async def _run_one(
    sample: dict,
    agent_kwargs: dict[str, Any],
    output_dir: str,
    label: str,
) -> None:
    """Load, synthesize, and save one sample."""
    qid = sample["question_id"]
    print(f"\n{label} question_id={qid}")

    person = PersonMedium.model_validate(sample["persona"])
    for raw_session in sample["haystack_sessions"]:
        messages = []
        for msg in raw_session:
            name = person.name if msg["role"] == "user" else "assistant" 
            message = Message(
                name=name,
                role=msg["role"],
                content=msg["content"],
                timestamp=msg["timestamp"],
            )
            message.update_metadata(
                {
                    "has_answer": msg.get("has_answer", False),
                }
            )
            messages.append(message)
        session = Session(messages=messages)
        person.add_grounded_session(session)

    n_grounded = person.num_grounded_sessions
    print(f"  Person: {person.name}")
    print(f"  Trajectory: {person.trajectory_start} -> {person.trajectory_end}")
    print(f"  Grounded sessions: {n_grounded}")

    sys_prompt_template = build_person_system_prompt(sample)

    print("  Synthesizing trajectory...")
    state = await synthesize_trajectory(
        person, 
        sys_prompt_template, 
        agent_kwargs
    )
    save_trajectory(state, sample, output_dir)


async def main():
    if len(API_KEYS) != len(BASE_URLS):
        raise ValueError(
            f"API_KEYS (len={len(API_KEYS)}) and BASE_URLS "
            f"(len={len(BASE_URLS)}) must have the same length."
        )

    batch_size = len(API_KEYS)

    slot_kwargs = []
    for i in range(batch_size):
        model = build_model(i)
        slot_kwargs.append(build_agent_kwargs(model))

    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        samples = json.load(f)[-1:]

    if not samples:
        print(f"No samples found in {INPUT_PATH}.")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"{len(samples)} samples loaded from {INPUT_PATH}")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Batch size: {batch_size}")
    print(
        f"Scheduler: min_events={MIN_EVENTS}, max_events={MAX_EVENTS}, "
        f"max_depth={MAX_DEPTH}, is_agent_control={IS_AGENT_CONTROL}"
    )
    print("=" * 60)

    for batch_start in range(0, len(samples), batch_size):
        batch = samples[batch_start:batch_start + batch_size]
        batch_end = batch_start + len(batch)
        print(f"\n{'=' * 60}")
        print(f"Batch [{batch_start + 1}-{batch_end} / {len(samples)}]")
        print(f"{'=' * 60}")

        tasks = []
        for j, sample in enumerate(batch):
            global_idx = batch_start + j
            label = f"[{global_idx + 1}/{len(samples)}]"
            tasks.append(
                _run_one(sample, slot_kwargs[j], OUTPUT_DIR, label)
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for j, result in enumerate(results):
            if isinstance(result, Exception):
                qid = batch[j]["question_id"]
                print(f"\n  [ERROR] question_id={qid}: {result}")
                traceback.print_exception(
                    type(result), result, result.__traceback__,
                )

    print(f"\n{'=' * 60}")
    print(f"Done. Trajectories saved to {OUTPUT_DIR}/")


if __name__ == "__main__":
    asyncio.run(main())

