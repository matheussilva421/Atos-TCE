import hashlib
import json
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from pathlib import Path

from playwright.sync_api import sync_playwright

from real_portal_session import (
    AREA_RESTRITA_URL,
    _normalize_portal_url,
    _sanitize_page,
    build_launch_args,
    build_sanitized_fixture,
    compare_portal_snapshot,
    portal_dependency_ids,
    validate_session_profile,
    write_sanitized_fixture,
)


class RealPortalUrlTests(unittest.TestCase):
    def test_defaults_to_the_authenticated_area_restrita_entrypoint(self):
        self.assertEqual(
            AREA_RESTRITA_URL,
            "https://novaarearestrita.tce.rn.gov.br/telaPrincipalMenu.asp",
        )
        self.assertEqual(_normalize_portal_url(None), AREA_RESTRITA_URL)

    def test_rejects_the_public_processos_origin_for_complementar_ato(self):
        with self.assertRaisesRegex(ValueError, "Área Restrita"):
            _normalize_portal_url("https://processos.tce.rn.gov.br/")


class RealPortalLaunchArgumentTests(unittest.TestCase):
    def test_launch_arguments_load_only_the_requested_extension_without_tls_bypass(self):
        args = build_launch_args(Path("C:/TCE/extensao-complementar-ato"))

        self.assertIn("--disable-extensions-except=C:/TCE/extensao-complementar-ato", args)
        self.assertIn("--load-extension=C:/TCE/extensao-complementar-ato", args)
        self.assertNotIn("--ignore-certificate-errors", args)
        self.assertFalse(any("user-data-dir" in arg for arg in args))
        self.assertFalse(any("ignore-certificate" in arg or "ignore-http" in arg for arg in args))

    def test_dependency_ids_cover_every_control_the_automation_needs(self):
        ids = portal_dependency_ids()

        for field_id in (
            "txtModalidade",
            "txtFundamentoLegal",
            "txtDataDOE",
            "txtCargo",
            "txtMatricula",
            "txtDataNascimento",
            "txtGenero",
            "txtNumeroProcesso",
            "txtAnoProcesso",
        ):
            self.assertIn(field_id, ids)
        self.assertEqual(len(ids), len(set(ids)))


class RealPortalSessionProfileTests(unittest.TestCase):
    def test_accepts_a_disposable_profile_inside_the_package_private_root(self):
        package = Path("C:/TCE")

        profile = validate_session_profile(package, Path("C:/TCE/dados-locais/real-portal-profile"))

        self.assertTrue(str(profile).replace("\\", "/").endswith("TCE/dados-locais/real-portal-profile"))

    def test_rejects_a_profile_outside_the_package_private_root(self):
        package = Path("C:/TCE")

        with self.assertRaisesRegex(ValueError, "dados-locais"):
            validate_session_profile(package, Path("C:/Users/Matheus/AppData/Chrome"))

    def test_rejects_the_private_root_itself(self):
        package = Path("C:/TCE")

        with self.assertRaisesRegex(ValueError, "dados-locais"):
            validate_session_profile(package, Path("C:/TCE/dados-locais"))


    def test_allows_the_caller_to_request_a_disposable_profile(self):
        package = Path("C:/TCE")

        self.assertIsNone(validate_session_profile(package, None))



