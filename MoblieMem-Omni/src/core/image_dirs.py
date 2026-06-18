"""Canonical on-disk directory names for image artifacts (single source of truth).

Each memory-artifact *category* (the stable internal key, also used as the
record ``type`` label across the pipeline) maps to the directory written under
``image/uid{N}/``. Renaming a published dataset folder means editing this map
only; readers resolve a folder back to its category through ``CATEGORY_BY_DIR``
(e.g. :func:`generation.memory_summary.determine_image_type`).
"""

# Internal category (stable) -> published on-disk folder name.
DIR_NAME = {
    "person": "persona_reference_photos",
    "group_chat_members": "kg_reference_photos",
    "event": "camera_photos",
    "book": "book_screenshots",
    "music": "music_screenshots",
    "video": "video_screenshots",
    "ticket": "ticket_records",
    "shopping": "shopping_records",
    "money": "transaction_records",
    "group_chat": "chat_records",
    "friend": "posts",
    "scenery": "others",
}

# Published folder name -> internal category (reverse of DIR_NAME).
CATEGORY_BY_DIR = {folder: category for category, folder in DIR_NAME.items()}
