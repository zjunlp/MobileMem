# `generation/conversation/` — Group-Chat Screenshots

Generates multi-party group-chat screenshots for events.

| Module | Responsibility |
|--------|----------------|
| `generator.py` | Orchestrates chat generation per event |
| `content.py` | Produces the chat messages via the LLM |
| `avatars.py` | Resolves group-member avatars |
| `render.py` | Builds the chat DOM from the messages |
| `screenshot.py` | Renders the HTML to an image |
| `templates.py` | Chat HTML templates (WeChat / Telegram / Discord / …) |
