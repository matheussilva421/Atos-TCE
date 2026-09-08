from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

from package_complete_archive import build_complete_zip
from test_portable_end_to_end import _build_fixture_zip

APP_ROOT = Path(__file__).parent / "portable" / "app"
import sys
sys.path.insert(0, str(APP_ROOT))
from prepare_transfer import prepare_transfer  # noqa: E402


class PrepareTransferTests(unittest.TestCase):
    def test_transfer_excludes_pairing_but_keeps_progress(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _fixture_zip, _fixture = _build_fixture_zip(root)
            package = root / "source-package"
            (package / "acervo-tce" / "progresso.json").write_text(
                '{"schema_version":1,"revision":0,"processes":{}}', encoding="utf-8"
            )
            bridge = package / "dados-locais" / "bridge"
            bridge.mkdir(parents=True)
            (bridge / "service.json").write_text('{"pid":123}', encoding="utf-8")
            destination = root / "transfer.zip"

            result = prepare_transfer(package, destination)

            self.assertTrue(result["progress_included"])
            self.assertFalse(result["bridge_state_included"])
            with zipfile.ZipFile(result["path"]) as archive:
                names = archive.namelist()
            self.assertIn("acervo-tce/progresso.json", names)
            self.assertFalse(any(name.startswith("dados-locais/") for name in names))

    def test_transfer_does_not_overwrite_existing_destination(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "transfer.zip"
            destination.write_bytes(b"existing")
            with self.assertRaises(FileExistsError):
                prepare_transfer(root / "missing-package", destination)


if __name__ == "__main__":
    unittest.main()
