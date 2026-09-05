"""Browser-level smoke test for the generated local HTML workbench."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", type=Path, required=True)
    parser.add_argument("--process", default="103487/2023")
    parser.add_argument("--screenshot", type=Path, required=True)
    args = parser.parse_args()

    args.screenshot.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=True,
            args=[
                "--disable-gpu",
                "--disable-pdf-extension",
                "--allow-file-access-from-files",
            ],
        )
        page = browser.new_page(viewport={"width": 900, "height": 1440})
        page.set_default_timeout(5_000)
        page.goto(args.html.resolve().as_uri(), wait_until="domcontentloaded")
        option = page.locator("#process-select option").filter(
            has_text=args.process
        ).first
        page.select_option("#process-select", value=option.get_attribute("value"))
        selected_document = page.locator("#document-select option:checked").inner_text()
        frame_source = page.locator("#pdf-frame").get_attribute("src")

        page.check("#process-done")
        done_before = page.locator("#stat-done").inner_text()
        splitter = page.locator("#splitter").bounding_box()
        assert splitter is not None
        y = splitter["y"] + min(20, splitter["height"] / 2)
        page.mouse.move(splitter["x"] + splitter["width"] / 2, y)
        page.mouse.down()
        page.mouse.move(450, y)
        page.mouse.up()
        split_before = page.evaluate(
            "() => getComputedStyle(document.documentElement)"
            ".getPropertyValue('--viewer-size').trim()"
        )
        page.screenshot(path=str(args.screenshot), full_page=False)

        page.reload(wait_until="domcontentloaded")
        option = page.locator("#process-select option").filter(
            has_text=args.process
        ).first
        page.select_option("#process-select", value=option.get_attribute("value"))
        result = {
            "process": args.process,
            "selected_document": selected_document,
            "frame_source": frame_source,
            "done_before_reload": done_before,
            "done_after_reload": page.locator("#stat-done").inner_text(),
            "checked_after_reload": page.is_checked("#process-done"),
            "split_before_reload": split_before,
            "split_after_reload": page.evaluate(
                "() => getComputedStyle(document.documentElement)"
                ".getPropertyValue('--viewer-size').trim()"
            ),
            "root_scroll_height": page.evaluate(
                "() => document.documentElement.scrollHeight"
            ),
            "inner_height": page.evaluate("() => innerHeight"),
        }
        browser.close()

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
