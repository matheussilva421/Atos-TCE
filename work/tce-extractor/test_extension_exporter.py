import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).parent
APP_ROOT = REPO_ROOT / "portable" / "app"
sys.path.insert(0, str(APP_ROOT))

from extension_exporter import (  # noqa: E402
    ALLOWED_FIELDS,
    build_extension_dataset,
    export_extension_dataset,
    validate_extension_dataset,
)


FIXED_TIME = "2026-09-04T12:00:00+00:00"
FULL_TEXT = "INTEGRAL_TEXT_MUST_NOT_BE_EXPORTED"
SENSITIVE_KEYS = (
    "cpf",
    "url",
    "cookie",
    "token",
    "session",
    "password",
    "absolute_path",
    "pdf_path",
)


def _field(
    key,
    value,
    *,
    status="found",
    process="103439/2023",
    event="9",
    document="Documento_Processo_Portal_Gestao.pdf",
    page=1,
    confidence="high",
    raw_value=None,
    candidates=None,
):
    payload = {
        "key": key,
        "value": value,
        "status": status,
        "process": process,
        "event": event,
        "document": document,
        "page": page,
        "confidence": confidence,
        "raw_value": raw_value,
        "candidates": list(candidates or []),
    }
    return payload


def _complete_fields(process="103439/2023", event="9"):
    values = {
        "modalidade": "Aposentadoria especial",
        "fundamento_legal": "Nos termos da Lei Complementar estadual",
        "data_publicacao_doe": "07/02/2020",
        "cargo": "PROFESSOR PN - IV",
        "matricula": "103.870-2/1",
        "data_nascimento": "30/04/1967",
        "genero": "Feminino",
    }
    return {
        key: _field(key, value, process=process, event=event)
        for key, value in values.items()
    }


def checkpoint_fixture():
    conflict_candidates = [
        _field(
            "cargo",
            "PROFESSOR PN - IV",
            process="103439/2023",
            event="9",
            page=1,
        ),
        _field(
            "cargo",
            "PROFESSOR PN - V",
            process="103439/2023",
            event="12",
            page=2,
        ),
    ]
    first_fields = _complete_fields()
    first_fields["cargo"] = _field(
        "cargo",
        None,
        status="conflict",
        confidence="low",
        candidates=conflict_candidates,
    )
    first_fields["genero"] = {"key": "genero", "value": None, "status": "missing"}

    return {
        "version": 1,
        "run_id": "20260904T120000Z",
        "created_at": "2026-09-04T11:00:00+00:00",
        "processes": {
            "103439/2023": {
                "status": "partial",
                "documents": [
                    {
                        "event": "9",
                        "pdf_path": "C:/private/archive/103439-event-9.pdf",
                        "absolute_path": "C:/private/archive/103439-event-9.pdf",
                        "url": "https://private.example/session/123",
                        "text": FULL_TEXT,
                        "cookie": "cookie-value",
                    }
                ],
                "result": {
                    "process": "103439/2023",
                    "status": "partial",
                    "blocks": [
                        {
                            "interested": "MÁGNOLIA   RAMALHO MACIEL PINTO LOPES",
                            "fields": first_fields,
                            "text": FULL_TEXT,
                            "token": "token-value",
                        },
                        {
                            "interested": "JOÃO DA SILVA",
                            "fields": {
                                "modalidade": _field(
                                    "modalidade",
                                    "Integral",
                                    process="103439/2023",
                                    event="12",
                                ),
                                "matricula": _field(
                                    "matricula",
                                    "103.871-2",
                                    process="103439/2023",
                                    event="12",
                                ),
                            },
                            "password": "password-value",
                        },
                    ],
                },
            },
            "103442 / 2023": {
                "status": "complete",
                "result": {
                    "process": "tampered-process-is-ignored",
                    "status": "complete",
                    "blocks": [
                        {
                            "interested": "ANA DE SOUZA",
                            "fields": {
                                "data_publicacao_doe": _field(
                                    "data_publicacao_doe",
                                    "07/02/2020",
                                    process="103442/2023",
                                    event="3",
                                    page=4,
                                )
                            },
                        }
                    ],
                },
                "session": "session-value",
            },
        },
        "metadata": {
            "absolute_path": "C:/private/checkpoint.json",
            "pdf_path": "C:/private/archive.pdf",
            "integral_text": FULL_TEXT,
        },
    }


