"""Opt-in Chrome smoke for the extracted portable package.

The smoke uses a disposable Chrome profile, a synthetic local dataset and the
local bridge only. It never opens the real portal or submits an act.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - environment-dependent gate
    sync_playwright = None  # type: ignore[assignment]

from test_extension_browser import _close_context, _extension_id, _open_context


SMOKE_ROOT = os.environ.get("TCE_PORTABLE_SMOKE_ROOT")
PACKAGE_ROOT = Path(SMOKE_ROOT).resolve() if SMOKE_ROOT else None
SMOKE_PORT = os.environ.get("TCE_PORTABLE_SMOKE_PORT", "18743")


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _write_synthetic_publication(archive: Path) -> None:
    def field(value: str) -> dict[str, object]:
        return {
            "status": "found",
            "confidence": "high",
            "source_value": value,
            "form_value": value,
            "citation": {
                "process": "103439/2023",
                "event": "9",
                "page": 1,
                "document": "Resolucao_103439.pdf",
            },
        }

    records = [
        {
            "process": {"key": "103439/2023", "number": "103439", "year": "2023"},
            "interested": {"original": "Ana", "normalized": "ana"},
            "status": "found",
            "fields": {
                "modalidade": field("Aposentadoria voluntária"),
                "fundamento_legal": field("Art. 40"),
                "data_publicacao_doe": field("07/02/2020"),
                "cargo": field("PROFESSOR PN - IV"),
                "matricula": field("103.870-2/1"),
                "data_nascimento": field("30/04/1967"),
                "genero": field("Feminino"),
            },
        }
    ]
    dataset = {
        "schema_version": 1,
        "generated_at": "2026-09-09T12:00:00+00:00",
        "batch": {
            "id": "portable-browser-smoke",
            "logical_sha256": "",
            "process_count": 1,
            "record_count": 1,
            "process_keys": ["103439/2023"],
        },
        "records": records,
    }
    logical = {
        "schema_version": dataset["schema_version"],
        "batch_id": dataset["batch"]["id"],
        "process_keys": dataset["batch"]["process_keys"],
        "records": records,
    }
    dataset["batch"]["logical_sha256"] = hashlib.sha256(
        _canonical_json(logical)
    ).hexdigest()
    publication = archive / "publicacoes" / "1"
    publication.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(dataset, ensure_ascii=False)
    (archive / "dados-complementar-ato.json").write_text(payload, encoding="utf-8")
    (publication / "dataset.json").write_text(payload, encoding="utf-8")
    (archive / "publicacao-atual.json").write_text(
        json.dumps({"schema_version": 1, "revision": 1}),
        encoding="utf-8",
    )


@unittest.skipUnless(
    PACKAGE_ROOT is not None and PACKAGE_ROOT.is_dir() and sync_playwright is not None,
    "defina TCE_PORTABLE_SMOKE_ROOT e tenha Playwright para o smoke do ZIP",
)
class PortableZipBrowserSmokeTests(unittest.TestCase):
    def test_extracted_package_pairs_extension_and_reaches_capabilities(self) -> None:
        assert PACKAGE_ROOT is not None
        package = PACKAGE_ROOT.resolve()
        archive = package / "acervo-tce"
        bridge = package / "dados-locais" / "bridge"
        runtime_python = package / "runtime" / "python" / "python.exe"
        service_script = package / "app" / "local_service.py"
        extension = package / "extensao-complementar-ato"
        self.assertTrue(runtime_python.is_file())
        self.assertTrue(service_script.is_file())
        self.assertTrue((extension / "manifest.json").is_file())
        _write_synthetic_publication(archive)
        metadata_path = bridge / "service.json"
        metadata_path.unlink(missing_ok=True)

        process = subprocess.Popen(
            [
                str(runtime_python),
                "-B",
                str(service_script),
                "--root",
                str(archive),
                "--bridge-root",
                str(bridge),
                "--port",
                SMOKE_PORT,
            ],
            cwd=package / "app",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        metadata = None
        try:
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    self.fail("serviço portátil encerrou antes de publicar service.json")
                if metadata_path.is_file():
                    try:
                        candidate = json.loads(metadata_path.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        candidate = None
                    if isinstance(candidate, dict) and candidate.get("pairing_code"):
                        metadata = candidate
                        break
                time.sleep(0.05)
            self.assertIsNotNone(metadata)
            assert metadata is not None

            with tempfile.TemporaryDirectory(prefix="tce-portable-chrome-smoke-") as profile:
                with sync_playwright() as playwright:
                    context = _open_context(
                        playwright,
                        Path(profile),
                        extension,
                        Path(playwright.chromium.executable_path),
                    )
                    try:
                        extension_id = _extension_id(context)
                        panel = context.new_page()
                        panel.goto(
                            f"chrome-extension://{extension_id}/sidepanel/panel.html",
                            wait_until="domcontentloaded",
                        )
                        base_url = f"http://127.0.0.1:{metadata['port']}"
                        panel.locator("#bridge-base-url").fill(base_url)
                        panel.locator("#bridge-pairing-code").fill(
                            str(metadata["pairing_code"])
                        )
                        panel.locator("#bridge-connect-button").click()
                        panel.wait_for_function(
                            "() => document.querySelector('#bridge-status')?.textContent.includes('Mesa local conectada.')",
                            timeout=10_000,
                        )
                        self.assertIn(
                            "Mesa local conectada.",
                            panel.locator("#bridge-status").inner_text(),
                        )
                        token_stored = panel.evaluate(
                            """async () => {
                                const state = await chrome.storage.session.get(['bridge:token:v1']);
                                return typeof state['bridge:token:v1'] === 'string'
                                    && state['bridge:token:v1'].length > 0;
                            }"""
                        )
                        self.assertTrue(token_stored)
                    finally:
                        _close_context(context, None)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
