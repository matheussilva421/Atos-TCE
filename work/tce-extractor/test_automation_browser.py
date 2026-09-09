"""Browser qualification against the disposable local portal simulator.

The test drives the real extension content scripts from an extension page in
Chrome. It is intentionally synthetic: no authenticated profile, real portal,
remote click, or real submission is involved.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - environment-dependent gate
    sync_playwright = None  # type: ignore[assignment]

from test_extension_browser import (
    ALLOWED_URL,
    EXTENSION,
    FixtureServer,
    _close_context,
    _extension_id,
    _open_context,
)


ROOT = Path(__file__).resolve().parent
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "automatic-portal"


def _message(message_type: str, payload: dict, request_id: str) -> dict:
    return {
        "schemaVersion": 1,
        "type": message_type,
        "requestId": request_id,
        "payload": payload,
    }


@unittest.skipIf(sync_playwright is None, "Playwright não está disponível")
class AutomationBrowserTests(unittest.TestCase):
    def test_simulated_pages_frames_and_send_block(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tce-automation-browser-") as directory:
            scratch = Path(directory)
            with FixtureServer(FIXTURE_ROOT, scratch / "tls"):
                with sync_playwright() as playwright:
                    executable_path = Path(playwright.chromium.executable_path)
                    context = _open_context(
                        playwright,
                        scratch / "chrome-profile",
                        EXTENSION,
                        executable_path,
                    )
                    try:
                        portal = context.new_page()
                        portal.goto(f"{ALLOWED_URL}simulator.html", wait_until="domcontentloaded")
                        extension_id = _extension_id(context)
                        extension_page = context.new_page()
                        extension_page.goto(
                            f"chrome-extension://{extension_id}/sidepanel/panel.html",
                            wait_until="domcontentloaded",
                        )

                        def send_to_portal(message: dict, frame_id: int | None = 0) -> dict:
                            portal.bring_to_front()
                            return extension_page.evaluate(
                                """async ({ message, frameId }) => {
                                  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
                                  if (!tab?.id) throw new Error("simulated portal tab is not active");
                                  return chrome.tabs.sendMessage(
                                    tab.id,
                                    message,
                                    Number.isSafeInteger(frameId) ? { frameId } : undefined,
                                  );
                                }""",
                                {"message": message, "frameId": frame_id},
                            )

                        initial = send_to_portal(
                            _message("PORTAL_GET_SNAPSHOT", {}, "browser-simulated-snapshot-1")
                        )
                        self.assertTrue(initial["ok"])
                        self.assertEqual(initial["payload"]["role"], "list")
                        self.assertEqual(len(initial["payload"]["identities"]), 3)
                        self.assertEqual(
                            sum(identity.get("pending") is True for identity in initial["payload"]["identities"]),
                            1,
                        )

                        moved = send_to_portal(
                            _message(
                                "PORTAL_NAVIGATE",
                                {"action": "next_page", "expected_generation": initial["payload"]["generation"], "timeoutMs": 2_000},
                                "browser-simulated-next-1",
                            )
                        )
                        self.assertTrue(moved.get("ok"), moved)
                        self.assertEqual(moved["snapshot"]["identities"][0]["processKey"], "103403/2024")

                        returned_first = send_to_portal(
                            _message(
                                "PORTAL_NAVIGATE",
                                {"action": "next_page", "expected_generation": moved["snapshot"]["generation"], "timeoutMs": 2_000},
                                "browser-simulated-first-1",
                            )
                        )
                        self.assertTrue(returned_first["ok"])
                        target = returned_first["snapshot"]["identities"][0]

                        opened = send_to_portal(
                            _message(
                                "PORTAL_NAVIGATE",
                                {"action": "open_act", "expected_generation": returned_first["snapshot"]["generation"], "identity": target, "timeoutMs": 2_000},
                                "browser-simulated-open-1",
                            )
                        )
                        self.assertTrue(opened.get("ok"), opened)
                        self.assertEqual(opened["snapshot"]["role"], "interested")
                        selected_identity = opened["snapshot"]["identities"][0]
                        selected = send_to_portal(
                            _message(
                                "PORTAL_NAVIGATE",
                                {"action": "select_interested", "expected_generation": opened["snapshot"]["generation"], "identity": selected_identity, "timeoutMs": 2_000},
                                "browser-simulated-select-1",
                            )
                        )
                        self.assertTrue(selected.get("ok"), selected)
                        self.assertTrue(selected["snapshot"]["identities"][0]["selected"])
                        back = send_to_portal(
                            _message(
                                "PORTAL_NAVIGATE",
                                {"action": "return_list", "expected_generation": selected["snapshot"]["generation"], "timeoutMs": 2_000},
                                "browser-simulated-return-1",
                            )
                        )
                        self.assertTrue(back["ok"])
                        self.assertEqual(back["snapshot"]["role"], "list")

                        form_frame_id = None
                        form_snapshot = None
                        form_portal_snapshot = None
                        for candidate_frame_id in range(0, 8):
                            try:
                                candidate = send_to_portal(
                                    _message("GET_FORM_SNAPSHOT", {}, f"browser-simulated-form-{candidate_frame_id}"),
                                    candidate_frame_id,
                                )
                                if candidate.get("ok") and candidate.get("payload", {}).get("process"):
                                    form_frame_id = candidate_frame_id
                                    form_snapshot = candidate["payload"]
                                    form_portal_snapshot = send_to_portal(
                                        _message("PORTAL_GET_SNAPSHOT", {}, f"browser-simulated-frame-{candidate_frame_id}"),
                                        candidate_frame_id,
                                    )["payload"]
                                    break
                            except Exception:
                                continue

                        self.assertIsNotNone(form_frame_id)
                        self.assertEqual(len(form_snapshot["fields"]), 7)
                        self.assertEqual(form_snapshot["process"]["key"], "SYN-0001/2099")
                        self.assertEqual(form_portal_snapshot["role"], "form")
                        expected_fields_hash = hashlib.sha256(
                            json.dumps(
                                {
                                    field: str(form_snapshot["fields"][field]["value"] or "")
                                    for field in sorted(form_snapshot["fields"])
                                },
                                ensure_ascii=False,
                                sort_keys=True,
                                separators=(",", ":"),
                            ).encode("utf-8")
                        ).hexdigest()

                        blocked = send_to_portal(
                            _message(
                                "AUTO_SUBMIT_COMMAND",
                                {
                                    "runId": "run-without-service",
                                    "expectedRevision": 0,
                                    "command": {
                                        "command_id": "browser-simulated-command",
                                        "state": "issued",
                                        "expires_at": int(time.time() * 1_000) + 10_000,
                                        "frame_id": form_frame_id,
                                        "generation": form_portal_snapshot["generation"],
                                        "expected_fields_hash": expected_fields_hash,
                                        "button_id": "btnComplementar",
                                        "identity": {
                                            "processKey": form_snapshot["process"]["key"],
                                            "interestedNormalized": form_snapshot["interested"]["normalized"],
                                            "portalActId": None,
                                        },
                                    },
                                },
                                "browser-simulated-submit-1",
                            ),
                            form_frame_id,
                        )
                        self.assertFalse(blocked["ok"])
                        self.assertIn(blocked["error"]["code"], {"SUBMIT_BLOCKED", "COMMAND_ALREADY_CONSUMED"})
                        self.assertEqual(
                            portal.frame(url=lambda url: url.endswith("/form.html")).locator("#btnComplementar").get_attribute("data-click-count"),
                            "0",
                        )
                    finally:
                        _close_context(context, None)


if __name__ == "__main__":
    unittest.main()
