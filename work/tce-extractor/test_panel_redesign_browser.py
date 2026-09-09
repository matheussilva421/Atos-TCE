"""Responsive and accessibility smoke for the synthetic redesign panel.

This test serves only the view component with sanitized fixture data. It does
not load the extension, the local service, or the authenticated portal.
Screenshots are temporary evidence and are not written to the repository.
"""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import tempfile
import threading
import unittest

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - environment-dependent gate
    sync_playwright = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parent
EXTENSION = ROOT / "portable" / "extensao-complementar-ato"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def _fixture_html() -> str:
    return """<!doctype html>
<html lang="pt-BR"><head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="panel-tokens.css">
  <link rel="stylesheet" href="panel.css">
</head><body><main id="preview" class="panel-view-root"></main>
<script type="module">
import { buildPanelViewModel, renderPanelView } from './panel-view.js';
const fields = Object.fromEntries([
  ['modalidade', 'Aposentadoria voluntária'],
  ['fundamento_legal', 'Art. 6º da EC 41/2003 com referência documental extensa'],
  ['data_publicacao_doe', '07/02/2020'],
  ['cargo', 'PROFESSOR PN - IV'],
  ['matricula', '103.870-2/1'],
  ['data_nascimento', '30/04/1967'],
  ['genero', 'Feminino'],
].map(([id, value]) => [id, {
  source_value: value, form_value: value, status: 'found', confidence: 'high',
  citation: { page: 2, document: 'fixture-sanitizada.pdf' },
}]));
const record = {
  process: { key: '103439/2023' },
  interested: { original: 'Nome sintético para validação visual', normalized: 'nome sintetico para validacao visual' },
  fields,
};
const snapshot = {
  process: { key: '103439/2023' },
  interested: record.interested,
  fields: Object.fromEntries(Object.keys(fields).map((id) => [id, { value: fields[id].form_value, disabled: false, readOnly: false }])),
};
const matches = {
  fundamento_legal: {
    kind: 'probable', optionValue: 'fixture-option', optionLabel: 'Fundamento documental por semelhança',
    legalDecision: { method: 'similarity', reasons: ['texto sintético da fixture'] },
  },
};
const run = {
  run_id: 'run-fixture-1', status: 'paused',
  spec: { sector: 'setor sintético' },
  last_confirmed_item_id: 'item-001',
  items: [{ item_id: 'item-002', state: 'unconfirmed', identity: { processKey: '103439/2023' } }],
};
const history = [{ run_id: 'run-fixture-1', created_at: '2026-09-09T12:00:00Z', state: 'paused', totals: { confirmed: 1 } }];
window.showView = (selectedView) => renderPanelView(
  document.querySelector('#preview'),
  buildPanelViewModel({ record, snapshot, matches, run, history,
    connection: { connected: true, automationAvailable: true }, selectedView, mode: 'automatic' }),
  {},
);
window.showView('current');
</script></body></html>"""


@unittest.skipIf(sync_playwright is None, "Playwright não está disponível")
class PanelRedesignBrowserTests(unittest.TestCase):
    def test_responsive_tabs_fields_and_synthetic_screenshots(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tce-panel-redesign-") as directory:
            root = Path(directory)
            (root / "panel.html").write_text(_fixture_html(), encoding="utf-8")
            for name in ("panel-view.js", "panel.css", "panel-tokens.css"):
                shutil.copy2(EXTENSION / "sidepanel" / name, root / name)
            handler = partial(_QuietHandler, directory=str(root))
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with sync_playwright() as playwright:
                    launch_options = {"headless": True}
                    if CHROME.is_file():
                        launch_options["executable_path"] = str(CHROME)
                    try:
                        browser = playwright.chromium.launch(**launch_options)
                    except Exception as error:  # pragma: no cover - machine-dependent
                        self.skipTest(f"Chrome/Playwright indisponível: {error}")
                    page = browser.new_page(viewport={"width": 640, "height": 900})
                    try:
                        page.goto(f"http://127.0.0.1:{server.server_port}/panel.html", wait_until="networkidle")
                        self.assertEqual(page.locator('[role="tab"]').count(), 3)
                        self.assertEqual(page.locator('[role="tabpanel"]').count(), 1)
                        self.assertEqual(page.locator("#fields-list [data-field]").count(), 7)
                        self.assertIn("Fundamentação", page.locator("#panel-current").inner_text())

                        for width in (320, 360, 480, 640):
                            page.set_viewport_size({"width": width, "height": 900})
                            page.evaluate("window.showView('current')")
                            metrics = page.evaluate(
                                """() => ({
                                  page_scroll: document.documentElement.scrollWidth,
                                  page_client: document.documentElement.clientWidth,
                                  fields: document.querySelectorAll('#fields-list [data-field]').length,
                                  selected: document.querySelector('[role=tab][aria-selected=true]')?.id,
                                })"""
                            )
                            self.assertLessEqual(metrics["page_scroll"], metrics["page_client"] + 1)
                            self.assertEqual(metrics["fields"], 7)
                            self.assertEqual(metrics["selected"], "tab-current")
                            page.screenshot(path=str(root / f"panel-{width}.png"), full_page=True)
                            if width == 360:
                                page.evaluate("document.body.style.fontSize = '200%'")
                                scaled = page.evaluate(
                                    """() => ({
                                      page_scroll: document.documentElement.scrollWidth,
                                      page_client: document.documentElement.clientWidth,
                                    })"""
                                )
                                self.assertLessEqual(scaled["page_scroll"], scaled["page_client"] + 1)
                                page.evaluate("document.body.style.fontSize = ''")

                        page.locator("#tab-current").focus()
                        page.keyboard.press("End")
                        self.assertEqual(page.evaluate("document.activeElement.id"), "tab-history")
                        page.evaluate("window.showView('execution')")
                        self.assertIn("Execução", page.locator("#panel-execution").inner_text())
                        self.assertIn("incertos", page.locator("#panel-execution").inner_text())
                        page.evaluate("window.showView('history')")
                        self.assertIn("Histórico", page.locator("#panel-history").inner_text())
                        self.assertEqual(page.locator("#panel-history button").count(), 2)
                    finally:
                        page.close()
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
