"""Open a disposable real-portal qualification session.

This runner pairs the unpacked extension with the local service, opens the
real portal in an isolated Chrome profile, and emits only a sanitized DOM
inventory plus a private structural action recording. It never submits an act
by itself. The process stays alive when ``--stay-open`` is used so an operator
can inspect the browser before the next supervised phase.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright
from qa_portal_recorder import (
    build_structural_capture_script,
    classify_page_error,
    classify_request_failure,
)
from qa_workflow import sanitize_event

AREA_RESTRITA_URL = 'https://novaarearestrita.tce.rn.gov.br/telaPrincipalMenu.asp'
AREA_RESTRITA_HOST = 'novaarearestrita.tce.rn.gov.br'
PRIVATE_DIRECTORY = 'dados-locais'

# IDs que a automacao le no portal. Fonte: content/form-detector.js
# FIELD_MAP/SENTINEL_IDS e o rotulo exato de envio em content/portal-submit.js.
# Se o portal renomear qualquer um destes controles, a automacao precisa parar.
PORTAL_DEPENDENCY_IDS = (
    'txtModalidade',
    'txtFundamentoLegal',
    'txtDataDOE',
    'txtCargo',
    'txtMatricula',
    'txtDataNascimento',
    'txtGenero',
    'txtNumeroProcesso',
    'txtAnoProcesso',
)
PORTAL_SUBMIT_LABEL = 'Complementar Ato'
PORTAL_BASELINE_SIGNALS = ('origin', 'complement_action_signal', 'select_count', 'form_count')
_PROCESS_KEY_RE = re.compile(r'\b\d{5,8}\s*/\s*20\d{2}\b')
_FIXTURE_KIND = 'real-portal-observation'
_FIXTURE_STATUS = 'sanitized'
_RECORDING_DIRECTORY = 'real-portal-runs'


def validate_recording_root(package_root: Path, recording_root: Path) -> Path:
    """Keep raw browser recordings below the package's private directory."""

    package = Path(package_root).resolve()
    private_root = (package / PRIVATE_DIRECTORY).resolve()
    recording = Path(recording_root).resolve()
    try:
        recording.relative_to(private_root)
    except ValueError as error:
        raise ValueError(
            f'Gravacao bruta deve ficar dentro de {PRIVATE_DIRECTORY}'
        ) from error
    if recording == private_root:
        raise ValueError(
            f'Gravacao bruta deve ficar dentro de {PRIVATE_DIRECTORY}'
        )
    return recording


def build_recording_launch_options(recording_root: Path) -> dict[str, str]:
    """Return Playwright's private HAR configuration for one run."""

    root = Path(recording_root).resolve()
    return {
        'record_har_path': (root / 'network.har').as_posix(),
        'record_har_content': 'attach',
    }


def _safe_url(value: object) -> str:
    """Remove query and fragment data from a recorded browser URL."""

    try:
        parsed = urlparse(str(value))
    except ValueError:
        return '[redacted-url]'
    if not parsed.scheme or not parsed.netloc:
        return '[redacted-url]'
    return parsed._replace(query='', fragment='').geturl()


def _hash_text(value: object) -> str:
    return hashlib.sha256(str(value).encode('utf-8', errors='replace')).hexdigest()


def _record_event(events: list[dict], event: dict) -> None:
    safe = sanitize_event(event)
    safe['sequence'] = len(events) + 1
    safe['captured_at'] = datetime.now(timezone.utc).isoformat()
    events.append(safe)


def build_recording_document(
    *,
    package: Path,
    run_id: str,
    events: list[dict],
    errors: list[dict],
    status: str,
) -> dict:
    """Build the local action record without absolute paths or field values."""

    return {
        'schema': 'real-portal-session-recording-v1',
        'run_id': run_id,
        'package_name': package.name,
        'status': status,
        'safety_mode': 'observe_only',
        'steps': [sanitize_event(event) for event in events],
        'errors': [sanitize_event(error) for error in errors],
        'artifacts': {
            'trace': 'trace.zip',
            'network': 'network.har',
            'recording': 'recording.json',
        },
    }


def _record_or_error(
    events: list[dict], errors: list[dict], classification: str, event: dict
) -> None:
    if classification in {'auth_challenge', 'navigation_abort', 'browser_error_page'}:
        _record_event(events, {'kind': classification, **event})
        return
    errors.append(sanitize_event(event))


