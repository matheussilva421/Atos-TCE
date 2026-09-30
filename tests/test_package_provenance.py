"""Provenance contract for the portable package.

A portable ZIP must prove which build produced it. The builder writes
package-manifest.json next to the app sources it stages, and the verifier
refuses any package whose declared build or file hashes disagree with the bytes
actually inside the archive.

Without this, a stale ZIP keeps verifying while shipping code older than the
fixes it claims to contain: the previous dist/Atos-TCE-portable.zip still passed
the verifier after the detection-failure gate and the terminal-guard fix had
landed in the source tree.
"""

import hashlib
import json
import os
import shutil
import subprocess
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFIER = REPO_ROOT / "packaging" / "verify-package.ps1"
MANIFEST_NAME = "package-manifest.json"

#: The build the package claims to be, and the build the operator expects. They
#: differ exactly in the stale-artifact scenario this module guards.
CURRENT_BUILD = "b" * 40
STALE_BUILD = "a" * 40

COVERED_ROOTS = ("app/", "extension/")
COVERED_FILES = (
    "START.cmd",
    "README.md",
    "LEIA-ME-OUTRO-PC.txt",
    "scripts/scan-area-cdp.ps1",
)


def product_payload() -> dict:
    """The product sources the manifest is responsible for."""

    return {
        "app/main.py": b"print('mesa')\n",
        "app/api/server.py": b"# server\n",
        "app/core/store.py": b"# store\n",
        "extension/manifest.json": json.dumps(
            {"manifest_version": 3, "name": "Complementar Ato", "version": "1.0.0"}
        ).encode("utf-8"),
        "extension/background/router.js": b"// router\n",
        "START.cmd": b"@echo off\r\npython -m app.main %*\r\n",
        "README.md": b"# Atos TCE\n",
        "LEIA-ME-OUTRO-PC.txt": b"Guia para outro PC.\n",
        "scripts/scan-area-cdp.ps1": b"# shared read-only scanner\n",
    }


def is_covered(name: str) -> bool:
    return name.startswith(COVERED_ROOTS) or name in COVERED_FILES

def release_payload(product: dict | None = None) -> dict:

    """A release-shaped payload: product sources plus a declared embedded runtime."""

    payload = dict(product if product is not None else product_payload())
    declared = (
        ("runtime/python/python.exe", "python", b"binary"),
        ("licenses/README.md", "licenses", b"# licencas\n"),
    )
    for name, _component, data in declared:
        payload[name] = data
    payload["runtime-manifest.json"] = json.dumps(
        {
            "python": {"version": "3.14.4"},
            "build": {
                "included_files": [
                    {
                        "path": name,
                        "component": component,
                        "size": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                    for name, component, data in declared
                ]
            },
        }
    ).encode("utf-8")
    return payload


def repo_payload() -> dict:
    """The committed product bytes of HEAD, for commit-backed checks.

    Reading the commit rather than the worktree keeps these fixtures valid while
    the checkout itself has work in progress.
    """

    listed = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "app", "extension"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    names = [name for name in listed if "__pycache__" not in name and not name.endswith(".pyc")]
    names += [name for name in COVERED_FILES if (REPO_ROOT / name).is_file()]
    return {
        name: subprocess.run(
            ["git", "-C", str(REPO_ROOT), "show", f"HEAD:{name}"],
            capture_output=True,
            check=True,
        ).stdout
        for name in names
    }


def head_commit() -> str:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def build_manifest(payload: dict, build_id: str, *, drop=(), corrupt=()) -> dict:
    """A manifest describing ``payload``, with optional deliberate damage."""

    files = []
    for name in sorted(name for name in payload if is_covered(name)):
        if name in drop:
            continue
        data = payload[name]
        digest = hashlib.sha256(data).hexdigest()
        files.append(
            {
                "path": name,
                "size": len(data),
                "sha256": "0" * 64 if name in corrupt else digest,
            }
        )
    return {"schema": 1, "build_id": build_id, "source_dirty": False, "files": files}


def make_package(path: Path, payload: dict, manifest: dict | None) -> Path:
    body = dict(payload)
    if manifest is not None:
        body[MANIFEST_NAME] = json.dumps(manifest, sort_keys=True, indent=1).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in body.items():
            archive.writestr(name, data)
    return path


def powershell_env() -> dict:
    """Windows PowerShell 5.1 needs its own module path to find Get-FileHash."""

    environment = dict(os.environ)
    program_files = environment.get("ProgramFiles", r"C:\Program Files")
    system_root = environment.get("SystemRoot", r"C:\Windows")
    environment["PSModulePath"] = os.pathsep.join(
        (
            os.path.join(program_files, "WindowsPowerShell", "Modules"),
            os.path.join(system_root, "System32", "WindowsPowerShell", "v1.0", "Modules"),
        )
    )
    return environment


def powershell(script: Path, *arguments, cwd: Path | None = None) -> subprocess.CompletedProcess:
    command = [
        "powershell.exe",
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
    ] + [str(argument) for argument in arguments]
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(cwd or REPO_ROOT),
        env=powershell_env(),
    )


