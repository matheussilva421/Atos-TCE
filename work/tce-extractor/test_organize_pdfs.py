import json
import tempfile
import unittest
from pathlib import Path

from organize_pdfs import organize_pdf_files, parse_pdf_name


class OrganizePdfsTests(unittest.TestCase):
    def test_parses_extension_file_name_without_analyzing_pdf(self):
        self.assertEqual(parse_pdf_name("103439-2023-evento-9.pdf"), ("103439/2023", "9"))
        self.assertIsNone(parse_pdf_name("documento-sem-processo.pdf"))

    def test_copies_only_pdf_signatures_and_writes_manifest_for_all_processes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            incoming = root / "incoming"
            organized = root / "organized"
            incoming.mkdir()
            (incoming / "103439-2023-evento-9.pdf").write_bytes(b"%PDF-1.7\nbody")
            (incoming / "erro.tmp").write_bytes(b"500 - Internal server error")
            manifest = root / "manifest.json"

            summary = organize_pdf_files(
                incoming,
                organized,
                manifest,
                processes=["103439/2023", "103442/2023"],
            )

            self.assertEqual(summary, {"files_seen": 2, "pdfs_organized": 1, "unrecognized": 0})
            copied = organized / "103439-2023" / "evento-0009.pdf"
            self.assertTrue(copied.exists())
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["processes"]), 2)
            self.assertEqual(payload["processes"][0]["documents"][0]["event"], "9")
            self.assertEqual(payload["processes"][1]["documents"], [])
            self.assertNotIn("Carimba_PDF", manifest.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
