"""Shared HTML -> PNG screenshot rendering (L1 infra, Playwright sync API).

Used by the app_trace and document generators, which previously each carried
their own copy of the write-html / goto / screenshot sequence. Playwright is
imported lazily so importing this module stays side-effect free.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

DEFAULT_VIEWPORT = {"width": 450, "height": 900}


@contextmanager
def open_screenshot_page(viewport=None):
    """Start Playwright + Chromium and yield a page sized for phone screenshots."""
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    browser = None
    try:
        browser = pw.chromium.launch()
        yield browser.new_page(viewport=dict(viewport or DEFAULT_VIEWPORT))
    finally:
        if browser:
            browser.close()
        pw.stop()


def render_html_to_png(page, html_content: str, png_path: str, html_path: str = None,
                       keep_html: bool = False, clip_to_body: bool = False,
                       viewport_width: int = 450) -> bool:
    """Write *html_content* to disk, load it in *page*, and screenshot to *png_path*.

    clip_to_body=True crops to the rendered body height (avoids bottom
    whitespace on short pages); otherwise a full-page screenshot is taken.
    """
    if html_path is None:
        html_path = png_path.replace('.png', '.html')

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    url = Path(html_path).resolve().as_uri()
    page.goto(url, wait_until="networkidle", timeout=15000)
    page.wait_for_timeout(300)

    if clip_to_body:
        bbox = page.locator('body').bounding_box()
        if bbox and bbox['height'] > 0:
            clip_height = min(int(bbox['height']) + 2, 4000)
            page.screenshot(path=png_path, clip={"x": 0, "y": 0, "width": viewport_width, "height": clip_height})
        else:
            page.screenshot(path=png_path, full_page=True)
    else:
        page.screenshot(path=png_path, full_page=True)

    if not keep_html and os.path.exists(html_path):
        os.remove(html_path)
    return True
