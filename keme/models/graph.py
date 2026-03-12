from __future__ import annotations
from datetime import datetime
import shortuuid
from pydantic import (
    BaseModel, 
    Field, 
    field_validator,
    model_validator, 
    ValidationInfo,
    PrivateAttr, 
    computed_field, 
)
from datetime import datetime 
from ..utils import get_timestamp
from collections import deque 
from .session import Session
from ._constants import NO_SIDE_NOTE
from typing import Literal, Self


NO_COMPATIBILITY_CONTEXT = "[NO COMPATIBILITY CONTEXT PROVIDED]"


class Requirement(BaseModel):
    """
    A constraint or requirement that guides event expansion during trajectory synthesis.
    
    Requirements selectively pass key information from ancestor events, predecessor siblings, 
    the global Person profile, or agent-generated constraints. They eliminate the need to 
    include complete information from all predecessor nodes when expanding events, serving 
    as information summaries that extract essential constraints, goals, and dependencies.
    """
    
    name: str = Field(
        description=(
            "The requirement name, should be concise, descriptive and not "
            "exceed 20 words."
        ),
    )
    id: str = Field(
        default_factory=lambda: f"requirement_{shortuuid.uuid()}",
        description="Unique identifier for the requirement.",
    )
    description: str = Field(
        description=(
            "Detailed description of the requirement, constraint, or goal that must be satisfied "
            "during event expansion. This description serves as a generation constraint that guides "
            "the creation of sub-events or conversation sessions. The description should exceed 50 words."
        ),
    )
    from_source: str = Field(
        description=(
            "Source identifier specifying where this requirement originates. "
            "Must be one of the following:\n\n"
            "- '<ancestor_event_id>': Requirement inherited from an ancestor event. "
            "The ancestor event can be the direct parent event or any "
            "higher-level ancestor event in the hierarchy. When inheriting a requirement from an "
            "ancestor event, set `from_source` to that ancestor event's ID.\n\n"
            "- '<sibling_event_id>': Requirement from a predecessor sibling event in the same "
            "temporal graph. When adding a requirement from a sibling event, set `from_source` to "
            "that sibling event's ID. A sibling event A can add requirements to event B if there exists an edge " 
            "from A to B, expressing dependencies like resource conflicts, scheduling constraints, or causal relationships.\n\n"
            "- '<person_id>': Constraint from the global user profile/root node, reflecting the current "
            "state of user preferences, habits, or long-term goals. When adding a requirement from the "
            "person profile, set `from_source` to the person's ID.\n\n"
            "- '<agent_id>': Requirement flexibly added by yourself during "
            "generation. When adding a requirement from yourself, set `from_source` to your own "
            "**ID NUMBER**. You can introduce diverse types of requirements, including:\n"
            "  * Global state changes: modifications to the **Person object's attributes** "
            "(the global root node), such as:\n"
            "    - `habits`: 'User developed a daily meditation habit'\n"
            "    - `likes`: 'User now enjoys public speaking'\n"
            "    - `dislikes`: 'User dislikes working overtime'\n"
            "    - `occupation`: 'User promoted to Senior Engineer'\n"
            "    - `education`: 'User completed Master's degree in Computer Science'\n"
            "    - `nationality`: 'User obtained citizenship in a new country'\n"
            "    - `location`: 'User relocated from New York to San Francisco'\n"
            "    - `personalities`: 'User became more confident'\n"
            "    - `values`: 'User now prioritizes work-life balance'\n"
            "    - `long_term_goals`: 'User shifted focus from IC to management'\n"
            "    These changes should be logged in Person.operations for tracking.\n"
            "  * New goals: emergent objectives arising from events (e.g., 'Must follow up "
            "on job interview', 'Need to maintain new habit')\n"
            "  * Logical implications: derived constraints (e.g., 'If event A happened, "
            "then B must address it', 'Project deadline creates time pressure')\n"
            "  * Conflict resolutions: adjustments to maintain consistency (e.g., 'Cannot "
            "schedule overlapping meetings', 'Budget constraint after purchase')\n"
            "  * Narrative requirements: story coherence needs (e.g., 'Character development "
            "should continue', 'Relationship dynamics must evolve')"
        ),
        alias="from",
    )
    source_evidence: str = Field(
        description=(
            "Evidence or snippet from the originating source that justifies this requirement. "
            "Store the exact excerpt, conversation turn, or data fragment taken from the ancestor event, "
            "person profile, or agent analysis."
        ),
    )
    side_note: str = Field(
        default=NO_SIDE_NOTE,
        description=(
            "Commentary or justification for this requirement, explaining why "
            "it exists and how it impacts the event structure. You may also "
            "reflect on how this requirement contributes to the overall objectives "
            "of the synthesis task."
        ),
    )
    created_at: str = Field(
        default_factory=get_timestamp,
        description="Timestamp of creation of the requirement object **in real-world system time**.",
    )

    @field_validator("from_source")
    @classmethod
    def validate_from_source(cls, v: str) -> str:
        """Validate the source identifier of the requirement."""
        if (
            not v.startswith("event_") and 
            not v.startswith("person_") and 
            not v.startswith("agent_")
        ):
            raise ValueError(
                "The source identifier of the requirement is invalid. "
                "It must start with 'event_', 'person_', or 'agent_'."
            )
        return v
    
    @computed_field
    @property
    def origin_type(self) -> str:
        """Return the origin type of the requirement."""
        if self.from_source.startswith("event_"):
            return "Event"
        elif self.from_source.startswith("person_"):
            return "Person Profile"
        else:
            return "Agent"

    def to_markdown(self, include_side_note: bool = False, level: int = 0) -> str:
        """
        Convert the requirement to MarkDown format.
        
        Args:
            include_side_note (`bool`, defaults to `False`):
                Whether to include side note of the requirement object.
            level (`int`, defaults to `0`):
                The level of the requirement in the hierarchy. 
        """
        indent = "\t" * level
        markdown_strs = [
            f"{indent}- {self.name} (id: {self.id})",
            f"{indent}\t- Description: {self.description}",
            f"{indent}\t- Origin Type: {self.origin_type}",
            f"{indent}\t- Origin ID: {self.from_source}",
            f"{indent}\t- Source Evidence: {self.source_evidence}",
            f"{indent}\t- Created At In Real-World System Time: {self.created_at}",
        ]
        if include_side_note:
            markdown_strs.append(f"{indent}\t- Side Note: {self.side_note}")
        return "\n".join(markdown_strs)


