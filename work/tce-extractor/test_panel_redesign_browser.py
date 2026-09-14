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
  <link rel="stylesheet" href="sidepanel/panel-tokens.css">
  <link rel="stylesheet" href="sidepanel/panel.css">
</head><body><main id="preview" class="panel-view-root"></main>
<nav class="panel-tabs" role="tablist" aria-label="Áreas do painel">
  <button id="tab-principal" type="button" role="tab" aria-controls="panel-tab-principal" aria-selected="false" tabindex="-1">Principal</button>
  <button id="tab-details" type="button" role="tab" aria-controls="panel-tab-details" aria-selected="true" tabindex="0">Detalhes</button>
  <button id="tab-automation" type="button" role="tab" aria-controls="panel-tab-automation" aria-selected="false" tabindex="-1">Automação</button>
  <button id="tab-execution" type="button" role="tab" aria-controls="panel-tab-execution" aria-selected="false" tabindex="-1">Execução</button>
  <button id="tab-history" type="button" role="tab" aria-controls="panel-tab-history" aria-selected="false" tabindex="-1">Histórico</button>
</nav>
<section id="panel-tab-principal" role="tabpanel" hidden></section>
<section id="panel-tab-details" role="tabpanel"><div id="details-preview"></div></section>
<section id="panel-tab-automation" role="tabpanel" hidden></section>
<section id="panel-tab-execution" role="tabpanel" hidden><div id="execution-preview"></div></section>
<section id="panel-tab-history" role="tabpanel" hidden><div id="history-preview"></div></section>
<script type="module">
import { buildPanelViewModel, renderPanelView } from './sidepanel/panel-view.js';
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
window.showView = (selectedView) => {
  const views = ['principal', 'details', 'automation', 'execution', 'history'];
  for (const view of views) {
    document.querySelector(`#panel-tab-${view}`).hidden = view !== selectedView;
    document.querySelector(`#tab-${view}`).setAttribute('aria-selected', String(view === selectedView));
  }
  renderPanelView(
    { details: document.querySelector('#details-preview'), execution: document.querySelector('#execution-preview'), history: document.querySelector('#history-preview') },
    buildPanelViewModel({ record, snapshot, matches, run, history,
      connection: { connected: true, automationAvailable: true }, selectedView, mode: 'automatic' }),
    {},
  );
};
window.showView('details');
</script></body></html>"""


@unittest.skipIf(sync_playwright is None, "Playwright não está disponível")
class PanelRedesignBrowserTests(unittest.TestCase):
    def test_responsive_tabs_fields_and_synthetic_screenshots(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tce-panel-redesign-") as directory:
            root = Path(directory)
            (root / "panel.html").write_text(_fixture_html(), encoding="utf-8")
            (root / "sidepanel").mkdir()
            (root / "lib").mkdir()
            for name in ("panel-view.js", "panel.css", "panel-tokens.css"):
                shutil.copy2(EXTENSION / "sidepanel" / name, root / "sidepanel" / name)
            shutil.copy2(EXTENSION / "lib" / "automation-preflight.js", root / "lib" / "automation-preflight.js")
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
                        self.assertEqual(page.locator('[role="tab"]').count(), 5)
                        self.assertEqual(page.locator('[role="tabpanel"]').count(), 5)
                        self.assertEqual(page.locator("#details-preview [data-field]").count(), 7)
                        self.assertIn("Fundamentação", page.locator("#details-preview").inner_text())

                        for width in (320, 360, 480, 640):
                            page.set_viewport_size({"width": width, "height": 900})
                            page.evaluate("window.showView('details')")
                            metrics = page.evaluate(
                                """() => ({
                                  page_scroll: document.documentElement.scrollWidth,
                                  page_client: document.documentElement.clientWidth,
                                  fields: document.querySelectorAll('#details-preview [data-field]').length,
                                  selected: document.querySelector('[role=tab][aria-selected=true]')?.id,
                                })"""
                            )
                            self.assertLessEqual(metrics["page_scroll"], metrics["page_client"] + 1)
                            self.assertEqual(metrics["fields"], 7)
                            self.assertEqual(metrics["selected"], "tab-details")
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

                        page.evaluate("window.showView('execution')")
                        self.assertIn("Execução", page.locator("#execution-preview").inner_text())
                        self.assertIn("incertos", page.locator("#execution-preview").inner_text())
                        page.evaluate("window.showView('history')")
                        self.assertIn("Histórico", page.locator("#history-preview").inner_text())
                        self.assertEqual(page.locator("#history-preview button").count(), 2)
                    finally:
                        page.close()
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
