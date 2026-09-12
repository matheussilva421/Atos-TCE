"""Verify painted PDF pixels, including the manual menu's authenticated route."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest

import pymupdf
from playwright.sync_api import sync_playwright

from html_generator import build_interface_payload, render_html
import test_html_generator
from test_local_service import create_server
from analysis_pipeline import write_visual_evidence


PAINTED_PDF = """() => {
  const canvas = document.querySelector('#pdf-canvas');
  if (!canvas || !canvas.checkVisibility() || canvas.width < 400) return false;
  const pixels = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
  let ink = 0, paper = 0;
  for (let i = 0; i < pixels.length; i += 4) {
    if (pixels[i+3] < 250) continue;
    if (pixels[i] < 100 && pixels[i+1] < 100 && pixels[i+2] < 100) ink++;
    if (pixels[i] > 240 && pixels[i+1] > 240 && pixels[i+2] > 240) paper++;
  }
  return ink > 500 && paper > 10000;
}"""


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


class ManualReviewBrowserTests(unittest.TestCase):
    def _exercise(self, *, authenticated, missing_assets=False):
        with tempfile.TemporaryDirectory(prefix='tce-manual-pdf-') as temporary:
            package = Path(temporary)
            manifest, checkpoint, index = test_html_generator.HtmlGeneratorTests()._write_all_documents_fixture(package)
            indexed = json.loads(index.read_text(encoding='utf-8'))
            for event in indexed['processes'][0]['events']:
                event['event_id'] = 'portal-' + str(event['event'])
            index.write_text(json.dumps(indexed), encoding='utf-8')
            archive = package / 'acervo-tce'
            for pdf_path in archive.rglob('*.pdf'):
                with pymupdf.open() as pdf:
                    pdf.new_page().insert_text((60, 100), 'PDF VISIVEL - DOCUMENTO DE TESTE', fontsize=22)
                    pdf_path.write_bytes(pdf.tobytes())
            shutil.copy2(manifest, archive / 'pdfs-alvo-manifest.json')
            shutil.copy2(checkpoint, archive / 'checkpoint-extracao.json')
            shutil.copy2(index, archive / 'indice-classificado.json')
            payload = build_interface_payload(manifest, checkpoint, archive_index_path=index)
            write_visual_evidence(manifest, checkpoint, archive / 'evidencias-visuais.json')
            (archive / 'complementar-ato.html').write_text(render_html(payload), encoding='utf-8')
            shutil.copytree(Path(__file__).parent / 'portable/app/web', package / 'app/web')
            server = (create_server(archive, port=0) if authenticated else
                      ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(package))))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    try:
                        page = browser.new_page()
                        api_requests = []
                        page.on('request', lambda request: api_requests.append(request.url)
                                if '/api/v1/review-data' in request.url else None)
                        if missing_assets:
                            page.route('**/web/**', lambda route: route.abort())
                        suffix = (f'/review#bootstrap={server.review_bootstrap_code}' if authenticated
                                  else '/acervo-tce/complementar-ato.html')
                        page.goto(f'http://127.0.0.1:{server.server_port}{suffix}', wait_until='networkidle')
                        if missing_assets:
                            self.assertIn('indisponível', page.locator('#review-mode-note').inner_text())
                            self.assertFalse(page.evaluate(PAINTED_PDF), 'Missing assets must never pass the PDF gate')
                        else:
                            page.wait_for_function(PAINTED_PDF, timeout=10000)
                            self.assertEqual(page.locator('#live-status').inner_text(), 'Modo manual · dados locais')
                            self.assertEqual(api_requests, [], 'Manual HTML must not poll an automation publication')
                            page.select_option('#document-select', '1')
                            page.wait_for_function(PAINTED_PDF)
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)
                if authenticated:
                    server.workflow_state.close()

    def test_manual_menu_route_renders_pdf_without_automation_publication(self):
        self._exercise(authenticated=True)

    def test_static_manual_html_renders_pdf_without_live_polling(self):
        self._exercise(authenticated=False)

    def test_missing_pdfjs_cannot_pass_the_visual_gate(self):
        self._exercise(authenticated=False, missing_assets=True)


if __name__ == '__main__':
    unittest.main()
