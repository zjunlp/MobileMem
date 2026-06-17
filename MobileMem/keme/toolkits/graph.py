import shortuuid
from agentscope.message import Msg, TextBlock
from agentscope.tool import ToolResponse
from datetime import datetime
from ._base import NotebookBase
from ._mixin import EventValidatorMixin
from .session import DefaultSessionToHint, SessionNotebook
from .refinement import DefaultGraphRefinementToHint, GraphRefinementNotebook
from .grounding import DefaultSessionGroundingToHint, SessionGroundingNotebook
from .agent import SynthesisAgent
from ..models import (
    TemporalEventGraph, 
    Event, 
    Edge,
    Session,
)
from ..models.persona import PersonBase
from ..schedulers import (
    GraphNotebookStateSchedulerBase, 
    ConstantGraphNotebookStateScheduler,
)
from ..utils import SYSTEM_PROMPT
from typing import (
    Callable, 
    Coroutine,
    Any,
)


class DefaultTemporalEventGraphToHint:
    """The default function to generate the hint message based on the current 
    temporal event graph to guide the agent on next steps."""

    hint_prefix: str = "<system-hint>"
    hint_suffix: str = "</system-hint>"

    no_graph: str = (
        "If the user wants to synthesize a hierarchical trajectory, "
        "you NEED to create events ({constraints}) first by calling 'create_events', then add dependencies "
        "by calling 'create_edges'. Otherwise, you can directly execute the user's query without creating a graph. "
        "When creating events, the requirements for each event should only come from the global node (Person profile) "
        "and ancestor events (if any ancestor events exist in the hierarchy). When inheriting a requirement from an "
        "ancestor event, the `from_source` field should be set to that ancestor event's ID."
    )

    when_initialize_edges: str = (
        "The current temporal event graph:\n"
        "```\n"
        "{graph}\n"
        "```\n"
        "Your options include:\n"
        "- Complete the graph setup by calling 'create_edges'. "
        "This step is required even if you don't want to add any dependencies between events. "
        "In that case, simply call 'create_edges' without passing any arguments."
    )

    when_session_allocation: str = (
        "The current temporal event graph:\n"
        "```\n"
        "{graph}\n"
        "```\n"
        "There are some external sessions to be allocated to events in this graph.\n"
        "Your options include:\n"
        "- Allocate external sessions to appropriate events by calling 'allocate_external_sessions'."
    )

    at_the_beginning: str = (
        "The current temporal event graph:\n"
        "```\n"
        "{graph}\n"
        "```\n"
        "Your options include:\n"
        "- Expand the event '{event_title}' (id: {event_id}) by calling {expansion_functions}."
    )

    when_events_expanding: str = (
        "The current temporal event graph:\n"
        "```\n"
        "{graph}\n"
        "```\n"
        "Now the event '{event_title}' (id: {event_id}) is in 'expanding' state.\n"
        "Your options include:\n"
        "- If the event isn't expanded successfully, try to expand this event again."
    )

    when_at_least_one_event_expanded: str = (
        "The current temporal event graph:\n"
        "```\n"
        "{graph}\n"
        "```\n"
        "{num_expanded} event(s) are expanded, and there is no event in 'expanding' state.\n"
        "Now your options include:\n"
        "- Expand the next event '{event_title}' (id: {event_id}) by calling {expansion_functions}." 
    )

    at_the_end: str = (
        "The current temporal event graph:\n"
        "```\n"
        "{graph}\n"
        "```\n"
        "All the events in this graph are expanded. Now your options are:\n"
        "- Finish this graph by calling 'finish_graph_expansion', and calling 'generate_response' to summarize the final graph."
    )

    def __call__(
        self, 
        graph: TemporalEventGraph | None,
        scheduler: GraphNotebookStateSchedulerBase | None,
        level: int | None = None,
    ) -> str | None:
        """Generate the hint message based on the input temporal event graph to guide the
        agent on next steps.

        Args:
            graph (`TemporalEventGraph | None`):
                The current temporal event graph, used to generate the hint message.
            scheduler (`GraphNotebookStateSchedulerBase | None`):
                The scheduler to determine expansion strategies for events.
            level (`int | None`, optional):
                The hierarchy level (0 = root level, higher = deeper). Used to determine
                expansion strategies. If not provided, strategies are determined only based
                on event.

        Returns:
            `str | None`:
                The generated hint message, or None if the graph is None or
                there is no relevant hint.
        """
        if graph is None:
            # Generate constraints string for no_graph hint
            if scheduler is not None:
                level_for_constraints = level if level is not None else 0
                min_events = scheduler.get_min_events(level_for_constraints)
                max_events = scheduler.get_max_events(level_for_constraints)
                constraints_parts = [f"at least {min_events} event(s)"]
                if max_events is not None:
                    constraints_parts.append(f"at most {max_events} event(s)")
                constraints = ", ".join(constraints_parts)
            else:
                constraints = "at least 1 event"
            hint = self.no_graph.format(constraints=constraints)
        else:
            # We don't include each expaned event's output in the graph markdown because it may cause context overflow
            # To leverage the output of each expanded event, we use another agent to handle the output of each expanded event.
            # This agent reviews the result of expansion and refines the current temporal event graph.
            graph_markdown = graph.to_markdown(include_side_note=True, include_output=False)
            hint = None

            # Check graph state
            if graph.state == "initialize_edges":
                hint = self.when_initialize_edges.format(graph=graph_markdown)
            elif graph.state == "session_allocation":
                hint = self.when_session_allocation.format(graph=graph_markdown)
            elif graph.state == "in_progress":
                # Count events by state
                n_to_expand, n_expanding, n_expanded = 0, 0, 0
                expanding_events = []
                
                for event in graph.events:
                    if event.state == "to_expand":
                        n_to_expand += 1
                    elif event.state == "expanding":
                        n_expanding += 1
                        expanding_events.append(event)
                    else:
                        n_expanded += 1

                if n_expanding > 0:
                    # Some events are being expanded
                    expanding_event = expanding_events[0]  # Use first expanding event
                    hint = self.when_events_expanding.format(
                        graph=graph_markdown,
                        event_title=expanding_event.title,
                        event_id=expanding_event.id,
                    )
                elif n_expanded == 0 and n_to_expand > 0:
                    # All events are to_expand (beginning)
                    next_event = graph.topological_sort()
                    # Get expansion functions based on strategy
                    if scheduler is not None:
                        strategy = scheduler.get_expansion_strategy(next_event, level=level)
                    else:
                        strategy = "both"
                    
                    if strategy == "session_only":
                        expansion_functions = "'expand_event_into_session'"
                    elif strategy == "subgraph_only":
                        expansion_functions = "'expand_event_into_graph'"
                    else:  # both
                        expansion_functions = "'expand_event_into_session' or 'expand_event_into_graph'"
                    
                    hint = self.at_the_beginning.format(
                        graph=graph_markdown,
                        event_title=next_event.title,
                        event_id=next_event.id,
                        expansion_functions=expansion_functions,
                    )
                elif n_expanded > 0 and n_to_expand > 0:
                    # Some expanded, some to_expand
                    next_event = graph.topological_sort()
                    if next_event is not None:
                        # Get expansion functions based on strategy
                        if scheduler is not None:
                            strategy = scheduler.get_expansion_strategy(next_event, level=level)
                        else:
                            strategy = "both"
                        
                        if strategy == "session_only":
                            expansion_functions = "'expand_event_into_session'"
                        elif strategy == "subgraph_only":
                            expansion_functions = "'expand_event_into_graph'"
                        else:  # both
                            expansion_functions = "'expand_event_into_session' or 'expand_event_into_graph'"
                        
                        hint = self.when_at_least_one_event_expanded.format(
                            graph=graph_markdown,
                            num_expanded=n_expanded,
                            event_title=next_event.title,
                            event_id=next_event.id,
                            expansion_functions=expansion_functions,
                        )
                elif n_expanded == len(graph.events):
                    # All events are expanded
                    hint = self.at_the_end.format(graph=graph_markdown)
        
        if hint:
            return f"{self.hint_prefix}{hint}{self.hint_suffix}"

        return hint