class Event(BaseModel):
    """
    Represent a single event in the hierarchical trajectory structure.
    
    Events can be expanded into sub-events recursively until reaching the
    dialogue generation level.
    """

    id: str = Field(
        default_factory=lambda: f"event_{shortuuid.uuid()}",
        description="Unique event identifier.",
    )
    title: str = Field(
        description=(
            "Short, descriptive event title (5-20 words). Should clearly "
            "indicate what happens during this event."
        ),
    )
    started_at: str = Field(
        description=(
            "Event start time in ISO 8601 format (YYYY-MM-DD HH:MM:SS). "
            "Must be >= parent's start time."
        ),
    )
    ended_at: str = Field(
        description=(
            "Event end time in ISO 8601 format (YYYY-MM-DD HH:MM:SS). "
            "Must be <= parent's end time and > started_at."
        ),
    )
    summary: str = Field(
        description=(
            "Event summary. " 
            "Should be detailed enough to understand the context and outcomes of the event."
        ),
    )
    requirements: list[Requirement] = Field(
        default_factory=list,
        description=(
            "List of constraints inherited from parent, siblings, or global "
            "context, plus any additional requirements added by the agent."
        ),
    )
    state: Literal["to_expand", "expanding", "expanded"] = Field(
        default="to_expand",
        description="The state of the event.",
    )
    side_note: str = Field(
        default=NO_SIDE_NOTE,
        description=(
            "Optional commentary explaining the rationale behind this event, "
            "its significance in the trajectory, or design decisions. You may also "
            "reflect on how this event contributes to the overall objectives of the "
            "synthesis task."
        ),
    )
    created_at: str = Field(
        default_factory=get_timestamp,
        description="Timestamp of creation of the event object **in real-world system time**.",
    )
    finished_at: str | None = Field(
        default=None,
        description="Timestamp of completion of expansion of the event object **in real-world system time**.",
    )
    _output: TemporalEventGraph | Session | None = PrivateAttr(default=None)
    _grounded_sessions: list[Session] = PrivateAttr(default_factory=list)
    _compatibility_context: str = PrivateAttr(default=NO_COMPATIBILITY_CONTEXT)

    @computed_field
    @property
    def output(self) -> TemporalEventGraph | Session | None:
        """Return the output of the event.
        
        The output of the event, which can be a temporal sub-event graph or a session.
        If the event is expanded into a temporal sub-event graph, the output should be a TemporalEventGraph object.
        If the event is expanded into a session, the output should be a Session object.
        If the event is not expanded, the output should be None.
        """
        if self._output is None:
            return None
        return self._output.model_copy(deep=True)

    @field_validator("started_at")
    @classmethod
    def validate_started_at(cls, v: str) -> str:
        """Validate that `started_at` is a valid ISO 8601 string."""
        try:
            _ = datetime.fromisoformat(v)
        except ValueError:
            raise ValueError(
                f"The starting time '{v}' is not in a valid format. "
                "Please use the format YYYY-MM-DD HH:MM:SS, for example: "
                "'2024-06-01 09:30:00'."
            )
        return v

    @field_validator("ended_at")
    @classmethod
    def validate_time_order(cls, v: str, info: ValidationInfo) -> str:
        """Validate that `ended_at` is after `started_at`."""
        start = datetime.fromisoformat(info.data["started_at"])
        try:
            end = datetime.fromisoformat(v)
        except ValueError:
            raise ValueError(
                f"The ending time '{v}' is not in a valid format. "
                "Please use the format YYYY-MM-DD HH:MM:SS, for example: "
                "'2024-06-01 09:30:00'."
            )
        if end <= start:
            raise ValueError(
                f"The ending time of the event ({v}) must be after "
                f"the starting time ({info.data['started_at']}). Please ensure "
                "the event has a valid time range."
            )   
        return v

    def complete(self, output: TemporalEventGraph | Session) -> None:
        """Complete the event with the output."""
        self._output = output
        self.finished_at = get_timestamp()
        self.state = "expanded"
    
    def reset(self) -> None:
        """Reset the event."""
        self._output = None
        self.finished_at = None
        if self.state == "expanded":
            self.state = "expanding"

    def add_grounded_session(self, session: Session) -> None:
        """Add a grounded (pre-existing) session to this event.
        
        Grounded sessions are pre-existing session data that have been
        assigned to this event. They are stored in chronological order based on their start time.
        
        Args:
            session (`Session`):
                The session to add to the grounded sessions list.
                The session will be inserted in chronological order.
        """
        sess_start = datetime.fromisoformat(session.started_at)
        sessions = self._grounded_sessions

        left, right = 0, len(sessions)
        while left < right:
            mid = (left + right) // 2
            mid_start = datetime.fromisoformat(sessions[mid].started_at)
            if sess_start < mid_start:
                right = mid
            else:
                left = mid + 1
        sessions.insert(left, session)

    @computed_field
    @property
    def grounded_sessions(self) -> list[Session]:
        """Get all grounded sessions assigned to this event.
        
        Returns:
            `list[Session]`:
                A list of grounded sessions in chronological order
                based on their start time.
        """
        return self._grounded_sessions.copy()

    @computed_field
    @property
    def num_grounded_sessions(self) -> int:
        """Get the number of grounded sessions assigned to this event.
        
        Returns:
            `int`:
                The number of grounded sessions.
        """
        return len(self._grounded_sessions)

    @computed_field
    @property
    def has_grounded_sessions(self) -> bool:
        """Check if this event has any grounded sessions.
        
        Returns:
            `bool`:
                True if the event has grounded sessions, False otherwise.
        """
        return len(self._grounded_sessions) > 0

    @computed_field
    @property
    def compatibility_context(self) -> str | None:
        """Get the compatibility context of this event.
        
        Returns:
            `str | None`:
                The compatibility context if set, None otherwise.
        """
        return self._compatibility_context
    
    def overwrite_compatibility_context(self, context: str) -> None:
        """Overwrite the compatibility context of this event.

        Args:
            context (`str`):
                The new compatibility context.
        """
        context = context or NO_COMPATIBILITY_CONTEXT
        self._compatibility_context = context

    def append_compatibility_context(self, context: str, separator: str = "\n\n") -> None:
        """Append additional context to the existing compatibility context.
        
        If no compatibility context exists, this sets it to the provided context.
        Otherwise, it appends the new context with the specified separator.
        
        Args:
            context (`str`):
                The context to append.
            separator (`str`, defaults to `"\\n\\n"`):
                The separator to use when appending to existing context.
        """
        if self._compatibility_context is NO_COMPATIBILITY_CONTEXT:
            self._compatibility_context = context
        elif context:
            self._compatibility_context = f"{self._compatibility_context}{separator}{context}"

    def to_markdown(
        self, 
        include_side_note: bool = False, 
        include_output: bool = False,
        level: int = 0,
    ) -> str:
        """
        Convert the event to MarkDown format.
        
        Args:
            include_side_note (`bool`, defaults to `False`):
                Whether to include side note of the event object.
            include_output (`bool`, defaults to `False`):
                Whether to include the output (a session or a temporal sub-event graph) of the event.
            level (`int`, defaults to `0`):
                The level of the event in the hierarchy.
        """
        indent = "\t" * level
        status_map = {
            "to_expand": "- [ ] [To Expand]",
            "expanding": "- [ ] [Expanding]",
            "expanded": "- [x] [Expanded]",
        }
        markdown_strs = [
            f"{indent}{status_map[self.state]} {self.title} (id: {self.id})", 
            f"{indent}\t- Temporal Span: {self.started_at} - {self.ended_at}",
            f"{indent}\t- Summary: {self.summary}",
            f"{indent}\t- Created At In Real-World System Time: {self.created_at}",
        ]
        if include_side_note:
            markdown_strs.append(f"{indent}\t- Side Note: {self.side_note}")

        markdown_strs.extend(
            [
                f"{indent}\t- Requirements",
                *[
                    requirement.to_markdown(
                        include_side_note=include_side_note, 
                        level=level + 2,
                    )
                    for requirement in self.requirements
                ],
            ]
        )

        # Add grounded sessions count
        num_grounded = self.num_grounded_sessions
        markdown_strs.append(f"{indent}\t- Grounded Sessions Count: {num_grounded}")
        markdown_strs.append(f"{indent}\t- Compatibility Context: {self.compatibility_context}")

        if self.state == "expanded":
            if self._output is None:
                raise AssertionError(
                    "The output of the event is None, but the event is marked as expanded. "
                    "Please ensure the output is not None when the event is marked as expanded."
                )
            markdown_strs.append(
                f"{indent}\t- Finished At In Real-World System Time: {self.finished_at}"
            )
            if include_output:
                if isinstance(self._output, TemporalEventGraph):
                    # For any sub-events, their outputs are not included in the parent event.
                    # This can avoid continuous recursive calls of `to_markdown` which can lead to context overflow.
                    markdown_strs.extend(
                        [
                            f"{indent}\t- Temporal Sub-event Graph",
                            self._output.to_markdown(
                                include_side_note=include_side_note,
                                level=level + 2,
                                include_output=False, 
                            ),
                        ]
                    )
                else:
                    markdown_strs.extend(
                        [
                            f"{indent}\t- Session",
                            self._output.to_markdown(
                                include_side_note=include_side_note,
                                level=level + 2,
                            ),
                        ]
                    )

        return "\n".join(markdown_strs)


