# -*- coding: utf-8 -*-
"""QA Notebook for question-answer pair synthesis from an existing user's trajectory."""
import shortuuid
from ._base import NotebookBase
from .agent import SynthesisAgent
from ..models import (
    QuestionType,
    QuestionTypeToolbook,
    QuestionAnswerPair,
    QASynthesisState,
    Message,
    Event,
)
from ..models.persona import PersonDimensionBase, PersonBase
from agentscope.message import Msg, TextBlock
from agentscope.tool import ToolResponse
from pydantic import BaseModel, Field
from typing import (
    Callable,
    Coroutine,
    Any,
)


_SYSTEM_PROMPT = (
    "You are an expert at analyzing question types, " 
    "capable of determining whether a new question type is novel compared to existing ones " 
    "for testing AI memory systems."
)
_TASK_PROMPT = (
    "## Existing Question Types\n\n"
    "All existing question types are documented in a question type tool book. "
    "The current information in the tool book is as follows:\n\n"
    "{toolbook}\n\n"
    "## New Question Type\n\n"
    "The new question type given to you is as follows:\n\n"
    "{new_question_type}\n\n"
    "## Task\n\n"
    "Please carefully analyze the new question type, focus on the new question type's description, " 
    "define your evaluation criteria, and determine whether it is sufficiently novel. Finally, provide your judgment."
)


class _JudgeResult(BaseModel):
    """Structured output for question type novelty judgment."""
    
    explanation: str = Field(
        ...,
        description=(
            "Your reasoning process for determining whether the new question type is novel " 
            "compared to existing ones. Explain why you reached your conclusion."
        ),
    )
    judge_result: bool = Field(
        ...,
        description=(
            "Your final judgment result. "
            "If the new question type is novel compared to existing ones, set it to `True`. "
            "Otherwise, set it to `False`."
        ),
    )
    

