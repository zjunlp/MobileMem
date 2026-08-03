# `generation/app_trace/` — App Screenshots

Generates mobile-app screenshots (book, music, video, shopping, ticket,
payment, …) by filling HTML templates and rendering them to images.

| Module | Responsibility |
|--------|----------------|
| `generator.py` | Orchestrates app-screenshot generation per event |
| `events.py` | Selects which events become app traces |
| `content.py` | Produces the per-app content fields via the LLM |
| `covers.py` | Cover images for media apps |
| `templates.py` | Maps a category to its HTML template and fields |
| `checkpoint.py` | Resume / checkpoint helpers |
