"""Tests for build retention in dist/ (M6 Task 6)."""

import hashlib
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "rotate-builds.py"
CURRENT = "Atos-TCE-portable.zip"
PREVIOUS = "Atos-TCE-portable.previous.zip"

_MODULE = None


def rotation_module():
    """Load the CLI script so the rotation can be driven in-process."""

    global _MODULE
    if _MODULE is None:
        spec = importlib.util.spec_from_file_location("rotate_builds_cli", SCRIPT_PATH)
        if spec is None or spec.loader is None:  # pragma: no cover - import plumbing
            raise AssertionError(f"cannot load {SCRIPT_PATH}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(spec.name, None)
            raise
        _MODULE = module
    return _MODULE


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RetentionTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dist = Path(self._tmp.name) / "dist"
        self.dist.mkdir(parents=True)

    def build_zip(self, name: str, payload: bytes) -> Path:
        path = self.dist / name
        path.write_bytes(payload)
        return path

    def seed(self) -> dict:
        """Seed the current build, the previous build and three older builds."""

        return {
            "current": self.build_zip(CURRENT, b"build atual"),
            "previous": self.build_zip(PREVIOUS, b"build anterior"),
            "older": [
                self.build_zip(f"Atos-TCE-portable-2026090{index}T120000.zip", b"antigo " + bytes([48 + index]))
                for index in (1, 2, 3)
            ],
        }

    def names(self) -> list:
        return sorted(path.name for path in self.dist.iterdir())


class DryRunTests(RetentionTestCase):
    def test_dry_run_reports_old_builds_without_touching_them(self):
        seeded = self.seed()
        before = self.names()

        plan = rotation_module().rotate_builds(self.dist)

        self.assertFalse(plan.applied)
        self.assertEqual(sorted(plan.keep), sorted([CURRENT, PREVIOUS]))
        self.assertEqual(sorted(plan.remove), sorted(path.name for path in seeded["older"]))
        self.assertGreater(plan.remove_bytes, 0)
        self.assertEqual(self.names(), before)

    def test_dry_run_reports_non_zip_files_as_ignored(self):
        self.seed()
        (self.dist / "leia-me.txt").write_text("nao sou um build", encoding="utf-8")

        plan = rotation_module().rotate_builds(self.dist)

        self.assertEqual(plan.ignored, ("leia-me.txt",))
        self.assertNotIn("leia-me.txt", plan.remove)

    def test_missing_dist_root_is_an_error(self):
        with self.assertRaises(rotation_module().RotationError):
            rotation_module().rotate_builds(self.dist / "inexistente")


class ApplyTests(RetentionTestCase):
    def test_apply_keeps_exactly_the_two_canonical_names(self):
        seeded = self.seed()
        verified = digest(seeded["current"])

        plan = rotation_module().rotate_builds(self.dist, verified_sha256=verified, apply=True)

        self.assertTrue(plan.applied)
        self.assertEqual(self.names(), sorted([CURRENT, PREVIOUS]))
        self.assertEqual((self.dist / CURRENT).read_bytes(), b"build atual")
        self.assertEqual((self.dist / PREVIOUS).read_bytes(), b"build anterior")
        for older in seeded["older"]:
            self.assertFalse(older.exists())

    def test_apply_refuses_without_a_verified_hash(self):
        seeded = self.seed()
        before = self.names()

        with self.assertRaises(rotation_module().RotationError):
            rotation_module().rotate_builds(self.dist, apply=True)

        self.assertEqual(self.names(), before)
        self.assertEqual((self.dist / CURRENT).read_bytes(), seeded["current"].read_bytes())

    def test_apply_refuses_a_hash_that_does_not_match(self):
        self.seed()
        before = self.names()

        with self.assertRaises(rotation_module().RotationError):
            rotation_module().rotate_builds(self.dist, verified_sha256="0" * 64, apply=True)

        self.assertEqual(self.names(), before)

    def test_newest_build_is_promoted_when_the_canonical_names_are_absent(self):
        oldest = self.build_zip("Atos-TCE-portable-20260901T120000.zip", b"um")
        middle = self.build_zip("Atos-TCE-portable-20260902T120000.zip", b"dois")
        newest = self.build_zip("Atos-TCE-portable-20260903T120000.zip", b"tres")
        for path, moment in ((oldest, 1000), (middle, 2000), (newest, 3000)):
            import os

            os.utime(path, (moment, moment))

        plan = rotation_module().rotate_builds(
            self.dist, verified_sha256=digest(middle), apply=True
        )

        self.assertTrue(plan.applied)
        self.assertEqual(self.names(), sorted([CURRENT, PREVIOUS]))
        self.assertEqual((self.dist / CURRENT).read_bytes(), b"dois")
        self.assertEqual((self.dist / PREVIOUS).read_bytes(), b"tres")

    def test_apply_keeps_non_zip_files(self):
        seeded = self.seed()
        (self.dist / "notas.md").write_text("anotacao", encoding="utf-8")

        rotation_module().rotate_builds(
            self.dist, verified_sha256=digest(seeded["current"]), apply=True
        )

        self.assertEqual(self.names(), sorted([CURRENT, PREVIOUS, "notas.md"]))


class RotationCliTests(RetentionTestCase):
    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--dist", str(self.dist), *arguments],
            capture_output=True,
            text=True,
        )

    def test_cli_defaults_to_dry_run_and_prints_the_plan(self):
        self.seed()

        result = self.run_cli()

        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertFalse(plan["applied"])
        self.assertEqual(len(plan["remove"]), 3)
        self.assertTrue((self.dist / CURRENT).exists())

    def test_cli_apply_requires_the_verified_hash(self):
        seeded = self.seed()

        refused = self.run_cli("--apply")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("verified", (refused.stderr + refused.stdout).lower())

        applied = self.run_cli("--apply", "--verified-hash", digest(seeded["current"]))
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertEqual(self.names(), sorted([CURRENT, PREVIOUS]))


if __name__ == "__main__":
    unittest.main()
