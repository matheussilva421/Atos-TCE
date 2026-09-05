"""A new archive cycle must not inherit completed-process checkmarks."""
import json
from pathlib import Path
import tempfile
import unittest

from playwright.sync_api import sync_playwright
from html_generator import write_html


class HtmlCycleTests(unittest.TestCase):
    def test_non_integer_cycle_version_cannot_replace_existing_html(self):
        with tempfile.TemporaryDirectory(prefix="tce-cycle-version-") as folder:
            root = Path(folder)
            (root / "manifest.json").write_text('{"processes":[]}', encoding="utf-8")
            (root / "checkpoint.json").write_text('{"processes":{}}', encoding="utf-8")
            output = root / "index.html"
            for version in (True, 1.0, "1"):
                with self.subTest(version=version):
                    output.write_text("previous document", encoding="utf-8")
                    (root / "ciclo-acervo.json").write_text(
                        json.dumps({"version": version, "id": "a" * 32}), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        write_html(root / "manifest.json", root / "checkpoint.json", output)
                    self.assertEqual(output.read_text(encoding="utf-8"), "previous document")

    def test_invalid_cycle_marker_does_not_overwrite_existing_html(self):
        with tempfile.TemporaryDirectory(prefix="tce-cycle-") as folder:
            root = Path(folder)
            (root / "manifest.json").write_text('{"processes":[]}', encoding="utf-8")
            (root / "checkpoint.json").write_text('{"processes":{}}', encoding="utf-8")
            (root / "ciclo-acervo.json").write_text('{"version":1,"id":"invalid"}', encoding="utf-8")
            output = root / "index.html"
            output.write_text("previous document", encoding="utf-8")
            with self.assertRaises(ValueError):
                write_html(root / "manifest.json", root / "checkpoint.json", output)
            self.assertEqual(output.read_text(encoding="utf-8"), "previous document")

    def test_new_cycle_clears_checks_without_erasing_previous_cycle(self):
        with tempfile.TemporaryDirectory(prefix="tce-cycle-") as folder:
            root = Path(folder)
            manifest = root / "manifest.json"
            checkpoint = root / "checkpoint.json"
            output = root / "index.html"
            marker = root / "ciclo-acervo.json"
            manifest.write_text(json.dumps({"processes": [{"process": "1/2023", "documents": []}]}), encoding="utf-8")
            checkpoint.write_text('{"processes":{}}', encoding="utf-8")

            def generate(cycle):
                if cycle is not None:
                    marker.write_text(json.dumps({"version": 1, "id": cycle}), encoding="utf-8")
                write_html(manifest, checkpoint, output)

            generate(None)
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
                page = browser.new_page()
                page.goto(output.as_uri())
                page.check("#process-done")
                page.reload()
                self.assertTrue(page.locator("#process-done").is_checked())
                generate("a" * 32)
                page.reload()
                self.assertFalse(page.locator("#process-done").is_checked())
                page.check("#process-done")
                generate("a" * 32)
                page.reload()
                self.assertTrue(page.locator("#process-done").is_checked())
                generate("b" * 32)
                page.reload()
                self.assertFalse(page.locator("#process-done").is_checked())
                generate("a" * 32)
                page.reload()
                self.assertTrue(page.locator("#process-done").is_checked())
                browser.close()


if __name__ == "__main__":
    unittest.main()
