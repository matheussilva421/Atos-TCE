"""Behavioral contracts for the isolated Chrome/CDP development lab."""

from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote


REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = REPO_ROOT / "scripts" / "portal-lab" / "Start-AtosChrome.ps1"
CDP_CHECKER = REPO_ROOT / "scripts" / "portal-lab" / "Test-CdpEndpoint.ps1"
MESA_QA_LAUNCHER = REPO_ROOT / "scripts" / "portal-lab" / "launch_mesa_in_qa_chrome.py"
MCP_CONFIG = REPO_ROOT / "devtools" / "area-restrita" / "chrome-devtools-mcp.example.json"
MCP_SAFETY = REPO_ROOT / ".agents" / "skills" / "area-restrita" / "references" / "safety.md"
SANITIZER = REPO_ROOT / "scripts" / "portal-lab" / "sanitize-capture.py"
STRUCTURE_CAPTURE = REPO_ROOT / "scripts" / "portal-lab" / "capture-structure.js"
CAPTURE_COMPARATOR = REPO_ROOT / "scripts" / "portal-lab" / "compare-captures.py"


def powershell_env() -> dict:
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


def run_powershell(script: Path, *arguments) -> subprocess.CompletedProcess:
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
        cwd=REPO_ROOT,
        env=powershell_env(),
        timeout=20,
    )


