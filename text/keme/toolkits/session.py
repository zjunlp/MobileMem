from ._base import NotebookBase
from ..models import (
    Message,
    Session,
    Event,
)
from ..models.persona import PersonBase
from agentscope.message import Msg, TextBlock
from agentscope.tool import ToolResponse
from datetime import datetime
from ..models._constants import NO_SIDE_NOTE
from copy import deepcopy
from typing import (
    Callable, 
    Coroutine,
    Literal, 
    Any,
)


class DefaultSessionToHint:
    """The default function to generate the hint message based on the current 
    session state and person profile to guide the agent on next steps."""

    hint_prefix: str = "<system-hint>"
    hint_suffix: str = "</system-hint>"

    no_session: str = (
        "The current person profile:\n"
        "```\n"
        "{person}\n"
        "```\n"
        "If the user wants to synthesize a session, "
        "you NEED to create a session by calling 'create_session'. "
        "The session should contain natural, contextually appropriate messages. "
        "Messages must be in strictly chronological order. " 
        "They should form a coherent, natural session. "
        "Otherwise, you can directly execute the user's query without creating a session."
    )

    session_created: str = (
       "The current person profile:\n"
        "```\n"
        "{person}\n"
        "```\n"
        "The session has been created successfully:\n"
        "```\n"
        "{session}\n"
        "```\n"
        "Now your options include:\n"
        "- Update person attributes if the session and requirements from parent event (if given) " 
        "reflect any changes to the person's profile by calling 'set_dimension_string_attribute' or 'set_dimension_list_attribute'. "
        "Each person attribute belongs to a specific dimension.\n"
        "- Link session messages from the user or system role to person attributes by calling 'link_string_attribute' or 'link_list_attribute_item'.\n"
        "- If no more changes or links are needed, finish the session creation by calling 'finish_session_creation', and calling 'generate_response' to " 
        "summarize the session to the user."
    )

    def __call__(
        self,
        person: PersonBase,
        session: Session | None,
    ) -> str | None:
        """Generate the hint message based on the current session state and person profile
        to guide the agent on next steps.

        Args:
            session (`Session | None`):
                The current session, used to generate the hint message.
            person (`PersonBase`):
                The current person profile, used to generate the hint message.

        Returns:
            `str | None`:
                The generated hint message, or None if there is no relevant hint.
        """
        person_markdown = person.to_markdown(include_side_note=True)
        
        if session is None:
            hint = self.no_session.format(person=person_markdown)
        else:
            session_markdown = session.to_markdown(include_side_note=True)
            hint = self.session_created.format(
                person=person_markdown, 
                session=session_markdown,
            )

        if hint:
            return f"{self.hint_prefix}{hint}{self.hint_suffix}"

        return hint


