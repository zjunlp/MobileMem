"""Document HTML template filling (ticket / money / WeChat-friend / X-feed).

Template path maps plus the per-type ``fill_*`` builders and the small avatar /
event-image helpers they use.
"""
import base64
import hashlib
import html as html_module
import json
import os
import random
import re
from datetime import datetime

from common import TEMPLATE_DIR
from core import DIR_NAME

# --- Template paths ---
TEMPLATES_CN = {
    "ticket": os.path.join(TEMPLATE_DIR, '\u706b\u8f66\u7968.html'),
    "money": os.path.join(TEMPLATE_DIR, '\u5fae\u4fe1\u8f6c\u8d26.html'),
    "friend": os.path.join(TEMPLATE_DIR, 'friend.html'),
}
TEMPLATES_EN = {
    "ticket": os.path.join(TEMPLATE_DIR, 'TrainTicket.html'),
    "money": os.path.join(TEMPLATE_DIR, 'PaymentTransfer.html'),
    "friend": os.path.join(TEMPLATE_DIR, 'twitter_feed.html'),
}


def _esc(s):
    return html_module.escape(str(s)) if s else ''


def fill_ticket_template(template, info, passenger_name="", is_cn=True, id_last4=None):
    dep_station = info.get("departure_station", "北京南" if is_cn else "London")
    arr_station = info.get("arrival_station", "上海虹桥" if is_cn else "Manchester")
    dep_time = info.get("departure_time", "08:30")
    travel_date = info.get("travel_date", "2025-04-15")
    train_number = info.get("train_number", "G1")
    seat_type = info.get("seat_type", "二等座" if is_cn else "Standard")
    seat_number = info.get("seat_number", "05车12A" if is_cn else "Car 5 Seat 42A")
    price = info.get("price", 553.0)
    pax_name = info.get("passenger_name", passenger_name or ("旅客" if is_cn else "Passenger"))

    # ID last-4 digits: reuse if passed in, otherwise generate randomly
    if id_last4 is None:
        id_last4 = f"****{random.randint(1000, 9999)}"
    order_number = f"E{''.join(str(random.randint(0,9)) for _ in range(9))}"

    # Generate a real QR code
    try:
        import qrcode
        import io
        import base64 as b64_mod
        qr = qrcode.QRCode(version=2, box_size=4, border=1)
        qr.add_data(f"https://12306.cn/otn/order/{order_number}")
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qr_b64 = b64_mod.b64encode(buf.getvalue()).decode('ascii')
    except Exception:
        qr_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

    if is_cn:
        replacements = {
            "{{departure_station}}": _esc(dep_station),
            "{{arrival_station}}": _esc(arr_station),
            "{{departure_time}}": _esc(dep_time),
            "{{travel_date}}": _esc(travel_date),
            "{{train_number}}": _esc(train_number),
            "{{seat_type}}": _esc(seat_type),
            "{{seat_number}}": _esc(seat_number),
            "{{price}}": str(price),
            "{{passenger_name}}": _esc(pax_name),
            "{{passenger_id_last4}}": id_last4,
            "{{order_number}}": order_number,
            "{{qr_code_base64}}": qr_b64,
        }
    else:
        if isinstance(price, (int, float)):
            price_usd = float(price)
        else:
            try:
                cleaned = re.sub(r'[^\d.]', '', str(price))
                price_usd = float(cleaned) if cleaned else 0.0
            except (ValueError, TypeError):
                price_usd = 0.0
        replacements = {
            "{{departure_station_en}}": _esc(dep_station),
            "{{arrival_station_en}}": _esc(arr_station),
            "{{departure_time}}": _esc(dep_time),
            "{{travel_date}}": _esc(travel_date),
            "{{train_number}}": _esc(train_number),
            "{{seat_type}}": _esc(seat_type),
            "{{seat_number}}": _esc(seat_number),
            "{{price_usd}}": f"{price_usd:.2f}",
            "{{passenger_name}}": _esc(pax_name),
            "{{passenger_id_last4}}": id_last4,
            "{{order_number}}": order_number,
            "{{qr_code_base64}}": qr_b64,
        }

    result = template
    for k, v in replacements.items():
        result = result.replace(k, v)
    return result

def fill_money_template(template, info, is_cn=True):
    amount = info.get("amount", 100.0)
    if isinstance(amount, (int, float)):
        amount_str = f"{amount:.2f}"
    else:
        amount_str = str(amount)
    recipient = info.get("recipient_name", "好友" if is_cn else "Friend")
    desc = info.get("description", "转账" if is_cn else "Transfer")
    transfer_time = info.get("transfer_time", datetime.now().strftime("%Y-%m-%d %H:%M"))
    status = info.get("status", "已收款" if is_cn else "Received")
    payment_method = info.get("payment_method", "零钱" if is_cn else "Bank Account")

    # Transaction ID
    txn_id = ''.join(str(random.randint(0, 9)) for _ in range(28))

    replacements = {
        "{{amount}}": amount_str,
        "{{recipient_name}}": _esc(recipient),
        "{{description}}": _esc(desc),
        "{{transfer_time}}": _esc(str(transfer_time)),
        "{{status}}": _esc(status),
        "{{payment_method}}": _esc(payment_method),
        "{{transaction_id}}": txn_id,
    }

    result = template
    for k, v in replacements.items():
        result = result.replace(k, v)
    return result

