"""Run trajectory synthesis for the profile-schema ablation study.

For every profile JSON produced by ``create_profiles.py``, this script runs
the KEME trajectory synthesis pipeline and saves the resulting sessions
(plus the person profile) as a JSON file.
"""

import os
import json
import asyncio
import glob
import traceback
from pathlib import Path

import shortuuid
from agentscope.formatter import OpenAIChatFormatter
from agentscope.message import Msg
from agentscope.model import OpenAIChatModel

from MobileMem.keme.models import TrajectorySynthesisState
from MobileMem.keme.models.persona import PersonBase
from MobileMem.keme.toolkits import (
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
from MobileMem.keme.schedulers import ConstantGraphNotebookStateScheduler
from MobileMem.keme.utils import SYSTEM_PROMPT

from custom_profile_schema import (
    PersonFull,
    PersonMedium,
    PersonCompact,
)

from typing import Any


_SCRIPT_DIR = Path(__file__).resolve().parent

MODEL_NAME = "gpt-4.1"
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

PROFILES_DIR = str(_SCRIPT_DIR / "output" / "profiles")
OUTPUT_DIR = str(_SCRIPT_DIR / "output" / "trajectories")

_ALL_SCHEMAS = [PersonFull, PersonMedium, PersonCompact]
SCHEMA_MAP = {cls.__name__: cls for cls in _ALL_SCHEMAS}

# Notebook classes that need hook registration and cleanup.
_HOOK_NOTEBOOK_CLASSES = [
    (SessionNotebook, "session"),
    (TemporalEventGraphNotebook, "graph"),
    (GraphRefinementNotebook, "refinement"),
    (SessionGroundingNotebook, "grounding"),
]


def build_model(slot_index: int) -> OpenAIChatModel:
    """Build an OpenAI chat model for the given batch slot."""
    api_key = API_KEYS[slot_index]
    base_url = BASE_URLS[slot_index]
    client_args = {"base_url": base_url} if base_url else None
    return OpenAIChatModel(
        model_name=MODEL_NAME,
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


def load_person(profile_path: str) -> PersonBase:
    """Load a person profile from a JSON file and instantiate the correct schema."""
    with open(profile_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    profile_type = data.pop("profile_type", None)
    if profile_type is None or profile_type not in SCHEMA_MAP:
        raise ValueError(
            f"Unknown or missing profile type '{profile_type}' in {profile_path}. "
            f"Expected profile types: {list(SCHEMA_MAP.keys())}."
        )

    schema_cls = SCHEMA_MAP[profile_type]
    return schema_cls.model_validate(data)


def save_trajectory(
    state: TrajectorySynthesisState,
    source_filename: str,
    output_dir: str,
) -> str:
    """Save the synthesized trajectory as JSON.

    Args:
        state (`TrajectorySynthesisState`):
            The trajectory synthesis state from which person and sessions are extracted.
        source_filename (`str`):
            The original profile JSON filename (used to derive the output name).
        output_dir (`str`):
            The directory to save the output JSON.

    Returns:
        `str`: 
            The path of the saved file.
    """
    os.makedirs(output_dir, exist_ok=True)

    person = state.person
    profile_type = type(person).__name__

    sessions = state.get_sessions()
    sessions_data = [s.model_dump(mode="json") for s in sessions]

    result = {
        "profile_type": profile_type,
        "person": person.model_dump(mode="json"),
        "sessions": sessions_data,
        "num_sessions": len(sessions_data),
    }

    stem = Path(source_filename).stem
    filename = f"{stem}_trajectory.json"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=4)

    print(f"  Saved: {filepath}  ({len(sessions_data)} sessions)")
    return filepath


def _hook_name(base: str, person_id: str) -> str:
    """Build a person-scoped hook name to avoid cross-task contamination."""
    return f"{base}_{person_id}"


def _register_hooks(
    person_id: str,
    global_state: TrajectorySynthesisState,
) -> None:
    """Register class-level hooks scoped to a specific ``person_id``.

    Every hook checks ``notebook.person.id`` before acting, so concurrent
    syntheses with different persons do not interfere with each other.
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
    """Remove all class-level hooks for the given ``person_id``."""
    for cls, base in _HOOK_NOTEBOOK_CLASSES:
        cls.remove_class_hook(_hook_name(base, person_id))


async def synthesize_trajectory(
    person: PersonBase,
    agent_kwargs: dict[str, Any],
) -> TrajectorySynthesisState:
    """Run the full trajectory synthesis pipeline for a single person profile.

    Args:
        person (`PersonBase`):
            The person profile to synthesize a trajectory for.
        agent_kwargs (`dict[str, Any]`):
            Shared keyword arguments for the synthesis agent (model, formatter, etc.).

    Returns:
        `TrajectorySynthesisState`:
            The completed trajectory synthesis state containing all graphs and sessions.
    """
    global_state = TrajectorySynthesisState(person=person)

    scheduler = ConstantGraphNotebookStateScheduler(
        min_events=MIN_EVENTS,
        max_events=MAX_EVENTS,
        max_depth=MAX_DEPTH,
        is_agent_control=IS_AGENT_CONTROL,
    )

    _register_hooks(person.id, global_state)

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
            **agent_kwargs,
        )
        root_agent = SynthesisAgent(
            name=root_agent_name,
            sys_prompt=SYSTEM_PROMPT.format(agent_id=root_agent_name),
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


async def _run_one(
    profile_path: str,
    agent_kwargs: dict[str, Any],
    output_dir: str,
    label: str,
) -> None:
    """Load, synthesize, and save one profile."""
    filename = os.path.basename(profile_path)
    print(f"\n{label} {filename}")

    person = load_person(profile_path)
    profile_type = type(person).__name__
    n_dims = len(type(person).get_dimension_fields())
    print(f"  Schema: {profile_type} ({n_dims} dimensions)")
    print(f"  Person: {person.name}")
    print(f"  Trajectory: {person.trajectory_start} -> {person.trajectory_end}")

    print("  Synthesizing trajectory...")
    state = await synthesize_trajectory(person, agent_kwargs)
    save_trajectory(state, filename, output_dir)


async def main():
    if len(API_KEYS) != len(BASE_URLS):
        raise ValueError(
            f"API_KEYS (len={len(API_KEYS)}) and BASE_URLS (len={len(BASE_URLS)}) "
            "must have the same length."
        )

    batch_size = len(API_KEYS)

    slot_kwargs = []
    for i in range(batch_size):
        model = build_model(i)
        slot_kwargs.append(build_agent_kwargs(model))

    profile_paths = sorted(glob.glob(os.path.join(PROFILES_DIR, "*.json")))
    if not profile_paths:
        print(f"No profile JSONs are found in {PROFILES_DIR}.")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"{len(profile_paths)} profiles are found in {PROFILES_DIR}.")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Batch size: {batch_size}")
    print(f"Scheduler: min_events={MIN_EVENTS}, max_events={MAX_EVENTS}, "
          f"max_depth={MAX_DEPTH}, is_agent_control={IS_AGENT_CONTROL}")
    print("=" * 60)

    # Process profiles in batches
    for batch_start in range(0, len(profile_paths), batch_size):
        batch = profile_paths[batch_start:batch_start + batch_size]
        batch_end = batch_start + len(batch)
        print(f"\n{'=' * 60}")
        print(f"Batch [{batch_start + 1}–{batch_end} / {len(profile_paths)}]")
        print(f"{'=' * 60}")

        tasks = []
        for j, profile_path in enumerate(batch):
            global_idx = batch_start + j
            label = f"[{global_idx + 1}/{len(profile_paths)}]"
            tasks.append(
                _run_one(profile_path, slot_kwargs[j], OUTPUT_DIR, label)
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for j, result in enumerate(results):
            if isinstance(result, Exception):
                filename = os.path.basename(batch[j])
                print(f"\n  [ERROR] {filename}: {result}")
                traceback.print_exception(type(result), result, result.__traceback__)

    print(f"\n{'=' * 60}")
    print(f"Done. Trajectories saved to {OUTPUT_DIR}/")


if __name__ == "__main__":
    asyncio.run(main())