class Edge(BaseModel):
    """
    Represent a temporal dependency between two events in the temporal event graph.
    
    Edges define the expansion order and dependencies in the temporal event graph.
    """

    id: str = Field(
        default_factory=lambda: f"edge_{shortuuid.uuid()}",
        description="Unique edge identifier.",
    )
    name: str = Field(
        description=(
            "Name of the edge. The name should clearly reflect why the target "
            "event depends on the source event. Do not exceed 20 words."
        ),
    )
    from_event: str = Field(
        description=(
            "Source event ID representing the prerequisite event. This event must "
            "start earlier than the target event. "
            "The edge creates a temporal dependency where the source event establishes "
            "conditions, outcomes, or constraints that the target event builds upon or responds to. "
            "For example, 'Job Interview' (source event) must occur before 'Follow-up Email' (target event)."
        ),
        alias="source_event_id",
    )
    to_event: str = Field(
        description=(
            "Target event ID representing the dependent event. This event must start "
            "after the source event. "
            "The target event may rely on outcomes from the source event, respond to "
            "its results, or logically follow it in the narrative sequence. For example, "
            "'Project Kickoff' (target event) depends on 'Team Formation' (source event) being completed."
        ),
        alias="target_event_id",
    )
    side_note: str = Field(
        default=NO_SIDE_NOTE,
        description=(
            "Optional commentary on why this edge exists, its significance " 
            "in the temporal event graph, or design decisions. You may also "
            "reflect on how this dependency contributes to the overall objectives "
            "of the synthesis task."
        ),
    )
    created_at: str = Field(
        default_factory=get_timestamp,
        description="Timestamp of creation of the edge object **in real-world system time**.",
    )

    def to_markdown(self, include_side_note: bool = False, level: int = 0) -> str:
        """
        Convert the edge to MarkDown format.
        
        Args:
            include_side_note (`bool`, defaults to `False`):
                Whether to include side note of the edge object.
            level (`int`, defaults to `0`):
                The level of the edge in the hierarchy.
        """
        indent = "\t" * level
        markdown_strs = [
            f"{indent}- {self.name} (id: {self.id})",
            f"{indent}\t- Source Event: {self.from_event}",
            f"{indent}\t- Target Event: {self.to_event}",
            f"{indent}\t- Created At In Real-World System Time: {self.created_at}",
        ]
        if include_side_note:
            markdown_strs.append(f"{indent}\t- Side Note: {self.side_note}")
        return "\n".join(markdown_strs)   


