# -*- coding: utf-8 -*-
"""The base class for the graph notebook state scheduler. It provides 
the base functionality for the graph notebook state scheduler."""
from ..models import (
    Event, 
    PersonBase, 
    Session,
) 
from agentscope.module import StateModule
from typing import Literal


class GraphNotebookStateSchedulerBase(StateModule):
    """The base class for the graph notebook state scheduler. It provides 
    the base functionality for the graph notebook state scheduler."""
    
    def get_min_events(self, level: int) -> int:
        """Get the minimum number of events for a given hierarchy level.
        
        Args:
            level (`int`):
                The hierarchy level (0 = root level, higher = deeper).
                
        Returns:
            `int`:
                The minimum number of events for this level.
        """
        raise NotImplementedError(
            "The get_min_events function is not implemented in "
            f"{self.__class__.__name__}"
        )
    
    def get_max_events(self, level: int) -> int | None:
        """Get the maximum number of events for a given hierarchy level.
        
        Args:
            level (`int`):
                The hierarchy level (0 = root level, higher = deeper).
                
        Returns:
            `int | None`:
                The maximum number of events for this level, or `None` if no limit.
        """
        raise NotImplementedError(
            "The get_max_events function is not implemented in "
            f"{self.__class__.__name__}"
        )
    
    def get_expansion_strategy(
        self, 
        parent: Event | PersonBase, 
        level: int | None = None,
    ) -> Literal[
        "session_only", 
        "subgraph_only", 
        "both"
    ]:
        """Get the expansion strategy for a given parent (an event or a person profile).
        
        Args:
            parent (`Event | PersonBase`):
                The parent event or person to get the expansion strategy for.
            level (`int | None`, optional):
                The hierarchy level (0 = root level, higher = deeper).
                If it is set to `None`, the expansion strategy is determined only 
                based on the parent (an event or a person profile).
                
        Returns:
            `Literal["session_only", "subgraph_only", "both"]`:
                - "session_only": Events should only be expanded to sessions.
                - "subgraph_only": Events should only be expanded to sub-event graphs.
                - "both": Events can be expanded to either sessions or sub-event graphs.
        """
        raise NotImplementedError(
            "The get_expansion_strategy function is not implemented in "
            f"{self.__class__.__name__}"
        )

    def _get_temporal_event_graph_task_instruction(
        self, 
        person: PersonBase, 
        parent_event: Event | None = None,
        level: int = 0,
    ) -> str:
        """Build instruction template for the agents using `TemporalEventGraphNotebook`.
    
        Args:
            person (`PersonBase`):
                The person profile (global context)
            parent_event (`Event | None`, optional):
                The parent event to expand (None for top-level temporal event graph)
            level (`int`, optional):
                The hierarchy level (0 = root, higher = deeper)
            
        Returns:
            `str`:
                The task instruction for the given person, parent event, and level.
        """
        if parent_event is None:
            task_description = (
                "You are creating a **top-level temporal event graph** that organizes "
                "the highest-level life events for this person during the specified time period. "
                "This graph will serve as the root structure for the entire trajectory."
            )
            time_constraint_source = "person's trajectory"
            time_start = person.trajectory_start
            time_end = person.trajectory_end
            parent = person 
        else:
            task_description = (
                f"You are expanding the parent event **'{parent_event.title}'** (id: {parent_event.id}) "
                f"into a temporal sub-event graph. This graph will decompose the parent event into "
                f"more granular sub-events that can be further expanded or converted into sessions."
            )
            time_constraint_source = "parent event's"
            time_start = parent_event.started_at
            time_end = parent_event.ended_at
            parent = parent_event
        
        # Get constraints from scheduler
        min_events = self.get_min_events(level)
        max_events = self.get_max_events(level)
        event_constraints = f"at least {min_events} event(s)"
        if max_events is not None:
            event_constraints += f" and at most {max_events} event(s)"
        
        # Build instruction
        instruction_parts = [
            "# Task",
            task_description,
            "",
            "# Context",
            "",
            "## Person Profile",
            person.to_markdown(include_side_note=True),
            "",
        ]
        if parent_event is not None:
            instruction_parts.extend(
                [
                    "## Parent Event",
                    parent_event.to_markdown(include_side_note=True, include_output=False),
                    "",
                ]
            )
        
        instruction_parts.extend(
            [
                "# Constraints and Requirements",
                "",
                "## Temporal Constraints",
                (
                    f"All events you create MUST fall within the {time_constraint_source} time range:\n"
                    f"- **Start:** {time_start}\n"
                    f"- **End:** {time_end}"
                ),
                "",
                "## Event Count Constraints",
                f"You must create {event_constraints} in this graph.",
                "",
                "## Dependency Constraints",
                (
                    "When creating dependencies (edges) between events:\n"
                    "- Dependencies form a directed acyclic graph (DAG) structure\n"
                    "- Events connected by an edge have strict temporal ordering: the source event must "
                    "complete before the target event begins with no temporal overlap permitted"
                ),
                "",
            ]
        )
        
        # Requirements section
        # Always include Person influence, add parent event if applicable
        instruction_parts.extend(
            [
                "## Requirements Management",
                "",
                (
                    "Requirements eliminate the need to include complete information from all predecessor nodes when expanding events, serving "
                    "as information summaries that extract essential constraints, goals, and dependencies. "
                    "The description of a requirement should be:\n"
                    "- **Specific**: Clearly state what needs to be achieved or what constraint must be "
                    "respected. Avoid vague or ambiguous language.\n"
                    "- **Measurable**: Include concrete criteria or outcomes that can be verified when "
                    "evaluating whether the requirement has been met.\n"
                    "- **Actionable**: Provide sufficient detail for the generation process to understand "
                    "how to incorporate this requirement into the expanded content.\n"
                    "- **Context-aware**: Reference relevant background information, dependencies, or "
                    "conditions that affect how the requirement should be interpreted.\n\n"
                    "The description should be comprehensive enough to serve as a standalone constraint "
                    "that can be understood and applied without requiring additional context from the "
                    "requirement's source."
                ),
                "",
            ]
        )
        
        if parent_event is not None:
            instruction_parts.extend(
                [
                    "### Inheriting Parent Requirements",
                    (
                        "Review every requirement already attached to the parent event. If a requirement should also "
                        "constrain a child event, copy that requirement into the child event's requirement list exactly "
                        "as-is. The `from_source` may reference higher-level ancestor events, the Person profile, "
                        "predecessor sibling events, or an upstream agent ID NUMBER. Copying requirements "
                        "in this way preserves how upstream constraints propagate through the hierarchy. "
                        "Be sure to note that `from_source` takes the value of the original requirement's `from_source` field, " 
                        "not the ID of the original requirement. "
                        f"**Please avert from setting `from_source` to the parent event's ID '{parent_event.id}'.**"
                    ),
                    "",
                ]
            )
        
        instruction_parts.extend(
            [
                "### Adding from Person Profile",
                (
                    "The Person profile (personality, values, likes, dislikes, habits, long-term goals, "
                    "education, occupation, nationality, location, gender, age) influences how events should be generated. "
                    "When creating events, if a Person attribute constrains or influences an event's content, "
                    f"you MUST add a requirement to that event with `from_source='{person.id}'` to explicitly "
                    "document this constraint."
                ),
                "",
            ]
        )
        
        if parent_event is not None:      
            instruction_parts.extend(
                [
                    "## Grounded Sessions and Compatibility Context",
                    "",
                    (
                        "The parent event may have pre-existing external sessions assigned to it. "
                        "You can see two fields in the parent event display:"
                        "- **Grounded Sessions Count**: The number of external sessions assigned to this event.\n"
                        "- **Compatibility Context**: A description that provides context about the grounded sessions assigned to this event, "
                        "and any constraints to consider when expanding the event."
                    ),
                    "",
                    (
                        "When expanding a parent event, especially through the creation of sub-events or edges, " 
                        "any expansion involving grounded sessions should remain semantically compatible with those sessions. This means:\n"
                        "- **Avoid contradictions**: Do not create sub-events whose content would conflict with what "
                        "happens in the grounded sessions.\n"
                        "- **Maintain narrative coherence**: Sub-events should logically lead to or follow from the "
                        "grounded session content. Some sub-events are allowed to be completely unrelated to the grounded session content."
                    ),
                    "",
                ]
            ) 
        
        instruction_parts.extend(
            [
                "# Quality Requirements",
                "",
                "## Event Quality",
                (
                    "- **Titles**: Clear, descriptive (5-20 words), indicating what happens\n"
                    "- **Summaries**: Detailed enough to understand context and outcomes\n"
                    "- **Requirements**: Specific, actionable constraints that influence child events\n"
                    "- **Memory-Testing**: Help create meaningful and difficult question-answering pairs that challenge memory mechanisms"
                ),
                "",
                "## Graph Quality",
                (
                    "- **Coherence**: Events form a logical, realistic sequence\n"
                    "- **Dependencies**: Edges represent meaningful relationships (causal, resource, scheduling, narrative, etc.)\n"
                    "- **Diversity**: Mix of event types and interaction patterns\n"
                    "- **Memory-Testing**: Help create meaningful and difficult question-answering pairs that challenge memory mechanisms"
                ),
                "", 
            ]
        ) 

        instruction_parts.extend(
            [
                "# Workflow and Problem-Solving Strategy",
                "",
                "## 1. Understand the Context",
                (
                    "Before creating any events, carefully read and analyze:\n\n"
                    "- **Person Profile**: Understand the person's profile. Think about how these attributes should influence the events you create."
                ) 
            ]
        ) 
        if parent_event is not None:
            instruction_parts.extend(
                [
                    (
                        "- **Parent Event**: Thoroughly review the parent event's title, summary, "
                        "requirements, compatibility context, and side note. Understand what the parent event represents and how child events "
                        "should decompose or advance it. Consider which parent requirements should be inherited by child events "
                        "(copying them as-is)."
                    )
                ]
            ) 
        instruction_parts.extend(
            [
                (
                    "- **Time Constraints**: Ensure all events fit within the specified time range.\n\n"
                    "Take time to think deeply about how these elements interact and what kind of events would "
                    "form a realistic, coherent narrative that serves the memory evaluation goal."
                ), 
                "" 
            ]
        ) 

        instruction_parts.extend(
            [
                "## 2. Plan the Event Structure",
                (
                    "Think strategically about the event graph structure:\n\n"
                    "- **Event Selection**: Consider what events would meaningfully decompose the parent event "
                    "(or organize the top-level trajectory). Think about diversity, realism, and memory-testing potential.\n"
                    "- **Temporal Organization**: Plan how events should be ordered in time. Consider natural "
                    "progressions, causal relationships, and realistic time distributions.\n"
                    "- **Dependency Design**: Think strategically about which events should depend on others. "
                    "Dependencies can represent various relationships including causal chains (one event causes another), "
                    "resource dependencies (one event provides resources needed by another), scheduling constraints "
                    "(one event must finish before another can start), or narrative connections (one event's outcome "
                    "influences another's context).\n"
                    "- **Requirements Flow**: Plan how requirements should be distributed across child events: "
                    "(1) which parent requirements should be inherited (copied as-is), (2) which new requirements "
                    "should be added from the person profile. "
                    "Consider which child events are most relevant for each requirement.\n\n"
                    "Your thinking should be thorough. It's fine if your planning is extensive. Think step by step "
                    "before creating events."
                ),
                "",
            ]
        ) 

        instruction_parts.extend(
            [   
                "## 3. Expansion and Automatic Graph Refinement",
                "",
                (
                    "The synthesis process requires alternating between expansion and refinement. **Always refine after expanding.** "
                    "This iterative approach ensures quality and coherence throughout the trajectory construction.\n\n"
                    "- **Expansion Purpose**: Expand events to enrich their content, decomposing them into more granular "
                    "sub-events or converting them into sessions. Expansion adds depth and detail to the trajectory.\n\n"
                    "- **Refinement Purpose**: Refine the graph to avoid factual conflicts, logical errors, and unnatural transitions. "
                    "Refinement also strengthens the graph's complexity by adding requirements and constraints, making the overall "
                    "trajectory structure more sophisticated and challenging for memory evaluation."
                ),
                "",
            ]
        )
        
        instruction_parts.extend(
            [
                "### Expansion",
                (
                    "Maintain coherence and consistency. "
                    "These hints will tell you when to expand events and finish the graph. Pay close attention to these hints "
                    "as they reflect the current state and guide your next actions.\n\n"
                    "When expanding events:\n"
                    "- Generate events that reflect your planning and the parent event's context.\n"
                    "- If an event is expanded into a session AND that event has grounded sessions assigned to it " 
                    "(i.e., `Grounded Sessions Count > 0`), the expansion result will be the grounded session itself (if there is only one) " 
                    "or the merged result of all grounded sessions (if there are multiple). This constraint is ensured by the system " 
                    "which automatically uses the pre-existing grounded session(s) as the expansion output.\n"
                ),
            ]
        )
        if self.get_expansion_strategy(parent, level=level) == "both":
            instruction_parts.extend(
                [
                    (
                        "Therefore, for events with grounded sessions, consider expanding into a sub-event graph if:\n"
                        "  - Additional human-AI dialogues are needed to bridge or contextualize the grounded sessions.\n"
                        "  - Merging multiple grounded sessions into one would be unnatural or inappropriate.\n"
                        "  - The grounded sessions alone cannot fulfill all the requirements attached to the event.\n"
                    ),
                    (
                        "- For each event (either with or without grounded sessions) expansion, consider whether it should become a sub-event graph (for further "
                        "decomposition) or a session (as a leaf node). Think about the event's granularity and duration.\n"
                    )
                ]
            )
        instruction_parts.extend(
            [
                "",
                "### Automatic Graph Refinement",
                (
                    "After each event expansion, the system will automatically invoke a refinement process to optimize the graph "
                    "based on the expansion result. You do NOT need to manually refine the graph, just focusing on creating well-planned "
                    "events and expanding them properly. The automatic refinement ensures the graph evolves naturally and maintains quality."
                ),
                "",
            ]
        )
        
        instruction_parts.extend(
            [
                (
                    "Continue this expansion-refinement cycle until all events are expanded." 
                ),
            ]
        )
        
        return "\n".join(instruction_parts)
    
    def _get_session_task_instruction(
        self, 
        person: PersonBase, 
        parent_event: Event | None = None,
    ) -> str:
        """Build instruction template for the agents using `SessionNotebook`.
        
        Args:
            person (`PersonBase`):
                The person profile (global context)
            parent_event (`Event | None`, optional):
                The parent event to expand (None for top-level session)
                
        Returns:
            `str`:
                The task instruction for the given person and parent event.
        """
        # Determine task type
        if parent_event is None:
            task_description = (
                "You are creating a **top-level session** that represents "
                "a direct interaction between the person and an AI assistant during the "
                "specified time period. This session is not associated with any specific event."
            )
            time_constraint_source = "person's trajectory"
            time_start = person.trajectory_start
            time_end = person.trajectory_end
        else:
            task_description = (
                "You are creating a **session** for the parent event "
                f"**'{parent_event.title}'** (id: {parent_event.id}). "
                "This session should reflect real-time interactions between the person "
                "and an AI assistant that occur within the context of this event."
            )
            time_constraint_source = "parent event's"
            time_start = parent_event.started_at
            time_end = parent_event.ended_at
        
        # Build instruction
        instruction_parts = [
            "# Task",
            task_description,
            "",
            "# Context",
            "",
            "## Person Profile",
            (
                "The person profile is dynamic and may be modified during session creation. "
                "Please refer to the **current person profile** in the hint message wrapped by "
                "`<system-hint></system-hint>` for the most up-to-date information."
            ),
            "",
        ]
        
        if parent_event is not None:
            instruction_parts.extend(
                [
                    "## Parent Event",
                    parent_event.to_markdown(include_side_note=True, include_output=False),
                    "",
                ]
            )
        
        instruction_parts.extend(
            [
                "# Constraints and Requirements",
                "",
                "## Temporal Constraints",
                (
                    "All messages in the session MUST have timestamps within the "
                    f"{time_constraint_source} time range:\n"
                    f"- **Start:** {time_start}\n"
                    f"- **End:** {time_end}\n\n"
                    "Message timestamps must be in **strictly chronological order** "
                    "(no equal timestamps allowed)."
                ),
                "",
            ]
        )
        
        if parent_event is not None:
            instruction_parts.extend(
                [
                    "## Parent Event Requirements",
                    (
                        "The session must follow the parent event's requirements. Review the parent "
                        "event's requirements listed above. The session should address and reflect "
                        "these requirements, ensuring that the session advances the goals and constraints "
                        "specified in the parent event. The session's content, tone, and outcomes "
                        "should align with what the parent event requires."
                    ),
                    "",
                ]
            )
        instruction_parts.extend(
            [
                "## Person Profile Influence",
                (
                    "Some aspects of the person profile (personality, gender, age, etc) may be reflected "
                    "in the session. The person's communication style, interests, concerns, and "
                    "goals should influence how they interact with the AI assistant."
                ),
                "",
                "## Person Profile Structure",
                (
                    "The person profile consists of multiple **dimensions**. Each dimension contains multiple **fields** (attributes). " 
                    "Each field can be one of two types:\n"
                    "- **String type**: A single string value\n"
                    "- **List of strings type**: An ordered list of string values\n\n"
                    "For list-type fields, the index is **0-based**. For example, in a list `['A', 'B', 'C']`:\n"
                    "- Index 0 refers to 'A'\n"
                    "- Index 2 refers to 'C'\n\n"
                    "When linking messages to list attributes or modifying list items, you must use the correct 0-based index."
                ),
                "", 
            ]
        )
        
        instruction_parts.extend(
            [
                "## AI Assistant Behavior Constraints",
                (
                    "The AI assistant in the session is a **conversational-only** assistant. It can:\n"
                    "- Answer questions and provide information\n"
                    "- Offer suggestions and recommendations\n"
                    "- Engage in discussions and brainstorming\n"
                    "- Help with planning and decision-making through dialogue\n\n"
                    "The AI assistant **CANNOT**:\n"
                    "- Write, create, or modify files (no code files, documents, images, etc.)\n"
                    "- Execute code or run programs\n"
                    "- Access external systems, APIs, or databases\n"
                    "- Perform any file system operations (read, write, delete)\n"
                    "- Make purchases, bookings, or transactions on behalf of the user\n\n"
                    "All interactions should be purely conversational. If the user asks for file operations "
                    "or code execution, the assistant should explain that it can only provide guidance "
                    "and suggestions through conversation, not perform the actual operations."
                ),
                "",
            ]
        )
        
        instruction_parts.extend(
            [
                "## Message Linking Constraints",
                (
                    "When linking session messages to person profile attributes:\n"
                    "- **Only user or system messages can be linked** to attributes. Assistant messages CANNOT be linked. "
                    "This is because attributes should only be marked as 'mentioned' when the user has disclosed or reflected "
                    "them (either explicitly or implicitly) through his or her own interactions, not when the assistant references or infers them.\n"
                    "- A single message can be linked to multiple attributes if the user discloses or reflects several profile-related details in one message."
                ),
                "",
            ]
        )
        
        instruction_parts.extend(
            [
                "# Quality Requirements",
                "",
                "## Session Quality",
            ]
        )
        if parent_event is not None:
            instruction_parts.extend(
                [
                    (
                        "The session quality should align with the parent event's expectations:\n"
                        "- **Follow Parent Event Requirements**: The session must address and fulfill "
                        "the requirements specified in the parent event"
                    ),
                ]
            )
        instruction_parts.extend(
            [
                (
                    "- **Naturalness**: Messages should feel like real human-AI interactions"
                ),
                (
                    "- **Memory Testing**: The session may naturally include indirect references, " 
                    "fragmented information, topic shifts, or subtle contextual cues, making it realistic but " 
                    "more challenging for memory modules to extract key details. "
                    "Specifically, we categorize these challenges into three distinct complexity dimensions:\n"
                    "  - **Implicit Inference (vs. Explicit Extraction)**: The memory modules must synthesize user attributes from behavioral patterns " 
                    "  or indirect speech acts, rather than relying solely on explicit declarations.\n"
                    "  - **Dynamic Refinement (vs. Static Intent)**: The session features underspecified user goals that evolve over time, requiring the memory module to update "
                    "  context and avoid premature commitment to initial ambiguous queries.\n"
                    "  - **Long-range Synthesis**: Key information pieces are fragmented and dispersed across topic shifts, demanding robust multi-hop reasoning to link non-adjacent details " 
                    "  under noisy context."
                ), 
            ]
        )
        if parent_event is not None:
            instruction_parts.extend(
                [
                    (
                        "- **Contextual Appropriateness**: Align with the parent event's context and Person profile\n"
                        "- **Purpose**: The session should meaningfully advance the parent event's narrative and goals\n"
                        "- **Coherence**: Messages should form a coherent, natural session flow that fits the event"
                    ),
                ]
            )
        else:
            instruction_parts.extend(
                [
                    (
                        "- **Contextual Appropriateness**: Align with Person profile\n"
                        "- **Purpose**: The session should meaningfully contribute to the overall trajectory\n"
                        "- **Coherence**: Messages should form a coherent, natural session flow"
                    ),
                ]
            )
        instruction_parts.extend(
            [
                (
                    "- **Diversity**: Include diverse interaction types (questions, requests, reflections, problem-solving, etc.)"
                ),
                "", 
            ]
        )
        instruction_parts.extend(
            [
                "## Message Quality",
                (
                    "- **Content**: Natural, contextually appropriate message content"
                ),
                (
                    "- **Role Distribution**: The session should start with a user message and end with an assistant message. "
                    "Follow a pattern of alternating between user and assistant messages (user message, then assistant message, "
                    "then user message, and so on)"
                ),
            ]
        )
        
        if parent_event is not None:
            instruction_parts.extend(
                [
                    (
                        "- **Timestamps**: Realistic timing that reflects natural session pace within the event's time span"
                    ),
                ]
            )
        else:
            instruction_parts.extend(
                [
                    (
                        "- **Timestamps**: Realistic timing that reflects natural session pace"
                    ),
                ]
            )
        
        # Workflow section
        instruction_parts.extend(
            [
                "", 
                "# Workflow and Strategy",
                "",
                "## High-Level Approach",
                (
                    "1. **Follow System Hints**: Pay close attention to the hint messages wrapped in "
                    "`<system-hint></system-hint>`. These hints guide you on when to create the session "
                    "and what steps to take next."
                ),
            ]
        )
        
        if parent_event is not None:
            instruction_parts.extend(
                [
                    (
                        "2. **Understand Context**: Carefully review the **current person profile from the hint** and the parent event to understand "
                        "the context, requirements, and constraints. Pay special attention to the parent event's "
                        "requirements, as the session must address and fulfill them.\n\n"
                        "You should understand the structure of the person profile:\n"
                        "- **What dimensions exist** in the person profile, and the **dimension name** for each dimension.\n"
                        "- For each dimension, **what fields exist**, which ones are **modifiable**, and which ones **have been disclosed or reflected in the user's interactions so far**.\n\n"
                        "How to identify modifiable fields:\n"
                        "- In the person profile markdown, fields that can be modified are explicitly labeled with an "
                        "**Attribute Name** and a **data type** such as:\n"
                        "  - `Attribute Name: <field_name> (string)`\n"
                        "  - `Attribute Name: <field_name> (list of strings)`\n"
                        "- Only these labeled fields are allowed to be modified.\n\n"
                        "Understanding the `Mentioned` status:\n"
                        "- Each modifiable attribute except the `description` field of each dimension displays a `(Mentioned: True/False)` indicator.\n"
                        "- `Mentioned: True` means this attribute has already been linked to one or more messages "
                        "in previous sessions, indicating the user's interactions so far have disclosed or reflected this attribute.\n"
                        "- `Mentioned: False` means this attribute has not yet been linked to any messages. "
                        "It may be a good opportunity to have the user naturally disclose or reflect this attribute (either explicitly or implicitly) "
                        "in the current session if contextually appropriate."
                    ),
                ]
            )
        else:
            instruction_parts.extend(
                [
                    (
                        "2. **Understand Context**: Carefully review the **current person profile from the hint** to understand the person's "
                        "characteristics, interests, and current state.\n\n"
                        "You should understand the structure of the person profile:\n"
                        "- **What dimensions exist** in the person profile, and the **dimension name** for each dimension.\n"
                        "- For each dimension, **what fields exist**, which ones are **modifiable**, and which ones **have been disclosed or reflected in the user's interactions so far**.\n\n"
                        "How to identify modifiable fields:\n"
                        "- In the person profile markdown, fields that can be modified are explicitly labeled with an "
                        "**Attribute Name** and a **data type** such as:\n"
                        "  - `Attribute Name: <field_name> (string)`\n"
                        "  - `Attribute Name: <field_name> (list of strings)`\n"
                        "- Only these labeled fields are allowed to be modified.\n\n"
                        "Understanding the `Mentioned` status:\n"
                        "- Each modifiable attribute except the `description` field of each dimension displays a `(Mentioned: True/False)` indicator.\n"
                        "- `Mentioned: True` means this attribute has already been linked to one or more messages "
                        "in previous sessions, indicating the user's interactions so far have disclosed or reflected this attribute.\n"
                        "- `Mentioned: False` means this attribute has not yet been linked to any messages. "
                        "It may be a good opportunity to have the user naturally disclose or reflect this attribute (either explicitly or implicitly) "
                        "in the current session if contextually appropriate."
                    ),
                ]
            )
        if parent_event is not None:
            instruction_parts.extend(
                [
                    # "3. **Design Session Flow**: Plan a natural session flow that ", 
                    # (
                    #     "addresses the parent event's requirements and reflects the person's characteristics. "
                    #     "Consider what topics, questions, or interactions would be appropriate for this event context. "
                    #     "You may incorporate subtle references, fragmented information, indirect hints, or topic shifts to make "
                    #     "the session realistic while making it more challenging for memory modules to extract explicit details. "
                    #     "**During the planning, you should consider how to structure a session that supports questions requiring multiple messages to answer, " 
                    #     "and carefully examine the three dimensions (Implicit Inference, Dynamic Refinement, Long-range Synthesis) of memory-testing mentioned above.**"
                    # ),
                    (
                        "3. **Design Session Flow**: First decide what memory-testing challenges you will embed "
                        "(Implicit Inference, Dynamic Refinement, Long-range Synthesis), then design a realistic session flow "
                        "that addresses the parent event's requirements and reflects the person's traits."
                    ),
                    (
                        "**(a) Decide the challenges to embed**: Think explicitly about how the session will test each dimension:\n"
                        "- **Implicit Inference**: Ensure some person-relevant information is revealed indirectly through behavior, tone, "
                        "constraints, or preferences (not only explicit statements), requiring inference across turns.\n"
                        "- **Dynamic Refinement**: Start with an underspecified or evolving user goal. Let constraints and preferences surface "
                        "gradually, and ensure later turns refine or redirect earlier intent without making the initial request trivially clear.\n"
                        "- **Long-range Synthesis**: Spread key information across non-adjacent turns with natural topic shifts, so answering "
                        "requires retrieving and combining details from earlier parts of the session."
                    ),
                    (
                        "**(b) Design the session flow around parent-event and person**: Based on the chosen challenges, plan a coherent interaction "
                        "sequence that stays grounded in the parent event context while reflecting the person's characteristics. " 
                        "Ensure the session naturally creates cross-turn dependencies (e.g., earlier constraints, later decisions, "
                        "and follow-up clarifications) so the embedded challenges are integral to the session rather than artificial add-ons."
                    ),
                ]
            )
        else:
            instruction_parts.extend(
                [
                    # "3. **Design Session Flow**: Plan a natural session flow that ",
                    # (
                    #     "reflects the person's characteristics and contributes meaningfully to the overall trajectory. "
                    #     "Consider what topics, questions, or interactions would be appropriate. "
                    #     "You may incorporate subtle references, fragmented information, indirect hints, or topic shifts to make "
                    #     "the session realistic while making it more challenging for memory modules to extract explicit details. "
                    #     "**During the planning, you should consider how to structure a session that supports questions requiring multiple messages to answer, " 
                    #     "and carefully examine the three dimensions (Implicit Inference, Dynamic Refinement, Long-range Synthesis) of memory-testing mentioned above.**"
                    # ),
                    (
                        "3. **Design Session Flow**: First decide what memory-testing challenges you will embed "
                        "(Implicit Inference, Dynamic Refinement, Long-range Synthesis), then design a realistic session flow "
                        "that reflects the person's traits while meaningfully contributing to their life trajectory."
                    ),
                    (
                        "**(a) Decide the challenges to embed**: Think explicitly about how the session will test each dimension:\n"
                        "- **Implicit Inference**: Ensure some person-relevant information is revealed indirectly through behavior, tone, "
                        "constraints, or preferences (not only explicit statements), requiring inference across turns.\n"
                        "- **Dynamic Refinement**: Start with an underspecified or evolving user goal. Let constraints and preferences surface "
                        "gradually, and ensure later turns refine or redirect earlier intent without making the initial request trivially clear.\n"
                        "- **Long-range Synthesis**: Spread key information across non-adjacent turns with natural topic shifts, so answering "
                        "requires retrieving and combining details from earlier parts of the session."
                    ),
                    (
                        "**(b) Design the session flow around the person**: Based on the chosen challenges, plan a coherent interaction sequence that "
                        "reflects the person's characteristics. Ensure the session naturally creates cross-turn "
                        "dependencies (e.g., earlier constraints, later decisions, and follow-up clarifications) so the embedded challenges are integral to the session "
                        "rather than artificial add-ons."
                    ),
                ]
            )
        instruction_parts.extend(
            [
                (
                    "4. **Create Messages**: Generate messages with realistic timestamps, natural content, and "
                    "appropriate role distribution. Ensure messages are in strictly chronological order. "
                    "You don't need to create each message's ID as it can be generated by the system automatically."
                ),
            ]
        )
        if parent_event is not None:
            instruction_parts.extend(
                [
                    (
                        "5. **Check for State Changes**: Review the parent event's requirements. If any requirement "
                        "with `from_source` set to an agent **ID NUMBER** indicates that the person's traits will change after "
                        "experiencing this event, you MUST update the corresponding Person attributes after creating "
                        "the session. In this case, you can cite the corresponding requirement id in the operation log. "
                        "After updating, the hint message will reflect the updated person profile."
                    ),
                ]
            )
        else:
            instruction_parts.extend(
                [
                    (
                        "5. **Update Person Attributes**: If the session reflects changes to the person's profile "
                        "(personality, preferences, education, occupation, etc), update these attributes using the appropriate tools. "
                        "After updating, the hint message will reflect the updated person profile."
                    ),
                ]
            )
        
        instruction_parts.extend(
            [
                "",
                (
                    "6. **Linking Messages to Attributes**: You can establish connections between session messages and "
                    "person profile attributes. These linkages track which messages reflect specific attribute values in the person profile "
                    "(e.g., a message mentioning the user's occupation can be linked to the 'occupation' attribute from the dimension model 'career')." 
                    "enabling downstream analysis to trace how the person's profile is manifested in user's interactions."
                ),
            ]
        )
        
        return "\n".join(instruction_parts)

    def _get_graph_refinement_task_instruction(
        self,
        person: PersonBase,
        expanded_event: Event,
        parent_event: Event | None = None,
        level: int = 0,
    ) -> str:
        """Build instruction template for graph refinement after event expansion.
        
        Args:
            person (`PersonBase`):
                The person profile (global context)
            expanded_event (`Event`):
                The event that was just expanded
            parent_event (`Event | None`, optional):
                The parent event that the current graph belongs to (None for top-level)
            level (`int`, defaults to 0):
                The hierarchy level (0 = root, higher = deeper)
        
        Returns:
            `str`:
                The task instruction for graph refinement.
        """
        # Determine context
        if parent_event is None:
            task_description = (
                "You are reviewing and refining the **top-level temporal event graph** after the expansion of event "
                f"**'{expanded_event.title}'** (id: {expanded_event.id}). This graph organizes the highest-level "
                "life events for this person."
            )
            time_constraint_source = "person's trajectory"
            time_start = person.trajectory_start
            time_end = person.trajectory_end
        else:
            task_description = (
                f"You are reviewing and refining the **temporal sub-event graph** for parent event "
                f"**'{parent_event.title}'** (id: {parent_event.id}) after the expansion of event "
                f"**'{expanded_event.title}'** (id: {expanded_event.id})."
            )
            time_constraint_source = "parent event's"
            time_start = parent_event.started_at
            time_end = parent_event.ended_at
        
        # Get constraints from scheduler
        min_events = self.get_min_events(level)
        max_events = self.get_max_events(level)
        event_constraints = f"at least {min_events} event(s)"
        if max_events is not None:
            event_constraints += f" and at most {max_events} event(s)"
        
        instruction_parts = [
            "# Task",
            "",
            task_description,
            "",
            (
                "Your goal is to analyze the expanded event's output and determine whether the current graph needs "
                "adjustments. Follow the system's guidance through hint messages wrapped in `<system-hint></system-hint>`. "
                "These hints show the current graph structure and guide you on available refinement actions."
            ),
            "",
            "# Context",
            "",
            "## Person Profile",
            person.to_markdown(include_side_note=True),
            "",
        ]
        
        if parent_event is not None:
            instruction_parts.extend(
                [
                    "## Parent Event",
                    parent_event.to_markdown(include_side_note=True, include_output=False),
                    "",
                ]
            )
        
        instruction_parts.extend(
            [
                "## Recently Expanded Event and Its Output",
                expanded_event.to_markdown(include_side_note=True, include_output=True),
                "",
                "# Constraints and Requirements",
                "",
                "## Temporal Constraints",
                (
                    f"When adding new events to the graph, all events MUST fall within the {time_constraint_source} time range:\n"
                    f"- **Start:** {time_start}\n"
                    f"- **End:** {time_end}"
                ),
                "",
                "## Event Count Constraints",
                (
                    f"The graph must maintain {event_constraints}. When adding or deleting events, "
                    "ensure the total number of events in the graph stays within this constraint."
                ),
                "",
                "## Dependency Constraints",
                (
                    "When adding or modifying dependencies (edges) between events:\n"
                    "- Dependencies form a directed acyclic graph (DAG) structure\n"
                    "- Events connected by an edge have strict temporal ordering: the source event must "
                    "complete before the target event begins with no temporal overlap permitted"
                ),
                "",
                "## Grounded Sessions and Compatibility Context",
                "",
                (
                    "Events in the current temporal event graph may have pre-existing external sessions assigned to them. "
                    "You can see two fields in each event display:"
                    "- **Grounded Sessions Count**: The number of external sessions assigned to this event.\n"
                    "- **Compatibility Context**: A description that provides context about the grounded sessions assigned to this event, "
                    "and any constraints to consider when expanding the event."
                ),
                "",
                (
                    "When refining the event graph, any modification to each event should remain semantically compatible with the grounded sessions assigned to it."
                ),
                "",
                "## Event Deletion Constraints",
                (
                    "Events that already have grounded sessions assigned or have been expanded cannot be deleted." 
                    "In particular, an unexpanded event that has grounded sessions assigned can be modified."
                ),
                "",
            ]
        ) 

        if parent_event is not None:
            instruction_parts.extend(
                [
                    "## Semantic Consistency Constraints",
                    (
                        "All modifications (adding, revising, or deleting events/edges) must not conflict with the parent event's content. "
                        "If the current graph already contains events that cover the parent event's main content, "
                        "you can consider adding events that are completely unrelated to the parent event's theme, as long as they do not "
                        "contradict the parent event's content." 
                    ),
                ]
            )

        instruction_parts.extend(
            [
                "## Requirements Management",
                "",
                (
                    "Based on the expansion result, you may need to add requirements to unexpanded events in the current graph. "
                    "Requirements eliminate the need to include complete information from all predecessor nodes when expanding events, serving "
                    "as information summaries that extract essential constraints, goals, and dependencies. "
                    "The description of a requirement should be:\n"
                    "- **Specific**: Clearly state what needs to be achieved or what constraint must be "
                    "respected. Avoid vague or ambiguous language.\n"
                    "- **Measurable**: Include concrete criteria or outcomes that can be verified when "
                    "evaluating whether the requirement has been met.\n"
                    "- **Actionable**: Provide sufficient detail for the generation process to understand "
                    "how to incorporate this requirement into the expanded content.\n"
                    "- **Context-aware**: Reference relevant background information, dependencies, or "
                    "conditions that affect how the requirement should be interpreted.\n\n"
                    "The description should be comprehensive enough to serve as a standalone constraint "
                    "that can be understood and applied without requiring additional context from the "
                    "requirement's source."
                ),
                "",
                "### Adding from Person Profile",
                "",
                (
                    "If the Person profile (personality, education, occupation, gender, preferences, etc) "
                    "constrains or influences an unexpanded event's content, "
                    f"add a requirement to that event with `from_source='{person.id}'` to document this constraint."
                ),
                "",
                "### Adding from Recently Expanded Event",
                "",
                (
                    f"If the expansion of **'{expanded_event.title}'** (id: {expanded_event.id}) revealed constraints, "
                    "outcomes, or dependencies that should affect other unexpanded events, you can add requirements to those events. "
                    "**Critical constraint**: There must be an edge from the expanded event to the target event you're adding "
                    f"requirements to. Set `from_source='{expanded_event.id}'` to indicate this requirement originates from "
                    "the recently expanded event."
                ),
                "",
                "### Adding Agent-Generated Requirements",
                "",
                (
                    "You can add requirements based on your analysis during refinement. Set `from_source` to **your agent ID NUMBER** "
                    "which starts with 'agent'. "
                    "These requirements can be closely related to the expansion result, or they can have weaker associations—added "
                    "primarily to increase the graph's complexity and enrich the person's dynamic evolution process. Common types include:"
                ),
                "",
                (
                    "- **Person State Changes**: If you anticipate that experiencing a future unexpanded event will cause the person's "
                    "traits to change (personality, values, likes, dislikes, habits, long-term goals, occupation, education, "
                    "nationality, location), add a requirement to that future event documenting this expected state change. This helps "
                    "create a rich, dynamic evolution of the person throughout the trajectory."
                ),
                "",
                (
                    "- **New Goals**: Emergent objectives arising from the expansion that should influence future events, or new goals "
                    "you introduce to enrich the narrative and increase complexity."
                ),
                "",
                (
                    "- **Logical Implications**: Derived constraints based on what happened in the expansion, or logical connections "
                    "you identify to strengthen the narrative structure."
                ),
                "",
                (
                    "- **Conflict Resolutions**: Adjustments needed to maintain consistency with the expansion result."
                ),
                "",
                (
                    "- **Narrative Requirements**: Story coherence needs to ensure the graph tells a realistic, complex, and evolving narrative."
                ),
                "",
                "# Event and Dependency Adjustments",
                "",
                (
                    "Beyond requirements, you may need to adjust the graph structure itself. Consider whether modifications "
                    "are needed to maintain coherence, resolve conflicts, or enhance complexity."
                ),
                "",
                "## Modify Unexpanded Events",
                "",
                (
                    "Use `revise_event` to adjust unexpanded events if the expansion suggests changes. You can modify the event's "
                    "title, summary, time range, requirements, or side note. Common reasons include:"
                ),
                "",
                (
                    "- Adjust timing if the expansion reveals different pacing than initially planned"
                ),
                (
                    "- Update summaries to reflect new context revealed by the expansion"
                ),
                (
                    "- Revise requirements that no longer fit the actual narrative"
                ),
                "",
                "## Add New Events",
                "",
                (
                    "Use `add_event` if the expansion reveals missing narrative pieces. Consider adding events when:"
                ),
                "",
                (
                    "- The expansion reveals obligations, goals, or follow-ups that deserve dedicated events"
                ),
                (
                    "- **IMPORTANT**: We encourage you to enrich the trajectory with events unrelated to the parent event's main "
                    "focus but compatible with the overall narrative (e.g., if parent event focuses on career development, "
                    "you can add personal life events like travel, hobbies, or family activities to enrich the trajectory)"
                ),
                (
                    "- New causal relationships emerged that should be captured as separate events"
                ),
                "",
                "## Delete Events",
                "",
                (
                    "Use `delete_event` only if necessary to resolve serious conflicts. Remove events that:"
                ),
                "",
                (
                    "- Create factual contradictions or logical conflicts with the expansion result"
                ),
                (
                    "- Cannot be reconciled with what actually happened in the expansion"
                ),
                "",
                "## Add, Modify, or Delete Edges",
                "",
                (
                    "Use `add_edge`, `revise_edge`, or `delete_edge` to adjust dependencies. Consider edge modifications when:"
                ),
                "",
                (
                    "- The expansion revealed causal relationships that should be captured as dependencies"
                ),
                (
                    "- Certain events must now wait for the expanded event's outcomes"
                ),
                (
                    "- Existing dependencies no longer reflect the actual narrative flow"
                ),
                (
                    "- You want to add requirements from the expanded event to unexpanded events (requires creating an edge first)"
                ),
                "",
                "# Quality Requirements",
                "",
                (
                    "Your refinements should achieve:"
                ),
                "",
                (
                    "- **Coherence**: The graph tells a realistic, logical story that reflects the expansion result"
                ),
                (
                    "- **Consistency**: All events, requirements, and dependencies align with what happened in the expansion"
                ),
                (
                    "- **Complexity**: The graph has rich requirements and dependencies that create sophisticated narrative structures"
                ),
                (
                    "- **Memory-Testing Value**: The graph creates challenging scenarios for memory evaluation through "
                    "cross-references and dependencies"
                ),
                "",
                "# Workflow",
                "",
                "## 1. Understand the Expansion",
                "",
                (
                    "Carefully read the expanded event's output (session messages or sub-event graph). Identify key outcomes, "
                    "state changes, timing patterns, and revealed information." 
                ),
                "",
                "## 2. Review the Current Graph",
                "",
                (
                    "Follow the system's guidance through hint messages wrapped in `<system-hint></system-hint>`. These hints "
                    "show all unexpanded events, existing edges, and current requirements. Identify potential conflicts, gaps, "
                    "or opportunities for enhancement."
                ),
                "",
                "## 3. Plan Your Refinements",
                "",
                (
                    "Think strategically about what changes would improve the graph. Consider:"
                ),
                "",
                (
                    "- Which unexpanded events need requirements added based on the expansion result?"
                ),
                (
                    "- Do any events need timing, summary, or requirement adjustments?"
                ),
                (
                    "- Should new events be added to capture missing narrative pieces or enrich the trajectory?"
                ),
                (
                    "- Do dependencies need to be created, modified, or removed?"
                ),
                (
                    "- How can you enhance the graph's complexity and memory-testing value?"
                ),
                "",
                (
                    "Think step by step. It's fine if your planning is extensive. Only make changes that genuinely improve "
                    "the graph based on the expansion result."
                ),
                "",
                "## 4. Execute Refinements with Iterative Thinking",
                "",
                (
                    "Use the available refinement tools to implement your planned changes. As you make each modification, "
                    "continue thinking about its implications and whether additional adjustments are needed. This is an iterative "
                    "process. Refine the graph step by step, and then think carefully about each change and how it affects the overall "
                    "structure. The system hints will guide you on which tools are available. When you want to end the iteration process, "
                    "call `finish_refinement` to finish the whole refinement process, and `generate_response` to summarize the refinement process."
                ),
            ]
        )
        
        return "\n".join(instruction_parts)

    def _get_session_grounding_task_instruction(
        self,
        person: PersonBase,
        session: Session,
        parent_event: Event | None = None,
        level: int = 0,
    ) -> str:
        """Build instruction template for the session grounding agent.
        
        Args:
            person (`PersonBase`):
                The person profile (global context)
            session (`Session`):
                The external session to be grounded into the temporal event graph.
            parent_event (`Event | None`, optional):
                The parent event that the current graph belongs to (None for top-level).
            level (`int`, defaults to 0):
                The hierarchy level (0 = root, higher = deeper).
                
        Returns:
            `str`:
                The task instruction for session grounding.
        """
        # Determine context
        if parent_event is None:
            task_description = (
                "You are distributing an **external session** from the person profile to " 
                "an event in the **top-level temporal event graph**."
            )
            time_constraint_source = "person's trajectory"
            time_start = person.trajectory_start
            time_end = person.trajectory_end
        else:
            task_description = (
                f"You are distributing an **external session** from the parent event " 
                "to an event in the **temporal event graph** "
            )
            time_constraint_source = "parent event's"
            time_start = parent_event.started_at
            time_end = parent_event.ended_at
        
        # Get constraints from scheduler
        min_events = self.get_min_events(level)
        max_events = self.get_max_events(level)
        event_constraints = f"at least {min_events} event(s)"
        if max_events is not None:
            event_constraints += f" and at most {max_events} event(s)"
        
        instruction_parts = [
            "# Task",
            "",
            task_description,
            "",
            (
                "Your goal is to assign the external session to an appropriate event in the current graph. "
                "The session's time interval must be fully contained within the target event's time boundaries. "
                "Follow the system's guidance through hint messages wrapped in `<system-hint></system-hint>`. "
                "These hints show the current graph structure, compatible events, and guide you on available actions."
            ),
            "",
            "# Context",
            "",
            "## Person Profile",
            person.to_markdown(include_side_note=True),
            "",
        ]
        
        if parent_event is not None:
            instruction_parts.extend(
                [
                    "## Parent Event",
                    parent_event.to_markdown(include_side_note=True, include_output=False),
                    "",
                ]
            )
        instruction_parts.extend(
            [
                "## External Session to Ground",
                session.to_markdown(include_side_note=True),
                "",
            ]
        )
        
        instruction_parts.extend(
            [
                "# Constraints and Requirements",
                "",
                "## Session Grounding Constraint",
                (
                    "The external session must be assigned to an event whose time range fully contains "
                    f"the session's time interval ({session.started_at} to {session.ended_at})."
                ),
                "",
                "## Temporal Constraints",
                (
                    f"When adding new events to the graph, all events MUST fall within the {time_constraint_source} time range:\n"
                    f"- **Start:** {time_start}\n"
                    f"- **End:** {time_end}"
                ),
                "",
                "## Event Count Constraints",
                (
                    f"The graph must maintain {event_constraints}. When adding or deleting events, "
                    "ensure the total number of events in the graph stays within this constraint."
                ),
                "",
                "## Dependency Constraints",
                (
                    "When adding or modifying dependencies (edges) between events:\n"
                    "- Dependencies form a directed acyclic graph (DAG) structure\n"
                    "- Events connected by an edge have strict temporal ordering: the source event must "
                    "complete before the target event begins with no temporal overlap permitted"
                ),
                "", 
                "## Event Deletion Constraints",
                (
                    "Events that already have grounded sessions assigned cannot be deleted, " 
                    "though they can be modified."
                ),
                "",
                "## Semantic Consistency Constraints",
                (
                    "When modifying the graph (adding, revising, or deleting events/edges), all changes must not "
                    "conflict with the person profile. Avoid creating events that contradict the person's "
                    "characteristics, background, or circumstances as described in the profile."
                ),
            ]
        )
        
        if parent_event is not None:
            instruction_parts.extend(
                [
                    (
                        "Additionally, all modifications (adding, revising, or deleting events/edges) must not conflict with the parent event's content. "
                        "If the current graph already contains events that cover the parent event's main content, "
                        "you can consider adding events that are completely unrelated to the parent event's theme, as long as they do not "
                        "contradict the parent event's content."
                    ),
                ]
            )
        
        instruction_parts.extend(
            [
                "",
                "## Requirements Management",
                "",
                (
                    "When modifying the temporal event graph, you may need to add requirements to events in the current graph. "
                    "Requirements eliminate the need to include complete information from all predecessor nodes when expanding events, serving "
                    "as information summaries that extract essential constraints, goals, and dependencies. "
                    "The description of a requirement should be:\n"
                    "- **Specific**: Clearly state what needs to be achieved or what constraint must be "
                    "respected. Avoid vague or ambiguous language.\n"
                    "- **Measurable**: Include concrete criteria or outcomes that can be verified when "
                    "evaluating whether the requirement has been met.\n"
                    "- **Actionable**: Provide sufficient detail for the generation process to understand "
                    "how to incorporate this requirement into the expanded content.\n"
                    "- **Context-aware**: Reference relevant background information, dependencies, or "
                    "conditions that affect how the requirement should be interpreted.\n\n"
                    "The description should be comprehensive enough to serve as a standalone constraint "
                    "that can be understood and applied without requiring additional context from the "
                    "requirement's source."
                ),
                "",
                "### Adding from Person Profile",
                "",
                (
                    "If the person profile (personality, education, occupation, gender, preferences, etc) "
                    "constrains or influences the event's content, "
                    f"add a requirement to that event with `from_source='{person.id}'` to document this constraint."
                ),
                "",
            ]
        )

        if parent_event is not None:
            instruction_parts.extend(
                [
                    "### Adding from Parent Requirements",
                    (
                        "Review every requirement already attached to the parent event. If a requirement should also "
                        "constrain a child event, copy that requirement into the child event's requirement list exactly "
                        "as-is. The `from_source` may reference higher-level ancestor events, the Person profile, "
                        "predecessor sibling events, or an upstream agent ID NUMBER. Copying requirements "
                        "in this way preserves how upstream constraints propagate through the hierarchy. "
                        "Be sure to note that `from_source` takes the value of the original requirement's `from_source` field, " 
                        "not the ID of the original requirement."
                    ),
                    "",
                ]
            )

        instruction_parts.extend(
            [
                "# Workflow",
                "",
                "## 1. Analyze the Session",
                (
                    "Carefully review the external session's content, time range, and purpose. Understand what the "
                    "session is about and when it occurs."
                ),
                "",
                "## 2. Review Compatible Events",
                (
                    "Check the hint message for a list of compatible events whose time ranges fully contain the "
                    "session's time interval. Evaluate whether any of these events are semantically appropriate "
                    "for the session."
                ),
                "",
                "## 3. Choose Action",
                (
                    "- If a compatible event has no semantic conflict with the session (being completely unrelated also counts as no conflict), "
                    "assign the session to it.\n"
                    "- If no compatible event exists or compatible events exist but are semantically inappropriate, "
                    "modify the graph topology or contents of event nodes in the graph by calling 'add_event', 'revise_event', or 'delete_event', "
                    "'add_edge', 'revise_edge', or 'delete_edge'."
                ),
                "",
                "## 4. Update Target Event's Compatibility Context",
                (
                    "After assigning the session to a target event, add new context to the target event's compatibility context. " 
                    "The purpose of this compatibility context is to inform subsequent expansion "
                    "processes about the grounded session, ensuring that when the event is later expanded into a sub-event graph, " 
                    "the generated content will be semantically compatible with the already-grounded external session. The new context can be used to describe:\n"
                    "- The main content of the grounded session (when, where, what, why, who)\n"
                    "- Any constraints or considerations for future expansion to avoid conflicts"
                ),
                "",
                "## 5. Finish Grounding",
                (
                    "Once the session is assigned and the target event's context is updated, call 'finish_session_grounding' to complete "
                    "the grounding process, then call 'generate_response' to summarize the session grounding process."
                ),
            ]
        )
        
        return "\n".join(instruction_parts)

    def get_task_instruction(
        self, 
        person: PersonBase, 
        parent_event: Event | None = None,
        level: int = 0,
        instruction_type: Literal[
            "temporal_event_graph", 
            "session",
            "graph_refinement",
            "session_grounding",
        ] = "temporal_event_graph",
        expanded_event: Event | None = None,
        session: Session | None = None,
    ) -> str:
        """Get the task instruction for the given person, parent event, and level.
        
        Args:
            person (`PersonBase`):
                The person profile (global context)
            parent_event (`Event | None`, optional):
                The parent event to expand (None for top-level graph)
            level (`int`, optional):
                Hierarchy level (0 = root, higher = deeper)
            instruction_type (`Literal["temporal_event_graph", "session", "graph_refinement", "session_grounding"]`, defaults to "temporal_event_graph"):
                The type of instruction to return.
            expanded_event (`Event | None`, optional):
                The event that was just expanded (required for graph_refinement)
            session (`Session | None`, optional):
                The external session to be grounded (required for session_grounding)
                
        Returns:
            `str`:
                The task instruction for the given person, parent event, level, and expanded event.
        """
        if instruction_type not in ["temporal_event_graph", "session", "graph_refinement", "session_grounding"]:
            raise ValueError(
                f"The instruction type '{instruction_type}' is invalid. "
                "It must be one of 'temporal_event_graph', 'session', 'graph_refinement', or 'session_grounding'."
            )
        if instruction_type == "temporal_event_graph":
            return self._get_temporal_event_graph_task_instruction(
                person, 
                parent_event=parent_event, 
                level=level,
            )
        elif instruction_type == "session":
            return self._get_session_task_instruction(
                person, 
                parent_event=parent_event,
            )
        elif instruction_type == "session_grounding":
            if session is None:
                raise ValueError(
                    "The `session` parameter is required for 'session_grounding' instruction type."
                )
            return self._get_session_grounding_task_instruction(
                person,
                session,
                parent_event=parent_event,
                level=level,
            )
        
        if expanded_event is None:
            raise ValueError(
                "The `expanded_event` parameter is required for 'graph_refinement' instruction type."
            )
        return self._get_graph_refinement_task_instruction(
            person,
            expanded_event,
            parent_event=parent_event,
            level=level,
        )


