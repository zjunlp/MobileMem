# -*- coding: utf-8 -*-
"""Data models for question answering synthesis from trajectories."""
from __future__ import annotations
import shortuuid
from datetime import datetime, timedelta
from pydantic import (
    BaseModel,
    Field,
    PrivateAttr,
    field_validator, 
    computed_field,
    model_validator,
    ModelWrapValidatorHandler, 
)
from ..utils import get_timestamp
from .session import Message
from .graph import Event, Session 
from .persona import PersonDimensionBase, PersonBase
from ._constants import NO_SIDE_NOTE, EMPTY_LIST_STR_REPR
from typing import (
    Literal, 
    Any,
    Self,
) 


NO_EXPIRY_TIMESTAMP = "[NO EXPIRY TIMESTAMP PROVIDED]"


class QuestionAnswerPair(BaseModel):
    """Represent a single question-answer pair for evaluation."""
    
    id: str = Field(
        default_factory=lambda: f"qa_{shortuuid.uuid()}",
        description="Unique identifier for the question-answer pair.",
    )
    question: str = Field(
        description="The question to be answered.",
    )
    question_type: str = Field(
        description="The type of this question.",
    )
    question_form: Literal["single_choice", "multiple_choice", "open_ended"] = Field(
        default="open_ended",
        description=(
            "The form of the question. `'single_choice'` expects 1 of 4 options, "
            "`'multiple_choice'` expects N of 4 options, "
            "and `'open_ended'` has no predefined options. "
            "If the question form is `'single_choice'` or `'multiple_choice'`, the options should be included in the `question` field."
        ),
    )
    golden_answers: list[str] = Field(
        description=(
            "Reference answers. The answers should be direct natural language answers "
            "that do not reference any message IDs and session IDs."
        ),
        min_length=1,
    )
    difficulty: Literal["easy", "medium", "hard"] = Field(
        description="Difficulty level of the question.",
    )
    topic: list[str] = Field(
        default_factory=list,
        description="List of topics involved in this question-answer pair.",
    )
    side_note: str = Field(
        default=NO_SIDE_NOTE,
        description=(
            "Meta-commentary explaining why this question-answer pair exists, what it tests, "
            "and how to solve it."
        ),
    )
    expiry_timestamp: str | None = Field(
        default=None,
        description=(
            "ISO 8601 timestamp (YYYY-MM-DD HH:MM:SS) indicating when this question-answer pair becomes invalid.\n\n"
            "For some questions, where the expiration date cannot currently be derived from the existing user trajectory, " 
            "`expiry_timestamp` can be set to `None`.\n"
            "For other questions, this timestamp marks the expiration. Consider this example:\n"
            "  [Initial State]\n"
            "  - Question: Does the user have a car? What brand?\n"
            "  - Answer: Yes, a BMW.\n"
            "  - Evidence: User says 'I have a BMW.' on 2024-07-01 12:00:00.\n\n"
            "The question-answer pair expires in two scenarios:\n"
            "1. **Information Update (The answer is no longer valid):** User says 'I sell my car.' on 2025-03-12 09:31:12.\n"
            "   Therefore, `expiry_timestamp` should be set to '2025-03-12 09:31:12'.\n"
            "2. **Evidence Obsolete (The answer is still valid, but the source is outdated):**\n"
            "   - User says 'I have a BMW.' again on 2024-08-14 17:25:36. The original evidence can be replaced by this new evidence.\n"
            "   Therefore, `expiry_timestamp` should be set to '2024-08-14 17:25:33'.\n"
            "   - Or user does not mention the BMW again but the assistant says 'You can drive your BMW.' on 2024-09-08 22:43:11. " 
            "The original evidence can also be replaced by this new evidence.\n"
            "   Therefore, `expiry_timestamp` should be set to '2024-09-08 22:43:11'."
        ),
    )
    created_at: str = Field(
        default_factory=get_timestamp,
        description="Timestamp of creation of the question-answer pair object **in real-world system time**.",
    )
    
    # Private fields for source tracking
    _source_evidences: list[Message] = PrivateAttr(default_factory=list)
    _sub_questions: list[QuestionAnswerPair] = PrivateAttr(default_factory=list)
    
    # Flag to indicate if this QA pair has been consumed as a sub-question
    _is_consumed: bool = PrivateAttr(default=False)

    @model_validator(mode="wrap")
    @classmethod
    def _restore_private_attrs(
        cls, 
        values: Any, 
        handler: ModelWrapValidatorHandler[Self]
    ) -> Self:
        """Restore private attributes from serialized data during deserialization.
        
        Args:
            values (`Any`):
                The input values to validate.
            handler (`ModelWrapValidatorHandler[Self]`):
                The handler function to create the instance.
        
        Returns:
            `Self`:
                The validated instance with private attributes restored.
        """
        if not isinstance(values, dict):
            return handler(values)
        
        # Create the instance
        instance = handler(values)
        
        is_consumed = values.get("is_consumed", False)
        if is_consumed:
            instance.mark_consumed()
        source_evidences = values.get("source_evidences", []) 
        for source_evidence in source_evidences:
            instance.add_message(
                Message.model_validate(source_evidence)
            )
        sub_qa_pairs = values.get("sub_questions", [])
        for sub_qa_pair in sub_qa_pairs:
            instance.add_subquestion(
                QuestionAnswerPair.model_validate(sub_qa_pair)
            )
        
        return instance

    @computed_field
    @property
    def num_hops(self) -> int:
        """Total number of messages in evidences.
        
        Returns:
            `int`:
                The total number of messages in the source evidences.
        """
        return len(self._source_evidences)

    @computed_field
    @property
    def num_sub_questions(self) -> int:
        """Count of sub-questions.
        
        Returns:
            `int`:
                The number of sub-questions.
        """
        return len(self._sub_questions)

    @computed_field
    @property
    def effective_timestamp(self) -> str | None:
        """Get the effective timestamp of this question-answer pair.
        
        Returns:
            `str | None`:
                The effective timestamp of this question-answer pair in ISO 8601 format.
        """
        if not self._source_evidences:
            return None
        effective_timestamp = max(
            datetime.fromisoformat(msg.timestamp) for msg in self._source_evidences
        )
        effective_timestamp = effective_timestamp + timedelta(seconds=1)
        return effective_timestamp.strftime("%Y-%m-%d %H:%M:%S")

    @computed_field
    @property
    def source_evidences(self) -> list[Message]:
        """Return a copy of the source evidences.
        
        Returns:
            `list[Message]`:
                A copy of the source evidences.
        """
        return self._source_evidences.copy()

    @computed_field
    @property
    def sub_questions(self) -> list[QuestionAnswerPair]:
        """Return a copy of the sub-questions list.
        
        Returns:
            `list[QuestionAnswerPair]`:
                A copy of the sub-questions list.
        """
        return self._sub_questions.copy()

    @computed_field
    @property
    def is_consumed(self) -> bool:
        """Check if this question-answer pair has been consumed as a sub-question.
        
        Returns:
            `bool`:
                True if this question-answer pair has been consumed as a sub-question, False otherwise.
        """
        return self._is_consumed

    def mark_consumed(self) -> None:
        """Mark this question-answer pair as consumed (used as a sub-question)."""
        self._is_consumed = True

    def add_message(self, message: Message) -> None:
        """Add a message as evidence for this question-answer pair.
        
        Args:
            message (`Message`):
                The message to add as evidence.
        """
        existing_ids = {m.id for m in self._source_evidences}
        if message.id not in existing_ids:
            self._source_evidences.append(message)

    def add_messages(self, messages: list[Message]) -> None:
        """Add multiple messages as evidence for this question-answer pair.
        
        Args:
            messages (`list[Message]`):
                The messages to add as evidence.
        """
        for message in messages:
            self.add_message(message)

    def add_subquestion(self, sub_qa_pair: QuestionAnswerPair) -> None:
        """Add a sub-question and merge its source evidences.
        
        When adding a sub-question, its source evidences are merged into
        this question-answer pair's evidences with deduplication.
        
        Args:
            sub_qa_pair (`QuestionAnswerPair`):
                The sub-question to add.
        """
        self._sub_questions.append(sub_qa_pair)
        sub_qa_pair.mark_consumed()
        
        # Merge source evidences with deduplication
        for message in sub_qa_pair.source_evidences:
            self.add_message(message)

    def to_markdown(
        self, 
        include_evidences: bool = False, 
        include_side_note: bool = False, 
        level: int = 0,
    ) -> str:
        """Convert the question-answer pair to MarkDown format.
        
        Args:
            include_evidences (`bool`, defaults to `False`):
                Whether to include the source evidences in the output.
            include_side_note (`bool`, defaults to `False`):
                Whether to include the side note in the output.
            level (`int`, defaults to `0`):
                The indentation level for the markdown output.
        
        Returns:
            `str`:
                The markdown representation of this question-answer pair.
        """
        indent = "\t" * level

        if len(self.golden_answers) == 1:
            answers_str = self.golden_answers[0]
        else:
            answers_str = ", ".join(self.golden_answers)
        topics_str = ", ".join(self.topic) if self.topic else EMPTY_LIST_STR_REPR 
        
        markdown_strs = [
            f"{indent}- Question-Answer Pair (id: {self.id})",
            f"{indent}\t- Question: {self.question}",
            f"{indent}\t- Question Type: {self.question_type}",
            f"{indent}\t- Question Form: {self.question_form}",
            f"{indent}\t- Difficulty: {self.difficulty}",
            f"{indent}\t- Golden Answers: {answers_str}",
            f"{indent}\t- Topics: {topics_str}",
            f"{indent}\t- Effective Timestamp: {self.effective_timestamp}",
            f"{indent}\t- Expiry Timestamp: {self.expiry_timestamp or NO_EXPIRY_TIMESTAMP}",
            f"{indent}\t- Total Number of Messages: {self.num_hops}",
            f"{indent}\t- Total Number of Sub-Questions: {self.num_sub_questions}",
            f"{indent}\t- Created At In Real-World System Time: {self.created_at}",
        ]
        
        if include_evidences and self._source_evidences:
            markdown_strs.append(f"{indent}\t- Source Evidences:")
            message_instances = sorted(
                self._source_evidences, 
                key=lambda msg: datetime.fromisoformat(msg.timestamp)
            ) 
            for msg in message_instances:
                markdown_strs.append(
                    msg.to_markdown(
                        include_side_note=include_side_note, 
                        level=level + 2,
                    )
                )

        if include_side_note:
            markdown_strs.append(f"{indent}\t- Side Note: {self.side_note}")
        
        return "\n".join(markdown_strs)


