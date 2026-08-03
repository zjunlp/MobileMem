"""Conversation generator package (per-event group-chat screenshots).

Re-exports the package's public surface (templates / screenshot / content /
avatar helpers) from the sub-modules so importers get a single stable entry point.
"""
from .templates import (
    CHAT_TEMPLATE_FILES, format_member_count, load_prompt, resolve_chat_template,
)
from .screenshot import (
    HTML_RENDER_LOCK, _find_chrome, html_to_multi_png, html_to_png,
)
from .render import (
    NAME_TO_PINYIN, WINDOWS_FILENAME_FORBIDDEN, _generate_unique_placeholder_avatar,
    find_member_avatar_path, find_person_avatar_path, image_to_data_uri,
    normalize_group_chat_messages, render_group_chat_html, sanitize_filename_component,
)
from .content import (
    _build_member_persona_text, _collect_all_social_members, _format_social_members_for_prompt,
    build_group_specs, generate_group_chat_content, select_group_members_by_llm,
)
from .avatars import (
    _cleanup_member_avatar_dir, _load_uuid_member_avatars, build_member_avatar_filename,
    build_member_avatar_prompt, build_persona_source_signature, ensure_member_avatars,
)
from .generator import (
    ConversationGenerator, GroupChat, ensure_person_portrait, load_init_state_map,
    logger, main, process_persona, set_log_context, setup_logging,
)

__all__ = [
    "CHAT_TEMPLATE_FILES", "format_member_count", "load_prompt", "resolve_chat_template",
    "HTML_RENDER_LOCK", "_find_chrome", "html_to_multi_png", "html_to_png",
    "NAME_TO_PINYIN", "WINDOWS_FILENAME_FORBIDDEN", "_generate_unique_placeholder_avatar",
    "find_member_avatar_path", "find_person_avatar_path", "image_to_data_uri",
    "normalize_group_chat_messages", "render_group_chat_html", "sanitize_filename_component",
    "_build_member_persona_text", "_collect_all_social_members", "_format_social_members_for_prompt",
    "build_group_specs", "generate_group_chat_content", "select_group_members_by_llm",
    "_cleanup_member_avatar_dir", "_load_uuid_member_avatars", "build_member_avatar_filename",
    "build_member_avatar_prompt", "build_persona_source_signature", "ensure_member_avatars",
    "ConversationGenerator", "GroupChat", "ensure_person_portrait", "load_init_state_map",
    "logger", "main", "process_persona", "set_log_context", "setup_logging",
]
