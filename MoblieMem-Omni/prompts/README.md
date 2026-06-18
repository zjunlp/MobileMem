# `prompts/` — Generation Prompts

Prompt templates for the generation stages, in Chinese (`*_zh` / `*_cn`) and
English (`*_en`) where the persona's language matters. Free-text persona fields
are written in the persona's own language, so the Chinese prompts are kept in
Chinese on purpose.

Templates are loaded at runtime by the generators (path configured via
`config.PROMPTS_DIR`) and grouped by stage, for example:

- `stage1_basic_profiles*` — persona basic profile
- `stage2_*` — life state
- `stage3_*` — important dates and social graph
- `stage4_annual_events*` — annual events
- `stage7_group_chat*` — group-chat content
- `image_person_portrait*`, `image_member_avatar*` — image prompts
- `stage10_image_summary*` — per-image memory summary