class TemporalEventGraph(BaseModel):
    """
    A directed acyclic graph (DAG) organizing events at a specific level.
    
    The graph defines temporal ordering and dependencies between sibling events
    that share the same parent.
    """

    id: str = Field(
        default_factory=lambda: f"graph_{shortuuid.uuid()}",
        description="Unique temporal graph identifier.",
    )
    parent_id: str | None = Field(
        default=None,
        description=(
            "Parent event's ID. `None` if this is the top-level graph "
            "(directly under the Person root)."
        ),
    )
    # Note that we don't use `default_factory` here because the list of events must be non-empty.
    events: list[Event] = Field(
        description="All events in this graph at the same hierarchical level.",
        min_length=1,
    )
    edges: list[Edge] = Field(
        default_factory=list,
        description=(
            "Directed edges defining dependencies and execution order. Must "
            "form a valid directed acyclic graph (DAG)."
        ),
    )
    state: Literal["initialize_events", "initialize_edges", "session_allocation", "in_progress", "done"] = Field(
        default="initialize_events",
        description="The state of the temporal event graph.",
    )
    side_note: str = Field(
        default=NO_SIDE_NOTE,
        description=(
            "Commentary on the graph's overall structure, design rationale, "
            "and how events work together to accomplish goals. You may also "
            "reflect on how this graph contributes to the overall objectives "
            "of the synthesis task."
        ),
    )
    created_at: str = Field(
        default_factory=get_timestamp,
        description="Timestamp of creation of the temporal event graph object **in real-world system time**.",
    )
    finished_at: str | None = Field(
        default=None,
        description="Timestamp of completion of expanding all events in the graph **in real-world system time**.",
    )

    def get_event_by_id(self, event_id: str) -> tuple[int, Event | None]:
        """Get an event and the corresponing index by its ID.
        
        Args:
            event_id: str
                The ID of the event to retrieve.
            
        Returns:
            index: int
                The index of the event if found, -1 otherwise.
            event: Event | None
                The event if found, None otherwise.
        """
        for i, event in enumerate(self.events):
            if event.id == event_id:
                return i, event
        return -1, None

    def get_edge_by_id(self, edge_id: str) -> tuple[int, Edge | None]:
        """Get an edge and the corresponing index by its ID.
        
        Args:
            edge_id: str
                The ID of the edge to retrieve.
            
        Returns:
            index: int
                The index of the edge if found, -1 otherwise.
            edge: Edge | None
                The edge if found, None otherwise.
        """
        for i, edge in enumerate(self.edges):
            if edge.id == edge_id:
                return i, edge
        return -1, None

    @model_validator(mode="after")
    def _validate_graph(self) -> Self:
        """Validate the graph is a valid directed acyclic graph (DAG)."""
        self.topological_sort()
        return self

    def get_num_connected_component(self) -> int:
        """Get the number of connected components in the graph."""
        adjacency = {event.id: set() for event in self.events}

        for edge in self.edges:
            adjacency[edge.from_event].add(edge.to_event)
            adjacency[edge.to_event].add(edge.from_event)

        visited = set()
        num_components = 0

        for node in adjacency:
            if node in visited:
                continue

            stack = [node]
            visited.add(node)
            num_components += 1

            while stack:
                current = stack.pop()
                for neighbor in adjacency[current]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        stack.append(neighbor)

        return num_components
    
    def get_statistics_of_requirements(self) -> dict[str, int]:
        """Get the statistics of requirements in the graph."""
        requirements_statistics = {
            "Number of Requirements From Agent": 0,
            "Number of Requirements From Event": 0,
            "Number of Requirements From Person Profile": 0,
        }
        for event in self.events:
            for requirement in event.requirements:
                if requirement.origin_type == "Agent":
                    requirements_statistics["Number of Requirements From Agent"] += 1
                elif requirement.origin_type == "Event":
                    requirements_statistics["Number of Requirements From Event"] += 1
                else:
                    requirements_statistics["Number of Requirements From Person Profile"] += 1
        return requirements_statistics

    def topological_sort(self) -> Event | None:
        """Perform topological sorting of events based on dependencies and return the 
        next event to expand. If there is no next event to expand, return `None`."""
        # Build adjacency list and in-degree map.
        adj_list = {event.id: [] for event in self.events}
        in_degree = {event.id: 0 for event in self.events}
        depth_table = {}

        for edge in self.edges:
            if edge.from_event not in adj_list or edge.to_event not in adj_list:
                raise ValueError(
                    f"A dependency connection in the event graph references an event "
                    f"that doesn't exist (from {edge.from_event} to {edge.to_event}). "
                    f"Please ensure all event dependencies are valid."
                )
            adj_list[edge.from_event].append(edge.to_event)
            in_degree[edge.to_event] += 1

        queue = deque((eid, 0) for eid, degree in in_degree.items() if degree == 0)

        while queue:
            current, depth = queue.popleft()
            depth_table[current] = depth

            for neighbor in adj_list[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append((neighbor, depth + 1))

        if len(depth_table) != len(self.events):
            # Print the cyclic nodes.
            cyclic_nodes_str = "\n".join(
                [f"- {event.title} ({event.id})" for event in self.events if in_degree[event.id] > 0]
            ) 
            raise ValueError(
                "The event graph contains circular dependencies, which creates an "
                "impossible situation where events depend on each other in a loop. "
                "Please ensure all event dependencies form a valid sequence without cycles. "
                f"The following nodes are involved in the cycle:\n{cyclic_nodes_str}."
            )

        # Events are sorted by depth and `ended_at` time.
        sorted_events = sorted(self.events, key=lambda e: (depth_table[e.id], e.ended_at))
        for event in sorted_events:
            if event.state == "to_expand":
                return event
        return None
    
    def finish(self) -> None:
        """Finish the temporal event graph."""
        self.state = "done"
        self.finished_at = get_timestamp()
    
    def to_markdown(
        self, 
        include_side_note: bool = False, 
        include_output: bool = False,
        level: int = 0,
    ) -> str:
        """
        Convert the temporal event graph to MarkDown format.
        
        Args:
            include_side_note (`bool`, defaults to `False`):
                Whether to include side note of the graph object.
            include_output (`bool`, defaults to `False`):
                Whether to include the output (a session or a temporal sub-event graph) 
                of all events in the current graph.
            level (`int`, defaults to `0`):
                The level of the graph in the hierarchy.
        """
        indent = "\t" * level
        markdown_strs = [
            f"{indent}- Temporal Event Graph ID: {self.id}",
            f"{indent}\t- Parent Event ID: {self.parent_id if self.parent_id is not None else '[NULL]'}",
            f"{indent}\t- State: {self.state}",
            f"{indent}\t- Created At In Real-World System Time: {self.created_at}",
        ]
        if include_side_note:
            markdown_strs.append(f"{indent}\t- Side Note: {self.side_note}")

        markdown_strs.extend(
            [
                f"{indent}\t- Events (Nodes In {self.id})",
                *[
                    event.to_markdown(
                        include_side_note=include_side_note, 
                        level=level + 2,
                        include_output=include_output,
                    )
                    for event in self.events
                ],
            ]
        )
        markdown_strs.extend(
            [
                f"{indent}\t- Edges (Dependencies Between Events In {self.id})",
                *[
                    edge.to_markdown(
                        include_side_note=include_side_note, 
                        level=level + 2,
                    )
                    for edge in self.edges
                ],
            ]
        )

        if self.finished_at is not None:
            markdown_strs.append(f"{indent}\t- Finished At In Real-World System Time: {self.finished_at}")
        return "\n".join(markdown_strs)


class GraphRefinementState(BaseModel):
    """The state of the graph refinement process."""

    graph: TemporalEventGraph = Field(
        description="The current temporal event graph.",
    )
    state: Literal["refining", "refined"] = Field(
        default="refining",
        description="The state of the graph refinement process.",
    )
    created_at: str = Field(
        default_factory=get_timestamp,
        description="The creation time of the graph refinement state.",
    )
    finished_at: str | None = Field(
        default=None,
        description="The finish time of the graph refinement process.",
    )

    def finish_refinement(self) -> None:
        """Finish the graph refinement process."""
        self.state = "refined"
        self.finished_at = get_timestamp()

    def to_markdown(
        self, 
        include_side_note: bool = False, 
        include_output: bool = False,
        level: int = 0,
    ) -> str:
        """Convert the graph refinement state to MarkDown format."""
        return self.graph.to_markdown(
            include_side_note=include_side_note, 
            include_output=include_output, 
            level=level,
        )
