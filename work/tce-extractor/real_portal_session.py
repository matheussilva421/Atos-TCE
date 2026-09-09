"""Open a disposable real-portal qualification session.

This runner pairs the unpacked extension with the local service, opens the
real portal in an isolated Chrome profile, and emits only a sanitized DOM
inventory. It never submits an act by itself. The process stays alive when
``--stay-open`` is used so an operator can inspect the browser before the
next supervised phase.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import time

from playwright.sync_api import sync_playwright


def _sanitize_page(page):
    return page.evaluate(
        """
        () => {
          const safeText = (value) => String(value || '').replace(/\\s+/gu, ' ').trim();
          const safeOrigin = (value) => {
            try { return new URL(value).origin; } catch (_) { return ''; }
          };
          const body = safeText(document.body?.innerText || '');
          const controls = [...document.querySelectorAll('input, select, textarea, button')];
          const names = controls.map((element) => ({
            tag: element.tagName.toLowerCase(),
            type: element.getAttribute('type') || '',
            id_present: Boolean(element.id),
            name_present: Boolean(element.getAttribute('name')),
          }));
          const labels = [...document.querySelectorAll('button, a, [role="button"]')]
            .map((element) => safeText(element.textContent))
            .filter((text) => /^(entrar|login|sair|próximo|avançar|voltar|complementar ato|salvar|cancelar)$/iu.test(text))
            .slice(0, 30);
          return {
            url: location.href.split('#')[0],
            origin: location.origin,
            title_present: Boolean(document.title),
            body_length: body.length,
            login_signal: /(login|senha|entrar|autentica|sessão expir)/iu.test(body),
            form_count: document.forms.length,
            control_count: controls.length,
            controls: names,
            safe_action_labels: labels,
            frame_origins: [...document.querySelectorAll('iframe')]
              .map((frame) => safeOrigin(frame.src))
              .filter(Boolean),
          };
        }
        """
    )


def _extension_id(context) -> str:
    if context.service_workers:
        return context.service_workers[0].url.split('/')[2]
    manager = context.new_page()
    manager.goto('chrome://extensions/', wait_until='domcontentloaded')
    manager.close()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if context.service_workers:
            return context.service_workers[0].url.split('/')[2]
        time.sleep(0.1)
    raise RuntimeError('service worker da extensão não iniciou')


def _read_pairing_code(package: Path) -> tuple[str, int]:
    metadata = package / 'dados-locais' / 'bridge' / 'service.json'
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if metadata.is_file():
            payload = json.loads(metadata.read_text(encoding='utf-8'))
            code = payload.get('pairing_code')
            port = payload.get('port')
            if isinstance(code, str) and code and isinstance(port, int):
                return code, port
        time.sleep(0.1)
    raise RuntimeError('service.json sem código de pareamento válido')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--package-root', type=Path, required=True)
    parser.add_argument('--portal-url', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--profile', type=Path)
    parser.add_argument('--executable', type=Path)
    parser.add_argument('--poll-seconds', type=float, default=5.0)
    parser.add_argument('--stay-open', action='store_true')
    args = parser.parse_args()

    package = args.package_root.resolve()
    extension = package / 'extensao-complementar-ato'
    code, port = _read_pairing_code(package)
    profile = args.profile.resolve() if args.profile else Path(tempfile.mkdtemp(prefix='tce-real-chrome-'))
    profile.mkdir(parents=True, exist_ok=True)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        executable = args.executable.resolve() if args.executable else Path(playwright.chromium.executable_path)
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            executable_path=str(executable),
            headless=False,
            args=[
                f'--disable-extensions-except={extension}',
                f'--load-extension={extension}',
                '--ignore-certificate-errors',
                '--disable-gpu',
                '--no-first-run',
                '--no-default-browser-check',
                '--new-window',
            ],
        )
        panel = context.new_page()
        extension_id = _extension_id(context)
        panel.goto(
            f'chrome-extension://{extension_id}/sidepanel/panel.html',
            wait_until='domcontentloaded',
        )
        panel.locator('#bridge-status').wait_for(state='visible', timeout=10_000)
        panel.locator('#bridge-base-url').fill(f'http://127.0.0.1:{port}')
        panel.locator('#bridge-pairing-code').fill(code)
        panel.wait_for_function(
            "() => document.querySelector('#bridge-connect-button')?.disabled === false",
            timeout=10_000,
        )
        panel.locator('#bridge-connect-button').click()
        try:
            panel.wait_for_function(
                "() => document.querySelector('#bridge-status')?.textContent.includes('Mesa local conectada.')",
                timeout=10_000,
            )
        except Exception:
            print(json.dumps({
                'pair_wait_failed': True,
                'bridge_status': panel.locator('#bridge-status').inner_text(),
                'panel_message_present': bool(panel.locator('#panel-message').inner_text()),
            }, ensure_ascii=False))
            raise

        portal = context.new_page()
        navigation_error = ''
        try:
            portal.goto(args.portal_url, wait_until='domcontentloaded', timeout=45_000)
        except Exception as error:  # navigation can remain usable after a timeout
            navigation_error = type(error).__name__
        portal.wait_for_timeout(5_000)
        def capture() -> dict:
            panel_snapshot = _sanitize_page(panel)
            portal_snapshot = _sanitize_page(portal)
            return {
                'schema_version': 1,
                'captured_at': datetime.now(timezone.utc).isoformat(),
                'browser': executable.name,
                'profile_disposable': True,
                'extension_id_present': bool(extension_id),
                'pair_status': panel.locator('#bridge-status').inner_text(),
                'portal_navigation_error_type': navigation_error,
                'panel': panel_snapshot,
                'portal': portal_snapshot,
                'portal_extension_origin_match': portal_snapshot['origin'] == 'https://novaarearestrita.tce.rn.gov.br',
                'submission_performed_by_runner': False,
            }

        evidence = capture()
        output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({
            'output': str(output),
            'browser': executable.name,
            'profile': str(profile),
            'pair_status': evidence['pair_status'],
            'portal_origin': evidence['portal']['origin'],
            'portal_extension_origin_match': evidence['portal_extension_origin_match'],
            'login_signal': evidence['portal']['login_signal'],
            'submission_performed_by_runner': False,
        }, ensure_ascii=False))
        if args.stay_open:
            print('REAL_PORTAL_SESSION_READY')
            sys.stdout.flush()
            reloaded_empty_portal = False
            while True:
                time.sleep(max(1.0, args.poll_seconds))
                if not reloaded_empty_portal:
                    current = _sanitize_page(portal)
                    if current['body_length'] < 20:
                        try:
                            portal.reload(wait_until='domcontentloaded', timeout=30_000)
                            portal.wait_for_timeout(5_000)
                        except Exception:
                            pass
                        reloaded_empty_portal = True
                evidence = capture()
                output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        context.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
