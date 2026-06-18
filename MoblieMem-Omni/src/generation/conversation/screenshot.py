"""Conversation HTML -> PNG screenshot rendering (Chrome / html2image)."""
import logging
import os
import sys
import tempfile
import threading
from typing import Optional

logger = logging.getLogger('stage7')


# Serializes Chrome/html2image runs (the native side is not thread-safe). Was a
# module-level lock in the original stage7_group_chats.
HTML_RENDER_LOCK = threading.Lock()


def _find_chrome() -> Optional[str]:
    """Return Chrome executable path for the current OS, or None to let html2image auto-detect."""
    if sys.platform == 'win32':
        candidates = [
            r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
            os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe'),
            r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        return None
    elif sys.platform == 'darwin':
        mac = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
        return mac if os.path.exists(mac) else None
    else:  # Linux
        for p in ['/usr/bin/google-chrome', '/usr/bin/chromium-browser', '/usr/bin/chromium']:
            if os.path.exists(p):
                return p
        return None

def html_to_png(html_content: str, output_path: str, width: int = 450, height: int = 800) -> bool:
    """Convert HTML to PNG using html2image (single screenshot, legacy)."""
    paths, _ranges = html_to_multi_png(html_content, output_path, width=width,
                                       segment_height=height, max_segments=1)
    return len(paths) > 0

def html_to_multi_png(html_content: str, output_path: str, width: int = 450,
                      segment_height: int = 800, max_segments: int = 5) -> list:
    """Render HTML to full-height PNG, then split into up to max_segments segments.

    output_path: base path like '.../0_gc_0_cropped.png'
    Returns list of saved file paths: ['..._cropped1.png', '..._cropped2.png', ...]
    """
    try:
        from html2image import Html2Image
        from PIL import Image, ImageChops
        import numpy as np

        output_dir = os.path.abspath(os.path.dirname(output_path))
        os.makedirs(output_dir, exist_ok=True)

        chrome_path = _find_chrome()
        if sys.platform == 'win32':
            flags = ['--allow-file-access-from-files']
        else:
            flags = ['--no-sandbox', '--disable-dev-shm-usage', '--allow-file-access-from-files']
        hti_kwargs = dict(output_path=output_dir, custom_flags=flags)
        if chrome_path:
            hti_kwargs['browser_executable'] = chrome_path

        # Render with a large height to capture the full content.
        full_height = segment_height * max_segments
        temp_output = os.path.basename(output_path) + ".full_temp.png"
        temp_html_path = None
        with HTML_RENDER_LOCK:
            with tempfile.NamedTemporaryFile('w', suffix='.html', delete=False, dir=output_dir, encoding='utf-8') as temp_html:
                temp_html.write(html_content)
                temp_html_path = temp_html.name
            try:
                hti = Html2Image(**hti_kwargs)
                hti.screenshot(html_file=temp_html_path, save_as=temp_output, size=(width, full_height))
            finally:
                if temp_html_path and os.path.exists(temp_html_path):
                    os.remove(temp_html_path)

        temp_full_path = os.path.join(output_dir, temp_output)
        if not os.path.exists(temp_full_path):
            logger.error(f"Full-height screenshot not created: {temp_full_path}")
            return []

        # Open and crop the bottom black area.
        img = Image.open(temp_full_path)
        if img.mode == 'RGBA':
            bg = Image.new('RGB', img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            img = bg
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        arr = np.array(img)
        row_means = arr.mean(axis=(1, 2))
        non_black_rows = np.where(row_means > 15)[0]
        if len(non_black_rows) > 0:
            bottom_cut = int(non_black_rows[-1]) + 1
            if bottom_cut < img.height:
                img = img.crop((0, 0, img.width, bottom_cut))

        # Trim blank margins on the left and right.
        bg_ref = Image.new('RGB', img.size, (235, 235, 235))
        diff = ImageChops.difference(img, bg_ref).convert('L')
        bbox = diff.getbbox()
        if bbox:
            left, top, right, bottom = bbox
            padding = 15
            left = max(0, left - padding)
            top = max(0, top - padding)
            right = min(img.width, right + padding)
            bottom = min(img.height, bottom + padding)
            img = img.crop((left, top, right, bottom))

        # Delete the temporary full screenshot.
        try:
            os.remove(temp_full_path)
        except OSError:
            pass

        content_height = img.height
        if content_height <= 0:
            return []

        # Compute the number of required segments.
        n_segments = min(max_segments, max(1, (content_height + segment_height - 1) // segment_height))

        # Build output filenames: xxx_cropped.png -> xxx_cropped1.png, xxx_cropped2.png, ...
        base, ext = os.path.splitext(output_path)

        # First remove possible old files, including single-file and segmented outputs.
        old_single = output_path  # e.g. xxx_cropped.png
        if os.path.exists(old_single):
            try:
                os.remove(old_single)
            except OSError:
                pass
        for j in range(1, max_segments + 1):
            old_seg = f"{base}{j}{ext}"
            if os.path.exists(old_seg):
                try:
                    os.remove(old_seg)
                except OSError:
                    pass

        # -- Scan message position markers.
        # Markers are created by JS injected from render_group_chat_html:
        # each message gets a 3px-wide, 1px-high color marker at x=0.
        # Color encoding: R=254, G=(idx%128)*2, B=(idx//128)*2.
        full_arr = np.array(img)
        msg_y_positions = {}  # msg_idx -> y_position
        for y_pos in range(full_arr.shape[0]):
            if full_arr.shape[1] < 2:
                break
            pixel = full_arr[y_pos, 1]  # scan x=1
            if pixel[0] == 254:
                msg_idx = int(pixel[1]) // 2 + (int(pixel[2]) // 2) * 128
                if msg_idx not in msg_y_positions:
                    msg_y_positions[msg_idx] = y_pos

        saved_paths = []
        segment_msg_ranges = []  # per-segment list of message indices
        for i in range(n_segments):
            y_start = i * segment_height
            y_end = min((i + 1) * segment_height, content_height)
            if y_start >= content_height:
                break

            segment = img.crop((0, y_start, img.width, y_end))
            seg_arr = np.array(segment)

            # Skip nearly blank segments: std < 10 means almost solid background.
            # Check meaningful content after excluding the fixed bottom UI bar.
            # Plain std < 10 cannot filter black-screen plus input-bar segments because the bar raises std.
            if i > 0:
                ui_chrome_h = 80  # Bottom input-bar height in pixels.
                content_area = seg_arr[: max(0, seg_arr.shape[0] - ui_chrome_h)]
                if content_area.size == 0 or content_area.std() < 10:
                    logger.debug(f"  Segment {i+1}: skipped (content std={content_area.std():.1f})")
                    continue

            # Special handling for the last segment: shift upward if the bottom has large gray blank space.
            if i > 0:
                # Compute per-row standard deviation and find the bottom gray-area ratio.
                row_stds = seg_arr.std(axis=(2,)).mean(axis=1)  # Average std per row.
                content_rows = np.where(row_stds > 5)[0]
                if len(content_rows) > 0:
                    last_content_y = int(content_rows[-1])
                    gray_bottom = seg_arr.shape[0] - last_content_y
                    gray_ratio = gray_bottom / seg_arr.shape[0]
                    # If more than 25% of the bottom is blank and there is room above, shift up.
                    if gray_ratio > 0.25 and y_start > 0:
                        shift_up = int(gray_bottom * 0.8)  # Shift up by 80% of the gray area.
                        new_y_start = max(0, y_start - shift_up)
                        new_y_end = min(new_y_start + segment_height, content_height)
                        segment = img.crop((0, new_y_start, img.width, new_y_end))

            seg_path = f"{base}{i + 1}{ext}"
            segment.save(seg_path)
            saved_paths.append(seg_path)
            # Record the message indexes included in this segment.
            seg_msgs = sorted([idx for idx, yp in msg_y_positions.items()
                              if yp >= y_start and yp < y_end])
            segment_msg_ranges.append(seg_msgs)

        if msg_y_positions:
            logger.debug(f"Detected {len(msg_y_positions)} message markers, "
                        f"{len(saved_paths)} segments")

        return saved_paths, segment_msg_ranges

    except ImportError as e:
        logger.warning(f"html2image/PIL not installed, skipping PNG generation: {e}")
        return [], []
    except Exception as e:
        logger.error(f"HTML to multi-PNG failed: {e}")
        return [], []