class QuestionType(BaseModel):
    """Represent a specific category of questions for question-answer synthesis.
    
    It defines a category of questions that test specific aspects of the memory system 
    (e.g., factual recall, temporal reasoning, preference inference, etc).
    """

    name: str = Field(
        description=(
            "Name of the question type (1-10 words). " 
            "It also serves as a unique identifier for the question type."
        ), 
        min_length=1,
        max_length=160,
    )
    description: str = Field(
        description=(
            "Describe the characteristics of this question type, including "
            "what memory aspect it tests and how questions in this category "
            "should be structured."
        ),
    )
    created_at: str = Field(
        default_factory=get_timestamp,
        description="Timestamp of creation of the question type object **in real-world system time**.",
    )
    _qa_pairs: list[QuestionAnswerPair] = PrivateAttr(default_factory=list)

    @model_validator(mode="wrap")
    @classmethod
    def _restore_private_attrs(
        cls, 
        values: Any, 
        handler: ModelWrapValidatorHandler[Self]
    ) -> Self:
        """Restore private attributes from serialized data during deserialization.
        
        Args:
            values (`Any`):
                The input values to validate.
            handler (`ModelWrapValidatorHandler[Self]`):
                The handler function to create the instance.
        
        Returns:
            `Self`:
                The validated instance with private attributes restored.
        """
        if not isinstance(values, dict):
            return handler(values)
        
        instance = handler(values)

        qa_pairs = values.get("qa_pairs", []) 
        for qa_pair in qa_pairs:
            instance.add_qa_pair(
                QuestionAnswerPair.model_validate(qa_pair)
            )
        
        return instance

    @computed_field
    @property
    def counts(self) -> int:
        """Return the current number of question-answer pairs in this type.
        
        Returns:
            `int`:
                The number of question-answer pairs in this type.
        """
        return len(self._qa_pairs)

    @computed_field
    @property
    def qa_pairs(self) -> list[QuestionAnswerPair]:
        """Return a copy of the question-answer pairs list.
        
        Returns:
            `list[QuestionAnswerPair]`:
                A copy of the question-answer pairs list.
        """
        return self._qa_pairs.copy()

    def add_qa_pair(self, qa_pair: QuestionAnswerPair) -> None:
        """Add a question-answer pair to this question type.
        
        Args:
            qa_pair (`QuestionAnswerPair`):
                The question-answer pair to add.
        """
        if qa_pair.question_type != self.name:
            raise ValueError(
                f"It is not allowed to add a question-answer pair with type '{qa_pair.question_type}' "
                f"to question type '{self.name}'. The question type must be the same as the " 
                "question type of the question-answer pair."
            )
        self._qa_pairs.append(qa_pair)

    def to_markdown(
        self, 
        include_qa_pairs: bool = False, 
        include_evidences: bool = False,
        include_side_note: bool = False, 
        level: int = 0,
    ) -> str:
        """Convert the question type to MarkDown format.
        
        Args:
            include_qa_pairs (`bool`, defaults to `False`):
                Whether to include the existing question-answer pairs in the output.
            include_evidences (`bool`, defaults to `False`):
                Whether to include the source evidences of the question-answer pairs in the output.
            include_side_note (`bool`, defaults to `False`):
                Whether to include the side note of the question-answer pairs in the output.
            level (`int`, defaults to `0`):
                The indentation level for the markdown output.
        
        Returns:
            `str`:
                The markdown representation of this question type.
        """
        indent = "\t" * level
        markdown_strs = [
            f"{indent}- Question Type: {self.name}",
            f"{indent}\t- Description: {self.description}",
            f"{indent}\t- Number of Question-Answer Pairs: {self.counts}",
            f"{indent}\t- Created At In Real-World System Time: {self.created_at}",
        ]
        
        if include_qa_pairs and self._qa_pairs:
            markdown_strs.append(f"{indent}\t- Question-Answer Pairs:")
            for qa_pair in self._qa_pairs:
                markdown_strs.append(
                    qa_pair.to_markdown(
                        include_evidences=include_evidences,
                        include_side_note=include_side_note, 
                        level=level + 2,
                    )
                )
        
        return "\n".join(markdown_strs)


