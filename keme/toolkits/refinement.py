# -*- coding: utf-8 -*-
"""The graph refinement notebook to manage graph refinement, 
providing hints and refinement-related tools to the agent."""
from agentscope.message import Msg, TextBlock
from agentscope.tool import ToolResponse
from datetime import datetime
from ..models import (
    GraphRefinementState, 
    TemporalEventGraph, 
    Event, 
    Edge, 
)
from ..models.persona import PersonBase
from ..schedulers import (
    GraphNotebookStateSchedulerBase, 
    ConstantGraphNotebookStateScheduler,
)
from ._base import NotebookBase
from ._mixin import EventValidatorMixin
from typing import (
    Callable, 
    Coroutine,
    Any,
)


class DefaultGraphRefinementToHint:
    """The default function to generate the hint message based on the current 
    temporal event graph state to guide the agent during graph refinement."""
    
    hint_prefix: str = "<system-hint>"
    hint_suffix: str = "</system-hint>"
    
    graph_ready_for_refinement: str = (
        "The current temporal event graph:\n"
        "```\n"
        "{graph}\n"
        "```\n"
        "The graph now has {num_events} event(s) and {num_edges} edge(s).\n"
        "The statistics of the current graph are as follows:\n"
        "The Number of Connected Components: {num_connected_component}\n"
        "The Statistics of Requirements:\n"
        "{requirements_statistics}\n"
        "Your options include:\n"
        "- Add a new event to the graph by calling 'add_event'.\n"
        "- Modify an existing unexpanded event (title, summary, time range, requirements, side note) by calling 'revise_event'.\n"
        "- Remove an unexpanded event and all its associated edges by calling 'delete_event'.\n"
        "- Add a dependency edge between events by calling 'add_edge'.\n"
        "- Modify an existing edge (name, source/target event IDs, side note) by calling 'revise_edge'.\n"
        "- Remove a dependency edge by calling 'delete_edge'.\n"
        "- Complete the refinement process and optionally update the graph's side note by calling 'finish_refinement', " 
        "and then call 'generate_response' to summarize the refinement process."
    )

    after_refinement: str = (
        "The final refined temporal event graph:\n"
        "```\n"
        "{graph}\n"
        "```\n"
        "The graph has {num_events} event(s) and {num_edges} edge(s).\n"
        "The statistics of the current graph are as follows:\n"
        "The Number of Connected Components: {num_connected_component}\n"
        "The Statistics of Requirements:\n"
        "{requirements_statistics}\n"
        "Your options include:\n"
        "- Summarize the refinement process by calling 'generate_response'."
    )
    
    def __call__(
        self,
        state: GraphRefinementState,
    ) -> str:
        """Generate the hint message based on the current graph refinement state 
        to guide the agent during refinement.
        
        Args:
            state (`GraphRefinementState`):
                The current graph refinement state, used to generate the hint message.
        
        Returns:
            `str`:
                The generated hint message.
        """
        state_markdown = state.to_markdown(include_side_note=True, include_output=False)

        num_events = len(state.graph.events)
        num_edges = len(state.graph.edges)
        num_connected_component = state.graph.get_num_connected_component() 
        requirements_statistics = state.graph.get_statistics_of_requirements()
        requirements_statistics_str = [f"- {k}: {v}" for k, v in requirements_statistics.items()]
        sorted_order = sorted(
            requirements_statistics.items(), 
            key=lambda origin_tuple: origin_tuple[1]
        ) 
        total_requirements = sum(count for _, count in sorted_order)
        if sorted_order[0][1] / total_requirements <= 0.1: 
            requirements_statistics_str.append(
                f"**WARNING**: {sorted_order[0][0]} is less than 10% of the total requirements. "
                "Please ensure the diversity of requirements."
            )
        requirements_statistics_str = "\n".join(requirements_statistics_str)

        if state.state == "refining":
            hint = self.graph_ready_for_refinement.format(
                graph=state_markdown,
                num_events=num_events,
                num_edges=num_edges,
                num_connected_component=num_connected_component,
                requirements_statistics=requirements_statistics_str,
            )
        else:
            hint = self.after_refinement.format(
                graph=state_markdown,
                num_events=num_events,
                num_edges=num_edges,
                num_connected_component=num_connected_component,
                requirements_statistics=requirements_statistics_str,
            )

        return f"{self.hint_prefix}{hint}{self.hint_suffix}"


