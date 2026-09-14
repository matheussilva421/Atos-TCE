"""Record a supervised, isolated Chrome QA session without driving portal actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from qa_workflow import build_run_document, sanitize_event, write_run_document


DEFAULT_PORTAL_URL = "https://novaarearestrita.tce.rn.gov.br/"
_PRIVATE_DIRECTORY = "dados-locais"


@dataclass(frozen=True)
class RecorderConfig:
    package_root: Path
    extension_root: Path
    profile_root: Path
    output_root: Path
    private_root: Path | None = None
    portal_url: str = DEFAULT_PORTAL_URL
    safety_mode: str = "observe_only"
    browser: str = "chrome"
    executable: Path | None = None


def _portable_path(path: Path) -> str:
    return path.as_posix()


def validate_qa_profile(package_root: Path, profile_root: Path) -> Path:
    """Require a persistent profile below the package's private data root."""

    package = package_root.resolve()
    private_root = (package / _PRIVATE_DIRECTORY).resolve()
    profile = profile_root.resolve()
    try:
        profile.relative_to(private_root)
    except ValueError as error:
        raise ValueError("Chrome QA profile must be inside package/dados-locais") from error
    if profile == private_root or profile.name.casefold() != "chrome-qa-profile":
        raise ValueError("Chrome QA profile must use the exact chrome-qa-profile directory")
    return profile


def build_launch_args(config: RecorderConfig) -> list[str]:
    """Build a narrow extension-only launch configuration."""

    extension = _portable_path(config.extension_root.resolve())
    return [
        f"--disable-extensions-except={extension}",
        f"--load-extension={extension}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        "--disable-gpu",
        "--in-process-gpu",
    ]


def build_structural_capture_script() -> str:
    """Install listeners that report control structure, never field values."""

    return r"""
(() => {
  if (window.__tceQaCaptureInstalled) return;
  window.__tceQaCaptureInstalled = true;
  const targetShape = (target) => ({
    tag: String(target?.tagName || '').toLowerCase(),
    id: String(target && target.id || ''),
    name: String(target && target.name || target?.getAttribute?.('name') || ''),
    type: String(target?.getAttribute?.('type') || ''),
    role: String(target?.getAttribute?.('role') || ''),
    aria_label: String(target?.getAttribute?.('aria-label') || ''),
  });
  const emit = (kind, event) => {
    try {
      window.tceQaEvent?.({
        kind,
        target: targetShape(event?.target),
        route: `${location.origin}${location.pathname}`,
        frame_depth: window.top === window ? 0 : 1,
      });
    } catch (_) {
      // Recording must never affect the page under test.
    }
  };
  addEventListener('click', (event) => emit('click', event), true);
  addEventListener('change', (event) => emit('change', event), true);
  addEventListener('submit', (event) => emit('submit_attempt', event), true);
  addEventListener('beforeunload', (event) => emit('beforeunload', event), true);
})();
"""


def _safe_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        if not parsed.scheme or not parsed.netloc:
            return "[redacted-url]"
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    except ValueError:
        return "[redacted-url]"


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def classify_request_failure(
    failure_type: str,
    *,
    is_navigation: bool,
    resource_type: str,
) -> str:
    """Classify browser diagnostics without treating expected transitions as defects."""

    normalized = str(failure_type).upper()
    if "ERR_INVALID_AUTH_CREDENTIALS" in normalized:
        return "auth_challenge"
    if "ERR_ABORTED" in normalized and (
        is_navigation or resource_type in {"document", "image", "media"}
    ):
        return "navigation_abort"
    return "request_failed"


def classify_page_error(url: str) -> str:
    """Separate Chrome's internal error page from a page-script exception."""

    normalized = str(url).lower()
    if normalized.startswith("chrome-error://") or normalized.startswith("chromewebdata"):
        return "browser_error_page"
    return "page_error"


