# -*- coding: utf-8 -*-
"""Base class for question-answer pairs synthesis notebook state schedulers."""
from datetime import datetime
from ..models import (
    Event, 
    PersonBase, 
    Session,
    QuestionAnswerPair,
    Message,
) 
from ..models.persona import PersonDimensionBase
from agentscope.module import StateModule


class QANotebookStateSchedulerBase(StateModule):
    """Base class for question-answer pairs synthesis notebook state schedulers.
    
    This class provides the base functionality for managing question-answer pairs synthesis
    parameters at different hierarchy levels and for different target types.
    """
    
    def get_qa_count_range(
        self,
        target: Event | PersonDimensionBase | PersonBase,
        level: int = 0,
    ) -> tuple[int, int]:
        """Get the target question-answer pairs count range for a given target and level.
        
        Args:
            target (`Event | PersonDimensionBase | PersonBase`):
                The target object for question-answer pairs synthesis.
            level (`int`, defaults to `0`):
                The hierarchy level (0 = root level, higher = deeper).
        
        Returns:
            `tuple[int, int]`:
                The target range of question-answer pairs to synthesize for the given target and level.
        """
        raise NotImplementedError(
            f"The get_qa_count_range function is not implemented in {self.__class__.__name__}"
        )
    
    def get_max_attempts(
        self,
        target: Event | PersonDimensionBase | PersonBase,
        level: int = 0,
    ) -> int:
        """Get the maximum number of attempts allowed for question-answer pairs synthesis.
        
        Args:
            target (`Event | PersonDimensionBase | PersonBase`):
                The target object for question-answer pairs synthesis.
            level (`int`, defaults to `0`):
                The hierarchy level (0 = root level, higher = deeper).
        
        Returns:
            `int`:
                The maximum number of attempts allowed.
        """
        raise NotImplementedError(
            f"The get_max_attempts function is not implemented in {self.__class__.__name__}"
        )
    
    def get_propagation_params(
        self,
        level: int = 0,
    ) -> int:
        """Get parameters for question-answer pairs propagation to upper levels (i.e., lower hierarchy levels).
        
        Args:
            level (`int`, defaults to `0`):
                The hierarchy level (0 = root level, higher = deeper).
        
        Returns:
            `int`:
                The number of unconsumed and unexpired question-answer pairs selected randomly for propagation.
        """
        raise NotImplementedError(
            f"The get_propagation_params function is not implemented in {self.__class__.__name__}"
        )

    def filter_qa_pairs_by_consumption(
        self,
        qa_pairs: list[QuestionAnswerPair],
    ) -> tuple[list[QuestionAnswerPair], list[QuestionAnswerPair]]:
        """Separate question-answer pairs into consumed and unconsumed groups.
        
        Consumed question-answer pairs are those that have been used as sub-questions
        in higher-level composite questions.
        
        Args:
            qa_pairs (`list[QuestionAnswerPair]`):
                The list of question-answer pairs to filter.
        
        Returns:
            `tuple[list[QuestionAnswerPair], list[QuestionAnswerPair]]`:
                A tuple containing the unconsumed question-answer pairs and consumed question-answer pairs.
        """
        unconsumed = []
        consumed = []
        for qa_pair in qa_pairs:
            if qa_pair.is_consumed:
                consumed.append(qa_pair)
            else:
                unconsumed.append(qa_pair)
        return unconsumed, consumed

    def filter_qa_pairs_by_expiry(
        self,
        qa_pairs: list[QuestionAnswerPair],
        reference_timestamp: str | None = None,
    ) -> tuple[list[QuestionAnswerPair], list[QuestionAnswerPair]]:
        """Separate question-answer pairs into valid and expired groups.
        
        Args:
            qa_pairs (`list[QuestionAnswerPair]`):
                The list of question-answer pairs to filter.
            reference_timestamp (`str | None`, optional):
                The reference timestamp in ISO 8601 format for expiry check. 
                If None, uses current time.
        
        Returns:
            `tuple[list[QuestionAnswerPair], list[QuestionAnswerPair]]`:
                A tuple containing the valid question-answer pairs and expired question-answer pairs.
        """
        if reference_timestamp is None:
            ref_dt = datetime.now()
        else:
            ref_dt = datetime.fromisoformat(reference_timestamp)
        
        valid = []
        expired = []
        for qa_pair in qa_pairs:
            if qa_pair.expiry_timestamp is None:
                valid.append(qa_pair)
            else:
                expiry_dt = datetime.fromisoformat(qa_pair.expiry_timestamp)
                if expiry_dt > ref_dt:
                    valid.append(qa_pair)
                else:
                    expired.append(qa_pair)
        return valid, expired

    def get_propagation_candidates(
        self,
        qa_pairs: list[QuestionAnswerPair],
        reference_timestamp: str | None = None,
    ) -> list[QuestionAnswerPair]:
        """Get question-answer pairs that are candidates for propagation to upper levels.
        
        Candidates refer to question-answer pairs that have neither been 
        utilized as sub-questions in higher-level composite questions nor have expired.
        
        Args:
            qa_pairs (`list[QuestionAnswerPair]`):
                The list of question-answer pairs to filter.
            reference_timestamp (`str | None`, optional):
                The reference timestamp in ISO 8601 format for expiry check. 
                If None, uses current time.
        
        Returns:
            `list[QuestionAnswerPair]`:
                The list of question-answer pairs that can be propagated.
        """
        unconsumed, _ = self.filter_qa_pairs_by_consumption(qa_pairs)
        candidates, _ = self.filter_qa_pairs_by_expiry(
            unconsumed, 
            reference_timestamp=reference_timestamp,
        )
        return candidates

    def get_expiry_timestamp_estimate_prompt(
        self,
        qa_pair: QuestionAnswerPair,
        future_messages: list[Message],
    ) -> str:
        """Build an instruction for estimating the expiry timestamp for a question-answer pair 
        based on provided future messages.
        
        Args:
            qa_pair (`QuestionAnswerPair`):
                The question-answer pair to estimate the expiry timestamp for.
            future_messages (`list[Message]`):
                The future messages used to estimate the expiry timestamp.

        Returns:
            `str`:
                The prompt for estimating the expiry timestamp.
        """
        # Get the effective timestamp of the question-answer pair
        effective_ts = qa_pair.effective_timestamp
        if effective_ts is None:
            raise ValueError(
                "The effective timestamp of the question-answer pair is not available. "
                "Please ensure the question-answer pair has source evidences."
            )

        effective_dt = datetime.fromisoformat(effective_ts)
        for i, future_message in enumerate(future_messages):
            future_dt = datetime.fromisoformat(future_message.timestamp)
            if future_dt <= effective_dt:
                raise ValueError(
                    f"The {i}-th future message with timestamp '{future_message.timestamp}' is before the "
                    "effective timestamp of the question-answer pair. "
                    "Please ensure the future messages are after the effective timestamp."
                )
        future_messages = sorted(future_messages, key=lambda m: datetime.fromisoformat(m.timestamp))
        
        future_messages_str = "\n".join(
            [
                future_message.to_markdown(include_side_note=True, level=0)
                for future_message in future_messages
            ]
        )

        # Build the instruction
        instruction_parts = [
            "# Task",
            (
                "You are analyzing a question-answer pair based on the future messages to " 
                "estimate when its answer becomes incorrect or its source evidence becomes obsolete. "
                "We refer to this point in time as the expiry timestamp of this question-answer pair."
            ),
            "",
            "# Context",
            "",
            "## Future Messages",
            future_messages_str,
            "",
            "## Question-Answer Pair to Analyze", 
            qa_pair.to_markdown(
                include_evidences=True, 
                include_side_note=True, 
                level=0, 
            ),
            "",  
            (
                f"The question-answer pair's effective timestamp is {effective_ts} "
                "(i.e., the latest timestamp from the source evidences plus 1 second)."
            ), 
            "", 
            "# Constraints",
            "## Expiry Timestamp Format",
            (
                "The expiry timestamp can be `None`. `None` indicates no expiration date, " 
                "meaning no future messages render this question-answer pair invalid. "
                "Otherwise, the expiry timestamp must follow the ISO 8601 format (YYYY-MM-DD HH:MM:SS)."
            ), 
            "",
            "## Temporal Logic", 
            (
                "For any question-answer pair, if the expiry timestamp is not `None`, " 
                "it must be greater than or equal to the effective timestamp."
            ), 
            "",
            "# Expiry Scenarios",
            "",
            (
                "A question-answer pair expires in two scenarios. We take the following example to illustrate the two scenarios:\n"
                "```Example\n"
                "Question: Does the user have a car? What brand?\n"
                "Answer: Yes, a BMW.\n"
                "Source Evidence: User says 'I have a BMW.' on 2024-07-01 12:00:00.\n"
                "```"
            ), 
            "",
            "## Information Update", 
            (
                "**Information Update** means a future message contradicts or updates the current answer of given question-answer pair.\n"
                "For example, the user says 'I sold my car.' on 2025-03-12 09:31:12, which contradicts the current answer 'Yes, a BMW.'. "
                "In this case, the answer is no longer valid. "
                "Therefore, the expiry timestamp should be set to `'2025-03-12 09:31:12'`."
            ), 
            "",
            "## Evidence Supersession",
            (
                "**Evidence Supersession** means a future message re-confirms the same information, " 
                "providing a more recent point of reference. This occurs in two way.\n" 
                "One way is **Direct Re-confirmation**, which means the the original source evidence provider (e.g., the user in this example) " 
                "mentions the information again, providing a more recent first-hand confirmation.\n" 
                "For example, the user says 'My BMW is in the shop.' on 2024-08-14 17:25:36, which re-confirms the information 'I have a BMW.'. "
                "In this case, the answer is still valid, but the source is outdated. "
                "Therefore, the expiry timestamp should be set to `'2024-08-14 17:25:36'`.\n"
                "The other way is **Indirect Re-confirmation**, which means other participants mention the information again.\n"
                "For example, the assistant says 'You can drive your BMW.' on 2024-09-08 22:43:11. "
                "Therefore, the expiry timestamp should be set to `'2024-09-08 22:43:11'`."
            ),
            "", 
            "# Workflow", 
            "",
            "## 1. Understand the Question-Answer Pair",
            "",
            (
                "Begin by thoroughly analyzing the question-answer pair you need to evaluate:\n\n"
                "- **Review the Question**: Understand what information is being queried.\n"
                "- **Review the Answer**: Understand the current answer and what claims it makes.\n"
                "- **Review Source Evidences**: Carefully read each source evidence message. These are the "
                "messages that support the current answer. Note the timestamps and the specific information "
                "each evidence provides.\n"
                "- **Identify Key Information**: Extract the core facts, claims, or states that the answer relies on. "
                "These are the pieces of information that could potentially become outdated or contradicted."
            ),
            "",
            "## 2. Process Future Messages Chronologically",
            "",
            (
                "Examine each future message in chronological order. For each message, ask yourself:"
            ),
            "",
            (
                "- **Does this message contradict the answer?** If the message provides information that directly "
                "contradicts or invalidates the current answer, this is an **Information Update** scenario. "
                "The expiry timestamp should be set to this message's timestamp.\n\n"
                "- **Does this message re-confirm the same information?** If the message mentions the same information "
                "again, providing a more recent reference point, this is an **Evidence Supersession** scenario:\n"
                "  - **Direct Re-confirmation**: The original evidence provider (e.g., the user) mentions the information "
                "  again. The expiry timestamp should be set to this message's timestamp.\n"
                "  - **Indirect Re-confirmation**: Another participant (e.g., the assistant) mentions the information. "
                "  The expiry timestamp should be set to this message's timestamp.\n\n"
                "- **Is this message irrelevant?** If the message does not relate to the question-answer pair's content, "
                "continue to the next message."
            ),
            "",
            "## 3. Determine the Expiry Timestamp",
            "",
            (
                "Based on your analysis of the future messages, determine the appropriate expiry timestamp:"
            ),
            "",
            (
                "- **If Information Update occurred**: Set the expiry timestamp to the timestamp of the first message "
                "that contradicts or invalidates the answer. This message marks when the answer becomes incorrect.\n\n"
                "- **If Evidence Supersession occurred**: Set the expiry timestamp to the timestamp of the first message "
                "that re-confirms the information (either directly or indirectly). This message provides a more recent "
                "source evidence, making the original evidence obsolete.\n\n"
                "- **If both scenarios occurred**: Use the timestamp of whichever event happened **first** in chronological order.\n\n"
                "- **If neither scenario occurred**: Return `None` to indicate that the question-answer pair does not expire "
                "based on the provided future messages. The answer remains valid and the evidence remains current."
            ),
            "",
            "## 4. Validate Your Decision",
            "",
            (
                "Before finalizing your answer, verify that:"
            ),
            "",
            (
                "- **Temporal Logic is Satisfied**: If you determined an expiry timestamp (not `None`), ensure it is "
                "greater than or equal to the effective timestamp of the question-answer pair.\n"
                "- **Format is Correct**: The expiry timestamp follows ISO 8601 format (YYYY-MM-DD HH:MM:SS), or is `None`.\n"
                "- **Reasoning is Sound**: Your decision is based on clear evidence from the future messages and aligns "
                "with the expiry scenarios defined above."
            ),
        ]
        
        return "\n".join(instruction_parts)

    def get_qa_synthesis_task_instruction(
        self,
        target: Event | PersonDimensionBase | PersonBase,
        level: int = 0,
        sub_questions: dict[str, list[QuestionAnswerPair]] | None = None,
        message_map: dict[str, Message] | None = None,
    ) -> str:
        """Build an instruction for question-answer pairs synthesis.

        Args:
            target (`Event | PersonDimensionBase | PersonBase`):
                The target object to synthesize question-answer pairs for.
            level (`int`, optional):
                The hierarchy level (0 = root level, higher = deeper).
            sub_questions (`dict[str, list[QuestionAnswerPair]] | None`, optional):
                Sub-questions for composition targets.
            message_map (`dict[str, Message] | None`, optional):
                Message map for dimension targets to display linked messages.

        Returns:
            `str`:
                The instruction for question-answer pairs synthesis.
        """
        sub_questions_overview = None
         
        if isinstance(target, PersonDimensionBase):
            target_type_desc = "a dimension of the person profile"
            title = "Dimension of Person Profile"
            target_info = target.to_markdown(detailed=True, level=0)
            if message_map is None:
                raise ValueError(
                    "Message map is required for the target dimension of person profile. "
                    "Please provide the message map."
                )

            field_history_str = [] 
            for str_field in target.get_string_fields():
                tracked_attr = getattr(target, str_field)
                field_history_str.append(f"### String Field `{str_field}`")
                for i, attr_version in enumerate(tracked_attr.history):
                    field_history_str.append(f"#### Version {i + 1}")
                    field_history_str.append(f"- Value: {attr_version['value']}")
                    if attr_version["connections"]:
                        field_history_str.append(f"- Related Messages")
                        for connection in sorted(
                            attr_version["connections"], 
                            key=lambda x: datetime.fromisoformat(message_map[x].timestamp)
                        ): 
                            msg = message_map[connection]
                            field_history_str.append(msg.to_markdown(include_side_note=True, level=1))
                    else:
                        field_history_str.append(f"- Related Messages: [NO_RELATED_MESSAGES]")

            for list_field in target.get_list_fields():
                tracked_attrs = getattr(target, list_field)
                field_history_str.append(f"### List Field `{list_field}`")
                for i, tracked_attr in enumerate(tracked_attrs):
                    field_history_str.append(f"#### The {i + 1}-th Item")
                    for j, attr_version in enumerate(tracked_attr.history):
                        field_history_str.append(f"##### Version {j + 1}")
                        field_history_str.append(f"- Value: {attr_version['value']}")
                        if attr_version["connections"]:
                            field_history_str.append(f"- Related Messages")
                            # Filter invalid messages. 
                            connections = [ 
                                connection 
                                for connection in attr_version["connections"]
                                if connection in message_map 
                            ] 
                            for connection in sorted(
                                connections,
                                key=lambda x: datetime.fromisoformat(message_map[x].timestamp)
                            ): 
                                msg = message_map[connection]
                                field_history_str.append(msg.to_markdown(include_side_note=True, level=1))
                        else:
                            field_history_str.append(f"- Related Messages: [NO_RELATED_MESSAGES]")

            field_history_str.append(f"### Removed Items")
            if target.removed_attributes:
                for i, removed_attr in enumerate(target.removed_attributes):
                    field_history_str.append(f"#### The {i + 1}-th Removed Item")
                    for j, attr_version in enumerate(removed_attr.history):
                        field_history_str.append(f"##### Version {j + 1}")
                        field_history_str.append(f"- Value: {attr_version['value']}")
                        if attr_version["connections"]:
                            field_history_str.append(f"- Related Messages")
                            for connection in sorted(
                                attr_version["connections"],
                                key=lambda x: datetime.fromisoformat(message_map[x].timestamp)
                            ): 
                                msg = message_map[connection]
                                field_history_str.append(msg.to_markdown(include_side_note=True, level=1))
                        else:
                            field_history_str.append(f"- Related Messages: [NO_RELATED_MESSAGES]")
            else:
                field_history_str.append(f"[NO_REMOVED_ITEMS]")
            
            target_info = "\n".join(
                [
                    target_info, 
                    "",
                    (
                        "Below is a structured history of this **dimension model's attributes**. It is derived from tracked attribute histories.\n\n"
                        "- The history is grouped by **field name** using markdown headers like `### List Field <field_name>` or `### String Field <field_name>`.\n"
                        "- For **string fields**, each field contains multiple versions like `#### Version k`, where each version lists:\n"
                        "  - `Value`: the attribute value at that version\n"
                        "  - `Related Messages`: the evidence messages connected to that version\n"
                        "- For **list fields**, the history is grouped by list field name (`### List Field <list_field>`), " 
                        "then by list item (`#### The i-th Item`), and each item has versions (`##### Version k`) with values and related messages.\n"
                        "- The `### Removed Items` section records list items that were deleted. Each removed item also has version histories and related messages.\n\n"
                        "You should treat these messages as the primary evidence for constructing question-answer pairs about this dimension."
                    ), 
                    "", 
                    *field_history_str,
                ]
            )

        elif isinstance(target, Event):
            # Event can be expanded into either Session or TemporalEventGraph.
            if isinstance(target.output, Session):
                target_type_desc = "an event whose output is a session"
            else:
                target_type_desc = "an event whose output is a temporal event graph"
                if sub_questions is None:
                    raise ValueError(
                        "Sub-questions are required for the target event with a temporal event graph output. "
                        "Please provide sub-questions."
                    )
                subevents = set(subevent.id for subevent in target.output.events)
                for event_id in sub_questions.keys():
                    if event_id not in subevents:
                        raise ValueError(
                            f"Event '{event_id}' is not found in the temporal event graph output. "
                            f"Valid events are {', '.join(sorted(subevents))}."
                        )
                sub_questions_overview = (
                    f"This event has {len(subevents)} child event(s), among which {len(sub_questions.keys())} event(s) "
                    "have previously synthesized question-answer pairs. "
                    "These question-answer pairs are available as child question-answer pairs for you to synthesize more complex questions."
                ) 
            title = "Event" 
            target_info = target.to_markdown(
                include_side_note=True,
                include_output=True,
                level=0
            )

        elif isinstance(target, PersonBase):
            target_type_desc = "a global person profile"
            title = "Person Profile"
            target_info = target.to_markdown(include_side_note=True, detailed=True, level=0)
            if sub_questions is None:
                raise ValueError(
                    "Sub-questions are required for the target person profile. "
                    "Please provide sub-questions."
                )
            dimensions = set(target.get_dimension_names()) 
            for dimension_name in sub_questions.keys():
                if dimension_name not in dimensions:
                    raise ValueError(
                        f"Dimension '{dimension_name}' is not found in the person profile. "
                        f"Valid dimensions are {', '.join(sorted(dimensions))}."
                    )
            sub_questions_overview = (
                f"This person profile has {len(dimensions)} dimension(s), among which {len(sub_questions.keys())} dimension(s) " 
                "have previously synthesized question-answer pairs. "
                "These question-answer pairs are available as child question-answer pairs for you to synthesize more complex questions."
            )

        else:
            raise ValueError(f"The target type '{type(target)}' is not supported.")

        min_count, max_count = self.get_qa_count_range(target, level=level)
        max_attempts = self.get_max_attempts(target, level=level)

        # Optional sub-questions section
        if sub_questions is not None:
            prefix = "Dimension" if isinstance(target, PersonDimensionBase) else "Sub-Event"
            sub_questions_section = [
                "## Available Child Question-Answer Pairs",
                "",
                sub_questions_overview,
                "", 
            ]
            for name in sorted(sub_questions.keys()):
                sub_questions_section.extend(
                    [
                        f"### Child Question-Answer Pairs from {prefix} {name}",
                        "",
                        *[
                            sub_qa.to_markdown(
                                include_evidences=False, 
                                include_side_note=True, 
                                level=0, 
                            )
                            for sub_qa in sub_questions[name]
                        ],
                    ]
                )
            sub_questions_section = "\n".join(sub_questions_section)
        else:
            sub_questions_section = None
        
        goal_desc = f"You are synthesizing question-answer pairs for **{target_type_desc}**. " 
        if sub_questions is not None:
            goal_desc += (
                "Your goal is to generate high-quality and diverse question-answer pairs "
                "by composing available child question-answer pairs."
            )
        elif isinstance(target, Event):
            goal_desc += (
                "Your goal is to generate high-quality and diverse question-answer pairs "
                "based on the messages in the current session."
            )
        else: 
            goal_desc += (
                "Your goal is to generate high-quality and diverse question-answer pairs "
                "based on the operations performed on this person profile dimension "
                "and messages linked to this dimension's attributes."
            )

        instruction_parts = [
            "# Task",
            "",
            (
                f"You are synthesizing question-answer pairs for **{target_type_desc}**. "
            ),
            "",
            f"{goal_desc}",
            "",
            "# Context",
            "",
            "## Question Type Tool Book", 
            (
                "The question type tool book is a collection of question types that are available for you to reference. "
                "It is dynamic and may be modified during the question-answer pairs synthesis process. "
                "Please refer to the **current question type tool book** in the hint message wrapped by "
                "`<system-hint></system-hint>` for the most up-to-date information."
            ),
            "", 
        ]

        instruction_parts.extend(
            [
                f"## {title}",
                target_info,
                "",
            ]
        )

        if sub_questions_section is not None:
            instruction_parts.append(sub_questions_section)


        instruction_parts.extend(
            [
                "# Constraints",
                "",
                "## Question-Answer Pair Count",
                (
                    f"You must generate **{min_count} to {max_count}** question-answer pair(s) for this target "
                    "(both bounds inclusive)."
                ),
                "",   
                "## Attempt Budget",
                (
                    f"You have at most **{max_attempts}** tries to synthesize multiple high-quality question-answer pairs. "
                    "Note that only attempts which successfully create at least one new question-answer pair are counted towards the attempt budget."
                ),
                "",
            ]
        )

        if isinstance(target, PersonDimensionBase):
            instruction_parts.append("## Source Evidence Constraint")
            instruction_parts.extend(
                [
                    (
                        "Each question-answer pair must be grounded in **source evidence messages** linked to the dimension's attributes. "
                        "Please only use message IDs that appear in the structured attribute history above. "
                        "When you select evidence for a question-answer pair, you should prefer the **minimal** set of messages " 
                        "that fully supports the golden answer to avoid adding unrelated messages."
                    ),
                    "", 
                ]
            )
            instruction_parts.append("## Question Type Constraint")
            instruction_parts.extend(
                [
                    (
                        "When possible, you should prioritize **preference-related** question types to better evaluate memory of the user's preferences. "
                        "Examples include applying the user's preferences to a **new scenario** (preference transfer), "
                        "detecting and reasoning about the **trajectory of preference changes over time** (preference evolution), "
                        "resolving **preference conflicts** under constraints, and **conditional preferences**."
                    ),
                    "",
                ]
            )
        elif isinstance(target, Event) and isinstance(target.output, Session):
            instruction_parts.append("## Source Evidence Constraint") 
            instruction_parts.extend(
                [
                    (
                        "Each question-answer pair must be grounded in **source evidence messages** from the target event's **session output** "
                        "(see the session messages in the target context above). "
                        "For each question-answer pair, provide a list of evidence message IDs that jointly support the golden answer. "
                        "You should prefer a minimal, sufficient evidence set to avoid adding unrelated messages."
                    ),
                    "",
                ]
            )
        elif isinstance(target, PersonBase):
            instruction_parts.append("## Composition Constraint")
            instruction_parts.extend(
                [
                    (
                        "Each question-answer pair must be composed from existing **child question-answer pairs**. "
                        "The child question-answer pairs are grouped by **child event id** in the `## Available Child Question-Answer Pairs` section. "
                        "Each composed question-answer pair should use at least 2 child question-answer pairs, "
                        "and require combining information across them. "
                        "Please avoid paraphrasing a single child question-answer pair."
                    ),
                    "",
                ]
            )
            instruction_parts.append("## Question Type Constraint")
            instruction_parts.extend(
                [
                    (
                        "When possible, you should prioritize **user trait abstraction / profile summary** question types "
                        "to evaluate whether the system can summarize stable aspects of the user from multiple events. "
                        "Examples include summarizing the user's **habits**, **communication style**, **decision-making patterns**, "
                        "**recurring preferences across contexts**, **constraints they often mention**, and **typical trade-offs** they make. "
                        "These questions must still be **provably supported** by combining information from multiple child question-answer pairs. "
                        "Do not speculate beyond what the child question-answer pairs jointly entail."
                    ),
                    "",
                ]
            )
        else:
            instruction_parts.append("## Composition Constraint") 
            instruction_parts.extend(
                [
                    (
                        "Each question-answer pair must be composed from existing **child question-answer pairs**. "
                        "The child question-answer pairs are grouped by **dimension name** in the `## Available Child Question-Answer Pairs` section. "
                        "Each composed question-answer pair should use at least 2 child question-answer pairs, "
                        "and require combining information across them. "
                        "Please avoid paraphrasing a single child question-answer pair."
                    ),
                    "",
                ]
            )
            if level == 1:
                instruction_parts.append("## Question Type Constraint")
                instruction_parts.extend(
                    [
                        (
                            "When possible, you should prioritize **summarization-style** question types to evaluate the AI memory system's ability to "
                            "**collect, consolidate, and summarize a large amount of dispersed information**. "
                            "These questions should require integrating information from **many** child question-answer pairs (not just one) to produce a coherent "
                            "high-level summary (e.g., main phases, key turning points, recurring themes, or how earlier events lead to later outcomes). "
                            "All summarizations must be **provably supported** by the selected child question-answer pairs. Do not speculate beyond what they jointly entail."
                        ),
                        "",
                    ]
                )

        source = "source evidence message" if sub_questions is None else "child question-answer pair"
        instruction_parts.extend(
            [
                "# Question-Answer Pair Quality Requirements",
                "",
                "## Question Quality",
                (
                    "- **Self-Contained**: A high-quality question should include sufficient contextual constraints to uniquely identify the target information, " 
                    "but does not need to be fully self-contained in all cases. " 
                    "When applicable, the question should explicitly specify **When, Where, and Who**, " 
                    "rather than using vague references such as \"that trip\" or \"that transition\". " 
                    "However, if the referenced information is inherently unique (e.g., the user's hometown, the user's current preferneces), additional contextual specification is unnecessary. "
                    "When the relevant information is not uniquely identifiable from context, questions must include sufficient disambiguating cues such as time or order. " 
                    "For example, if a user has attended multiple meetings, questions like \"What was discussed in this meeting?\" may become ambiguous. " 
                    "If time is mentioned, it should be specified at **day-level at most**, avoiding overly precise timestamps. "
                    "**Please avoid making questions overly self-contained**, " 
                    "as directly embedding answer-bearing information in the question may leak the answer and substantially reduce the difficulty of the task. "
                    "Additionally, consider the **phrasing** of your question to ensure that the source evidences are **not easily retrievable** via semantic similarity or keyword matching.\n"
                    "- **No Question Type Leakage**: Do **not** reveal or mention the **question type** (e.g., \"This is a single-hop question. Does user have a car?\") "
                    "in the question.\n"
                    "- **Form-Specific Clarity**: If the question is a single-choice or multiple-choice question, you should include 4 options in the question, "
                    f"and avoid trick wording. The incorrect options should be **plausible and highly confusable** but still **provably wrong** based on the provided {source}s.\n"
                    "- **Answerability**: Most questions should be answerable. You can include a small number of unanswerable questions to test the AI memory system's " 
                    "ability to recognize missing information. For answerable questions, the golden answer(s) must be fully "
                    f"derivable from the corresponding {source}s. Please ensure the AI memory system cannot answer these questions based on its own world knowledge. "
                    f"For unanswerable questions, the golden answer must be unique. Each unanswerable question should be provided with a minimal set of {source}s that contain "
                    "relevant context but fall short of answering this question."
                ),
                "", 
                "## Answer Quality",
                (
                    f"- **Clear and Direct**: Answers should be concise natural language statements that do not reference any {source}s.\n"
                    "- **Complete**: If a question asks for multiple facets (e.g., what and when, or action and reason), the answer must cover all facets.\n"
                    "- **Answers of Open-Ended Questions**: Open-ended questions may have multiple reference answers."
                ),
                "", 
                "## Diversity", 
                (
                    f"- **Topic Coverage**: Spread questions across different attributes, topics, events rather than repeatedly targeting the same {source}.\n"
                    "- **Question Diversity**: When generating a batch of question-answer pairs, you should ensure high diversity in difficulty levels, " 
                    "phrasing formats, question forms, and question types."
                ), 
                "", 
            ]
        ) 

        instruction_parts.extend(
            [
                "# Workflow",
                "",
                (
                    "1. **Follow System Hints**: Pay close attention to the hint messages wrapped in "
                    "`<system-hint></system-hint>`. These hints guide you on what question types exist in the tool book, " 
                    "and what you should do next."
                ),
                (
                    f"2. **Understand Context and Constraints**: Carefully review the target context above, especially the {source}s given to you." 
                ),
            ] 
        ) 
        
        if isinstance(target, PersonDimensionBase | PersonBase):
            instruction_parts.extend(
                [
                    (
                        "Note that you should understand the `Mentioned` status:\n"
                        "- `Mentioned: True` means this attribute has already been linked to one or more messages, "
                        "indicating the user's interactions so far have disclosed or reflected this attribute.\n"
                        "- `Mentioned: False` means this attribute has not yet been linked to any messages. "
                    ),
                ]
            )

        instruction_parts.extend(
            [
                (
                    "3. **Consider Adding New Question Types**: Before drafting question-answer pairs, think about whether the current question type tool book "
                    "is sufficient for you to create diverse question-answer pairs for the target context. If you can construct a meaningful and novel question type " 
                    "that makes memory evaluation more comprehensive and effective, you should add it to the tool book. "
                    "**We encourage you to exercise your creativity and propose new question types to further enrich the tool book**." 
                ),
                (
                    "4. **Plan a Diverse Batch of Question-Answer Pairs**: Decide a concrete coverage plan to maximize diversity of question-answer pairs."
                ),
                (
                    "5. **Generate Question-Answer Pairs**: Create diverse question-answer pairs based on the coverage plan. " 
                    "You don't need to compute each question-answer pair's effective timestamp and expiry timestamp."
                ),
                (
                    "6. **Complete**: Stop when you have generated enough high-quality question-answer pairs "
                    "(within the required range) or when the attempt budget is exhausted."
                ),
            ]
        )

        instruction = "\n".join(instruction_parts) 
        return instruction 
    