"""Conversation HTML -> PNG screenshot rendering (Chrome / html2image)."""
import logging
import os
import sys
import tempfile
import threading
from typing import Optional

logger = logging.getLogger('conversation')


# Serializes Chrome/html2image runs (the native side is not thread-safe). Was a
# module-level lock in the original conversation (group chats) script.
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
        # --force-device-scale-factor=1: without it, Windows display scaling
        # (e.g. 125%) makes Chrome render more CSS pixels than the window
        # width, clipping the right side of the page out of the screenshot.
        common_flags = ['--allow-file-access-from-files',
                        '--force-device-scale-factor=1', '--hide-scrollbars']
        if sys.platform == 'win32':
            flags = common_flags
        else:
            flags = ['--no-sandbox', '--disable-dev-shm-usage', *common_flags]
        hti_kwargs = dict(output_path=output_dir, custom_flags=flags)
        if chrome_path:
            hti_kwargs['browser_executable'] = chrome_path

        # Render with a large height to capture the full content.
        # Width: Chrome silently enforces a minimum window width (~500px), so
        # asking for 450 yields a ~504px viewport; the centered .phone then
        # sits ~27px to the right and the left-anchored crop cuts its right
        # edge off. Render comfortably wider than the minimum and crop the
        # centered target strip afterwards (both chat templates center the
        # phone via body{justify-content:center}).
        render_width = max(width, 600)
        full_height = segment_height * max_segments
        temp_output = os.path.basename(output_path) + ".full_temp.png"
        temp_html_path = None
        with HTML_RENDER_LOCK:
            with tempfile.NamedTemporaryFile('w', suffix='.html', delete=False, dir=output_dir, encoding='utf-8') as temp_html:
                temp_html.write(html_content)
                temp_html_path = temp_html.name
            try:
                hti = Html2Image(**hti_kwargs)
                hti.screenshot(html_file=temp_html_path, save_as=temp_output, size=(render_width, full_height))
            finally:
                if temp_html_path and os.path.exists(temp_html_path):
                    os.remove(temp_html_path)

        temp_full_path = os.path.join(output_dir, temp_output)
        if not os.path.exists(temp_full_path):
            logger.error(f"Full-height screenshot not created: {temp_full_path}")
            return [], []

        # Open the full render. load() forces PIL to read and release the file
        # handle now — otherwise the os.remove below silently fails on Windows
        # (open handle) and .full_temp.png files accumulate next to the output.
        img = Image.open(temp_full_path)
        img.load()
        if img.mode == 'RGBA':
            bg = Image.new('RGB', img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            img = bg
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        # Delete the temporary full screenshot.
        try:
            os.remove(temp_full_path)
        except OSError as e:
            # Not silently ignorable: a leftover .full_temp.png sits next to the
            # real screenshots and would be picked up by downstream image scans.
            logger.warning(f"[WARN] Could not delete temp screenshot {temp_full_path}: {e}")

        arr = np.array(img)
        height, width_px = arr.shape[:2]

        # -- Scan message position markers (before any cropping / erasing).
        # Markers are created by JS injected from render_group_chat_html:
        # each message gets a 3px-wide, 1px-high color marker at x=0.
        # Color encoding: R=254, G=(idx%128)*2, B=(idx//128)*2.
        msg_y_positions = {}  # msg_idx -> y_position (message top)
        if width_px >= 5:
            marker_rows = np.where(arr[:, 1, 0] == 254)[0]
            for y_pos in marker_rows:
                pixel = arr[y_pos, 1]
                msg_idx = int(pixel[1]) // 2 + (int(pixel[2]) // 2) * 128
                if msg_idx not in msg_y_positions:
                    msg_y_positions[msg_idx] = int(y_pos)
            # Erase the marker strip so the colored dots are not visible in the
            # final screenshots (copy the adjacent background pixel over it).
            for y_pos in marker_rows:
                arr[y_pos, 0:4] = arr[y_pos, 4]

        # -- Cut the centered phone strip out of the wider render (see
        # render_width above; the phone is centered by the template's body
        # justify-content:center). Markers live at x=0 of the full render and
        # fall away with this crop.
        if width_px > width:
            left = (width_px - width) // 2
            arr = arr[:, left:left + width]
            height, width_px = arr.shape[:2]
        img = Image.fromarray(arr)

        # -- Bottom crop, theme-independent.
        # Per-row *spatial* std is ~0 for any uniform row (black, white, or
        # gray), so this works for dark themes too — the old brightness-based
        # "non-black rows" check kept huge black voids on the X/dark template.
        # Content ends after the last message bubble; everything below (empty
        # chat area + the input bar pinned to the bottom of the tall render by
        # min-height:100vh) is dropped.
        row_spatial_std = arr.astype(np.float32).std(axis=1).mean(axis=1)
        content_rows = np.where(row_spatial_std > 3.0)[0]
        if len(content_rows) > 0:
            if msg_y_positions:
                last_marker = max(msg_y_positions.values())
                bottom = last_marker
                prev = last_marker
                for y in content_rows[content_rows >= last_marker]:
                    if int(y) - prev > 40:  # vertical gap => the last bubble ended
                        break
                    bottom = int(y)
                    prev = int(y)
                bottom_cut = min(height, bottom + 20)
            else:
                bottom_cut = min(height, int(content_rows[-1]) + 15)
            if bottom_cut < img.height:
                img = img.crop((0, 0, img.width, bottom_cut))

        content_height = img.height
        if content_height <= 0:
            return [], []

        # Build output filenames: xxx_cropped.png -> xxx_cropped1.png, xxx_cropped2.png, ...
        base, ext = os.path.splitext(output_path)

        # First remove possible old files, including single-file and segmented outputs.
        old_single = output_path  # e.g. xxx_cropped.png
        if os.path.exists(old_single):
            try:
                os.remove(old_single)
            except OSError as e:
                # Not silently ignorable: a surviving stale output would be
                # treated as a valid screenshot by downstream consumers.
                logger.warning(f"[WARN] Could not delete stale screenshot {old_single}: {e}")
        for j in range(1, max_segments + 1):
            old_seg = f"{base}{j}{ext}"
            if os.path.exists(old_seg):
                try:
                    os.remove(old_seg)
                except OSError as e:
                    # Same as above: a stale segment left behind can outlive the
                    # new render (e.g. old segment 3 when the new render has 2).
                    logger.warning(f"[WARN] Could not delete stale screenshot segment {old_seg}: {e}")

        # -- Plan segment boundaries aligned to message tops so no bubble is
        # cut in half (the old fixed-height slicing sliced through bubbles).
        marker_ys = sorted(set(msg_y_positions.values()))
        boundaries = []  # list of (y_start, y_end)
        y_start = 0
        while y_start < content_height and len(boundaries) < max_segments:
            ideal_end = y_start + segment_height
            if ideal_end >= content_height:
                boundaries.append((y_start, content_height))
                break
            cut = ideal_end
            # Last message whose top lies inside this segment: end the segment
            # just above it (its bubble may extend past the boundary). Skip the
            # alignment when it would make the segment shorter than half the
            # target height (e.g. one very tall message).
            in_range = [y for y in marker_ys if y_start + segment_height // 2 < y <= ideal_end - 8]
            if in_range:
                cut = in_range[-1] - 8
            boundaries.append((y_start, cut))
            y_start = cut

        saved_paths = []
        segment_msg_ranges = []  # per-segment list of message indices
        for i, (seg_start, seg_end) in enumerate(boundaries):
            segment = img.crop((0, seg_start, img.width, seg_end))
            seg_arr = np.array(segment)

            # Skip nearly blank segments (safety net; rare with aligned cuts).
            if i > 0:
                if seg_arr.size == 0 or seg_arr.astype(np.float32).std(axis=1).mean(axis=1).max() < 3.0:
                    logger.debug(f"  Segment {i+1}: skipped (blank)")
                    continue

            seg_path = f"{base}{len(saved_paths) + 1}{ext}"
            segment.save(seg_path)
            saved_paths.append(seg_path)
            # Record the message indexes included in this segment.
            seg_msgs = sorted([idx for idx, yp in msg_y_positions.items()
                              if seg_start <= yp < seg_end])
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