def _attach_recording_page(page, events: list[dict], errors: list[dict]) -> None:
    """Record structural browser activity while excluding field contents."""

    page.on(
        'console',
        lambda message: _record_event(
            events,
            {
                'kind': 'console',
                'level': str(message.type),
                'url': _safe_url(getattr(page, 'url', '')),
                'message_sha256': _hash_text(getattr(message, 'text', '')),
            },
        ),
    )
    page.on(
        'pageerror',
        lambda error: _record_or_error(
            events,
            errors,
            classify_page_error(str(getattr(page, 'url', ''))),
            {
                'kind': 'pageerror',
                'url': _safe_url(getattr(page, 'url', '')),
                'message_sha256': _hash_text(error),
            },
        ),
    )

    def record_request_failure(request) -> None:
        failure = str(request.failure or 'unknown')
        _record_or_error(
            events,
            errors,
            classify_request_failure(
                failure,
                is_navigation=bool(request.is_navigation_request()),
                resource_type=str(request.resource_type),
            ),
            {
                'kind': 'requestfailed',
                'url': _safe_url(request.url),
                'method': str(request.method),
                'failure_type': failure,
                'is_navigation': bool(request.is_navigation_request()),
                'resource_type': str(request.resource_type),
            },
        )

    page.on('requestfailed', record_request_failure)
    page.on(
        'framenavigated',
        lambda frame: _record_event(
            events,
            {
                'kind': 'frame_navigated',
                'url': _safe_url(frame.url),
                'is_main_frame': bool(frame == page.main_frame),
            },
        ),
    )


def _write_recording_document(
    run_root: Path,
    package: Path,
    run_id: str,
    events: list[dict],
    errors: list[dict],
    *,
    status: str,
) -> Path:
    path = run_root / 'recording.json'
    document = build_recording_document(
        package=package,
        run_id=run_id,
        events=events,
        errors=errors,
        status=status,
    )
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    return path


def _assert_no_process_identity(value, path: str = 'observacao') -> None:
    """Recusa qualquer texto que carregue identidade de processo ou pessoa."""

    if isinstance(value, str):
        if _PROCESS_KEY_RE.search(value):
            raise ValueError(
                f'{path} contem identidade de processo; fixture precisa ser sanitizada'
            )
        return
    if isinstance(value, dict):
        for key, child in value.items():
            _assert_no_process_identity(child, f'{path}.{key}')
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _assert_no_process_identity(child, f'{path}[{index}]')


def build_sanitized_fixture(observation: dict) -> tuple[dict, str]:
    """Convert a real-portal observation into a hashed, sanitized fixture.

    A qualificacao registra ``fixture_hashes``, entao a fixture precisa existir
    e ter hash SHA-256 estavel. O conteudo e estrutural: ids de controle, origem
    e sinais booleanos. Identidade de processo/pessoa e qualquer indicio de envio
    sao recusados em vez de virar fixture, e um portal que divergiu do contrato
    nao pode ser promovido a fixture de qualificacao."""

    if not isinstance(observation, dict):
        raise ValueError('observacao invalida para fixture')
    if observation.get('submission_performed_by_runner') is not False:
        raise ValueError(
            'submission_performed_by_runner precisa ser False: a fixture de '
            'qualificacao nao pode conter envio'
        )
    portal = observation.get('portal')
    if not isinstance(portal, dict):
        raise ValueError('observacao sem bloco de portal')
    expected_ids = list(PORTAL_DEPENDENCY_IDS)
    if observation.get('profile_disposable') is not True:
        raise ValueError('perfil da observacao precisa ser isolado e descartavel')
    if observation.get('extension_id_present') is not True:
        raise ValueError('observacao sem extensao carregada')
    if observation.get('portal_extension_origin_match') is not True:
        raise ValueError('observacao sem correspondencia segura da origem do portal')
    if observation.get('portal_navigation_error_type') not in (None, ''):
        raise ValueError('observacao contem erro de navegacao do portal')
    _assert_no_process_identity(portal.get('known_ids'), 'portal.known_ids')
    _assert_no_process_identity(portal.get('origin'), 'portal.origin')
    _assert_no_process_identity(observation.get('captured_at'), 'observacao.captured_at')
    _assert_no_process_identity(observation.get('browser'), 'observacao.browser')
    if portal.get('origin') != f'https://{AREA_RESTRITA_HOST}':
        raise ValueError('observacao contem origem de portal inesperada')
    if portal.get('authenticated_ui_signal') is not True:
        raise ValueError('observacao sem sinal de interface autenticada')
    if portal.get('known_ids') != expected_ids:
        raise ValueError('observacao nao expos todos os controles do contrato')
    if observation.get('portal_contract_ids') != expected_ids:
        raise ValueError('observacao nao corresponde ao contrato de controles')
    drift = observation.get('portal_drift')
    missing = observation.get('portal_missing_contract_ids')
    if missing != []:
        raise ValueError(
            'portal divergiu do contrato; fixture recusada ate nova qualificacao'
        )
    if not isinstance(drift, dict) or drift.get('drift') is not False:
        raise ValueError(
            'portal divergiu do contrato; fixture recusada ate nova qualificacao'
        )
    fixture = {
        'schema_version': 1,
        'fixture_kind': _FIXTURE_KIND,
        'fixture_status': _FIXTURE_STATUS,
        'captured_at': observation.get('captured_at'),
        'browser': observation.get('browser'),
        'profile_disposable': observation.get('profile_disposable') is True,
        'extension_id_present': observation.get('extension_id_present') is True,
        'portal_origin': portal.get('origin'),
        'portal_authenticated_ui_signal': portal.get('authenticated_ui_signal') is True,
        'portal_extension_origin_match': (
            observation.get('portal_extension_origin_match') is True
        ),
        'portal_contract_ids': expected_ids,
        'portal_missing_contract_ids': [],
        'portal_drift': {'drift': False},
    }
    payload = _serialize_fixture(fixture)
    return fixture, hashlib.sha256(payload).hexdigest()


