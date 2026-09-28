"""Integrated regressions for the v1.0.1 canonical portal identity workflow."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.area_restrita.fill_service import FillError, FillService
from app.area_restrita.navigation_service import NavigationService
from app.area_restrita.preflight import FillPlan
from app.core.models import ProcessRecord
from app.core.store import Store


SOURCE_KEY = "102390/2026"
TARGET_KEY = "102391/2026"
SOURCE_ACT_ID = "act-fixture-source-42"
TARGET_ACT_ID = "act-fixture-target-43"
SOURCE_ALIAS = {
    "processKey": SOURCE_KEY,
    "interestedNormalized": "pessoa exemplo",
    "portalActId": SOURCE_ACT_ID,
}


class V101IdentityWorkflowTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = Store.open(Path(self._tmp.name) / "atos-tce.db")
        self.addCleanup(self.store.close)

    def add_process(self, process_key, interested, interested_normalized):
        return self.store.upsert_process(
            ProcessRecord(
                process_key=process_key,
                interested=interested,
                interested_normalized=interested_normalized,
                status="PRONTO",
            )
        )

    @staticmethod
    def identity_only_preflight(_process, snapshot):
        return FillPlan(
            identity=dict(snapshot["identity"]),
            generation=int(snapshot.get("generation") or 1),
            fields={},
        )

    def test_strong_id_keeps_scan_manual_fill_automatic_fill_and_next_target_canonical(self):
        canonical_id = self.add_process(
            SOURCE_KEY,
            "Pessoa Exemplo Nome Completo",
            "pessoa exemplo nome completo",
        )
        target_id = self.add_process(TARGET_KEY, "Pessoa Destino", "pessoa destino")
        self.store._connection.execute(
            "UPDATE processes SET portal_act_id = ? WHERE id = ?",
            (SOURCE_ACT_ID, canonical_id),
        )
        self.store._connection.execute(
            "UPDATE processes SET portal_act_id = ? WHERE id = ?",
            (TARGET_ACT_ID, target_id),
        )

        scan_id = self.store.create_area_scan(
            source_scope="sector_finalistic",
            marker_label="FIXTURE - SANITIZADO",
            marker_value="fixture-marker-10",
            rows=[
                {
                    "process_key": SOURCE_KEY,
                    "interested": "Pessoa Exemplo",
                    "interested_normalized": "pessoa exemplo",
                    "portal_act_id": SOURCE_ACT_ID,
                    "classification": "PRECISA_COMPLEMENTAR",
                },
                {
                    "process_key": TARGET_KEY,
                    "interested": "Pessoa Destino",
                    "interested_normalized": "pessoa destino",
                    "portal_act_id": TARGET_ACT_ID,
                    "classification": "PRECISA_COMPLEMENTAR",
                },
            ],
        )

        processes = self.store.list_processes()
        self.assertEqual(len(processes), 2)
        self.assertEqual(
            self.store.get_area_scan(scan_id)["items"][0]["process_id"], canonical_id
        )
        self.assertEqual(self.store.get_process(canonical_id)["interested"], "Pessoa Exemplo Nome Completo")

        fill_service = FillService(self.store, preflight=self.identity_only_preflight)
        manual_request_id = fill_service.request_manual_fill(
            {"identity": SOURCE_ALIAS, "generation": 7}
        )
        manual_request = self.store.get_fill_request(manual_request_id)
        manual_command = self.store.get_extension_command(manual_request["current_command_id"])
        self.assertEqual(manual_request["process_id"], canonical_id)
        self.assertEqual(manual_request["state"], "FILLING")
        self.assertEqual(manual_command["type"], "FILL_FORM")
        self.assertEqual(manual_command["payload"]["identity"], SOURCE_ALIAS)

        automatic_request_id = fill_service.request_fill(canonical_id)
        automatic_request = self.store.get_fill_request(automatic_request_id)
        automatic_command = self.store.get_extension_command(
            automatic_request["current_command_id"]
        )
        self.assertEqual(automatic_request["process_id"], canonical_id)
        self.assertEqual(automatic_command["type"], "OPEN_ACT")
        self.assertEqual(automatic_command["payload"]["identity"], SOURCE_ALIAS)
        self.assertEqual(automatic_command["payload"]["context"]["scan_id"], scan_id)

        next_target = NavigationService(self.store).next_target(process_id=canonical_id)
        self.assertEqual(next_target["current_process_id"], canonical_id)
        self.assertEqual(next_target["target_process_id"], target_id)
        self.assertEqual(next_target["current_identity"], SOURCE_ALIAS)
        self.assertEqual(next_target["target_identity"]["portalActId"], TARGET_ACT_ID)
        self.assertEqual(next_target["scan_id"], scan_id)

    def test_without_strong_id_different_names_do_not_merge_and_unknown_alias_fails_closed(self):
        canonical_id = self.add_process(
            SOURCE_KEY,
            "Pessoa Exemplo Nome Completo",
            "pessoa exemplo nome completo",
        )
        self.store.create_area_scan(
            source_scope="sector_finalistic",
            marker_label="FIXTURE - SANITIZADO",
            marker_value="fixture-marker-no-id",
            rows=[
                {
                    "process_key": SOURCE_KEY,
                    "interested": "Pessoa Exemplo",
                    "interested_normalized": "pessoa exemplo",
                    "portal_act_id": None,
                    "classification": "PRECISA_COMPLEMENTAR",
                }
            ],
        )

        processes = self.store.list_processes()
        self.assertEqual(len(processes), 2)
        self.assertEqual(self.store.get_process(canonical_id)["interested_normalized"], "pessoa exemplo nome completo")
        self.assertIsNone(self.store.get_process(canonical_id)["portal_act_id"])

        fill_service = FillService(self.store, preflight=self.identity_only_preflight)
        with self.assertRaises(FillError):
            fill_service.request_manual_fill(
                {
                    "identity": {
                        "processKey": SOURCE_KEY,
                        "interestedNormalized": "pessoa apelido",
                    },
                    "generation": 1,
                }
            )


if __name__ == "__main__":
    unittest.main()
