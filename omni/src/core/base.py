"""Lossless dict <-> model round-trip base for the domain types (L2).

``JsonlModel`` gives every dataclass model a declared-fields + ``extra`` passthrough
round-trip: ``Model.from_dict(x).to_dict() == x`` for any real record, including rows
that omit optional keys. Pure data: no I/O, no LLM, no import-time side effects.
"""

from __future__ import annotations

from dataclasses import fields
from typing import Any, Dict, List, Type, TypeVar

# Sentinel meaning "this declared field was absent from the source record", so a
# model can round-trip a record that omits some known keys without inventing
# them. Kept distinct from ``None`` (a legitimate value) and ``dataclasses.MISSING``.
_ABSENT: Any = object()

T = TypeVar("T", bound="JsonlModel")


class JsonlModel:
    """Mixin giving dataclass models a lossless ``dict`` <-> model round-trip.

    Subclasses are ``@dataclass`` types that declare their known fields (each
    defaulting to ``_ABSENT``) plus a final ``extra: Dict[str, Any]`` field.
    """

    extra: Dict[str, Any]

    @classmethod
    def _declared(cls) -> List[str]:
        """Declared field names in definition order, excluding ``extra``."""
        return [f.name for f in fields(cls) if f.name != "extra"]

    @classmethod
    def from_dict(cls: Type[T], data: Dict[str, Any]) -> T:
        """Build a model from a record, preserving unknown keys in ``extra``."""
        rest = dict(data)
        known: Dict[str, Any] = {}
        for name in cls._declared():
            if name in rest:
                known[name] = rest.pop(name)
        return cls(**known, extra=rest)

    def to_dict(self) -> Dict[str, Any]:
        """Reconstruct the original mapping exactly (absent fields omitted)."""
        out: Dict[str, Any] = {}
        for name in self._declared():
            value = getattr(self, name)
            if value is not _ABSENT:
                out[name] = value
        out.update(self.extra)
        return out
