"""App-trace HTML template filling (book / music / video / shopping)."""
import html as html_module
import json
import logging
import os
import random
from datetime import datetime, timedelta

from backends.llm import get_text_llm_model, llm_request
from common import TEMPLATE_DIR

logger = logging.getLogger('fix_app_screenshots')


# Per-uuid phone cache (generated once per uuid, then reused within a run).
_persona_phones: dict = {}

# Template path maps (CN / EN).
TEMPLATES_CN = {
    "book": os.path.join(TEMPLATE_DIR, '微信读书.html'),
    "music": os.path.join(TEMPLATE_DIR, '网易云音乐.html'),
    "video": os.path.join(TEMPLATE_DIR, 'B站.html'),
    "shopping": os.path.join(TEMPLATE_DIR, '淘宝订单.html'),
    "ticket": os.path.join(TEMPLATE_DIR, '火车票.html'),
    "money": os.path.join(TEMPLATE_DIR, '微信转账.html'),
}
TEMPLATES_EN = {
    "book": os.path.join(TEMPLATE_DIR, 'Kindle.html'),
    "music": os.path.join(TEMPLATE_DIR, 'Spotify.html'),
    "video": os.path.join(TEMPLATE_DIR, 'YouTube.html'),
    "shopping": os.path.join(TEMPLATE_DIR, 'Amazon.html'),
    "ticket": os.path.join(TEMPLATE_DIR, 'TrainTicket.html'),
    "money": os.path.join(TEMPLATE_DIR, 'PaymentTransfer.html'),
}


def _esc(text):
    if text is None:
        return ""
    return html_module.escape(str(text))

_en_translation_cache = {}

def _contains_cn(text):
    return any('\u4e00' <= c <= '\u9fff' for c in str(text))

def _ensure_english(text):
    # English fallback: schemas are split by language, but the LLM can still
    # emit Chinese for free text such as product names, shop names, or reviews.
    # Translate detected Chinese to avoid Chinese text in English screenshots.
    # Return the original text on failure or when no Chinese is present; cache results.
    s = str(text) if text is not None else ""
    if not s.strip() or not _contains_cn(s):
        return s
    if s in _en_translation_cache:
        return _en_translation_cache[s]
    try:
        translated, _ = llm_request(
            system_prompt="You translate Chinese text into natural English for app screenshots. Output ONLY the English translation, with no quotes or notes.",
            user_prompt=s,
            model=get_text_llm_model(False),
            temperature=0.3,
            max_tokens=200,
            extract_json=False,
        )
        translated = (translated or "").strip().strip('"').strip()
        result = translated if (translated and not _contains_cn(translated)) else s
    except Exception as e:
        logger.warning(f"[_ensure_english] translate failed, keep original: {e}")
        result = s
    _en_translation_cache[s] = result
    return result

def _load_template(app_type, nationality="Chinese"):
    tmap = TEMPLATES_CN if nationality == "Chinese" else TEMPLATES_EN
    path = tmap.get(app_type)
    if not path or not os.path.exists(path):
        raise FileNotFoundError(f"Template not found: {path}")
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def fill_book_template(template, info, is_cn=True):
    title = info.get("title", "Unknown Book" if not is_cn else "未知书籍")
    author = info.get("author", "Unknown Author" if not is_cn else "未知作者")
    progress_str = info.get("progress", "50%")
    rating = info.get("rating", 4)
    highlight = info.get("highlight", "")
    platform = info.get("platform", "微信读书" if is_cn else "Kindle")

    progress_num = int(''.join(c for c in str(progress_str) if c.isdigit()) or '50')
    recommend_rate = max(70, min(98, progress_num + 30))
    reader_count = round(progress_num * 2.5 + 10, 1)
    word_count = round(progress_num * 0.3 + 5, 1)
    review_count = round(reader_count * 0.2, 1)

    if is_cn:
        rec_books = [{"title": "活着"}, {"title": "人生"}, {"title": "平凡的世界"}, {"title": "围城"}]
    else:
        rec_books = [{"title": "1984"}, {"title": "The Great Gatsby"}, {"title": "To Kill a Mockingbird"}, {"title": "Sapiens"}]
    rec_books_json = json.dumps(rec_books, ensure_ascii=False)

    replacements = {
        "{{STATUS_TIME}}": "12:01",
        "{{TITLE}}": _esc(title),
        "{{AUTHOR}}": _esc(author),
        "{{READER_COUNT}}": str(reader_count),
        "{{WORD_COUNT}}": str(word_count),
        "{{PUBLISHER}}": _esc(platform),
        "{{DESCRIPTION}}": _esc(highlight) if highlight else _esc(f"《{title}》是{author}的作品。"),
        "{{RECOMMEND_RATE}}": str(recommend_rate),
        "{{REVIEW_COUNT}}": str(review_count),
        "{{MY_VOTE}}": "good" if rating >= 4 else ("normal" if rating >= 3 else "bad"),
        "{{REC_BOOKS_JSON}}": rec_books_json,
    }
    result = template
    for k, v in replacements.items():
        result = result.replace(k, v)
    return result

