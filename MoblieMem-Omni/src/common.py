"""
Shared utilities: JSONL I/O, checkpoint management, event expansion, logging.

This module is a thin convenience layer over the infrastructure below it, so
existing pipeline scripts keep importing familiar names from ``common``:

- Path constants (``PROJECT_ROOT`` ... ``LOG_DIR``) and ``.env`` loading are
  owned by :mod:`config`, the single source of truth for configuration. They are
  re-exported here only for backward compatibility.
- JSONL read/write and checkpoint helpers are owned by :mod:`infra.store`, the
  single data-access layer, and are likewise re-exported.

The only logic that still lives here is what has no better home yet: sub-event
expansion (used by the imaging stages) and the standard logger factory.
"""

import os
import logging

# Path constants come from config (single source of truth; it also loads .env
# and configures the console/proxy). Re-exported so ``from common import
# OUTPUT_DIR``-style callers stay unchanged. No second load_dotenv / sys.path
# bootstrap here: importing this module already proves ``src`` is importable, so
# ``config`` and ``infra`` resolve without help.
from config import (
    PROJECT_ROOT,
    SRC_DIR,
    PROMPTS_DIR,
    TEMPLATE_DIR,
    OUTPUT_DIR,
    LOG_DIR,
)

# JSONL I/O + checkpoint: canonical implementation in ``infra.store``,
# re-exported so existing ``from common import read_jsonl``-style callers keep
# working unchanged while the logic lives in one place.
from infra.store import (
    read_jsonl,
    write_jsonl,
    append_jsonl,
    load_existing_by_role,
    load_existing_by_uuid,
    make_save_callback,
    index_by,
    JsonlStore,
)

__all__ = [
    # Re-exported from config (single source of truth)
    "PROJECT_ROOT",
    "SRC_DIR",
    "PROMPTS_DIR",
    "TEMPLATE_DIR",
    "OUTPUT_DIR",
    "LOG_DIR",
    # Re-exported from infra.store
    "read_jsonl",
    "write_jsonl",
    "append_jsonl",
    "load_existing_by_role",
    "load_existing_by_uuid",
    "make_save_callback",
    "index_by",
    "JsonlStore",
    # Defined in this module
    "load_sub_events_index",
    "expand_events_for_imaging",
    "setup_logger",
]


# ============================================================================
# Event expansion (stage 4.5 sub-event integration)
# ============================================================================

def load_sub_events_index(sub_events_path):
    """Load stage4_5_sub_events.jsonl and build an index.

    Returns:
        dict: {(uuid, parent_event_id): [children_list]}
    """
    if not os.path.exists(sub_events_path):
        return {}
    records = read_jsonl(sub_events_path)
    index = {}
    for rec in records:
        uid = rec['uuid']
        for group in rec.get('sub_events', []):
            parent_id = group['parent_event_id']
            index[(uid, parent_id)] = group['children']
    return index


def expand_events_for_imaging(uuid, events, sub_events_index):
    """Expand a single user's event list: keep short-term events, replace mid/long-term ones with sub-events.

    Args:
        uuid: user ID
        events: stage4 Events list
        sub_events_index: index returned by load_sub_events_index()

    Returns:
        list of (image_id, event_dict):
            - short-term: image_id = event_id (int)
            - sub-event:  image_id = sub_event_id (str, e.g. "4_1")
    """
    result = []
    for event in events:
        if event.get('duration_type') == 'short-term':
            result.append((event['event_id'], event))
        else:
            children = sub_events_index.get((uuid, event['event_id']), [])
            if children:
                for child in children:
                    if child.get('is_intro'):
                        continue  # skip recall/intro sub-events
                    result.append((child['sub_event_id'], child))
            else:
                # no sub-events, keep the original event
                result.append((event['event_id'], event))
    return result


# ============================================================================
# Logging
# ============================================================================

def setup_logger(name, log_file=None, level=logging.INFO):
    """Create a standard logger."""
    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if not logger.handlers:
        fmt = logging.Formatter('%(asctime)s [%(name)s] %(levelname)s: %(message)s')
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(sh)
        if log_file:
            fh = logging.FileHandler(os.path.join(LOG_DIR, log_file), encoding='utf-8')
            fh.setFormatter(fmt)
            logger.addHandler(fh)
    return logger
