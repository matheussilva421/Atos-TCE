"""Supervised, non-submitting fill check against the already-open project Chrome."""

from __future__ import annotations

import argparse
import json
from typing import Any

from playwright.sync_api import sync_playwright


CDP_URL = "http://127.0.0.1:63097"
PORTAL_ORIGIN = "https://novaarearestrita.tce.rn.gov.br/"
FORM_PREFIX = PORTAL_ORIGIN + "SISTEMAS/PROCESSO/ComplementarAto.asp?"
FIELD_IDS = (
    "txtModalidade",
    "txtFundamentoLegal",
    "txtDataDOE",
    "txtCargo",
    "txtMatricula",
    "txtDataNascimento",
    "txtGenero",
)


def _value(locator: Any) -> dict[str, str]:
    value = locator.input_value()
    selected = ""
    if locator.evaluate("element => element.tagName === 'SELECT'"):
        selected = locator.locator("option:checked").inner_text()
    return {"value": value, "label": selected}


def _frame_values(frame: Any) -> dict[str, dict[str, str]]:
    return {field_id: _value(frame.locator(f"#{field_id}")) for field_id in FIELD_IDS}


def _open_pages(browser: Any) -> tuple[Any, Any, Any]:
    pages = [page for context in browser.contexts for page in context.pages]
    panel = next(page for page in pages if page.url.endswith("/sidepanel/panel.html"))
    portal = next(page for page in pages if page.url.startswith(PORTAL_ORIGIN))
    frame = next(frame for frame in portal.frames if frame.url.startswith(FORM_PREFIX))
    return panel, portal, frame


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fill", action="store_true", help="click the explicit fill button")
    parser.add_argument("--restore-empty", action="store_true", help="restore the pre-test empty documentary fields")
    parser.add_argument("--process", default="101440/2026")
    args = parser.parse_args()

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(CDP_URL)
        panel, portal, frame = _open_pages(browser)
        before = _frame_values(frame)
        result: dict[str, object] = {
            "process": args.process,
            "portal_url_before": portal.url,
            "form_url_before": frame.url,
            "fill_enabled": panel.locator("#fill-button").is_enabled(),
            "before": before,
        }
        if args.fill:
            if not result["fill_enabled"]:
                raise AssertionError("Preencher campos disponíveis está desabilitado")
            panel.locator("#fill-button").click()
            panel.wait_for_function(
                "() => document.querySelector('#screen-status')?.textContent.includes('Preenchimento')",
                timeout=10_000,
            )
            panel, portal, frame = _open_pages(browser)
            after = _frame_values(frame)
            result.update(
                {
                    "portal_url_after": portal.url,
                    "form_url_after": frame.url,
                    "after": after,
                    "status": panel.locator("#screen-status").inner_text(),
                    "navigated": portal.url != result["portal_url_before"]
                    or frame.url != result["form_url_before"],
                }
            )
            if result["navigated"]:
                raise AssertionError("o preenchimento navegou no portal")
            if before == after:
                raise AssertionError("nenhum campo documental foi preenchido")
        if args.restore_empty:
            for field_id in FIELD_IDS:
                locator = frame.locator(f"#{field_id}")
                if locator.evaluate("element => element.tagName === 'SELECT'"):
                    locator.select_option(value="")
                else:
                    locator.fill("")
                locator.dispatch_event("change")
            restored = _frame_values(frame)
            if any(item["value"] for item in restored.values()):
                raise AssertionError(f"campos não restaurados: {restored}")
            result["restored_empty"] = True
            result["restored"] = restored
        print(json.dumps(result, ensure_ascii=False, indent=2))
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
