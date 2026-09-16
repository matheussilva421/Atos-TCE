from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).parent / "portable" / "app"))

from qualification import (
    QUALIFICATION_SCHEMA_VERSION,
    expected_qualification_versions,
    inspect_qualification,
    write_qualification,
)


class AutomationQualificationTests(unittest.TestCase):
    def valid_payload(self) -> dict:
        return {
            "schema_version": QUALIFICATION_SCHEMA_VERSION,
            "status": "qualified",
            "versions": expected_qualification_versions("1.1.0"),
            "fixture_hashes": ["a" * 64],
            "real_event_id": "real-event-2026-09-09",
        }

    def write_payload(self, root: Path, payload: dict) -> Path:
        path = root / "automacao" / "qualificacao.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def test_accepts_a_versioned_qualification_only_when_all_proofs_match(self):
        with TemporaryDirectory() as temporary:
            path = self.write_payload(Path(temporary), self.valid_payload())
            result = inspect_qualification(path, expected_qualification_versions("1.1.0"))
            self.assertEqual(result.valid, True)
            self.assertEqual(result.reason, "qualified")

    def test_rejects_stale_versions_and_missing_real_event(self):
        with TemporaryDirectory() as temporary:
            payload = self.valid_payload()
            payload["versions"]["extension"] = "1.0.0"
            payload["real_event_id"] = ""
            path = self.write_payload(Path(temporary), payload)
            result = inspect_qualification(path, expected_qualification_versions("1.1.0"))
            self.assertEqual(result.valid, False)
            self.assertEqual(result.reason, "version_mismatch")

    def test_missing_or_unqualified_file_fails_closed(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = inspect_qualification(
                root / "automacao" / "qualificacao.json",
                expected_qualification_versions("1.1.0"),
            )
            self.assertEqual(result.valid, False)
            self.assertEqual(result.reason, "missing")

            payload = self.valid_payload()
            payload["status"] = "pending"
            path = self.write_payload(root, payload)
            result = inspect_qualification(path, expected_qualification_versions("1.1.0"))
            self.assertEqual(result.valid, False)
            self.assertEqual(result.reason, "status_not_qualified")




class QualificationWriterTests(unittest.TestCase):
    """O artefato de qualificacao precisa ser gravado fail-closed."""

    def test_writes_a_record_the_inspector_accepts(self):
        with TemporaryDirectory() as temporary:
            template = Path(temporary)
            path = write_qualification(
                template / "automacao" / "qualificacao.json",
                extension_version="1.1.0",
                fixture_hashes=["a" * 64, "b" * 64],
                real_event_id="real-event-2026-09-16",
            )
            check = inspect_qualification(path, expected_qualification_versions("1.1.0"))
            self.assertEqual(check.valid, True)
            self.assertEqual(check.reason, "qualified")

    def test_refuses_to_write_without_real_event_evidence(self):
        with TemporaryDirectory() as temporary:
            template = Path(temporary)
            with self.assertRaisesRegex(ValueError, "real_event_id"):
                write_qualification(
                    template / "automacao" / "qualificacao.json",
                    extension_version="1.1.0",
                    fixture_hashes=["a" * 64],
                    real_event_id="",
                )

    def test_refuses_to_write_without_fixture_hashes(self):
        with TemporaryDirectory() as temporary:
            template = Path(temporary)
            with self.assertRaisesRegex(ValueError, "fixture_hashes"):
                write_qualification(
                    template / "automacao" / "qualificacao.json",
                    extension_version="1.1.0",
                    fixture_hashes=[],
                    real_event_id="real-event-2026-09-16",
                )

    def test_refuses_malformed_hashes(self):
        with TemporaryDirectory() as temporary:
            template = Path(temporary)
            with self.assertRaisesRegex(ValueError, "fixture_hashes"):
                write_qualification(
                    template / "automacao" / "qualificacao.json",
                    extension_version="1.1.0",
                    fixture_hashes=["not-a-hash"],
                    real_event_id="real-event-2026-09-16",
                )


class QualificationServiceIntegrationTests(unittest.TestCase):
    """O artefato gravado precisa liberar o gate fail-closed do servico."""

    def test_written_artifact_is_accepted_by_the_service_gate(self):
        from local_service import EXTENSION_VERSION, QUALIFICATION_RELATIVE_PATH

        with TemporaryDirectory() as temporary:
            workflow_root = Path(temporary) / "acervo-tce"
            workflow_root.mkdir(parents=True)
            write_qualification(
                workflow_root / QUALIFICATION_RELATIVE_PATH,
                extension_version=EXTENSION_VERSION,
                fixture_hashes=["a" * 64],
                real_event_id="real-event-2026-09-16",
            )
            check = inspect_qualification(
                workflow_root / QUALIFICATION_RELATIVE_PATH,
                expected_qualification_versions(EXTENSION_VERSION),
            )
            self.assertEqual(check.valid, True, check.reason)


class QualificationVersionBindingTests(unittest.TestCase):
    """A qualificacao precisa estar presa a versao realmente distribuida."""

    def manifest_version(self) -> str:
        manifest = json.loads(
            (
                Path(__file__).parent
                / "portable"
                / "extensao-complementar-ato"
                / "manifest.json"
            ).read_text(encoding="utf-8")
        )
        return manifest["version"]

    def test_service_extension_version_matches_the_shipped_manifest(self):
        from local_service import EXTENSION_VERSION

        self.assertEqual(EXTENSION_VERSION, self.manifest_version())

    def test_package_audit_extension_version_matches_the_shipped_manifest(self):
        from package_audit import _EXTENSION_VERSION

        self.assertEqual(_EXTENSION_VERSION, self.manifest_version())

    def test_qualification_versions_are_bound_to_the_shipped_manifest(self):
        from local_service import EXTENSION_VERSION

        versions = expected_qualification_versions(EXTENSION_VERSION)

        self.assertEqual(versions["extension"], self.manifest_version())


    def test_service_reads_the_manifest_instead_of_a_hardcoded_literal(self):
        from local_service import _shipped_extension_version

        with TemporaryDirectory() as temporary:
            extension = Path(temporary) / "extensao-complementar-ato"
            extension.mkdir(parents=True)
            (extension / "manifest.json").write_text(
                json.dumps({"version": "9.9.9"}), encoding="utf-8"
            )

            self.assertEqual(_shipped_extension_version(extension), "9.9.9")

    def test_service_falls_back_only_when_the_manifest_is_unreadable(self):
        from local_service import _FALLBACK_EXTENSION_VERSION, _shipped_extension_version

        with TemporaryDirectory() as temporary:
            missing = Path(temporary) / "extensao-complementar-ato"

            self.assertEqual(_shipped_extension_version(missing), _FALLBACK_EXTENSION_VERSION)

            broken = Path(temporary) / "broken"
            broken.mkdir(parents=True)
            (broken / "manifest.json").write_text("{not json", encoding="utf-8")

            self.assertEqual(_shipped_extension_version(broken), _FALLBACK_EXTENSION_VERSION)


if __name__ == "__main__":



    unittest.main()
