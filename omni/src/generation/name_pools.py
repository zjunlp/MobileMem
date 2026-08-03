"""Shared name pools + unique-name fallback generation.

Previously duplicated (and slightly diverged) between ``life_state`` and
``social_world``; this module is now the single source for both.
"""
from __future__ import annotations

import itertools

SURNAME_POOL = [
    '宋', '徐', '韩', '冯', '曹', '魏', '程', '苏', '叶', '卢',
    '贺', '龚', '潘', '顾', '史', '方', '邓', '武', '钱', '唐',
]
GIVEN_POOL = [
    '昊', '晨', '睿', '泽', '皓', '帆', '峰', '洋', '凯', '博',
    '婷', '颖', '琳', '燕', '霞', '洁', '娜', '雯', '莹', '璐',
]
EN_FIRST_POOL = [
    'James', 'Robert', 'Michael', 'David', 'Richard', 'Joseph', 'Thomas', 'William',
    'Sarah', 'Emily', 'Jessica', 'Hannah', 'Rachel', 'Lauren', 'Megan', 'Olivia',
]
EN_LAST_POOL = [
    'Smith', 'Johnson', 'Brown', 'Davis', 'Wilson', 'Anderson', 'Taylor', 'Thomas',
    'Harris', 'Clark', 'Lewis', 'Walker', 'Hall', 'Young', 'King', 'Wright',
]


def make_unique_name(existing: set, surname: str = '', is_chinese: bool = True) -> str:
    """Generate a name not in *existing*, optionally with a given surname."""
    if is_chinese:
        # If a surname is specified, prefer combinations with that surname
        if surname:
            for g in GIVEN_POOL:
                candidate = surname + g
                if candidate not in existing:
                    return candidate
        for s, g in itertools.product(SURNAME_POOL, GIVEN_POOL):
            candidate = s + g
            if candidate not in existing:
                return candidate
        base = SURNAME_POOL[0] + GIVEN_POOL[0]
        i = 2
        while f"{base}{i}" in existing:
            i += 1
        return f"{base}{i}"
    else:
        if surname:
            for f in EN_FIRST_POOL:
                candidate = f"{f} {surname}"
                if candidate not in existing:
                    return candidate
        for f, last in itertools.product(EN_FIRST_POOL, EN_LAST_POOL):
            candidate = f"{f} {last}"
            if candidate not in existing:
                return candidate
        base = f"{EN_FIRST_POOL[0]} {EN_LAST_POOL[0]}"
        i = 2
        while f"{base} {i}" in existing:
            i += 1
        return f"{base} {i}"