def _sha256_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(
        (item for item in root.rglob("*") if item.is_file()),
        key=lambda value: str(value).casefold(),
    ):
        if not path.is_file():
            continue
        if "dados-locais" in path.parts:
            continue
        digest.update(str(path.relative_to(root)).replace(os.sep, "/").encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _git_revision(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def find_chrome(executable: Path | None = None) -> Path:
    if executable is not None:
        candidate = executable.resolve()
        if not candidate.is_file():
            raise FileNotFoundError(f"Chrome executable not found: {candidate}")
        return candidate
    candidates = [
        Path(os.environ.get("ProgramFiles", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    found = shutil.which("chrome.exe") or shutil.which("chrome")
    if found:
        return Path(found).resolve()
    raise FileNotFoundError("Google Chrome was not found")


def extension_worker_matches(
    worker_url: str,
    manifest: dict[str, Any],
    expected_manifest: dict[str, Any],
) -> bool:
    """Return true only for the requested extension, never a Chrome component."""

    if not worker_url.startswith("chrome-extension://"):
        return False
    if manifest.get("name") != expected_manifest.get("name"):
        return False
    if manifest.get("version") != expected_manifest.get("version"):
        return False
    expected_background = expected_manifest.get("background", {})
    actual_background = manifest.get("background", {})
    expected_worker = expected_background.get("service_worker")
    actual_worker = actual_background.get("service_worker")
    if not isinstance(expected_worker, str) or actual_worker != expected_worker:
        return False
    return worker_url.rstrip("/").endswith("/" + expected_worker)


@dataclass
class QaPortalRecorder:
    config: RecorderConfig
    events: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    _playwright: Any = field(default=None, init=False, repr=False)
    _context: Any = field(default=None, init=False, repr=False)
    _run_root: Path | None = field(default=None, init=False)
    _run_id: str | None = field(default=None, init=False)

    def _record(self, event: dict[str, Any]) -> None:
        safe = sanitize_event(event)
        safe["sequence"] = len(self.events) + 1
        safe["captured_at"] = datetime.now(timezone.utc).isoformat()
        self.events.append(safe)

    def _record_structural_event(self, _source: Any, event: Any) -> None:
        if isinstance(event, dict):
            self._record({"kind": "page_event", **event})

    def _page_url(self, page: Any) -> str:
        return _safe_url(str(getattr(page, "url", "")))

    def _attach_page(self, page: Any) -> None:
        page.on(
            "console",
            lambda message: self._record(
                {
                    "kind": "console",
                    "level": str(message.type),
                    "url": self._page_url(page),
                    "message_sha256": _hash_text(str(message.text)),
                }
            ),
        )
        page.on(
            "pageerror",
            lambda error: self._record_or_error(
                classify_page_error(str(getattr(page, "url", ""))),
                {
                    "kind": "pageerror",
                    "url": self._page_url(page),
                    "message_sha256": _hash_text(str(error)),
                },
            ),
        )
        page.on(
            "requestfailed",
            lambda request: self._record_or_error(
                classify_request_failure(
                    str(request.failure or "unknown"),
                    is_navigation=bool(request.is_navigation_request()),
                    resource_type=str(request.resource_type),
                ),
                {
                    "kind": "requestfailed",
                    "url": _safe_url(str(request.url)),
                    "method": str(request.method),
                    "failure_type": str(request.failure or "unknown"),
                    "is_navigation": bool(request.is_navigation_request()),
                    "resource_type": str(request.resource_type),
                },
            ),
        )
        page.on(
            "framenavigated",
            lambda frame: self._record(
                {
                    "kind": "frame_navigated",
                    "url": _safe_url(str(frame.url)),
                    "is_main_frame": bool(frame == page.main_frame),
                }
            ),
        )

    def _record_or_error(self, classification: str, event: dict[str, Any]) -> None:
        if classification in {"auth_challenge", "navigation_abort", "browser_error_page"}:
            self._record({"kind": classification, **event})
            return
        self.errors.append(event)

    def start(self) -> dict[str, str]:
        """Start Chrome and expose only observation controls."""

        if self.config.safety_mode not in {"observe_only", "reversible_fill"}:
            raise ValueError("unsupported recorder safety mode")
        if self.config.browser not in {"chrome", "chromium"}:
            raise ValueError("unsupported recorder browser")
        if self.config.browser == "chromium" and self.config.executable is not None:
            raise ValueError("chromium mode uses Playwright's managed browser; omit executable")
        private_root = (self.config.private_root or self.config.package_root).resolve()
        validate_qa_profile(private_root, self.config.profile_root)
        if not self.config.extension_root.is_dir():
            raise FileNotFoundError(f"extension directory not found: {self.config.extension_root}")
        self.config.output_root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        self._run_id = f"qa-{timestamp}"
        self._run_root = self.config.output_root / self._run_id
        self._run_root.mkdir(parents=True, exist_ok=False)
        (self._run_root / "screenshots").mkdir()

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as error:
            raise RuntimeError("Playwright is required for Chrome QA recording") from error

        chrome = None
        try:
            self._playwright = sync_playwright().start()
            launch_options: dict[str, Any] = {
                "user_data_dir": str(self.config.profile_root),
                "headless": False,
                "args": build_launch_args(self.config),
                # Playwright adds --disable-extensions by default. Removing only
                # that default is required for the explicit allow-list above to
                # work with the installed Chrome channel.
                "ignore_default_args": [
                    "--disable-extensions",
                    "--disable-component-extensions-with-background-pages",
                ],
                "record_har_path": str(self._run_root / "network.har"),
                "record_har_content": "attach",
            }
            if self.config.browser == "chromium":
                launch_options["channel"] = "chromium"
                browser_label = "Chromium QA"
                browser_executable = "playwright-managed"
            else:
                chrome = find_chrome(self.config.executable)
                launch_options["executable_path"] = str(chrome)
                browser_label = "Google Chrome"
                browser_executable = chrome.name
            self._context = self._playwright.chromium.launch_persistent_context(**launch_options)
            self._context.expose_binding("tceQaEvent", self._record_structural_event)
            self._context.add_init_script(build_structural_capture_script())
            self._context.tracing.start(screenshots=True, snapshots=True, sources=True)
            self._context.on("page", self._attach_page)
            for page in self._context.pages:
                self._attach_page(page)

            panel = self._context.new_page()
            extension_id = self._extension_id()
            panel.goto(
                f"chrome-extension://{extension_id}/sidepanel/panel.html",
                wait_until="domcontentloaded",
            )
            portal = self._context.new_page()
            try:
                portal.goto(self.config.portal_url, wait_until="domcontentloaded", timeout=45_000)
            except Exception as error:
                classification = classify_request_failure(
                    str(error),
                    is_navigation=True,
                    resource_type="document",
                )
                self._record(
                    {
                        "kind": (
                            classification
                            if classification != "request_failed"
                            else "portal_navigation_failed"
                        ),
                        "url": _safe_url(self.config.portal_url),
                        "error_type": type(error).__name__,
                        "message_sha256": _hash_text(str(error)),
                    }
                )
                if classification == "request_failed":
                    self.errors.append(
                        {
                            "kind": "portal_navigation_failed",
                            "url": _safe_url(self.config.portal_url),
                            "error_type": type(error).__name__,
                            "message_sha256": _hash_text(str(error)),
                        }
                    )
            self._record({"kind": "recorder_ready", "extension_id_present": bool(extension_id)})
            return {
                "run_id": self._run_id,
                "run_root": str(self._run_root),
                "browser": browser_label,
                "executable": browser_executable,
            }
        except Exception as error:
            self._record(
                {
                    "kind": "recorder_start_failed",
                    "error_type": type(error).__name__,
                    "message_sha256": _hash_text(str(error)),
                }
            )
            self.errors.append(
                {
                    "kind": "recorder_start_failed",
                    "error_type": type(error).__name__,
                    "message_sha256": _hash_text(str(error)),
                }
            )
            if self._context is not None and self._run_root is not None and self._run_id is not None:
                try:
                    self.stop(status="BLOCKED")
                except Exception:
                    self._close_runtime()
            else:
                self._close_runtime()
            raise

    def _extension_id(self) -> str:
        manifest_path = self.config.extension_root / "manifest.json"
        try:
            expected_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError("requested extension manifest cannot be read") from error
        for worker in self._context.service_workers:
            try:
                manifest = worker.evaluate("() => chrome.runtime.getManifest()")
            except Exception:
                continue
            if extension_worker_matches(str(worker.url), manifest, expected_manifest):
                return str(worker.url).split("/")[2]
        manager = self._context.new_page()
        manager.goto("chrome://extensions/", wait_until="domcontentloaded")
        manager.close()
        deadline = datetime.now(timezone.utc).timestamp() + 10
        while datetime.now(timezone.utc).timestamp() < deadline:
            for worker in self._context.service_workers:
                try:
                    manifest = worker.evaluate("() => chrome.runtime.getManifest()")
                except Exception:
                    continue
                if extension_worker_matches(str(worker.url), manifest, expected_manifest):
                    return str(worker.url).split("/")[2]
            time.sleep(0.1)
        raise RuntimeError("extension service worker did not start")

    def _close_runtime(self) -> None:
        context, playwright = self._context, self._playwright
        self._context = None
        self._playwright = None
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:
                pass

    def screenshot(self, page: Any, label: str) -> Path:
        if self._run_root is None:
            raise RuntimeError("recorder has not started")
        safe_label = "".join(character if character.isalnum() or character in "-_" else "_" for character in label)
        path = self._run_root / "screenshots" / f"{len(self.events):04d}-{safe_label}.png"
        page.screenshot(path=str(path), full_page=False)
        self._record({"kind": "screenshot", "artifact": path.relative_to(self._run_root).as_posix()})
        return path

    def stop(self, *, status: str = "BLOCKED") -> Path:
        if self._context is None or self._run_root is None or self._run_id is None:
            raise RuntimeError("recorder has not started")
        trace_path = self._run_root / "trace.zip"
        try:
            self._context.tracing.stop(path=str(trace_path))
            self._context.close()
        finally:
            self._close_runtime()
        document = build_run_document(
            package_root=self.config.package_root,
            package_sha256=_sha256_tree(self.config.package_root),
            git_revision=_git_revision(self.config.package_root),
            run_id=self._run_id,
            browser={
                "name": "Google Chrome" if self.config.browser == "chrome" else "Chromium QA",
                "executable": "local" if self.config.browser == "chrome" else "playwright-managed",
            },
            safety_mode=self.config.safety_mode,
            status=status,
            steps=self.events,
            errors=self.errors,
            artifacts={"trace": "trace.zip", "network": "network.har", "screenshots": "screenshots/"},
            coverage=[],
        )
        run_path = self._run_root / "run.json"
        write_run_document(run_path, document)
        return run_path


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, help="Private root for profile and raw artifacts; defaults to the repository root")
    parser.add_argument("--extension", type=Path)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--executable", type=Path, help="Chrome/Chromium executable for the isolated QA profile")
    parser.add_argument("--portal-url", default=DEFAULT_PORTAL_URL)
    parser.add_argument("--safety-mode", choices=("observe_only", "reversible_fill"), default="observe_only")
    parser.add_argument("--browser", choices=("chrome", "chromium"), default="chrome")
    parser.add_argument("--stay-open", action="store_true")
    parser.add_argument("--status", choices=("BLOCKED", "PASS_REAL", "NOT_TESTED"), default="BLOCKED")
    args = parser.parse_args(argv)
    package_root = args.package_root.resolve()
    private_root = (args.private_root or package_root.parent.parent).resolve()
    config = RecorderConfig(
        package_root=package_root,
        extension_root=(args.extension or package_root / "extensao-complementar-ato").resolve(),
        profile_root=(args.profile or private_root / "dados-locais" / "chrome-qa-profile").resolve(),
        output_root=(args.output_root or private_root / "dados-locais" / "qa-runs").resolve(),
        private_root=private_root,
        portal_url=args.portal_url,
        safety_mode=args.safety_mode,
        browser=args.browser,
        executable=args.executable,
    )
    recorder = QaPortalRecorder(config)
    ready = recorder.start()
    print(json.dumps({"QA_RECORDER_READY": True, **ready}, ensure_ascii=False), flush=True)
    if args.stay_open:
        print("Execute o fluxo manual no Chrome QA; pressione ENTER no terminal para encerrar.", flush=True)
        sys.stdin.readline()
    run_path = recorder.stop(status=args.status)
    print(json.dumps({"run": str(run_path), "status": args.status}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
