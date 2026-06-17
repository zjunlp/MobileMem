# -*- coding: utf-8 -*-
"""The constant graph notebook state scheduler."""
from ._base import GraphNotebookStateSchedulerBase
from ..models import Event, PersonBase
from typing import Literal


class ConstantGraphNotebookStateScheduler(GraphNotebookStateSchedulerBase):
    """The scheduler that uses constant values for the minimum and maximum number of events."""
    
    def __init__(
        self,
        min_events: int | None = None, 
        max_events: int | None = None, 
        max_depth: int | None = None,
        is_agent_control: bool = False,
        grounded_session_subgraph_threshold: int | None = None,
    ) -> None:
        """
        Initialize the constant scheduler. 
        
        It is the simplest scheduler that uses constant values for the minimum and 
        maximum number of events for each level.
        
        Args:
            min_events (`int | None`, optional):
                The minimum number of events for each level. If `None`, `1` is used.
            max_events (`int | None`, optional):
                The maximum number of events for each level. If `None`, no limit is used.
            max_depth (`int | None`, optional):
                The maximum depth of the trajectory. If `None`, no limit is used.
            is_agent_control (`bool`, defaults to `False`):
                Whether the scheduler is agent-controlled.
            grounded_session_subgraph_threshold (`int | None`, optional):
                The threshold on the number of grounded sessions assigned to an event.
                When an event's grounded session count exceeds this threshold, the event is
                not forced to expand into a single session even at the maximum depth. 
        """
        super().__init__()

        if min_events is not None and min_events <= 0:
            raise ValueError(
                "The minimum number of events must be greater than 0. "
                f"However, you provided {min_events}."
            )
        self.min_events = min_events or 1 

        if max_events is not None and max_events < self.min_events:
            raise ValueError(
                "The maximum number of events must be greater than or equal to the minimum number of events. "
                f"However, you provided {max_events}, which is less than {self.min_events}."
            ) 
        self.max_events = max_events

        if max_depth is not None and max_depth <= 0:
            raise ValueError(
                "The maximum depth must be greater than 0. "
                f"However, you provided {max_depth}."
            )
        self.max_depth = max_depth or float("inf")

        self.is_agent_control = is_agent_control

        if (
            grounded_session_subgraph_threshold is not None
            and grounded_session_subgraph_threshold < 0
        ):
            raise ValueError(
                "The grounded session subgraph threshold must be non-negative. "
                f"However, you provide '{grounded_session_subgraph_threshold}'."
            )
        self.grounded_session_subgraph_threshold = grounded_session_subgraph_threshold
        
        # Register state for serialization
        self.register_state("min_events")
        self.register_state("max_events")
        self.register_state("max_depth")
        self.register_state("is_agent_control")
        self.register_state("grounded_session_subgraph_threshold")
    
    def get_min_events(self, level: int) -> int:
        return self.min_events
    
    def get_max_events(self, level: int) -> int | None:
        return self.max_events
    
    def get_expansion_strategy(
        self,
        parent: Event | PersonBase, 
        level: int | None = None,
    ) -> Literal["session_only", "subgraph_only", "both"]:
        level = level or 0 
        # If the event already holds too many grounded sessions, do not force it to expand
        # into a single session at the maximum depth. Expanding it into a sub-event graph
        # instead allows the grounded sessions to be distributed across sub-events rather than
        # being merged into one session.
        if (
            self.grounded_session_subgraph_threshold is not None
            and isinstance(parent, Event)
            and parent.num_grounded_sessions > self.grounded_session_subgraph_threshold
        ):
            return "both" if self.is_agent_control else "subgraph_only"
        if level + 1 <= self.max_depth - 1:
            return "both" if self.is_agent_control else "subgraph_only"
        return "session_only"