class SessionNotebook(NotebookBase):
    """The session notebook to manage session creation, 
    providing hints and session-related tools to the agent."""

    description: str = (
        "The session-related tools for session generation. "
        "Activate this tool when you need to create a session for a given event. "
        "Once activated, you'll enter the session creation mode, where you will be guided "
        "to create natural, contextually appropriate sessions. The hint messages wrapped by "
        "<system-hint></system-hint> will guide you to complete the task. "
        "If you think the user no longer wants to continue the session creation, you need to confirm with the user "
        "and call 'finish_session_creation' to finish the session creation."
    )
    name: str = "session_generation_related"

    def __init__(
        self,
        person: PersonBase,
        parent_event: Event | None = None,
        session_to_hint: Callable[[PersonBase, Session | None], str | None] | None = None,
    ) -> None:
        """Initialize the session notebook.

        Args:
            person (`PersonBase`):
                The person that this notebook belongs to.
            parent_event (`Event | None`, optional):
                The parent event that this session will expand. 
                If provided, this notebook is used to create a session for the specified parent event. 
                If None, this notebook creates a top-level session (directly under the Person root).
            session_to_hint (`Callable[[PersonBase, Session | None], str | None] | None`, optional):
                The function to generate hint messages based on the current session state and person.
                If not provided, a default `DefaultSessionToHint` object will be used.
                The hint function guides the agent on next steps (e.g., when to create session,
                how to handle person attribute updates).
        """
        super().__init__()

        self.person = person
        self.parent_event = parent_event

        self.session_to_hint = session_to_hint or DefaultSessionToHint()

        self.current_session: Session | None = None

        # Register the current_session state for state management
        self.register_state(
            "current_session",
            custom_to_json=lambda _: _.model_dump() if _ else None,
            custom_from_json=lambda _: Session.model_validate(_) if _ else None,
        )

        # The following attributes are also registered as state variables to track the changes.
        # NOTE: the following codes may be changed when the logic of agent changes.
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

    def _validate_messages_time_range(self, messages: Message | list[Message]) -> str | None:
        """Validate the time range of messages."""
        if isinstance(messages, Message):
            messages = [messages]

        if self.parent_event is None:
            parent_start = datetime.fromisoformat(self.person.trajectory_start)
            parent_end = datetime.fromisoformat(self.person.trajectory_end)
            constraint_source = "person's trajectory"
        else:
            parent_start = datetime.fromisoformat(self.parent_event.started_at)
            parent_end = datetime.fromisoformat(self.parent_event.ended_at)
            constraint_source = "parent event's"

        for i, message in enumerate(messages):
            msg_time = datetime.fromisoformat(message.timestamp)
            if msg_time < parent_start or msg_time > parent_end:
                return (
                    f"Error: Message at index {i} has timestamp '{message.timestamp}' "
                    f"which is outside the {constraint_source} time range ({parent_start} to {parent_end}). "
                    f"All message timestamps must fall within the {constraint_source} time span."
                )

        return None

    async def create_session(
        self,
        messages: list[Message],
        session_side_note: str | None = None,
    ) -> ToolResponse:
        """Create a session.

        Args:
            messages (`list[Message]`):
                The list of messages in the session. Must have at least one message.
                Messages must be in chronological order. They should form a coherent, natural 
                session.
            session_side_note (`str | None`, optional):
                Commentary on the session's purpose, how it advances the 
                parent event, and any significant outcomes or impacts. You may also 
                reflect on how this session contributes to the overall objectives 
                of the synthesis task.

        Returns:
            `ToolResponse`:
                The response of the tool call, confirming session creation or reporting errors.
        """
        # Validate messages
        if not messages:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text="Error: At least one message is required to create a session.",
                    ),
                ],
            )

        new_messages = [] 
        for message in messages:
            if isinstance(message, dict):
                message = deepcopy(message) 
                # If the model generates the message id, we need to remove it 
                # to ensure each message has a unique id.
                if "id" in message:
                    del message["id"]
            new_messages.append(Message.model_validate(message))
        messages = new_messages

        # Determine event_id
        event_id = self.parent_event.id if self.parent_event is not None else None

        # Validate that all message timestamps fall within parent's time range
        msg = self._validate_messages_time_range(messages)
        if msg is not None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=msg,
                    ),
                ],
            )

        if self.current_session is not None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text="Error: The session has already been created.",
                    ),
                ],
            )

        # Create session object
        side_note = session_side_note or NO_SIDE_NOTE
        try:
            session = Session(
                event_id=event_id,
                messages=messages,
                side_note=side_note,
            )
        except Exception as e:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"Error: Failed to create session. {str(e)}",
                    ),
                ],
            ) 

        self.current_session = session
        await self._trigger_hooks()

        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=(
                        f"Session ({session.started_at} to {session.ended_at}) " 
                        f"is created successfully with {len(session.messages)} message(s)."
                    ),
                ),
            ],
        )

    async def set_dimension_string_attribute(
        self,
        operation_description: str, 
        dimension_name: str,
        attribute_name: str,
        attribute_value: str,
    ) -> ToolResponse:
        """Set a string attribute value in a specific dimension and record the operation. 

        Args:
            operation_description (`str`):
                Description of the operation to be recorded in the dimension's operations log.
                It should describe what changed and why. 
            dimension_name (`str`):
                The name of the dimension containing the attribute.
            attribute_name (`str`):
                The name of the attribute to update within the specified dimension.
                Each dimension has its own set of valid string attributes.
            attribute_value (`str`):
                The new value for the attribute. 

        Returns:
            `ToolResponse`:
                The response of the tool call, confirming the attribute update or reporting errors.
        """
        if self.current_session is None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: You must create a session first before updating person attributes. "
                            "Person attribute changes occur at the end of the session (after the last message), "
                            "reflecting that a person's characteristics change after experiencing an event. "
                            "Please call 'create_session' first, then update person attributes."
                        ),
                    ),
                ],
            )
            
        response = self.is_finished()
        blocks = []
        if response.metadata["success"]:
            # NOTE: We use "Warning" instead of "Error" here because when the agent outputs 
            # multiple tool calls in a single response, earlier tool calls (e.g., person 
            # profile updates via `set_dimension_string_attribute`) may fail while a later 
            # tool call (e.g., `finish_session_creation`) succeeds. In such cases, retrying 
            # the failed operations would find the session already finished. Using "Warning" 
            # allows the operation to proceed and simply informs the agent to call 
            # `generate_response`, rather than blocking execution with an error.
            blocks.append(
                TextBlock(
                    type="text",
                    text=(
                        "Warning: The session creation process has been finished before. " 
                        "Please call 'generate_response' to summarize the session and person profile changes to the user."
                    ),
                ),
            )

        # Delegate to the Person model's dimension-based method
        result = self.person.set_dimension_string_attribute(
            dimension_name,
            attribute_name,
            attribute_value,
            operation_description,
            self.current_session.ended_at,
        )
        blocks.append(
            TextBlock(
                type="text",
                text=result,
            ),
        )

        return ToolResponse(content=blocks)

    async def set_dimension_list_attribute(
        self,
        operation_description: str, 
        dimension_name: str,
        attribute_name: str,
        action: Literal["add", "revise", "delete"],
        item_index: int | None = None,
        item_value: str | None = None,
    ) -> ToolResponse:
        """Modify a list attribute in a specific dimension and record the operation.

        Args:
            operation_description (`str`):
                Description of the operation to be recorded in the dimension's operations log.
                It should describe what changed and why. 
            dimension_name (`str`):
                The name of the dimension containing the attribute.
            attribute_name (`str`):
                The name of the list attribute to modify within the specified dimension.
                Each dimension has its own set of valid list attributes.
            action (`Literal["add", "revise", "delete"]`):
                The action to perform on the list. 
            item_index (`int | None`, optional):
                The index of the item to revise or delete. Required for 'revise' and 'delete' actions.
                Ignored for 'add' action.
            item_value (`str | None`, optional):
                The value for the item to add or revise. Required for 'add' and 'revise' actions.
                Ignored for 'delete' action.
        
        Notes:
            - 'add': Add a new item to the list. 
            - 'revise': Revise an existing item at `item_index`. 
            - 'delete': Delete an item at `item_index`. 

        Returns:
            `ToolResponse`:
                The response of the tool call, confirming the attribute update or reporting errors.
        """
        if self.current_session is None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: You must create a session first before updating person attributes. "
                            "Person attribute changes occur at the end of the session (after the last message), "
                            "reflecting that a person's characteristics change after experiencing an event. "
                            "Please call 'create_session' first, then update person attributes."
                        ),
                    ),
                ],
            )
        
        response = self.is_finished()
        blocks = [] 
        if response.metadata["success"]:
            # Same as above.
            blocks.append(
                TextBlock(
                    type="text",
                    text=(
                        "Warning: The session creation process has been finished before. "
                        "Please call 'generate_response' to summarize the session and person profile changes to the user."
                    ),
                ), 
            )

        # Delegate to the Person model's dimension-based method
        result = self.person.set_dimension_list_attribute(
            dimension_name,
            attribute_name,
            action,
            operation_description,
            self.current_session.ended_at,
            item_index=item_index,
            item_value=item_value,
        )
        blocks.append(
            TextBlock(
                type="text",
                text=result,
            ), 
        )

        return ToolResponse(content=blocks)
    
    async def finish_session_creation(self) -> ToolResponse:
        """Finish the creation of the current session.

        Returns:
            `ToolResponse`:
                The response of the tool call, confirming the session completion.
        """
        if self.current_session is None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text="Error: There is no session to finish creation.",
                    ),
                ],
            )

        if self.parent_event is not None:
            self.parent_event.complete(self.current_session)
        await self._trigger_hooks()
        
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=(
                        "The session creation is finished successfully. " 
                        "Now you can call 'generate_response' to summarize the session and person profile changes to the user."
                    ),
                ),
            ],
        )

    async def link_string_attribute(
        self,
        message_ids: list[str],
        dimension_name: str,
        attribute_name: str,
    ) -> ToolResponse:
        """Link session messages to a string attribute in the person profile.
        
        It establishes a connection indicating that the specified messages 
        reflect a specific string attribute's value. 
        
        Args:
            message_ids (`list[str]`):
                The list of message IDs from the current session to link.
                These messages should reflect the attribute value.
            dimension_name (`str`):
                The name of the dimension containing the attribute.
            attribute_name (`str`):
                The name of the string attribute to link.
        
        Returns:
            `ToolResponse`:
                The response confirming the link or reporting errors.
        """
        if self.current_session is None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: You must create a session first before linking messages to attributes. "
                            "Please call 'create_session' first. " 
                            "Note that each message in the session will have a unique ID "
                            "which is automatically generated by the system during session creation."
                        ),
                    ),
                ],
            )
        
        response = self.is_finished()
        blocks = []
        if response.metadata["success"]:
            # Same as above.
            blocks.append(
                TextBlock(
                    type="text",
                    text=(
                        "Warning: The session creation process has been finished before. "
                        "Please call 'generate_response' to summarize the session and person profile changes to the user."
                    ),
                ),
            )
        
        # Validate that all `message_ids` exist in the current session (only user/system messages are valid)
        session_message_ids = {msg.id for msg in self.current_session.messages if msg.role != "assistant"}
        assistant_message_ids = {msg.id for msg in self.current_session.messages if msg.role == "assistant"}
        invalid_ids = [mid for mid in message_ids if mid not in session_message_ids]
        if invalid_ids:
            invalid_assistant_ids = [mid for mid in invalid_ids if mid in assistant_message_ids]
            not_found_ids = [mid for mid in invalid_ids if mid not in assistant_message_ids]
            
            error_parts = ["Error: Invalid message IDs are provided."]
            if invalid_assistant_ids:
                error_parts.append(
                    f"\n\nThe following message IDs are from the assistant role and cannot be linked to attributes: {', '.join(invalid_assistant_ids)}."
                )
            if not_found_ids:
                error_parts.append(
                    f"\n\nThe following message IDs are not found in the current session: {', '.join(not_found_ids)}."
                )
            error_parts.append(f"\n\nValid message IDs are {', '.join(sorted(session_message_ids))}.")
            
            blocks.append(
                TextBlock(
                    type="text",
                    text="".join(error_parts),
                ),
            )
            return ToolResponse(content=blocks)
        
        result = self.person.link_string_attribute(
            dimension_name,
            attribute_name,
            message_ids,
        )
        blocks.append(
            TextBlock(
                type="text",
                text=result,
            ),
        )
        
        return ToolResponse(content=blocks)

    async def link_list_attribute_item(
        self,
        message_ids: list[str],
        dimension_name: str,
        attribute_name: str,
        item_index: int,
    ) -> ToolResponse:
        """Link session messages to a specific item in a list attribute.
        
        It establishes a connection indicating that the specified messages 
        reflect a specific list item's value.
        
        Args:
            message_ids (`list[str]`):
                The list of message IDs from the current session to link.
                These messages should reflect the list item's value.
            dimension_name (`str`):
                The name of the dimension containing the attribute.
            attribute_name (`str`):
                The name of the list attribute.
            item_index (`int`):
                The index of the item in the list to link.
        
        Returns:
            `ToolResponse`:
                The response confirming the link or reporting errors.
        """
        if self.current_session is None:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=(
                            "Error: You must create a session first before linking messages to attributes. "
                            "Please call 'create_session' first. " 
                            "Note that each message in the session will have a unique ID "
                            "which is automatically generated by the system during session creation."
                        ),
                    ),
                ],
            )

        response = self.is_finished()
        blocks = []
        if response.metadata["success"]:
            # Same as above.
            blocks.append(
                TextBlock(
                    type="text",
                    text=(
                        "Warning: The session creation process has been finished before. "
                        "Please call 'generate_response' to summarize the session and person profile changes to the user."
                    ),
                ),
            )
        
        # Validate that all `message_ids` exist in the current session (only user/system messages are valid)
        session_message_ids = {msg.id for msg in self.current_session.messages if msg.role != "assistant"}
        assistant_message_ids = {msg.id for msg in self.current_session.messages if msg.role == "assistant"}
        invalid_ids = [mid for mid in message_ids if mid not in session_message_ids]
        if invalid_ids:
            invalid_assistant_ids = [mid for mid in invalid_ids if mid in assistant_message_ids]
            not_found_ids = [mid for mid in invalid_ids if mid not in assistant_message_ids]
            
            error_parts = ["Error: Invalid message IDs are provided."]
            if invalid_assistant_ids:
                error_parts.append(
                    f"\n\nThe following message IDs are from the assistant role and cannot be linked to attributes: {', '.join(invalid_assistant_ids)}."
                )
            if not_found_ids:
                error_parts.append(
                    f"\n\nThe following message IDs are not found in the current session: {', '.join(not_found_ids)}."
                )
            error_parts.append(f"\n\nValid message IDs are {', '.join(sorted(session_message_ids))}.")
            
            blocks.append(
                TextBlock(
                    type="text",
                    text="".join(error_parts),
                ),
            )
            return ToolResponse(content=blocks)
        
        result = self.person.link_list_attribute_item(
            dimension_name,
            attribute_name,
            item_index,
            message_ids,
        )
        blocks.append(
            TextBlock(
                type="text",
                text=result,
            ),
        )
        
        return ToolResponse(content=blocks)
        
    def list_tools(
        self,
    ) -> list[Callable[..., Coroutine[Any, Any, ToolResponse]]]:
        return [
            self.create_session,
            self.set_dimension_string_attribute,
            self.set_dimension_list_attribute,
            self.link_string_attribute,
            self.link_list_attribute_item,
            self.finish_session_creation,
        ]

    async def get_current_hint(self) -> Msg | None:
        hint_content = self.session_to_hint(self.person, self.current_session)
        if hint_content:
            msg = Msg(
                "user",
                hint_content,
                "user",
            )
            return msg

        return None

    def is_finished(self) -> ToolResponse:
        """Check whether the session creation process is finished.
        
        Returns:
            `ToolResponse`:
                The response indicating whether the session creation is complete.
        """
        if (
            (self.parent_event is None and self.current_session is not None) or 
            (
                self.parent_event is not None and 
                self.current_session is not None and 
                isinstance(self.parent_event.output, Session) and 
                self.parent_event.output.id == self.current_session.id
            )
        ):
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text="The state of the session creation process is the final state.",
                    ),
                ],
                metadata={
                    "success": True,
                    "response_msg": None,
                },
            ) 
            
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=(
                        "Error: The session creation process is not finished yet. "
                        "Please finish the session creation process first by calling "
                        "'finish_session_creation'."
                    ),
                ),
            ],
            metadata={
                "success": False,
                "response_msg": None,
            },
        )