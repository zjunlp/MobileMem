"""Event-photo generator package (per-persona event scene images).

Re-exports the package's public surface (data / prompt / generation helpers) from
the sub-modules so importers get a single stable entry point.
"""
from .data import (
    compute_age, load_init_state_map, load_nationality_map, load_profile_map,
)
from .prompts import (
    CHINESE_EDIT_PROMPT_MAX, GPT_PROMPT_MAX,
    build_event_generation_prompt, build_identity_prompt, create_safer_prompt,
    extract_ethnicity_from_description, fit_generation_prompt, format_attempt_logs,
    generate_scene_prompt, get_prompt_limit, shorten_text,
)
from .generator import (
    CLOTHING_MAP, CLOTHING_MAP_ZH, EventPhotoGenerator, FACE_SIMILARITY_THRESHOLD,
    PORTRAITS_DIR, PROMPTS_DIR, build_person_portrait_prompt,
    cleanup_generated_images, ensure_person_portrait, expand_events_for_imaging,
    generate_event_image_for_uuid, generate_event_images, generate_person_images,
    get_appearance, get_face_threshold, get_reference_embeddings_for_uuid, logger,
    main, read_jsonl, resolve_companion_data_file, set_log_context,
    verify_face_match, write_jsonl, load_sub_events_index,
)

__all__ = [
    "compute_age", "load_init_state_map", "load_nationality_map", "load_profile_map",
    "CHINESE_EDIT_PROMPT_MAX", "GPT_PROMPT_MAX",
    "build_event_generation_prompt", "build_identity_prompt", "create_safer_prompt",
    "extract_ethnicity_from_description", "fit_generation_prompt", "format_attempt_logs",
    "generate_scene_prompt", "get_prompt_limit", "shorten_text",
    "CLOTHING_MAP", "CLOTHING_MAP_ZH", "EventPhotoGenerator", "FACE_SIMILARITY_THRESHOLD",
    "PORTRAITS_DIR", "PROMPTS_DIR", "build_person_portrait_prompt",
    "cleanup_generated_images", "ensure_person_portrait", "expand_events_for_imaging",
    "generate_event_image_for_uuid", "generate_event_images", "generate_person_images",
    "get_appearance", "get_face_threshold", "get_reference_embeddings_for_uuid", "logger",
    "main", "read_jsonl", "resolve_companion_data_file", "set_log_context",
    "verify_face_match", "write_jsonl", "load_sub_events_index",
]
