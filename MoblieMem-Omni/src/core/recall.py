"""Recall domain types: image summaries (L2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from core.base import JsonlModel, _ABSENT


@dataclass
class Stage10Summary(JsonlModel):
    """A stage10 image-summary row (bilingual summary + success flag).

    ``error`` (present only on failure) round-trips via ``extra``.
    """

    image_path: Any = _ABSENT
    filename: Any = _ABSENT
    uuid: Any = _ABSENT
    image_type: Any = _ABSENT
    nationality: Any = _ABSENT
    summary_zh: Any = _ABSENT
    summary_en: Any = _ABSENT
    success: Any = _ABSENT
    extra: Dict[str, Any] = field(default_factory=dict)