def fill_music_template(template, info, is_cn=True):
    song = info.get("song", "未知歌曲" if is_cn else "Unknown Song")
    artist = info.get("artist", "未知歌手" if is_cn else "Unknown Artist")
    album = info.get("album", "")
    duration = info.get("duration", "3:30")
    current_time = info.get("current_time", "1:24")
    playlist = info.get("playlist", "我喜欢的音乐" if is_cn else "Liked Songs")
    lyric_line = info.get("lyric_line", "♪ ♪ ♪")
    comment = info.get("comment", "")
    comment_user = info.get("comment_user", "云村音乐人" if is_cn else "MusicFan")

    replacements = {
        "{{STATUS_TIME}}": "9:41",
        "{{SONG}}": _esc(song),
        "{{ARTIST}}": _esc(artist),
        "{{ALBUM}}": _esc(album) if album else _esc(song),
        "{{DURATION}}": _esc(duration),
        "{{CURRENT_TIME}}": _esc(current_time),
        "{{PLAYLIST}}": _esc(playlist),
        "{{LYRIC_LINE}}": _esc(lyric_line),
        "{{LYRIC_PREV}}": _esc(info.get("lyric_prev", "")),
        "{{LYRIC_NEXT}}": _esc(info.get("lyric_next", "")),
        "{{COMMENT}}": _esc(comment),
        "{{COMMENT_USER}}": _esc(comment_user),
    }
    result = template
    for k, v in replacements.items():
        result = result.replace(k, v)
    return result

def fill_video_template(template, info, cover_b64="", is_cn=True):
    title = info.get("title", "视频" if is_cn else "Video")
    uploader = info.get("uploader", "UP主" if is_cn else "Creator")
    duration = info.get("duration", "10:00")
    view_count = info.get("view_count", "1.2万" if is_cn else "12K")
    action = info.get("action", "点赞" if is_cn else "Like")
    danmaku = info.get("danmaku", "")
    tags = info.get("tags", [])
    description = info.get("description", "")

    danmaku_list = [danmaku] if danmaku else []
    if is_cn:
        danmaku_list.extend(["前排", "666", "太强了", "学到了", "yyds", "哈哈哈"])
    else:
        danmaku_list.extend(["First!", "Amazing", "So good", "Learned a lot", "GOAT", "LOL"])
    danmaku_json = json.dumps(danmaku_list[:8], ensure_ascii=False)
    tags_json = json.dumps(tags, ensure_ascii=False)

    if is_cn:
        default_comments = [
            {"name": "路人甲", "text": "太棒了！", "time": "昨天", "likes": random.randint(50, 500)},
            {"name": "小白", "text": "催更！", "time": "3天前", "likes": random.randint(20, 200)},
        ]
    else:
        default_comments = [
            {"name": "John", "text": "Great video!", "time": "yesterday", "likes": random.randint(50, 500)},
            {"name": "Sarah", "text": "More please!", "time": "3 days ago", "likes": random.randint(20, 200)},
        ]
    hot_comments = info.get("hot_comments", default_comments)
    hot_comments_json = json.dumps(hot_comments, ensure_ascii=False)

    replacements = {
        "{{STATUS_TIME}}": "9:41",
        "{{TITLE}}": _esc(title),
        "{{UPLOADER}}": _esc(uploader),
        "{{DURATION}}": _esc(duration),
        "{{VIEW_COUNT}}": _esc(str(view_count)),
        "{{ACTION}}": _esc(action),
        "{{DANMAKU_JSON}}": danmaku_json,
        "{{TAGS_JSON}}": tags_json,
        "{{DANMAKU_COUNT}}": _esc(str(info.get("danmaku_count", random.randint(100, 3000)))),
        "{{PUBLISH_DATE}}": _esc(str(info.get("publish_date", "2025-06-15"))),
        "{{FANS_COUNT}}": _esc(str(info.get("fans_count", f"{random.randint(1, 99)}万"))),
        "{{LIKE_COUNT}}": _esc(str(info.get("like_count", random.randint(500, 9999)))),
        "{{FAV_COUNT}}": _esc(str(info.get("fav_count", random.randint(100, 5000)))),
        "{{DESCRIPTION}}": _esc(description).replace('\n', '\\n').replace('\r', ''),
        "{{HOT_COMMENTS_JSON}}": hot_comments_json,
        "{{COVER_BASE64}}": cover_b64 if cover_b64 else "",
    }
    result = template
    for k, v in replacements.items():
        result = result.replace(k, v)
    return result

