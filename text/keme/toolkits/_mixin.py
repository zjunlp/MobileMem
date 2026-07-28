from ..models import Event
from datetime import datetime
import difflib


class EventValidatorMixin:
    """The mixin class to validate the event."""

    def _validate_events_time_range(self, events: Event | list[Event]) -> str | None:
        """Validate the time range of events."""
        if isinstance(events, Event):
            events = [events]
        
        if self.parent_event is None:
            parent_start = datetime.fromisoformat(self.person.trajectory_start)
            parent_end = datetime.fromisoformat(self.person.trajectory_end)
            constraint_source = "person's trajectory"
        else:
            parent_start = datetime.fromisoformat(self.parent_event.started_at)
            parent_end = datetime.fromisoformat(self.parent_event.ended_at)
            constraint_source = "parent event's"
        
        for i, event in enumerate(events):
            event_start = datetime.fromisoformat(event.started_at)
            event_end = datetime.fromisoformat(event.ended_at)
            if event_start < parent_start or event_end > parent_end:
                return (
                    f"Error: Event '{event.title}' (index {i}) has time range " 
                    f"({event.started_at} to {event.ended_at}) which is outside "
                    f"the {constraint_source} time range ({parent_start} to {parent_end}). " 
                    f"All events must fall within the {constraint_source} time span."
                )
        
        return None
    
    def _validate_requirements_source(self, events: Event | list[Event]) -> str | None: 
        """Validate each event's requirements by checking the source of each requirement."""
        if isinstance(events, Event):
            events = [events]
        
        invalid_requirements = [] 
        for event in events:
            event_id = event.id 
            for requirement in event.requirements:
                source_id = requirement.from_source

                # Valid case 1: source is the Person profile
                if source_id == self.person.id:
                    continue 

                # Valid case 2: source is an agent ID (starts with 'agent')
                if source_id == self.agent_name:
                    continue 

                # Valid case 3: source is inherited from parent event requirements
                if (
                    self.parent_event is not None  
                    and any(
                        source_id == parent_req.from_source 
                        for parent_req in self.parent_event.requirements
                    )
                ): 
                    continue

                # Valid case 4: source is an event in current graph with edge to target event
                source_found = False 
                if self.current_graph is not None:
                    for source_event in self.current_graph.events:
                        if source_id == source_event.id:
                            source_found = True
                            # Check if there's an edge from source_event to the target event
                            if all(
                                edge.to_event != event_id 
                                for edge in self.current_graph.edges 
                                if edge.from_event == source_event.id
                            ):
                                # Source event exists but no edge to target event
                                invalid_requirements.append(
                                    f"Event '{event.title}' (id: {event_id}) has a requirement " 
                                    f"'{requirement.name}' with an invalid source. "
                                    f"The source (id: {source_id}) is an event that exists in the same graph, "
                                    "but there is no dependency edge from the source event to the target event. "
                                    "According to the requirements management rules, when a requirement's source "
                                    "is an event in the current graph, there must be an edge from that source event "
                                    "to the event containing the requirement."
                                )
                            break
                
                # Invalid case: source not found in any valid location
                if not source_found:
                    if self.parent_event is not None and source_id == self.parent_event.id:
                        # Remind the agent to keep the original `from_source` unchanged
                        invalid_requirements.append(
                            f"Event '{event.title}' (id: {event_id}) has a requirement "
                            f"'{requirement.name}' with an invalid source (id: {source_id}). "
                            "This source ID is equal to the parent event's ID. When copying or inheriting "
                            "requirements from the parent event, you MUST keep each requirement's original "
                            "`from_source` unchanged (i.e., the person / agent / event that originally "
                            "introduced the requirement). Do NOT set `from_source` to the parent event's ID."
                        )
                    else: 
                        invalid_requirements.append(
                            f"Event '{event.title}' (id: {event_id}) has a requirement "
                            f"'{requirement.name}' with an unrecognized source (id: {source_id}). "
                            "The source is not: (1) the Person profile, "
                            "(2) your ID NUMBER, "
                            "(3) an event in the current graph with an edge to the target event containing this requirement, "
                            "(4) or a source ID that exactly matches the `from_source` of a requirement in the parent event "
                            "when the parent event is given (i.e., the source ID is inherited unchanged from the parent "
                            "requirement, not set to the parent event's own ID)."
                        )
                        # Begin to find the most similar candidate
                        candidate = None
                        if source_id.startswith("person_"):
                            candidate = self.person.id
                        elif source_id.startswith("agent_"):
                            candidates = [self.agent_name.lstrip("agent_")]
                            if self.parent_event is not None:
                                for parent_req in self.parent_event.requirements:
                                    if parent_req.from_source.startswith("agent_"):
                                        candidates.append(parent_req.from_source.lstrip("agent_"))
                            candidates = list(set(candidates))
                            closest_match = difflib.get_close_matches(
                                source_id.lstrip("agent_"), 
                                candidates, 
                                n=1, 
                                cutoff=0.8
                            ) 
                            if closest_match:
                                candidate = f"agent_{closest_match[0]}"
                        elif source_id.startswith("event_"):
                            if self.current_graph is not None:
                                candidates = [
                                    edge.from_event.lstrip("event_")
                                    for edge in self.current_graph.edges
                                    if edge.to_event == event_id
                                ]
                            else: 
                                candidates = []
                            if self.parent_event is not None:
                                for parent_req in self.parent_event.requirements:
                                    if parent_req.from_source.startswith("event_"):
                                        candidates.append(parent_req.from_source.lstrip("event_"))
                            candidates = list(set(candidates))
                            closest_match = difflib.get_close_matches(
                                source_id.lstrip("event_"), 
                                candidates, 
                                n=1, 
                                cutoff=0.8
                            ) 
                            if closest_match:
                                candidate = f"event_{closest_match[0]}"
                        if candidate is not None:
                            invalid_requirements.append(f"Do you mean {candidate}?")
        
        if invalid_requirements: 
            invalid_requirements.append(
                "Please verify that the source ID is correct and the requirement follows the requirements management rules." 
            )
            return f"Error: Find invalid requirement(s).\n{'\n'.join(invalid_requirements)}"
                

        return None