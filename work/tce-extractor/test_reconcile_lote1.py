import unittest

import reconcile_lote1


REQUIRED_FIELDS = (
    "modalidade",
    "fundamento_legal",
    "data_publicacao_doe",
    "cargo",
    "matricula",
    "data_nascimento",
)


def _field(status="found", value="SYNTHETIC-VALUE"):
    return {"status": status, "value": value if status == "found" else None}


def _block(identity_token, missing=()):
    fields = {field: _field() for field in REQUIRED_FIELDS}
    fields["genero"] = _field("missing")
    for field in missing:
        fields[field] = _field("missing")
    return {
        "interested": identity_token,
        "fields": fields,
        "pending": [],
    }


def _payload():
    return {
        "schema_version": 1,
        "revision": 999,
        "results": {
            "SYNTH-PROCESS-1": {
                "process": "SYNTH-PROCESS-1",
                "status": "partial",
                "pending": [],
                "blocks": [
                    _block("SYNTHETIC-IDENTITY-1"),
                    _block("SYNTHETIC-IDENTITY-2", ("data_nascimento",)),
                ],
            },
            "SYNTH-PROCESS-2": {
                "process": "SYNTH-PROCESS-2",
                "status": "partial",
                "pending": [],
                "blocks": [
                    _block(
                        "SYNTHETIC-IDENTITY-3",
                        ("modalidade", "fundamento_legal"),
                    ),
                ],
            },
        },
    }


class ReconcileLote1Tests(unittest.TestCase):
    def test_reconciles_processes_identities_missing_fields_and_readiness(self):
        summary = reconcile_lote1.reconcile_payload(_payload())

        self.assertEqual(summary["structure"]["process_key_count"], 2)
        self.assertEqual(summary["structure"]["record_count"], 3)
        self.assertEqual(
            summary["source_structure"],
            {
                "root_type": "object",
                "root_keys": ["results", "revision", "schema_version"],
                "results_container_type": "object",
                "result_entry_keys": ["blocks", "pending", "process", "status"],
                "block_entry_keys": ["fields", "interested", "pending"],
                "field_keys": [
                    "cargo",
                    "data_nascimento",
                    "data_publicacao_doe",
                    "fundamento_legal",
                    "genero",
                    "matricula",
                    "modalidade",
                ],
            },
        )
        self.assertEqual(summary["counts"]["interested_identity_count"], 3)
        self.assertEqual(
            summary["counts"]["distinct_interested_identity_count"], 3
        )
        self.assertEqual(
            summary["counts"]["records_per_process"],
            {"SYNTH-PROCESS-1": 2, "SYNTH-PROCESS-2": 1},
        )
        self.assertEqual(
            summary["records"],
            [
                {
                    "process_key": "SYNTH-PROCESS-1",
                    "record_index": 1,
                    "missing_required_fields": [],
                    "missing_optional_fields": ["genero"],
                    "ready_for_preflight": True,
                },
                {
                    "process_key": "SYNTH-PROCESS-1",
                    "record_index": 2,
                    "missing_required_fields": ["data_nascimento"],
                    "missing_optional_fields": ["genero"],
                    "ready_for_preflight": False,
                },
                {
                    "process_key": "SYNTH-PROCESS-2",
                    "record_index": 1,
                    "missing_required_fields": [
                        "modalidade",
                        "fundamento_legal",
                    ],
                    "missing_optional_fields": ["genero"],
                    "ready_for_preflight": False,
                },
            ],
        )
        self.assertEqual(
            summary["preflight_matrix"],
            [
                {
                    "ready_for_preflight": True,
                    "blocked_fields": [],
                    "record_count": 1,
                },
                {
                    "ready_for_preflight": False,
                    "blocked_fields": ["data_nascimento"],
                    "record_count": 1,
                },
                {
                    "ready_for_preflight": False,
                    "blocked_fields": ["modalidade", "fundamento_legal"],
                    "record_count": 1,
                },
            ],
        )
        self.assertEqual(
            summary["reconciliation"],
            {
                "process_keys": 2,
                "interested_records": 3,
                "extra_records_over_processes": 1,
                "processes_with_one_record": 1,
                "processes_with_two_records": 1,
            },
        )


if __name__ == "__main__":
    unittest.main()
