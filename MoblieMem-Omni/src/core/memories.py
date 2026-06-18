"""Memory-artifact domain types: group chats and generated image records (L2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from core.base import JsonlModel, _ABSENT


@dataclass
class GroupChat(JsonlModel):
    """A stage7 group-chat document: all chats generated for one protagonist.

    ``_errors`` and any other keys round-trip via ``extra``.
    """

    uuid: Any = _ABSENT
    source_signature: Any = _ABSENT
    nationality: Any = _ABSENT
    language: Any = _ABSENT
    template: Any = _ABSENT
    group_chats: Any = _ABSENT
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ImageRecord(JsonlModel):
    """A stage10 ``total_images`` row.

    Only the four keys shared by every row are declared; the type-specific
    payload (book -> title/author; video -> uploader/duration; group_chat ->
    messages; shopping -> price/...; etc.) round-trips via ``extra``.
    """

    uuid: Any = _ABSENT
    sub_event_id: Any = _ABSENT
    type: Any = _ABSENT
    image_path: Any = _ABSENT
    extra: Dict[str, Any] = field(default_factory=dict)
