from pathlib import Path
import sys
import unittest

APP_ROOT = Path(__file__).parent / "portable" / "app"
sys.path.insert(0, str(APP_ROOT))

from area_restrita_analysis import (  # noqa: E402
    AreaScanGuard,
    classify_area_evidence,
    split_eligible_lots,
)
from batch_scope import validate_batch_spec  # noqa: E402


def control(kind, alt, title, src="icon.png"):
    return {"kind": kind, "alt": alt, "title": title, "src": src}


class AreaRestritaAnalysisTests(unittest.TestCase):
    def test_citation_only_document_cannot_be_ready_or_eligible(self):
        from batch_scope import build_preview

        spec = {
            "schema_version": 3,
            "source_scope": "sector_finalistic",
            "marker": {"label": "M", "value": "1"},
            "acquisition_source": "econtas",
            "lot_size": 50,
            "analysis_only": True,
            "auto_prepare": False,
            "auto_submit": False,
            "dataset_sha256": None,
            "area_snapshot_sha256": "a" * 64,
            "input_list_id": "input-" + "b" * 24,
            "input_sha256": "c" * 64,
            "input_unique_count": 1,
        }
        row = {
            "process_key": "1/2023",
            "interested_key": "ana",
            "area_restrita": {
                "scope": "sector_finalistic",
                "marker_label": "M",
                "marker_value": "1",
                "classification": "PRECISA_COMPLEMENTAR",
                "needs_complement": True,
                "action_observed": "Complementar Ato",
                "action_signature": control("red_complement_icon", "Complementar Ato", "Complementar Ato"),
                "snapshot_hash": "d" * 64,
            },
            "econtas": {
                "match": "exact",
                "documents": [{"label": "Resolucao_1.pdf"}],
                "snapshot_hash": None,
                "ocr_status": "ready",
            },
        }

        preview = build_preview(spec, [row])

        self.assertEqual(preview["ocr_ready"], 0)
        self.assertEqual(preview["eligible"], 0)
        self.assertEqual(preview["acquisition_eligible"], 1)

    def test_local_document_identity_hash_and_artifact_can_be_ready(self):
        from batch_scope import build_preview

        spec = {
            "schema_version": 3,
            "source_scope": "sector_finalistic",
            "marker": {"label": "M", "value": "1"},
            "acquisition_source": "econtas",
            "lot_size": 50,
            "analysis_only": True,
            "auto_prepare": False,
            "auto_submit": False,
            "dataset_sha256": None,
            "area_snapshot_sha256": "a" * 64,
            "input_list_id": "input-" + "b" * 24,
            "input_sha256": "c" * 64,
            "input_unique_count": 1,
        }
        row = {
            "process_key": "1/2023",
            "interested_key": "ana",
            "area_restrita": {
                "scope": "sector_finalistic",
                "marker_label": "M",
                "marker_value": "1",
                "classification": "PRECISA_COMPLEMENTAR",
                "needs_complement": True,
                "action_observed": "Complementar Ato",
                "action_signature": control("red_complement_icon", "Complementar Ato", "Complementar Ato"),
                "snapshot_hash": "d" * 64,
            },
            "econtas": {
                "match": "exact",
                "documents": [{
                    "document_id": "doc-1",
                    "relative_path": "documentos/doc-1.pdf",
                    "sha256": "e" * 64,
                }],
                "snapshot_hash": "f" * 64,
                "ocr_status": "ready",
            },
        }

        preview = build_preview(spec, [row])

        self.assertEqual(preview["ocr_ready"], 1)
        self.assertEqual(preview["eligible"], 1)

    def test_analysis_schema_v3_carries_authoritative_input_provenance(self):
        spec = validate_batch_spec(
            {
                "schema_version": 3,
                "source_scope": "sector_finalistic",
                "marker": {"label": "M", "value": "1"},
                "acquisition_source": "econtas",
                "lot_size": 300,
                "analysis_only": True,
                "auto_prepare": False,
                "auto_submit": False,
                "dataset_sha256": None,
                "area_snapshot_sha256": "a" * 64,
                "input_list_id": "input-" + "b" * 24,
                "input_sha256": "c" * 64,
                "input_unique_count": 1128,
            }
        )
        self.assertEqual(spec["schema_version"], 3)
        self.assertEqual(spec["input_unique_count"], 1128)

    def test_v2_remains_accepted_only_as_legacy_shape(self):
        spec = validate_batch_spec(
            {
                "schema_version": 2,
                "source_scope": "sector_finalistic",
                "marker": {"label": "M", "value": "1"},
                "acquisition_source": "econtas",
                "lot_size": 50,
                "analysis_only": True,
                "auto_prepare": False,
                "auto_submit": False,
                "dataset_sha256": None,
                "area_snapshot_sha256": "a" * 64,
            }
        )
        self.assertEqual(spec["schema_version"], 2)
    def test_only_red_complement_action_is_eligible(self):
        result = classify_area_evidence(
            {
                "present": True,
                "marker": {"label": "PROFESSOR - IPERN", "value": "m1"},
                "controls": [control("red_complement_icon", "Complementar Ato", "Complementar Ato", "red.png")],
            },
            expected_marker={"label": "PROFESSOR - IPERN", "value": "m1"},
        )
        self.assertEqual(result["classification"], "PRECISA_COMPLEMENTAR")

    def test_completed_text_and_false_positive_icons_are_excluded(self):
        for controls in (
            [control("green_icon", "Ato Complementado", "Ato Complementado", "green.png")],
            [control("red_other_icon", "Complementar Ato", "Complementar Ato", "red.png")],
            [control("red_complement_icon", "Ato Complementado", "Ato Complementado", "red.png")],
        ):
            with self.subTest(controls=controls):
                result = classify_area_evidence(
                    {"present": True, "marker": {"label": "M", "value": "1"}, "controls": controls},
                    expected_marker={"label": "M", "value": "1"},
                )
                self.assertNotEqual(result["classification"], "PRECISA_COMPLEMENTAR")

    def test_absent_and_guard_conditions_are_fail_closed(self):
        absent = classify_area_evidence(
            {"present": False, "marker": {"label": "M", "value": "1"}, "controls": []},
            expected_marker={"label": "M", "value": "1"},
        )
        self.assertEqual(absent["classification"], "NAO_ENCONTRADO_AREA_RESTRITA")
        guard = AreaScanGuard(marker={"label": "M", "value": "1"}, origin="sector_finalistic")
        guard.accept_page(1, "snapshot-a")
        with self.assertRaisesRegex(RuntimeError, "página repetida"):
            guard.accept_page(1, "snapshot-b")
        with self.assertRaisesRegex(RuntimeError, "página repetida"):
            guard.accept_page(2, "snapshot-a")
        with self.assertRaisesRegex(RuntimeError, "marcador"):
            guard.check(marker={"label": "OUTRO", "value": "2"}, origin="sector_finalistic", session_valid=True)
        with self.assertRaisesRegex(RuntimeError, "sessão"):
            guard.check(marker={"label": "M", "value": "1"}, origin="sector_finalistic", session_valid=False)

    def test_lots_use_three_hundred_as_queue_size_and_preserve_order(self):
        for count, expected in ((0, []), (1, [1]), (299, [299]), (300, [300]), (301, [300, 1]), (600, [300, 300]), (601, [300, 300, 1])):
            with self.subTest(count=count):
                queue = [{"process_key": f"{index}/2023"} for index in range(count)]
                lots = split_eligible_lots(queue)
                self.assertEqual([len(lot["items"]) for lot in lots], expected)
                self.assertEqual([item["process_key"] for lot in lots for item in lot["items"]], [item["process_key"] for item in queue])

    def test_v3_preview_counts_all_classifications_and_freezes_only_pending(self):
        from batch_scope import build_preview, freeze_queue

        spec = {
            "schema_version": 3,
            "source_scope": "sector_finalistic",
            "marker": {"label": "M", "value": "1"},
            "acquisition_source": "econtas",
            "lot_size": 300,
            "analysis_only": True,
            "auto_prepare": False,
            "auto_submit": False,
            "dataset_sha256": None,
            "area_snapshot_sha256": "a" * 64,
            "input_list_id": "input-" + "b" * 24,
            "input_sha256": "c" * 64,
            "input_unique_count": 5,
        }

        def row(key, classification, interested=None):
            pending = classification == "PRECISA_COMPLEMENTAR"
            return {
                "process_key": key,
                "interested_key": interested,
                "area_restrita": {
                    "scope": "sector_finalistic",
                    "marker_label": "M",
                    "marker_value": "1",
                    "classification": classification,
                    "needs_complement": pending,
                    "action_observed": "Complementar Ato" if pending else None,
                    "action_signature": control("red_complement_icon", "Complementar Ato", "Complementar Ato") if pending else None,
                    "snapshot_hash": "d" * 64,
                },
                "econtas": {"match": "missing", "documents": [], "snapshot_hash": None, "ocr_status": "not_run"},
            }

        rows = [
            row("1/2023", "PRECISA_COMPLEMENTAR", "ana"),
            row("2/2023", "ATO_COMPLEMENTADO", "bruno"),
            row("3/2023", "NAO_ENCONTRADO_AREA_RESTRITA"),
            row("4/2023", "AMBIGUO"),
            row("5/2023", "BLOQUEADO"),
        ]
        preview = build_preview(spec, rows)
        frozen = freeze_queue(spec, rows, observed_at="2026-09-14T00:00:00Z")

        self.assertEqual(preview["needs_complement"], 1)
        self.assertEqual(preview["already_complemented"], 1)
        self.assertEqual(preview["absent"], 1)
        self.assertEqual(preview["ambiguous"], 1)
        self.assertEqual(preview["blocked"], 1)
        self.assertEqual(len(frozen["queue"]), 1)
        self.assertEqual(len(frozen["blocked"]), 3)


if __name__ == "__main__":
    unittest.main()
