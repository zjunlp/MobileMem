"""App-trace video cover generation (image API + PIL gradient fallback)."""
import base64
import logging

import requests

import config

logger = logging.getLogger('fix_app_screenshots')


COVER_API_URL = config.DMX_GENERATION_URL


def _make_fallback_cover_b64(title: str, tags: list) -> str:
    """Generate a simple PIL gradient cover as a fallback when the API fails."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        import colorsys
        import hashlib
        # Choose a hue from the title hash.
        h = int(hashlib.md5(title.encode()).hexdigest()[:4], 16) / 65536
        r1, g1, b1 = [int(c * 255) for c in colorsys.hsv_to_rgb(h, 0.7, 0.9)]
        r2, g2, b2 = [int(c * 255) for c in colorsys.hsv_to_rgb((h + 0.1) % 1, 0.85, 0.6)]
        img = Image.new('RGB', (640, 360))
        draw = ImageDraw.Draw(img)
        for x in range(640):
            t = x / 639
            rc = int(r1 * (1 - t) + r2 * t)
            gc = int(g1 * (1 - t) + g2 * t)
            bc = int(b1 * (1 - t) + b2 * t)
            draw.line([(x, 0), (x, 360)], fill=(rc, gc, bc))
        # Title text, capped at 16 characters.
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 32)
        except Exception:
            font = ImageFont.load_default()
        short_title = title[:16] + ("…" if len(title) > 16 else "")
        draw.text((20, 150), short_title, fill=(255, 255, 255), font=font)

        import io
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        logger.debug(f"[cover] fallback PIL cover failed: {e}")
        return ""

def generate_video_cover_b64(info, nationality="Chinese"):
    """Generate a video cover image and return it as a data URI, falling back to PIL."""
    title = info.get("title", "视频")
    tags = info.get("tags", [])
    tags_str = "、".join(tags[:5]) if tags else ""

    if nationality == "Chinese":
        prompt = (
            f"为B站视频生成一张高质量封面图，视频标题：'{title}'。"
            + (f"标签：{tags_str}。" if tags_str else "")
            + "风格吸睛、色彩鲜明，适合作为视频缩略图，不要文字水印。"
        )
    else:
        prompt = (
            f"Generate a high-quality YouTube video thumbnail for the video titled '{title}'."
            + (f" Tags: {tags_str}." if tags_str else "")
            + " Eye-catching style, vibrant colors, suitable as a video thumbnail, no text or watermarks."
        )

    # Always use doubao for cover generation.
    headers = {"Authorization": f"Bearer {config.DMX_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "doubao-seedream-4-5-251128",
        "prompt": prompt,
        "n": 1,
        "size": "2K",
    }

    try:
        resp = requests.post(COVER_API_URL, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        entry = data.get("data", [{}])[0]
        b64_str = entry.get("b64_json", "")
        if b64_str:
            return f"data:image/png;base64,{b64_str}"
        url = entry.get("url", "")
        if url:
            img_resp = requests.get(url, timeout=30)
            img_resp.raise_for_status()
            b64_str = base64.b64encode(img_resp.content).decode()
            return f"data:image/png;base64,{b64_str}"
        logger.warning(f"[cover] API returned empty data (title={title!r})")
    except Exception as e:
        logger.warning(f"[cover] Cover API failed (title={title!r}): {e}")

    # Fallback: generate a gradient cover with PIL.
    logger.info(f"[cover] Using PIL gradient fallback cover: {title!r}")
    return _make_fallback_cover_b64(title, tags)
