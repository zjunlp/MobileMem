"""Annual-events generator package.

Re-exports the package's public surface (per-record parse / validate + the batch
runner) from the sub-modules so importers get a single stable entry point.
"""
from .parse import (
    extract_events_from_response,
    generate_events_with_llm,
    load_prompt,
    process_single_persona,
    validate_and_normalize_events,
)
from .generator import AnnualEventsGenerator, generate_annual_events, logger

__all__ = [
    "extract_events_from_response",
    "generate_events_with_llm",
    "load_prompt",
    "process_single_persona",
    "validate_and_normalize_events",
    "AnnualEventsGenerator",
    "generate_annual_events",
    "logger",
]
