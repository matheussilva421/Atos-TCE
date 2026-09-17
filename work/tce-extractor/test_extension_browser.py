"""Task 7 browser contract and Chrome fixture smoke tests.

The smoke uses a disposable Chrome profile and a synthetic HTTPS origin that
is mapped to loopback.  It never opens the real TCE portal or an authenticated
browser profile.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import ssl
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from playwright.sync_api import (
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)
ROOT = Path(__file__).resolve().parent
EXTENSION = ROOT / "portable" / "extensao-complementar-ato"
FIXTURE_ROOT = ROOT / "tests" / "fixtures"
DATASET = FIXTURE_ROOT / "dados-complementar-ato.json"
SCREENSHOT = ROOT.parent / "outputs" / "qa-extensao-fixture-test.png"
ALLOWED_HOST = "novaarearestrita.tce.rn.gov.br"
ALLOWED_URL = f"https://{ALLOWED_HOST}/"
INSTALLED_CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
DEFAULT_SMOKE_TIMEOUT_SECONDS = 60.0


class SmokeTimeout(TimeoutError):
    """Raised when the disposable browser smoke reaches its total deadline."""


def _remaining_timeout_ms(deadline: float, operation: str, cap_ms: int = 10_000) -> int:
    remaining_ms = int((deadline - time.monotonic()) * 1_000)
    if remaining_ms <= 0:
        raise SmokeTimeout(f"Task 7 smoke deadline exceeded during {operation}")
    return min(cap_ms, remaining_ms)


def _run_with_deadline(
    callback: Any,
    deadline: float | None,
    operation: str,
) -> None:
    if deadline is None:
        callback()
        return
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise SmokeTimeout(f"Task 7 smoke deadline exceeded during {operation}")
    error: list[BaseException] = []

    def invoke() -> None:
        try:
            callback()
        except BaseException as exc:  # pragma: no cover - exercised through caller
            error.append(exc)

    worker = threading.Thread(target=invoke, daemon=True)
    worker.start()
    worker.join(timeout=remaining)
    if worker.is_alive():
        raise SmokeTimeout(f"Task 7 smoke deadline exceeded during {operation}")
    if error:
        raise error[0]


def _close_context(context: BrowserContext, deadline: float | None) -> None:
    if deadline is not None and deadline - time.monotonic() <= 0:
        raise SmokeTimeout("Task 7 smoke deadline exceeded during browser context cleanup")
    # Playwright's sync API is greenlet-bound to the thread that owns the
    # BrowserContext; invoking context.close from a deadline helper thread
    # raises greenlet.error.  The CLI supervisor owns the hard outer deadline
    # and reaps this worker if close does not return.
    context.close()


class _QuietFixtureHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


class FixtureServer:
    def __init__(
        self,
        root: Path,
        certificate_dir: Path,
        deadline: float | None = None,
    ) -> None:
        self.root = root
        self.certificate_dir = certificate_dir
        self.deadline = deadline
        self.httpd: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def __enter__(self) -> "FixtureServer":
        self.certificate_dir.mkdir(parents=True, exist_ok=True)
        certificate, key = _make_certificate(self.certificate_dir)
        handler = lambda *args, **kwargs: _QuietFixtureHandler(
            *args, directory=str(self.root), **kwargs
        )
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 443), handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=str(certificate), keyfile=str(key))
        self.httpd.socket = context.wrap_socket(self.httpd.socket, server_side=True)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return self

    def close(self) -> None:
        if self.httpd is not None:
            _run_with_deadline(self.httpd.shutdown, self.deadline, "fixture server shutdown")
            self.httpd.server_close()
        if self.thread is not None:
            if self.deadline is None:
                self.thread.join(timeout=5)
            else:
                remaining = self.deadline - time.monotonic()
                if remaining <= 0:
                    raise SmokeTimeout("Task 7 smoke deadline exceeded during fixture server join")
                self.thread.join(timeout=remaining)
                if self.thread.is_alive():
                    raise SmokeTimeout("Task 7 smoke deadline exceeded during fixture server join")

    def __exit__(self, *_exc: object) -> None:
        self.close()


def _make_certificate(directory: Path) -> tuple[Path, Path]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, ALLOWED_HOST)])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=2))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(ALLOWED_HOST)]), critical=False
        )
        .sign(key, hashes.SHA256())
    )
    certificate_path = directory / "fixture-cert.pem"
    key_path = directory / "fixture-key.pem"
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    return certificate_path, key_path


def _assert_manifest_contract(test: unittest.TestCase) -> dict[str, Any]:
    manifest_path = EXTENSION / "manifest.json"
    test.assertTrue(manifest_path.is_file(), manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    test.assertEqual(manifest["manifest_version"], 3)
    test.assertEqual(manifest["version"], "1.1.0")
    test.assertEqual(
        manifest["permissions"], ["storage", "sidePanel", "alarms", "webNavigation"]
    )
    test.assertEqual(
        manifest["host_permissions"], [f"https://{ALLOWED_HOST}/*", "http://127.0.0.1/*"]
    )
    test.assertEqual(
        manifest["content_scripts"][0]["matches"],
        [f"https://{ALLOWED_HOST}/*"],
    )
    test.assertTrue(manifest["content_scripts"][0]["all_frames"])
    test.assertEqual(manifest["background"]["type"], "module")
    test.assertEqual(manifest["side_panel"]["default_path"], "sidepanel/panel.html")
    test.assertNotIn("localhost", json.dumps(manifest).lower())
    forbidden = {"cookies", "downloads", "debugger", "clipboardWrite", "<all_urls>"}
    serialized = json.dumps(manifest)
    for value in forbidden:
        test.assertNotIn(value, serialized)
    test.assertNotIn("processos.tce", serialized)
    test.assertNotIn("e-contas", serialized.lower())
    worker_source = (EXTENSION / "background" / "service-worker.js").read_text(
        encoding="utf-8"
    )
    test.assertIn("openPanelOnActionClick", worker_source)
    content_source = (EXTENSION / "content" / "form-detector.js").read_text(
        encoding="utf-8"
    )
    test.assertIn("installContentScript({ documentRef: runtimeDocument, chromeApi: runtimeChrome });", content_source)
    return manifest


def _open_context(
    playwright: Any,
    profile: Path,
    extension: Path,
    executable_path: Path,
    timeout_ms: int | None = None,
) -> BrowserContext:
    launch_options: dict[str, Any] = {
        "user_data_dir": str(profile),
        "executable_path": str(executable_path),
        "headless": False,
        "args": [
            f"--disable-extensions-except={extension}",
            f"--load-extension={extension}",
            f"--host-resolver-rules=MAP {ALLOWED_HOST} 127.0.0.1",
            "--ignore-certificate-errors",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
        ],
    }
    if timeout_ms is not None:
        launch_options["timeout"] = timeout_ms
    return playwright.chromium.launch_persistent_context(
        **launch_options,
    )


def _extension_id(context: BrowserContext, deadline: float | None = None) -> str:
    worker = context.service_workers[0] if context.service_workers else None
    if worker is None:
        # A newly loaded MV3 worker is lazy. This local manager page wakes it
        # without touching any portal or authenticated browser profile.
        manager = context.new_page()
        manager.goto(
            "chrome://extensions/",
            wait_until="domcontentloaded",
            **({"timeout": _remaining_timeout_ms(deadline, "extension manager")}
               if deadline is not None else {}),
        )
        manager.close()
        worker = context.service_workers[0] if context.service_workers else None
        if worker is None:
            worker = context.wait_for_event(
                "serviceworker",
                timeout=(
                    _remaining_timeout_ms(deadline, "service worker startup")
                    if deadline is not None
                    else 10_000
                ),
            )
    return worker.url.split("/")[2]


def _form_frame(page: Page):
    return next(
        frame
        for frame in page.frames
        if frame.url.endswith("/complementar-ato-form.html")
    )


def _chrome_version(page: Page) -> str:
    user_agent = page.evaluate("() => navigator.userAgent")
    match = re.search(r"(?:HeadlessChrome|Chrome|Chromium)/([\d.]+)", user_agent)
    return match.group(1) if match else "unknown"


def _wait_for_preview(
    panel: Page,
    diagnostics: list[str] | None = None,
    deadline: float | None = None,
) -> None:
    panel.locator("#screen-status").wait_for(state="visible")
    try:
        panel.wait_for_function(
            "() => document.querySelector('#identity-status').textContent.includes('Processo')",
            timeout=(
                _remaining_timeout_ms(deadline, "preview identity")
                if deadline is not None
                else 10_000
            ),
        )
        panel.wait_for_function(
            "() => document.querySelectorAll('#preview-body [data-field]').length === 7",
            timeout=(
                _remaining_timeout_ms(deadline, "preview rows")
                if deadline is not None
                else 10_000
            ),
        )
    except PlaywrightTimeoutError as error:
        raise AssertionError(
            "preview did not become ready: "
            + panel.locator("body").inner_text()
            + ("\nDiagnostics:\n" + "\n".join(diagnostics) if diagnostics else "")
        ) from error


def _protected_form_snapshot(frame: Any) -> dict[str, Any]:
    return frame.evaluate(
        """() => {
            const values = {
                proventos: document.querySelector('#txtValorProventos').value,
                contribuicao: document.querySelector('#txtValorContribuicao').value,
                conclusion: document.querySelector('#txtConclusaoAnalise').value,
                complement: document.querySelector('#btnComplementar').dataset.clickCount,
                clear: document.querySelector('#btnLimpar').dataset.clickCount
            };
            return {
                values,
                utf8: Array.from(new TextEncoder().encode(JSON.stringify(values)))
            };
        }"""
    )


def _assert_protected_form_unchanged(
    before: dict[str, Any], after: dict[str, Any]
) -> None:
    before_values = before["values"]
    after_values = after["values"]
    if before_values != after_values:
        raise AssertionError(
            f"protected form values changed: before={before_values!r} after={after_values!r}"
        )
    before_bytes = bytes(before["utf8"])
    after_bytes = bytes(after["utf8"])
    if before_bytes != after_bytes:
        for index, (before_byte, after_byte) in enumerate(
            zip(before_bytes, after_bytes)
        ):
            if before_byte != after_byte:
                raise AssertionError(
                    "protected form UTF-8 snapshot changed at byte "
                    f"{index}: before={before_byte} after={after_byte}"
                )
        raise AssertionError(
            "protected form UTF-8 snapshot changed length: "
            f"before={len(before_bytes)} after={len(after_bytes)}"
        )


def run_smoke(
    extension: Path = EXTENSION,
    fixture_root: Path = FIXTURE_ROOT,
    dataset: Path = DATASET,
    screenshot: Path = SCREENSHOT,
    timeout_seconds: float = DEFAULT_SMOKE_TIMEOUT_SECONDS,
    scratch_dir: Path | None = None,
) -> dict[str, Any]:
    """Run the complete disposable-profile smoke and return metadata only."""

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    started = time.monotonic()
    deadline = started + timeout_seconds
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    diagnostics: list[str] = []

    def record_console(label: str, message: Any) -> None:
        diagnostics.append(f"{label}: {message.type} {message.text}")

    def record_worker(worker: Any) -> None:
        worker.on("console", lambda message: record_console("WORKER", message))

    owned_scratch = scratch_dir is None
    scratch_path = (
        Path(tempfile.mkdtemp(prefix="tce-extension-fixture-") )
        if scratch_dir is None
        else scratch_dir.resolve()
    )
    scratch_path.mkdir(parents=True, exist_ok=True)
    try:
        with FixtureServer(fixture_root, scratch_path / "tls", deadline=deadline):
            with sync_playwright() as playwright:
                executable_path = Path(playwright.chromium.executable_path)
                profile = scratch_path / "chrome-profile"
                context: BrowserContext | None = None
                try:
                    context = _open_context(
                        playwright,
                        profile,
                        extension,
                        executable_path,
                        _remaining_timeout_ms(deadline, "browser startup", 15_000),
                    )
                    context.set_default_timeout(_remaining_timeout_ms(deadline, "browser action", 5_000))
                    context.set_default_navigation_timeout(_remaining_timeout_ms(deadline, "browser navigation", 10_000))
                    context.on("serviceworker", record_worker)
                    for worker in context.service_workers:
                        record_worker(worker)
                    page = context.new_page()
                    page.on("console", lambda message: record_console("PAGE", message))
                    page.goto(
                        f"{ALLOWED_URL}complementar-ato-shell.html",
                        wait_until="domcontentloaded",
                        timeout=_remaining_timeout_ms(deadline, "fixture navigation"),
                    )
                    page.wait_for_function(
                        "() => [...document.querySelectorAll('iframe')].some((iframe) => iframe.contentDocument?.readyState === 'complete')",
                        timeout=_remaining_timeout_ms(deadline, "fixture frame load"),
                    )
                    frame = _form_frame(page)
                    panel = context.new_page()
                    panel.on("console", lambda message: record_console("PANEL", message))
                    extension_id = _extension_id(context, deadline)
                    panel.goto(
                        f"chrome-extension://{extension_id}/sidepanel/panel.html",
                        wait_until="domcontentloaded",
                        timeout=_remaining_timeout_ms(deadline, "panel navigation"),
                    )
                    # A side panel belongs to the currently focused portal tab. The
                    # direct extension page used by this fixture has its own tab, so
                    # return focus to the fixture tab before sending panel messages.
                    page.bring_to_front()
                    panel.locator("#dataset-file").set_input_files(str(dataset))
                    _wait_for_preview(panel, diagnostics, deadline)
                    panel.locator("#identity-status").wait_for()
                    panel.screenshot(path=str(screenshot), full_page=True)

                    initial_kind = panel.locator(
                        '[data-field="modalidade"][data-kind]'
                    ).get_attribute("data-kind")
                    test_state: dict[str, Any] = {
                        "chrome_version": _chrome_version(page),
                        "initial_identity": panel.locator("#identity-status").inner_text(),
                        "initial_modality_kind": initial_kind,
                        "preview_rows": panel.locator("#preview-body [data-field]").count(),
                    }

                    before = _protected_form_snapshot(frame)
                    panel.locator("#fill-button").click()
                    panel.wait_for_function(
                        "() => document.querySelector('#screen-status').textContent.includes('Preenchimento')",
                        timeout=_remaining_timeout_ms(deadline, "field application"),
                    )
                    after = _protected_form_snapshot(frame)
                    expected_protected = {
                        "proventos": "R$ 9.999,99",
                        "contribuicao": "R$ 1.111,11",
                        "conclusion": "Conclusão manual intacta",
                        "complement": "0",
                        "clear": "0",
                    }
                    assert before["values"] == expected_protected
                    assert bytes(before["utf8"]) == bytes(
                        json.dumps(
                            expected_protected,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    )
                    assert after["values"] == expected_protected
                    _assert_protected_form_unchanged(before, after)
                    test_state["negative_controls_unchanged"] = True

                    panel.locator("#tab-details").click()
                    panel.locator("#review-section").wait_for(state="visible")
                    panel.locator("#reviewed-checkbox").check()
                    panel.wait_for_function(
                        "() => document.querySelector('#reviewed-checkbox').checked === true",
                        timeout=_remaining_timeout_ms(deadline, "review persistence"),
                    )

                    frame.evaluate(
                        """() => {
                            document.querySelector('#txtNumeroProcesso').value = '103487';
                            document.querySelector('#txtAnoProcesso').value = '2023';
                            const radios = [...document.querySelectorAll('input[type=radio]')];
                            radios[0].checked = true;
                            radios[1].checked = false;
                            const select = document.querySelector('#txtFundamentoLegal');
                            select.replaceChildren(
                                ...[
                                    ['f-tie-a', 'Fundamento documental alfa'],
                                    ['f-tie-b', 'Fundamento documental beta']
                                ].map(([value, label]) => {
                                    const option = document.createElement('option');
                                    option.value = value;
                                    option.textContent = label;
                                    return option;
                                })
                            );
                        }"""
                    )
                    panel.locator("#tab-principal").click()
                    panel.locator("#panel-tab-principal").wait_for(state="visible")
                    panel.locator("#refresh-button").click()
                    panel.wait_for_function(
                        "() => document.querySelector('#identity-status').textContent.includes('103487/2023')",
                        timeout=_remaining_timeout_ms(deadline, "process switch"),
                    )
                    legal_kind = panel.locator(
                        '[data-field="fundamento_legal"][data-kind]'
                    ).get_attribute("data-kind")
                    # Without a legal context served by the local bridge the
                    # foundation stays blocked instead of faking a tie.
                    assert legal_kind == "pending", legal_kind
                    assert panel.locator("#fill-button").is_enabled()
                    test_state["switched_without_reimport"] = True
                    test_state["recalculated_tie"] = legal_kind

                    incomplete = frame.evaluate(
                        """() => {
                            const gender = document.querySelector('#txtGenero');
                            gender.remove();
                            return document.querySelectorAll('#txtGenero').length;
                        }"""
                    )
                    assert incomplete == 0
                    panel.locator("#tab-principal").click()
                    panel.locator("#panel-tab-principal").wait_for(state="visible")
                    panel.locator("#refresh-button").click()
                    panel.wait_for_function(
                        "() => document.querySelector('#screen-status').dataset.state === 'blocked'",
                        timeout=_remaining_timeout_ms(deadline, "incomplete DOM block"),
                    )
                    assert not panel.locator("#fill-button").is_enabled()
                    test_state["incomplete_dom_blocked"] = True
                finally:
                    if context is not None:
                        _close_context(context, deadline)

                context = _open_context(
                    playwright,
                    profile,
                    extension,
                    executable_path,
                    _remaining_timeout_ms(deadline, "browser restart", 15_000),
                )
                try:
                    restored_page = context.new_page()
                    restored_page.goto(
                        f"{ALLOWED_URL}complementar-ato-shell.html",
                        wait_until="domcontentloaded",
                        timeout=_remaining_timeout_ms(deadline, "restored fixture navigation"),
                    )
                    restored_page.wait_for_function(
                        "() => [...document.querySelectorAll('iframe')].some((iframe) => iframe.contentDocument?.readyState === 'complete')",
                        timeout=_remaining_timeout_ms(deadline, "restored frame load"),
                    )
                    restored_panel = context.new_page()
                    restored_extension_id = _extension_id(context, deadline)
                    restored_panel.goto(
                        f"chrome-extension://{restored_extension_id}/sidepanel/panel.html",
                        wait_until="domcontentloaded",
                        timeout=_remaining_timeout_ms(deadline, "restored panel navigation"),
                    )
                    restored_page.bring_to_front()
                    restored_panel.locator("#tab-details").click()
                    restored_panel.locator("#review-section").wait_for(state="visible")
                    restored_panel.wait_for_function(
                        "() => document.querySelector('#dataset-status').textContent.includes('2 processos')",
                        timeout=_remaining_timeout_ms(deadline, "persisted dataset"),
                    )
                    restored_panel.wait_for_function(
                        "() => document.querySelector('#reviewed-checkbox').checked === true",
                        timeout=_remaining_timeout_ms(deadline, "persisted review"),
                    )
                    assert restored_panel.locator("#reviewed-checkbox").is_checked()
                    test_state["persisted_after_profile_restart"] = True
                finally:
                    _close_context(context, deadline)
                test_state["elapsed_seconds"] = round(time.monotonic() - started, 3)
                test_state["timeout_seconds"] = timeout_seconds
                return test_state
    finally:
        if owned_scratch and scratch_path.exists():
            _run_with_deadline(
                lambda: shutil.rmtree(scratch_path),
                deadline,
                "temporary directory cleanup",
            )


class ExtensionBrowserTests(unittest.TestCase):
    def test_context_cleanup_stays_on_playwright_owner_thread(self) -> None:
        owner_thread = threading.get_ident()
        close_threads: list[int] = []

        class FakeContext:
            def close(self) -> None:
                close_threads.append(threading.get_ident())

        _close_context(FakeContext(), time.monotonic() + 1.0)

        self.assertEqual(close_threads, [owner_thread])

    def test_protected_form_snapshot_is_utf8_stable(self) -> None:
        expected = {
            "proventos": "R$ 9.999,99",
            "contribuicao": "R$ 1.111,11",
            "conclusion": "Conclusão manual intacta",
            "complement": "0",
            "clear": "0",
        }

        class FakeFrame:
            def evaluate(self, script: str) -> dict[str, Any]:
                self.script = script
                encoded = list(
                    json.dumps(
                        expected,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ).encode("utf-8")
                )
                return {"values": expected, "utf8": encoded}

        frame = FakeFrame()
        before = _protected_form_snapshot(frame)
        after = _protected_form_snapshot(frame)

        self.assertEqual(before["values"], expected)
        self.assertEqual(bytes(before["utf8"]), bytes(after["utf8"]))
        self.assertIn("#txtValorProventos", frame.script)
        self.assertIn("#txtValorContribuicao", frame.script)
        self.assertIn("#txtConclusaoAnalise", frame.script)
        self.assertIn("#btnComplementar", frame.script)
        self.assertIn("#btnLimpar", frame.script)
        _assert_protected_form_unchanged(before, after)

    def test_manifest_has_minimal_permissions_and_restricted_injection(self) -> None:
        _assert_manifest_contract(self)

    def test_manifest_content_script_is_classic_compatible(self) -> None:
        manifest = _assert_manifest_contract(self)
        script_path = EXTENSION / manifest["content_scripts"][0]["js"][0]
        source = script_path.read_text(encoding="utf-8")
        self.assertNotRegex(source, re.compile(r"^\s*export\s", re.MULTILINE))
        self.assertIn("module.exports", source)
        package_path = script_path.parent / "package.json"
        self.assertTrue(package_path.is_file(), package_path)
        self.assertEqual(
            json.loads(package_path.read_text(encoding="utf-8"))["type"],
            "commonjs",
        )

    def test_chrome_fixture_smoke_uses_disposable_profile(self) -> None:
        self.assertTrue(DATASET.is_file(), DATASET)
        result = run_smoke()
        self.assertEqual(result["preview_rows"], 7)
        self.assertTrue(result["negative_controls_unchanged"])
        self.assertTrue(result["persisted_after_profile_restart"])
        self.assertTrue(result["incomplete_dom_blocked"])
        # The foundation stays fail-closed without a legal context from the
        # local bridge; the modalidade tie is validated in the panel suite.
        self.assertEqual(result["recalculated_tie"], "pending")


if __name__ == "__main__":
    unittest.main(verbosity=2)