def fill_shopping_template(template, info, persona_name="用户", location="", is_cn=True, uuid=0):
    item_name = info.get("item_name", "商品" if is_cn else "Product")
    shop = info.get("shop_name", "店铺" if is_cn else "Store")
    if not is_cn:
        item_name = _ensure_english(item_name)
        shop = _ensure_english(shop)
    short_name = item_name[:8] + "…" if len(item_name) > 8 else item_name
    price = info.get("price", 0)
    if isinstance(price, (int, float)):
        price_str = f"{price:.2f}"
        price_num = float(price)
    else:
        price_str = str(price)
        price_num = float(str(price).replace("¥", "").replace("$", "").replace(",", "") or "0")

    orig_price = price_num * random.uniform(1.05, 1.3)
    shop_discount = round(orig_price - price_num - random.uniform(0, 1), 2)
    if shop_discount < 0:
        shop_discount = 0
    pay_discount = round(orig_price - price_num - shop_discount, 2)
    if pay_discount < 0:
        pay_discount = 0

    order_time = info.get("order_time", "")
    review_text = info.get("review_text", "")
    if not is_cn:
        review_text = _ensure_english(review_text)
    order_status = info.get("order_status", "已完成" if is_cn else "Delivered")
    rating = info.get("rating", 5)

    # Defensive translation: English personas can still get Chinese order_status
    # values because the schema shares Chinese and English enums.
    if not is_cn and any('\u4e00' <= c <= '\u9fff' for c in str(order_status)):
        _CN_TO_EN_STATUS = {
            "已完成": "Delivered",
            "已签收": "Delivered",
            "已发货": "Shipped",
            "运输中": "In Transit",
            "待发货": "Pending Shipment",
            "待付款": "Pending Payment",
            "待支付": "Pending Payment",
            "待收货": "Out for Delivery",
            "已取消": "Cancelled",
            "退款中": "Refunding",
        }
        order_status = _CN_TO_EN_STATUS.get(str(order_status).strip(), "Delivered")

    if is_cn:
        if "待发" in str(order_status):
            action_btn, logistics = "退款", "预计后天送达"
        elif "已完成" in str(order_status) or "已签收" in str(order_status):
            action_btn, logistics = "再次购买", "已签收"
        else:
            action_btn, logistics = "确认收货", "运输中"
    else:
        status_lower = str(order_status).lower()
        if "pending" in status_lower or "processing" in status_lower:
            action_btn, logistics = "Cancel", "Expected delivery in 2 days"
        elif "delivered" in status_lower or "completed" in status_lower:
            action_btn, logistics = "Buy Again", "Delivered"
        else:
            action_btn, logistics = "Confirm Receipt", "In Transit"

    guard_date = (datetime.now() + timedelta(days=15)).strftime("%m/%d %H:%M")
    if is_cn:
        guarantee_tags = json.dumps(["退货宝", "15天价保", "破损包退"], ensure_ascii=False)
    else:
        guarantee_tags = json.dumps(["A-to-z Guarantee", "Free Returns", "Prime"], ensure_ascii=False)

    replacements = {
        "{{STATUS_TIME}}": "00:06",
        "{{ORDER_STATUS}}": _esc(order_status),
        "{{ADDRESS}}": _esc(location) if location else ("收货地址" if is_cn else "Shipping address"),
        "{{BUYER_NAME}}": _esc(persona_name),
        "{{PHONE}}": _persona_phones.setdefault(
            uuid,
            f"86-1{random.randint(30, 99)}****{random.randint(1000, 9999)}"
        ),
        "{{LOGISTICS_TEXT}}": _esc(logistics),
        "{{SHOP_NAME}}": _esc(shop),
        "{{ITEM_NAME}}": _esc(item_name),
        "{{ITEM_NAME_SHORT}}": _esc(short_name),
        "{{ITEM_SKU}}": _esc(info.get("sku", short_name)),
        "{{PRICE}}": price_str,
        "{{ORIG_PRICE}}": f"{orig_price:.2f}",
        "{{QTY}}": str(info.get("qty", 1)),
        "{{ACTION_BTN}}": _esc(action_btn),
        "{{SHOP_DISCOUNT}}": f"{shop_discount:.2f}",
        "{{PAY_DISCOUNT}}": f"{pay_discount:.2f}",
        "{{ORDER_TIME}}": _esc(str(order_time)),
        "{{RATING}}": str(rating),
        "{{REVIEW_TEXT}}": _esc(review_text),
        "{{PRICE_GUARD_DATE}}": guard_date,
        "{{GUARANTEE_TAGS_JSON}}": guarantee_tags,
    }
    result = template
    for k, v in replacements.items():
        result = result.replace(k, v)
    return result

def fill_template(app_type, template, info, **kwargs):
    is_cn = kwargs.get("nationality", "Chinese") == "Chinese"
    if app_type == "book":
        return fill_book_template(template, info, is_cn=is_cn)
    elif app_type == "music":
        return fill_music_template(template, info, is_cn=is_cn)
    elif app_type == "video":
        return fill_video_template(template, info, cover_b64=kwargs.get("cover_b64", ""), is_cn=is_cn)
    elif app_type == "shopping":
        return fill_shopping_template(
            template, info,
            persona_name=kwargs.get("persona_name", "用户"),
            location=kwargs.get("location", ""),
            is_cn=is_cn,
            uuid=kwargs.get("uuid", 0),
        )
    else:
        raise ValueError(f"Unknown app_type: {app_type}")
