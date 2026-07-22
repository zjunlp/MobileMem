"""Life domain types: the persona's timeline (events / sub-events) and social world (L2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from core.base import JsonlModel, _ABSENT


@dataclass
class Event(JsonlModel):
    """One annual event inside the ``Events`` list (annual_events).

    Declared fields are the ones confirmed in code: the schedule (consumed by
    sub_events) plus ``participants`` / ``importance`` (read by annual_events'
    own summary pass). The per-image payloads — ``additional_info`` and the
    type-specific ``ticket_info`` / ``food_info`` / ``money_info`` /
    ``friend_info`` / ``wechat_info`` — round-trip via ``extra``. The field
    *order* here is inferred from code, not from a frozen sample, so verify the
    key order on a real annual_events row before adopting this model at that
    node's boundary (annual_events is a copy-then-extend node).
    """

    event_name: Any = _ABSENT
    duration_type: Any = _ABSENT
    event_start_time: Any = _ABSENT
    event_end_time: Any = _ABSENT
    participants: Any = _ABSENT
    importance: Any = _ABSENT
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SocialGraph(JsonlModel):
    """The ``Social_Graph`` payload added to a Persona at social_world.

    Top-level keys: ``inner_circle`` (carried over from life_state relationships) and
    ``organizations`` are declared; the planned person categories
    (``extended_contacts`` / ``online_contacts`` / ...) round-trip via ``extra``.
    Each person node (e.g. in ``inner_circle``) has the shape ``{name, gender,
    age_range, category, relationship_to_protagonist, brief, can_appear_in}``
    (see ``_build_inner_circle``); a dedicated node model is deferred until a
    pipeline node actually consumes it.
    """

    inner_circle: Any = _ABSENT
    organizations: Any = _ABSENT
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SubEvent(JsonlModel):
    """A sub_events row: a protagonist's long/mid events split into sub-events."""

    uuid: Any = _ABSENT
    sub_events: Any = _ABSENT
    cost_info: Any = _ABSENT
    extra: Dict[str, Any] = field(default_factory=dict)