def _rehash_dataset(dataset):
    logical_payload = {
        "schema_version": dataset["schema_version"],
        "batch_id": dataset["batch"]["id"],
        "records": dataset["records"],
    }
    if "process_keys" in dataset["batch"]:
        logical_payload["process_keys"] = dataset["batch"]["process_keys"]
    serialized = json.dumps(
        logical_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    dataset["batch"]["logical_sha256"] = hashlib.sha256(serialized).hexdigest()


class ExtensionExporterTests(unittest.TestCase):
    def test_blocks_distinct_interested_names_that_share_a_normalized_identity(self):
        checkpoint = checkpoint_fixture()
        blocks = checkpoint["processes"]["103439/2023"]["result"]["blocks"]
        blocks[1]["interested"] = "MAGNOLIA RAMALHO MACIEL PINTO LOPES"

        with self.assertRaisesRegex(ValueError, "interested identity collision"):
            build_extension_dataset(checkpoint, generated_at=FIXED_TIME)

    def test_builds_one_batch_with_all_processes_and_interested_parties(self):
        dataset = build_extension_dataset(checkpoint_fixture(), generated_at=FIXED_TIME)

        self.assertEqual(dataset["schema_version"], 1)
        self.assertEqual(dataset["generated_at"], FIXED_TIME)
        self.assertEqual(dataset["batch"]["id"], "20260904T120000Z")
        self.assertEqual(dataset["batch"]["process_count"], 2)
        self.assertEqual(dataset["batch"]["record_count"], 3)
        self.assertEqual(
            [record["process"]["key"] for record in dataset["records"]],
            ["103439/2023", "103439/2023", "103442/2023"],
        )
        self.assertEqual(
            dataset["records"][0]["interested"],
            {
                "original": "MÁGNOLIA   RAMALHO MACIEL PINTO LOPES",
                "normalized": "magnolia ramalho maciel pinto lopes",
            },
        )

    def test_projects_all_seven_fields_in_fixed_order_and_preserves_document_evidence(self):
        dataset = build_extension_dataset(checkpoint_fixture(), generated_at=FIXED_TIME)
        record = dataset["records"][0]

        self.assertEqual(list(record["fields"]), list(ALLOWED_FIELDS))
        self.assertEqual(
            record["fields"]["matricula"]["source_value"], "103.870-2/1"
        )
        self.assertEqual(
            record["fields"]["matricula"]["form_value"], "103.870-2/1"
        )
        self.assertEqual(
            record["fields"]["data_publicacao_doe"]["form_value"], "07/02/2020"
        )
        citation = record["fields"]["data_publicacao_doe"]["citation"]
        self.assertEqual(
            citation,
            {
                "process": "103439/2023",
                "event": "9",
                "page": 1,
                "document": "Documento_Processo_Portal_Gestao.pdf",
            },
        )
        self.assertEqual(record["fields"]["genero"]["status"], "missing")
        self.assertIsNone(record["fields"]["genero"]["citation"])

    def test_keeps_conflicts_and_projected_candidates_without_private_source_data(self):
        dataset = build_extension_dataset(checkpoint_fixture(), generated_at=FIXED_TIME)
        cargo = dataset["records"][0]["fields"]["cargo"]

        self.assertEqual(cargo["status"], "conflict")
        self.assertIsNone(cargo["form_value"])
        self.assertEqual(
            [candidate["source_value"] for candidate in cargo["candidates"]],
            ["PROFESSOR PN - IV", "PROFESSOR PN - V"],
        )
        self.assertEqual(cargo["candidates"][1]["citation"]["event"], "12")
        self.assertEqual(cargo["candidates"][1]["citation"]["page"], 2)

    def test_allowlist_does_not_export_sensitive_keys_or_integral_text(self):
        dataset = build_extension_dataset(checkpoint_fixture(), generated_at=FIXED_TIME)
        serialized = json.dumps(dataset, ensure_ascii=False, sort_keys=True)

        self.assertNotIn(FULL_TEXT, serialized)
        for sensitive_key in SENSITIVE_KEYS:
            self.assertNotIn(f'"{sensitive_key}"', serialized)
        self.assertNotIn("private/archive", serialized)

    def test_unsafe_value_or_raw_value_is_omitted_without_rewriting(self):
        cases = (
            ("value", "https://private.example/ato"),
            ("value", r"C:\Users\private\ato.pdf"),
            ("value", "/private/archive/ato.pdf"),
            ("value", "CPF: 123.456.789-00"),
            ("value", "Bearer super-secret-token"),
            ("raw_value", "session=super-secret-session"),
            ("raw_value", "texto integral\nsegunda linha privada"),
        )
        expected = {
            "status": "missing",
            "confidence": "none",
            "source_value": None,
            "form_value": None,
            "citation": None,
        }

        for source_key, unsafe_value in cases:
            with self.subTest(source_key=source_key, unsafe_value=unsafe_value):
                checkpoint = checkpoint_fixture()
                evidence = checkpoint["processes"]["103439/2023"]["result"]["blocks"][0][
                    "fields"
                ]["modalidade"]
                evidence["value"] = "Aposentadoria especial"
                evidence["raw_value"] = None
                evidence[source_key] = unsafe_value

                dataset = build_extension_dataset(checkpoint, generated_at=FIXED_TIME)
                projected = dataset["records"][0]["fields"]["modalidade"]

                self.assertEqual(projected, expected)
                self.assertNotIn("super-secret", json.dumps(dataset, ensure_ascii=False))

    def test_validation_rejects_unsafe_values_even_with_a_matching_hash(self):
        dataset = build_extension_dataset(checkpoint_fixture(), generated_at=FIXED_TIME)
        modalidade = dataset["records"][0]["fields"]["modalidade"]
        modalidade["source_value"] = "https://private.example/ato"
        modalidade["form_value"] = "https://private.example/ato"
        _rehash_dataset(dataset)

        with self.assertRaisesRegex(ValueError, "unsafe"):
            validate_extension_dataset(dataset)

    def test_validation_rejects_unsafe_citation_document_with_matching_hash(self):
        checkpoint = checkpoint_fixture()
        checkpoint["processes"]["103439/2023"]["result"]["blocks"][0]["fields"][
            "genero"
        ] = _field("genero", "Feminino", status="found", confidence="high")
        dataset = build_extension_dataset(checkpoint, generated_at=FIXED_TIME)
        dataset["records"][0]["fields"]["genero"]["citation"][
            "document"
        ] = "https://private.example/source.pdf"
        _rehash_dataset(dataset)

        with self.assertRaisesRegex(ValueError, "document"):
            validate_extension_dataset(dataset)

    def test_citation_document_preserves_only_a_safe_basename(self):
        cases = (
            ("private/secret", "secret"),
            (r"private\secret", "secret"),
            ("/private/archive/source.pdf", "source.pdf"),
            (r"C:\private\archive\source.pdf", "source.pdf"),
        )

        for document, expected_basename in cases:
            with self.subTest(document=document):
                checkpoint = checkpoint_fixture()
                checkpoint["processes"]["103439/2023"]["result"]["blocks"][0][
                    "fields"
                ]["modalidade"]["document"] = document

                dataset = build_extension_dataset(checkpoint, generated_at=FIXED_TIME)
                citation = dataset["records"][0]["fields"]["modalidade"]["citation"]

                self.assertEqual(citation.get("document"), expected_basename)
                self.assertNotIn("private", citation.get("document", ""))

    def test_process_inventory_counts_process_without_blocks_and_is_hashed(self):
        checkpoint = checkpoint_fixture()
        checkpoint["processes"]["103500/2023"] = {
            "status": "partial",
            "result": {"process": "103500/2023", "status": "partial", "blocks": []},
        }

        dataset = build_extension_dataset(checkpoint, generated_at=FIXED_TIME)

        self.assertEqual(
            dataset["batch"].get("process_keys"),
            ["103439/2023", "103442/2023", "103500/2023"],
        )
        self.assertEqual(dataset["batch"]["process_count"], 3)
        self.assertEqual(dataset["batch"]["record_count"], 3)
        self.assertNotIn(
            "103500/2023", [record["process"]["key"] for record in dataset["records"]]
        )

        dataset["batch"]["process_keys"][-1] = "103501/2023"
        with self.assertRaisesRegex(ValueError, "logical_sha256"):
            validate_extension_dataset(dataset)

    def test_gender_is_exported_only_from_found_high_confidence_complete_citation(self):
        valid_checkpoint = checkpoint_fixture()
        valid_gender = _field("genero", "Feminino", status="found", confidence="high")
        valid_checkpoint["processes"]["103439/2023"]["result"]["blocks"][0]["fields"][
            "genero"
        ] = valid_gender

        valid_dataset = build_extension_dataset(valid_checkpoint, generated_at=FIXED_TIME)
        self.assertEqual(
            valid_dataset["records"][0]["fields"]["genero"]["form_value"],
            "Feminino",
        )

        unsafe_sources = (
            {"status": "ambiguous"},
            {"confidence": "low"},
            {"process": None},
            {"process": "999999/2023"},
            {"event": None},
            {"page": None},
            {"document": None},
            {"document": "https://private.example/gender-source.pdf"},
        )
        expected_missing = {
            "status": "missing",
            "confidence": "none",
            "source_value": None,
            "form_value": None,
            "citation": None,
        }
        for changes in unsafe_sources:
            with self.subTest(changes=changes):
                checkpoint = checkpoint_fixture()
                gender = _field("genero", "Feminino", status="found", confidence="high")
                gender.update(changes)
                checkpoint["processes"]["103439/2023"]["result"]["blocks"][0]["fields"][
                    "genero"
                ] = gender

                dataset = build_extension_dataset(checkpoint, generated_at=FIXED_TIME)

                self.assertEqual(
                    dataset["records"][0]["fields"]["genero"], expected_missing
                )

    def test_found_doe_requires_strict_valid_civil_date(self):
        invalid_dates = (
            "7/2/2020",
            "2020-02-07",
            "31/02/2020",
            "29/02/2019",
            "sete de fevereiro de 2020",
        )
        expected_missing = {
            "status": "missing",
            "confidence": "none",
            "source_value": None,
            "form_value": None,
            "citation": None,
        }

        for invalid_date in invalid_dates:
            with self.subTest(invalid_date=invalid_date):
                checkpoint = checkpoint_fixture()
                doe = checkpoint["processes"]["103439/2023"]["result"]["blocks"][0][
                    "fields"
                ]["data_publicacao_doe"]
                doe["value"] = invalid_date
                doe["raw_value"] = invalid_date

                dataset = build_extension_dataset(checkpoint, generated_at=FIXED_TIME)

                self.assertEqual(
                    dataset["records"][0]["fields"]["data_publicacao_doe"],
                    expected_missing,
                )

    def test_validation_requires_exact_process_and_record_counts(self):
        for count_key in ("process_count", "record_count"):
            with self.subTest(count_key=count_key):
                dataset = build_extension_dataset(checkpoint_fixture(), generated_at=FIXED_TIME)
                dataset["batch"][count_key] += 1

                with self.assertRaisesRegex(ValueError, count_key):
                    validate_extension_dataset(dataset)

    def test_same_checkpoint_and_generated_at_produce_identical_bytes_and_hash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            checkpoint_path = root / "checkpoint.json"
            checkpoint_path.write_text(
                json.dumps(checkpoint_fixture(), ensure_ascii=False), encoding="utf-8"
            )

            first = export_extension_dataset(
                checkpoint_path, root / "first.json", generated_at=FIXED_TIME
            )
            second = export_extension_dataset(
                checkpoint_path, root / "second.json", generated_at=FIXED_TIME
            )

            self.assertEqual((root / "first.json").read_bytes(), (root / "second.json").read_bytes())
            self.assertEqual(first["batch"]["logical_sha256"], second["batch"]["logical_sha256"])
            self.assertEqual(len(first["batch"]["logical_sha256"]), 64)

    def test_changing_an_exported_value_changes_logical_hash(self):
        original = build_extension_dataset(checkpoint_fixture(), generated_at=FIXED_TIME)
        changed_checkpoint = checkpoint_fixture()
        changed_checkpoint["processes"]["103439/2023"]["result"]["blocks"][1]["fields"][
            "modalidade"
        ]["value"] = "Proporcional"
        changed = build_extension_dataset(changed_checkpoint, generated_at=FIXED_TIME)

        self.assertNotEqual(
            original["batch"]["logical_sha256"], changed["batch"]["logical_sha256"]
        )

    def test_validation_rejects_a_tampered_logical_hash(self):
        dataset = build_extension_dataset(checkpoint_fixture(), generated_at=FIXED_TIME)
        dataset["batch"]["logical_sha256"] = "0" * 64

        with self.assertRaises(ValueError):
            validate_extension_dataset(dataset)

    def test_invalid_process_key_is_rejected_before_projection(self):
        checkpoint = checkpoint_fixture()
        checkpoint["processes"]["not-a-process"] = checkpoint["processes"].pop(
            "103442 / 2023"
        )

        with self.assertRaises(ValueError):
            build_extension_dataset(checkpoint, generated_at=FIXED_TIME)

    def test_failed_atomic_replace_preserves_previous_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            checkpoint_path = root / "checkpoint.json"
            output_path = root / "dataset.json"
            checkpoint_path.write_text(
                json.dumps(checkpoint_fixture(), ensure_ascii=False), encoding="utf-8"
            )
            output_path.write_text("previous-output\n", encoding="utf-8")

            with patch("extension_exporter.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaises(OSError):
                    export_extension_dataset(
                        checkpoint_path, output_path, generated_at=FIXED_TIME
                    )

            self.assertEqual(output_path.read_text(encoding="utf-8"), "previous-output\n")
            self.assertEqual(list(root.glob(".dataset.json.*.tmp")), [])

    def test_cli_summary_contains_counts_hash_and_path_but_no_personal_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            checkpoint_path = root / "checkpoint.json"
            output_path = root / "dataset.json"
            checkpoint_path.write_text(
                json.dumps(checkpoint_fixture(), ensure_ascii=False), encoding="utf-8"
            )

            # Exercise the public script contract in a subprocess.
            from subprocess import run

            result = run(
                [
                    sys.executable,
                    "-s",
                    str(APP_ROOT / "extension_exporter.py"),
                    "--checkpoint",
                    str(checkpoint_path),
                    "--output",
                    str(output_path),
                    "--generated-at",
                    FIXED_TIME,
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary["process_count"], 2)
            self.assertEqual(summary["record_count"], 3)
            self.assertEqual(
                summary["logical_sha256"],
                json.loads(output_path.read_text(encoding="utf-8"))["batch"][
                    "logical_sha256"
                ],
            )
            self.assertEqual(summary["path"], str(output_path))
            self.assertNotIn("MÁGNOLIA", result.stdout)
            self.assertNotIn(FULL_TEXT, result.stdout)

    def test_cli_validates_an_existing_dataset_without_reexporting_it(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset_path = Path(temp_dir) / "dataset.json"
            dataset = build_extension_dataset(
                checkpoint_fixture(), generated_at=FIXED_TIME
            )
            dataset_path.write_text(
                json.dumps(dataset, ensure_ascii=False), encoding="utf-8-sig"
            )

            from subprocess import run

            result = run(
                [
                    sys.executable,
                    "-B",
                    "-s",
                    str(APP_ROOT / "extension_exporter.py"),
                    "--validate",
                    str(dataset_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "dataset-ok")


if __name__ == "__main__":
    unittest.main()
