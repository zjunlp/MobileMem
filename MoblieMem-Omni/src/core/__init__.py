"""Domain model (L2): pure typed data for the synthetic-persona memory dataset.

Persona / Life / Memories / Recall live here as dataclasses with lossless
dict <-> object round-trips. No I/O, no LLM, no import-time side effects.
"""

from core.base import JsonlModel, _ABSENT
from core.persona import Persona, BasicProfile
from core.life import Event, SocialGraph, SubEvent
from core.memories import GroupChat, ImageRecord
from core.recall import Stage10Summary
from core.image_dirs import DIR_NAME, CATEGORY_BY_DIR

__all__ = [
    "JsonlModel",
    "_ABSENT",
    "Persona",
    "BasicProfile",
    "Event",
    "SocialGraph",
    "SubEvent",
    "GroupChat",
    "ImageRecord",
    "Stage10Summary",
    "DIR_NAME",
    "CATEGORY_BY_DIR",
]
