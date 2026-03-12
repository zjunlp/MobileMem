"""Postprocessing utilities for session data."""
from ..models.session import Session
from typing import Literal


def merge_parallel_sessions(
    sessions: list[Session],
    check_messages: bool = True,
) -> list[Session]:
    """Merge temporally overlapping (parallel) sessions into single sessions.

    It iterates through sessions in order and merges consecutive sessions whose
    time spans overlap.  Merged sessions receive a combined event identifier.

    Args:
        sessions (`list[Session]`):
            The list of sessions to process.  Each session is deep-copied
            before mutation so the originals are not modified.
        check_messages (`bool`, defaults to `True`):
            Whether to check and adjust message timestamps to ensure
            chronological order when merging.

    Returns:
        `list[Session]`:
            A new list of sessions where all temporally overlapping
            consecutive sessions have been merged.
    """
    merged = []
    for session in sessions:
        session = session.model_copy(deep=True)
        if len(merged) == 0:
            merged.append(session)
            continue

        last_session = merged[-1]
        if last_session.ended_at > session.started_at:
            new_event_id = f"f{last_session.event_id}&{session.event_id}"
            session.event_id = last_session.event_id = new_event_id
            merged[-1] = Session.merge(
                [last_session, session],
                check_messages=check_messages,
            )
        else:
            merged.append(session)

    return merged


def unify_message_names(
    sessions: list[Session],
    name: str,
    role: Literal["user", "assistant", "system"] = "user",
    in_place: bool = True,
) -> list[Session]:
    """Replace the sender name of all messages with the given role.

    Args:
        sessions (`list[Session]`):
            The sessions whose messages will be updated.
        name (`str`):
            The name to assign to matching messages.
        role (`Literal["user", "assistant", "system"]`, defaults to ``"user"``):
            Only messages with this role will have their name replaced.
        in_place (`bool`, defaults to `True`):
            If it is enabled, the function mutates the provided sessions directly and returns
            them.  If it is disabled, the function deep-copies each session first so the
            originals are not modified.

    Returns:
        `list[Session]`:
            The sessions with names unified.
    """
    if not in_place:
        sessions = [s.model_copy(deep=True) for s in sessions]

    for session in sessions:
        for message in session.messages:
            if message.role == role:
                message.name = name

    return sessions