def _serialize_fixture(fixture: dict) -> bytes:
    """Return the canonical bytes used both for writing and hashing."""

    return json.dumps(
        fixture, ensure_ascii=False, sort_keys=True, separators=(',', ':')
    ).encode('utf-8')


def write_sanitized_fixture(input_path: Path, output_path: Path) -> tuple[Path, str]:
    """Read one private observation and write its safe derived fixture.

    The source observation is never replaced. The returned digest covers the
    exact bytes written to ``output_path`` so it can be copied to the later
    qualification record without a second serialization step.
    """

    source = Path(input_path).resolve()
    output = Path(output_path).resolve()
    if source == output:
        raise ValueError('o fixture precisa ser gravado em arquivo separado')
    try:
        observation = json.loads(source.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f'observacao JSON invalida: {source}') from error
    fixture, digest = build_sanitized_fixture(observation)
    payload = _serialize_fixture(fixture)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    return output, digest


def portal_dependency_ids() -> list[str]:
    """Return every portal control id the automation depends on."""

    return list(PORTAL_DEPENDENCY_IDS)


def is_portal_contract_ready(snapshot: dict | None) -> bool:
    """Return whether a snapshot is safe to establish the portal baseline."""

    return (
        isinstance(snapshot, dict)
        and snapshot.get('origin') == f'https://{AREA_RESTRITA_HOST}'
        and snapshot.get('authenticated_ui_signal') is True
        and snapshot.get('known_ids') == portal_dependency_ids()
    )


def compare_portal_snapshot(baseline: dict | None, observed: dict | None) -> dict:
    """Compare an observed structural snapshot against the known contract.

    Retorna um relatorio de deriva; qualquer divergencia estrutural significa
    que o portal mudou e que a automacao deve parar ate nova qualificacao.
    """

    if not isinstance(baseline, dict) or not isinstance(observed, dict):
        return {
            'drift': True,
            'reason': 'observation_missing',
            'missing_ids': [],
            'unexpected_ids': [],
            'changed_signals': [],
        }
    expected_ids = baseline.get('known_ids')
    if not isinstance(expected_ids, list):
        expected_ids = portal_dependency_ids()
    observed_ids = observed.get('known_ids')
    observed_ids = observed_ids if isinstance(observed_ids, list) else []
    missing_ids = [item for item in expected_ids if isinstance(item, str) and item not in observed_ids]
    unexpected_ids = [
        item for item in observed_ids
        if isinstance(item, str) and item not in expected_ids
    ]
    changed_signals = []
    for signal in PORTAL_BASELINE_SIGNALS:
        if signal in baseline and baseline.get(signal) != observed.get(signal):
            changed_signals.append(signal)
    drift = bool(missing_ids or changed_signals)
    return {
        'drift': drift,
        'reason': 'structural_drift' if drift else 'unchanged',
        'missing_ids': missing_ids,
        'unexpected_ids': unexpected_ids,
        'changed_signals': changed_signals,
    }


