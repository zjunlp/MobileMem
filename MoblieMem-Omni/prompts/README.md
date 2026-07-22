# `prompts/` — Generation Prompts

Prompt templates for the generation stages, in Chinese (`*_zh`) and English
(`*_en`) where the persona's language matters. Free-text persona fields are
written in the persona's own language, so the Chinese prompts are kept in
Chinese on purpose.

Templates are loaded at runtime by the generators via
`infra.prompts.load_prompt` / `load_bilingual_prompt` (path configured through
`config.PROMPTS_DIR`, overridable with `--prompts-dir`). Language selection is
done with `core.lang.is_chinese_persona`.

| Prompt pair (`*_zh` / `*_en`) | Used by stage |
|-------------------------------|---------------|
| `init_state_nation_*`, `extra_instruction_*` | `life_state` (Init_State) |
| `fix_relationship_names_*` | `social_name_fix` (Stage 2.1) |
| `important_dates_*` | `timeline_dates` |
| `social_graph_*` | `social_world` |
| `annual_events_*` | `annual_events` |
| `group_chat_*` | `conversation` |
| `image_person_portrait_*`, `image_member_avatar_*` | `event_photo` / `conversation` avatars |
| `image_summary_*` | `memory_summary` (per-image captions) |
