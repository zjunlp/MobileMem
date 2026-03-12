# -*- coding: utf-8 -*-
"""
Run question-answer pairs synthesis from a pre-synthesized trajectory.

This script runs the KEME question-answer pairs synthesis pipeline using an existing trajectory state
(loaded from a pickle file) and provides visualization through the AgentScope studio server.
"""
import argparse
import asyncio
import os
import pickle
import signal
import json 
from datetime import datetime
from collections import deque 

import shortuuid
from agentscope.formatter import OpenAIChatFormatter
from agentscope.message import Msg
from agentscope.model import OpenAIChatModel

from keme.models import (
    TrajectorySynthesisState,
    QuestionTypeToolbook,
    QuestionType, 
    QuestionAnswerPair,
    Event,
    Session,
    Message,
    Person,
)
from keme.models.persona import PersonDimensionBase
from keme.toolkits import (
    SynthesisAgent,
    QANotebook,
    DefaultQAToHint,
)
from keme.schedulers import QANotebookStateSchedulerBase, ConstantQANotebookStateScheduler
from keme.data import merge_parallel_sessions, unify_message_names
from keme.utils import StudioServer, QA_SYSTEM_PROMPT
from typing import Any 


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run HASTE QA synthesis from pre-synthesized trajectory.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    
    # Trajectory configuration
    parser.add_argument(
        "--trajectory_path",
        type=str,
        default="trajectory_state.pkl",
        help="Path to the trajectory state pickle file.",
    )
    
    # Model configuration
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4.1",
        help="Model name to use for synthesis.",
    )
    parser.add_argument(
        "--api_key",
        type=str,
        default=None,
        help="OpenAI API key. If not provided, uses OPENAI_API_KEY environment variable.",
    )
    parser.add_argument(
        "--api_base",
        type=str,
        default=None,
        help="OpenAI API base URL. If not provided, uses OPENAI_API_BASE environment variable.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=1.0,
        help="Temperature for model generation.",
    )
    
    # QA synthesis configuration
    parser.add_argument(
        "--min_qa_pairs",
        type=int,
        default=2,
        help="Minimum number of question-answer pairs to generate per target.",
    )
    parser.add_argument(
        "--max_qa_pairs",
        type=int,
        default=10,
        help="Maximum number of question-answer pairs to generate per target.",
    )
    parser.add_argument(
        "--max_attempts",
        type=int,
        default=5,
        help="Maximum attempts for question-answer pairs synthesis per target.",
    )
    parser.add_argument(
        "--propagation_count",
        type=int,
        default=10,
        help="Number of question-answer pairs to propagate to upper levels.",
    )
    parser.add_argument(
        "--max_iters",
        type=int,
        default=50,
        help="Maximum iterations for the synthesis agent.",
    )
    parser.add_argument(
        "--parallel_tool_calls",
        action="store_true",
        help="Enable parallel tool calls.",
    )
    parser.add_argument(
        "--random_seed",
        type=int,
        default=42,
        help="Random seed for reproducibility.",
    )
    
    # Server configuration
    parser.add_argument(
        "--studio_url",
        type=str,
        default=None,
        help="URL for the AgentScope studio server. If not provided, studio visualization is disabled.",
    )
    parser.add_argument(
        "--studio_project",
        type=str,
        default="haste_qa_synthesis",
        help="Project name for the AgentScope studio.",
    )
    
    # Output configuration
    parser.add_argument(
        "--output_path",
        type=str,
        default="qa_synthesis_results.json",
        help="Path to save the question-answer pairs synthesis results.",
    )
    
    return parser.parse_args()