def _portable_path(path: Path) -> str:
    return Path(path).resolve().as_posix()


def build_launch_args(extension_root: Path) -> list[str]:
    """Build the narrow extension-only launch configuration for this runner.

    The qualification session must exercise the same TLS chain the operator
    uses, so no certificate bypass is allowed here.
    """

    extension = _portable_path(extension_root)
    return [
        f'--disable-extensions-except={extension}',
        f'--load-extension={extension}',
        '--disable-gpu',
        '--no-first-run',
        '--no-default-browser-check',
        '--new-window',
    ]


def validate_session_profile(package_root: Path, profile_root: Path | None) -> Path | None:
    """Require a persistent profile below the package's private data root.

    ``None`` keeps the caller's disposable temporary profile; an explicit
    profile must stay inside the private data directory so personal browser
    state is never reused for qualification.
    """

    if profile_root is None:
        return None
    package = Path(package_root).resolve()
    private_root = (package / PRIVATE_DIRECTORY).resolve()
    profile = Path(profile_root).resolve()
    try:
        profile.relative_to(private_root)
    except ValueError as error:
        raise ValueError(
            f'Perfil de qualificacao deve ficar dentro de {PRIVATE_DIRECTORY}'
        ) from error
    if profile == private_root:
        raise ValueError(
            f'Perfil de qualificacao deve ficar dentro de {PRIVATE_DIRECTORY}'
        )
    return profile


def _normalize_portal_url(value: str | None) -> str:
    """Return a safe Area Restrita entrypoint for this qualification runner."""
    candidate = AREA_RESTRITA_URL if value is None or not str(value).strip() else str(value).strip()
    parsed = urlparse(candidate)
    if parsed.scheme.lower() != 'https' or parsed.hostname != AREA_RESTRITA_HOST:
        raise ValueError(
            'A qualificação de Complementar Ato exige a Área Restrita '
            f'({AREA_RESTRITA_HOST}); a origem pública não é aceita.'
        )
    return candidate