class RealPortalFixtureTests(unittest.TestCase):
    """A observacao real precisa virar fixture sanitizada com hash estavel."""

    def observation(self) -> dict:
        return {
            "schema_version": 1,
            "captured_at": "2026-09-16T12:00:00+00:00",
            "browser": "chrome.exe",
            "profile_disposable": True,
            "extension_id_present": True,
            "pair_status": "Mesa local conectada.",
            "panel": {"url": "chrome-extension://abc/sidepanel/panel.html"},
            "portal": {
                "origin": "https://novaarearestrita.tce.rn.gov.br",
                "known_ids": list(portal_dependency_ids()),
                "authenticated_ui_signal": True,
            },
            "portal_contract_ids": list(portal_dependency_ids()),
            "portal_missing_contract_ids": [],
            "portal_drift": {"drift": False, "reason": "unchanged"},
            "portal_extension_origin_match": True,
            "submission_performed_by_runner": False,
        }

    def test_builds_a_sanitized_fixture_without_private_portal_fields(self):
        fixture, digest = build_sanitized_fixture(self.observation())

        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        self.assertEqual(fixture["fixture_kind"], "real-portal-observation")
        self.assertEqual(fixture["fixture_status"], "sanitized")
        self.assertNotIn("localStorage", json.dumps(fixture))
        self.assertNotIn("pair_status", fixture)

    def test_rejects_an_observation_that_carried_process_identity(self):
        observation = self.observation()
        observation["portal"]["known_ids"] = list(portal_dependency_ids()) + ["123456/2026"]

        with self.assertRaisesRegex(ValueError, "process"):
            build_sanitized_fixture(observation)

    def test_rejects_an_observation_that_performed_a_submission(self):
        observation = self.observation()
        observation["submission_performed_by_runner"] = True

        with self.assertRaisesRegex(ValueError, "submission_performed_by_runner"):
            build_sanitized_fixture(observation)

    def test_rejects_a_portal_that_drifted_from_the_contract(self):
        observation = self.observation()
        observation["portal_drift"] = {"drift": True, "reason": "structural_drift"}
        observation["portal_missing_contract_ids"] = ["txtCargo"]

        with self.assertRaisesRegex(ValueError, "drift|contrato"):
            build_sanitized_fixture(observation)

    def test_digest_is_stable_and_matches_the_fixture_bytes(self):
        fixture, digest = build_sanitized_fixture(self.observation())
        payload = json.dumps(
            fixture, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )

        self.assertEqual(digest, hashlib.sha256(payload.encode("utf-8")).hexdigest())

    def test_digest_is_reproducible_for_equivalent_observations(self):
        first, digest_a = build_sanitized_fixture(self.observation())
        second, digest_b = build_sanitized_fixture(self.observation())

        self.assertEqual(first, second)
        self.assertEqual(digest_a, digest_b)

    def test_rejects_an_observation_without_authenticated_contract_evidence(self):
        observation = self.observation()
        observation["portal"]["authenticated_ui_signal"] = False

        with self.assertRaisesRegex(ValueError, "autenticad|autentica"):
            build_sanitized_fixture(observation)

    def test_rejects_an_observation_with_wrong_origin_or_contract_ids(self):
        observation = self.observation()
        observation["portal"]["origin"] = "https://example.invalid"

        with self.assertRaisesRegex(ValueError, "origem|portal"):
            build_sanitized_fixture(observation)

        observation = self.observation()
        observation["portal_contract_ids"] = ["txtCargo"]

        with self.assertRaisesRegex(ValueError, "contrato|controle"):
            build_sanitized_fixture(observation)

    def test_writes_fixture_and_returns_hash_of_the_written_bytes(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            observation_path = root / "observacao.json"
            fixture_path = root / "automacao" / "fixtures" / "portal-real.json"
            observation_path.write_text(
                json.dumps(self.observation(), ensure_ascii=False), encoding="utf-8"
            )

            output, digest = write_sanitized_fixture(observation_path, fixture_path)

            self.assertEqual(output, fixture_path.resolve())
            self.assertEqual(digest, hashlib.sha256(output.read_bytes()).hexdigest())
            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8"))["fixture_status"],
                "sanitized",
            )

    def test_refuses_to_replace_the_observation_with_its_derived_fixture(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "observacao.json"
            path.write_text(json.dumps(self.observation()), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "diferente|separad"):
                write_sanitized_fixture(path, path)

    def test_cli_derives_a_fixture_without_opening_a_browser_session(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            observation_path = root / "observacao.json"
            fixture_path = root / "fixture.json"
            observation_path.write_text(
                json.dumps(self.observation(), ensure_ascii=False), encoding="utf-8"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).with_name("real_portal_session.py")),
                    "--fixture-input",
                    str(observation_path),
                    "--fixture-output",
                    str(fixture_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(Path(report["output"]).resolve(), fixture_path.resolve())
            self.assertEqual(report["sha256"], hashlib.sha256(fixture_path.read_bytes()).hexdigest())

class RealPortalSanitizerTests(unittest.TestCase):
    def baseline(self):
        return {
            "origin": "https://novaarearestrita.tce.rn.gov.br",
            "known_ids": list(portal_dependency_ids()),
            "complement_action_signal": True,
            "select_count": 2,
            "form_count": 1,
        }

    def test_matching_observation_reports_no_drift(self):
        report = compare_portal_snapshot(self.baseline(), self.baseline())

        self.assertEqual(report["drift"], False)
        self.assertEqual(report["missing_ids"], [])
        self.assertEqual(report["unexpected_ids"], [])

    def test_missing_required_control_is_reported_as_drift(self):
        observed = self.baseline()
        observed["known_ids"] = [item for item in observed["known_ids"] if item != "txtCargo"]

        report = compare_portal_snapshot(self.baseline(), observed)

        self.assertEqual(report["drift"], True)
        self.assertEqual(report["missing_ids"], ["txtCargo"])

    def test_lost_submit_action_or_selects_are_reported_as_drift(self):
        observed = self.baseline()
        observed["complement_action_signal"] = False
        observed["select_count"] = 0

        report = compare_portal_snapshot(self.baseline(), observed)

        self.assertEqual(report["drift"], True)
        self.assertIn("complement_action_signal", report["changed_signals"])
        self.assertIn("select_count", report["changed_signals"])

    def test_origin_change_is_reported_as_drift(self):
        observed = self.baseline()
        observed["origin"] = "https://processos.tce.rn.gov.br"

        report = compare_portal_snapshot(self.baseline(), observed)

        self.assertEqual(report["drift"], True)
        self.assertIn("origin", report["changed_signals"])

    def test_missing_observation_fails_closed(self):
        report = compare_portal_snapshot(self.baseline(), None)

        self.assertEqual(report["drift"], True)
        self.assertEqual(report["reason"], "observation_missing")

    def test_captures_structural_authenticated_signals_without_private_text(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context()
            context.route(
                "http://sanitized.test/**",
                lambda route: route.fulfill(
                    status=200,
                    content_type="text/html",
                    body="""
                <html lang="pt-BR">
                  <body>
                    <header><span>Sair</span></header>
                    <main>
                      <h1>Meus Processos</h1>
                      <p>123456/2026</p>
                      <a href="/complementar">Complementar Ato</a>
                      <form id="formComplementar">
                        <input id="btnComplementar" type="text">
                        <input id="txtModalidade" type="text">
                        <input id="txtNumeroProcesso" type="text">
                      </form>
                    </main>
                  </body>
                </html>
                """,
                ),
            )
            page = context.new_page()
            page.goto(
                "http://sanitized.test/#/dashboard/meus/meus-processos",
                wait_until="domcontentloaded",
            )
            page.evaluate(
                """
                () => localStorage.setItem(
                    'currentUser',
                    JSON.stringify({token: 'private-token', setorSelecionado: {codigoSetor: 'private'}})
                )
                """
            )

            snapshot = _sanitize_page(page)

            self.assertEqual(snapshot["authenticated_ui_signal"], True)
            self.assertEqual(snapshot["process_list_signal"], True)
            self.assertEqual(snapshot["complement_action_signal"], True)
            self.assertEqual(snapshot["process_key_count"], 1)
            self.assertEqual(snapshot["known_ids"], ["txtModalidade", "txtNumeroProcesso"])
            self.assertEqual(snapshot["local_storage_auth_signal"], True)
            self.assertEqual(snapshot["route_signals"], {
                "dashboard": True,
                "meus_processos": True,
                "complementar_ato": False,
            })
            self.assertNotIn("private-token", repr(snapshot))
            self.assertNotIn("Meus Processos", repr(snapshot))
            context.close()
            browser.close()


if __name__ == "__main__":
    unittest.main()