def _generate_avatar_data_uri(name: str) -> str:
    """Generate a colored SVG placeholder avatar based on the name hash; returns a data URI."""
    char = name[-1] if name else '?'
    h = int(hashlib.md5(name.encode('utf-8')).hexdigest()[:6], 16) % 360
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="88" height="88">'
        f'<rect width="88" height="88" rx="6" fill="hsl({h},55%,50%)"/>'
        f'<text x="44" y="44" text-anchor="middle" dominant-baseline="central" '
        f'fill="#fff" font-size="40" font-family="sans-serif">{char}</text></svg>'
    )
    b64 = base64.b64encode(svg.encode('utf-8')).decode()
    return f"data:image/svg+xml;base64,{b64}"

def _load_person_avatar_uri(uid: int, image_base_dir: str) -> str:
    """Load the protagonist avatar and convert it to a data URI; returns None if not found."""
    for person_dir in [
        os.path.join(image_base_dir, f"uid{uid}", DIR_NAME["person"]),
    ]:
        if not os.path.isdir(person_dir):
            continue
        for fname in sorted(os.listdir(person_dir)):
            if fname.endswith('.png') and 'person' in fname:
                fpath = os.path.join(person_dir, fname)
                try:
                    with open(fpath, 'rb') as f:
                        b64 = base64.b64encode(f.read()).decode()
                    return f"data:image/png;base64,{b64}"
                except Exception:
                    pass
    return None

