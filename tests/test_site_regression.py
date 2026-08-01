"""Persistent browser regression checks for the static MobileMem project page."""

from pathlib import Path

try:
    from playwright.sync_api import Page, sync_playwright
except ModuleNotFoundError as error:
    raise SystemExit(
        "Playwright is not installed. Run `pip install -r requirements-test.txt` "
        "and `playwright install chromium`."
    ) from error


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE_URL = f"{(PROJECT_ROOT / 'index.html').as_uri()}#mobilemem"
TEST_RESULTS = PROJECT_ROOT / "test-results"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def dimensions(page: Page, selector: str) -> dict[str, float]:
    result = page.locator(selector).evaluate(
        """element => {
          const rect = element.getBoundingClientRect();
          return { width: rect.width, height: rect.height };
        }"""
    )
    return {"width": result["width"], "height": result["height"]}


def close_to(actual: float, expected: float, tolerance: float = 1.5) -> bool:
    return abs(actual - expected) <= tolerance


def assert_geometry(page: Page, viewport: str) -> None:
    expected = {
        "desktop": {
            ".application-layout": (1180, 790),
            ".application-phone": (300, 630),
            ".case-phone": (230, 500),
            ".memory-room": (500, 500),
        },
        "mobile": {
            ".application-layout": (362, 811.56),
            ".application-phone": (266, 548),
            ".case-phone": (308, 500),
            ".memory-room": (328, 500),
        },
    }[viewport]

    for selector, (expected_width, expected_height) in expected.items():
        measured = dimensions(page, selector)
        require(
            close_to(measured["width"], expected_width),
            f"{viewport} {selector} width changed: {measured['width']}",
        )
        require(
            close_to(measured["height"], expected_height),
            f"{viewport} {selector} height changed: {measured['height']}",
        )

    scroll_width = page.evaluate("document.documentElement.scrollWidth")
    viewport_width = page.evaluate("window.innerWidth")
    require(scroll_width == viewport_width, f"{viewport} page has horizontal overflow")


def assert_release_metadata(page: Page) -> None:
    description = page.locator('meta[name="description"]').get_attribute("content") or ""
    require(len(description) >= 60, "Page description is missing or too generic")

    cdn_scripts = page.locator('script[src^="https://cdn.jsdelivr.net/"]')
    require(cdn_scripts.count() == 2, "Expected the two pinned GSAP CDN scripts")
    for index in range(cdn_scripts.count()):
        script = cdn_scripts.nth(index)
        require(
            (script.get_attribute("integrity") or "").startswith("sha384-"),
            "CDN script is missing SHA-384 integrity metadata",
        )
        require(
            script.get_attribute("crossorigin") == "anonymous",
            "CDN script is missing anonymous CORS mode",
        )

    require(
        page.locator("[data-oppo-video]").get_attribute("preload") == "none",
        "Hidden video must not preload on initial page load",
    )
    require(
        page.locator("#busuanzi_value_site_pv").count() == 1,
        "Required page-view counter target is missing",
    )


