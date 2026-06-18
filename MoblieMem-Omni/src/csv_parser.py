"""
CSV Parser: Utility to parse user_profile.csv files from information/ subfolders.
Extracts structured profile data for the 10-person pipeline.
"""

import csv
import os
import re
from typing import Dict, List, Optional


def parse_csv(csv_path: str) -> Dict[str, str]:
    """
    Parse a user_profile.csv file and return a dict mapping dimension -> content.
    Skips entries where content is '-' or empty.

    Supports two CSV formats:
    1. Standard: Chinese dimension/content columns.
    2. Alternative: Chinese name/value columns (e.g., young_manager).
    """
    profile = {}
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Try standard format first, then alternative format
            dim = (row.get('画像维度', '') or row.get('画像名', '')).strip()
            content = (row.get('画像内容', '') or row.get('画像值', '')).strip()
            if dim and content and content != '-':
                profile[dim] = content
    return profile


def extract_gender(profile: Dict[str, str]) -> str:
    """
    Extract gender from basic_info or baiscInfo field.
    Returns 'Male' or 'Female'.

    Checks for explicit female indicators, including mother-related terms.
    Also checks for explicit male indicators.
    """
    info = profile.get('basic_info', '') or profile.get('baiscInfo', '')

    # Female indicators (check first since some are more specific)
    female_keywords = ['宝妈', '妈妈', '母亲', '女性', '女外卖员', '女大学生',
                       '已婚女', '离异女', '单身女']
    for kw in female_keywords:
        if kw in info:
            return 'Female'

    # Check the single-character female marker, but avoid compound words
    # that do not indicate the subject's gender.
    if '女' in info and '女儿' not in info:
        return 'Female'

    # Default to Male if a male marker is found or no clear indicator exists.
    return 'Male'


def extract_age(profile: Dict[str, str]) -> Optional[int]:
    """Extract age from basic_info or baiscInfo field."""
    info = profile.get('basic_info', '') or profile.get('baiscInfo', '')
    match = re.search(r'(\d+)\s*岁', info)
    if match:
        return int(match.group(1))
    return None


def extract_birth_date(profile: Dict[str, str], reference_year: int = 2025) -> str:
    """
    Calculate approximate birth date from age in basic_info.
    Uses June 15 as approximate birthday.
    """
    age = extract_age(profile)
    if age:
        birth_year = reference_year - age
        return f"{birth_year}-06-15"
    return "1990-01-01"


def get_all_person_folders(info_dir: str) -> List[str]:
    """
    Get all person subfolders under information/, excluding zip files.
    Only includes folders that contain a user_profile.csv.
    Returns sorted list of folder names.
    """
    folders = []
    for name in sorted(os.listdir(info_dir)):
        full_path = os.path.join(info_dir, name)
        if os.path.isdir(full_path) and not name.endswith('.zip'):
            csv_path = os.path.join(full_path, 'user_profile.csv')
            if os.path.exists(csv_path):
                folders.append(name)
    return folders


def build_csv_context(profile: Dict[str, str]) -> str:
    """Build a formatted text context from all CSV data for LLM consumption."""
    lines = []
    for dim, content in profile.items():
        lines.append(f"- {dim}: {content}")
    return '\n'.join(lines)


def extract_csv_field(profile: Dict[str, str], *keys: str) -> str:
    """
    Extract a field value from the profile, trying multiple possible key names.
    Returns the first non-empty match, or empty string.
    """
    for key in keys:
        val = profile.get(key, '').strip()
        if val and val != '-':
            return val
    return ''


def build_preferences_summary(profile: Dict[str, str]) -> str:
    """
    Build a summary of preferences from various CSV fields.
    Used as context for LLM to generate structured preferences.
    """
    pref_mapping = {
        'diet': 'Food/Diet',
        'restaurants': 'Restaurants',
        'music': 'Music',
        'sport': 'Sports/Exercise',
        'game': 'Games',
        'film_television': 'Film/TV',
        'literature': 'Reading/Literature',
        'shopping': 'Shopping',
        'fashion': 'Fashion/Clothing',
        'short_travel': 'Short Travel',
        'long_travel': 'Long Travel',
        'pet': 'Pets',
        'technology': 'Technology',
        'car': 'Vehicle/Car',
        'transportation': 'Transportation',
        'art': 'Art',
        'beauty': 'Beauty',
        'entertainment': 'Entertainment',
        'photography': 'Photography',
    }

    parts = []
    for csv_key, label in pref_mapping.items():
        val = profile.get(csv_key, '').strip()
        if val and val != '-':
            parts.append(f"- {label}: {val}")

    return '\n'.join(parts) if parts else 'No specific preferences data available.'
