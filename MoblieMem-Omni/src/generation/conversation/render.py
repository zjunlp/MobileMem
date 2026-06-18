"""Conversation chat-UI HTML rendering + avatar path resolution + filename sanitize."""
import base64
import hashlib
import logging
import os
import re
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from .templates import format_member_count

logger = logging.getLogger('stage7')


WINDOWS_FILENAME_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename_component(value: str) -> str:
    """Make a string safe for use as a Windows filename component."""
    cleaned = WINDOWS_FILENAME_FORBIDDEN.sub('_', (value or '').strip())
    cleaned = cleaned.rstrip(' .')
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned or 'unknown'


NAME_TO_PINYIN = {
    '妈妈': 'mama',
    '爸爸': 'baba',
    '小张': 'xiaozhang',
    '小李': 'xiaoli',
    '小王': 'xiaowang',
    '张经理': 'zhangjingli',
    '李同事': 'litongshi',
    '王同事': 'wangtongshi',
    '赵同事': 'zhaotongshi',
    '陈同事': 'chentongshi',
}

def image_to_data_uri(image_path: str) -> Optional[str]:
    """Return a file:// URI for a local image so that Chrome can load it directly.

    The old implementation read the full image into bytes and embedded it as
    base64 in HTML, making BeautifulSoup spike memory during `str(soup)` (MBs
    per HTML file, then OOM under concurrency). Returning a `file:///...` URI
    keeps HTML in KBs while Chrome loads the image from disk with identical
    rendering output.
    """
    if not image_path or not os.path.exists(image_path):
        return None
    try:
        from pathlib import Path
        return Path(image_path).resolve().as_uri()
    except Exception as exc:
        logger.debug(f"Failed to build file URI for {image_path}: {exc}")
        return None

def normalize_group_chat_messages(messages: List[Dict], members: List[str], main_person_name: str) -> List[Dict]:
    """Map LLM-generated senders back to known group members for stable avatar lookup.
    
    Strict matching: assign only exact group-member names or reliable fuzzy
    matches. Random assignment is forbidden because it can pair one person's
    name with another person's avatar.
    """
    normalized = []
    left_members = [member for member in members if member != main_person_name]
    sender_map: Dict[str, str] = {}

    for msg in messages:
        message = dict(msg)
        side = message.get('side', 'left')
        sender = str(message.get('sender', '')).strip()

        if side == 'right':
            if main_person_name:
                message['sender'] = main_person_name
            normalized.append(message)
            continue

        # 1. Exact match.
        if sender in left_members:
            message['sender'] = sender
            sender_map.setdefault(sender, sender)
            normalized.append(message)
            continue

        # 2. Existing mapping.
        if sender in sender_map:
            message['sender'] = sender_map[sender]
            normalized.append(message)
            continue

        # 3. Substring match: sender contains a member name, or a member name contains sender.
        substring_match = None
        for member in left_members:
            # Sender contains a member's full name.
            if member in sender and len(member) >= 2:
                substring_match = member
                break
            # A member's full name contains sender.
            if sender in member and len(sender) >= 2:
                substring_match = member
                break

        if substring_match:
            sender_map[sender] = substring_match
            message['sender'] = substring_match
            normalized.append(message)
            continue

        # 4. If no match is possible, keep the LLM's original sender name.
        # Do not randomly assign an unused member, which can pair the wrong avatar with a name.
        logger.warning(f"normalize_group_chat_messages: sender '{sender}' not in members {left_members}, keeping as-is")
        normalized.append(message)

    return normalized


def find_person_avatar_path(person_image_dir: str, uuid: int) -> Optional[str]:
    """Return the protagonist avatar path for a persona UUID."""
    if not os.path.exists(person_image_dir):
        return None
    for fname in sorted(os.listdir(person_image_dir)):
        if fname.startswith(f"{uuid}_person_") and fname.endswith('.png'):
            return os.path.join(person_image_dir, fname)
    return None

def find_member_avatar_path(member_avatar_dir: str, sender_name: str, uuid: int = None) -> Optional[str]:
    """Return a group member avatar path by matching sender name in *_avatar.png files."""
    if not sender_name or not os.path.exists(member_avatar_dir):
        return None

    safe_sender_name = sanitize_filename_component(sender_name)
    exact_suffixes = [f"_{safe_sender_name}_avatar.png"]
    direct_names = [f"{safe_sender_name}_avatar.png"]
    if safe_sender_name != sender_name:
        exact_suffixes.append(f"_{sender_name}_avatar.png")
        direct_names.append(f"{sender_name}_avatar.png")
    pinyin = NAME_TO_PINYIN.get(sender_name)

    for fname in sorted(os.listdir(member_avatar_dir)):
        if not fname.endswith('.png'):
            continue
        if fname in direct_names or any(fname.endswith(suffix) for suffix in exact_suffixes):
            return os.path.join(member_avatar_dir, fname)
        if pinyin and fname == f"member_{pinyin}.png":
            return os.path.join(member_avatar_dir, fname)

    return None

