"""Root package layout tests for the new Mesa application (M1 Task 1)."""

import importlib
import unittest


class PackageLayoutTests(unittest.TestCase):
    def test_packages_import(self):
        for name in ("app", "app.core", "app.archive", "app.api"):
            self.assertIsNotNone(importlib.import_module(name))


if __name__ == "__main__":
    unittest.main()
