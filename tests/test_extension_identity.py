import base64
import hashlib
import json
import unittest
from pathlib import Path

from app.api.bridge import TRUSTED_EXTENSION_ID, is_trusted_extension_origin


ROOT = Path(__file__).resolve().parents[1]
ALPHABET = "abcdefghijklmnop"


def chromium_extension_id(public_key_der: bytes) -> str:
    digest = hashlib.sha256(public_key_der).digest()[:16]
    return "".join(ALPHABET[b >> 4] + ALPHABET[b & 0x0F] for b in digest)


class ExtensionIdentityTests(unittest.TestCase):
    def test_manifest_key_derives_the_id_trusted_by_the_mesa(self):
        manifest = json.loads((ROOT / "extension" / "manifest.json").read_text(encoding="utf-8"))
        derived = chromium_extension_id(base64.b64decode(manifest["key"]))
        self.assertEqual(derived, TRUSTED_EXTENSION_ID)

    def test_only_the_shipped_extension_origin_is_trusted(self):
        self.assertTrue(
            is_trusted_extension_origin(f"chrome-extension://{TRUSTED_EXTENSION_ID}")
        )
        self.assertFalse(
            is_trusted_extension_origin("chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        )
        self.assertFalse(is_trusted_extension_origin("https://example.com"))
        self.assertFalse(is_trusted_extension_origin(None))


if __name__ == "__main__":
    unittest.main()