class GraphRefinementNotebook(NotebookBase, EventValidatorMixin):
    """The graph refinement notebook to manage graph refinement, 
    providing hints and refinement-related tools to the agent."""
    
    description: str = (
        "The graph refinement-related tools for improving temporal event graphs. "
        "Activate this tool when you need to refine and improve an existing temporal event graph. "
        "Once activated, you'll enter the refinement mode, where you will be guided to review and improve "
        "the graph structure, events, dependencies, and requirements. The hint messages wrapped by "
        "<system-hint></system-hint> will guide you to complete the task. "
        "If you think the refinement is complete, call 'finish_refinement' to finish the refinement process."
    )
    name: str = "graph_refinement_related"

    def __init__(
        self,
        person: PersonBase,
        agent_name: str,
        current_graph: TemporalEventGraph,
        parent_event: Event | None = None,
        level: int | None = None,
        scheduler: GraphNotebookStateSchedulerBase | None = None,
        refinement_to_hint: Callable[[TemporalEventGraph | None], str | None] | None = None,
    ) -> None:
        """Initialize the graph refinement notebook.
        
        Args:
            person (`PersonBase`):
                The person that this notebook belongs to.
            agent_name (`str`):
                The name of the agent that this notebook belongs to.
            current_graph (`TemporalEventGraph`):
                The temporal event graph to refine. This graph must already exist.
            parent_event (`Event | None`, optional):
                The parent event of the current graph. If not provided, the current graph is the root event.
            level (`int | None`, optional):
                The hierarchy level (0 = root level, higher = deeper). If not provided, the root level is used.
            scheduler (`GraphNotebookStateSchedulerBase | None`, optional):
                The scheduler instance to use for managing constraints. If not provided, 
                a default `ConstantGraphNotebookStateScheduler` object will be used.
            refinement_to_hint (`Callable[[TemporalEventGraph | None], str | None] | None`, optional):
                The function to generate hint messages based on the current graph state.
                If not provided, a default `DefaultGraphRefinementToHint` object will be used.
        """
        super().__init__()
        
        self.person = person
        self.agent_name = agent_name
        self.current_state = GraphRefinementState(graph=current_graph)
        self.parent_event = parent_event
        self.level = level or 0 
        if self.parent_event is None and self.level > 0:
            raise ValueError(
                "The parent event is not provided, but the level is greater than 0. "
                "You need to provide the parent event when the level is greater than 0."
            )

        self.scheduler = scheduler or ConstantGraphNotebookStateScheduler()
        self.refinement_to_hint = refinement_to_hint or DefaultGraphRefinementToHint()
        
        # Register state for state management
        self.register_state(
            "current_state",
            custom_to_json=lambda _: _.model_dump() if _ else None,
            custom_from_json=lambda _: GraphRefinementState.model_validate(_) if _ else None,
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

    @property 
    def current_graph(self) -> TemporalEventGraph:
        """Get the current temporal event graph."""
        return self.current_state.graph
    
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
        if max_events is not None and len(self.current_state.graph.events) >= max_events:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: Cannot add the event. The current graph already has "
                            f"{len(self.current_state.graph.events)} event(s), which reaches the maximum limit "
                            f"of {max_events} event(s) allowed at this hierarchy level."
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
        
        self.current_state.graph.events.append(event)
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
        event_idx, existing_event = self.current_state.graph.get_event_by_id(event_id)
        if existing_event is None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"Error: Event with ID '{event_id}' is not found in the current graph.",
                    ),
                ],
            )
        
        # Check if event is already expanded
        if existing_event.state == "expanded":
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: Cannot revise event '{existing_event.title}' (id: {event_id}) "
                            "because it has already been expanded (state: 'expanded'). "
                            "Only events in 'to_expand' or 'expanding' state can be revised."
                        ),
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
            # If the time span is changed, we need to check whether relevant edges are still valid
            for edge in self.current_state.graph.edges:
                if edge.from_event == event_id: 
                    _, target_event = self.current_state.graph.get_event_by_id(edge.to_event)
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
                                        "which breaks the required temporal order that the source event " 
                                        "must complete before the target event begins."
                                    ), 
                                ),
                            ],
                        )
                elif edge.to_event == event_id:
                    _, source_event = self.current_state.graph.get_event_by_id(edge.from_event)
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
                                        "which breaks the required temporal order that the source event " 
                                        "must complete before the target event begins."
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
        self.current_state.graph.events[event_idx] = event
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
        min_events = self.scheduler.get_min_events(self.level)
        if len(self.current_state.graph.events) <= min_events:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: Cannot delete the event. The current graph already has "
                            f"{len(self.current_state.graph.events)} event(s), which reaches the minimum limit of "
                            f"{min_events} event(s) allowed at this hierarchy level."
                        ),
                    ),
                ],
            )
        
        # Find the event to delete
        _, existing_event = self.current_state.graph.get_event_by_id(event_id)
        if existing_event is None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"Error: Event with ID '{event_id}' is not found in the current graph.",
                    ),
                ],
            )
        
        if existing_event.state == "expanded":
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: Cannot delete event '{existing_event.title}' (id: {event_id}) "
                            "because it has already been expanded (state: 'expanded'). "
                            "Only events in 'to_expand' or 'expanding' state can be deleted."
                        ),
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
                            "You can try other approaches to refine the graph."
                        ),
                    ),
                ],
            )
        
        # Remove edges involving this event
        self.current_state.graph.edges = [
            e for e in self.current_state.graph.edges 
            if e.from_event != event_id and e.to_event != event_id
        ]
        self.current_state.graph.events = [e for e in self.current_state.graph.events if e.id != event_id]
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
        _, from_event = self.current_state.graph.get_event_by_id(edge.from_event)
        if from_event is None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"Error: Source event with ID '{edge.from_event}' is not found in the current graph.",
                    ),
                ],
            )
        
        _, to_event = self.current_state.graph.get_event_by_id(edge.to_event)
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
        
        # Check if target event is already expanded
        if to_event.state == "expanded":
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: Cannot add edge because the target event '{to_event.title}' "
                            f"(id: {edge.to_event}) has already been expanded (state: 'expanded'). "
                            "The target event must be in 'to_expand' or 'expanding' state."
                        ),
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
                            "The source event must complete before the target event begins."
                        ),
                    ),
                ],
            )
        
        # Try to add edge and validate DAG structure
        try:
            self.current_state.graph.edges.append(edge)
            self.current_state.graph.topological_sort()
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
            self.current_state.graph.edges = self.current_state.graph.edges[:-1]
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
        edge_idx, existing_edge = self.current_state.graph.get_edge_by_id(edge_id)
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
        _, from_event = self.current_state.graph.get_event_by_id(edge.from_event)
        if from_event is None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"Error: Source event with ID '{edge.from_event}' is not found in the current graph.",
                    ),
                ],
            )
        
        _, to_event = self.current_state.graph.get_event_by_id(edge.to_event)
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
        
        # Check if new target event is already expanded
        if to_event.state == "expanded":
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: Cannot revise edge because the new target event '{to_event.title}' "
                            f"(id: {edge.to_event}) has already been expanded (state: 'expanded'). "
                            "The target event must be in 'to_expand' or 'expanding' state."
                        ),
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
                            "You can try other approaches to refine the temporal event graph. If you really want to set "
                            f"this edge from '{from_event.title}' (id: {edge.from_event}) to '{to_event.title}' (id: {edge.to_event}), "
                            f"you can revise the source event (if it is not expanded) to end earlier than {to_event.started_at}, "
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
            self.current_state.graph.edges[edge_idx] = edge
            self.current_state.graph.topological_sort()
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
            self.current_state.graph.edges[edge_idx] = existing_edge
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
        edge_idx, existing_edge = self.current_state.graph.get_edge_by_id(edge_id)
        if existing_edge is None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"Error: Edge with ID '{edge_id}' is not found in the current graph.",
                    ),
                ],
            )

        _, to_event = self.current_state.graph.get_event_by_id(existing_edge.to_event)
        if to_event is not None and to_event.state == "expanded":
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: Cannot delete edge '{existing_edge.name}' (id: {edge_id}) because its target event '{to_event.title}' " 
                            f"(id: {existing_edge.to_event}) has already been expanded (state: 'expanded'). "
                            "It is not allowed to delete an edge that is connected to an expanded target event."
                        ),
                    ),
                ],
            )
        
        # Delete the edge
        deleted_edge = self.current_state.graph.edges.pop(edge_idx)
        await self._trigger_hooks()
        
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Edge '{deleted_edge.name}' (id: {edge_id}) is deleted successfully.",
                ),
            ],
        )
    
    async def finish_refinement(self, graph_side_note: str | None = None) -> ToolResponse:
        """Finish the refinement process and comment on the refined graph.
        
        Args:
            graph_side_note (`str | None`, optional):
                The new side note of the refined graph. 
                If not provided, the original side note will be preserved.
        
        Returns:
            `ToolResponse`:
                The response of the tool call, confirming the refinement process completion.
        """
        if graph_side_note is not None:
            self.current_state.graph.side_note = graph_side_note
            text = (
                "The graph refinement process is finished successfully with the graph's side note updated. "
                "The refined graph is now ready for next expansion."
            )
        else:
            text = (
                "The graph refinement process is finished successfully. "
                "The refined graph is now ready for next expansion."
            )
        self.current_state.finish_refinement()
        await self._trigger_hooks()
        
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=text,
                ),
            ],
        )
    
    def list_tools(
        self,
    ) -> list[Callable[..., Coroutine[Any, Any, ToolResponse]]]:
        return [
            self.add_event,
            self.revise_event,
            self.delete_event,
            self.add_edge,
            self.revise_edge,
            self.delete_edge,
            self.finish_refinement,
        ]
    
    async def get_current_hint(self) -> Msg | None:
        hint_content = self.refinement_to_hint(self.current_state)
        if hint_content:
            msg = Msg(
                "user",
                hint_content,
                "user",
            )
            return msg
        
        return None
    
    def is_finished(self) -> ToolResponse:
        """Check whether the graph refinement process is finished.
        
        Returns:
            `ToolResponse`:
                The response indicating whether the graph refinement is complete.
        """
        if self.current_state.state != "refined":
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: The graph refinement process is not finished yet. "
                            "Please finish the graph refinement process first by calling "
                            "'finish_refinement'."
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
                    text="The state of the graph refinement process is the final state.",
                ),
            ],
            metadata={
                "success": True,
                "response_msg": None,
            },
        )