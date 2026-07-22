"""Shared prompt-file loading (L1 infra).

Replaces the per-module ``load_prompt`` copies that used to live in
``life_state``, ``timeline_dates``, ``annual_events.parse``,
``conversation.templates`` and ``social_world``.
"""
from __future__ import annotations

import os


def load_prompt(prompt_path: str) -> str:
    """Read a prompt file as UTF-8 text.

    Raises FileNotFoundError with the offending path so a missing/renamed
    prompt file is immediately diagnosable.
    """
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()
    except OSError as e:
        raise FileNotFoundError(f"Failed to load prompt file {prompt_path}: {e}") from e


def load_bilingual_prompt(prompts_dir: str, stem: str, is_chinese: bool) -> str:
    """Load ``{stem}_zh.txt`` or ``{stem}_en.txt`` from *prompts_dir*."""
    suffix = 'zh' if is_chinese else 'en'
    return load_prompt(os.path.join(prompts_dir, f'{stem}_{suffix}.txt'))
