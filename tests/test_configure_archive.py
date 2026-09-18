"""Tests for the supported external archive configuration (CR-22)."""

import importlib.util
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.archive.manager import EXTERNAL_ROOT_KEY
from app.core.store import Store

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "configure-archive.py"

_MODULE = None


def configure_module():
    """Load the hyphenated CLI script so it can be driven in-process."""

    global _MODULE
    if _MODULE is None:
        spec = importlib.util.spec_from_file_location("configure_archive_cli", SCRIPT_PATH)
        if spec is None or spec.loader is None:  # pragma: no cover - import plumbing
            raise AssertionError(f"cannot load {SCRIPT_PATH}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(spec.name, None)
            raise
        _MODULE = module
    return _MODULE


class ConfigureArchiveTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.data = self.tmp / "data"
        self.external = self.tmp / "arquivo-externo"

    def configured(self):
        store = Store.open(self.data / "atos-tce.db")
        try:
            return store.get_metadata(EXTERNAL_ROOT_KEY)
        finally:
            store.close()

    def test_a_valid_absolute_folder_is_persisted(self):
        payload = configure_module().configure(self.data, self.external)

        self.assertTrue(payload["ok"])
        self.assertTrue(self.external.is_dir())
        self.assertEqual(self.configured(), str(self.external.resolve()))
        self.assertEqual(list(self.external.iterdir()), [], "a sonda não pode ficar para trás")

    def test_a_relative_path_is_refused(self):
        with self.assertRaises(configure_module().ConfigureError) as context:
            configure_module().validate_external_root(
                Path("arquivo-relativo"), data_root=self.data, repo_root=REPO_ROOT
            )

        self.assertIn("absoluto", str(context.exception))

    def test_a_folder_inside_the_data_root_is_refused(self):
        with self.assertRaises(configure_module().ConfigureError) as context:
            configure_module().validate_external_root(
                self.data / "dentro", data_root=self.data, repo_root=REPO_ROOT
            )

        self.assertIn("raiz de dados", str(context.exception))

    def test_a_folder_inside_the_build_or_scratch_areas_is_refused(self):
        for name in ("dist", "tmp"):
            with self.subTest(name=name):
                with self.assertRaises(configure_module().ConfigureError) as context:
                    configure_module().validate_external_root(
                        REPO_ROOT / name / "arquivo", data_root=self.data, repo_root=REPO_ROOT
                    )
                self.assertIn(name, str(context.exception))

    def test_nothing_is_persisted_when_the_validation_fails(self):
        with self.assertRaises(configure_module().ConfigureError):
            configure_module().configure(self.data, self.data / "dentro")

        self.assertIsNone(self.configured())

    def test_show_reports_the_configured_root(self):
        configure_module().configure(self.data, self.external)

        payload = configure_module().show(self.data)

        self.assertTrue(payload["configured"])
        self.assertTrue(payload["usable"])
        self.assertEqual(payload["external_root"], str(self.external.resolve()))

    def test_show_reports_an_unconfigured_root(self):
        payload = configure_module().show(self.data)

        self.assertFalse(payload["configured"])
        self.assertIsNone(payload["external_root"])


if __name__ == "__main__":
    unittest.main()
