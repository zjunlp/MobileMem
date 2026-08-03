"""sub_events expansion, shared by imaging nodes (event_photo / conversation / app_trace / document)."""

import os

from infra.store import read_jsonl


def load_sub_events_index(sub_events_path):
    """Load sub_events.jsonl and build an index.

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
        events: annual_events Events list
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
