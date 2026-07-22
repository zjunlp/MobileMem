"""Single source of truth for "is this persona Chinese?".

Historically each node re-implemented this check with different rules
(strict ``nationality == 'Chinese'`` vs substring matching vs looking at the
``language`` field), so a persona with ``nationality = "中国"`` could take the
Chinese branch in one node and the English branch in the next. Every node
must call :func:`is_chinese_persona` instead of comparing strings inline.
"""
from __future__ import annotations

from typing import Any, Optional

_CHINESE_MARKERS = ('中国', 'Chinese', 'China')
_CHINESE_LANG_CODES = ('zh', 'chinese', 'zh-cn', 'zh_cn')


def is_chinese_persona(nationality: Optional[Any] = None, language: Optional[Any] = None) -> bool:
    """Return True when either the nationality or the language marks the persona as Chinese.

    Accepts the loose values seen in real data: "Chinese", "中国", "China",
    and language codes/labels like "zh" or "Chinese". None/empty means unknown
    and never matches.
    """
    if nationality:
        s = str(nationality)
        if any(m in s for m in _CHINESE_MARKERS):
            return True
    if language:
        s = str(language).strip().lower()
        if s in _CHINESE_LANG_CODES or any(m.lower() in s for m in _CHINESE_MARKERS):
            return True
    return False