class DefaultQAToHint:
    """The default function to generate hint messages for question-answer pairs synthesis
    based on the current synthesis state to guide the agent during question-answer pairs synthesis."""

    hint_prefix: str = "<system-hint>"
    hint_suffix: str = "</system-hint>"

    no_qa_pairs: str = (
        "The current question type tool book:\n"
        "```\n"
        "{toolbook}\n" 
        "```\n"
        "If the user wants to synthesize high-quality question-answer pairs, "
        "you NEED to construct question-answer pairs by calling '{construct_tool}'. "
        "Otherwise, you can directly execute the user's query without constructing question-answer pairs. "
        "Please note that if the questions you wish to synthesize include types not found in the tool book, " 
        "you must call 'add_question_type' to add the new question type to the book before constructing the question-answer pairs. "
        "You can also refine an existing question type's description in the tool book by calling 'refine_question_type_description' "
        "before constructing the question-answer pairs."
    )

    in_progress: str = (
        "The current question type tool book:\n"
        "```\n"
        "{toolbook}\n" 
        "```\n"
        "The question-answer pair(s) you have generated so far:\n"
        "```\n"
        "{qa_pairs}\n"
        "```\n"
        "{num_qa_pairs} question-answer pair(s) have been generated. "
        "You have called {construct_tool} {attempts} time(s) without any fatal errors. "
        "This means that for these {attempts} invocation(s), each invocation synthesized at least one question-answer pair successfully. "
        "You are permitted {num_permitted_attempts} more invocation(s).\n"
        "Now you need to generate at least {num_permitted_count} question-answer pair(s) to reach the target quantity.\n"
        "Your options include:\n"
        "- Synthesize new question-answer pairs to reach the target quantity by calling '{construct_tool}'. " 
        "During the process of constructing new question-answer pairs, you should minimize the overlap " 
        "between the evidence supporting the new question-answer pairs and the evidence used in the previous ones.\n"
        "- Add new question types to the tool book by calling 'add_question_type'.\n"
        "- Refine an existing question type's description in the tool book by calling 'refine_question_type_description'."
    )

    target_reached: str = (
        "The current question type tool book:\n"
        "```\n"
        "{toolbook}\n" 
        "```\n"
        "The question-answer pair(s) you have generated so far:\n"
        "```\n"
        "{qa_pairs}\n"
        "```\n"
        "{num_qa_pairs} question-answer pair(s) have been generated. "
        "You have called {construct_tool} {attempts} time(s) without any fatal errors. "
        "This means that for these {attempts} invocation(s), each invocation synthesized at least one question-answer pair successfully.\n"
        "{stop_msg}\n" 
        "Your options include:\n"
        "- Refine an existing question type's description in the tool book by calling 'refine_question_type_description'.\n"
        "- Complete the question-answer pairs synthesis process by calling 'finish_qa_construction', "
        "and then call 'generate_response' to summarize the synthesis process."
    )

    def __call__(self, state: QASynthesisState) -> str | None:
        """Generate the hint message based on the current synthesis state 
        to guide the agent during question-answer pairs synthesis.
        
        Args:
            state (`QASynthesisState`):
                The current question-answer pairs synthesis state, used to generate the hint message.
        
        Returns:
            `str`:
                The generated hint message.
        """
        target_type = state.target_type
        if target_type in ["event_with_session", "dimension"]:
            construct_tool = "construct_questions"
        else:
            construct_tool = "compose_questions"
        
        toolbook = state.question_type_toolbook.to_markdown(
            include_qa_pairs=False,
            include_evidences=False,
            include_side_note=False,
            level=0,
        )

        if state.state == "to_do": 
            hint = self.no_qa_pairs.format(
                toolbook=toolbook,
                construct_tool=construct_tool,
            )
        else:
            min_count = state.min_qa_count
            num_qa_pairs = len(state.qa_pairs)
            num_permitted_attempts = state.max_attempts - state.attempts
            attempts = state.attempts
            qa_pairs = "\n".join(
                qa.to_markdown(
                    include_evidences=True,
                    include_side_note=True,
                    level=0,
                )
                for qa in state.qa_pairs
            )
            
            if num_qa_pairs >= min_count or num_permitted_attempts <= 0:
                if num_qa_pairs >= min_count:
                    stop_msg = f"You have reached the target minimum number ({min_count}) of question-answer pairs."
                else:
                    stop_msg = f"You have reached the maximum number of attempts ({state.max_attempts})."
                hint = self.target_reached.format(
                    toolbook=toolbook,
                    construct_tool=construct_tool,
                    qa_pairs=qa_pairs,
                    num_qa_pairs=num_qa_pairs,
                    attempts=attempts,
                    stop_msg=stop_msg,
                )
            else:
                num_permitted_count = min_count - num_qa_pairs
                hint = self.in_progress.format(
                    toolbook=toolbook,
                    construct_tool=construct_tool,
                    qa_pairs=qa_pairs,
                    num_qa_pairs=num_qa_pairs,
                    attempts=attempts,
                    num_permitted_attempts=num_permitted_attempts,
                    num_permitted_count=num_permitted_count,
                )

        return f"{self.hint_prefix}{hint}{self.hint_suffix}"


