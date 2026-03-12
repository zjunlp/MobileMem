# -*- coding: utf-8 -*-
"""Session Grounding Notebook for distributing external sessions to temporal event graphs."""
from agentscope.message import Msg, TextBlock
from agentscope.tool import ToolResponse
from agentscope.token import OpenAITokenCounter
from datetime import datetime
from pydantic import BaseModel, Field
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
from ._base import NotebookBase
from ._mixin import EventValidatorMixin
import shortuuid
from typing import (
    Callable, 
    Coroutine,
    Any,
)


_SYSTEM_PROMPT = (
    "You are an expert at summarizing long text while preserving key information."
)
_TASK_PROMPT = (
    "Please summarize the following compatibility context. "
    "The context consists of multiple entries, each associated with a specific and relatively fine-grained time range. "
    "When summarizing, you may merge adjacent or contiguous entries into broader time spans, " 
    "thereby coarsening the temporal granularity, as long as no important temporal distinctions are lost. "
    "Focus on preserving key events, decisions, and information that are important for maintaining consistency in the future.\n\n"
    "Compatibility Context:\n{context}"
)


class _SummarizationOutput(BaseModel):
    """Structured output for compatibility context summarization."""
    
    summarization_result: str = Field(
        ...,
        description=(
            "The summarized compatibility context that preserves key information "
            "from different time periods while being more concise."
        ),
    )


def _find_compatible_events(graph: TemporalEventGraph, session: Session) -> list[Event]:
    """Find events in the graph whose time range fully contains the session.
    
    Args:
        graph (`TemporalEventGraph`):
            The temporal event graph to find compatible events in.
        session (`Session`):
            The session to find compatible events for.
            
    Returns:
        `list[Event]`:
            List of events that can accommodate the session.
    """
    session_start = datetime.fromisoformat(session.started_at)
    session_end = datetime.fromisoformat(session.ended_at)
    compatible_events = []
    for event in graph.events:
        event_start = datetime.fromisoformat(event.started_at)
        event_end = datetime.fromisoformat(event.ended_at)
        if event_start <= session_start and event_end >= session_end:
            compatible_events.append(event)
    
    return compatible_events


class DefaultSessionGroundingToHint:
    """The default function to generate the hint message based on the current 
    session grounding state to guide the agent during session distribution."""
    
    hint_prefix: str = "<system-hint>"
    hint_suffix: str = "</system-hint>"
    
    session_pending: str = (
        "The current temporal event graph:\n"
        "```\n"
        "{graph}\n"
        "```\n"
        "The compatible events whose time range fully contains the session's time interval:\n"
        "{compatible_events}\n"
        "Your options include:\n"
        "- If compatible events exist, assign the session to one of them by calling 'assign_session_to_event'.\n"
        "- If no compatible events exist or existing events are not suitable, you can:\n"
        "  - Add a new event by calling 'add_event'.\n"
        "  - Modify an existing event (title, summary, time range, requirements, side note) by calling 'revise_event'.\n"
        "  - Delete an event and all its associated edges by calling 'delete_event'.\n"
        "  - Add, revise, or delete edges by calling 'add_edge', 'revise_edge', or 'delete_edge'."
    )
    
    after_assignment: str = (
        "The current temporal event graph:\n"
        "```\n"
        "{graph}\n"
        "```\n"
        "Your options include:\n"
        "- Append new content to the current compatibility context of {event_title} (id: {event_id}) by calling 'append_compatibility_context'.\n"
        "- Revise other events (title, summary, time range, requirements, side note) by calling 'revise_event'.\n"
        "- Finish the session grounding process by calling 'finish_session_grounding', and then call 'generate_response' to summarize the grounding results."
    )
    
    def __call__(
        self,
        graph: TemporalEventGraph,
        session: Session,
    ) -> str | None:
        """Generate the hint message based on the current session grounding state.
        
        Args:
            graph (`TemporalEventGraph`):
                The current temporal event graph.
            session (`Session`):
                The external session to be grounded.
        
        Returns:
            `str | None`:
                The generated hint message, or None if there is no relevant hint.
        """
        graph_markdown = graph.to_markdown(include_side_note=True, include_output=False)
        
        # Check if the external session has been assigned to an event
        session_event_id = session.event_id or "" 
        _, assigned_event = graph.get_event_by_id(session_event_id) 
        
        if assigned_event is not None:
            hint = self.after_assignment.format(
                graph=graph_markdown,
                event_title=assigned_event.title,
                event_id=assigned_event.id,
            )
        else:
            compatible_events = _find_compatible_events(graph, session)
            if compatible_events:
                compatible_events_str = "\n".join(
                    [
                        f"- '{event.title}' (id: {event.id}, time: {event.started_at} to {event.ended_at})"
                        for event in compatible_events
                    ]
                )
            else:
                compatible_events_str = "- No compatible events are found. You need to modify the graph structure."
            hint = self.session_pending.format(
                graph=graph_markdown,
                compatible_events=compatible_events_str,
            )
        
        return f"{self.hint_prefix}{hint}{self.hint_suffix}"


