import unittest

from app.main import bootstrap_handoff_message


class MainLauncherTests(unittest.TestCase):
    def test_bootstrap_url_is_explicitly_copyable_to_another_browser_profile(self):
        url = "http://127.0.0.1:18743/bootstrap#token=one-time"

        message = bootstrap_handoff_message(url)

        self.assertIn("URL de sessão da Mesa", message)
        self.assertIn(url, message)
        self.assertIn("outro Chrome", message)
        self.assertIn("uso único", message)
        self.assertIn("Copiar sessão para outro Chrome", message)


if __name__ == "__main__":
    unittest.main()
