# `generation/event_photo/` — Event Photos

Generates event scene photos that stay visually consistent with each persona
and their social contacts.

| Module | Responsibility |
|--------|----------------|
| `generator.py` | Orchestrates event-photo generation per event |
| `prompts.py` | Builds the scene and identity prompts |
| `data.py` | Loads participants, reference portraits, and avatars |
| `face_swapper.py` | Two-stage face swap (InsightFace `inswapper_128`): the protagonist is locked to the best-matching face, then the remaining faces are matched to side characters by maximum-weight assignment |
