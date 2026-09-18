"""The M2 real gate needs one command that compares both scans (read-only)."""

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.store import Store

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "compare-area-scans.py"

CDP_PAYLOAD = {
    "role": "sector_finalistic",
    "source_scope": "sector_finalistic",
    "marker": {"label": "PROFESSOR - IPERN - 2 RUBRICAS", "value": "6189"},
    "page": 2,
    "total_pages": 2,
    "origin": "cdp",
    "rows": [
        {
            "process_key": "100015/2026",
            "interested": "FERNANDO DE PAIVA FERREIRA",
            "interested_normalized": "fernando de paiva ferreira",
            "classification": "PRECISA_COMPLEMENTAR",
            "portal_act_id": "630290",
        },
        {
            "process_key": "100023/2026",
            "interested": "REGINA MICHELE PEREIRA",
            "interested_normalized": "regina michele pereira",
            "classification": "ATO_COMPLEMENTADO",
        },
    ],
}

MESA_PAYLOAD = {
    "source_scope": "sector_finalistic",
    "marker": {"label": "PROFESSOR - IPERN - 2 RUBRICAS", "value": "6189"},
    "origin": "extension",
    "items": [
        {
            "process_key": "100015/2026",
            "interested": "FERNANDO DE PAIVA FERREIRA",
            "interested_normalized": "fernando de paiva ferreira",
            "classification": "PRECISA_COMPLEMENTAR",
            "portal_act_id": "630290",
        },
        {
            "process_key": "100023/2026",
            "interested": "REGINA MICHELE PEREIRA",
            "interested_normalized": "regina michele pereira",
            "classification": "ATO_COMPLEMENTADO",
        },
    ],
}


class CompareTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def write(self, name: str, payload: dict) -> Path:
        path = self.tmp / name
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def compare(self, cdp: dict, mesa: dict):
        module = _module()
        return module.compare_scans(cdp, mesa)

    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), *[str(argument) for argument in arguments]],
            capture_output=True,
            text=True,
        )


_MODULE = None


def _module():
    """Load the CLI script as a module so the comparison can be driven in-process."""

    global _MODULE
    if _MODULE is None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("compare_area_scans_cli", SCRIPT_PATH)
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


class ComparisonTests(CompareTestCase):
    def test_identical_scans_are_equal(self):
        report = self.compare(CDP_PAYLOAD, MESA_PAYLOAD)

        self.assertTrue(report["equal"])
        self.assertEqual(report["only_in_cdp"], [])
        self.assertEqual(report["only_in_mesa"], [])
        self.assertEqual(report["classification_mismatches"], [])
        self.assertEqual(report["counts"]["cdp"], report["counts"]["mesa"])

    def test_a_row_only_in_the_cdp_scan_is_a_divergence(self):
        cdp = json.loads(json.dumps(CDP_PAYLOAD))
        cdp["rows"].append(
            {
                "process_key": "100099/2026",
                "interested": "PESSOA EXEMPLO",
                "interested_normalized": "pessoa exemplo",
                "classification": "PRECISA_COMPLEMENTAR",
            }
        )

        report = self.compare(cdp, MESA_PAYLOAD)

        self.assertFalse(report["equal"])
        self.assertEqual([row["process_key"] for row in report["only_in_cdp"]], ["100099/2026"])

    def test_a_row_only_in_the_mesa_scan_is_a_divergence(self):
        mesa = json.loads(json.dumps(MESA_PAYLOAD))
        mesa["items"].append(
            {
                "process_key": "100088/2026",
                "interested": "PESSOA EXEMPLO",
                "interested_normalized": "pessoa exemplo",
                "classification": "AMBIGUO",
            }
        )

        report = self.compare(CDP_PAYLOAD, mesa)

        self.assertFalse(report["equal"])
        self.assertEqual([row["process_key"] for row in report["only_in_mesa"]], ["100088/2026"])

    def test_a_classification_mismatch_is_a_divergence(self):
        mesa = json.loads(json.dumps(MESA_PAYLOAD))
        mesa["items"][0]["classification"] = "ATO_COMPLEMENTADO"

        report = self.compare(CDP_PAYLOAD, mesa)

        self.assertFalse(report["equal"])
        mismatch = report["classification_mismatches"][0]
        self.assertEqual(mismatch["process_key"], "100015/2026")
        self.assertEqual(mismatch["cdp"], "PRECISA_COMPLEMENTAR")
        self.assertEqual(mismatch["mesa"], "ATO_COMPLEMENTADO")

    def test_a_different_marker_is_reported(self):
        mesa = json.loads(json.dumps(MESA_PAYLOAD))
        mesa["marker"] = {"label": "OUTRO", "value": "1"}

        report = self.compare(CDP_PAYLOAD, mesa)

        self.assertFalse(report["equal"])
        self.assertIn("marker", report["context_differences"])

    def test_the_scan_origin_is_reported_without_failing(self):
        report = self.compare(CDP_PAYLOAD, MESA_PAYLOAD)

        self.assertEqual(report["origins"], {"cdp": "cdp", "mesa": "extension"})
        self.assertTrue(report["equal"])


class MesaSideTests(CompareTestCase):
    def seed_scan(self) -> tuple:
        data_root = self.tmp / "data"
        store = Store.open(data_root / "atos-tce.db")
        self.addCleanup(store.close)
        scan_id = store.create_area_scan(
            "sector_finalistic",
            "PROFESSOR - IPERN - 2 RUBRICAS",
            "6189",
            CDP_PAYLOAD["rows"],
            origin="cdp",
        )
        return data_root, scan_id

    def test_the_mesa_side_can_be_read_from_the_database(self):
        data_root, scan_id = self.seed_scan()

        report = _module().compare_with_database(CDP_PAYLOAD, data_root / "atos-tce.db", scan_id)

        self.assertTrue(report["equal"], report)
        self.assertEqual(report["counts"]["mesa"]["total"], 2)

    def test_an_unknown_scan_id_is_an_error(self):
        data_root, _scan_id = self.seed_scan()

        with self.assertRaises(_module().ComparisonError):
            _module().compare_with_database(CDP_PAYLOAD, data_root / "atos-tce.db", 4242)

    def test_a_missing_database_is_an_error_and_is_not_created(self):
        missing = self.tmp / "sem-banco" / "atos-tce.db"

        with self.assertRaises(_module().ComparisonError):
            _module().compare_with_database(CDP_PAYLOAD, missing)

        self.assertFalse(missing.exists())


class CompareCliTests(CompareTestCase):
    def test_cli_file_against_file_reports_equality(self):
        cdp = self.write("cdp.json", CDP_PAYLOAD)
        mesa = self.write("mesa.json", MESA_PAYLOAD)

        result = self.run_cli("--cdp-json", cdp, "--mesa-json", mesa)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["equal"])

    def test_cli_returns_a_failure_exit_code_on_divergence(self):
        cdp = self.write("cdp.json", CDP_PAYLOAD)
        mesa = json.loads(json.dumps(MESA_PAYLOAD))
        mesa["items"] = mesa["items"][:1]
        mesa_path = self.write("mesa.json", mesa)

        result = self.run_cli("--cdp-json", cdp, "--mesa-json", mesa_path)

        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)["equal"])


if __name__ == "__main__":
    unittest.main()