def _sanitize_page(page):
    return page.evaluate(
        """
        (dependencyIds) => {
          const safeText = (value) => String(value || '').replace(/\\s+/gu, ' ').trim();
          const safeOrigin = (value) => {
            try { return new URL(value).origin; } catch (_) { return ''; }
          };
          const body = safeText(document.body?.innerText || '');
          const controls = [...document.querySelectorAll('input, select, textarea, button')];
          const visible = (element) => {
            if (!element) return false;
            const style = getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style.display !== 'none'
              && style.visibility !== 'hidden'
              && rect.width > 0
              && rect.height > 0;
          };
          const exactTextPresent = (pattern) => [...document.querySelectorAll(
            'button, a, [role="button"], h1, h2, h3, label, span'
          )].some((element) => visible(element) && pattern.test(safeText(element.textContent)));
          let localStorageAuthSignal = false;
          try {
            const currentUser = JSON.parse(localStorage.getItem('currentUser') || 'null');
            localStorageAuthSignal = Boolean(currentUser && typeof currentUser.token === 'string' && currentUser.token);
          } catch (_) {
            localStorageAuthSignal = false;
          }
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
          const knownIdAllowlist = [
            ...dependencyIds,
          ];
          const knownIds = knownIdAllowlist.filter((id) => Boolean(document.getElementById(id)));
          const routeText = `${location.pathname} ${location.hash}`;
          const routeSignals = {
            dashboard: /dashboard/iu.test(routeText),
            meus_processos: /meus[-_ ]processos/iu.test(routeText) || routeText.includes('meus/meus'),
            complementar_ato: /complementar[-_/ ]ato|complementarato/iu.test(routeText),
          };
          const processKeys = body.match(new RegExp('[0-9]{5,8}[ ]*/[ ]*20[0-9]{2}', 'gu')) || [];
          const processKeyCount = new Set(processKeys).size;
          const authenticatedUiSignal = localStorageAuthSignal
            || exactTextPresent(/^(sair|logout)$/iu)
            || routeSignals.dashboard
            || routeSignals.meus_processos;
          const processListSignal = exactTextPresent(/^meus processos$/iu)
            || routeSignals.meus_processos;
          const complementActionSignal = exactTextPresent(/^complementar ato$/iu);
          return {
            url: location.href.split('#')[0],
            origin: location.origin,
            html_lang: document.documentElement.getAttribute('lang') || '',
            title_present: Boolean(document.title),
            body_length: body.length,
            login_signal: /(login|senha|entrar|autentica|sessão expir)/iu.test(body),
            authenticated_ui_signal: authenticatedUiSignal,
            process_list_signal: processListSignal,
            complement_action_signal: complementActionSignal,
            local_storage_auth_signal: localStorageAuthSignal,
            route_signals: routeSignals,
            process_key_count: processKeyCount,
            known_ids: knownIds,
            link_count: document.querySelectorAll('a').length,
            select_count: document.querySelectorAll('select').length,
            visible_button_count: [...document.querySelectorAll('button, [role="button"]')].filter(visible).length,
            form_count: document.forms.length,
            control_count: controls.length,
            controls: names,
            safe_action_labels: labels,
            frame_origins: [...document.querySelectorAll('iframe')]
              .map((frame) => safeOrigin(frame.src))
              .filter(Boolean),
          };
        }
        """,
        portal_dependency_ids(),
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
    parser.add_argument('--package-root', type=Path)
    parser.add_argument('--portal-url', default=AREA_RESTRITA_URL)
    parser.add_argument('--output', type=Path)
    parser.add_argument(
        '--fixture-input',
        type=Path,
        help='observacao JSON privada a converter em fixture sanitizada',
    )
    parser.add_argument(
        '--fixture-output',
        type=Path,
        help='arquivo derivado que recebera a fixture sanitizada',
    )
    parser.add_argument('--profile', type=Path)
    parser.add_argument(
        '--record-root',
        type=Path,
        help='pasta privada para trace, HAR e recording.json; por padrao fica em dados-locais',
    )
    parser.add_argument('--executable', type=Path)
    parser.add_argument('--poll-seconds', type=float, default=5.0)
    parser.add_argument('--stay-open', action='store_true')
    args = parser.parse_args()

    if args.fixture_input is not None or args.fixture_output is not None:
        if args.fixture_input is None or args.fixture_output is None:
            parser.error('--fixture-input e --fixture-output devem ser usados juntos')
        try:
            fixture_path, fixture_hash = write_sanitized_fixture(
                args.fixture_input, args.fixture_output
            )
        except (OSError, ValueError) as error:
            parser.error(str(error))
        print(
            json.dumps(
                {'output': str(fixture_path), 'sha256': fixture_hash},
                ensure_ascii=False,
            )
        )
        return 0

    if args.package_root is None or args.output is None:
        parser.error('--package-root e --output sao obrigatorios para abrir a sessao')
    portal_url = _normalize_portal_url(args.portal_url)

    package = args.package_root.resolve()
    extension = package / 'extensao-complementar-ato'
    code, port = _read_pairing_code(package)
    validated_profile = validate_session_profile(package, args.profile)
    profile = validated_profile or Path(tempfile.mkdtemp(prefix='tce-real-chrome-'))
    profile.mkdir(parents=True, exist_ok=True)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    requested_recording_root = (
        args.record_root
        or package / PRIVATE_DIRECTORY / _RECORDING_DIRECTORY
    )
    recording_parent = validate_recording_root(package, requested_recording_root)
    recording_id = f"real-portal-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
    recording_root = recording_parent / recording_id
    recording_root.mkdir(parents=True, exist_ok=False)
    events: list[dict] = []
    errors: list[dict] = []

    def persist_recording() -> None:
        _write_recording_document(
            recording_root,
            package,
            recording_id,
            events,
            errors,
            status='BLOCKED',
        )

    with sync_playwright() as playwright:
        executable = args.executable.resolve() if args.executable else Path(playwright.chromium.executable_path)
        context = None
        try:
            launch_options = {
                'user_data_dir': str(profile),
                'executable_path': str(executable),
                'headless': False,
                'args': build_launch_args(extension),
                **build_recording_launch_options(recording_root),
            }
            context = playwright.chromium.launch_persistent_context(**launch_options)
            context.expose_binding(
                'tceQaEvent',
                lambda _source, event: _record_event(events, {'kind': 'page_event', **event})
                if isinstance(event, dict)
                else None,
            )
            context.add_init_script(build_structural_capture_script())
            context.tracing.start(screenshots=True, snapshots=True, sources=True)
            context.on('page', lambda page: _attach_recording_page(page, events, errors))
            for existing_page in context.pages:
                _attach_recording_page(existing_page, events, errors)
            _record_event(events, {'kind': 'recorder_ready', 'extension_id_present': False})

            panel = context.new_page()
            extension_id = _extension_id(context)
            _record_event(events, {'kind': 'extension_loaded', 'extension_id_present': bool(extension_id)})
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
                portal.goto(portal_url, wait_until='domcontentloaded', timeout=45_000)
            except Exception as error:  # navigation can remain usable after a timeout
                navigation_error = type(error).__name__
                _record_or_error(
                    events,
                    errors,
                    classify_request_failure(
                        str(error), is_navigation=True, resource_type='document'
                    ),
                    {
                        'kind': 'portal_navigation_failed',
                        'url': _safe_url(portal_url),
                        'error_type': navigation_error,
                        'message_sha256': _hash_text(error),
                    },
                )
            portal.wait_for_timeout(5_000)
            # Contrato observado nesta execucao: os IDs que a automacao le na
            # primeira captura. A comparacao posterior acusa mudanca do portal.
            observed_baseline = None

            def capture() -> dict:
                nonlocal observed_baseline
                panel_snapshot = _sanitize_page(panel)
                portal_snapshot = _sanitize_page(portal)
                if observed_baseline is None and is_portal_contract_ready(portal_snapshot):
                    observed_baseline = {
                        'origin': portal_snapshot['origin'],
                        'known_ids': portal_snapshot['known_ids'],
                        'complement_action_signal': portal_snapshot['complement_action_signal'],
                        'select_count': portal_snapshot['select_count'],
                        'form_count': portal_snapshot['form_count'],
                    }
                drift = (
                    compare_portal_snapshot(observed_baseline, portal_snapshot)
                    if observed_baseline is not None
                    else {
                        'drift': False,
                        'reason': 'awaiting_contract_snapshot',
                        'missing_ids': [],
                        'unexpected_ids': [],
                        'changed_signals': [],
                    }
                )
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
                    'portal_contract_ids': portal_dependency_ids(),
                    'portal_missing_contract_ids': [
                        item for item in portal_dependency_ids()
                        if item not in portal_snapshot['known_ids']
                    ],
                    'portal_drift': drift,
                    'portal_extension_origin_match': portal_snapshot['origin'] == 'https://novaarearestrita.tce.rn.gov.br',
                    'submission_performed_by_runner': False,
                    'recording': {
                        'run_id': recording_id,
                        'event_count': len(events),
                        'error_count': len(errors),
                        'artifacts': {
                            'trace': 'trace.zip',
                            'network': 'network.har',
                            'recording': 'recording.json',
                        },
                    },
                }

            def persist_evidence() -> dict:
                current_evidence = capture()
                output.write_text(
                    json.dumps(current_evidence, ensure_ascii=False, indent=2) + '\n',
                    encoding='utf-8',
                )
                persist_recording()
                return current_evidence

            evidence = persist_evidence()
            print(json.dumps({
                'output': str(output),
                'recording_root': str(recording_root),
                'browser': executable.name,
                'profile': str(profile),
                'pair_status': evidence['pair_status'],
                'portal_origin': evidence['portal']['origin'],
                'portal_extension_origin_match': evidence['portal_extension_origin_match'],
                'login_signal': evidence['portal']['login_signal'],
                'portal_missing_contract_ids': evidence['portal_missing_contract_ids'],
                'portal_drift': evidence['portal_drift'],
                'recording': evidence['recording'],
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
                    persist_evidence()
        except KeyboardInterrupt:
            _record_event(events, {'kind': 'human_stop'})
            print('REAL_PORTAL_SESSION_STOPPED', flush=True)
        finally:
            if context is not None:
                try:
                    context.tracing.stop(path=str(recording_root / 'trace.zip'))
                except Exception as error:
                    errors.append({
                        'kind': 'trace_stop_failed',
                        'error_type': type(error).__name__,
                        'message_sha256': _hash_text(error),
                    })
                try:
                    context.close()
                except Exception as error:
                    errors.append({
                        'kind': 'browser_close_failed',
                        'error_type': type(error).__name__,
                        'message_sha256': _hash_text(error),
                    })
            persist_recording()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