def verify(archive: Path, *arguments) -> subprocess.CompletedProcess:
    return powershell(VERIFIER, "-ZipPath", archive, *arguments)


class PackageProvenanceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_verifier_refuses_a_package_without_a_manifest(self):
        archive = make_package(
            self.tmp / "sem-manifesto.zip", product_payload(), None
        )

        result = verify(archive, "-AllowMissingRuntime", "-SkipSmoke")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(MANIFEST_NAME, result.stdout + result.stderr)

    def test_verifier_refuses_a_declared_hash_that_does_not_match(self):
        payload = product_payload()
        manifest = build_manifest(payload, CURRENT_BUILD, corrupt=("app/main.py",))
        archive = make_package(self.tmp / "hash-errado.zip", payload, manifest)

        result = verify(archive, "-AllowMissingRuntime", "-SkipSmoke")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("app/main.py", result.stdout + result.stderr)

    def test_verifier_refuses_a_stale_build_id(self):
        payload = product_payload()
        manifest = build_manifest(payload, STALE_BUILD)
        archive = make_package(self.tmp / "build-antigo.zip", payload, manifest)

        result = verify(
            archive,
            "-AllowMissingRuntime",
            "-SkipSmoke",
            "-ExpectedBuildId",
            CURRENT_BUILD,
        )
        output = result.stdout + result.stderr

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(STALE_BUILD, output)
        self.assertIn(CURRENT_BUILD, output)

    def test_a_valid_package_with_a_matching_build_passes(self):
        payload = product_payload()
        manifest = build_manifest(payload, CURRENT_BUILD)
        archive = make_package(self.tmp / "valido.zip", payload, manifest)

        result = verify(
            archive,
            "-AllowMissingRuntime",
            "-SkipSmoke",
            "-ExpectedBuildId",
            CURRENT_BUILD,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_verifier_refuses_a_source_the_manifest_does_not_declare(self):
        payload = product_payload()
        manifest = build_manifest(payload, CURRENT_BUILD)
        payload = dict(payload, **{"extension/extra.js": b"// added later\n"})
        archive = make_package(self.tmp / "extra.zip", payload, manifest)

        result = verify(archive, "-AllowMissingRuntime", "-SkipSmoke")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("extension/extra.js", result.stdout + result.stderr)

    def test_verifier_refuses_a_covered_source_with_a_disguised_path(self):
        """Case and ./ prefixes must not smuggle a source past the coverage check."""

        payload = product_payload()
        manifest = build_manifest(payload, CURRENT_BUILD)
        for disguise in ("APP/main.py", "./app/main.py"):
            with self.subTest(disfarce=disguise):
                disguised = dict(payload)
                disguised[disguise] = b"# undeclared\n"
                archive = make_package(self.tmp / f"disfarcado-{len(disguise)}.zip", disguised, manifest)

                result = verify(archive, "-AllowMissingRuntime", "-SkipSmoke")

                self.assertNotEqual(result.returncode, 0)

    def test_verifier_refuses_a_declared_file_that_is_absent(self):
        payload = product_payload()
        manifest = build_manifest(payload, CURRENT_BUILD)
        manifest["files"] = list(manifest["files"]) + [
            {"path": "app/ghost.py", "size": 12, "sha256": "1" * 64}
        ]
        archive = make_package(self.tmp / "ausente.zip", payload, manifest)

        result = verify(archive, "-AllowMissingRuntime", "-SkipSmoke")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("app/ghost.py", result.stdout + result.stderr)

    def test_verifier_refuses_a_declared_size_that_does_not_match(self):
        payload = product_payload()
        manifest = build_manifest(payload, CURRENT_BUILD)
        manifest["files"][0]["size"] = int(manifest["files"][0]["size"]) + 1
        archive = make_package(self.tmp / "tamanho.zip", payload, manifest)

        result = verify(archive, "-AllowMissingRuntime", "-SkipSmoke")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(manifest["files"][0]["path"], result.stdout + result.stderr)

    def test_verifier_refuses_an_invalid_manifest(self):
        payload = product_payload()
        cases = {
            "schema": lambda manifest: manifest.update({"schema": 2}),
            "build": lambda manifest: manifest.update({"build_id": "not-a-sha"}),
            "duplicado": lambda manifest: manifest.update(
                {"files": list(manifest["files"]) + [dict(manifest["files"][0])]}
            ),
            "hash": lambda manifest: manifest["files"][0].update({"sha256": "xyz"}),
        }
        for label, mutate in cases.items():
            with self.subTest(caso=label):
                manifest = build_manifest(payload, CURRENT_BUILD)
                mutate(manifest)
                archive = make_package(self.tmp / f"invalido-{label}.zip", payload, manifest)

                result = verify(archive, "-AllowMissingRuntime", "-SkipSmoke")

                self.assertNotEqual(result.returncode, 0)

    def test_a_release_package_from_a_dirty_tree_is_refused(self):
        payload = release_payload()
        manifest = build_manifest(payload, CURRENT_BUILD)
        manifest["source_dirty"] = True
        archive = make_package(self.tmp / "sujo-release.zip", payload, manifest)

        result = verify(archive, "-SkipSmoke")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source_dirty", result.stdout + result.stderr)

    def test_release_verification_requires_the_expected_build(self):
        dist_zip = REPO_ROOT / "dist" / "Atos-TCE-portable.zip"
        if not dist_zip.is_file():
            self.skipTest("dist/Atos-TCE-portable.zip ausente neste checkout")

        result = verify(dist_zip, "-SkipSmoke")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ExpectedBuildId", result.stdout + result.stderr)

    def test_verifier_refuses_release_bytes_that_differ_from_the_commit(self):
        """A rewritten manifest cannot authenticate bytes the commit never had."""

        product = repo_payload()
        build_id = head_commit()
        tampered = dict(product)
        victim = next(name for name in sorted(tampered) if name.startswith("app/"))
        tampered[victim] = tampered[victim] + b"\n# injected after the commit\n"
        payload = release_payload(tampered)
        manifest = build_manifest(tampered, build_id)
        archive = make_package(self.tmp / "reescrito.zip", payload, manifest)

        result = verify(archive, "-SkipSmoke", "-ExpectedBuildId", build_id)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(victim, result.stdout + result.stderr)

    def test_verifier_refuses_release_bytes_missing_from_the_commit(self):
        product = dict(repo_payload())
        build_id = head_commit()
        # Sorts before every real app/ path, so this file is the one the verifier
        # reports when the rest of the tree is also clean or dirty.
        product["app/aaa-untracked-extra.py"] = b"# never committed\n"
        payload = release_payload(product)
        manifest = build_manifest(product, build_id)
        archive = make_package(self.tmp / "nao-commitado.zip", payload, manifest)

        result = verify(archive, "-SkipSmoke", "-ExpectedBuildId", build_id)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("app/aaa-untracked-extra.py", result.stdout + result.stderr)

    def test_verifier_ignores_the_environment_build_pin_for_provenance(self):
        """The environment labels runs; it must not stand in for the manifest."""

        payload = product_payload()
        manifest = build_manifest(payload, STALE_BUILD)
        archive = make_package(self.tmp / "env-nao-basta.zip", payload, manifest)

        command_env = powershell_env()
        command_env["ATOS_TCE_BUILD_ID"] = CURRENT_BUILD
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(VERIFIER),
                "-ZipPath",
                str(archive),
                "-AllowMissingRuntime",
                "-SkipSmoke",
                "-ExpectedBuildId",
                CURRENT_BUILD,
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=command_env,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(STALE_BUILD, result.stdout + result.stderr)

    def test_a_dirty_source_is_refused_for_a_release_build(self):
        """A release build must refuse a tree with uncommitted source changes."""

        repo = self.tmp / "repo"
        (repo / "packaging" / "licenses").mkdir(parents=True)
        (repo / "app").mkdir()
        (repo / "extension").mkdir()
        (repo / "scripts").mkdir()
        for name, data in product_payload().items():
            target = repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        shutil.copy2(REPO_ROOT / "packaging" / "build-portable.ps1", repo / "packaging" / "build-portable.ps1")
        shutil.copy2(REPO_ROOT / "packaging" / "verify-package.ps1", repo / "packaging" / "verify-package.ps1")
        (repo / "packaging" / "licenses" / "README.md").write_text("# licencas\n", encoding="utf-8")

        def git(*arguments):
            return subprocess.run(
                ["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.com", *arguments],
                cwd=str(repo),
                capture_output=True,
                text=True,
            )

        self.assertEqual(git("init", "-q").returncode, 0)
        self.assertEqual(git("add", "-A").returncode, 0)
        self.assertEqual(git("commit", "-q", "-m", "fixture").returncode, 0)

        def build(destination):
            return powershell(
                repo / "packaging" / "build-portable.ps1",
                "-SkipRuntime",
                "-OutputPath",
                destination,
                "-StagingRoot",
                "staging-package-dirty",
                cwd=repo,
            )

        clean = build(self.tmp / "limpo.zip")
        self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)

        (repo / "app" / "main.py").write_bytes(b"print('changed but not committed')\n")
        dirty = build(self.tmp / "sujo.zip")

        self.assertNotEqual(dirty.returncode, 0)
        # ASCII-only assertions: the refusal text is Portuguese and the encoding
        # of a captured PowerShell stream is not worth depending on.
        self.assertIn("working tree", dirty.stdout + dirty.stderr)
        self.assertIn("recusado", dirty.stdout + dirty.stderr)


if __name__ == "__main__":
    unittest.main()
