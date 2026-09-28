"""Selection of the next eligible process from the stored portal order."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.area_restrita.navigation_service import NavigationError, NavigationService
from app.core.models import ProcessRecord
from app.core.store import Store


class NavigationServiceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = Store.open(Path(self._tmp.name) / "atos-tce.db")
        self.addCleanup(self.store.close)
        self.service = NavigationService(self.store)

    def add_process(self, label, process_key, *, status="PRONTO"):
        interested = f"Pessoa {label}"
        return self.store.upsert_process(
            ProcessRecord(
                process_key=process_key,
                interested=interested,
                interested_normalized=interested.casefold(),
                source_scope="scope-fixture",
                marker="marker-label-fixture",
                status=status,
            )
        )

    def create_scan(
        self,
        ordered_processes,
        *,
        marker_label=" marker-label-fixture ",
        marker_value=" marker-value-fixture ",
    ):
        rows = [
            {
                "process_key": process_key,
                "interested": f"Pessoa {label}",
                "interested_normalized": f"pessoa {label.casefold()}",
                "portal_act_id": f"act-{label.casefold()}",
                "classification": "PRECISA_COMPLEMENTAR",
            }
            for label, process_key in ordered_processes
        ]
        return self.store.create_area_scan(
            source_scope="scope-fixture",
            marker_label=marker_label,
            marker_value=marker_value,
            rows=rows,
        )

    def test_uses_scan_order_skips_ineligible_and_does_not_wrap(self):
        ids = {
            "A": self.add_process("A", "800/2026"),
            "B": self.add_process("B", "100/2026"),
            "C": self.add_process("C", "200/2026", status="REVISAR"),
            "D": self.add_process("D", "300/2026"),
        }
        scan_id = self.create_scan(
            [("A", "800/2026"), ("B", "100/2026"), ("C", "200/2026"), ("D", "300/2026")]
        )

        from_a = self.service.next_target(process_id=ids["A"])
        from_b = self.service.next_target(process_id=ids["B"])
        from_d = self.service.next_target(process_id=ids["D"])

        self.assertEqual(from_a["target_identity"]["processKey"], "100/2026")
        self.assertEqual(from_a["scan_id"], scan_id)
        self.assertEqual(from_a["source_scope"], "scope-fixture")
        self.assertEqual(
            from_a["marker"],
            {"label": " marker-label-fixture ", "value": " marker-value-fixture "},
        )
        self.assertEqual(from_a["current_identity"]["processKey"], "800/2026")
        self.assertEqual(from_a["target_identity"]["interestedNormalized"], "pessoa b")
        self.assertEqual(from_a["target_identity"]["portalActId"], "act-b")
        self.assertEqual(from_b["target_identity"]["processKey"], "300/2026")
        self.assertIsNone(from_d)

    def test_identity_lookup_requires_one_unambiguous_current_process(self):
        self.add_process("A", "700/2026")
        self.add_process("B", "700/2026")
        self.add_process("C", "900/2026")
        self.create_scan(
            [("A", "700/2026"), ("B", "700/2026"), ("C", "900/2026")]
        )

        exact = self.service.next_target(
            identity={"processKey": "700/2026", "interestedNormalized": "pessoa a"}
        )

        self.assertEqual(exact["current_identity"]["interestedNormalized"], "pessoa a")
        self.assertEqual(exact["target_identity"]["processKey"], "700/2026")
        self.assertEqual(exact["target_identity"]["interestedNormalized"], "pessoa b")
        with self.assertRaises(NavigationError):
            self.service.next_target(identity={"processKey": "700/2026"})

    def test_navigation_preserves_the_portal_alias_and_strong_id_from_the_scan(self):
        current_id = self.add_process("A nome completo", "800/2026")
        target_id = self.add_process("B nome completo", "100/2026")
        self.store._connection.execute(
            "UPDATE processes SET portal_act_id = ? WHERE id IN (?, ?)",
            ("act-fixture-shared", current_id, target_id),
        )
        self.store.create_area_scan(
            source_scope="scope-fixture",
            marker_label="marker-label-fixture",
            marker_value="marker-value-fixture",
            rows=[
                {
                    "process_key": "800/2026",
                    "interested": "Pessoa A",
                    "interested_normalized": "pessoa a",
                    "portal_act_id": "act-fixture-shared",
                    "classification": "PRECISA_COMPLEMENTAR",
                },
                {
                    "process_key": "100/2026",
                    "interested": "Pessoa B",
                    "interested_normalized": "pessoa b",
                    "portal_act_id": "act-fixture-shared",
                    "classification": "PRECISA_COMPLEMENTAR",
                },
            ],
        )

        result = self.service.next_target(process_id=current_id)

        self.assertEqual(result["current_identity"]["interestedNormalized"], "pessoa a")
        self.assertEqual(result["current_identity"]["portalActId"], "act-fixture-shared")
        self.assertEqual(result["target_identity"]["interestedNormalized"], "pessoa b")
        self.assertEqual(result["target_identity"]["portalActId"], "act-fixture-shared")
        self.assertEqual(result["target_process_id"], target_id)

    def test_process_missing_from_its_referenced_scan_is_refused(self):
        current_id = self.add_process("A", "800/2026")
        self.add_process("B", "100/2026")
        scan_id = self.create_scan([("B", "100/2026")])
        with self.store._transaction() as connection:
            connection.execute(
                "UPDATE processes SET last_area_scan_id = ? WHERE id = ?",
                (scan_id, current_id),
            )

        with self.assertRaises(NavigationError):
            self.service.next_target(process_id=current_id)

    def test_process_with_an_old_scan_reference_is_refused(self):
        current_id = self.add_process("A", "800/2026")
        self.add_process("B", "100/2026")
        self.create_scan([("A", "800/2026"), ("B", "100/2026")])
        self.create_scan([("B", "100/2026")])

        with self.assertRaises(NavigationError) as raised:
            self.service.next_target(process_id=current_id)

        self.assertEqual(raised.exception.code, "stale_scan")

    def test_process_with_a_different_marker_context_is_refused(self):
        current_id = self.add_process("A", "800/2026")
        self.add_process("B", "100/2026")
        self.create_scan([("A", "800/2026"), ("B", "100/2026")])
        self.store.upsert_process(
            ProcessRecord(
                process_key="800/2026",
                interested="Pessoa A",
                interested_normalized="pessoa a",
                source_scope="scope-fixture",
                marker="different-marker",
                status="PRONTO",
            )
        )

        with self.assertRaises(NavigationError) as raised:
            self.service.next_target(process_id=current_id)

        self.assertEqual(raised.exception.code, "scan_context_mismatch")

    def test_target_with_a_different_marker_context_is_refused(self):
        current_id = self.add_process("A", "800/2026")
        self.add_process("B", "100/2026")
        self.create_scan([("A", "800/2026"), ("B", "100/2026")])
        self.store.upsert_process(
            ProcessRecord(
                process_key="100/2026",
                interested="Pessoa B",
                interested_normalized="pessoa b",
                source_scope="scope-fixture",
                marker="different-marker",
                status="PRONTO",
            )
        )

        with self.assertRaises(NavigationError) as raised:
            self.service.next_target(process_id=current_id)

        self.assertEqual(raised.exception.code, "scan_context_mismatch")

    def test_process_without_marker_context_is_refused(self):
        current_id = self.add_process("A", "800/2026")
        self.add_process("B", "100/2026")
        self.create_scan([("A", "800/2026"), ("B", "100/2026")])
        with self.store._transaction() as connection:
            connection.execute("UPDATE processes SET marker = NULL WHERE id = ?", (current_id,))

        with self.assertRaises(NavigationError) as raised:
            self.service.next_target(process_id=current_id)

        self.assertEqual(raised.exception.code, "scan_context_mismatch")

    def test_target_without_marker_context_is_refused(self):
        current_id = self.add_process("A", "800/2026")
        target_id = self.add_process("B", "100/2026")
        self.create_scan([("A", "800/2026"), ("B", "100/2026")])
        with self.store._transaction() as connection:
            connection.execute("UPDATE processes SET marker = NULL WHERE id = ?", (target_id,))

        with self.assertRaises(NavigationError) as raised:
            self.service.next_target(process_id=current_id)

        self.assertEqual(raised.exception.code, "scan_context_mismatch")


if __name__ == "__main__":
    unittest.main()