class QANotebook(NotebookBase):
    """The question-answer pairs synthesis notebook to manage question-answer pairs synthesis, 
    providing hints and related tools to the agent for generating high-quality question-answer pairs."""

    description: str = (
        "The tools for generating question-answer pairs around a target object from a user's trajectory. "
        "Activate this tool when you need to generate question-answer pairs for a specific target object. "
        "Once activated, you'll enter the question-answer pairs synthesis mode, " 
        "where you will be guided to generate question-answer pairs for the target object. "
        "The hint messages wrapped by <system-hint></system-hint> will guide you to complete the task. "
        "If you think the question-answer pairs synthesis process is complete, call 'finish_qa_construction' to finish this process."
    )
    name: str = "question_answer_pairs_synthesis_related"

    def __init__(
        self,
        target_object: Event | PersonDimensionBase | PersonBase,
        question_type_toolbook: QuestionTypeToolbook | None = None,
        qa_count_range: tuple[int, int] = (5, 10),
        max_attempts: int = 5,
        qa_to_hint: Callable[..., str | None] | None = None,
        child_qa_pairs: list[QuestionAnswerPair] | None = None,
        message_map: dict[str, Message] | None = None,
        **kwargs: Any, 
    ) -> None:
        """Initialize the question-answer pairs synthesis notebook.
        
        Args:
            target_object (`Event | PersonDimensionBase | PersonBase`):
                The object around which question-answer pairs are built.
            question_type_toolbook (`QuestionTypeToolbook | None`, optional):
                The question type toolbook. If not provided, an empty toolbook will be created.
            qa_count_range (`tuple[int, int]`, defaults to `(5, 10)`):
                The target range of question-answer pairs to generate around the given target object. 
                Both bounds are inclusive.
            max_attempts (`int`, defaults to `5`):
                The maximum number of attempts to generate question-answer pairs. If reached, stop even if range not met.
            qa_to_hint (`Callable[..., str | None] | None`, optional):
                The function to generate the hint message based on the current question-answer pair synthesis state.
            child_qa_pairs (`list[QuestionAnswerPair] | None`, optional):
                Child question-answer pairs available for composition. 
                This is required when the target object is a person or an event with a temporal event graph output.
            message_map (`dict[str, Message] | None`, optional):
                A mapping from message IDs to `Message` objects. It is required for persona dimension targets 
                (which only store message IDs, not `Message` objects). It can also be used as a whitelist filter for 
                event targets with session outputs (messages not present in this map will be treated as invalid).
            **kwargs: (`Any`)
                Additional keyword arguments to pass to the question type similarity judgment agent. 
                The agent is an instance of `ReActAgent`.
        """
        super().__init__()
        
        self.current_state = QASynthesisState(
            target_object=target_object,
            question_type_toolbook=question_type_toolbook or QuestionTypeToolbook(),
            min_qa_count=qa_count_range[0],
            max_qa_count=qa_count_range[1],
            max_attempts=max_attempts,
        )
        self.qa_to_hint = qa_to_hint or DefaultQAToHint()
        self.agent_kwargs = kwargs 

        target_object_type = self.current_state.target_type
        if target_object_type in ["event_with_graph", "person"] and child_qa_pairs is None:
            raise ValueError(
                "Child question-answer pairs are required " 
                "when the target object is an event with a temporal event graph output or a person."
            )
        self.child_qa_pairs = child_qa_pairs or []
        if target_object_type == "dimension" and message_map is None:
            raise ValueError(
                "A message map is required when the target object is a persona dimension model."
            )
        self.message_map = message_map
        self._child_qa_map = {
            qa.id: qa for qa in self.child_qa_pairs
        }
        
        # Register state variables.
        self.register_state(
            "current_state",
            custom_to_json=lambda _: _.model_dump() if _ else None,
            custom_from_json=lambda _: QASynthesisState.model_validate(_) if _ else None,
        )
        self.register_state(
            "child_qa_pairs", 
            custom_to_json=lambda _: [
                __.model_dump() if __ else None
                for __ in _
            ] if _ else None,
            custom_from_json=lambda _: [
                QuestionAnswerPair.model_validate(__) if __ else None
                for __ in _
            ] if _ else None,
        )
        self.register_state(
            "message_map",
            custom_to_json=lambda _: {
                k: __.model_dump() if __ else None
                for k, __ in _.items()
            } if _ else None,
            custom_from_json=lambda _: {
                k: Message.model_validate(__) if __ else None
                for k, __ in _.items()
            } if _ else None,
        )
        self.register_state(
            "_child_qa_map",
            custom_to_json=lambda _: {
                k: __.model_dump() if __ else None
                for k, __ in _.items()
            } if _ else None,
            custom_from_json=lambda _: {
                k: QuestionAnswerPair.model_validate(__) if __ else None
                for k, __ in _.items()
            } if _ else None,
        )

    def _get_valid_messages(self) -> dict[str, Message]:
        """Get valid messages from the message map.
        
        Returns:
            `dict[str, Message]`:
                A mapping from message IDs to `Message` objects.
        """
        target_type = self.current_state.target_type
        if target_type not in ("event_with_session", "dimension"):
            raise AssertionError(
                f"The target object's type '{target_type}' is not supported in the function 'construct_questions'."
            )

        if target_type == "event_with_session":
            session = self.current_state.target_object.output
            valid_messages = {
                message.id: message 
                for message in session.messages 
                if (
                    self.message_map is None 
                    or (self.message_map is not None and message.id in self.message_map)
                )
            }
        else:
            persona_dimension = self.current_state.target_object
            valid_messages = {} 
            for str_field in persona_dimension.get_string_fields():
                tracked_attr = getattr(persona_dimension, str_field)
                for attr_version in tracked_attr.history:
                    for connection in attr_version["connections"]: 
                        msg_instance = self.message_map.get(connection, None) 
                        if msg_instance is not None:
                            valid_messages[connection] = msg_instance
            for list_field in persona_dimension.get_list_fields():
                tracked_attrs = getattr(persona_dimension, list_field)
                for tracked_attr in tracked_attrs:
                    for attr_version in tracked_attr.history:
                        for connection in attr_version["connections"]: 
                            msg_instance = self.message_map.get(connection, None) 
                            if msg_instance is not None:
                                valid_messages[connection] = msg_instance
            for removed_attr in persona_dimension.removed_attributes:
                for attr_version in removed_attr.history:
                    for connection in attr_version["connections"]: 
                        msg_instance = self.message_map.get(connection, None) 
                        if msg_instance is not None:
                            valid_messages[connection] = msg_instance
        
        return valid_messages

    async def _judge_question_type_similarity(self, question_type: QuestionType) -> _JudgeResult:
        """Judge whether the new question type is novel compared to existing question types.
        
        Args:
            question_type (`QuestionType`):
                The new question type to check for novelty.
        
        Returns:
            `_JudgeResult`:
                The judgment result containing explanation and final decision.
        """
        toolbook = self.current_state.question_type_toolbook.to_markdown(include_qa_pairs=False)
        new_question_type = question_type.to_markdown(include_qa_pairs=False)
        
        judge_agent_kwargs = {**self.agent_kwargs} 
        judge_agent_kwargs["name"] = f"agent_{shortuuid.uuid()}"
        judge_agent_kwargs["sys_prompt"] = _SYSTEM_PROMPT

        judge_agent = SynthesisAgent(**judge_agent_kwargs)
        response_msg = await judge_agent(
            msg=Msg(
                "user",
                _TASK_PROMPT.format(
                    toolbook=toolbook,
                    new_question_type=new_question_type,
                ),
                "user",
            ),
            structured_model=_JudgeResult,
        )
        return _JudgeResult.model_validate(response_msg.metadata)

    async def add_question_type(self, question_type: QuestionType) -> ToolResponse:
        """Add a new question type to the toolbook.
        
        Args:
            question_type (`QuestionType`):
                The question type to add.
        
        Returns:
            `ToolResponse`:
                The response of the tool call, confirming the addition or reporting errors.
        """
        question_type = QuestionType.model_validate(question_type)
        name = question_type.name
        existing_qtype = self.current_state.question_type_toolbook.get_question_type(name) 
        
        # First, check for exact name match
        if existing_qtype is not None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"The question type '{name}' already exists. "
                            "If you want to refine the description, use 'refine_question_type_description' instead."
                        ),
                    ),
                ],
            )
        
        # Second, check if the question type is similar to existing types via large language models
        if self.current_state.question_type_toolbook.question_types:
            judge_result = await self._judge_question_type_similarity(question_type)
            if not judge_result.judge_result:
                return ToolResponse(
                    content=[
                        TextBlock(
                            type="text",
                            text=(
                                f"The question type '{name}' is not novel compared to existing ones. "
                                "The operation of adding this question type is rejected. The reason is as follows:\n\n"
                                f"{judge_result.explanation}\n\n"
                                "You can consider refining the description of an existing question type " 
                                "by incorporating the rationale behind the judgment. "
                            ),
                        ),
                    ],
                )

        self.current_state.question_type_toolbook.add_question_type(question_type)
        await self._trigger_hooks()
        
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"The question type '{name}' is added to the tool book successfully.",
                ),
            ],
        )

    async def refine_question_type_description(
        self,
        type_name: str,
        description: str,
    ) -> ToolResponse:
        """Update the description of an existing question type.
        
        Args:
            type_name (`str`):
                The name of the question type to update.
            description (`str`):
                The new description. 
                Please note that this new description will completely overwrite the existing one. 
        
        Returns:
            `ToolResponse`:
                The response of the tool call, confirming the refinement or reporting errors.
        """
        existing_qtype = self.current_state.question_type_toolbook.get_question_type(type_name)  
        if existing_qtype is None:
            available_types = ", ".join(
                sorted(self.current_state.question_type_toolbook.get_stats().keys())
            )
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"The question type '{type_name}' is not found in the tool book. "
                            f"The available question type(s) are {available_types}. "
                            "If you want to add a new question type, use 'add_question_type' instead."
                        ) 
                    ),
                ],
            )
        
        existing_qtype.description = description
        await self._trigger_hooks()
        
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"The description of question type '{type_name}' is updated successfully.",
                ),
            ],
        )

    async def construct_questions(
        self,
        qa_pairs: list[QuestionAnswerPair],
        message_ids_list: list[list[str]],
    ) -> ToolResponse:
        """Construct question-answer pairs from evidence messages.

        Args:
            qa_pairs (`list[QuestionAnswerPair]`):
                A list of question-answer pairs to create. Must have at least one question-answer pair.
            message_ids_list (`list[list[str]]`):
                A list of message ID lists. Each inner list corresponds to
                the evidence messages for the question-answer pair at the same index.
        
        Returns:
            `ToolResponse`:
                Response of the tool call, confirming the construction or reporting errors.
        """
        blocks = [] 
        if self.current_state.state == "done":
            blocks.append(
                TextBlock(
                    type="text",
                    text=(
                        "Warning: The question-answer pairs synthesis process has been finished before. "
                        "Please call 'generate_response' to summarize the synthesis process."
                    ),
                )
            )
        
        # The list of question-answer pairs cannot be empty. 
        if not qa_pairs: 
            blocks.append(
                TextBlock(
                    type="text",
                    text="Error: The list of question-answer pairs cannot be empty.",
                ),
            )
            return ToolResponse(content=blocks)

        # Check max attempts
        if self.current_state.attempts >= self.current_state.max_attempts:
            blocks.append(
                TextBlock(
                    type="text",
                    text=(
                        "Error: It is found that you have already called 'construct_questions' "
                        f"{self.current_state.attempts} time(s), which has reached the maximum allowed "
                        f"attempts ({self.current_state.max_attempts}). "
                        "Please call 'finish_qa_construction' to finish the question-answer pairs synthesis process."
                    ),
                )
            )
            return ToolResponse(content=blocks)
        
        # Check if the maximum number of QA pairs has been reached
        if len(self.current_state.qa_pairs) >= self.current_state.max_qa_count:
            blocks.append(
                TextBlock(
                    type="text",
                    text=(
                        f"Warning: The maximum number of question-answer pairs ({self.current_state.max_qa_count}) has been reached. "
                        "Please call 'finish_qa_construction' to finish the question-answer pairs synthesis process."
                    ),
                )
            )
        
        # Validate input lengths match
        if len(qa_pairs) != len(message_ids_list):
            blocks.append(
                TextBlock(
                    type="text",
                    text=(
                        "Error: Input size mismatch occurs between `qa_pairs` and `message_ids_list`.\n"
                        f"You provided {len(qa_pairs)} question-answer pair(s) .\n"
                        f"while {len(message_ids_list)} evidence list(s) in `message_ids_list` are provided.\n\n"
                        "The length of `qa_pairs` and `message_ids_list` must be the same."
                    ),
                ),
            )
            return ToolResponse(content=blocks) 
                
        # Validate and create QA pairs
        created_count = 0      
        valid_messages = self._get_valid_messages()
        hint_needed = False 

        for i, (qa_pair, msg_ids) in enumerate(zip(qa_pairs, message_ids_list), start=1):
            qa_pair = QuestionAnswerPair.model_validate(qa_pair)
            existing_qtype = self.current_state.question_type_toolbook.get_question_type(qa_pair.question_type)
            if existing_qtype is None:
                blocks.append(
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: For the {i}-th question-answer pair, the question type '{qa_pair.question_type}' is not found in the tool book. "
                            "If you want to construct a question-answer pair with this question type, " 
                            "you need to add it to the tool book first by calling 'add_question_type'."
                        ),
                    ),
                )
                continue
            
            # Check whether each message ID is valid
            invalid_msg_ids = set() 
            for msg_id in msg_ids:
                if msg_id not in valid_messages:
                    invalid_msg_ids.add(msg_id)
            if invalid_msg_ids:
                blocks.append(
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: For the {i}-th question-answer pair, the following message IDs are invalid: {', '.join(sorted(invalid_msg_ids))}."
                        ),
                    ), 
                )
                hint_needed = True 
                continue
            
            # Register with toolbook and add to our list
            for msg_id in msg_ids:
                qa_pair.add_message(valid_messages[msg_id])
            self.current_state.question_type_toolbook.register_qa_pair(qa_pair)
            self.current_state.qa_pairs.append(qa_pair)
            blocks.append(
                TextBlock(
                    type="text",
                    text=f"The {i}-th question-answer pair is added to the tool book successfully.",
                )
            )
            created_count += 1
        
        # As the number of message ids may be large, we only display them once at the end of tool response.
        if hint_needed:
            blocks.append(
                TextBlock(
                    type="text",
                    text=f"The available message IDs are {', '.join(sorted(valid_messages.keys()))}.",
                ),
            )
        
        if created_count > 0:
            self.current_state.attempts += 1
            if self.current_state.state == "to_do":
                self.current_state.state = "doing"
            await self._trigger_hooks()

        blocks.append(
            TextBlock(
                type="text",
                text=f"{created_count} question-answer pair(s) are added to the tool book successfully.",
            )
        )        
        return ToolResponse(content=blocks)

    async def compose_questions(
        self,
        qa_pairs: list[QuestionAnswerPair],
        sub_question_ids_list: list[list[str]],
    ) -> ToolResponse:
        """Construct more complex question-answer pairs by combining child question-answer pairs.
        
        Args:
            qa_pairs (`list[QuestionAnswerPair]`):
                A list of question-answer pairs to create. Must have at least one question-answer pair.
            sub_question_ids_list (`list[list[str]]`):
                A list of sub-question ID lists. Each inner list contains
                the IDs of sub-questions used to compose the more complex question-answer pair at
                the same index. Each list should have at least 2 sub-question IDs. 
        
        Returns:
            `ToolResponse`:
                The response of the tool call, confirming the composition or reporting errors.
        """
        blocks = []
        if self.current_state.state == "done":
            blocks.append(
                TextBlock(
                    type="text",
                    text=(
                        "Warning: The question-answer pairs synthesis process has been finished before. "
                        "Please call 'generate_response' to summarize the synthesis process."
                    ),
                )
            )
        
        # The list of question-answer pairs cannot be empty. 
        if not qa_pairs: 
            blocks.append(
                TextBlock(
                    type="text",
                    text="Error: The list of question-answer pairs cannot be empty.",
                ),
            ) 
            return ToolResponse(content=blocks)

        # Check max attempts
        if self.current_state.attempts >= self.current_state.max_attempts:
            blocks.append(
                TextBlock(
                    type="text",
                    text=(
                        f"Error: You have already called 'compose_questions' {self.current_state.attempts} time(s), which has reached the maximum allowed "
                        f"attempts ({self.current_state.max_attempts}). Please call 'finish_qa_construction' to finish the question-answer pairs synthesis process."
                    ),
                )
            )
            return ToolResponse(content=blocks)
        
        # Check if the maximum number of question-answer pairs has been reached
        if len(self.current_state.qa_pairs) >= self.current_state.max_qa_count:
            blocks.append(
                TextBlock(
                    type="text",
                    text=(
                        f"Warning: The maximum number of question-answer pairs ({self.current_state.max_qa_count}) has been reached. "
                        "Please call 'finish_qa_construction' to finish the question-answer pairs synthesis process."
                    ),
                )
            )
        
        # Validate input lengths match
        if len(qa_pairs) != len(sub_question_ids_list):
            blocks.append(
                TextBlock(
                    type="text",
                    text=(
                        f"Error: The input size mismatch occurs between `qa_pairs` and `sub_question_ids_list`. "
                        f"You provided {len(qa_pairs)} question-answer pair(s) .\n"
                        f"while {len(sub_question_ids_list)} sub-question ID list(s) in `sub_question_ids_list` are provided.\n\n"
                        "The length of `qa_pairs` and `sub_question_ids_list` must be the same."
                    ),
                )
            )
            return ToolResponse(content=blocks)
        
        # Validate and create QA pairs
        created_count = 0
        hint_needed = False 

        for i, (qa_pair, sub_ids) in enumerate(zip(qa_pairs, sub_question_ids_list)):
            qa_pair = QuestionAnswerPair.model_validate(qa_pair)
            existing_qtype = self.current_state.question_type_toolbook.get_question_type(qa_pair.question_type)
            if existing_qtype is None:
                blocks.append(
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: For the {i}-th question-answer pair, the question type '{qa_pair.question_type}' is not found in the tool book. "
                            "If you want to construct a question-answer pair with this question type, " 
                            "you need to add it to the tool book first by calling 'add_question_type'."
                        ),
                    ),
                )
                continue
        
            invalid_sub_ids = set() 
            for sub_id in sub_ids:
                if sub_id not in self._child_qa_map:
                    invalid_sub_ids.add(sub_id)
            if invalid_sub_ids:
                blocks.append(
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: For the {i}-th question-answer pair, the following sub-question IDs are invalid: {', '.join(sorted(invalid_sub_ids))}."
                        ),
                    ),
                )
                hint_needed = True 
                continue

            # Register with toolbook and add to our list
            for sub_id in sub_ids:
                child_qa = self._child_qa_map[sub_id]
                qa_pair.add_subquestion(child_qa)
            self.current_state.question_type_toolbook.register_qa_pair(qa_pair)
            self.current_state.qa_pairs.append(qa_pair)
            created_count += 1
        
        # As the number of sub-question IDs may be large, we only display them once at the end of tool response.
        if hint_needed:
            blocks.append(
                TextBlock(
                    type="text",
                    text=f"The available sub-question IDs are {', '.join(sorted(self._child_qa_map.keys()))}.",
                ),
            )

        if created_count > 0:
            self.current_state.attempts += 1
            if self.current_state.state == "to_do":
                self.current_state.state = "doing"
            await self._trigger_hooks()
        
        blocks.append(
            TextBlock(
                type="text",
                text=f"{created_count} question-answer pair(s) are added to the tool book successfully.",
            )
        )        
        return ToolResponse(content=blocks)

    async def finish_qa_construction(self) -> ToolResponse:
        """Finish the question-answer pairs synthesis process.
        
        Returns:
            `ToolResponse`:
                The response of the tool call, confirming the synthesis process completion.
        """
        min_count = self.current_state.min_qa_count
        current_count = len(self.current_state.qa_pairs)
        
        if current_count < min_count and self.current_state.attempts < self.current_state.max_attempts:
            target_object_type = self.current_state.target_type
            if target_object_type in ["event_with_session", "dimension"]:
                tool_name = "construct_questions"
            else:
                tool_name = "compose_questions"
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            f"Error: The current number of question-answer pairs ({current_count}) " 
                            f"is below the minimum target ({min_count}). "
                            f"Please continue generating question-answer pairs by calling '{tool_name}'."
                        ),
                    ),
                ],
            )
        
        self.current_state.state = "done"
        await self._trigger_hooks()
        
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=(
                        "The question-answer pairs synthesis process is finished successfully " 
                        f"with {current_count} question-answer pair(s) generated. "
                        "Please call 'generate_response' to summarize the synthesis process to the user."
                    ),
                ),
            ],
        )

    def list_tools(
        self,
    ) -> list[Callable[..., Coroutine[Any, Any, ToolResponse]]]:
        base_tools = [
            self.add_question_type,
            self.refine_question_type_description,
            self.finish_qa_construction,
        ]
        
        if self.current_state.target_type in ("event_with_session", "dimension"):
            base_tools.append(self.construct_questions)
        else:
            base_tools.append(self.compose_questions)
        
        return base_tools

    async def get_current_hint(self) -> Msg | None:
        hint_content = self.qa_to_hint(self.current_state)
        if hint_content:
            msg = Msg(
                "user",
                hint_content,
                "user",
            )
            return msg

        return None

    def is_finished(self) -> ToolResponse:
        if self.current_state.state != "done":
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=( 
                            "Error: The question-answer pairs synthesis process is not finished yet. "
                            "Please finish the question-answer pairs synthesis process first."
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
                    text="The state of the question-answer pairs synthesis process is the final state.", 
                ),
            ],
            metadata={
                "success": True,
                "response_msg": None,
            },
        )