class QASynthesisRunner:
    """Runner class for HASTE question-answer pairs synthesis."""

    def __init__(self, args: argparse.Namespace) -> None:
        """Initialize the question-answer pairs synthesis runner.
        
        Args:
            args (`argparse.Namespace`):
                Parsed command line arguments.
        """
        self.args = args
        
        # Server instances
        self.studio_server = None
        
        # State
        self.trajectory_state = None
        self.question_type_toolbook = None 
        self.all_qa_pairs = []
        self.synthesis_task_cancelled = False
        
        # Set up signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _build_initial_question_type_toolbook(self) -> QuestionTypeToolbook:
        """Build the initial question type tool book."""
        question_types = [
            QuestionType(
                name="single-hop", 
                description=(
                    "Single-hop questions require an AI memory system to retain a single piece of salient information " 
                    "and directly leverage it to answer the question."
                ),
            ),
            QuestionType(
                name="multi-hop", 
                description=(
                    "Multi-hop questions require an AI memory system to store multiple relevant pieces of information " 
                    "and integrate them through reasoning to produce an answer. " 
                    "These pieces of information may be scattered across different messages within the same session or " 
                    "distributed over multiple sessions." 
                ),
            ),
            QuestionType(
                name="temporal-reasoning", 
                description=(
                    "Temporal reasoning questions require an AI memory system to capture time-related information " 
                    "and perform chronological or temporal reasoning over stored memories to derive the correct answer."
                ),
            ),
            QuestionType(
                name="preference-inference", 
                description=(
                    "Preference inference questions require an AI memory system to infer user preferences " 
                    "based on observed behavior or interactions, and then use these preferences to answer the question."
                ),
            ),
            QuestionType(
                name="preference dynamic update", 
                description=(
                    "Preference dynamic update questions require an AI memory system to track and update changes in the user's " 
                    "preferences over time, reflecting the evolving user profile.\n"
                    "Examples (each includes a short chat log + a corresponding question):\n"
                    "- Interaction History:\n"
                    "  - User: I'm trying to eat vegetarian this month.\n"
                    "  - Assistant: Got it. Any exceptions?\n"
                    "  - User: Actually I started eating seafood again—fish and shrimp are okay.\n"
                    "  Question: If the user orders dinner today, should seafood dishes be considered acceptable?\n"
                    "- Interaction History:\n"
                    "  - User: I love intense HIIT workouts.\n"
                    "  - Assistant: How often do you do HIIT?\n"
                    "  - User: My knees have been acting up lately, so I switched to low-impact workouts.\n"
                    "  Question: Recommend a workout style for this week that matches the user's latest preference."
                ),
            ),
            QuestionType(
                name="preference-oriented generalization", 
                description=(
                    "Preference-oriented generalization questions require an AI memory system to generalize " 
                    "from observed user preferences and provide effective personalized recommendations in previously " 
                    "unseen scenarios.\n"
                    "Examples (each includes a short chat log + a corresponding question):\n"
                    "- Interaction History:\n"
                    "  - User: When I work outside, I need a quiet place with Wi-Fi and plenty of outlets.\n"
                    "  - Assistant: Any preference on seating?\n"
                    "  - User: A desk-like table is best; bar stools are uncomfortable.\n"
                    "  Question: The user is visiting a new city not mentioned before. What kind of café or workspace should you recommend?\n"
                    "- Interaction History:\n"
                    "  - User: I hate long flights.\n"
                    "  - Assistant: What do you like doing on trips?\n"
                    "  - User: Hiking, especially in mountains, and I'd rather do a weekend trip.\n"
                    "  Question: Suggest a weekend travel plan that fits the user's constraints without referencing any specific destination previously mentioned."
                ),
            ),
            QuestionType(
                name="relationship-related",
                description=(
                    "Relationship-related questions require an AI memory system to model social and relational information, " 
                    "such as who the user has interacted with, what activities were jointly involved in, and the nature of the user's " 
                    "relationships with other individuals." 
                ),
            ), 
            QuestionType(
                name="query-focused summarization",
                description=(
                    "Query-focused summarization questions require an AI memory system to summarize specific aspects of the user's trajectory, " 
                    "which may be conditioned on a particular topic or constrained to a specific time span.\n"
                    "Examples:\n"
                    "- In the last month, which places did the user visit or mention going to?\n"
                    "- In 2024, what health-related actions or interventions did the user take (e.g., exercise, diet changes, medication, checkups)?\n"
                    "- Summarize the user's stated constraints for choosing a product (e.g., budget, platform, weight)."
                ),
            ), 
            QuestionType(
                name="adversarial",
                description=(
                    "Adversarial questions require an AI memory system to recognize that the query cannot be answered " 
                    "based on the available historical information, and to appropriately abstain or signal insufficient evidence."
                ),
            ), 
        ]
        return QuestionTypeToolbook(question_types=question_types)

    def _signal_handler(self, signum: int, frame: Any) -> None:
        """Handle Ctrl+C signals."""
        if not self.synthesis_task_cancelled:
            print("\n⚠️  Synthesis task cancelled.")
            self.synthesis_task_cancelled = True
            try:
                loop = asyncio.get_running_loop()
                for task in asyncio.all_tasks(loop):
                    if not task.done():
                        task.cancel()
            except RuntimeError:
                pass
        else:
            self._shutdown()
            os._exit(0)

    def _shutdown(self) -> None:
        """Shutdown all servers and connections."""
        if self.studio_server is not None:
            print("🛑 Deactivating studio server...")
            self.studio_server.deactivate()

    def _load_trajectory(self) -> TrajectorySynthesisState:
        """Load trajectory state from pickle file.
        
        Returns:
            `TrajectorySynthesisState`:
                The loaded trajectory state object.
        """
        if not os.path.exists(self.args.trajectory_path):
            raise FileNotFoundError(
                f"Trajectory file '{self.args.trajectory_path}' is not found. "
                "Please provide a valid trajectory state pickle file."
            )
        
        with open(self.args.trajectory_path, "rb") as f:
            trajectory_state = pickle.load(f)
        
        print(f"✅ Loaded trajectory state")
        print(f"   - Person: {trajectory_state.person.name}")
        print(f"   - Total graphs: {len(trajectory_state.graphs)}")
        print(f"   - Total sessions: {len(trajectory_state.sessions)}")
        return trajectory_state

    def _setup_model(self) -> dict[str, Any]:
        """Set up the model and return agent keyword arguments.
        
        Returns:
            `dict[str, Any]`:
                Keyword arguments for the synthesis agent.
        """
        api_key = self.args.api_key or os.environ.get("OPENAI_API_KEY")
        api_base = self.args.api_base or os.environ.get("OPENAI_API_BASE")
        
        if not api_key:
            raise ValueError(
                "OpenAI API key is required. Provide via --api_key or OPENAI_API_KEY environment variable."
            )
        
        client_args = {}
        if api_base:
            client_args["base_url"] = api_base
        
        model = OpenAIChatModel(
            model_name=self.args.model,
            api_key=api_key,
            stream=False, 
            client_args=client_args,
            generate_kwargs={
                "temperature": self.args.temperature,
            },
        )
        
        print(f"✅ Model configured: {self.args.model}")
        print(f"   - Temperature: {self.args.temperature}")
        
        return {
            "model": model,
            "formatter": OpenAIChatFormatter(),
            "max_iters": self.args.max_iters,
            "parallel_tool_calls": self.args.parallel_tool_calls,
        }

    def _setup_studio(self) -> None:
        """Set up AgentScope studio server."""
        if self.args.studio_url:
            try:
                self.studio_server = StudioServer(
                    url=self.args.studio_url,
                    project=self.args.studio_project,
                )
                self.studio_server.activate()
                print(f"✅ Studio server connected: {self.args.studio_url}")
            except Exception as e:
                print(f"⚠️  Failed to connect to studio server: {e}")
                self.studio_server = None

    def _get_message_map(self) -> dict[str, Message]:
        """Build a message map from all sessions.
        
        Returns:
            `dict[str, Message]`:
                A mapping from message ID to Message object.
        """
        message_map = {}
        for session in self.trajectory_state.sessions.values():
            for message in session.messages:
                message_map[message.id] = message
        return message_map

    def _collect_events_by_type(
        self,
    ) -> tuple[dict[str, tuple[Event, int]], dict[str, tuple[Event, int]]]:
        """Collect events categorized by their output type with their depths.
        
        Uses BFS from the person root node to calculate depths.
        
        Returns:
            `tuple[dict[str, tuple[Event, int]], dict[str, tuple[Event, int]]]`:
                A tuple containing the mapping from event id to the corresponding event instance and depth 
                for session events and graph events respectively.
        """
        session_events = {}
        graph_events = {}
        
        person_id = self.trajectory_state.person.id
        queue = deque([(person_id, 1)])
        
        while queue:
            node_id, depth = queue.popleft()
            child_id = self.trajectory_state.get_child_node_id(node_id)
            
            if child_id is None:
                continue
            
            if child_id.startswith("graph_"):
                graph = self.trajectory_state.get_graph_by_id(child_id)
                if graph is None:
                    continue
                for event in graph.events:
                    if event.state != "expanded" or event.output is None:
                        continue
                    if isinstance(event.output, Session):
                        session_events[event.id] = (event, depth)
                    else:
                        graph_events[event.id] = (event, depth)
                    queue.append((event.id, depth + 1))
        
        return session_events, graph_events

    async def _synthesize_for_event_with_session(
        self,
        event: Event,
        level: int,
        agent_kwargs: dict[str, Any],
        scheduler: QANotebookStateSchedulerBase,
        message_map: dict[str, Message],
    ) -> list[QuestionAnswerPair]:
        """Synthesize question-answer pairs for an event with session output.
        
        Args:
            event (`Event`):
                The event with session output.
            level (`int`):
                The depth of the event in the hierarchy.
            agent_kwargs (`dict[str, Any]`):
                Agent configuration arguments.
            scheduler (`QANotebookStateSchedulerBase`):
                The question-answer pairs synthesis scheduler.
            message_map (`dict[str, Message]`):
                Mapping from message ID to Message.
        
        Returns:
            `list[QuestionAnswerPair]`:
                The synthesized question-answer pairs.
        """
        print(f"   📝 Processing event (depth={level}): {event.title[:50]}...")
        
        min_count, max_count = scheduler.get_qa_count_range(event, level=level)
        max_attempts = scheduler.get_max_attempts(event, level=level)
        
        qa_notebook = QANotebook(
            target_object=event,
            question_type_toolbook=self.question_type_toolbook,
            qa_count_range=(min_count, max_count),
            max_attempts=max_attempts,
            qa_to_hint=DefaultQAToHint(),
            message_map=message_map,
            **agent_kwargs,
        )
        
        agent_name = f"agent_{shortuuid.uuid()}"
        agent = SynthesisAgent(
            name=agent_name,
            sys_prompt=QA_SYSTEM_PROMPT,
            notebook=qa_notebook,
            **agent_kwargs,
        )
        
        task_instruction = scheduler.get_qa_synthesis_task_instruction(
            target=event,
            level=level,
            message_map=message_map,
        )
        
        try:
            _ = await agent(
                msg=Msg(
                    "user", 
                    task_instruction, 
                    "user"
                )
            )
        except asyncio.CancelledError:
            pass
        
        qa_pairs = qa_notebook.current_state.qa_pairs
        print(f"      ✓ Generated {len(qa_pairs)} question-answer pairs")
        return qa_pairs

    async def _synthesize_for_event_with_graph(
        self,
        event: Event,
        level: int,
        child_qa_pairs_by_event: dict[str, list[QuestionAnswerPair]],
        agent_kwargs: dict[str, Any],
        scheduler: QANotebookStateSchedulerBase,
    ) -> list[QuestionAnswerPair]:
        """Synthesize question-answer pairs for an event with graph output by composing child question-answer pairs.
        
        Args:
            event (`Event`):
                The event with graph output.
            level (`int`):
                The depth of the event in the hierarchy.
            child_qa_pairs_by_event (`dict[str, list[QuestionAnswerPair]]`):
                Question-answer pairs from child events, grouped by child event ID.
            agent_kwargs (`dict[str, Any]`):
                Agent configuration arguments.
            scheduler (`QANotebookStateSchedulerBase`):
                The question-answer pairs synthesis scheduler.
        
        Returns:
            `list[QuestionAnswerPair]`:
                The synthesized question-answer pairs.
        """
        print(f"   📝 Composing for event (depth={level}): {event.title[:50]}...")
        
        if not child_qa_pairs_by_event:
            print(f"      ⚠️ No child question-answer pairs available for composition")
            return []
        
        min_count, max_count = scheduler.get_qa_count_range(event, level=level)
        max_attempts = scheduler.get_max_attempts(event, level=level)
        
        all_child_qa_pairs = []
        for qa_list in child_qa_pairs_by_event.values():
            all_child_qa_pairs.extend(qa_list)
        
        qa_notebook = QANotebook(
            target_object=event,
            question_type_toolbook=self.question_type_toolbook,
            qa_count_range=(min_count, max_count),
            max_attempts=max_attempts,
            qa_to_hint=DefaultQAToHint(),
            child_qa_pairs=all_child_qa_pairs,
            **agent_kwargs,
        )
        
        agent_name = f"agent_{shortuuid.uuid()}"
        agent = SynthesisAgent(
            name=agent_name,
            sys_prompt=QA_SYSTEM_PROMPT,
            notebook=qa_notebook,
            **agent_kwargs,
        )
        
        task_instruction = scheduler.get_qa_synthesis_task_instruction(
            target=event,
            level=level,
            sub_questions=child_qa_pairs_by_event,
        )
        
        try:
            _ = await agent(
                msg=Msg(
                    "user", 
                    task_instruction, 
                    "user"
                )
            )
        except asyncio.CancelledError:
            pass
        
        qa_pairs = qa_notebook.current_state.qa_pairs
        print(f"      ✓ Composed {len(qa_pairs)} QA pairs")
        return qa_pairs

    async def _synthesize_for_dimension(
        self,
        dimension_name: str,
        dimension: PersonDimensionBase,
        agent_kwargs: dict[str, Any],
        scheduler: QANotebookStateSchedulerBase,
        message_map: dict[str, Message],
    ) -> list[QuestionAnswerPair]:
        """Synthesize question-answer pairs for a person dimension.
        
        Args:
            dimension_name (`str`):
                The name of the dimension.
            dimension (`PersonDimensionBase`):
                The person dimension object.
            agent_kwargs (`dict[str, Any]`):
                Agent configuration arguments.
            scheduler (`QANotebookStateSchedulerBase`):
                The question-answer pairs synthesis scheduler.
            message_map (`dict[str, Message]`):
                Mapping from message ID to Message.
        
        Returns:
            `list[QuestionAnswerPair]`:
                The synthesized question-answer pairs.
        """
        print(f"   📝 Processing dimension: {dimension_name}...")
        
        # Check if dimension has any connections (mentioned in messages)
        has_connections = False
        for str_field in dimension.get_string_fields():
            tracked_attr = getattr(dimension, str_field)
            if tracked_attr.has_connections:
                has_connections = True
                break
        if not has_connections:
            for list_field in dimension.get_list_fields():
                tracked_attrs = getattr(dimension, list_field)
                for tracked_attr in tracked_attrs:
                    if tracked_attr.has_connections:
                        has_connections = True
                        break
                if has_connections:
                    break
        
        if not has_connections:
            print(f"      ⚠️ Dimension '{dimension_name}' has no message connections")
            return []
        
        min_count, max_count = scheduler.get_qa_count_range(dimension, level=1)
        max_attempts = scheduler.get_max_attempts(dimension, level=1)
        
        qa_notebook = QANotebook(
            target_object=dimension,
            question_type_toolbook=self.question_type_toolbook,
            qa_count_range=(min_count, max_count),
            max_attempts=max_attempts,
            qa_to_hint=DefaultQAToHint(),
            message_map=message_map,
            **agent_kwargs,
        )
        
        agent_name = f"agent_{shortuuid.uuid()}"
        agent = SynthesisAgent(
            name=agent_name,
            sys_prompt=QA_SYSTEM_PROMPT,
            notebook=qa_notebook,
            **agent_kwargs,
        )
        
        task_instruction = scheduler.get_qa_synthesis_task_instruction(
            target=dimension,
            level=1,
            message_map=message_map,
        )
        
        try:
            _ = await agent(
                msg=Msg(
                    "user", 
                    task_instruction, 
                    "user"
                )
            )
        except asyncio.CancelledError:
            pass
        
        qa_pairs = qa_notebook.current_state.qa_pairs
        print(f"      ✓ Generated {len(qa_pairs)} QA pairs")
        return qa_pairs

    async def _synthesize_for_person(
        self,
        person: Person,
        dimension_qa_map: dict[str, list[QuestionAnswerPair]],
        agent_kwargs: dict[str, Any],
        scheduler: QANotebookStateSchedulerBase,
    ) -> list[QuestionAnswerPair]:
        """Synthesize question-answer pairs for the person by composing dimension question-answer pairs.
        
        Args:
            person (`Person`):
                The person model.
            dimension_qa_map (`dict[str, list[QuestionAnswerPair]]`):
                Mapping from dimension name to question-answer pairs.
            agent_kwargs (`dict[str, Any]`):
                Agent configuration arguments.
            scheduler (`QANotebookStateSchedulerBase`):
                The question-answer pairs synthesis scheduler.
        
        Returns:
            `list[QuestionAnswerPair]`:
                The synthesized question-answer pairs.
        """
        print(f"   📝 Composing for person: {person.name}...")
        
        if not dimension_qa_map:
            print(f"      ⚠️ No dimension question-answer pairs available for composition")
            return []
        
        min_count, max_count = scheduler.get_qa_count_range(person, level=0)
        max_attempts = scheduler.get_max_attempts(person, level=0)
        
        all_child_qa_pairs = []
        for qa_list in dimension_qa_map.values():
            all_child_qa_pairs.extend(qa_list)
        
        qa_notebook = QANotebook(
            target_object=person,
            question_type_toolbook=self.question_type_toolbook,
            qa_count_range=(min_count, max_count),
            max_attempts=max_attempts,
            qa_to_hint=DefaultQAToHint(),
            child_qa_pairs=all_child_qa_pairs,
            **agent_kwargs,
        )
        
        agent_name = f"agent_{shortuuid.uuid()}"
        agent = SynthesisAgent(
            name=agent_name,
            sys_prompt=QA_SYSTEM_PROMPT,
            notebook=qa_notebook,
            **agent_kwargs,
        )
        
        task_instruction = scheduler.get_qa_synthesis_task_instruction(
            target=person,
            level=0,
            sub_questions=dimension_qa_map,
        )
        
        try:
            _ = await agent(
                msg=Msg(
                    "user", 
                    task_instruction, 
                    "user"
                )
            )
        except asyncio.CancelledError:
            pass
        
        qa_pairs = qa_notebook.current_state.qa_pairs
        print(f"      ✓ Composed {len(qa_pairs)} question-answer pairs")
        return qa_pairs

    async def run(self) -> None:
        """Run the question-answer pairs synthesis pipeline."""
        # Load trajectory
        self.trajectory_state = self._load_trajectory()
        
        # Set up model
        agent_kwargs = self._setup_model()
        
        # Set up studio server
        self._setup_studio()
        
        # Initialize the global question type toolbook (pre-populated with canonical types)
        self.question_type_toolbook = self._build_initial_question_type_toolbook()
        
        # Create the scheduler
        scheduler = ConstantQANotebookStateScheduler(
            min_qa_pairs=self.args.min_qa_pairs,
            max_qa_pairs=self.args.max_qa_pairs,
            max_attempts=self.args.max_attempts,
            total_select=self.args.propagation_count,
            random_seed=self.args.random_seed,
        )
        
        print(f"✅ Scheduler configured:")
        print(f"   - Min QA pairs: {self.args.min_qa_pairs}")
        print(f"   - Max QA pairs: {self.args.max_qa_pairs}")
        print(f"   - Max attempts: {self.args.max_attempts}")
        print(f"   - Random propagation count: {self.args.propagation_count}")
        
        # Build message map
        message_map = self._get_message_map()
        print(f"✅ Built message map with {len(message_map)} messages")
        
        # Collect events by type with depths
        session_events_map, graph_events_map = self._collect_events_by_type()
        print(f"✅ Collected {len(session_events_map)} session events and {len(graph_events_map)} graph events")
        
        print("\n" + "=" * 60)
        print("🚀 Starting QA synthesis...")
        print("=" * 60 + "\n")
        
        # Store QA pairs by event/dimension for composition
        event_qa_map = {}
        event_random_selected_map = {}
        dimension_qa_map = {}
        
        # Sort session events by start time for processing order
        sorted_session_events = sorted(
            session_events_map.values(),
            key=lambda x: datetime.fromisoformat(x[0].started_at),
        )
        # Sort graph events by their depths
        sorted_graph_events = sorted(
            graph_events_map.values(),
            key=lambda x: -x[1],
        )
        
        try:
            # Phase 1: Synthesize question-answer pairs for person dimensions
            if not self.synthesis_task_cancelled:
                print("📋 Phase 1: Synthesizing question-answer pairs for person dimensions")
                print("-" * 50)
                person = self.trajectory_state.person
                for dimension_name in person.get_dimension_names():
                    if self.synthesis_task_cancelled:
                        break
                    dimension = person.get_dimension(dimension_name)
                    qa_pairs = await self._synthesize_for_dimension(
                        dimension_name, 
                        dimension, 
                        agent_kwargs, 
                        scheduler, 
                        message_map, 
                    )
                    if qa_pairs:
                        dimension_qa_map[dimension_name] = qa_pairs
                        self.all_qa_pairs.extend(qa_pairs)
                
                if not self.synthesis_task_cancelled:
                    print(f"\n✅ Phase 1 complete: {len(self.all_qa_pairs)} total question-answer pairs\n")
            
            # Phase 2: Synthesize question-answer pairs for person (compose from dimensions)
            if not self.synthesis_task_cancelled:
                print("📋 Phase 2: Composing question-answer pairs for person profile")
                print("-" * 50)

                person = self.trajectory_state.person
                qa_pairs = await self._synthesize_for_person(
                    person, 
                    dimension_qa_map, 
                    agent_kwargs, 
                    scheduler, 
                )
                self.all_qa_pairs.extend(qa_pairs)

                if not self.synthesis_task_cancelled:
                    print(f"\n✅ Phase 2 complete: {len(self.all_qa_pairs)} total question-answer pairs\n")

            # Phase 3: Synthesize question-answer pairs for events with session outputs
            print("📋 Phase 3: Synthesizing question-answer pairs for session-level events")
            print("-" * 50)
            for event, depth in sorted_session_events:
                if self.synthesis_task_cancelled:
                    break
                qa_pairs = await self._synthesize_for_event_with_session(
                    event, 
                    depth, 
                    agent_kwargs, 
                    scheduler, 
                    message_map, 
                )
                event_qa_map[event.id] = qa_pairs
                self.all_qa_pairs.extend(qa_pairs)
            
            if not self.synthesis_task_cancelled:
                total_phase1 = sum(len(v) for v in event_qa_map.values())
                print(f"\n✅ Phase 3 complete: {total_phase1} question-answer pairs generated\n")
            
            # Phase 4: Synthesize question-answer pairs for events with graph outputs
            if not self.synthesis_task_cancelled and graph_events_map:
                print("📋 Phase 4: Composing question-answer pairs for graph-level events")
                print("-" * 50)
                for event, depth in sorted_graph_events:
                    if self.synthesis_task_cancelled:
                        break
                    
                    # Collect child question-answer pairs from child events, grouped by child event ID
                    child_event_ids = {e.id for e in event.output.events}
                    child_qa_pairs_by_event = {}
                    for child_id in child_event_ids:
                        if child_id in event_qa_map:
                            child_qa_list = event_qa_map[child_id]
                            child_qa_pairs_by_event[child_id] = (
                                child_qa_list + event_random_selected_map.get(child_id, [])
                            ) 
                    
                    qa_pairs = await self._synthesize_for_event_with_graph(
                        event, 
                        depth, 
                        child_qa_pairs_by_event, 
                        agent_kwargs, 
                        scheduler, 
                    )
                    event_qa_map[event.id] = qa_pairs
                    self.all_qa_pairs.extend(qa_pairs)

                    # Add randomly-selected question-answer pairs for exploration
                    child_qa_pairs = []
                    for event_child_qa_pairs in child_qa_pairs_by_event.values():
                        child_qa_pairs.extend(event_child_qa_pairs)
                    candidates = scheduler.get_propagation_candidates(
                        child_qa_pairs,
                        reference_timestamp=None,
                    )
                    selected, _ = scheduler.random_select_for_propagation(
                        candidates,
                        reference_timestamp=None,
                        level=depth,
                    ) 
                    event_random_selected_map[event.id] = selected
                
                if not self.synthesis_task_cancelled:
                    print(f"\n✅ Phase 4 complete: {len(self.all_qa_pairs)} total question-answer pairs\n")
            
            # Postprocess the session data 
            new_sessions = merge_parallel_sessions(
                self.trajectory_state.get_sessions(),
                check_messages=True,
            )
            new_sessions = unify_message_names(
                new_sessions,
                name=self.trajectory_state.person.name,
                role="user",
                in_place=True, 
            )

            # Save results
            results = {
                "person": self.trajectory_state.person.model_dump(), 
                "sessions": [
                    session.model_dump()
                    for session in new_sessions
                ], 
                "graphs": [
                    graph.model_dump()
                    for graph in self.trajectory_state.graphs.values() 
                ],
                "question_type_toolbook": self.question_type_toolbook.model_dump(),
            }
            
            with open(self.args.output_path, "w", encoding="utf-8") as f:
                json.dump(
                    results, 
                    f, 
                    ensure_ascii=False, 
                    indent=4,
                )
            print(f"💾 Results saved to {self.args.output_path}")
            
        except asyncio.CancelledError:
            pass
        except KeyboardInterrupt:
            pass
        
        # Print summary
        print("\n" + "=" * 60)
        if self.synthesis_task_cancelled:
            print("⏸️  Synthesis cancelled")
        else:
            print("✅ Question-answer pairs synthesis complete")
        print("=" * 60)
        print(f"   Total question-answer pairs: {len(self.all_qa_pairs)}")
        print(f"   Question types: {self.question_type_toolbook.total_question_types}")
        print(f"   Question-answer pairs by type: {self.question_type_toolbook.get_stats()}")


async def main() -> None:
    """Main entry point."""
    args = parse_args()
    
    print("\n" + "=" * 60)
    print("KEME: Knowledge-Guided Experience Synthesis for Evolving Memory")
    print("=" * 60 + "\n")
    
    runner = QASynthesisRunner(args)
    await runner.run()


if __name__ == "__main__":
    asyncio.run(main())
