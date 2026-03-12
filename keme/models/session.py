from __future__ import annotations
from datetime import datetime, timedelta
import shortuuid
from pydantic import (
    BaseModel, 
    Field, 
    field_validator,
    computed_field,
    PrivateAttr,
    ModelWrapValidatorHandler, 
    model_validator,
)
from ..utils import get_timestamp
from ._constants import NO_SIDE_NOTE
from typing import (
    Literal, 
    Any,
    Self, 
) 


class Message(BaseModel):
    """Represent a single message in a session."""

    id: str = Field(
        default_factory=lambda: f"message_{shortuuid.uuid()}",
        description="Unique message identifier.",
    )
    name: str = Field(
        description="Name of the message sender.",
    )
    content: str = Field(
        description="Message content. Should be natural and contextually appropriate.",
    )
    role: Literal["user", "assistant", "system"] = Field(
        description=(
            "Role of the message sender. Must be one of: 'user', 'assistant', 'system'. "
            "'user' means the message is from the user, 'assistant' means the message is from the AI assistant, " 
            "'system' means the message is from the system which refers to an AI-centered integrated architecture " 
            "that encompasses the assistant, perception modules (e.g., sensors), external tools, memory components, " 
            "and actuators that collectively enable autonomous perception, reasoning, and action."
        ),
    )
    timestamp: str = Field(
        description=(
            "Timestamp when the message was sent, in ISO 8601 format (YYYY-MM-DD HH:MM:SS). "
            "Must fall within the parent session's time range (between `started_at` and `ended_at`)."
        ),
    )
    side_note: str = Field(
        default=NO_SIDE_NOTE,
        description=(
            "Commentary on the message rationale, what it accomplishes, or "
            "why it was generated this way. You may also reflect on how this "
            "message contributes to the overall objectives of the synthesis task."
        ),
    )
    created_at: str = Field(
        default_factory=get_timestamp,
        description=(
            "Timestamp of creation of the message object **in real-world system time**."
        ),
    )
    # Metadata of the message object, which can be used to store additional information about the message.
    # For example, the metadata can be used to store file paths of related images or videos.
    _metadata: dict[str, Any] = PrivateAttr(default_factory=dict)

    def update_metadata(self, metadata: dict[str, Any]) -> None:
        """Update the metadata of the message object.

        Args:
            metadata (`dict[str, Any]`):
                The metadata to be attached to the message object.
        """
        self._metadata = metadata

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

        metadata = values.get("metadata", {}) 
        instance.update_metadata(metadata)
        
        return instance

    @computed_field
    @property
    def metadata(self) -> dict[str, Any]:
        """Get the metadata of the message object.
        
        Returns:
            `dict[str, Any]`:
                The metadata of the message object.
        """
        return self._metadata.copy()

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        """Validate that `timestamp` is a valid ISO 8601 string."""
        try:
            _ = datetime.fromisoformat(v)
        except ValueError:
            raise ValueError(
                f"The timestamp '{v}' is not in a valid format. "
                "Please use the format YYYY-MM-DD HH:MM:SS, for example: "
                "'2024-08-25 12:01:42'."
            )
        return v

    def to_markdown(self, include_side_note: bool = False, level: int = 0) -> str:
        """
        Convert the message to MarkDown format.
        
        Args:
            include_side_note (`bool`, defaults to `False`):
                Whether to include side note of the message object.
            level (`int`, defaults to `0`):
                The level of the message in the hierarchy.
        """
        indent = "\t" * level
        markdown_strs = [
            f"{indent}- Message ID: {self.id}",
            f"{indent}- {self.name} (timestamp: {self.timestamp})",
            f"{indent}\t- Role: {self.role}",
            f"{indent}\t- Content: {self.content}",
            f"{indent}\t- Created At In Real-World System Time: {self.created_at}",
        ]
        if include_side_note:
            markdown_strs.append(f"{indent}\t- Side Note: {self.side_note}")
        return "\n".join(markdown_strs)  


