from .session import Message, Session
from .persona import (
    Person, 
    PersonBase, 
    TrackedAttribute, 
    AttributeVersion,
)
from .app_interactions import (
    AppInteractionBase,
    VoiceMemoInteraction,
    CalendarInteraction,
    NoteInteraction,
    TodoInteraction,
)
from .graph import (
    Requirement,
    TemporalEventGraph,
    Event,
    Edge,
    GraphRefinementState,
)
from .question_answering import (
    QuestionType,
    QuestionTypeToolbook,
    QuestionAnswerPair,
    QASynthesisState, 
)
from pydantic import (
    BaseModel, 
    Field, 
    PrivateAttr,
)
from datetime import datetime
from typing import Any, Literal


class TrajectorySynthesisState(BaseModel):
    """
    Track the global state of the recursive trajectory synthesis process.
    
    This model maintains the current person context, active graphs, and
    synthesis progress. Acts as a "snapshot" of the entire trajectory at any point.
    """

    person: PersonBase = Field(
        description="The global user context for the trajectory.",
    )
    graphs: dict[str, TemporalEventGraph] = Field(
        default_factory=dict,
        description=(
            "All temporal event graphs created during synthesis, indexed by "
            "graph_id."
        ),
    )
    sessions: dict[str, Session] = Field(
        default_factory=dict,
        description=(
            "All sessions generated during synthesis, indexed by "
            "session_id."
        ),
    )

    # All events generated during synthesis, indexed by event_id.
    _event_id_to_event: dict[str, Event] = PrivateAttr(default_factory=dict)
    _event_id_to_graph_id: dict[str, str] = PrivateAttr(default_factory=dict)
    
    # Track event IDs for each graph to detect additions and deletions.
    _graph_id_to_event_ids: dict[str, set[str]] = PrivateAttr(default_factory=dict)

    # All messages generated during synthesis, indexed by message_id.
    _message_id_to_message: dict[str, Message] = PrivateAttr(default_factory=dict)
    _message_id_to_session_id: dict[str, str] = PrivateAttr(default_factory=dict)

    # It is used to query the child node ID of a given node ID in the hierarchy. 
    _node_id_to_child_id: dict[str, str] = PrivateAttr(default_factory=dict)

    def model_post_init(self, context: Any) -> None:
        """It is used to initialize the private attributes after the model is created."""
        for graph in self.graphs.values():
            event_ids = set()
            for event in graph.events:
                self._event_id_to_event[event.id] = event
                self._event_id_to_graph_id[event.id] = graph.id
                event_ids.add(event.id)
            self._graph_id_to_event_ids[graph.id] = event_ids
            
            if graph.parent_id is None: 
                if self.person.id in self._node_id_to_child_id:
                    raise ValueError(f"Person with id {self.person.id} already has a child graph.")
                self._node_id_to_child_id[self.person.id] = graph.id
            else:
                if graph.parent_id in self._node_id_to_child_id:
                    raise ValueError(f"Event with id {graph.parent_id} already has a child graph.")
                self._node_id_to_child_id[graph.parent_id] = graph.id
        
        for session_id, session in self.sessions.items():
            for message in session.messages:
                self._message_id_to_message[message.id] = message
                self._message_id_to_session_id[message.id] = session_id
            if session.event_id is None:
                if self.person.id in self._node_id_to_child_id:
                    raise ValueError(f"Person with id {self.person.id} already has a child.")
                self._node_id_to_child_id[self.person.id] = session_id
            else:
                if session.event_id in self._node_id_to_child_id:
                    raise ValueError(f"Event with id {session.event_id} already has a child.")
                self._node_id_to_child_id[session.event_id] = session_id

    def add_graph(self, graph: TemporalEventGraph) -> None:
        """
        Add a new temporal event graph to the state.
        
        Args:
            graph (`TemporalEventGraph`):
                The temporal event graph to add to the state.
        """
        if graph.id in self.graphs:
            raise ValueError(f"Graph with id {graph.id} already exists.")
        self.graphs[graph.id] = graph
        
        # Update mappings
        event_ids = set()
        for event in graph.events:
            if event.id in self._event_id_to_event:
                raise ValueError(
                    f"Event with id {event.id} already exists. "
                    "Different graphs cannot have the same event ID."
                )
            self._event_id_to_event[event.id] = event
            self._event_id_to_graph_id[event.id] = graph.id
            event_ids.add(event.id)
        self._graph_id_to_event_ids[graph.id] = event_ids
        
        if graph.parent_id is None:
            if self.person.id in self._node_id_to_child_id:
                raise ValueError(f"Person with id {self.person.id} already has a child.")
            self._node_id_to_child_id[self.person.id] = graph.id
        else:
            if graph.parent_id in self._node_id_to_child_id:
                raise ValueError(f"Event with id {graph.parent_id} already has a child.")
            self._node_id_to_child_id[graph.parent_id] = graph.id

    def refresh_graph(self, graph_id: str) -> None:
        """
        Refresh the specified graph's content by updating event mappings.
        
        This method detects newly added events and deleted events in the graph,
        and updates the internal mappings accordingly. Only unexpanded events
        can be deleted. 
        
        It also considers the case where the event is replaced by a new event with the same ID.
        
        Args:
            graph_id (`str`):
                The ID of the graph to refresh.
        
        Raises:
            `ValueError`:
                If the graph with the given ID does not exist.
        """
        if graph_id not in self.graphs:
            raise ValueError(f"Graph with id {graph_id} does not exist.")
        
        graph = self.graphs[graph_id]
        
        # Get previous event IDs for this graph
        previous_event_ids = self._graph_id_to_event_ids[graph_id]
        current_event_ids = set()
        
        for current_event in graph.events: 
            if current_event.id not in previous_event_ids:
                if current_event.id in self._event_id_to_event:
                    raise ValueError(
                        f"Event with id {current_event.id} already exists in another graph. "
                        "Different graphs cannot have the same event ID."
                    )
            # Always update the reference, even for existing events.
            # This is crucial because graph.events may contain a new Event instance with
            # the same ID (e.g., after `revise_event` replaces the old object).
            self._event_id_to_event[current_event.id] = current_event
            self._event_id_to_graph_id[current_event.id] = graph_id
            current_event_ids.add(current_event.id)

            current_output = current_event._output
            if isinstance(current_output, Session) and current_output.id not in self.sessions:
                self.add_session(current_output)
        
        for previous_event_id in previous_event_ids:
            if previous_event_id not in current_event_ids:
                del self._event_id_to_event[previous_event_id]
                del self._event_id_to_graph_id[previous_event_id]

        # Update the tracked event IDs for this graph
        self._graph_id_to_event_ids[graph_id] = current_event_ids

    def add_session(self, session: Session) -> None:
        """
        Add a new session to the state.
        
        Args:
            session (`Session`):
                The session to add to the state.
        """
        if session.id in self.sessions:
            raise ValueError(f"Session with id {session.id} already exists.")
        self.sessions[session.id] = session
        
        # Update mappings
        for message in session.messages:
            if message.id in self._message_id_to_message:
                raise ValueError(
                    f"Message with id {message.id} already exists. "
                    "Different sessions cannot have the same message ID."
                )
            self._message_id_to_message[message.id] = message
            self._message_id_to_session_id[message.id] = session.id
        if session.event_id is None:
            if self.person.id in self._node_id_to_child_id:
                raise ValueError(f"Person with id {self.person.id} already has a child.")
            self._node_id_to_child_id[self.person.id] = session.id
        else:
            if session.event_id in self._node_id_to_child_id:
                raise ValueError(f"Event with id {session.event_id} already has a child.")
            self._node_id_to_child_id[session.event_id] = session.id

    def get_sessions(self, start: str | None = None, end: str | None = None) -> list[Session]:
        """
        Get a list of sessions sorted by start time.

        Optionally filter by time range which returns sessions that have any
        overlap with the specified time interval (start, end).
        
        Args:
            start (`str | None`, optional, defaults to `None`):
                Start time in ISO 8601 format (YYYY-MM-DD HH:MM:SS). If None, 
                no lower bound is applied.
            end (`str | None`, optional, defaults to `None`):
                End time in ISO 8601 format (YYYY-MM-DD HH:MM:SS). If None,
                no upper bound is applied.
            
        Returns:
            `list[Session]`:
                List of sessions sorted by start time (earliest first).
                Sessions are guaranteed to be non-overlapping in time.
        """
        sessions = list(self.sessions.values())
        
        # Filter by time range if specified
        if start is not None or end is not None:
            start_dt = datetime.fromisoformat(start) if start else None
            end_dt = datetime.fromisoformat(end) if end else None
            
            filtered = []
            for sess in sessions:
                sess_start = datetime.fromisoformat(sess.started_at)
                sess_end = datetime.fromisoformat(sess.ended_at)
                
                # Check if session overlaps with (start, end)
                if start_dt and sess_end <= start_dt:
                    continue
                if end_dt and sess_start >= end_dt:
                    continue
                    
                filtered.append(sess)
            
            sessions = filtered
        
        # Sort by start time
        sessions.sort(key=lambda s: datetime.fromisoformat(s.started_at))
        return sessions

    def get_events(
        self,
        start: str | None = None,
        end: str | None = None,
    ) -> list[Event]:
        """
        Get a list of all events sorted by completion order (end time).
        
        Optionally filter by time range which returns events that have any
        overlap with the specified time interval (start, end).
        
        Args:
            start (`str | None`, optional, defaults to `None`):
                Start time in ISO 8601 format (YYYY-MM-DD HH:MM:SS). If None,
                no lower bound is applied.
            end (`str | None`, optional, defaults to `None`):
                End time in ISO 8601 format (YYYY-MM-DD HH:MM:SS). If None,
                no upper bound is applied.
            
        Returns:
            `list[Event]`:
                List of events sorted by end time (earliest completion first).
                Events may be overlapping in time.
        """
        # Collect all events from all graphs
        events = []
        for graph in self.graphs.values():
            events.extend(graph.events)
        
        # Filter by time range if specified
        if start is not None or end is not None:
            start_dt = datetime.fromisoformat(start) if start else None
            end_dt = datetime.fromisoformat(end) if end else None
            
            filtered = []
            for event in events:
                event_start = datetime.fromisoformat(event.started_at)
                event_end = datetime.fromisoformat(event.ended_at)
                
                # Check if event overlaps with (start, end)
                if start_dt and event_end <= start_dt:
                    continue
                if end_dt and event_start >= end_dt:
                    continue
                    
                filtered.append(event)
            
            events = filtered
        
        # Sort by end time (completion order)
        events.sort(key=lambda e: datetime.fromisoformat(e.ended_at))
        return events

    def get_last_session(self) -> Session | None:
        """
        Get the last session in the state.
        
        Returns:
            `Session | None`:
                The last session, or None if no sessions exist.
        """
        sessions = self.get_sessions()
        return sessions[-1] if sessions else None

    def get_first_session(self) -> Session | None:
        """
        Get the first session in the state.
        
        Returns:
            `Session | None`:
                The first session, or None if no sessions exist.
        """
        sessions = self.get_sessions()
        return sessions[0] if sessions else None

    def get_last_event(self) -> Event | None:
        """
        Get the last event in the state.
        
        Returns:
            `Event | None`:
                The last event, or None if no events exist.
        """
        events = self.get_events()
        return events[-1] if events else None

    def get_first_event(self) -> Event | None:

        """
        Get the first event in the state.
        
        Returns:
            `Event | None`:
                The first event, or None if no events exist.
        """
        events = self.get_events()
        return events[0] if events else None

    def get_event_by_id(self, event_id: str) -> Event | None:
        """
        Find an event by its ID across all graphs.
        
        Args:
            event_id (`str`):
                The event ID to search for.
            
        Returns:
            `Event | None`:
                The event if found, None otherwise.
        """
        return self._event_id_to_event.get(event_id)

    def get_graph_by_id(self, graph_id: str) -> TemporalEventGraph | None:
        """
        Get a graph by its ID.
        
        Args:
            graph_id (`str`):
                The graph ID to retrieve.
            
        Returns:
            `TemporalEventGraph | None`:
                The graph if found, None otherwise.
        """
        return self.graphs.get(graph_id)

    def get_session_by_id(self, session_id: str) -> Session | None:
        """
        Get a session by its ID.
        
        Args:
            session_id (`str`):
                The session ID to retrieve.
            
        Returns:
            `Session | None`:
                The session if found, None otherwise.
        """
        return self.sessions.get(session_id)

    def get_message_by_id(self, message_id: str) -> Message | None:
        """
        Find a message by its ID.
        
        Args:
            message_id (`str`):
                The message ID to search for.
                
        Returns:
            `Message | None`:
                The message if found, None otherwise.
        """
        return self._message_id_to_message.get(message_id)

    def get_child_node_id(self, node_id: str) -> str | None:
        """
        Get the child node ID for a given parent node ID.
        
        Args:
            node_id (`str`):
                The parent node ID (person_id, event_id).
                
        Returns:
            `str | None`:
                The child node ID (graph_id or session_id), or None if no child exists.
        """
        return self._node_id_to_child_id.get(node_id)

    def get_node_type(self, node_id: str) -> Literal[
        "person", 
        "graph", 
        "event", 
        "session", 
        "message"
    ]:
        """
        Determine the type of a node by its ID prefix.
        
        Args:
            node_id (`str`):
                The node ID to check.
                
        Returns:
            `Literal[
                "person", 
                "graph", 
                "event", 
                "session", 
                "message"
            ]
                One of: 'person', 'graph', 'event', 'session', 'message'.
        """
        for node_type in [
            "person", 
            "graph", 
            "event", 
            "session", 
            "message"
        ]:
            if node_id.startswith(node_type):
                return node_type
        raise ValueError(
            f"The node ID {node_id} is invalid. "
            "It should start with one of the following: person, graph, event, session, message. "
            "Note that the ID of each node should be set by the system, not by the user."
        )

    def get_graph_for_visualization(
        self, 
        node_id: str | None = None, 
        expand_messages: bool = False
    ) -> dict[str, Any]:
        """
        Get graph data structure for visualization.
        
        Args:
            node_id (`str | None`, optional, defaults to `None`):
                The node ID to visualize. If None, shows the root.
            expand_messages (`bool`, optional, defaults to `False`):
                If True, expand the conversation to show messages.
        Returns:
            `dict[str, Any]`:
                Dictionary containing:
                    - nodes: list of node dictionaries with id, name, symbolSize, category
                    - edges: list of edge dictionaries with source, target
                    - categories: list of category dictionaries
                    - current_node_id: ID of the current node being visualized
                    - node_details: markdown string of current node details
                    - can_expand: whether the current view can be expanded to next level
                    - can_go_back: whether can go back to parent level
                    - parent_node_id: ID of parent node if exists
        """
        nodes = []
        edges = []
        categories = [
            {
                "name": "Person", 
                "itemStyle": {"color": "#5470c6"}
            },
            {
                "name": "Graph", 
                "itemStyle": {"color": "#91cc75"}
            },
            {
                "name": "Event (Expanded)", 
                "itemStyle": {"color": "#fa8c16"}
            },
            {
                "name": "Event (Unexpanded)", 
                "itemStyle": {"color": "#faad14"}
            },
            {
                "name": "Session", 
                "itemStyle": {"color": "#f44336"}
            },
            {
                "name": "User Message", 
                "itemStyle": {"color": "#d5a6bd"}
            },
            {
                "name": "Assistant Message", 
                "itemStyle": {"color": "#9fc5e8"}
            },
            {
                "name": "System Message", 
                "itemStyle": {"color": "#b4a7d6"}
            }
        ]

        def get_message_category(msg: Message) -> int:
            if msg.role == "user":
                return 5  
            elif msg.role == "assistant":
                return 6  
            else:
                return 7 
        
        current_node_id = node_id or self.person.id
        try:
            node_type = self.get_node_type(current_node_id)
        except ValueError as e:
            return self._get_error_graph_data(e.message)
        
        if node_type == "person":
            # Show only person node at root level
            category = 0 
            item_style = categories[category]["itemStyle"]
            nodes.append(
                {
                    "id": self.person.id,
                    "name": f"Person: {self.person.name}",
                    "symbolSize": 80,
                    "category": category,
                    "label": {"show": True},
                    "itemStyle": item_style
                }
            )
            
            node_details = self.person.to_markdown(include_side_note=True)
            parent_node_id = None
            child_id = self.get_child_node_id(self.person.id)
            can_expand = child_id is not None
            can_go_back = False
            
        elif node_type == "graph":
            graph = self.get_graph_by_id(current_node_id)
            if not graph:
                return self._get_error_graph_data("Graph not found")
            
            # Store parent for navigation
            if graph.parent_id is not None:
                parent_node_id = graph.parent_id
            else:
                parent_node_id = self.person.id
            
            # Only show events in this graph (not the graph node itself or parent)
            for event in graph.events:
                size = 50 if event.state == "expanded" else 40
                category = 2 if event.state == "expanded" else 3
                item_style = categories[category]["itemStyle"]
                nodes.append(
                    {
                        "id": event.id,
                        "name": event.title[:40] + "..." if len(event.title) > 40 else event.title,
                        "symbolSize": size,
                        "category": category,
                        "label": {"show": True},
                        "itemStyle": item_style
                    }
                )
            
            # Add edges between events (dependencies)
            for edge in graph.edges:
                edges.append(
                    {
                        "source": edge.from_event,
                        "target": edge.to_event,
                        "lineStyle": {
                            "color": "#1f1836",
                            "type": "dashed",
                            "width": 2
                        },
                        "symbol": ["none", "arrow"],
                        "symbolSize": [0, 12]
                    }
                )
            
            node_details = graph.to_markdown(include_side_note=True)
            can_expand = False
            can_go_back = True
            
        elif node_type == "event":
            event = self.get_event_by_id(current_node_id)
            if not event:
                return self._get_error_graph_data("Event not found")
            
            # Find parent graph for navigation
            parent_graph = self.get_graph_by_id(self._event_id_to_graph_id[event.id])

            parent_node_id = parent_graph.id
            category = 2 if event.state == "expanded" else 3
            item_style = categories[category]["itemStyle"]
            
            # Only show current event (no children)
            nodes.append(
                {
                    "id": event.id,
                    "name": event.title,
                    "symbolSize": 70,
                    "category": category,
                    "label": {"show": True},
                    "itemStyle": item_style
                }
            )
            
            node_details = event.to_markdown(include_side_note=True)
            child_id = self.get_child_node_id(event.id)
            can_expand = child_id is not None
            can_go_back = parent_node_id
            
        elif node_type == "session":
            sess = self.get_session_by_id(current_node_id)
            if not sess:
                return self._get_error_graph_data("Session not found")
            
            # Find parent for navigation
            if sess.event_id is not None:
                parent_node_id = sess.event_id
            else:
                parent_node_id = self.person.id
            
            if expand_messages:
                # Show messages as a chain/list
                prev_msg_id = None
                for msg in sess.messages:
                    msg_preview = msg.content[:50] + "..." if len(msg.content) > 50 else msg.content
                    category = get_message_category(msg)
                    item_style = categories[category]["itemStyle"]
                    nodes.append(
                        {
                            "id": msg.id,
                            "name": f"{msg.name}: {msg_preview}",
                            "symbolSize": 35,
                            "category": category,
                            "label": {"show": True, "fontSize": 11},
                            "itemStyle": item_style
                        }
                    )
                    
                    # Link messages in sequence (chain)
                    if prev_msg_id is not None:
                        edges.append(
                            {
                                "source": prev_msg_id,
                                "target": msg.id,
                                "lineStyle": {"color": "#999", "width": 2, "type": "solid"},
                                "symbol": ["none", "arrow"],
                                "symbolSize": [0, 10]
                            }
                        )
                    prev_msg_id = msg.id
                
                node_details = sess.to_markdown(include_side_note=True)
                can_expand = False  # Already expanded to messages
                can_go_back = True  # Can go back to session node
            else:
                # Only show session node (can be expanded to see messages)
                category = 4
                item_style = categories[category]["itemStyle"]
                nodes.append(
                    {
                        "id": sess.id,
                        "name": f"Session ({len(sess.messages)} messages)",
                        "symbolSize": 70,
                        "category": category, 
                        "label": {"show": True},
                        "itemStyle": item_style
                    }
                )
                
                node_details = sess.to_markdown(include_side_note=True)
                can_expand = True  # Can expand to see messages
                can_go_back = True
            
        else:
            msg = self.get_message_by_id(current_node_id)
            if not msg:
                return self._get_error_graph_data("Message not found")
            parent_sess = self.get_session_by_id(self._message_id_to_session_id[msg.id])
            category = get_message_category(msg)
            item_style = categories[category]["itemStyle"]
            nodes.append(
                {
                    "id": msg.id,
                    "name": f"{msg.name}: {msg.content[:60]}...",
                    "symbolSize": 50,
                    "category": category,
                    "label": {"show": True},
                    "itemStyle": item_style
                }
            )
            
            # Build detailed markdown for this message
            node_details = msg.to_markdown(include_side_note=True)
            parent_node_id = parent_sess.id
            can_expand = False  
            can_go_back = True  # Can go back to session messages view
        
        return {
            "nodes": nodes,
            "edges": edges,
            "categories": categories,
            "current_node_id": current_node_id,
            "node_details": node_details,
            "can_expand": can_expand,
            "can_go_back": can_go_back,
            "parent_node_id": parent_node_id,
        }

    def _get_error_graph_data(self, error_message: str) -> dict[str, Any]:
        """Create error graph data structure."""
        return {
            "nodes": [],
            "edges": [],
            "categories": [],
            "current_node_id": None,
            "node_details": f"# Error\n\n{error_message}",
            "can_expand": False,
            "can_go_back": False,
            "parent_node_id": None,
        } 

    def get_statistics(self) -> dict[str, Any]:
        """
        Get comprehensive statistics about the trajectory.
        
        Returns:
            `dict[str, Any]`:
                Dictionary containing various statistics including:
                - total_graphs: Number of temporal event graphs
                - total_events: Total number of events across all graphs
                - total_sessions: Number of sessions
                - total_messages: Total number of messages
                - events_by_state: Count of events in each state
                - avg_events_per_graph: Average events per graph
                - avg_messages_per_session: Average messages per session
                - time_span_days: Duration of trajectory in days
        """
        total_events = sum(len(graph.events) for graph in self.graphs.values())
        total_messages = sum(len(sess.messages) for sess in self.sessions.values())
        
        # Count events by state
        events_by_state: dict[str, int] = {
            "to_expand": 0,
            "expanding": 0,
            "expanded": 0,
        }
        for graph in self.graphs.values():
            for event in graph.events:
                events_by_state[event.state] += 1
        
        # Calculate time span
        start_dt = datetime.fromisoformat(self.person.trajectory_start)
        end_dt = datetime.fromisoformat(self.person.trajectory_end)
        time_span_days = (end_dt - start_dt).days
        
        return {
            "person_name": self.person.name,
            "trajectory_start": self.person.trajectory_start,
            "trajectory_end": self.person.trajectory_end,
            "time_span_days": time_span_days,
            "total_graphs": len(self.graphs),
            "total_events": total_events,
            "total_sessions": len(self.sessions),
            "total_messages": total_messages,
            "events_by_state": events_by_state,
            "avg_events_per_graph": (
                total_events / len(self.graphs) if self.graphs else 0
            ),
            "avg_messages_per_session": (
                total_messages / len(self.sessions) if self.sessions else 0
            ),
        }


__all__ = [
    "Message",
    "Session",
    "Person",
    "Requirement",
    "TemporalEventGraph",
    "Event",
    "Edge",
    "GraphRefinementState",
    "TrajectorySynthesisState",
    "TrackedAttribute",
    "AttributeVersion",
    "AppInteractionBase",
    "VoiceMemoInteraction",
    "CalendarInteraction",
    "NoteInteraction",
    "TodoInteraction",
    "QuestionType",
    "QuestionTypeToolbook",
    "QuestionAnswerPair",
    "QASynthesisState",
]

