import unittest

from playwright.sync_api import sync_playwright

from real_portal_session import _sanitize_page


class RealPortalSanitizerTests(unittest.TestCase):
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
            self.assertEqual(snapshot["known_ids"], ["btnComplementar", "formComplementar"])
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
