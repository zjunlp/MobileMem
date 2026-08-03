"""Persona domain types: the synthetic person's identity / profile (L2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from core.base import JsonlModel, _ABSENT


@dataclass
class Persona(JsonlModel):
    """The profile node's top-level row — the nine base fields below.

    Main-trunk data flow: profile / persona_seeds emit these nine fields at
    the *top level*. From life_state onward the row is **repackaged** into
    ``{uuid, Basic_Profile, Init_State}`` — the base profile moves into the
    nested :class:`BasicProfile` (note: that sub-object drops ``role_identity``,
    orders ``name`` before ``uuid``, and may add ``appearance``).
    timeline_dates / social_world / annual_events then append
    ``Important_Dates`` / ``Social_Graph`` / ``Events`` onto that container.
    So ``Persona`` models the profile row specifically; later trunk rows wrap
    the profile in ``Basic_Profile`` (see :class:`BasicProfile`).
    """

    uuid: Any = _ABSENT
    role_identity: Any = _ABSENT
    name: Any = _ABSENT
    gender: Any = _ABSENT
    birth_date: Any = _ABSENT
    nationality: Any = _ABSENT
    language: Any = _ABSENT
    personality_traits: Any = _ABSENT
    life_experiences: Any = _ABSENT
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BasicProfile(JsonlModel):
    """The ``Basic_Profile`` sub-object life_state packs the profile row into.

    Distinct from :class:`Persona` (the profile node's top-level row): it omits
    ``role_identity``, orders ``name`` before ``uuid``, and may carry an optional
    ``appearance`` (kept for foreign personas) that round-trips via ``extra``.
    """

    name: Any = _ABSENT
    uuid: Any = _ABSENT
    gender: Any = _ABSENT
    birth_date: Any = _ABSENT
    nationality: Any = _ABSENT
    language: Any = _ABSENT
    personality_traits: Any = _ABSENT
    life_experiences: Any = _ABSENT
    extra: Dict[str, Any] = field(default_factory=dict)