class QuestionTypeToolbook(BaseModel):
    """Aggregate and manage all active question types.
    
    It serves as a registry for `QuestionType` instances, allowing dynamic accumulation 
    of question types across the synthesis pipeline.
    """
    
    id: str = Field(
        default_factory=lambda: f"qtoolbook_{shortuuid.uuid()}",
        description="Unique identifier for the toolbook.",
    )
    question_types: list[QuestionType] = Field(
        default_factory=list,
        description="A list of registered question types.",
    )
    created_at: str = Field(
        default_factory=get_timestamp,
        description="Timestamp of creation of the question type toolbook object **in real-world system time**.",
    )
    
    # Internal mapping for fast lookup by name
    _name_to_type: dict[str, QuestionType] = PrivateAttr(default_factory=dict)

    def model_post_init(self, context: Any) -> None:
        """Initialize the internal name-to-type mapping."""
        for qtype in self.question_types:
            if qtype.name in self._name_to_type:
                raise ValueError(
                    f"A duplicate question type name '{qtype.name}' is found during initialization."
                )
            self._name_to_type[qtype.name] = qtype

    def add_question_type(self, question_type: QuestionType) -> None:
        """Add a new question type to the toolbook.
        
        Args:
            question_type (`QuestionType`):
                The question type to add.
        """
        if question_type.name in self._name_to_type:
            raise ValueError(
                f"The question type with name '{question_type.name}' is already exists."
            )
        self.question_types.append(question_type)
        self._name_to_type[question_type.name] = question_type

    def get_question_type(self, name: str) -> QuestionType | None:
        """Get a question type by name.
        
        Args:
            name (`str`):
                The name of the question type to retrieve.
        
        Returns:
            `QuestionType | None`:
                The question type if found, None otherwise.
        """
        return self._name_to_type.get(name)

    def register_qa_pair(self, qa_pair: QuestionAnswerPair) -> None:
        """Register a question-answer pair to the matching question type.
                
        Args:
            qa_pair (`QuestionAnswerPair`):
                The question-answer pair to register.
        """
        qtype = self._name_to_type.get(qa_pair.question_type)
        if qtype is None:
            available_types = ", ".join(sorted(self._name_to_type.keys()))
            raise ValueError(
                f"The question type '{qa_pair.question_type}' is not found in the tool book. "
                f"The available question type(s) are {available_types}. "
            )
        qtype.add_qa_pair(qa_pair)

    def get_stats(self) -> dict[str, int]:
        """Return statistics mapping type names to their question-answer pair counts.
        
        Returns:
            `dict[str, int]`:
                A dictionary mapping question type names to their counts.
        """
        return {qtype.name: qtype.counts for qtype in self.question_types}

    @computed_field
    @property
    def total_qa_pairs(self) -> int:
        """Return the total number of question-answer pairs across all types.
        
        Returns:
            `int`:
                The total number of question-answer pairs across all types.
        """
        return sum(qtype.counts for qtype in self.question_types)
    
    @computed_field
    @property
    def total_question_types(self) -> int:
        """Return the total number of question types in the toolbook.
        
        Returns:
            `int`:
                The total number of question types in the toolbook.
        """
        return len(self.question_types)


    def to_markdown(
        self, 
        include_qa_pairs: bool = False, 
        include_evidences: bool = False,
        include_side_note: bool = False, 
        level: int = 0,
    ) -> str:
        """Convert the question type toolbook to MarkDown format.
        
        Args:
            include_qa_pairs (`bool`, defaults to `False`):
                Whether to include the existing question-answer pairs in the output.
            include_evidences (`bool`, defaults to `False`):
                Whether to include the source evidences of the question-answer pairs in the output.
            include_side_note (`bool`, defaults to `False`):
                Whether to include the side note of the question-answer pairs in the output.
            level (`int`, defaults to `0`):
                The indentation level for the markdown output.
        
        Returns:
            `str`:
                The markdown representation of this toolbook.
        """
        indent = "\t" * level
        markdown_strs = [
            f"{indent}- Question Type Toolbook (id: {self.id})",
            f"{indent}\t- Statistics",
            f"{indent}\t\t- Total Number of Question Types: {self.total_question_types}",
            f"{indent}\t\t- Total Number of Question-Answer Pairs: {self.total_qa_pairs}",
            f"{indent}\t- Created At In Real-World System Time: {self.created_at}" 
        ]

        if self.total_question_types > 0:
            markdown_strs.extend(
                [
                    f"{indent}\t- Details of Question Types",
                    *[
                        qtype.to_markdown(
                            include_qa_pairs=include_qa_pairs, 
                            include_evidences=include_evidences,
                            include_side_note=include_side_note,
                            level=level + 2
                        )
                        for qtype in sorted(self.question_types, key=lambda qtype: qtype.name)
                    ],
                ]
            ) 
        
        return "\n".join(markdown_strs)


