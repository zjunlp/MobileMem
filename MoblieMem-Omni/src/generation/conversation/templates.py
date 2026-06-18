"""Conversation chat-template resolution + prompt loading."""
import os

from common import TEMPLATE_DIR


CHAT_TEMPLATE_FILES = {
    'wechat': 'wechat_group.html',
    'telegram': 'telegram_group.html',
    'discord': 'discord_group.html',
    'x': 'x_dm.html',
}


def load_prompt(path: str) -> str:
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def resolve_chat_template(template_name: str, language: str, nationality: str = 'Chinese') -> str:
    """Resolve a chat template name to an HTML template path.
    auto: Chinese nationality → wechat, others → x
    """
    selected = template_name
    if template_name == 'auto':
        selected = 'wechat' if nationality == 'Chinese' else 'x'

    template_file = CHAT_TEMPLATE_FILES[selected]
    return os.path.join(TEMPLATE_DIR, template_file)

def format_member_count(template_name: str, member_count: int, language: str, nationality: str = 'Chinese') -> str:
    """Format the member count for the selected chat template."""
    if template_name == 'auto':
        template_name = 'wechat' if nationality == 'Chinese' else 'x'

    if template_name == 'telegram':
        return f"{member_count} 位成员" if language == 'zh' else f"{member_count} members"
    if template_name in {'discord', 'x'}:
        return str(member_count)
    return f"({member_count})"
