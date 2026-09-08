from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def choose_process(page, process_key: str) -> None:
    option = page.locator("#process-select option").filter(has_text=process_key).first
    value = option.get_attribute("value")
    if value is None:
        raise AssertionError(f"processo não encontrado: {process_key}")
    page.select_option("#process-select", value=value)
    page.wait_for_timeout(250)


def document_snapshot(page) -> dict[str, object]:
    frame = page.locator("#pdf-frame")
    return {
        "document_options": page.locator("#document-select option").count(),
        "document_value": page.locator("#document-select").input_value(),
        "frame_src": frame.get_attribute("src"),
        "canvas_display": page.locator("#pdf-canvas-stage").evaluate("el => getComputedStyle(el).display"),
        "frame_display": frame.evaluate("el => getComputedStyle(el).display"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", type=Path, required=True)
    parser.add_argument("--process", default="102885/2023")
    parser.add_argument("--screenshot", type=Path, required=True)
    args = parser.parse_args()

    args.screenshot.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=True,
            args=["--disable-gpu", "--allow-file-access-from-files"],
        )
        context = browser.new_context(viewport={"width": 900, "height": 1440})
        page = context.new_page()
        page.set_default_timeout(7_000)
        page.goto(args.html.resolve().as_uri(), wait_until="domcontentloaded")
        choose_process(page, args.process)

        initial_url = page.url
        initial_process = page.locator("#process-heading").inner_text()
        source_count = page.locator(".source-button").count()
        if source_count < 5:
            raise AssertionError(f"fontes de evidência insuficientes: {source_count}")

        manual_pause = {
            "text": page.locator("#follow-toggle").inner_text(),
            "pressed": page.locator("#follow-toggle").get_attribute("aria-pressed"),
        }
        page.locator("#follow-toggle").click()
        resumed = {
            "text": page.locator("#follow-toggle").inner_text(),
            "pressed": page.locator("#follow-toggle").get_attribute("aria-pressed"),
        }
        if resumed["text"] != "Acompanhar portal" or resumed["pressed"] != "true":
            raise AssertionError(f"retomada não confirmada: {resumed}")
        page.locator("#follow-toggle").click()
        paused = {
            "text": page.locator("#follow-toggle").inner_text(),
            "pressed": page.locator("#follow-toggle").get_attribute("aria-pressed"),
        }
        if paused["text"] != "Retomar acompanhamento" or paused["pressed"] != "false":
            raise AssertionError(f"pause não confirmado: {paused}")
        page.locator("#follow-toggle").click()

        page.wait_for_timeout(1_000)
        page.locator("#pdf-zoom-in").click()
        page.wait_for_timeout(150)
        zoom_in = {
            "label": page.locator("#pdf-zoom-label").inner_text(),
            "scale": page.locator("#pdf-canvas-stage").get_attribute("data-pdf-scale"),
        }
        if zoom_in != {"label": "175%", "scale": "1.75"}:
            raise AssertionError(f"zoom não confirmado: {zoom_in}")
        page.locator("#pdf-rotate").click()
        page.wait_for_timeout(150)
        rotation = page.locator("#pdf-canvas-stage").get_attribute("data-pdf-rotation")
        if rotation != "90":
            raise AssertionError(f"rotação não confirmada: {rotation}")
        page.locator("#pdf-view-reset").click()
        page.wait_for_timeout(150)
        reset_view = {
            "label": page.locator("#pdf-zoom-label").inner_text(),
            "rotation": page.locator("#pdf-canvas-stage").get_attribute("data-pdf-rotation"),
        }
        if reset_view != {"label": "150%", "rotation": "0"}:
            raise AssertionError(f"reset da visualização não confirmado: {reset_view}")

        evidence_results = []
        for index in range(source_count):
            buttons = page.locator(".source-button")
            buttons.nth(index).click()
            page.wait_for_timeout(150)
            snapshot = document_snapshot(page)
            if not snapshot["frame_src"] or "#page=" not in str(snapshot["frame_src"]):
                raise AssertionError(f"fonte {index + 1} não resolveu PDF/página: {snapshot}")
            evidence_results.append(snapshot)

        second = context.new_page()
        second.set_default_timeout(7_000)
        second.goto(args.html.resolve().as_uri(), wait_until="domcontentloaded")
        choose_process(second, args.process)
        second.select_option("#document-select", value="0")
        second.wait_for_timeout(150)
        first_tab_src = page.locator("#pdf-frame").get_attribute("src")
        second_tab_src = second.locator("#pdf-frame").get_attribute("src")
        if not first_tab_src or not second_tab_src:
            raise AssertionError("duas abas não exibiram PDF")
        if first_tab_src == second_tab_src:
            second.select_option("#document-select", value="1")
            second.wait_for_timeout(150)
            second_tab_src = second.locator("#pdf-frame").get_attribute("src")
        if first_tab_src == second_tab_src:
            raise AssertionError("duas abas não mantiveram PDFs distintos")

        page.locator("#process-done").check()
        page.wait_for_timeout(200)
        if not page.locator("#process-done").is_checked() or page.url != initial_url:
            raise AssertionError("Concluído alterou navegação ou não ficou marcado")
        page.reload(wait_until="domcontentloaded")
        choose_process(page, args.process)
        page.wait_for_timeout(2_000)
        if not page.locator("#process-done").is_checked():
            raise AssertionError("Concluído não persistiu após reload")
        page.screenshot(path=str(args.screenshot), full_page=False)

        print(
            json.dumps(
                {
                    "process": args.process,
                    "initial_process": initial_process,
                    "source_count": source_count,
                    "manual_selection_pause": manual_pause,
                    "pause": paused,
                    "resume": resumed,
                    "zoom_in": zoom_in,
                    "rotation": rotation,
                    "reset_view": reset_view,
                    "evidence_results": evidence_results,
                    "two_tabs": {"first": first_tab_src, "second": second_tab_src},
                    "completed_without_navigation": True,
                    "completed_after_reload": True,
                    "url": page.url,
                },
                ensure_ascii=False,
            )
        )
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
