"""App-trace generator package (book / music / video / shopping app screenshots).

Folded domain module re-split into a sub-package. ``generation.app_trace`` keeps
its full public surface via these re-exports, so existing importers and the old
``stage7_2_*`` shims are unaffected.
"""
from .templates import (
    TEMPLATES_CN, TEMPLATES_EN, _esc, _load_template, _persona_phones,
    fill_book_template, fill_music_template, fill_shopping_template,
    fill_template, fill_video_template,
)
from .checkpoint import (
    _ckpt_path, clear_checkpoint, load_checkpoint, save_checkpoint,
)
from .events import assign_all_events_to_types, select_events_for_type
from .covers import COVER_API_URL, _make_fallback_cover_b64, generate_video_cover_b64
from .content import (
    INFO_SCHEMAS, _call_llm_generate_info, _call_llm_generate_info_single,
    _compute_publish_date,
)
from .generator import (
    APP_TYPE_CN, APP_TYPE_EN, APP_TYPES, AppTraceGenerator, logger,
    main, process_persona, read_jsonl, render_screenshots, render_single_sync,
    set_log_context, write_jsonl,
)

__all__ = [
    "TEMPLATES_CN", "TEMPLATES_EN", "_esc", "_load_template", "_persona_phones",
    "fill_book_template", "fill_music_template", "fill_shopping_template",
    "fill_template", "fill_video_template",
    "_ckpt_path", "clear_checkpoint", "load_checkpoint", "save_checkpoint",
    "assign_all_events_to_types", "select_events_for_type",
    "COVER_API_URL", "_make_fallback_cover_b64", "generate_video_cover_b64",
    "INFO_SCHEMAS", "_call_llm_generate_info", "_call_llm_generate_info_single",
    "_compute_publish_date",
    "APP_TYPE_CN", "APP_TYPE_EN", "APP_TYPES", "AppTraceGenerator", "logger",
    "main", "process_persona", "render_screenshots", "render_single_sync",
    "read_jsonl", "write_jsonl", "set_log_context",
]
