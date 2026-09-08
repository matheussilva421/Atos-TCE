"""Browser integration checks for the authenticated live review desk."""

from __future__ import annotations

import json
import time
import unittest

from playwright.sync_api import sync_playwright

from test_local_service import json_request, running_server


def review_payload() -> dict:
    processes = []
    for process_key, interested in (
        ("103439/2023", "MARIA DE SOUZA"),
        ("103487/2023", "JOÃO DA SILVA"),
    ):
        processes.append(
            {
                "process": process_key,
                "status": "partial",
                "documents": [],
                "all_documents": [],
                "blocks": [{"interested": interested, "pending": [], "fields": {}}],
            }
        )
    return {
        "live_revision": 1,
        "run_id": "fixture-live",
        "processes": processes,
        "stats": {
            "processes": 2,
            "documents": 0,
            "priority_documents": 0,
            "all_documents": 0,
            "found": 0,
            "conflicts": 0,
            "pending": 0,
        },
    }


class ReviewLiveBrowserTests(unittest.TestCase):
    def test_authenticated_desk_follows_selection_and_manual_pause_resume(self):
        with running_server() as (root, server, base):
            publication = root / "publicacoes" / "1"
            publication.mkdir(parents=True)
            (root / "publicacao-atual.json").write_text(
                json.dumps({"schema_version": 1, "revision": 1}), encoding="utf-8"
            )
            (publication / "review-data.json").write_text(
                json.dumps(review_payload(), ensure_ascii=False), encoding="utf-8"
            )
            code = server.review_bootstrap_code
            pairing_code = server.auth.issue_pairing_code()
            _status, _headers, pair_body = json_request(
                f"{base}/api/v1/pair",
                method="POST",
                payload={"code": pairing_code},
                origin="chrome-extension://test-extension",
            )
            token = json.loads(pair_body)["token"]

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    executable_path=playwright.chromium.executable_path,
                    headless=True,
                    args=["--disable-gpu"],
                )
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                page.set_default_timeout(5_000)
                try:
                    page.goto(
                        f"{base}/review#bootstrap={code}",
                        wait_until="networkidle",
                    )
                    page.locator("#process-heading").wait_for()
                    self.assertEqual(page.locator("#process-heading").inner_text(), "103439/2023")

                    started = time.monotonic()
                    json_request(
                        f"{base}/api/v1/selection",
                        method="POST",
                        token=token,
                        payload={
                            "process_key": "103487/2023",
                            "interested_normalized": "joao da silva",
                            "tab_id": 1,
                            "frame_id": 0,
                            "sequence": 1,
                        },
                    )
                    page.locator("#process-heading").filter(has_text="103487/2023").wait_for()
                    self.assertLess(time.monotonic() - started, 2.0)
                    self.assertEqual(page.locator("#live-status").inner_text(), "Sincronização ativa")

                    page.select_option("#process-select", label="103439/2023 · MARIA DE SOUZA")
                    self.assertEqual(page.locator("#follow-toggle").inner_text(), "Retomar acompanhamento")
                    json_request(
                        f"{base}/api/v1/selection",
                        method="POST",
                        token=token,
                        payload={
                            "process_key": "103487/2023",
                            "interested_normalized": "joao da silva",
                            "tab_id": 1,
                            "frame_id": 0,
                            "sequence": 2,
                        },
                    )
                    page.wait_for_timeout(1_200)
                    self.assertEqual(page.locator("#process-heading").inner_text(), "103439/2023")

                    page.locator("#follow-toggle").click()
                    page.locator("#process-heading").filter(has_text="103487/2023").wait_for()
                finally:
                    browser.close()


if __name__ == "__main__":
    unittest.main()
