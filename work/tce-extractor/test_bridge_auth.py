from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

APP_ROOT = Path(__file__).parent / "portable" / "app"
sys.path.insert(0, str(APP_ROOT))

from bridge_auth import BridgeAuth, BridgeAuthError  # noqa: E402


class BridgeAuthTests(unittest.TestCase):
    def test_pairing_code_redeems_once_for_chrome_extension_origin(self):
        now = [datetime(2026, 9, 8, tzinfo=timezone.utc)]
        auth = BridgeAuth(clock=lambda: now[0])

        code = auth.issue_pairing_code()
        token = auth.redeem(code, "chrome-extension://test-extension")

        self.assertIsInstance(token, str)
        self.assertGreater(len(token), 20)
        with self.assertRaises(BridgeAuthError):
            auth.redeem(code, "chrome-extension://test-extension")

    def test_pairing_rejects_wrong_origin_and_expires(self):
        now = [datetime(2026, 9, 8, tzinfo=timezone.utc)]
        auth = BridgeAuth(clock=lambda: now[0], ttl=timedelta(seconds=120))
        code = auth.issue_pairing_code()

        with self.assertRaises(BridgeAuthError):
            auth.redeem(code, "null")
        with self.assertRaises(BridgeAuthError):
            auth.redeem(code, "https://evil.example")

        now[0] += timedelta(seconds=121)
        with self.assertRaises(BridgeAuthError):
            auth.redeem(code, "chrome-extension://test-extension")

    def test_redeem_limits_failed_attempts(self):
        auth = BridgeAuth()
        code = auth.issue_pairing_code()
        for _ in range(5):
            with self.assertRaises(BridgeAuthError):
                auth.redeem("00000000", "chrome-extension://test-extension")
        with self.assertRaises(BridgeAuthError):
            auth.redeem(code, "chrome-extension://test-extension")

    def test_pairing_rejects_chrome_extension_url_decorations(self):
        for origin in (
            "chrome-extension://test-extension?query=1",
            "chrome-extension://test-extension#fragment",
            "chrome-extension://user@test-extension",
            "chrome-extension://test-extension:443",
        ):
            auth = BridgeAuth()
            code = auth.issue_pairing_code()
            with self.assertRaises(BridgeAuthError):
                auth.redeem(code, origin)

    def test_token_is_bound_to_the_exact_extension_origin_and_can_allow_omitted_browser_origin(self):
        auth = BridgeAuth()
        token = auth.redeem(auth.issue_pairing_code(), "chrome-extension://test-extension")

        self.assertTrue(auth.validate(token, "chrome-extension://test-extension"))
        self.assertFalse(auth.validate(token, None))
        self.assertTrue(auth.validate(token, None, allow_missing_origin=True))
        self.assertFalse(auth.validate(token, "chrome-extension://other-extension"))


if __name__ == "__main__":
    unittest.main()
