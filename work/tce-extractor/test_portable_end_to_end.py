import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from package_complete_archive import EXTENSION_FILE_ALLOWLIST, build_complete_zip


ROOT = Path(__file__).parent


def _make_pdf(path: Path, text: str, *, scanned: bool) -> None:
    import pymupdf

    source = pymupdf.open()
    page = source.new_page(width=1000, height=1400)
    page.insert_textbox(
        pymupdf.Rect(60, 60, 940, 1340), text, fontsize=28, fontname="helv"
    )
    if not scanned:
        source.save(path)
        source.close()
        return
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
    png = pixmap.tobytes("png")
    source.close()
    scanned_pdf = pymupdf.open()
    scanned_page = scanned_pdf.new_page(width=1000, height=1400)
    scanned_page.insert_image(scanned_page.rect, stream=png)
    scanned_pdf.save(path)
    scanned_pdf.close()


def _write_event(process_dir: Path, archive: Path, number: int, event_id: str, title: str, pdf: Path) -> dict:
    event_dir = process_dir / f"evento-{number:04d}-{event_id}"
    event_dir.mkdir()
    destination = event_dir / pdf.name
    shutil.copyfile(pdf, destination)
    event = {
        "event": number,
        "event_id": str(event_id),
        "date": "2000-01-01T00:00:00",
        "title": title,
        "active": True,
        "documents": [{
            "id": f"doc-{event_id}",
            "title": title,
            "extension": ".pdf",
            "path": destination.relative_to(archive).as_posix(),
            "status": "complete",
        }],
    }
    (event_dir / "evento.json").write_text(json.dumps(event), encoding="utf-8")
    return event


def _build_fixture_zip(root: Path) -> tuple[Path, dict[str, object]]:
    source = root / "source-package"
    app = source / "app"
    app.mkdir(parents=True)
    app_sources = {
        "archive_index.py": ROOT / "portable" / "app" / "archive_index.py",
        "analysis_pipeline.py": ROOT / "portable" / "app" / "analysis_pipeline.py",
        "runtime_paths.py": ROOT / "portable" / "app" / "runtime_paths.py",
        "package_audit.py": ROOT / "portable" / "app" / "package_audit.py",
        "extension_exporter.py": ROOT / "portable" / "app" / "extension_exporter.py",
        "package_complete_archive.py": ROOT / "package_complete_archive.py",
        "batch_runner.py": ROOT / "batch_runner.py",
        "html_generator.py": ROOT / "html_generator.py",
        "tce_extractor.py": ROOT / "tce_extractor.py",
    }
    for name, source_path in app_sources.items():
        shutil.copyfile(source_path, app / name)

    extension_source = ROOT / "portable" / "extensao-complementar-ato"
    for relative in EXTENSION_FILE_ALLOWLIST:
        destination = source / "extensao-complementar-ato" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(extension_source / relative, destination)

    runtime_files = {
        "runtime/python/python.exe": b"python-fixture",
        "runtime/tesseract/tesseract.exe": b"tesseract-fixture",
        "runtime/tesseract/tessdata/por.traineddata": b"por-fixture",
        "runtime/tesseract/tessdata/eng.traineddata": b"eng-fixture",
    }
    manifest_entries = []
    for relative, contents in runtime_files.items():
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        manifest_entries.append({
            "path": relative,
            "size": len(contents),
            "sha256": hashlib.sha256(contents).hexdigest(),
        })
    license_file = source / "licenses" / "README.md"
    license_file.parent.mkdir(parents=True)
    license_file.write_text("Licenças fixture", encoding="utf-8")
    license_bytes = license_file.read_bytes()
    manifest_entries.append({
        "path": "licenses/README.md",
        "size": len(license_bytes),
        "sha256": hashlib.sha256(license_bytes).hexdigest(),
    })
    (source / "runtime-manifest.json").write_text(
        json.dumps({"schema_version": 1, "build": {"included_files": manifest_entries}}),
        encoding="utf-8",
    )

    archive = source / "acervo-tce"
    process_dir = archive / "processos" / "fixture-process"
    process_dir.mkdir(parents=True)
    (archive / "dados-complementar-ato.json").write_text(
        '{"records":[]}', encoding="utf-8"
    )
    resolution_text = (
        "RESOLUCAO ADMINISTRATIVA N 1, DE 01 DE JANEIRO DE 2000.\n"
        "Concede aposentadoria voluntaria por tempo de contribuicao.\n"
        "PESSOA TESTE DA SILVA no cargo de PROFESSOR PN - I, "
        "Classe A, matricula 000.000-0/0."
    )
    guide_text = (
        "GUIA FINANCEIRA - TAXACAO DE PROVENTOS\n"
        "COMPOSICAO DA REMUNERACAO\n"
        "PESSOA TESTE DA SILVA\n"
        "Data de nascimento: 01/01/2000\nMatricula: 000.000-0/0\nGenero: Feminino"
    )
    resolution_source = root / "resolution-fixture.pdf"
    guide_source = root / "guide-fixture.pdf"
    _make_pdf(resolution_source, resolution_text, scanned=True)
    _make_pdf(guide_source, guide_text, scanned=False)
    events = [
        _write_event(process_dir, archive, 2, "fixture-alpha", "Resolução Administrativa", resolution_source),
        _write_event(process_dir, archive, 3, "fixture-beta", "Guia Financeira - Taxação de Proventos", guide_source),
    ]
    process = {
        "key": "0/0000",
        "id": "fixture-process",
        "number": "0",
        "year": 0,
        "status": "complete",
        "events": events,
    }
    (process_dir / "processo.json").write_text(json.dumps(process), encoding="utf-8")

    destination = root / "fixture-package.zip"
    stats = build_complete_zip(source, destination, distribution="private")
    return destination, {**stats, "resolution_text": resolution_text}