def assert_application_interactions(page: Page) -> None:
    require(page.locator("#dataset-construction").count() == 0, "Removed dataset DOM returned")
    require(page.locator(".application-path").count() == 0, "Removed breadcrumb DOM returned")
    require(
        page.locator("[data-application-enter-uid], [data-application-enter-type]").count() == 0,
        "Removed application selection views returned",
    )

    phone = page.locator(".application-phone")
    require(phone.get_attribute("data-application-phone-mode") == "home", "Phone must open at home")
    require(page.locator("[data-application-phone-type]").count() == 12, "Expected 12 image types")

    active_profile = page.locator('[data-application-phone-uid][aria-pressed="true"]')
    require(active_profile.get_attribute("data-application-phone-uid") == "uid10", "English must use uid10 initially")
    require(page.locator(".application-uid-group:visible button").count() == 3, "Expected 3 English profiles")

    language_toggle = page.locator("[data-toggle-lang]")
    language_toggle.click()
    require(page.locator("body.lang-zh").count() == 1, "Language toggle did not switch to Chinese")
    require(page.locator("html").get_attribute("lang") == "zh", "Document language did not switch")
    require(
        active_profile.get_attribute("data-application-phone-uid") == "uid0",
        "Chinese must switch to uid0",
    )
    require(page.locator(".application-uid-group:visible button").count() == 3, "Expected 3 Chinese profiles")
    language_toggle.click()
    require(page.locator("html").get_attribute("lang") == "en", "Document language did not reset")

    image = page.locator("#application-visual-image")
    image_before_accordion = image.get_attribute("src")
    page.locator(".application-item summary").nth(2).click()
    require(image.get_attribute("src") == image_before_accordion, "Accordion changed the phone image")
    require(page.locator(".application-item[open]").count() == 1, "Accordion must keep one item open")

    category_buttons = page.locator("[data-application-phone-type]")
    for index in range(category_buttons.count()):
        button = category_buttons.nth(index)
        category = button.get_attribute("data-application-phone-type")
        button.click()
        page.wait_for_timeout(140)
        require(phone.get_attribute("data-application-phone-mode") == "record", f"{category} did not open")
        require(f"-{category}-01.png" in (image.get_attribute("src") or ""), f"Wrong {category} image")
        require(image.evaluate("element => element.naturalWidth") > 0, f"{category} image failed to load")
        page.locator('[data-application-system-action="home"]').click()

    category_buttons.first.click()
    require(page.locator("#application-phone-position").inner_text() == "01 / 05", "Wrong initial sample count")
    page.locator("[data-application-phone-direction][data-application-direction='next']").click()
    page.wait_for_timeout(140)
    require(page.locator("#application-phone-position").inner_text() == "02 / 05", "Image cycling failed")
    page.locator('[data-application-system-action="home"]').click()

    page.locator("[data-application-phone-ai]").click()
    require(phone.get_attribute("data-application-phone-mode") == "dialogue", "AI dialogue did not open")
    image_bubbles = page.locator(".application-ai-image-bubble")
    require(image_bubbles.count() > 0, "Dialogue should contain image messages")
    bubble_style = image_bubbles.first.evaluate(
        """element => {
          const style = getComputedStyle(element);
          return {
            padding: style.padding,
            borderWidth: style.borderWidth,
            backgroundColor: style.backgroundColor,
            bubbleWidth: element.getBoundingClientRect().width,
            imageWidth: element.querySelector("img").getBoundingClientRect().width,
          };
        }"""
    )
    require(bubble_style["padding"] == "0px", "Image messages must not have a white gutter")
    require(bubble_style["borderWidth"] == "0px", "Image messages must not have a card border")
    require(
        bubble_style["backgroundColor"] == "rgba(0, 0, 0, 0)",
        "Image messages must use a transparent background",
    )
    require(
        close_to(bubble_style["bubbleWidth"], bubble_style["imageWidth"], 0.5),
        "Image messages must shrink to the rendered image width",
    )
    page.locator("[data-application-ai-history-open]").click()
    history = page.locator("[data-application-ai-history]")
    require(not history.is_hidden(), "Dialogue history did not open")
    require(
        page.locator("[data-application-ai-session-tabs] button").count() == 5,
        "Expected 5 dialogue trajectories",
    )
    page.locator("[data-application-ai-session-tabs] button").nth(1).click()
    require(history.is_hidden(), "Selecting a trajectory did not close history")
    page.locator('[data-application-system-action="back"]').click()
    require(phone.get_attribute("data-application-phone-mode") == "home", "Back did not return home")

    page.locator('[data-application-system-action="recents"]').click()
    require(phone.get_attribute("data-application-phone-mode") == "recents", "Recents did not open")
    page.locator('[data-application-system-action="back"]').click()
    require(phone.get_attribute("data-application-phone-mode") == "home", "Back did not leave recents")


def run() -> None:
    quick_start_source = (PROJECT_ROOT / "assets/web/js/quick-start.js").read_text()
    main_source = (PROJECT_ROOT / "assets/web/js/main.js").read_text()
    require("MoblieMem" not in quick_start_source, "Quick Start contains a misspelled project path")
    require(
        "huggingface-cli" not in quick_start_source,
        "Quick Start contains the retired Hugging Face CLI command",
    )
    require(
        'text: "pip install -r MobileMem/requirements.txt"' in quick_start_source,
        "Quick Start is missing the textual benchmark dependency path",
    )
    require(
        "busuanzi.ibruce.info/busuanzi/2.3/busuanzi.pure.mini.js" in main_source,
        "Required page-view counter was removed or replaced",
    )

    errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            desktop = browser.new_page(
                viewport={"width": 1664, "height": 900}, reduced_motion="reduce"
            )
            desktop.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            desktop.on("pageerror", lambda error: errors.append(str(error)))
            desktop.goto(PAGE_URL)
            desktop.wait_for_load_state("networkidle")
            assert_release_metadata(desktop)
            assert_geometry(desktop, "desktop")
            assert_application_interactions(desktop)

            mobile = browser.new_page(
                viewport={"width": 390, "height": 844}, reduced_motion="reduce"
            )
            mobile.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            mobile.on("pageerror", lambda error: errors.append(str(error)))
            mobile.goto(PAGE_URL)
            mobile.wait_for_load_state("networkidle")
            assert_geometry(mobile, "mobile")

            require(not errors, f"Browser console errors: {errors}")
        except Exception:
            TEST_RESULTS.mkdir(exist_ok=True)
            for name, page in (("desktop", locals().get("desktop")), ("mobile", locals().get("mobile"))):
                if page and not page.is_closed():
                    page.screenshot(path=str(TEST_RESULTS / f"regression-{name}.png"), full_page=True)
            raise
        finally:
            browser.close()

    print("Browser regression checks passed for desktop and mobile.")


if __name__ == "__main__":
    run()