class TemporalEventGraphNotebook(NotebookBase, EventValidatorMixin):
    """The temporal event graph notebook to manage the temporal event graph, 
    providing hints and temporal event graph related tools to the agent."""

    description: str = (
        "The temporal event graph-related tools for hierarchical trajectory synthesis. "
        "Activate this tool when you need to expand a given event or person profile into a temporal sub-event graph. "
        "Once activated, you'll enter the expansion mode, where you will be guided to create and expand temporal event "
        "graphs recursively. The hint messages wrapped by <system-hint></system-hint> will guide you to complete the task. "
        "If you think the user no longer wants to continue the expansion, you need to confirm with the user "
        "and call 'finish_graph_expansion' to finish the graph expansion."
    )
    name: str = "temporal_event_graph_generation_related"

    def __init__(
        self,
        person: PersonBase,
        agent_name: str, 
        level: int | None = None,
        scheduler: GraphNotebookStateSchedulerBase | None = None,
        parent_event: Event | None = None,
        graph_to_hint: Callable[[TemporalEventGraph | None], str | None] | None = None,
        session_to_hint: Callable[[Session | None, PersonBase], str | None] | None = None,
        graph_refinement_to_hint: Callable[[TemporalEventGraph | None], str | None] | None = None,
        session_grounding_to_hint: Callable[[TemporalEventGraph, Session], str | None] | None = None,
        compatibility_context_max_tokens: int = 8000,
        **kwargs: Any, 
    ) -> None:
        """Initialize the temporal event graph notebook.

        Args:
            person (`PersonBase`):
                The person that this notebook belongs to.
            agent_name (`str`):
                The name of the agent that this notebook belongs to.
            level (`int | None`, optional):
                The hierarchy level (0 = root level, higher = deeper). If not provided, the root level is used.
            scheduler (`GraphNotebookStateSchedulerBase | None`, optional):
                The scheduler instance to use for managing the temporal event graph state based on the hierarchy level.
                If not provided, a default `ConstantGraphNotebookStateScheduler` object will be used.
            parent_event (`Event | None`, optional):
                The parent event that this notebook will expand. 
                If provided, this notebook is used to expand the specified parent event 
                into a temporal sub-event graph. If None, this notebook creates a top-level 
                graph by expanding the person (root level). 
            graph_to_hint (`Callable[[TemporalEventGraph | None], str | None] | None`, optional):
                The function to generate hint messages based on the current temporal event graph.
                If not provided, a default `DefaultTemporalEventGraphToHint` object will be used.
                The hint function guides the agent on next steps (e.g., which events to expand,
                how to handle dependencies, when to finish the graph).
            session_to_hint (`Callable[[Session | None, PersonBase], str | None] | None`, optional):
                The function to generate hint messages based on the current session state and person.
                If not provided, a default `DefaultSessionToHint` object will be used.
                The hint function guides the agent on next steps (e.g., when to create session,
                how to handle person attribute updates).
            graph_refinement_to_hint (`Callable[[TemporalEventGraph | None], str | None] | None`, optional):
                The function to generate hint messages based on the current temporal event graph refinement result.
                If not provided, a default `DefaultGraphRefinementToHint` object will be used.
                The hint function guides the agent on next steps (e.g., when to finish the graph refinement,
                how to handle the refinement result).
            session_grounding_to_hint (`Callable[[TemporalEventGraph, Session], str | None] | None`, optional):
                The function to generate hint messages based on the current temporal event graph and session grounding result.
                If not provided, a default `DefaultSessionGroundingToHint` object will be used.
                The hint function guides the agent on next steps (e.g., how to distribute an external session to an event in a 
                temporal event graph).
            compatibility_context_max_tokens (`int`, Defaults to `8000`):
                The maximum number of tokens allowed for compatibility context before triggering 
                summarization.
            **kwargs: (`Any`)
                Additional keyword arguments to pass to the child agent. The child agent is an instance of `ReActAgent`.
        """
        super().__init__()

        self.person = person 
        self.agent_name = agent_name
        self.level = level or 0
        self.parent_event = parent_event
        if self.parent_event is None and self.level > 0:
            raise ValueError(
                "The parent event is not provided, but the level is greater than 0. "
                "You need to provide the parent event when the level is greater than 0."
            )
 
        self.scheduler = scheduler or ConstantGraphNotebookStateScheduler()
        self.graph_to_hint = graph_to_hint or DefaultTemporalEventGraphToHint()
        self.session_to_hint = session_to_hint or DefaultSessionToHint()
        self.graph_refinement_to_hint = graph_refinement_to_hint or DefaultGraphRefinementToHint()
        self.session_grounding_to_hint = session_grounding_to_hint or DefaultSessionGroundingToHint()
        self.compatibility_context_max_tokens = compatibility_context_max_tokens
        self.current_graph: TemporalEventGraph | None = None

        # Each graph is assigned a single refinement agent 
        # Each refinement process for this graph shares the same agent instance
        self.refinement_agent_name = f"agent_{shortuuid.uuid()}"

        # Other parameters used to pass to the child agent.
        self.agent_kwargs = kwargs 

        # Register the current_graph state for state management
        self.register_state(
            "current_graph",
            custom_to_json=lambda _: _.model_dump() if _ else None,
            custom_from_json=lambda _: TemporalEventGraph.model_validate(_) if _ else None,
        )

        person_type = type(self.person)
        self.register_state(
            "person", 
            custom_to_json=lambda _: _.model_dump() if _ else None,
            custom_from_json=lambda _: person_type.model_validate(_) if _ else None,
        )
        self.register_state(
            "parent_event", 
            custom_to_json=lambda _: _.model_dump() if _ else None,
            custom_from_json=lambda _: Event.model_validate(_) if _ else None,
        )
        self.register_state("agent_name") 
        self.register_state("refinement_agent_name")
        self.register_state("level")
        self.register_state("compatibility_context_max_tokens")

    def _validate_current_graph(self) -> None:
        """Validate the current graph."""
        if self.current_graph is None:
            raise ValueError(
                "The current temporal event graph is None, you need to create events by "
                "calling create_events() first, then optionally add dependencies with create_edges().",
            )

    async def create_events(
        self,
        events: list[Event],
    ) -> ToolResponse:
        """Create events and initialize a temporal event graph without edges.
        
        This is the first step in creating a temporal event graph. It creates a graph
        with events but no dependencies (edges). After events are created, you can use
        `create_edges` to add dependencies between events using their IDs.
        
        This two-step approach is necessary because edge creation requires event IDs,
        which are only generated when events are created.
        
        Args:
            events (`list[Event]`):
                A list of events in the graph. Must have at least one event.
                Each event should represent a significant time period or activity
                that can be further decomposed into sub-events or converted into a
                conversation session. Events are initially in 'to_expand' state.
                Each event will be assigned a unique ID upon creation.

        Returns:
            `ToolResponse`:
                The response of the tool call, confirming event creation and providing
                event IDs that can be used in `create_edges`.
        """
        if not events:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text="Error: At least one event is required to create a temporal event graph.",
                    ),
                ],
            )

        # Validate min/max events
        min_events = self.scheduler.get_min_events(self.level)
        if len(events) < min_events:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: At least {min_events} event(s) are required, "
                            f"but only {len(events)} event(s) were provided."
                        ),
                    ),
                ],
            )

        max_events = self.scheduler.get_max_events(self.level) 
        if max_events is not None and len(events) > max_events:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: At most {max_events} event(s) are allowed, "
                            f"but {len(events)} event(s) were provided."
                        ),
                    ),
                ],
            )

        # Validate events and convert to Event model
        events = [Event.model_validate(event) for event in events]

        # Validate all events by checking their time range and requirements
        msg = self._validate_events_time_range(events) or self._validate_requirements_source(events)
        if msg is not None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=msg,
                    ),
                ],
            )

        if self.current_graph is None:
            # Create graph with events but no edges
            graph = TemporalEventGraph(
                events=events,
                parent_id=self.parent_event.id if self.parent_event is not None else None,
            )
            res = ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Events are created successfully ({len(events)} event(s)). "
                            "Next step: Use 'create_edges' to add dependencies between events."
                        ),
                    ),
                ],
            )
            self.current_graph = graph 
            # Begin to initialize edges
            self.current_graph.state = "initialize_edges"
            await self._trigger_hooks() 
        else:
            if self.current_graph.state == "in_progress":
                text = (
                    "Error: The temporal event graph has been created already.\n"
                    "If you want to modify the graph, use the following tools:\n"
                    "- 'revise_event': Modify events (add new events, revise event details like "
                    "'title'/summary'/'start time'/'end time'/'requirements'/'side note', or delete unwanted events)\n"
                    "- 'revise_edges': Modify dependencies (add new edges, revise edge details like " 
                    "'name'/'source event ID'/'target event ID/side note' or delete edges to remove dependencies)"
                )
            elif self.current_graph.state == "initialize_edges":
                text = (
                    "Error: The temporal event graph has been created already.\n"
                    "It is found that you haven't called 'create_edges' to add dependencies between events. "
                    "Please call this function. If you don't want to add any dependencies, you can call it without passing any arguments."
                )
            elif self.current_graph.state == "session_allocation":
                text = (
                    "Error: The temporal event graph has been created already.\n"
                    "It is found that you haven't called 'allocate_external_sessions' to distribute external sessions to events. "
                    "Please call this function."
                )
            else:
                text = (
                    "Error: The temporal event graph has been created before. The graph expansion process has been completed already.\n"
                    "It is found that you haven't called 'generate_response' to summarize the final graph. "
                    "Please call this function."
                )
            res = ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=text,
                    ),
                ],
            )

        return res

    async def create_edges(
        self,
        edges: list[Edge] | None = None,
        graph_side_note: str | None = None,
    ) -> ToolResponse:
        """Add edges (dependencies) to the current temporal event graph.
        
        This is the second step in creating a temporal event graph. After creating
        events with `create_events`, use this function to add dependencies between events.
        You can call this function without providing any edges if you want to initialize
        a graph where all events are independent (no dependencies).

        Args:
            edges (`list[Edge] | None`, optional):
                A list of edges defining temporal dependencies between events. 
                If not provided (None or empty list), no edges will be added and all events 
                will remain independent.
                
                Each edge creates a dependency from the source event to the target event, 
                meaning the target event must wait for the source event to be expanded first.
                The reasons for creating dependencies can be flexible and diverse.
                
                Important temporal constraint: Events connected by an edge cannot overlap 
                in time. The source event must complete before the target event begins. 
                Specifically, the source event's `ended_at` must be earlier than the target 
                event's `started_at`. 
                
                All edge source and target event IDs must reference events that exist in 
                the current graph (created via `create_events`). The resulting graph must 
                form a valid directed acyclic graph (DAG).
                
            graph_side_note (`str | None`, optional):
                Optional commentary on the graph's overall structure (including events and edges), 
                design rationale, and how events and edges work together to accomplish goals. 
                You may also reflect on how this graph contributes to the overall objectives of the synthesis task.

        Returns:
            `ToolResponse`:
                The response of the tool call, confirming edge creation or reporting errors.
        """
        self._validate_current_graph() 
        parent = self.parent_event or self.person
        session_source = "parent event" if isinstance(parent, Event) else "person profile"
        if self.current_graph.state == "in_progress":
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: You have already called 'create_edges' to add dependencies between events. "
                            "If you want to modify the graph, use the following tools:\n"
                            "- 'revise_event': Modify events (add new events, revise event details like "
                            "'title'/summary'/'start time'/'end time'/'requirements'/'side note', or delete unwanted events)\n"
                            "- 'revise_edges': Modify dependencies (add new edges, revise edge details like " 
                            "'name'/'source event ID'/'target event ID' or delete edges to remove dependencies)"
                        ),
                    ),
                ],
            )
        elif self.current_graph.state == "session_allocation":
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: You have already called 'create_edges' to add dependencies between events. "
                            "The process has advanced to the session allocation phase. You need to use the tool " 
                            "'allocate_external_sessions' to distribute the existing session data from the " 
                            f"{session_source} to the various event nodes in the current temporal event graph."
                        ),
                    ),
                ],
            )
        elif self.current_graph.state == "done":
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: The edges of this graph have been initialized before. The graph expansion process has been completed already.\n"
                            "It is found that you haven't called 'generate_response' to summarize the final graph. "
                            "Please call this function."
                        ),
                    ),
                ],
            )

        side_note_changed = graph_side_note is not None  
        if parent.has_grounded_sessions:
            next_graph_state = "session_allocation"
            # The detailed hint message will be provided by `self.graph_to_hint`. 
            next_step_hint = "The state of graph is updated to 'session_allocation'." 
        else:
            next_graph_state = "in_progress"
            next_step_hint = (
                f"There are no off-the-shelf external sessions from {session_source} " 
                "to allocate to the events in the current temporal event graph. "
                "The session allocation stage is skipped. "
                "The state of graph is updated to 'in_progress'."
            )

        # Handle case when no edges are provided
        if not edges:
            # Transition to the next state
            self.current_graph.state = next_graph_state
            if side_note_changed:
                self.current_graph.side_note = graph_side_note
                await self._trigger_hooks()
                return ToolResponse(
                    content=[
                        TextBlock(
                            type="text",
                            text=(
                                "No edges provided. The graph will remain without dependencies. "
                                "The graph's side note has been updated."
                                f"\n{next_step_hint}"
                            ),
                        ),
                    ],
                )
            else:
                return ToolResponse(
                    content=[
                        TextBlock(
                            type="text",
                            text=(
                                "No edges provided. The graph will remain without dependencies."
                                f"\n{next_step_hint}"
                            ),
                        ),
                    ],
                )

        edges = [Edge.model_validate(edge) for edge in edges]

        # Validate that all edge references exist
        event_ids = {event.id for event in self.current_graph.events}
        event_by_id = {event.id: event for event in self.current_graph.events}
        invalid_edges = []
        for edge in edges:
            if edge.from_event not in event_ids:
                invalid_edges.append(
                    f"Edge '{edge.name}': source event '{edge.from_event}' is not found in graph."
                )
            elif edge.to_event not in event_ids:
                invalid_edges.append(
                    f"Edge '{edge.name}': target event '{edge.to_event}' is not found in graph."
                )
            elif edge.from_event == edge.to_event:
                invalid_edges.append(
                    f"Edge '{edge.name}': cannot create self-loop (event cannot depend on itself)."
                )
            else:
                # Validate temporal constraint: source event must end before target event starts
                source_event = event_by_id[edge.from_event]
                target_event = event_by_id[edge.to_event]
                source_end = datetime.fromisoformat(source_event.ended_at)
                target_start = datetime.fromisoformat(target_event.started_at)
                
                if source_end > target_start:
                    invalid_edges.append(
                        f"Edge '{edge.name}': temporal constraint violation. "
                        f"Source event '{source_event.title}' ends at {source_event.ended_at}, "
                        f"but target event '{target_event.title}' starts at {target_event.started_at}. "
                        f"The source event must complete before the target event begins."
                    )

        if invalid_edges:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text="Error: Find invalid edge(s).\n" + "\n".join(invalid_edges),
                    ),
                ],
            )

        # Try to add edges and validate DAG structure
        prev_num_edges = len(self.current_graph.edges) 
        try:
            # We don't create a new instance of temporal event graph here
            self.current_graph.edges.extend(edges)
            self.current_graph.topological_sort() 
            text = (
                f"Edges added successfully ({len(edges)} edge(s)). "
                f"The graph now has {len(self.current_graph.edges)} total edge(s)."
            ) 

            if side_note_changed:
                self.current_graph.side_note = graph_side_note
                text += " The graph's side note has been updated."
            self.current_graph.state = next_graph_state
            text += f"\n{next_step_hint}"
            await self._trigger_hooks()
            
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=text,
                    ),
                ],
            )

        except ValueError as e:
            # Recover the graph to the previous state
            self.current_graph.edges = self.current_graph.edges[:prev_num_edges]
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"Error: Failed to add edges. {str(e)}",
                    ),
                ],
            )

    async def allocate_external_sessions(self) -> ToolResponse:
        """Allocate external sessions to appropriate events in the temporal event graph.
        
        Assigning external session data to appropriate events in the graph may require updates to the 
        graph topology and event node contents.
        
        Returns:
            `ToolResponse`:
                The response of the tool call, confirming the allocation results or reporting errors.
        """
        self._validate_current_graph()
        parent = self.parent_event or self.person
        session_source = "parent event" if isinstance(parent, Event) else "person profile"
        
        if self.current_graph.state == "initialize_edges":
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: Before allocating external sessions, you must complete the graph setup "
                            "by calling 'create_edges'. This step is required even if you don't want to add "
                            "any dependencies between events."
                        ),
                    ),
                ],
            )
        elif self.current_graph.state == "in_progress":
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: The session allocation has already been completed or there are no "
                            f"external sessions from {session_source} to allocate." 
                        ),
                    ),
                ],
            )
        elif self.current_graph.state == "done":
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: The graph expansion process has been completed already.\n"
                            "It is found that you haven't called 'generate_response' to summarize the final graph. "
                            "Please call this function."
                        ),
                    ),
                ],
            )
        
        grounded_sessions = parent.grounded_sessions
        blocks = [
            TextBlock(
                type="text",
                text=f"Starting session allocation for {len(grounded_sessions)} external session(s)...",
            ),
        ]
        
        # Process each external session sequentially in chronological order
        for i, session in enumerate(grounded_sessions):
            # Create a session grounding agent for this session
            grounding_agent_kwargs = {**self.agent_kwargs}
            grounding_agent_kwargs["name"] = f"agent_{shortuuid.uuid()}"
            grounding_agent_kwargs["sys_prompt"] = grounding_agent_kwargs.get(
                "sys_prompt", 
                SYSTEM_PROMPT
            ).format(
                agent_id=grounding_agent_kwargs["name"]
            )
            grounding_agent_kwargs["notebook"] = SessionGroundingNotebook(
                self.person,
                grounding_agent_kwargs["name"],
                self.current_graph,
                session,
                parent_event=self.parent_event,
                level=self.level,
                scheduler=self.scheduler,
                grounding_to_hint=self.session_grounding_to_hint,
                compatibility_context_max_tokens=self.compatibility_context_max_tokens,
                **self.agent_kwargs,
            )
            grounding_agent = SynthesisAgent(**grounding_agent_kwargs)
            
            try:
                # The response message is not used here as it may cause context overflow. 
                _ = await grounding_agent(
                    msg=Msg(
                        "user",
                        self.scheduler.get_task_instruction(
                            self.person,
                            parent_event=self.parent_event,
                            level=self.level,
                            instruction_type="session_grounding",
                            session=session,
                        ),
                        "user",
                    ),
                )
                blocks.append(
                    TextBlock(
                        type="text",
                        text=f"The {i + 1}-th external session has been grounded successfully.",
                    ),
                )
            except Exception:
                blocks.append(
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: Failed to ground the {i + 1}-th external session."
                        ),
                    ),
                )
        
        self.current_graph.state = "in_progress"
        await self._trigger_hooks()
        
        blocks.append(
            TextBlock(
                type="text",
                text="The session allocation process is completed. The graph is now ready for event expansion.",
            ),
        )
        
        return ToolResponse(content=blocks)

    async def expand_event_into_session(self) -> ToolResponse:
        """Expand the next event into a session.
        
        This function initiates the expansion of an event into a session.
        It marks the event as 'expanding' and initializes a session generation agent
        to create the session content.
        
        Returns:
            `ToolResponse`:
                The response of the tool call, confirming the expansion initiation.
                The actual session will be generated by the session agent.
        """
        self._validate_current_graph()

        if self.current_graph.state == "initialize_edges":
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: Before expanding events, you must complete the graph setup by calling 'create_edges'. "
                            "This step is required even if you don't want to add any dependencies between events. "
                            "In that case, simply call 'create_edges' without passing any arguments. "
                            "Once the graph setup is complete, you can then expand events using 'expand_event_into_session'."
                        ), 
                    ),
                ],
            )
        elif self.current_graph.state == "session_allocation":
            session_source = "parent event" if isinstance(self.parent_event or self.person, Event) else "person profile"
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: Before expanding events, you must allocate external sessions " 
                            f"from {session_source} by calling 'allocate_external_sessions'. " 
                            "This step distributes pre-existing sessions to appropriate events in the graph. " 
                            "Once session allocation is complete, you can then expand events based on the new graph " 
                            "using 'expand_event_into_session'."
                        ),
                    ),
                ],
            )
        elif self.current_graph.state == "done":
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: Tool 'expand_event_into_session' cannot be called as you have finished " 
                            "the graph expansion process before.\n"
                            "It is found that you haven't called 'generate_response' to summarize the final graph. "
                            "Please call this function."
                        ),
                    ),
                ],
            )

        next_event = self.current_graph.topological_sort()
        if next_event is None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: All events have been expanded already. "
                            "No events are left to expand."
                        ), 
                    ),
                ],
            )

        # Check expansion strategy
        strategy = self.scheduler.get_expansion_strategy(next_event, level=self.level)
        if strategy == "subgraph_only":
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Event '{next_event.title}' (id: {next_event.id}) cannot be expanded to a session. "
                            "This event must be expanded into a sub-event graph instead. "
                            "Please use 'expand_event_into_graph' instead."
                        ),
                    ),
                ],
            )

        # Mark event as expanding
        next_event.state = "expanding"
        await self._trigger_hooks()
        blocks = [
            TextBlock(
                type="text",
                text=f"Event '{next_event.title}' (id: {next_event.id}) is marked as 'expanding' for session generation.",
            ),
        ]

        # Start to expand the event into a session
        response_msg = new_session = None 
        if next_event.has_grounded_sessions:
            num_grounded = next_event.num_grounded_sessions
            try:
                new_session = Session.merge(next_event.grounded_sessions)
                if num_grounded == 1:
                    blocks.append(
                        TextBlock(
                            type="text",
                            text=(
                                "<expansion_result>\n"
                                f"Event '{next_event.title}' (id: {next_event.id}) has 1 pre-existing external session. "
                                "Therefore, the expansion result of this event is this external session.\n"
                                "Below is the external session:\n"
                                f"{new_session.to_markdown(include_side_note=True)}"
                                "\n</expansion_result>"
                            ),
                        ),
                    )
                else:
                    blocks.append(
                        TextBlock(
                            type="text",
                            text=(
                                "<expansion_result>\n"
                                f"Event '{next_event.title}' (id: {next_event.id}) has {num_grounded} pre-existing external sessions. "
                                "Therefore, these sessions have been merged into a single session, " 
                                "and the expansion result of this event is the merged session.\n"
                                "Below is the merged session:\n"
                                f"{new_session.to_markdown(include_side_note=True)}"
                                "\n</expansion_result>"
                            ),
                        ),
                    )
            except Exception as e:
                blocks.append(
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: Event '{next_event.title}' (id: {next_event.id}) has {num_grounded} pre-existing external session(s) "
                            f"that need to be merged. However, an error occurred during the merge process: {str(e)}"
                        ),
                    ),
                )
                return ToolResponse(content=blocks)

        # The client and other objects are shared 
        session_agent_kwargs = {**self.agent_kwargs}
        session_agent_kwargs["name"] = f"agent_{shortuuid.uuid()}"
        session_agent_kwargs["sys_prompt"] = session_agent_kwargs.get(
            "sys_prompt", 
            SYSTEM_PROMPT
        ).format(
            agent_id=session_agent_kwargs["name"]
        )
        session_agent_kwargs["notebook"] = SessionNotebook(
            self.person,
            parent_event=next_event,
            session_to_hint=self.session_to_hint,
        )
        # If the new session is created by the system, we just simply set the current session to the new session.
        # The session construction agent will not call the `create_session` tool as the hint messages will guide the agent.
        session_agent_kwargs["notebook"].current_session = new_session
        session_agent = SynthesisAgent(**session_agent_kwargs) 
        try:
            response_msg = await session_agent(
                msg=Msg(
                    "user",
                    self.scheduler.get_task_instruction(
                        self.person, 
                        parent_event=next_event, 
                        instruction_type="session",
                    ),
                    "user",
                ),
            )
            blocks.append(
                TextBlock(
                    type="text",
                    text=f"<expansion_result>\n{response_msg.content}\n</expansion_result>",
                ),
            )
            if new_session is not None:
                new_session.side_note += (
                    "\n[Grounded Session Notice] This session is derived from pre-existing external data and may not fully "
                    "align with the parent event's summary and requirements. During the subsequent graph refinement phase, "
                    "consider the following strategies to handle potential discrepancies: "
                    "(1) Adjust unexpanded events in the graph to reasonably bridge or accommodate the discrepancy; "
                    "(2) Ensure that subsequent events are thematically unrelated to the discrepancy, thereby avoiding conflicts."
                )
            await self._trigger_hooks() 
        except Exception as e:
            next_event.reset()
            blocks.append(
                TextBlock(
                    type="text",
                    text=f"Error: Failed to expand event '{next_event.title}' (id: {next_event.id}) into a session. {str(e)}",
                ),
            )
        
        if response_msg is not None:
            # If the next event is expanded successfully, the refinement process is invoked automatically
            refinement_agent_kwargs = {**self.agent_kwargs} 
            refinement_agent_kwargs["name"] = self.refinement_agent_name
            refinement_agent_kwargs["sys_prompt"] = refinement_agent_kwargs.get(
                "sys_prompt", 
                SYSTEM_PROMPT
            ).format(
                agent_id=self.refinement_agent_name
            )
            refinement_agent_kwargs["notebook"] = GraphRefinementNotebook(
                self.person,
                self.refinement_agent_name, 
                self.current_graph,
                parent_event=self.parent_event, 
                level=self.level,
                scheduler=self.scheduler,
                refinement_to_hint=self.graph_refinement_to_hint,
            )
            refinement_agent = SynthesisAgent(**refinement_agent_kwargs)
            response_msg = await refinement_agent(
                msg=Msg(
                    "user",
                    self.scheduler.get_task_instruction(
                        self.person, 
                        parent_event=self.parent_event, 
                        level=self.level,  
                        instruction_type="graph_refinement",
                        expanded_event=next_event,
                    ),
                    "user",
                ),
            )
            blocks.append(
                TextBlock(
                    type="text",
                    text=f"<refinement_result>\n{response_msg.content}\n</refinement_result>",
                ),
            )
            await self._trigger_hooks() 

        return ToolResponse(content=blocks)

    async def expand_event_into_graph(self) -> ToolResponse:
        """Expand the next event into a temporal sub-event graph.
        
        This function initiates the expansion of an event into a sub-event graph.
        It marks the event as 'expanding' and initializes a graph generation agent
        to create the sub-event graph.
        
        Returns:
            `ToolResponse`:
                The response of the tool call, confirming the expansion initiation.
                The actual sub-event graph will be generated by the graph generation agent.
        """
        self._validate_current_graph()

        if self.current_graph.state == "initialize_edges":
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: Before expanding events, you must complete the graph setup by calling 'create_edges'. "
                            "This step is required even if you don't want to add any dependencies between events. "
                            "In that case, simply call 'create_edges' without passing any arguments. "
                            "Once the graph setup is complete, you can then expand events using 'expand_event_into_graph'."
                        ), 
                    ),
                ],
            )
        elif self.current_graph.state == "session_allocation":
            session_source = "parent event" if isinstance(self.parent_event or self.person, Event) else "person profile"
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: Before expanding events, you must allocate external sessions " 
                            f"from {session_source} by calling 'allocate_external_sessions'. " 
                            "This step distributes pre-existing sessions to appropriate events in the graph. " 
                            "Once session allocation is complete, you can then expand events based on the new graph " 
                            "using 'expand_event_into_graph'."
                        ),
                    ),
                ],
            )
        elif self.current_graph.state == "done":
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: Tool 'expand_event_into_graph' cannot be called as you have finished " 
                            "the graph expansion process before.\n"
                            "It is found that you haven't called 'generate_response' to summarize the final graph. "
                            "Please call this function."
                        ),
                    ),
                ],
            )

        next_event = self.current_graph.topological_sort()
        if next_event is None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: All events have been expanded already. "
                            "No events are left to expand."
                        ), 
                    ),
                ],
            )   

        strategy = self.scheduler.get_expansion_strategy(next_event, level=self.level)
        if strategy == "session_only":
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Event '{next_event.title}' (id: {next_event.id}) cannot be expanded to a sub-event graph. "
                            "This event must be expanded into a session instead. "
                            "Please use 'expand_event_into_session' instead."
                        ),
                    ),
                ],
            )

        next_event.state = "expanding"
        await self._trigger_hooks()
        blocks = [
            TextBlock(
                type="text",
                text=f"Event '{next_event.title}' (id: {next_event.id}) is marked as 'expanding' for sub-event graph generation.",
            ),
        ]

        # Start to expand the event into a temporal sub-event graph 
        graph_agent_kwargs = {**self.agent_kwargs}
        graph_agent_kwargs["name"] = f"agent_{shortuuid.uuid()}"
        graph_agent_kwargs["sys_prompt"] = graph_agent_kwargs.get(
            "sys_prompt", 
            SYSTEM_PROMPT
        ).format(
            agent_id=graph_agent_kwargs["name"]
        )
        graph_agent_kwargs["notebook"] = TemporalEventGraphNotebook(
            self.person,
            graph_agent_kwargs["name"], 
            level=self.level + 1,
            scheduler=self.scheduler,
            parent_event=next_event,
            graph_to_hint=self.graph_to_hint,
            session_to_hint=self.session_to_hint,
            graph_refinement_to_hint=self.graph_refinement_to_hint,
            session_grounding_to_hint=self.session_grounding_to_hint,
            compatibility_context_max_tokens=self.compatibility_context_max_tokens,
            **self.agent_kwargs,
        )
        graph_agent = SynthesisAgent(**graph_agent_kwargs)
        response_msg = None 
        try:
            response_msg = await graph_agent(
                msg=Msg(
                    "user",
                    self.scheduler.get_task_instruction(
                        self.person, 
                        parent_event=next_event, 
                        instruction_type="temporal_event_graph",
                        level=self.level + 1
                    ),
                    "user",
                ),
            )
            blocks.append(
                TextBlock(
                    type="text",
                    text=f"<expansion_result>\n{response_msg.content}\n</expansion_result>",
                ),
            )
            await self._trigger_hooks() 
        except Exception as e:
            next_event.reset() 
            blocks.append(
                TextBlock(
                    type="text",
                    text=f"Error: Failed to expand event '{next_event.title}' (id: {next_event.id}) into a sub-event graph. {str(e)}",
                ),
            ) 

        if response_msg is not None:
            refinement_agent_kwargs = {**self.agent_kwargs} 
            refinement_agent_kwargs["name"] = self.refinement_agent_name
            refinement_agent_kwargs["sys_prompt"] = refinement_agent_kwargs.get(
                "sys_prompt", 
                SYSTEM_PROMPT
            ).format(
                agent_id=self.refinement_agent_name
            )
            refinement_agent_kwargs["notebook"] = GraphRefinementNotebook(
                self.person,
                self.refinement_agent_name, 
                self.current_graph,
                parent_event=self.parent_event, 
                level=self.level,
                scheduler=self.scheduler,
                refinement_to_hint=self.graph_refinement_to_hint,
            )
            refinement_agent = SynthesisAgent(**refinement_agent_kwargs)
            response_msg = await refinement_agent(
                msg=Msg(
                    "user",
                    self.scheduler.get_task_instruction(
                        self.person, 
                        parent_event=self.parent_event, 
                        level=self.level, 
                        instruction_type="graph_refinement",
                        expanded_event=next_event,
                    ),
                    "user",
                ),
            )
            blocks.append(
                TextBlock(
                    type="text",
                    text=f"<refinement_result>\n{response_msg.content}\n</refinement_result>",
                ),
            )
            await self._trigger_hooks() 

        return ToolResponse(content=blocks)

    async def finish_graph_expansion(self) -> ToolResponse:
        """Finish the expansion of the current temporal event graph.

        Returns:
            `ToolResponse`:
                The response of the tool call, confirming the graph completion.
        """
        if self.current_graph is None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text="There is no graph to finish expansion.",
                    ),
                ],
            )
        
        next_event = self.current_graph.topological_sort() 
        if next_event is not None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text", 
                        text=(
                            "Error: The graph expansion cannot be finished. " 
                            f"The event '{next_event.title}' (id: {next_event.id}) is still pending expansion. " 
                            "Only after all events are expanded, the graph expansion can be finished."
                        ),
                    )
                ], 
            )

        self.current_graph.finish()
        if self.parent_event is not None:
            self.parent_event.complete(self.current_graph)
        await self._trigger_hooks()
        
        return ToolResponse(
            content=[
                TextBlock(
                    type="text", 
                    text="The current temporal event graph is finished successfully as 'done'.",
                ),
            ],
        )
        
    def list_tools(
        self,
    ) -> list[Callable[..., Coroutine[Any, Any, ToolResponse]]]:
        base_tools = [
            self.create_events,
            self.create_edges,
            self.allocate_external_sessions,
            self.expand_event_into_session,
            self.expand_event_into_graph,
            self.finish_graph_expansion,
        ]
        return base_tools

    async def get_current_hint(self) -> Msg | None:
        hint_content = self.graph_to_hint(
            graph=self.current_graph,
            scheduler=self.scheduler,
            level=self.level,
        )
        if hint_content:
            msg = Msg(
                "user",
                hint_content,
                "user",
            )
            return msg

        return None

    def is_finished(self) -> ToolResponse:
        """Check whether the graph expansion process is finished.
        
        Returns:
            `ToolResponse`:
                The response indicating whether the graph expansion is complete.
        """
        if self.current_graph.state != "done":
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: The graph expansion process is not finished yet. "
                            "Please finish the graph expansion process first by calling "
                            "'finish_graph_expansion'."
                        ),
                    ),
                ],
                metadata={
                    "success": False,
                    "response_msg": None,
                },
            )
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text="The state of the graph expansion process is the final state.",
                ),
            ],
            metadata={
                "success": True,
                "response_msg": None,
            },
        )