@contextmanager
def cdp_fixture(websocket_url: str, status: int = 200):
    payload = {"webSocketDebuggerUrl": websocket_url}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.server.requests.append(self.path)
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.requests = []
    server.payload = payload
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@contextmanager
def cdp_browser_fixture():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.server.requests.append(("GET", self.path))
            body = json.dumps(
                {"webSocketDebuggerUrl": f"ws://127.0.0.1:{self.server.server_port}/devtools/browser/test"}
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_PUT(self):
            self.server.requests.append(("PUT", self.path))
            from urllib.parse import unquote, urlsplit

            target_url = unquote(urlsplit(self.path).query)
            body = json.dumps({"id": "test-target", "type": "page", "url": target_url}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.requests = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class ChromeLauncherContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.chrome = self.root / "chrome.exe"
        self.chrome.write_bytes(b"test executable; never launched with -WhatIf")
        self.profile = self.root / "isolated chrome profile"

    def test_preview_uses_loopback_and_profile_outside_repository_without_creating_it(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]

        result = run_powershell(
            LAUNCHER,
            "-Port",
            port,
            "-ProfileRoot",
            self.profile,
            "-ChromePath",
            self.chrome,
            "-WhatIf",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        launch = json.loads(result.stdout)
        self.assertEqual(launch["port"], port)
        self.assertEqual(Path(launch["profileRoot"]), self.profile.resolve())
        self.assertEqual(Path(launch["executable"]), self.chrome.resolve())
        self.assertIn("--remote-debugging-address=127.0.0.1", launch["arguments"])
        self.assertIn(f"--remote-debugging-port={port}", launch["arguments"])
        self.assertIn(f'--user-data-dir="{self.profile.resolve()}"', launch["arguments"])
        self.assertIn("--no-first-run", launch["arguments"])
        self.assertFalse(self.profile.exists())

    def test_launcher_refuses_a_profile_inside_the_repository(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        profile = REPO_ROOT / "tmp" / "portal-lab" / "must-not-be-created"

        result = run_powershell(
            LAUNCHER,
            "-Port",
            port,
            "-ProfileRoot",
            profile,
            "-ChromePath",
            self.chrome,
            "-WhatIf",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ProfileRoot must be outside the repository", result.stderr)
        self.assertFalse(profile.exists())


class CdpEndpointContractTests(unittest.TestCase):
    def test_checker_reads_only_the_loopback_version_endpoint_and_redacts_websocket_url(self):
        with cdp_fixture("pending") as server:
            server.payload["webSocketDebuggerUrl"] = (
                f"ws://127.0.0.1:{server.server_port}/devtools/browser/fake-id"
            )
            result = run_powershell(CDP_CHECKER, "-Port", server.server_port)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"CDP_ENDPOINT_OK port={server.server_port}", result.stdout)
        self.assertEqual(server.requests, ["/json/version"])
        self.assertNotIn("/devtools/browser/", result.stdout)

    def test_checker_rejects_a_non_loopback_websocket_host(self):
        with cdp_fixture("ws://192.0.2.10:9222/devtools/browser/fake-id") as server:
            result = run_powershell(CDP_CHECKER, "-Port", server.server_port)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CDP websocket endpoint must use loopback", result.stderr)
        self.assertNotIn("192.0.2.10", result.stderr)

    def test_checker_rejects_non_success_http_status(self):
        with cdp_fixture("ws://127.0.0.1:9222/devtools/browser/fake-id", status=503) as server:
            result = run_powershell(CDP_CHECKER, "-Port", server.server_port)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CDP version endpoint did not return HTTP 200", result.stderr)


class MesaQaHandoffContractTests(unittest.TestCase):
    def load_launcher(self):
        self.assertTrue(MESA_QA_LAUNCHER.is_file(), "missing Mesa-to-QA Chrome launcher")
        spec = importlib.util.spec_from_file_location("portal_lab_mesa_qa_launcher", MESA_QA_LAUNCHER)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_bootstrap_handoff_opens_only_the_official_local_bootstrap_in_loopback_cdp(self):
        with cdp_browser_fixture() as server:
            cdp_url = f"http://127.0.0.1:{server.server_port}"
            bootstrap_url = "http://127.0.0.1:18743/bootstrap#token=synthetic-one-time-code"

            opened = self.load_launcher().open_bootstrap_in_chrome(cdp_url, bootstrap_url)

            self.assertTrue(opened)
            self.assertEqual(
                server.requests,
                [
                    ("GET", "/json/version"),
                    ("PUT", "/json/new?" + quote(bootstrap_url, safe="")),
                ],
            )

    def test_handoff_rejects_non_loopback_targets_before_network_access(self):
        with cdp_browser_fixture() as server:
            launcher = self.load_launcher()

            opened = launcher.open_bootstrap_in_chrome(
                f"http://127.0.0.1:{server.server_port}",
                "https://portal.example/act",
            )

            self.assertFalse(opened)
            self.assertEqual(server.requests, [])

    def test_handoff_rejects_noncanonical_local_bootstrap_urls_before_network_access(self):
        with cdp_browser_fixture() as server:
            launcher = self.load_launcher()
            cdp_url = f"http://127.0.0.1:{server.server_port}"
            invalid_urls = (
                "http://user@127.0.0.1:18743/bootstrap#token=synthetic-one-time-code",
                "http://127.0.0.1:18743/bootstrap#token=synthetic-one-time-code&extra=1",
            )

            for bootstrap_url in invalid_urls:
                with self.subTest(bootstrap_url="malformed local bootstrap"):
                    self.assertFalse(launcher.open_bootstrap_in_chrome(cdp_url, bootstrap_url))

            self.assertEqual(server.requests, [])

    def test_safe_handoff_message_never_echoes_the_one_time_url(self):
        one_time_url = "http://127.0.0.1:18743/bootstrap#token=synthetic-one-time-code"

        message = self.load_launcher().safe_bootstrap_handoff_message(one_time_url)

        self.assertIn("Chrome QA", message)
        self.assertNotIn("synthetic-one-time-code", message)

    def test_launcher_refuses_a_port_already_owned_by_another_mesa_process(self):
        with cdp_browser_fixture() as server:
            launcher = self.load_launcher()

            available = launcher.can_bind_mesa_port("127.0.0.1", server.server_port)

            self.assertFalse(available)

    def test_launcher_only_allows_the_loopback_host_used_by_bootstrap(self):
        launcher = self.load_launcher()

        self.assertFalse(launcher.can_bind_mesa_port("0.0.0.0", 18743))


class McpConfigContractTests(unittest.TestCase):
    def test_example_uses_dedicated_loopback_chrome_and_privacy_flags(self):
        self.assertTrue(MCP_CONFIG.is_file(), "missing versioned Chrome DevTools MCP example")
        config = json.loads(MCP_CONFIG.read_text(encoding="utf-8"))
        server = config["mcpServers"]["chrome-devtools"]
        args = server["args"]

        self.assertEqual(server["command"], "npx")
        self.assertIn("chrome-devtools-mcp@latest", args)
        self.assertIn("--browser-url=http://127.0.0.1:9222", args)
        self.assertIn("--categoryExtensions", args)
        self.assertIn("--no-usage-statistics", args)
        self.assertIn("--no-performance-crux", args)
        self.assertEqual(sum(arg.startswith("--browser-url=") for arg in args), 1)

    def test_safety_policy_documents_default_l1_l2_and_prohibited_actions(self):
        self.assertTrue(MCP_SAFETY.is_file(), "missing Area Restrita MCP safety policy")
        policy = MCP_SAFETY.read_text(encoding="utf-8").casefold()
        required = (
            "permitido por padrão",
            "listar páginas/frames",
            "snapshot",
            "console",
            "network",
            "evaluate de leitura",
            "screenshot estrutural",
            "exige gate l1",
            "paginação",
            "abrir complementar ato",
            "exige gate l2",
            "selecionar interessado",
            "preencher campos",
            "proibido",
            "clicar conclusão",
            "submit final",
            "assinatura",
            "tramitação",
        )
        for item in required:
            with self.subTest(item=item):
                self.assertIn(item, policy)


class CaptureSanitizerContractTests(unittest.TestCase):
    def load_sanitizer(self):
        self.assertTrue(SANITIZER.is_file(), f"missing sanitizer: {SANITIZER.relative_to(REPO_ROOT)}")
        spec = importlib.util.spec_from_file_location("portal_lab_sanitizer", SANITIZER)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_sanitizer_removes_private_values_and_url_query(self):
        raw = {
            "url": "https://portal/ComplementarAto.asp?cpf=12345678900",
            "cookies": [{"name": "ASPSESSIONID", "value": "secret"}],
            "fields": [{"id": "txtMatricula", "value": "12345"}],
            "text": "MARIA DA SILVA 012.345.678-90 processo 123456/2026",
        }

        clean = self.load_sanitizer().sanitize_capture(raw)
        blob = json.dumps(clean, ensure_ascii=False)

        for forbidden in (
            "12345678900",
            "secret",
            "12345",
            "MARIA DA SILVA",
            "012.345.678-90",
            "123456/2026",
            "ASPSESSIONID",
            "cpf=",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, blob)
        self.assertEqual(clean["url"], "https://portal/ComplementarAto.asp")
        self.assertIn("textClass", clean)

    def test_sanitizer_preserves_only_structural_control_metadata(self):
        raw = {
            "route": "/ComplementarAto.asp?processo=123456/2026",
            "readyState": "complete",
            "framePath": [{"tag": "iframe", "id": "frmMain", "name": "main"}],
            "controls": [
                {
                    "tag": "select",
                    "id": "cmbInteressado",
                    "name": "interessado",
                    "type": "select-one",
                    "disabled": False,
                    "readOnly": False,
                    "optionCount": 4,
                    "value": "MARIA DA SILVA",
                }
            ],
            "sentinels": ["FORM_COMPLEMENTAR"],
            "childFrameCount": 1,
            "headers": {"Authorization": "Bearer private-token"},
            "storage": {"access_token": "private-token"},
        }

        clean = self.load_sanitizer().sanitize_capture(raw)

        self.assertEqual(clean["route"], "/ComplementarAto.asp")
        self.assertEqual(clean["readyState"], "complete")
        self.assertEqual(clean["framePath"], [{"tag": "iframe", "id": "frmMain", "name": "main"}])
        self.assertEqual(
            clean["controls"],
            [
                {
                    "tag": "select",
                    "id": "cmbInteressado",
                    "name": "interessado",
                    "type": "select-one",
                    "disabled": False,
                    "readOnly": False,
                    "optionCount": 4,
                }
            ],
        )
        self.assertEqual(clean["sentinels"], ["FORM_COMPLEMENTAR"])
        self.assertEqual(clean["childFrameCount"], 1)
        self.assertNotIn("headers", clean)
        self.assertNotIn("storage", clean)

    def test_sanitizer_preserves_frame_visibility_and_form_counts_only(self):
        raw = {
            "route": "/ComplementarAto.asp",
            "framePath": [
                {"tag": "iframe", "id": "iframeOBJ", "name": "iframe4", "index": 4},
                {"tag": "iframe", "id": "form", "name": "form", "index": 0},
            ],
            "frameBox": {
                "id": "form",
                "name": "form",
                "hidden": False,
                "display": "block",
                "visibility": "visible",
                "width": 1397,
                "height": 565,
                "value": "must never persist",
            },
            "forms": [
                {"id": "Form1", "name": "form1", "method": "post", "controlCount": 26, "value": "private"}
            ],
            "tableRows": 21,
            "controlCount": 26,
            "radioCount": 1,
            "selectCount": 4,
        }

        clean = self.load_sanitizer().sanitize_capture(raw)

        self.assertEqual(
            clean["frameBox"],
            {
                "id": "form",
                "name": "form",
                "hidden": False,
                "display": "block",
                "visibility": "visible",
                "width": 1397,
                "height": 565,
            },
        )
        self.assertEqual(
            clean["forms"],
            [{"id": "Form1", "name": "form1", "method": "POST", "controlCount": 26}],
        )
        self.assertEqual(clean["tableRows"], 21)
        self.assertEqual(clean["controlCount"], 26)
        self.assertEqual(clean["radioCount"], 1)
        self.assertEqual(clean["selectCount"], 4)
        self.assertNotIn("value", json.dumps(clean))

    def test_sanitizer_fails_closed_when_identifiers_or_tokens_survive(self):
        sanitizer = self.load_sanitizer()
        for key, value in (
            ("id", "123.456.789-00"),
            ("name", "123456/2026"),
            ("id", "Bearer abcdefghijklmnop"),
            ("url", "https://portal/123456%2F2026"),
        ):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                raw = {"url": value} if key == "url" else {"controls": [{"tag": "input", key: value}]}
                sanitizer.sanitize_capture(raw)

    def test_sanitizer_cli_preserves_existing_output_unless_force_is_explicit(self):
        self.assertTrue(SANITIZER.is_file(), "missing sanitizer CLI")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "raw.json"
            destination = Path(directory) / "sanitized.json"
            source.write_text(json.dumps({"url": "https://portal/list.asp?cpf=12345678900"}), encoding="utf-8")
            destination.write_text("preserve-existing-output", encoding="utf-8")

            refused = subprocess.run(
                [sys.executable, str(SANITIZER), str(source), str(destination)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertNotEqual(refused.returncode, 0)
            self.assertEqual(destination.read_text(encoding="utf-8"), "preserve-existing-output")

            forced = subprocess.run(
                [sys.executable, str(SANITIZER), "--force", str(source), str(destination)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(forced.returncode, 0, forced.stderr)
            clean = destination.read_text(encoding="utf-8")
            self.assertNotIn("12345678900", clean)
            self.assertIn("https://portal/list.asp", clean)


class StructureCaptureContractTests(unittest.TestCase):
    def test_capture_reads_structure_without_accessing_control_values(self):
        self.assertTrue(STRUCTURE_CAPTURE.is_file(), "missing structural capture script")
        harness = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const input = {tagName: 'INPUT', id: 'txtMatricula', name: 'matricula', type: 'text', disabled: false, readOnly: false};
const select = {tagName: 'SELECT', id: 'cmbInteressado', name: 'interessado', type: 'select-one', disabled: false, readOnly: true, options: [{}, {}, {}]};
Object.defineProperty(input, 'value', {get() { throw new Error('input value was accessed'); }});
Object.defineProperty(select, 'value', {get() { throw new Error('select value was accessed'); }});
const window = {location: {pathname: '/ComplementarAto.asp'}, frameElement: null};
window.top = window;
const document = {
  readyState: 'complete',
  querySelectorAll(selector) { return selector === 'iframe,frame' ? [{}, {}] : [input, select]; }
};
const result = vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), {window, document});
process.stdout.write(JSON.stringify(result));
"""
        result = subprocess.run(
            ["node", "-e", harness, str(STRUCTURE_CAPTURE)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        capture = json.loads(result.stdout)
        self.assertEqual(capture["route"], "/ComplementarAto.asp")
        self.assertEqual(capture["readyState"], "complete")
        self.assertEqual(capture["framePath"], [])
        self.assertEqual(capture["childFrameCount"], 2)
        self.assertEqual(capture["sentinels"], [])
        self.assertEqual(capture["controls"][0]["id"], "txtMatricula")
        self.assertEqual(capture["controls"][1]["optionCount"], 3)
        self.assertNotIn("value", result.stdout)


class CaptureComparisonContractTests(unittest.TestCase):
    def test_comparator_reports_frame_route_sentinel_control_and_state_deltas(self):
        self.assertTrue(CAPTURE_COMPARATOR.is_file(), "missing capture comparator")
        before = {
            "frames": [
                {
                    "route": "/lista.asp",
                    "readyState": "complete",
                    "framePath": ["top"],
                    "sentinels": ["LISTA"],
                    "controls": [
                        {"tag": "input", "id": "filtro", "type": "text", "disabled": False, "readOnly": False, "optionCount": 0}
                    ],
                }
            ]
        }
        after = {
            "frames": [
                {
                    "route": "/ComplementarAto.asp",
                    "readyState": "interactive",
                    "framePath": ["top"],
                    "sentinels": ["FORMULARIO"],
                    "controls": [
                        {"tag": "select", "id": "interessado", "type": "select-one", "disabled": False, "readOnly": False, "optionCount": 3}
                    ],
                },
                {
                    "route": "/ComplementarAto.asp",
                    "readyState": "complete",
                    "framePath": ["top", "botoes"],
                    "sentinels": ["ACOES"],
                    "controls": [],
                },
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            before_path = Path(directory) / "before.json"
            after_path = Path(directory) / "after.json"
            before_path.write_text(json.dumps(before), encoding="utf-8")
            after_path.write_text(json.dumps(after), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(CAPTURE_COMPARATOR), str(before_path), str(after_path)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=10,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        delta = json.loads(result.stdout)
        self.assertEqual(len(delta["framesAdded"]), 1)
        self.assertEqual(delta["framesRemoved"], [])
        self.assertEqual(len(delta["routesChanged"]), 1)
        self.assertEqual(delta["sentinelsAdded"], [{"framePath": ["top"], "sentinel": "FORMULARIO"}, {"framePath": ["top", "botoes"], "sentinel": "ACOES"}])
        self.assertEqual(delta["sentinelsRemoved"], [{"framePath": ["top"], "sentinel": "LISTA"}])
        self.assertEqual(len(delta["controlsAdded"]), 1)
        self.assertEqual(len(delta["controlsRemoved"]), 1)
        self.assertEqual(len(delta["readyStateChanges"]), 1)


if __name__ == "__main__":
    unittest.main()