def _generate_unique_placeholder_avatar(sender_name: str) -> str:
    """Generate a name-hash-based SVG placeholder avatar as a data URI."""
    h = hashlib.md5(sender_name.encode('utf-8')).hexdigest()
    # Use different hash parts to generate a soft background color.
    hue = int(h[:3], 16) % 360
    bg_color = f"hsl({hue}, 55%, 65%)"
    # Use the last one or two characters of the name as display text.
    display_char = sender_name[-2:] if len(sender_name) >= 2 else sender_name
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80">'
        f'<rect width="80" height="80" rx="8" fill="{bg_color}"/>'
        f'<text x="40" y="48" text-anchor="middle" fill="white" '
        f'font-size="28" font-family="sans-serif" font-weight="bold">{display_char}</text>'
        f'</svg>'
    )
    encoded = base64.b64encode(svg.encode('utf-8')).decode('utf-8')
    return f"data:image/svg+xml;base64,{encoded}"


def render_group_chat_html(
    group_data: Dict, group_spec: Dict, template_path: str,
    language: str, person_image_dir: str, member_avatar_dir: str, uuid: int,
    template_name: str, nationality: str = 'Chinese'
) -> str:
    """Fill the wechat_group.html template with group chat data."""
    with open(template_path, 'r', encoding='utf-8') as f:
        html_content = f.read()

    soup = BeautifulSoup(html_content, 'html.parser')

    # Update group name
    group_name_el = soup.find(id='groupName')
    if group_name_el:
        group_name_el.string = group_data.get('group_name', group_spec['group_name'])

    member_count_el = soup.find(id='memberCount')
    if member_count_el:
        # Use the actual member-list length to avoid stale member_count cache mismatches.
        actual_member_count = len(group_spec.get('members', []))
        member_count_el.string = format_member_count(template_name, actual_member_count, language, nationality)

    person_avatar_uri = image_to_data_uri(find_person_avatar_path(person_image_dir, uuid))
    placeholder_avatar_uri = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACgAAAAoCAYAAACM/rhtAAAAOklEQVR42u3OQQ0AAAgDINc/9Mzg0xMEtJJ2aqnqQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEDgvwcMjAABHbfuVAAAAABJRU5ErkJggg=="

    # Collect unique left-side senders in order of appearance
    left_senders_ordered = []
    for msg in group_data.get('messages', []):
        if msg.get('side', 'left') == 'left':
            s = msg.get('sender', '')
            if s and s not in left_senders_ordered:
                left_senders_ordered.append(s)

    # Map each sender to an avatar: exact match only, no round-robin reuse
    sender_avatar_map: Dict[str, Optional[str]] = {}
    for sender in left_senders_ordered:
        exact = image_to_data_uri(find_member_avatar_path(member_avatar_dir, sender, uuid))
        if exact:
            sender_avatar_map[sender] = exact
        else:
            # Generate a unique name-based colored placeholder avatar.
            sender_avatar_map[sender] = _generate_unique_placeholder_avatar(sender)

    # Fill messages
    chat_container = soup.find(id='chatContainer')
    if chat_container:
        chat_container.clear()
        messages = group_data.get('messages', [])

        for msg_idx, msg in enumerate(messages):
            side = msg.get('side', 'left')
            sender = msg.get('sender', '')
            text = msg.get('content', '') or msg.get('text', '')

            msg_row = soup.new_tag('div', **{'class': f'message-row {side}',
                                              'id': f'msg-{msg_idx}'})

            # Avatar
            avatar_img = soup.new_tag('img', **{'class': 'avatar', 'alt': sender})
            if side == 'right':
                avatar_uri = person_avatar_uri
            else:
                avatar_uri = sender_avatar_map.get(sender)
            avatar_img['src'] = avatar_uri or placeholder_avatar_uri

            # Message content div
            msg_content = soup.new_tag('div', **{'class': 'message-content'})

            # Sender name (only for left messages)
            if side == 'left':
                name_div = soup.new_tag('div', **{'class': 'sender-name'})
                name_div.string = sender
                msg_content.append(name_div)

            # Bubble
            bubble = soup.new_tag('div', **{'class': 'bubble'})
            bubble.string = text
            msg_content.append(bubble)

            msg_row.append(avatar_img)
            msg_row.append(msg_content)
            chat_container.append(msg_row)

    # Inject JS marker script: place 3px-wide color markers at each message for post-render position extraction.
    marker_script = soup.new_tag('script')
    marker_script.string = """
    window.addEventListener('load', function() {
        var msgs = document.querySelectorAll('[id^="msg-"]');
        msgs.forEach(function(el) {
            var idx = parseInt(el.id.split('-')[1]);
            var rect = el.getBoundingClientRect();
            var m = document.createElement('div');
            var g = (idx % 128) * 2;
            var b = Math.floor(idx / 128) * 2;
            m.style.cssText = 'position:absolute;left:0;top:'+Math.round(rect.top)+'px;width:3px;height:1px;background:rgb(254,'+g+','+b+');z-index:99999;pointer-events:none';
            document.body.appendChild(m);
        });
    });
    """
    soup.body.append(marker_script)

    return str(soup)
