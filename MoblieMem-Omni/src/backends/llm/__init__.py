"""Text-LLM capability (L1 backend) — stable import surface for generators.

This is the package generators should import the LLM from: ``from backends.llm import
llm_request, get_text_llm_model, ...``. For now it re-exports the existing
``llm_request`` implementation unchanged (facade-first: establish the layered import
path with zero behavior risk); a later step moves the implementation into
``backends/llm/{client,request,json_repair,cost,logging,models}.py`` and turns
``llm_request.py`` into the shim. Behavior is identical either way.
"""

from llm_request import (  # noqa: F401  (re-exported public surface)
    llm_request,
    calculate_cumulative_cost,
    get_text_llm_model,
    set_log_context,
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
    "log_llm_call",
    "get_client",
    "log_image_api_call",
    "get_image_client",
]