class QASynthesisState(BaseModel):
    """The state of the question-answer synthesis process."""
    
    target_object: Event | PersonDimensionBase | PersonBase = Field(
        description="The target object to synthesize question-answer pairs for.",
    )
    question_type_toolbook: QuestionTypeToolbook = Field(
        description="The question type toolbook.",
    )
    state: Literal["to_do", "doing", "done"] = Field(
        default="to_do",
        description="The state of the question-answer synthesis process.",
    )
    max_attempts: int = Field(
        default=5,
        description="The maximum number of attempts to synthesize question-answer pairs.",
    )
    attempts: int = Field(
        default=0,
        description="The number of attempts to synthesize question-answer pairs so far.",
    )
    qa_pairs: list[QuestionAnswerPair] = Field(
        default_factory=list,
        description="The question-answer pairs synthesized so far.",
    )
    min_qa_count: int = Field(
        default=5,
        description="The target minimum number of question-answer pairs to synthesize.",
    )
    max_qa_count: int = Field(
        default=10,
        description="The target maximum number of question-answer pairs to synthesize.",
    )
    created_at: str = Field(
        default_factory=get_timestamp,
        description="The creation time of the question-answer synthesis state.",
    )
    finished_at: str | None = Field(
        default=None,
        description="The finish time of the question-answer synthesis process.",
    )

    @field_validator("target_object")
    @classmethod
    def validate_target_object(
        cls, v: Event | PersonDimensionBase | PersonBase
    ) -> Event | PersonDimensionBase | PersonBase:
        """Validate the target object."""
        if isinstance(v, Event) and v.output is None:
            raise ValueError(
                f"The target object is an event but it has no output provided."
            )
        return v

    @computed_field
    @property
    def target_type(self) -> Literal[
        "event_with_session", 
        "event_with_graph",
        "dimension", 
        "person"
    ]:
        """Get the type of the target object.
        
        Returns:
            `Literal["event_with_session", "event_with_graph", "dimension", "person"]`:
                The type of the target object.
        """
        if isinstance(self.target_object, Event):
            if isinstance(self.target_object.output, Session):
                return "event_with_session"
            return "event_with_graph"
        elif isinstance(self.target_object, PersonDimensionBase):
            return "dimension"
        elif isinstance(self.target_object, PersonBase):
            return "person"
        raise ValueError(f"The target object's type '{type(self.target_object)}' is not supported.")

    def finish_synthesis(self) -> None:
        """Finish the question-answer synthesis process."""
        self.state = "done"
        self.finished_at = get_timestamp()