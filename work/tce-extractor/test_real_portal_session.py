import unittest

from pathlib import Path

from playwright.sync_api import sync_playwright

from real_portal_session import (
    AREA_RESTRITA_URL,
    _normalize_portal_url,
    _sanitize_page,
    build_launch_args,
    compare_portal_snapshot,
    portal_dependency_ids,
    validate_session_profile,
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