class PortableEndToEndTests(unittest.TestCase):
    def test_packaging_sources_expose_public_extension_and_private_distribution_contract(self):
        packager = (ROOT / "empacotar-coletor-portatil.ps1").read_text(
            encoding="utf-8-sig"
        )
        self.assertIn("$extensionFiles", packager)
        self.assertIn("extension_exporter.py", packager)
        self.assertIn("package_complete_archive.py", packager)
        self.assertIn("extensao-complementar-ato", packager)

        private_packager = (ROOT / "portable" / "Empacotar-Acervo-Completo.ps1").read_text(
            encoding="utf-8-sig"
        )
        self.assertIn("dados-complementar-ato.json", private_packager)

    def test_self_contained_zip_pipeline_generates_html_and_reuses_ocr_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture_zip, fixture = _build_fixture_zip(root)
            package = root / "package"
            with zipfile.ZipFile(fixture_zip) as archive_zip:
                archive_zip.extractall(package)

            self.assertEqual(fixture["processes"], 1)
            self.assertEqual(fixture["events"], 2)
            self.assertEqual(fixture["pdfs"], 2)

            embedded_python = package / "runtime" / "python" / "python.exe"
            cli = package / "app" / "analysis_pipeline.py"
            self.assertTrue(embedded_python.is_file())
            help_result = subprocess.run(
                [sys.executable, "-s", str(cli), "--help"],
                cwd=package,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            self.assertEqual(help_result.returncode, 0, help_result.stderr)
            self.assertIn("--archive-root", help_result.stdout)

            archive = package / "acervo-tce"
            app_path = str(package / "app")
            previous = list(sys.path)
            dependency_names = (
                "archive_index",
                "batch_runner",
                "extension_exporter",
                "html_generator",
                "tce_extractor",
            )
            saved_modules = {
                name: sys.modules.pop(name)
                for name in dependency_names
                if name in sys.modules
            }
            sys.path.insert(0, app_path)
            try:
                spec = importlib.util.spec_from_file_location(
                    "portable_e2e_pipeline", package / "app" / "analysis_pipeline.py"
                )
                module = importlib.util.module_from_spec(spec)
                assert spec.loader is not None
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)
                batch_runner = sys.modules["batch_runner"]
                tesseract = package / "runtime" / "tesseract" / "tesseract.exe"
                tessdata = package / "runtime" / "tesseract" / "tessdata"

                def extract_fixture_pages(path, **_kwargs):
                    if Path(path).name == "resolution-fixture.pdf":
                        return [fixture["resolution_text"]]
                    return module._native_pdf_pages(Path(path))

                with patch.object(
                    module, "_ocr_pdf_pages", return_value=[fixture["resolution_text"]]
                ), patch.object(
                    batch_runner, "extract_pdf_pages", side_effect=extract_fixture_pages
                ):
                    first = module.run_local_pipeline(
                        archive, tesseract=tesseract, tessdata=tessdata
                    )
                self.assertEqual(first.total_processes, 1)
                self.assertEqual(first.priority_documents, 2)
                cache_before = json.loads((archive / "cache-ocr.json").read_text(encoding="utf-8"))
                self.assertTrue(cache_before["entries"])
                with patch.object(
                    module,
                    "_ocr_pdf_pages",
                    side_effect=AssertionError("OCR não deve repetir para SHA/runtime idênticos"),
                ), patch.object(
                    batch_runner,
                    "extract_pdf_pages",
                    side_effect=extract_fixture_pages,
                ):
                    second = module.run_local_pipeline(
                        archive, tesseract=tesseract, tessdata=tessdata
                    )
                self.assertEqual(second.priority_documents, 2)
                cache_after = json.loads((archive / "cache-ocr.json").read_text(encoding="utf-8"))
                self.assertEqual(cache_before["entries"], cache_after["entries"])
                html = (archive / "complementar-ato.html").read_text(encoding="utf-8")
                self.assertIn("0/0000", html)
                self.assertIn("Evento 2", html)
                self.assertIn("p. 1", html)
            finally:
                sys.modules.pop("portable_e2e_pipeline", None)
                for name in dependency_names:
                    sys.modules.pop(name, None)
                sys.modules.update(saved_modules)
                sys.path[:] = previous


if __name__ == "__main__":
    unittest.main()