class SessionGroundingNotebook(NotebookBase, EventValidatorMixin):
    """The session grounding notebook to manage the distribution of an external session
    to events within a temporal event graph."""
    
    description: str = (
        "The session grounding-related tools for distributing an external session to events. "
        "Activate this tool when you need to assign an external session to events in a temporal event graph. "
        "Once activated, you'll enter the session grounding mode, where you will be guided to assign the session to events in a temporal event graph. "
        "The hint messages wrapped by <system-hint></system-hint> will guide you to complete the task. "
        "If you think the grounding process is complete, call 'finish_session_grounding' to finish the grounding process."
    )
    name: str = "session_grounding_related"

    def __init__(
        self,
        person: PersonBase,
        agent_name: str,
        current_graph: TemporalEventGraph,
        session: Session,
        parent_event: Event | None = None,
        level: int | None = None,
        scheduler: GraphNotebookStateSchedulerBase | None = None,
        grounding_to_hint: Callable[[TemporalEventGraph, Session], str | None] | None = None,
        compatibility_context_max_tokens: int = 8000,
        **kwargs: Any,
    ) -> None:
        """Initialize the session grounding notebook.
        
        Args:
            person (`PersonBase`):
                The person that this notebook belongs to.
            agent_name (`str`):
                The name of the agent that this notebook belongs to.
            current_graph (`TemporalEventGraph`):
                The temporal event graph to ground sessions into.
            session (`Session`):
                The session to be grounded.
            parent_event (`Event | None`, optional):
                The parent event of the current graph.
            level (`int | None`, optional):
                The hierarchy level (0 = root level, higher = deeper).
            scheduler (`GraphNotebookStateSchedulerBase | None`, optional):
                The scheduler instance to use for managing constraints.
            grounding_to_hint (`Callable[..., str] | None`, optional):
                The function to generate hint messages based on the current grounding state.
            compatibility_context_max_tokens (`int`, Defaults to `8000`):
                The maximum number of tokens allowed for compatibility context before 
                triggering summarization.
            **kwargs: (`Any`)
                Additional keyword arguments to pass to the summarization agent. The summarization agent is an instance of `ReActAgent`.
        """
        super().__init__()
        
        self.person = person
        self.agent_name = agent_name
        self.current_graph = current_graph
        self.session = session
        self.parent_event = parent_event
        self.level = level or 0
        
        self.scheduler = scheduler or ConstantGraphNotebookStateScheduler()
        self.grounding_to_hint = grounding_to_hint or DefaultSessionGroundingToHint()
        
        self.compatibility_context_max_tokens = compatibility_context_max_tokens
        self.agent_kwargs = kwargs
        
        # Track the grounding progress
        self._is_completed = False 
        
        # Register state for state management
        self.register_state(
            "current_graph",
            custom_to_json=lambda _: _.model_dump() if _ else None,
            custom_from_json=lambda _: TemporalEventGraph.model_validate(_) if _ else None,
        )
        self.register_state(
            "session",
            custom_to_json=lambda _: _.model_dump() if _ else None,
            custom_from_json=lambda _: Session.model_validate(_) if _ else None,
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
        self.register_state("level")
        self.register_state("_is_completed")
        self.register_state("compatibility_context_max_tokens")

    async def assign_session_to_event(self, event_id: str) -> ToolResponse:
        """Assign the current session to a specified event.
        
        Args:
            event_id (`str`):
                The ID of the event to assign the session to.
        
        Returns:
            `ToolResponse`:
                The response of the tool call, confirming the assignment or reporting errors.
        """
        # First, validate the session has not been assigned to any event yet
        session_event_id = self.session.event_id or "" 
        _, assigned_event = self.current_graph.get_event_by_id(session_event_id)
        if assigned_event is not None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: The session has already been assigned to event '{assigned_event.title}' (id: {assigned_event.id}). "
                            "The session can only be assigned once to an event."
                        ),
                    ),
                ],
            )

        # Second, validate the event ID
        _, target_event = self.current_graph.get_event_by_id(event_id)
        if target_event is None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"Error: Event with ID '{event_id}' is not found in the current graph.",
                    ),
                ],
            )
        
        # Third, validate whether the event is compatible with the session
        candidates = _find_compatible_events(self.current_graph, self.session)
        is_candidate = False 
        candidate_strs = [] 
        for candidate in candidates:
            if candidate.id == event_id:
                is_candidate = True
                break
            candidate_strs.append(f"- '{candidate.title}' (id: {candidate.id}, time range: {candidate.started_at} to {candidate.ended_at})")
        if not is_candidate:
            if candidate_strs:
                guide_message = (
                    "The compatible events (whose time range fully contains the session's time range) are listed as follows:\n"
                    f"{'\n'.join(candidate_strs)}\n"
                    "Please choose one of the compatible events to assign the session to. "
                    "If these events are not semantically suitable for the session, you can either add a new event "
                    "or revise an existing event's content (such as summary, requirements, or other attributes) "
                    "to better align with the session before assigning."
                )
            else:
                guide_message = (
                    "No compatible events found whose time range fully contains the session's time range. "
                    "You need to modify the graph structure by adding a new event with an appropriate time range, "
                    "or revising an existing event's time range and other attributes to accommodate the session, then assign the session to it."
                )
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: Event '{target_event.title}' (id: {target_event.id}) is not a compatible event for the session. "
                            f"The session's time range ({self.session.started_at} to {self.session.ended_at}) "
                            f"is not fully contained within the event's time range ({target_event.started_at} to {target_event.ended_at}).\n\n"
                            f"{guide_message}"
                        ),
                    ),
                ],
            )
        
        # Assign the session to the target event
        target_event.add_grounded_session(self.session)
        self.session.event_id = target_event.id
        await self._trigger_hooks()
        
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"The session has been assigned to event '{target_event.title}' (id: {target_event.id}) successfully.",
                ),
            ],
        )

    async def add_event(self, event: Event) -> ToolResponse:
        """Add a new event to the current temporal event graph.
        
        Args:
            event (`Event`):
                The event to add to the graph. The event will be assigned a unique ID upon creation.
        
        Returns:
            `ToolResponse`:
                The response of the tool call, confirming event addition or reporting errors.
        """                
        event = Event.model_validate(event)
        
        # Validate max events constraint
        max_events = self.scheduler.get_max_events(self.level)
        if max_events is not None and len(self.current_graph.events) >= max_events:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: Cannot add a new event. The current graph already has "
                            f"{len(self.current_graph.events)} event(s), which reaches the maximum limit "
                            f"of {max_events} event(s) allowed at this hierarchy level.\n\n"
                            "You can try other approaches to modify the graph structure. If you really need to add a new event, "
                            "you can delete an existing event that has no grounded sessions by calling 'delete_event'."
                        ),
                    ),
                ],
            )
        
        # Validate the event 
        msg = self._validate_events_time_range(event) or self._validate_requirements_source(event)
        if msg is not None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=msg,
                    ),
                ],
            )
        
        self.current_graph.events.append(event)
        await self._trigger_hooks()
        
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Event '{event.title}' (id: {event.id}) is added to the current graph successfully.",
                ),
            ],
        )

    async def revise_event(self, event_id: str, event: Event) -> ToolResponse:
        """Modify an existing event in the current temporal event graph.
        
        Args:
            event_id (`str`):
                The ID of the event to revise.
            event (`Event`):
                The revised event data. This event object will completely replace the existing event,
                so you must provide all attributes (title, summary, time range, requirements, side note, etc.),
                including those that remain unchanged. The event ID will be preserved from the `event_id` parameter
                and should not be included in the event object.
        
        Returns:
            `ToolResponse`:
                The response of the tool call, confirming the revision or reporting errors.
        """
        # Find the event to revise
        event_idx, existing_event = self.current_graph.get_event_by_id(event_id)
        if existing_event is None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"Error: Event with ID '{event_id}' is not found in the current graph.",
                    ),
                ],
            )
        
        event = Event.model_validate(event)
        event.id = event_id
        
        msg = self._validate_events_time_range(event) or self._validate_requirements_source(event)
        if msg is not None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=msg,
                    ),
                ],
            )

        if event.state != existing_event.state:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: You are attempting to change the state of event '{event_id}' "
                            f"from '{existing_event.state}' to '{event.state}'. However, the 'state' "
                            "field is managed internally by the system and cannot be modified directly. "
                            "Please remove the 'state' change from your update and try again."
                        ),
                    ),
                ],
            )

        if event.started_at != existing_event.started_at or event.ended_at != existing_event.ended_at:        
            for edge in self.current_graph.edges:
                if edge.from_event == event_id: 
                    _, target_event = self.current_graph.get_event_by_id(edge.to_event)
                    end_time = datetime.fromisoformat(event.ended_at)
                    start_time = datetime.fromisoformat(target_event.started_at)
                    if end_time > start_time:
                        return ToolResponse(
                            content=[
                                TextBlock(
                                    type="text",
                                    text=(
                                        f"Error: Updating the event with ID '{event_id}' to the new time range " 
                                        f"({event.started_at} to {event.ended_at}) would violate " 
                                        f"the dependency edge '{edge.name}' (id: {edge.id}). "
                                        "In this edge, the current event is the source event and must finish " 
                                        f"no later than the start time of its target event '{target_event.title}' (id: {edge.to_event}), " 
                                        f"which begins at {target_event.started_at}. "
                                        f"However, the new end time {event.ended_at} exceeds this start time, " 
                                        "which breaks the required temporal order that the source event must complete before the target event begins.\n\n"
                                        "You can try other approaches to modify the graph structure. If you really want to set "
                                        f"the event's time range to ({event.started_at} to {event.ended_at}), you can "
                                        f"delete the dependency edge (id: {edge.id}) first, "
                                        f"or revise the target event (id: {edge.to_event}) to start later than {event.ended_at}, "
                                        "or adjust the current event's end time to be earlier than the target event's start time."
                                    ), 
                                ),
                            ],
                        )
                elif edge.to_event == event_id:
                    _, source_event = self.current_graph.get_event_by_id(edge.from_event)
                    start_time = datetime.fromisoformat(event.started_at)
                    end_time = datetime.fromisoformat(source_event.ended_at)
                    if end_time > start_time:
                        return ToolResponse(
                            content=[
                                TextBlock(
                                    type="text",
                                    text=(
                                        f"Error: Updating the event with ID '{event_id}' to the new time range " 
                                        f"({event.started_at} to {event.ended_at}) would violate " 
                                        f"the dependency edge '{edge.name}' (id: {edge.id}). "
                                        "In this edge, the current event is the target event and must begin " 
                                        f"later than the end time of its source event '{source_event.title}' (id: {edge.from_event}), " 
                                        f"which ends at {source_event.ended_at}. "
                                        f"However, the new start time {event.started_at} occurs before this end time, " 
                                        "which breaks the required temporal order that the source event must complete before the target event begins.\n\n"
                                        "You can try other approaches to modify the graph structure. If you really want to set "
                                        f"the event's time range to ({event.started_at} to {event.ended_at}), you can "
                                        f"delete the dependency edge (id: {edge.id}) first, "
                                        f"or revise the source event (id: {edge.from_event}) to end earlier than {event.started_at}, "
                                        "or adjust the current event's start time to be later than the source event's end time."
                                    ), 
                                ),
                            ],
                        )
                
        if existing_event.has_grounded_sessions:
            grounded_sessions = existing_event.grounded_sessions
            if event.started_at > grounded_sessions[0].started_at or event.ended_at < grounded_sessions[-1].ended_at:
                return ToolResponse(
                    content=[
                        TextBlock(
                            type="text",
                            text=(
                                f"Error: The new time range you specified for event '{existing_event.title}' (ID: '{event_id}') "
                                f"({event.started_at} to {event.ended_at}) is not compatible with its grounded sessions. "
                                f"This event has {len(grounded_sessions)} grounded session(s) with time range from "
                                f"{grounded_sessions[0].started_at} to {grounded_sessions[-1].ended_at}. "
                                "The event's time range must fully contain all grounded sessions. "
                                f"Please ensure the new start time is no later than {grounded_sessions[0].started_at} "
                                f"and the new end time is no earlier than {grounded_sessions[-1].ended_at}."
                            ),
                        ),
                    ],
                )
            
            for grounded_session in grounded_sessions:
                event.add_grounded_session(grounded_session)
            event.append_compatibility_context(existing_event.compatibility_context)
        
        # Update the event
        self.current_graph.events[event_idx] = event
        await self._trigger_hooks()
        
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Event with ID '{event_id}' is revised successfully.",
                ),
            ],
        )

    async def delete_event(self, event_id: str) -> ToolResponse:
        """Remove an unexpanded event from the current temporal event graph.
        
        This will also remove all edges connected to this event.
        
        Args:
            event_id (`str`):
                The ID of the event to delete.
        
        Returns:
            `ToolResponse`:
                The response of the tool call, confirming the deletion or reporting errors.
        """        
        # Check minimum events constraint
        min_events = self.scheduler.get_min_events(self.level)
        if len(self.current_graph.events) <= min_events:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: Cannot delete event. The graph has {len(self.current_graph.events)} event(s), "
                            f"which is the minimum required ({min_events}) at this hierarchy level.\n\n"
                            "You can try other approaches to modify the graph structure. If you really need to delete a new event, "
                            "you can add a new event by calling 'add_event' first."
                        ),
                    ),
                ],
            )
        
        _, existing_event = self.current_graph.get_event_by_id(event_id)
        if existing_event is None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"Error: Event with ID '{event_id}' is not found in the current graph.",
                    ),
                ],
            )
        
        # Events with grounded sessions cannot be deleted
        if existing_event.has_grounded_sessions:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: Cannot delete event '{existing_event.title}' (id: {event_id}) "
                            f"because it has {existing_event.num_grounded_sessions} grounded session(s). "
                            "Events with grounded sessions are protected from deletion. " 
                            "You can try other approaches to modify the graph structure."
                        ),
                    ),
                ],
            )
        
        # Remove associated edges
        self.current_graph.edges = [
            e for e in self.current_graph.edges 
            if e.from_event != event_id and e.to_event != event_id
        ]
        self.current_graph.events = [e for e in self.current_graph.events if e.id != event_id]
        await self._trigger_hooks()
        
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Event '{existing_event.title}' (id: {event_id}) is deleted successfully.",
                ),
            ],
        )

    async def add_edge(self, edge: Edge) -> ToolResponse:
        """Add a dependency edge between events in the current temporal event graph.
        
        Args:
            edge (`Edge`):
                The edge to add. Must reference existing events in the graph.
        
        Returns:
            `ToolResponse`:
                The response of the tool call, confirming edge addition or reporting errors.
        """
        edge = Edge.model_validate(edge)
        
        # Validate that both events exist
        _, from_event = self.current_graph.get_event_by_id(edge.from_event)
        if from_event is None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"Error: Source event with ID '{edge.from_event}' is not found in the current graph.",
                    ),
                ],
            )
        
        _, to_event = self.current_graph.get_event_by_id(edge.to_event)
        if to_event is None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"Error: Target event with ID '{edge.to_event}' is not found in the current graph.",
                    ),
                ],
            )
        
        if edge.from_event == edge.to_event:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text="Error: Cannot create self-loop. An event cannot depend on itself.",
                    ),
                ],
            )
        
        # Validate temporal constraint: source event must end before target event starts
        source_end = datetime.fromisoformat(from_event.ended_at)
        target_start = datetime.fromisoformat(to_event.started_at)
        if source_end > target_start:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: Temporal constraint violation. "
                            f"Source event '{from_event.title}' ends at {from_event.ended_at}, "
                            f"but target event '{to_event.title}' starts at {to_event.started_at}. "
                            "The source event must complete before the target event begins.\n\n"
                            "You can try other approaches to modify the graph structure. If you really want to add this edge, "
                            f"you can revise the source event (id: {edge.from_event}) to end earlier than {to_event.started_at}, "
                            f"or revise the target event (id: {edge.to_event}) to start later than {from_event.ended_at}."
                        ),
                    ),
                ],
            )
        
        # Try to add edge and validate DAG structure
        try:
            self.current_graph.edges.append(edge)
            self.current_graph.topological_sort()
            await self._trigger_hooks()
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"Edge '{edge.name}' (id: {edge.id}) is added successfully.",
                    ),
                ],
            )
        except ValueError as e:
            self.current_graph.edges = self.current_graph.edges[:-1]
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"Error: Failed to add edge '{edge.name}' (id: {edge.id}). {str(e)}",
                    ),
                ],
            )
    
    async def revise_edge(self, edge_id: str, edge: Edge) -> ToolResponse:
        """Modify an existing edge in the current temporal event graph.
        
        Args:
            edge_id (`str`):
                The ID of the edge to revise.
            edge (`Edge`):
                The revised edge data. This edge object will completely replace the existing edge,
                so you must provide all attributes (name, side note, etc.), including those that remain unchanged. 
                The edge ID will be preserved from the `edge_id` parameter and should not be included in the edge object.
        
        Returns:
            `ToolResponse`:
                The response of the tool call, confirming the revision or reporting errors.
        """
        # Find the edge to revise
        edge_idx, existing_edge = self.current_graph.get_edge_by_id(edge_id)
        if existing_edge is None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"Error: Edge with ID '{edge_id}' is not found in the current graph.",
                    ),
                ],
            )
        
        edge = Edge.model_validate(edge)
        
        # Validate that both events exist
        _, from_event = self.current_graph.get_event_by_id(edge.from_event)
        if from_event is None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"Error: Source event with ID '{edge.from_event}' is not found in the current graph.",
                    ),
                ],
            )
        
        _, to_event = self.current_graph.get_event_by_id(edge.to_event)
        if to_event is None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"Error: Target event with ID '{edge.to_event}' is not found in the current graph.",
                    ),
                ],
            )
        
        if edge.from_event == edge.to_event:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text="Error: Cannot create self-loop. An event cannot depend on itself.",
                    ),
                ],
            )
        
        # Validate temporal constraint
        source_end = datetime.fromisoformat(from_event.ended_at)
        target_start = datetime.fromisoformat(to_event.started_at)
        if source_end > target_start:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: Temporal constraint violation. "
                            f"Source event '{from_event.title}' ends at {from_event.ended_at}, "
                            f"but target event '{to_event.title}' starts at {to_event.started_at}. "
                            "The source event must complete before the target event begins.\n\n"
                            "You can try other approaches to modify the graph structure. If you really want to set "
                            f"this edge from '{from_event.title}' (id: {edge.from_event}) to '{to_event.title}' (id: {edge.to_event}), "
                            f"you can revise the source event to end earlier than {to_event.started_at}, "
                            f"or revise the target event to start later than {from_event.ended_at}, "
                            "or choose different events for this edge that satisfy the temporal constraint."
                        ),
                    ),
                ],
            )
        
        # Preserve the original edge ID
        edge.id = edge_id
        
        # Try to update edge and validate DAG structure
        try:
            self.current_graph.edges[edge_idx] = edge
            self.current_graph.topological_sort()
            await self._trigger_hooks()
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"Edge with ID '{edge_id}' is revised successfully.",
                    ),
                ],
            )
        except ValueError as e:
            # Rollback the change
            self.current_graph.edges[edge_idx] = existing_edge
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"Error: Failed to revise edge with ID '{edge_id}'. {str(e)}",
                    ),
                ],
            )
    
    async def delete_edge(self, edge_id: str) -> ToolResponse:
        """Remove a dependency edge from the current temporal event graph.
        
        Args:
            edge_id (`str`):
                The ID of the edge to delete.
        
        Returns:
            `ToolResponse`:
                The response of the tool call, confirming the deletion or reporting errors.
        """
        # Find the edge to delete
        edge_idx, existing_edge = self.current_graph.get_edge_by_id(edge_id)
        if existing_edge is None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"Error: Edge with ID '{edge_id}' is not found in the current graph.",
                    ),
                ],
            )
        
        # Delete the edge
        deleted_edge = self.current_graph.edges.pop(edge_idx)
        await self._trigger_hooks()
        
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Edge '{deleted_edge.name}' (id: {edge_id}) is deleted successfully.",
                ),
            ],
        )

    async def _summarize_compatibility_context(self, context: str) -> str:
        """Summarize the compatibility context when it exceeds the token limit.
        
        Args:
            context (`str`):
                The compatibility context to summarize.
        
        Returns:
            `str`:
                The summarized compatibility context.
        """
        summarization_agent_kwargs = {**self.agent_kwargs} 
        summarization_agent_kwargs["name"] = f"agent_{shortuuid.uuid()}"
        summarization_agent_kwargs["sys_prompt"] = _SYSTEM_PROMPT

        summarization_agent = SynthesisAgent(**summarization_agent_kwargs)
        response_msg = await summarization_agent(
            msg=Msg(
                "user",
                _TASK_PROMPT.format(context=context),
                "user",
            ),
            structured_model=_SummarizationOutput,
        )
        result = _SummarizationOutput.model_validate(response_msg.metadata)
        return result.summarization_result

    async def append_compatibility_context(self, event_id: str, content: str | None = None) -> ToolResponse:
        """Given an event, it appends new content to this event's compatibility context.
                
        Args:
            event_id (`str`):
                The ID of the event to append the content to.
            content (`str | None`, optional):
                The content to append to the compatibility context of given event. 
                If not provided, the compatibility context of given event will be unchanged.
        
        Returns:
            `ToolResponse`:
                The response of the tool call, confirming the compatibility context update.
        """
        session_event_id = self.session.event_id or "" 
        _, event = self.current_graph.get_event_by_id(session_event_id)
        if event is None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: The session has not yet been assigned to any event in the current "
                            "temporal event graph. Please first call 'assign_session_to_event' to assign "
                            "the session to a compatible event before appending compatibility context."
                        ),
                    ),
                ],
            )
        
        if event_id != session_event_id:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: The session has been assigned to event '{event.title}' (id: {event.id}), "
                            "so you can only append content to this event's compatibility context. "
                            f"The provided event id '{event_id}' does not match."
                        ),
                    ),
                ],
            )

        # Append compatibility context to the event this session is assigned to
        content = content or "" 
        event.append_compatibility_context(content)

        # The token counter is fixed, which means it doesn't depend on the model used. 
        token_counter = OpenAITokenCounter("gpt-4.1")
        token_count = await token_counter.count(
            [
                {
                    "role": "user", 
                    "content": event.compatibility_context
                } 
            ]
        ) 
        
        # Summarize if token count exceeds threshold
        summarization_performed = False
        if token_count > self.compatibility_context_max_tokens:
            summarized_context = await self._summarize_compatibility_context(event.compatibility_context)
            event.overwrite_compatibility_context(summarized_context)
            summarization_performed = True
        
        await self._trigger_hooks() 

        if content: 
            if summarization_performed:
                return ToolResponse(
                    content=[
                        TextBlock(
                            type="text",
                            text=(
                                f"The compatibility context of event with ID '{event_id}' has been updated successfully. "
                                f"The context exceeded {self.compatibility_context_max_tokens} tokens and has been summarized."
                            ),
                        ),
                    ],
                )
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"The compatibility context of event with ID '{event_id}' has been updated successfully.",
                    ),
                ],
            )
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"The compatibility context of event with ID '{event_id}' is unchanged.",
                ),
            ],
        )

    async def finish_session_grounding(self) -> ToolResponse:
        """Finish the session grounding process.
                
        Returns:
            `ToolResponse`:
                The response of the tool call, confirming the grounding process completion.
        """
        session_event_id = self.session.event_id or "" 
        _, event = self.current_graph.get_event_by_id(session_event_id) 

        if event is None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: The session grounding process cannot be finished. "
                            "The session has not yet been assigned to any event in the current temporal event graph. " 
                            "Please assign the session to a compatible event first."
                        ),  
                    ),
                ],
            )

        self._is_completed = True 
        self._trigger_hooks() 
        
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text="The session grounding process is finished successfully."                
                ),
            ],
        )

    def list_tools(
        self,
    ) -> list[Callable[..., Coroutine[Any, Any, ToolResponse]]]:
        return [
            self.assign_session_to_event,
            self.add_event,
            self.revise_event,
            self.delete_event,
            self.add_edge,
            self.revise_edge,
            self.delete_edge,
            self.append_compatibility_context,
            self.finish_session_grounding,
        ]

    async def get_current_hint(self) -> Msg | None:
        hint_content = self.grounding_to_hint(self.current_graph, self.session)
        if hint_content:
            msg = Msg(
                "user",
                hint_content,
                "user",
            )
            return msg
        
        return None

    def is_finished(self) -> ToolResponse:
        if not self._is_completed:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: The session grounding process is not finished yet. "
                            "Please finish the session grounding process first."
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
                    text="The state of the session grounding process is the final state.", 
                ),
            ],
            metadata={
                "success": True,
                "response_msg": None,
            }, 
        )