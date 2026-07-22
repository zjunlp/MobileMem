"""Text-LLM capability (L1 backend) — stable import surface for generators.

This is the package generators should import the LLM from: ``from backends.llm
import llm_request, get_text_llm_model, ...``. The implementation lives in
``backends/llm/request.py``.
"""

from backends.llm.request import (  # noqa: F401  (re-exported public surface)
    llm_request,
    calculate_cumulative_cost,
    get_text_llm_model,
    set_log_context,
    clear_log_context,
    update_log_context,
    setup_llm_logging,
    log_llm_call,
    get_client,
    log_image_api_call,
    get_image_client,
)

__all__ = [
    "llm_request",
    "calculate_cumulative_cost",
    "get_text_llm_model",
    "set_log_context",
    "clear_log_context",
    "update_log_context",
    "setup_llm_logging",
    "log_llm_call",
    "get_client",
    "log_image_api_call",
    "get_image_client",
]
