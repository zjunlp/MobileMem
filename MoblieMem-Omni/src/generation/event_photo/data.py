"""Event-photo persona data loaders (profiles / init-states / nationality / age)."""
import logging
import os
from typing import Dict, Optional

import jsonlines

from common import read_jsonl

logger = logging.getLogger('fix_event_images')


def load_profile_map(profiles_file: str) -> Dict[int, Dict]:
    """Load stage1 basic profiles keyed by uuid."""
    records = read_jsonl(profiles_file)
    profile_map = {}
    for record in records:
        uuid = record.get('uuid')
        if uuid is not None:
            profile_map[uuid] = record
    return profile_map

def load_init_state_map(init_states_file: str) -> Dict[int, Dict]:
    """Load stage2 init states keyed by uuid."""
    records = read_jsonl(init_states_file)
    state_map = {}
    for record in records:
        uuid = record.get('uuid')
        if uuid is not None:
            state_map[uuid] = record
    return state_map

def load_nationality_map(profiles_file: str) -> Dict[int, str]:
    """
    Load basic_profiles.jsonl and return a uuid -> nationality mapping.
    """
    if not os.path.exists(profiles_file):
        logger.warning(f"Profiles file not found: {profiles_file}")
        return {}

    nationality_map = {}
    try:
        with jsonlines.open(profiles_file, 'r') as reader:
            for record in reader:
                uuid = record.get('uuid')
                nationality = record.get('nationality')
                if uuid is not None and nationality is not None:
                    nationality_map[uuid] = nationality
        logger.info(f"Loaded nationality map from {profiles_file}: {len(nationality_map)} records")
    except Exception as e:
        logger.error(f"Error loading nationality map: {e}")

    return nationality_map

def compute_age(birth_date: str) -> Optional[int]:
    if not birth_date:
        return None
    try:
        from datetime import datetime
        birth = datetime.strptime(birth_date, "%Y-%m-%d")
        today = datetime.now()
        return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
    except Exception:
        return None