class Session(BaseModel):
    """
    Represent a session (human-AI interaction or external application usage).
    
    Sessions are the leaf nodes in the trajectory hierarchy.
    """

    id: str = Field(
        default_factory=lambda: f"session_{shortuuid.uuid()}",
        description="Unique session identifier.",
    )
    event_id: str | None = Field(
        default=None, 
        description=(
            "ID of the parent event that this session belongs to. "
            "`None` if this is the top-level session (directly under the person root)."
        ),
    )
    messages: list[Message] = Field(
        description=(
            "Ordered list of messages in the session. Should form a "
            "coherent, natural session."
        ),
        min_length=1,
    )
    side_note: str = Field(
        default=NO_SIDE_NOTE,
        description=(
            "Commentary on the session's purpose, how it advances the "
            "parent event, and any significant outcomes or impacts. You may also "
            "reflect on how this session contributes to the overall objectives "
            "of the synthesis task."
        ),
    )
    created_at: str = Field(
        default_factory=get_timestamp,
        description="Timestamp of creation of the session object **in real-world system time**.",
    )

    @field_validator("messages")
    @classmethod
    def validate_messages(cls, v: list[Message]) -> list[Message]:
        """Validate that messages are in chronological order."""
        prev_time = None 
        for i, message in enumerate(v): 
            current_time = datetime.fromisoformat(message.timestamp)
            if prev_time is None: 
                prev_time = current_time
                continue
            if current_time <= prev_time:
                raise ValueError(
                    "Messages must be in strict chronological order. "
                    f"The message at index {i} (timestamp: '{message.timestamp}') "
                    f"is not later than the previous message at index {i - 1} (timestamp: '{v[i - 1].timestamp}'). "
                    "Please ensure all message timestamps are strictly increasing."
                )
            prev_time = current_time
        return v

    @computed_field
    @property
    def started_at(self) -> str:
        """Return session start time (the first message's timestamp) 
        in ISO 8601 format (YYYY-MM-DD HH:MM:SS)."""
        return self.messages[0].timestamp
    
    @computed_field
    @property
    def ended_at(self) -> str:
        """Return session end time (the last message's timestamp) 
        in ISO 8601 format (YYYY-MM-DD HH:MM:SS)."""
        return self.messages[-1].timestamp

    def to_markdown(self, include_side_note: bool = False, level: int = 0) -> str:
        """
        Convert the session to MarkDown format.
        
        Args:
            include_side_note (`bool`, defaults to `False`):
                Whether to include side note of the session object.
            level (`int`, defaults to `0`):
                The level of the session in the hierarchy.
        """
        indent = "\t" * level
        markdown_strs = [
            f"{indent}- Session ID: {self.id}",
            f"{indent}\t- Parent Event ID: {self.event_id}",
            f"{indent}\t- Temporal Span: {self.started_at} - {self.ended_at}",
            f"{indent}\t- Created At In Real-World System Time: {self.created_at}",
        ]
        if include_side_note:
            markdown_strs.append(f"{indent}\t- Side Note: {self.side_note}")

        markdown_strs.extend(
            [
                f"{indent}\t- Messages",
                *[
                    message.to_markdown(
                        include_side_note=include_side_note, 
                        level=level + 2,
                    )
                    for message in self.messages
                ],
            ]
        )
        return "\n".join(markdown_strs)

    @classmethod
    def merge(cls, sessions: list[Session], check_messages: bool = False) -> Session:
        """
        Merge multiple sessions into a single session.

        This method combines multiple sessions that belong to the same parent event
        into one unified session.

        Args:
            sessions (`list[Session]`):
                A list of sessions to merge. Must contain at least one session,
                and all sessions must have the same `event_id`.
            check_messages (`bool`, defaults to `False`):
                Whether to check and adjust the timestamps of the messages to ensure
                they are in chronological order.

        Returns:
            `Session`:
                A new session containing all messages from the input sessions,
                sorted by timestamp.

        Raises:
            `ValueError`:
                If the input list is empty or if sessions have different `event_id` values.
        """
        if not sessions:
            raise ValueError("Cannot merge an empty list of sessions.")

        # Check that all sessions have the same `event_id`
        event_ids = {session.event_id for session in sessions}
        if len(event_ids) > 1:
            raise ValueError(
                f"Cannot merge sessions with different `event_id` values. "
                f"Find {len(event_ids)} distinct event IDs: {event_ids}."
            )

        # Collect and sort all messages by timestamp
        all_messages = []
        for session in sessions:
            all_messages.extend(session.messages)
        all_messages.sort(key=lambda msg: datetime.fromisoformat(msg.timestamp))

        if check_messages:
            for i, message in enumerate(all_messages[1: ], start=1): 
                prev_message = all_messages[i - 1]
                current_message = message
                prev_ts = datetime.fromisoformat(prev_message.timestamp)
                current_ts = datetime.fromisoformat(current_message.timestamp)
                if current_ts <= prev_ts:
                    current_message.timestamp = (prev_ts + timedelta(seconds=120)).strftime("%Y-%m-%d %H:%M:%S")

        # Build side note indicating which sessions were merged
        session_ids = [session.id for session in sessions]
        if len(session_ids) > 1:
            side_note = f"This session is merged from {len(sessions)} session(s): {', '.join(session_ids)}."
        else:
            side_note = f"{sessions[0].side_note}\nNote that this session is the copy of the session with ID '{session_ids[0]}'."

        return cls(
            event_id=sessions[0].event_id,
            messages=all_messages,
            side_note=side_note,
        )