def find_event_images(uid, event_id, image_base_dir):
    """Find all images associated with the event; returns a list of base64 data URIs."""
    uid_dir = os.path.join(image_base_dir, f"uid{uid}")
    if not os.path.isdir(uid_dir):
        return []

    images = []
    # Only match files of the form {uid}_{type}_{event_id}.png
    import re
    pattern = re.compile(rf"^\d+_\w+_{event_id}\.png$")
    for sub in os.listdir(uid_dir):
        sub_path = os.path.join(uid_dir, sub)
        if not os.path.isdir(sub_path):
            continue
        # Only use event images; other types (tickets, transfers, etc.) are not suitable for the social feed
        if sub != "event":
            continue
        for fname in os.listdir(sub_path):
            if pattern.match(fname):
                fpath = os.path.join(sub_path, fname)
                try:
                    with open(fpath, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode()
                    images.append(f"data:image/png;base64,{b64}")
                except Exception:
                    pass
    return images[:9]  # social feed shows at most 9 images

def fill_wechat_friend_template(template, friend_info, poster_name, image_data_uris=None, avatar_data_uri=None):
    post_text = friend_info.get('post_text', '')
    post_time = friend_info.get('post_time', '1小时前')
    likes = friend_info.get('likes', [])
    comments = friend_info.get('comments', [])

    avatar_text = poster_name[-1] if poster_name else '?'
    # If there is no real avatar, generate a name-based colored SVG placeholder
    if not avatar_data_uri:
        avatar_data_uri = _generate_avatar_data_uri(poster_name)
    # Use real images if available, otherwise random placeholders
    if image_data_uris:
        image_count = len(image_data_uris)
    else:
        image_count = random.choice([0, 0, 1, 1, 3, 3, 6, 9])
    like_names = '，'.join(likes) if likes else ''
    safe_comments = []
    for c in comments:
        safe_comments.append({
            'name': _esc(c.get('name', '')),
            'text': _esc(c.get('text', '') or c.get('content', ''))
        })
    comments_json = json.dumps(safe_comments, ensure_ascii=False)

    # Pass the list of image data URIs into the template
    images_json = json.dumps(image_data_uris or [], ensure_ascii=False)

    replacements = {
        '{{POSTER_NAME}}': _esc(poster_name),
        '{{POSTER_AVATAR_TEXT}}': _esc(avatar_text),
        '{{POSTER_AVATAR_SRC}}': avatar_data_uri,
        '{{POST_TEXT}}': _esc(post_text),
        '{{POST_TIME}}': _esc(post_time),
        '{{IMAGE_COUNT}}': str(image_count),
        '{{IMAGE_DATA}}': images_json,
        '{{LIKE_NAMES}}': _esc(like_names),
        '{{COMMENTS_JSON}}': comments_json,
        '{{AVATAR_MAP_JSON}}': '{}',
    }

    result = template
    for k, v in replacements.items():
        result = result.replace(k, v)
    return result

def _generate_x_handle(name):
    clean = name.replace(' ', '').replace('-', '_')
    return f"@{clean}{random.randint(10, 99)}"

def fill_x_feed_template(template, friend_info, poster_name, image_data_uris=None, avatar_data_uri=None):
    post_text = friend_info.get('post_text', '')
    post_time = friend_info.get('post_time', '2h')
    likes = friend_info.get('likes', [])
    comments = friend_info.get('comments', [])

    handle = _generate_x_handle(poster_name)
    like_count = len(likes) + random.randint(5, 50)
    reply_count = len(comments) + random.randint(0, 5)
    retweet_count = random.randint(1, 30)
    view_count = like_count * random.randint(8, 30)

    def _fmt(n):
        return f"{n/1000:.1f}K" if n >= 1000 else str(n)

    avatar_initial = poster_name[0].upper() if poster_name else '?'

    # Image area HTML
    images_html = ''
    if image_data_uris:
        n_imgs = min(len(image_data_uris), 4)
        cols = 1 if n_imgs == 1 else 2
        images_html = f'<div style="display:grid;grid-template-columns:repeat({cols},1fr);gap:2px;border-radius:16px;overflow:hidden;margin-top:12px">'
        for img_uri in image_data_uris[:4]:
            images_html += f'<img src="{img_uri}" style="width:100%;height:{"280px" if n_imgs==1 else "150px"};object-fit:cover">'
        images_html += '</div>'

    # Build tweet HTML matching new twitter_feed.html structure
    tweet_html = f'''
    <div class="tweet">
      <div class="avatar">{avatar_initial}</div>
      <div class="content">
        <div class="tweet-header">
          <span class="name">{_esc(poster_name)}</span>
          <span class="handle">{_esc(handle)}</span>
          <span class="dot">\u00b7</span>
          <span class="time">{_esc(post_time)}</span>
        </div>
        <div class="tweet-body">{_esc(post_text)}{images_html}</div>
        <div class="actions">
          <div class="action reply">
            <svg viewBox="0 0 24 24"><path d="M1.751 10c0-4.42 3.584-8 8.005-8h4.366c4.49 0 8.129 3.64 8.129 8.13 0 2.25-.893 4.32-2.383 5.83l-4.61 4.6c-.57.57-1.49.18-1.49-.61v-2.03c-5.14-.22-7.77-2.61-8.77-4.51-.54-1.03-.1-2.29 1.05-2.29h1.2c-.44-1.19-.67-2.14-.67-3.11z"/></svg>
            <span>{reply_count}</span>
          </div>
          <div class="action retweet">
            <svg viewBox="0 0 24 24"><path d="M4.5 3.88l4.432 4.14-1.364 1.46L5.5 7.55V16c0 1.1.896 2 2 2H13v2H7.5c-2.209 0-4-1.79-4-4V7.55L1.432 9.48.068 8.02 4.5 3.88zM16.5 6H11V4h5.5c2.209 0 4 1.79 4 4v8.45l2.068-1.93 1.364 1.46-4.432 4.14-4.432-4.14 1.364-1.46 2.068 1.93V8c0-1.1-.896-2-2-2z"/></svg>
            <span>{retweet_count}</span>
          </div>
          <div class="action like">
            <svg viewBox="0 0 24 24"><path d="M16.697 5.5c-1.222-.06-2.679.51-3.89 2.16l-.805 1.09-.806-1.09C9.984 6.01 8.526 5.44 7.304 5.5c-1.243.07-2.349.78-2.91 1.91-.552 1.12-.633 2.78.479 4.82 1.074 1.97 3.257 4.27 7.129 6.61 3.87-2.34 6.052-4.64 7.126-6.61 1.111-2.04 1.03-3.7.477-4.82-.56-1.13-1.666-1.84-2.908-1.91z"/></svg>
            <span>{_fmt(like_count)}</span>
          </div>
          <div class="action views">
            <svg viewBox="0 0 24 24"><path d="M8.75 21V3h2v18h-2zM18.75 21V8h2v13h-2zM13.75 21v-8h2v8h-2zM3.75 21v-4h2v4h-2z"/></svg>
            <span>{_fmt(view_count)}</span>
          </div>
          <div class="action share">
            <svg viewBox="0 0 24 24"><path d="M12 2.59l5.7 5.7-1.41 1.42L13 6.41V16h-2V6.41l-3.3 3.3-1.41-1.42L12 2.59zM21 15l-.02 3.51c0 1.38-1.12 2.49-2.5 2.49H5.5C4.11 21 3 19.88 3 18.5V15h2v3.5c0 .28.22.5.5.5h12.98c.28 0 .5-.22.5-.5L19 15h2z"/></svg>
          </div>
        </div>
      </div>
    </div>
    '''

    marker = '<!-- 消息将由脚本动态填充 -->'
    if marker in template:
        return template.replace(marker, tweet_html)
    return template.replace(
        '<div id="feed">\n',
        f'<div id="feed">\n{tweet_html}\n'
    )
