"""Behavioral contracts for the isolated Chrome/CDP development lab."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = REPO_ROOT / "scripts" / "portal-lab" / "Start-AtosChrome.ps1"
CDP_CHECKER = REPO_ROOT / "scripts" / "portal-lab" / "Test-CdpEndpoint.ps1"


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


if __name__ == "__main__":
    unittest.main()
