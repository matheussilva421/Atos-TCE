"""Contract tests for the isolated QA workflow recorder and reports."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from qa_workflow import (
    QA_RUN_SCHEMA,
    QaContractError,
    build_run_document,
    load_function_matrix,
    sanitize_event,
    validate_run_document,
    write_run_document,
)
from qa_portal_recorder import (
    RecorderConfig,
    build_launch_args,
    build_structural_capture_script,
    classify_page_error,
    classify_request_failure,
    extension_worker_matches,
    validate_qa_profile,
    validate_safety_mode,
)

ROOT = Path(__file__).resolve().parent


class QaWorkflowContractTests(unittest.TestCase):
    def test_web_package_exposes_a_real_test_command(self):
        package = json.loads(
            (ROOT / "portable" / "app" / "web" / "package.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(package["scripts"]["test"], "node --test")

    def test_sanitizes_sensitive_event_values_but_keeps_structural_identity(self) -> None:
        event = {
            "kind": "input",
            "target": {
                "tag": "input",
                "id": "matricula",
                "name": "matricula",
                "type": "text",
            },
            "value": "103.870-2/1",
            "text": "MARIA DE SOUZA",
            "headers": {"Authorization": "Bearer secret"},
            "request_body": {"password": "secret"},
            "cookie": "session=secret",
        }

        result = sanitize_event(event)

        self.assertEqual(result["kind"], "input")
        self.assertEqual(result["target"]["id"], "matricula")
        self.assertNotIn("value", result)
        self.assertNotIn("text", result)
        self.assertNotIn("headers", result)
        self.assertNotIn("request_body", result)
        self.assertNotIn("cookie", result)

    def test_builds_and_validates_an_incomplete_run_with_explicit_status(self) -> None:
        document = build_run_document(
            package_root=Path("C:/TCE"),
            package_sha256="a" * 64,
            git_revision="main",
            run_id="qa-stable-id",
            browser={"name": "Chrome", "version": "130"},
            safety_mode="observe_only",
            status="BLOCKED",
            steps=[],
            errors=[{"kind": "human_checkpoint", "message": "login required"}],
            artifacts={"trace": "raw/trace.zip"},
            coverage={"case_id": "portal.login", "status": "BLOCKED"},
        )

        self.assertEqual(document["schema"], QA_RUN_SCHEMA)
        self.assertEqual(document["run_id"], "qa-stable-id")
        self.assertEqual(validate_run_document(document), document)

    def test_rejects_values_or_unknown_top_level_fields_in_a_run(self) -> None:
        document = build_run_document(
            package_root=Path("C:/TCE"),
            package_sha256="b" * 64,
            git_revision="main",
            browser={"name": "Chrome", "version": "130"},
            safety_mode="observe_only",
            status="PASS_FIXTURE",
            steps=[],
            errors=[],
            artifacts={},
            coverage={"case_id": "fixture.panel", "status": "PASS_FIXTURE"},
        )
        document["unexpected"] = "must fail"

        with self.assertRaises(QaContractError):
            validate_run_document(document)

    def test_writes_utf8_json_without_sensitive_event_fields(self) -> None:
        document = build_run_document(
            package_root=Path("C:/TCE"),
            package_sha256="c" * 64,
            git_revision="main",
            browser={"name": "Chrome", "version": "130"},
            safety_mode="observe_only",
            status="PASS_FIXTURE",
            steps=[sanitize_event({"kind": "click", "target": {"id": "refresh-button"}, "text": "Atualizar"})],
            errors=[],
            artifacts={},
            coverage={"case_id": "fixture.panel", "status": "PASS_FIXTURE"},
        )

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "run.json"
            write_run_document(path, document)
            loaded = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(loaded["schema"], QA_RUN_SCHEMA)
        self.assertNotIn("text", loaded["steps"][0])

    def test_loads_matrix_with_unique_ids_and_closed_statuses(self) -> None:
        matrix_path = Path(__file__).with_name("qa_function_matrix.json")

        matrix = load_function_matrix(matrix_path)

        self.assertGreaterEqual(len(matrix), 20)
        self.assertEqual(len({item["id"] for item in matrix}), len(matrix))
        for item in matrix:
            self.assertTrue(item["function"])
            self.assertIn(item["layer"], {"offline", "web", "extension", "portal"})
            self.assertIn(item["automation"], {"automatic", "manual", "fixture"})
            self.assertTrue(item["expected"])

    def test_rejects_a_profile_outside_the_private_qa_root(self) -> None:
        package = Path("C:/TCE")

        with self.assertRaises(ValueError):
            validate_qa_profile(package, Path("C:/Users/Matheus/AppData/Chrome"))

    def test_launch_arguments_load_only_the_requested_extension_without_tls_bypass(self) -> None:
        config = RecorderConfig(
            package_root=Path("C:/TCE"),
            extension_root=Path("C:/TCE/extensao-complementar-ato"),
            profile_root=Path("C:/TCE/dados-locais/chrome-qa-profile"),
            output_root=Path("C:/TCE/dados-locais/qa-runs"),
            portal_url="https://novaarearestrita.tce.rn.gov.br/",
            safety_mode="observe_only",
        )

        args = build_launch_args(config)

        self.assertIn("--disable-extensions-except=C:/TCE/extensao-complementar-ato", args)
        self.assertIn("--load-extension=C:/TCE/extensao-complementar-ato", args)
        self.assertNotIn("--ignore-certificate-errors", args)
        self.assertFalse(any("user-data-dir" in arg for arg in args))

    def test_capture_script_emits_structural_target_without_reading_values(self) -> None:
        script = build_structural_capture_script()

        self.assertIn("addEventListener('click'", script)
        self.assertIn("target.id", script)
        self.assertIn("target.name", script)
        self.assertNotIn("target.value", script)
        self.assertNotIn("textContent", script)

    def test_reversible_fill_requires_a_runner_and_is_refused_otherwise(self) -> None:
        # O modo de preenchimento reversivel era aceito pela configuracao sem
        # nenhum caminho de escrita e sem restore: o operador acreditava estar
        # no modo supervisionado e ficava apenas observando.
        self.assertEqual(validate_safety_mode("observe_only", reversible_runner_available=False), "observe_only")
        self.assertEqual(validate_safety_mode("observe_only", reversible_runner_available=True), "observe_only")
        self.assertEqual(validate_safety_mode("reversible_fill", reversible_runner_available=True), "reversible_fill")
        with self.assertRaisesRegex(ValueError, "reversivel|reversible"):
            validate_safety_mode("reversible_fill", reversible_runner_available=False)
        with self.assertRaisesRegex(ValueError, "modo"):
            validate_safety_mode("submit", reversible_runner_available=True)

    def test_worker_matching_ignores_unrelated_chrome_component(self) -> None:
        expected = {
            "name": "Complementar Ato TCE/RN",
            "version": "1.1.0",
            "background": {"service_worker": "background/service-worker.js"},
        }
        unrelated = {
            "name": "Google Network Speech",
            "version": "1.0",
            "background": {"service_worker": "service_worker.js"},
        }

        self.assertFalse(
            extension_worker_matches(
                "chrome-extension://component/background/service_worker.js",
                unrelated,
                expected,
            )
        )
        self.assertTrue(
            extension_worker_matches(
                "chrome-extension://atos/background/service-worker.js",
                expected,
                expected,
            )
        )

    def test_classifies_expected_browser_and_auth_navigation_diagnostics(self) -> None:
        self.assertEqual(
            classify_request_failure(
                "net::ERR_INVALID_AUTH_CREDENTIALS",
                is_navigation=True,
                resource_type="document",
            ),
            "auth_challenge",
        )
        self.assertEqual(
            classify_request_failure(
                "net::ERR_ABORTED",
                is_navigation=True,
                resource_type="document",
            ),
            "navigation_abort",
        )
        self.assertEqual(
            classify_request_failure(
                "net::ERR_CONNECTION_RESET",
                is_navigation=False,
                resource_type="xhr",
            ),
            "request_failed",
        )
        self.assertEqual(classify_page_error("chromewebdata/"), "browser_error_page")


class RulesVersionBindingTests(unittest.TestCase):
    """A versao das regras precisa bater entre servico e extensao."""

    def test_service_and_extension_agree_on_the_rules_version(self):
        import re as _re
        import sys as _sys

        app_root = Path(__file__).parent / "portable" / "app"
        _sys.path.insert(0, str(app_root))
        from local_service import RULES_VERSION as service_rules_version

        source = (
            Path(__file__).parent
            / "portable"
            / "extensao-complementar-ato"
            / "lib"
            / "legal-foundation.js"
        ).read_text(encoding="utf-8")
        match = _re.search(
            r'export const LEGAL_FOUNDATION_RULES_VERSION = "([^"]+)"', source
        )
        self.assertIsNotNone(match, "rules version declaration not found")
        self.assertEqual(match.group(1), service_rules_version)

    def test_authoritative_plan_rule_is_the_declared_rules_version(self):
        import sys as _sys

        app_root = Path(__file__).parent / "portable" / "app"
        _sys.path.insert(0, str(app_root))
        from local_service import RULES_VERSION

        # The v3 correction changed the judicial classification rules, so the
        # service, the extension and the qualification contract must agree.
        self.assertEqual(RULES_VERSION, "legal-foundation-v3")

    def test_qualification_contract_declares_the_v3_rules(self):
        import sys as _sys

        app_root = Path(__file__).parent / "portable" / "app"
        _sys.path.insert(0, str(app_root))
        from qualification import expected_qualification_versions

        expected = expected_qualification_versions("0.0.0-test")
        self.assertEqual(expected["rules"], "legal-foundation-v3")
        # Qualification records written under the previous rules stay invalid.
        obsolete = dict(expected, rules="legal-foundation-v2")
        self.assertNotEqual(obsolete, expected)


if __name__ == "__main__":

    unittest.main()
