"""Document generator package (ticket / money / social-feed screenshots).

Folded domain module (old ``stage7_3_tickets`` + ``stage7_3_llm_info`` +
``stage7_3_templates``) re-split into a sub-package. ``generation.document`` keeps
its full public surface via these re-exports, so the ``stage7_3_*`` shims and the
pipeline DAG (which delegates to ``generation.document.main``) are unaffected.
"""
from .templates import (
    TEMPLATES_CN, TEMPLATES_EN, _esc, _generate_avatar_data_uri,
    _generate_x_handle, _load_person_avatar_uri, fill_money_template,
    fill_ticket_template, fill_wechat_friend_template, fill_x_feed_template,
    find_event_images,
)
from .content import (
    INFO_SCHEMAS, LLM_BATCH_SIZE, LLM_SELECT_PROMPTS, _call_llm_generate_info_single,
    call_llm_generate_info, llm_select_events, select_friend_events,
)
from .generator import (
    APP_TYPES, DocumentGenerator, logger, main, render_screenshot, set_log_context,
)

__all__ = [
    "TEMPLATES_CN", "TEMPLATES_EN", "_esc", "_generate_avatar_data_uri",
    "_generate_x_handle", "_load_person_avatar_uri", "fill_money_template",
    "fill_ticket_template", "fill_wechat_friend_template", "fill_x_feed_template",
    "find_event_images",
    "INFO_SCHEMAS", "LLM_BATCH_SIZE", "LLM_SELECT_PROMPTS",
    "_call_llm_generate_info_single", "call_llm_generate_info",
    "llm_select_events", "select_friend_events",
    "APP_TYPES", "DocumentGenerator", "logger", "main", "render_screenshot",
    "set_log_context",
]
