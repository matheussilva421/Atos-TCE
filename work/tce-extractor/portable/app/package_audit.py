"""Privacy, provenance, and license checks for the distributable package."""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat as stat_module
import sys
from typing import Any
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class AuditFinding:
    """One actionable reason why a package cannot be distributed."""

    code: str
    path: str
    message: str


# ``Finding`` is kept as a short public alias for callers that prefer the
# generic name while ``AuditFinding`` makes the report API self-describing.
Finding = AuditFinding


@dataclass
class AuditReport:
    """Results of an audit; an empty finding list is the only green state."""

    findings: list[AuditFinding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings

    def add(self, code: str, path: str, message: str) -> None:
        finding = AuditFinding(code=code, path=path, message=message)
        if finding not in self.findings:
            self.findings.append(finding)

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "findings": [
                {
                    "code": finding.code,
                    "path": finding.path,
                    "message": finding.message,
                }
                for finding in self.findings
            ],
        }


_TEXT_SUFFIXES = {
    ".cmd",
    ".conf",
    ".css",
    ".csv",
    ".html",
    ".ini",
    ".js",
    ".mjs",
    ".json",
    ".md",
    ".ps1",
    ".psm1",
    ".py",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
_ALLOWLISTED_BINARY_SUFFIXES = {
    ".cat",
    ".dll",
    ".exe",
    ".lib",
    ".pyd",
    ".pyc",
    ".traineddata",
    ".zip",
}
_TEMPORARY_URL_RE = re.compile(
    r"(?:https?://|/)[^\s\"']*consultaprocessotemp\b", re.IGNORECASE
)
_REMOTE_URL_RE = re.compile(r"https?://[^\s\"'`<>]+", re.IGNORECASE)
_DYNAMIC_CODE_RE = re.compile(r"\beval\s*\(|\bnew\s+Function\s*\(", re.IGNORECASE)
_AUTHORIZATION_RE = re.compile(
    r"(?i)(?<![\w-])(?:[\"']authorization[\"']|authorization)\s*:\s*"
    r"(?:[\"'][^\"'\r\n]*[\"']|(?:bearer|basic|digest|token)\s+[^\s,}\]]+)",
)
_COOKIE_HEADER_RE = re.compile(
    r"(?i)(?<![\w-])(?:cookie|set-cookie)\s*:\s*"
    r"(?:[\"'][^\"'\r\n]+[\"']|[^\s\r\n][^\r\n]*)",
)
_COOKIE_ACCESS_RE = re.compile(
    r"\b(?:(?:chrome|browser)\s*\.\s*cookies\s*\.|document\s*\.\s*cookie\b|cookieStore\s*\.)",
    re.IGNORECASE,
)
_AUTHORIZATION_SETTER_RE = re.compile(
    r"\b(?:headers\s*\.\s*set|(?:[A-Za-z_$][\w$]*\s*\.\s*)?setRequestHeader)"
    r"\s*\(\s*[\"']authorization[\"']\s*,\s*"
    r"(?:[\"'][^\"'\r\n]*[\"']|(?:bearer|basic|digest|token)\s+[^\s,}\]]+)",
    re.IGNORECASE,
)
_COOKIE_SETTER_RE = re.compile(
    r"\b(?:headers\s*\.\s*set|(?:[A-Za-z_$][\w$]*\s*\.\s*)?setRequestHeader)"
    r"\s*\(\s*[\"'](?:cookie|set-cookie)[\"']\s*,",
    re.IGNORECASE,
)
_JSON_SECRET_KEY_RE = re.compile(
    r"(?<![\w-])[\"']?\s*(?:token|access_?token|refresh_?token|id_?token|auth_?token|session_?token|cookies)\s*[\"']?\s*:"
    r"\s*(?:[\"'][^\"'\r\n]*[\"']|\d+(?:\.\d+)?|true|false|null)",
    re.IGNORECASE,
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
_FORBIDDEN_SUFFIXES = {".pdf", ".part", ".tmp"}
_FORBIDDEN_DIRECTORY_NAMES = {"dados-locais", "downloads"}
_PRIVATE_DATA_DIRECTORY_NAMES = {"cache", "data", "dados", "database", "databases", "state"}
_BROWSER_PROFILE_DIRECTORY_NAMES = {
    "chrome",
    "chromium",
    "user data",
    "perfil-navegador",
    "default",
    "guest profile",
    "system profile",
}
_BROWSER_CREDENTIAL_FILE_NAMES = {"cookies", "login data", "web data", "local state"}
_ACERVO_DIRECTORY = "acervo-tce"
_EXTENSION_DIRECTORY = "extensao-complementar-ato"
_PRIVATE_PACKAGE_DIRECTORY_ALLOWLIST = {
    "app",
    _ACERVO_DIRECTORY,
    _EXTENSION_DIRECTORY,
    "licenses",
    "runtime",
}
_ALLOWED_HOST = "https://novaarearestrita.tce.rn.gov.br"
_ALLOWED_HOST_PATTERN = f"{_ALLOWED_HOST}/*"
_EXTENSION_FILE_ALLOWLIST = frozenset(
    {
        "manifest.json",
        "package.json",
        "content/package.json",
        "content/form-detector.js",
        "background/service-worker.js",
        "lib/matcher.js",
        "lib/messages.js",
        "lib/normalizer.js",
        "lib/schema.js",
        "sidepanel/panel.css",
        "sidepanel/panel.html",
        "sidepanel/panel.js",
    }
)
_SENSITIVE_JSON_KEYS = frozenset(
    {"token", "accesstoken", "refreshtoken", "idtoken", "authtoken", "sessiontoken", "cookies"}
)
_REPARSE_POINT_FLAG = 0x400


def _relative_name(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path).replace("\\", "/")


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _append_path_findings(
    report: AuditReport,
    relative: str,
    *,
    distribution: str = "public",
) -> None:
    parts = PurePosixPath(relative.casefold()).parts
    if any(part in _FORBIDDEN_DIRECTORY_NAMES for part in parts):
        report.add(
            "private_path",
            relative,
            "pacote não pode conter perfil ou acervo local",
        )
    if any(part in _BROWSER_PROFILE_DIRECTORY_NAMES for part in parts):
        report.add("browser_profile", relative, "perfil de navegador não é distribuível")
    if parts and parts[-1] in _BROWSER_CREDENTIAL_FILE_NAMES:
        report.add("credential_path", relative, "arquivo de credenciais do navegador não é distribuível")

    is_acervo_path = bool(parts and parts[0] == _ACERVO_DIRECTORY)
    if _ACERVO_DIRECTORY in parts and distribution == "public":
        report.add(
            "private_path",
            relative,
            "pacote público não pode conter acervo local",
        )
    if distribution == "private" and _ACERVO_DIRECTORY in parts[1:]:
        report.add(
            "private_data_path",
            relative,
            "acervo-tce privado só pode existir na raiz do pacote",
        )
    if (
        distribution == "private"
        and not is_acervo_path
        and (
            any(part in _PRIVATE_DATA_DIRECTORY_NAMES for part in parts[:-1])
            or (len(parts) > 1 and parts[0] not in _PRIVATE_PACKAGE_DIRECTORY_ALLOWLIST)
        )
    ):
        report.add(
            "private_data_path",
            relative,
            "área de dados privada só é permitida sob acervo-tce",
        )
    if any("checkpoint" in part for part in parts) and not (
        distribution == "private" and is_acervo_path
    ):
        report.add("checkpoint_present", relative, "checkpoint de usuário não é distribuível")

    suffix = PurePosixPath(relative).suffix.casefold()
    if suffix == ".pdf" and not (distribution == "private" and is_acervo_path):
        report.add("forbidden_file", relative, "arquivo .pdf não é distribuível nesta distribuição")
    elif suffix in {".part", ".tmp"}:
        report.add("forbidden_file", relative, f"arquivo {suffix} não é distribuível")

    if parts and parts[-1] == "dados-complementar-ato.json" and not (
        distribution == "private" and is_acervo_path
    ):
        report.add(
            "private_data_path",
            relative,
            "dados da extensão só podem acompanhar o acervo privado",
        )


def _is_reparse_point(info: os.stat_result) -> bool:
    attributes = int(getattr(info, "st_file_attributes", 0) or 0)
    return stat_module.S_ISLNK(info.st_mode) or bool(attributes & _REPARSE_POINT_FLAG)


def _walk_package(
    root: Path,
    report: AuditReport,
    *,
    distribution: str = "public",
) -> Iterator[tuple[Path, os.stat_result]]:
    """Walk without following links and report every enumeration failure."""

    stack = [root]
    while stack:
        directory = stack.pop()
        relative_directory = _relative_name(root, directory)
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda item: item.name.casefold())
        except OSError as error:
            report.add(
                "enumeration_error",
                relative_directory or ".",
                f"não foi possível enumerar o diretório: {error}",
            )
            continue

        for entry in entries:
            path = Path(entry.path)
            relative = _relative_name(root, path)
            _append_path_findings(report, relative, distribution=distribution)
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError as error:
                report.add(
                    "enumeration_error",
                    relative,
                    f"não foi possível inspecionar o item: {error}",
                )
                continue

            if _is_reparse_point(info):
                report.add(
                    "reparse_point",
                    relative,
                    "symlink, junction ou outro reparse point não é permitido",
                )
                continue
            if stat_module.S_ISDIR(info.st_mode):
                stack.append(path)
            elif stat_module.S_ISREG(info.st_mode):
                yield path, info
            else:
                report.add("unsupported_item", relative, "item não é arquivo ou diretório regular")


def _looks_utf16(data: bytes, little_endian: bool) -> bool:
    sample = data[:4096]
    if len(sample) < 8:
        return False
    zeroes = sample[1::2] if little_endian else sample[0::2]
    non_zeroes = sample[0::2] if little_endian else sample[1::2]
    if len(zeroes) == 0 or sum(value == 0 for value in zeroes) < 4:
        return False
    if sum(value == 0 for value in zeroes) / len(zeroes) < 0.35:
        return False
    printable = sum(value in (9, 10, 13) or 32 <= value <= 126 for value in non_zeroes)
    return printable / max(1, len(non_zeroes)) >= 0.75


def _decode_text(data: bytes) -> str:
    encodings: list[str] = []
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        encodings.append("utf-16")
    elif _looks_utf16(data, little_endian=True):
        encodings.append("utf-16-le")
    elif _looks_utf16(data, little_endian=False):
        encodings.append("utf-16-be")
    encodings.append("utf-8-sig")

    last_error: UnicodeError | None = None
    for encoding in encodings:
        try:
            text = data.decode(encoding)
        except UnicodeError as error:
            last_error = error
            continue
        if "\x00" in text:
            last_error = UnicodeDecodeError(
                "package_audit",
                data,
                0,
                min(1, len(data)),
                "NUL byte in decoded text",
            )
            continue
        return text
    if last_error is None:
        raise UnicodeError("conteúdo vazio não é texto")
    raise last_error


def _read_text(path: Path, relative: str, report: AuditReport) -> str | None:
    suffix = path.suffix.casefold()
    if suffix in _ALLOWLISTED_BINARY_SUFFIXES or suffix in _FORBIDDEN_SUFFIXES:
        return None
    try:
        data = path.read_bytes()
    except OSError as error:
        report.add("read_error", relative, f"não foi possível ler o arquivo: {error}")
        return None
    try:
        return _decode_text(data)
    except UnicodeError as error:
        report.add(
            "binary_unrecognized",
            relative,
            f"arquivo não é texto decodificável nem extensão binária allowlisted: {error}",
        )
        return None


def _scan_text_fragments(
    report: AuditReport,
    relative: str,
    text: str,
    *,
    scan_credentials: bool = True,
) -> None:
    if _TEMPORARY_URL_RE.search(text):
        report.add(
            "temporary_url",
            relative,
            "URL ConsultaProcessoTemp detectada no conteúdo",
        )
    if not scan_credentials:
        return
    if _AUTHORIZATION_RE.search(text) or _AUTHORIZATION_SETTER_RE.search(text):
        report.add("authorization_present", relative, "cabeçalho Authorization detectado")
    if (
        _COOKIE_HEADER_RE.search(text)
        or _COOKIE_SETTER_RE.search(text)
        or _JSON_SECRET_KEY_RE.search(text)
    ):
        report.add(
            "credential_field",
            relative,
            "cookie ou campo de token detectado no conteúdo",
        )
    if _COOKIE_ACCESS_RE.search(text):
        report.add("credential_access", relative, "acesso a cookies detectado no conteúdo")


def _has_json_value(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _scan_json_value(
    report: AuditReport,
    relative: str,
    value: Any,
    *,
    scan_credentials: bool = True,
) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            key_folded = re.sub(r"[^a-z0-9]", "", key_text.casefold())
            if scan_credentials and key_folded in _SENSITIVE_JSON_KEYS:
                report.add(
                    "credential_field",
                    relative,
                    f"chave JSON sensível detectada: {key_text}",
                )
            if scan_credentials and key_folded == "authorization" and _has_json_value(child):
                report.add(
                    "authorization_present",
                    relative,
                    "campo JSON Authorization com valor detectado",
                )
            _scan_text_fragments(
                report, relative, key_text, scan_credentials=scan_credentials
            )
            _scan_json_value(
                report, relative, child, scan_credentials=scan_credentials
            )
        return
    if isinstance(value, list):
        for child in value:
            _scan_json_value(report, relative, child, scan_credentials=scan_credentials)
        return
    if isinstance(value, str):
        _scan_text_fragments(
            report, relative, value, scan_credentials=scan_credentials
        )


def _audit_content(
    report: AuditReport,
    path: Path,
    relative: str,
    *,
    scan_credentials: bool = True,
) -> None:
    text = _read_text(path, relative, report)
    if text is None:
        return
    _scan_text_fragments(
        report, relative, text, scan_credentials=scan_credentials
    )
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        if path.suffix.casefold() == ".json":
            report.add("json_invalid", relative, "arquivo JSON inválido")
        return
    except (TypeError, ValueError):
        if path.suffix.casefold() == ".json":
            report.add("json_invalid", relative, "arquivo JSON inválido")
        return
    _scan_json_value(
        report, relative, parsed, scan_credentials=scan_credentials
    )


def _extension_relative(relative: str) -> str | None:
    prefix = _EXTENSION_DIRECTORY + "/"
    folded = relative.casefold()
    if not folded.startswith(prefix):
        return None
    return relative[len(prefix) :]


def _extension_path(root: Path, relative: str) -> Path | None:
    resolved = _manifest_path(root / _EXTENSION_DIRECTORY, relative)
    if resolved is None:
        return None
    _safe_relative, candidate = resolved
    return candidate


def _append_manifest_file_reference(
    root: Path,
    report: AuditReport,
    manifest_relative: str,
    declared: list[str],
    raw_path: object,
    location: str,
) -> None:
    resolved = _manifest_path(root / _EXTENSION_DIRECTORY, raw_path)
    if resolved is None:
        report.add(
            "extension_declared_file_invalid",
            f"{manifest_relative}#{location}",
            "referência de arquivo do Manifest V3 deve ser caminho relativo seguro",
        )
        return
    relative, _candidate = resolved
    declared.append(relative)


def _append_manifest_icon_references(
    root: Path,
    report: AuditReport,
    manifest_relative: str,
    declared: list[str],
    value: object,
    location: str,
) -> None:
    if isinstance(value, str):
        _append_manifest_file_reference(
            root, report, manifest_relative, declared, value, location
        )
        return
    if not isinstance(value, Mapping) or not value:
        report.add(
            "extension_declared_file_invalid",
            f"{manifest_relative}#{location}",
            "ícones do Manifest V3 devem declarar caminho ou mapa de caminhos",
        )
        return
    for size, raw_path in value.items():
        _append_manifest_file_reference(
            root,
            report,
            manifest_relative,
            declared,
            raw_path,
            f"{location}.{size}",
        )


def _manifest_reference_exists(extension: Path, relative: str) -> bool:
    if any(character in relative for character in "*?["):
        try:
            return any(path.is_file() for path in extension.glob(relative))
        except (OSError, ValueError):
            return False
    candidate = _extension_path(extension.parent, relative)
    return candidate is not None and candidate.is_file()


def _audit_extension(
    root: Path,
    report: AuditReport,
    audited_files: Iterable[tuple[Path, os.stat_result]],
) -> None:
    extension = root / _EXTENSION_DIRECTORY
    extension_files = [
        (path, info)
        for path, info in audited_files
        if _extension_relative(_relative_name(root, path)) is not None
    ]
    manifest_path = extension / "manifest.json"
    if not extension.is_dir():
        report.add(
            "extension_missing",
            _relative_name(root, extension),
            "extensão complementar ausente",
        )
        return

    allowlisted = {name.casefold() for name in _EXTENSION_FILE_ALLOWLIST}
    observed = set()
    for path, _info in extension_files:
        relative = _extension_relative(_relative_name(root, path))
        assert relative is not None
        observed.add(relative.casefold())
        if relative.casefold() not in allowlisted:
            report.add(
                "extension_file_unlisted",
                _relative_name(root, path),
                "arquivo da extensão não está no inventário allowlisted",
            )
    for relative in sorted(allowlisted - observed):
        report.add(
            "extension_file_missing",
            f"{_EXTENSION_DIRECTORY}/{relative}",
            "arquivo allowlisted da extensão não existe",
        )

    try:
        manifest_text = _decode_text(manifest_path.read_bytes())
        manifest = json.loads(manifest_text)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        report.add(
            "extension_manifest_invalid",
            _relative_name(root, manifest_path),
            f"Manifest V3 inválido: {error}",
        )
        return
    if not isinstance(manifest, dict):
        report.add(
            "extension_manifest_invalid",
            _relative_name(root, manifest_path),
            "Manifest V3 deve ser um objeto JSON",
        )
        return
    if manifest.get("manifest_version") != 3:
        report.add(
            "extension_manifest_version",
            _relative_name(root, manifest_path),
            "a extensão deve usar Manifest V3",
        )

    permissions = manifest.get("permissions")
    if not isinstance(permissions, list) or [str(item) for item in permissions] != [
        "storage",
        "sidePanel",
    ]:
        report.add(
            "extension_permissions",
            _relative_name(root, manifest_path),
            "permissões devem ser exatamente storage e sidePanel",
        )

    host_permissions = manifest.get("host_permissions")
    if host_permissions != [_ALLOWED_HOST_PATTERN]:
        report.add(
            "extension_hosts",
            _relative_name(root, manifest_path),
            f"host permitido deve ser somente {_ALLOWED_HOST_PATTERN}",
        )

    manifest_relative = _relative_name(root, manifest_path)
    declared: list[str] = []
    background = manifest.get("background")
    if not isinstance(background, dict) or not isinstance(
        background.get("service_worker"), str
    ):
        report.add(
            "extension_declared_file_invalid",
            _relative_name(root, manifest_path),
            "background.service_worker ausente ou inválido",
        )
    else:
        _append_manifest_file_reference(
            root,
            report,
            manifest_relative,
            declared,
            background["service_worker"],
            "background.service_worker",
        )

    side_panel = manifest.get("side_panel")
    if not isinstance(side_panel, dict) or not isinstance(side_panel.get("default_path"), str):
        report.add(
            "extension_declared_file_invalid",
            _relative_name(root, manifest_path),
            "side_panel.default_path ausente ou inválido",
        )
    else:
        _append_manifest_file_reference(
            root,
            report,
            manifest_relative,
            declared,
            side_panel["default_path"],
            "side_panel.default_path",
        )

    content_scripts = manifest.get("content_scripts")
    if not isinstance(content_scripts, list) or not content_scripts:
        report.add(
            "extension_declared_file_invalid",
            _relative_name(root, manifest_path),
            "content_scripts ausente ou vazio",
        )
    else:
        for index, script in enumerate(content_scripts):
            if not isinstance(script, dict) or not isinstance(script.get("js"), list):
                report.add(
                    "extension_declared_file_invalid",
                    f"{_relative_name(root, manifest_path)}#content_scripts[{index}]",
                    "content script deve declarar uma lista js",
                )
                continue
            if script.get("matches") != [_ALLOWED_HOST_PATTERN]:
                report.add(
                    "extension_hosts",
                    f"{_relative_name(root, manifest_path)}#content_scripts[{index}]",
                    f"content script deve usar somente {_ALLOWED_HOST_PATTERN}",
                )
            for key in ("js", "css"):
                paths = script.get(key, [])
                if not isinstance(paths, list):
                    report.add(
                        "extension_declared_file_invalid",
                        f"{manifest_relative}#content_scripts[{index}].{key}",
                        f"content_scripts[{index}].{key} deve ser uma lista",
                    )
                    continue
                for item_index, path in enumerate(paths):
                    _append_manifest_file_reference(
                        root,
                        report,
                        manifest_relative,
                        declared,
                        path,
                        f"content_scripts[{index}].{key}[{item_index}]",
                    )

    action = manifest.get("action")
    if "action" in manifest and not isinstance(action, Mapping):
        report.add(
            "extension_declared_file_invalid",
            f"{manifest_relative}#action",
            "action deve ser um objeto",
        )
    elif isinstance(action, Mapping):
        if "default_popup" in action:
            _append_manifest_file_reference(
                root, report, manifest_relative, declared, action["default_popup"], "action.default_popup"
            )
        if "default_icon" in action:
            _append_manifest_icon_references(
                root, report, manifest_relative, declared, action["default_icon"], "action.default_icon"
            )
    if "icons" in manifest:
        _append_manifest_icon_references(
            root, report, manifest_relative, declared, manifest["icons"], "icons"
        )

    for key in ("options_page", "devtools_page"):
        if key in manifest:
            _append_manifest_file_reference(
                root, report, manifest_relative, declared, manifest[key], key
            )
    options_ui = manifest.get("options_ui")
    if "options_ui" in manifest and not isinstance(options_ui, Mapping):
        report.add(
            "extension_declared_file_invalid",
            f"{manifest_relative}#options_ui",
            "options_ui deve ser um objeto",
        )
    elif isinstance(options_ui, Mapping) and "page" in options_ui:
        _append_manifest_file_reference(
            root, report, manifest_relative, declared, options_ui["page"], "options_ui.page"
        )
    storage = manifest.get("storage")
    if "storage" in manifest and not isinstance(storage, Mapping):
        report.add(
            "extension_declared_file_invalid",
            f"{manifest_relative}#storage",
            "storage deve ser um objeto",
        )
    elif isinstance(storage, Mapping) and "managed_schema" in storage:
        _append_manifest_file_reference(
            root,
            report,
            manifest_relative,
            declared,
            storage["managed_schema"],
            "storage.managed_schema",
        )
    theme = manifest.get("theme")
    if "theme" in manifest and not isinstance(theme, Mapping):
        report.add(
            "extension_declared_file_invalid",
            f"{manifest_relative}#theme",
            "theme deve ser um objeto",
        )
    theme_images = theme.get("images") if isinstance(theme, Mapping) else None
    if isinstance(theme_images, Mapping):
        for image_name, raw_path in theme_images.items():
            _append_manifest_file_reference(
                root,
                report,
                manifest_relative,
                declared,
                raw_path,
                f"theme.images.{image_name}",
            )
    if "default_locale" in manifest:
        locale = manifest["default_locale"]
        locale_path = (
            f"_locales/{locale}/messages.json" if isinstance(locale, str) else None
        )
        _append_manifest_file_reference(
            root,
            report,
            manifest_relative,
            declared,
            locale_path,
            "default_locale",
        )
    overrides = manifest.get("chrome_url_overrides")
    if "chrome_url_overrides" in manifest and not isinstance(overrides, Mapping):
        report.add(
            "extension_declared_file_invalid",
            f"{manifest_relative}#chrome_url_overrides",
            "chrome_url_overrides deve ser um objeto",
        )
    elif isinstance(overrides, Mapping):
        for page_name, raw_path in overrides.items():
            _append_manifest_file_reference(
                root, report, manifest_relative, declared, raw_path, f"chrome_url_overrides.{page_name}"
            )
    sandbox = manifest.get("sandbox")
    if "sandbox" in manifest and not isinstance(sandbox, Mapping):
        report.add(
            "extension_declared_file_invalid",
            f"{manifest_relative}#sandbox",
            "sandbox deve ser um objeto",
        )
    elif isinstance(sandbox, Mapping) and "pages" in sandbox:
        pages = sandbox["pages"]
        if not isinstance(pages, list):
            report.add(
                "extension_declared_file_invalid",
                f"{manifest_relative}#sandbox.pages",
                "sandbox.pages deve ser uma lista",
            )
        else:
            for index, raw_path in enumerate(pages):
                _append_manifest_file_reference(
                    root, report, manifest_relative, declared, raw_path, f"sandbox.pages[{index}]"
                )
    resources = manifest.get("web_accessible_resources")
    if "web_accessible_resources" in manifest and not isinstance(resources, list):
        report.add(
            "extension_declared_file_invalid",
            f"{manifest_relative}#web_accessible_resources",
            "web_accessible_resources deve ser uma lista",
        )
    elif isinstance(resources, list):
        for index, entry in enumerate(resources):
            raw_paths = entry.get("resources") if isinstance(entry, Mapping) else None
            if not isinstance(raw_paths, list):
                report.add(
                    "extension_declared_file_invalid",
                    f"{manifest_relative}#web_accessible_resources[{index}].resources",
                    "web_accessible_resources.resources deve ser uma lista",
                )
                continue
            for item_index, raw_path in enumerate(raw_paths):
                _append_manifest_file_reference(
                    root,
                    report,
                    manifest_relative,
                    declared,
                    raw_path,
                    f"web_accessible_resources[{index}].resources[{item_index}]",
                )
    dnr = manifest.get("declarative_net_request")
    if "declarative_net_request" in manifest and not isinstance(dnr, Mapping):
        report.add(
            "extension_declared_file_invalid",
            f"{manifest_relative}#declarative_net_request",
            "declarative_net_request deve ser um objeto",
        )
    rules = dnr.get("rule_resources") if isinstance(dnr, Mapping) else None
    if rules is not None:
        if not isinstance(rules, list):
            report.add(
                "extension_declared_file_invalid",
                f"{manifest_relative}#declarative_net_request.rule_resources",
                "declarative_net_request.rule_resources deve ser uma lista",
            )
        else:
            for index, rule in enumerate(rules):
                raw_path = rule.get("path") if isinstance(rule, Mapping) else None
                _append_manifest_file_reference(
                    root,
                    report,
                    manifest_relative,
                    declared,
                    raw_path,
                    f"declarative_net_request.rule_resources[{index}].path",
                )

    for relative in declared:
        if not _manifest_reference_exists(extension, relative):
            report.add(
                "extension_file_missing",
                f"{_EXTENSION_DIRECTORY}/{relative}",
                "arquivo declarado no Manifest V3 não existe",
            )

    for path, _info in extension_files:
        relative = _relative_name(root, path)
        text = _read_text(path, relative, report)
        if text is None:
            continue
        for match in _REMOTE_URL_RE.finditer(text):
            raw_url = match.group(0).rstrip(".,;:)]}>")
            parsed = urlsplit(raw_url)
            origin = f"{parsed.scheme}://{parsed.netloc}".casefold()
            if origin != _ALLOWED_HOST.casefold() or parsed.scheme.casefold() != "https":
                report.add(
                    "extension_remote_code",
                    relative,
                    "URL remota ou host fora da origem única permitida",
                )
        if _DYNAMIC_CODE_RE.search(text):
            report.add(
                "extension_dynamic_code",
                relative,
                "eval( e new Function( não são permitidos na extensão",
            )


def _audit_required_app_files(
    root: Path, report: AuditReport, *, required: bool = False
) -> None:
    app = root / "app"
    if not required and not app.is_dir():
        return
    for name in ("extension_exporter.py", "package_complete_archive.py"):
        path = app / name
        if not path.is_file():
            report.add(
                "app_file_missing",
                _relative_name(root, path),
                "módulo obrigatório do pacote público não existe",
            )


def _audit_private_dataset(root: Path, report: AuditReport) -> None:
    path = root / _ACERVO_DIRECTORY / "dados-complementar-ato.json"
    if not path.is_file():
        report.add(
            "private_data_missing",
            _relative_name(root, path),
            "distribuição privada exige dados-complementar-ato.json sob acervo-tce",
        )


def _manifest_path(root: Path, raw_path: object) -> tuple[str, Path] | None:
    if not isinstance(raw_path, str) or not raw_path.strip() or "\x00" in raw_path:
        return None

    normalized = raw_path.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(normalized)
    if (
        posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or any(part in {"", ".", ".."} for part in posix.parts)
    ):
        return None

    relative = posix.as_posix()
    candidate = root.joinpath(*posix.parts)
    try:
        if not _is_within(candidate.resolve(), root.resolve()):
            return None
    except OSError:
        return None
    return relative, candidate


def _load_manifest(root: Path, report: AuditReport) -> list[dict[str, object]]:
    manifest_path = root / "runtime-manifest.json"
    relative = _relative_name(root, manifest_path)
    if not manifest_path.is_file():
        report.add("manifest_missing", relative, "runtime-manifest.json ausente")
        return []

    try:
        text = _decode_text(manifest_path.read_bytes())
        document = json.loads(text)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        report.add("manifest_invalid", relative, f"manifesto inválido: {error}")
        return []

    if not isinstance(document, dict):
        report.add("manifest_invalid", relative, "manifesto deve ser um objeto JSON")
        return []
    if document.get("schema_version") != 1:
        report.add("manifest_schema_invalid", relative, "schema_version deve ser 1")
    build = document.get("build")
    entries = build.get("included_files") if isinstance(build, dict) else None
    if not isinstance(entries, list):
        report.add(
            "manifest_entries_missing",
            relative,
            "build.included_files ausente ou inválido",
        )
        return []
    if not entries:
        report.add("manifest_entries_empty", relative, "build.included_files não pode ser vazio")

    valid_entries: list[dict[str, object]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            report.add(
                "manifest_entry_invalid",
                f"{relative}#build.included_files[{index}]",
                "cada entrada do manifesto deve ser um objeto JSON",
            )
            continue
        valid_entries.append(entry)
    return valid_entries


def _audit_manifest_entries(
    root: Path,
    report: AuditReport,
    entries: list[dict[str, object]],
    audited_files: Iterable[tuple[Path, os.stat_result]],
) -> set[str]:
    listed: set[str] = set()
    trusted_vendor_files: set[str] = set()
    has_runtime = False
    has_license = False
    for entry in entries:
        raw_path = entry.get("path")
        resolved = _manifest_path(root, raw_path)
        if resolved is None:
            report.add(
                "manifest_path_invalid",
                str(raw_path) if raw_path is not None else "<missing>",
                "entrada do manifesto deve ser um caminho relativo seguro",
            )
            continue

        relative, candidate = resolved
        normalized_key = relative.casefold()
        if normalized_key in listed:
            report.add("manifest_duplicate", relative, "caminho duplicado no manifesto")
        listed.add(normalized_key)
        if relative.casefold().startswith("runtime/"):
            has_runtime = True
        elif relative.casefold().startswith("licenses/"):
            has_license = True
        else:
            report.add(
                "manifest_path_scope",
                relative,
                "included_files só pode declarar runtime/ ou licenses/",
            )

        expected_size = entry.get("size")
        expected_hash = entry.get("sha256")
        valid_size = (
            isinstance(expected_size, int)
            and not isinstance(expected_size, bool)
            and expected_size >= 0
        )
        valid_hash = isinstance(expected_hash, str) and _SHA256_RE.fullmatch(expected_hash)
        if not valid_size:
            report.add("manifest_entry_invalid", relative, "tamanho esperado inválido")
        if not valid_hash:
            report.add("hash_invalid", relative, "SHA-256 esperado inválido")

        try:
            exists_as_file = candidate.is_file() and not _is_reparse_point(candidate.lstat())
        except OSError as error:
            report.add("enumeration_error", relative, f"não foi possível inspecionar a entrada: {error}")
            continue
        if not exists_as_file:
            report.add("file_missing", relative, "arquivo listado no manifesto não existe")
            continue

        verified = valid_size and valid_hash
        try:
            observed_size = candidate.stat().st_size
        except OSError as error:
            report.add("read_error", relative, f"não foi possível obter o tamanho: {error}")
            continue
        if valid_size and observed_size != expected_size:
            verified = False
            report.add(
                "size_divergence",
                relative,
                f"tamanho divergente: esperado {expected_size}, observado {observed_size}",
            )

        if valid_hash:
            try:
                observed_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
            except OSError as error:
                verified = False
                report.add("read_error", relative, f"não foi possível calcular SHA-256: {error}")
                continue
            if observed_hash.casefold() != expected_hash.casefold():
                verified = False
                report.add(
                    "hash_divergence",
                    relative,
                    f"SHA-256 divergente: esperado {expected_hash}, observado {observed_hash}",
                )
        if verified and (
            relative.casefold().startswith("runtime/")
            or relative.casefold().startswith("licenses/")
        ):
            trusted_vendor_files.add(normalized_key)

    if not has_runtime:
        report.add("manifest_runtime_missing", "runtime-manifest.json", "manifesto não declara runtime/")
    if not has_license:
        report.add("manifest_license_missing", "runtime-manifest.json", "manifesto não declara licenses/")

    for path, _info in audited_files:
        relative = _relative_name(root, path)
        normalized = relative.casefold()
        if (normalized.startswith("runtime/") or normalized.startswith("licenses/")) and normalized not in listed:
            report.add("file_unlisted", relative, "arquivo runtime/licença não está no manifesto")

    return trusted_vendor_files


def _audit_licenses(root: Path, report: AuditReport, audited_files: Iterable[tuple[Path, os.stat_result]]) -> None:
    licenses = root / "licenses"
    license_prefix = _relative_name(root, licenses).casefold().rstrip("/") + "/"
    files = [
        path
        for path, _info in audited_files
        if _relative_name(root, path).casefold().startswith(license_prefix)
    ]
    try:
        exists_as_directory = licenses.is_dir() and not _is_reparse_point(licenses.lstat())
    except OSError as error:
        report.add("license_missing", _relative_name(root, licenses), f"falha ao ler licenças: {error}")
        return
    if not exists_as_directory or not files:
        report.add(
            "license_missing",
            _relative_name(root, licenses),
            "ao menos um aviso de licença deve acompanhar o runtime",
        )


def audit_package(root: Path, *, distribution: str = "public") -> AuditReport:
    """Audit a package staging directory without changing any file."""

    root = Path(root)
    report = AuditReport()
    if distribution not in {"public", "private"}:
        report.add(
            "distribution_invalid",
            "<distribution>",
            "distribuição deve ser public ou private",
        )
        return report
    try:
        root_info = root.lstat()
    except OSError as error:
        report.add("enumeration_error", str(root), f"não foi possível inspecionar a raiz: {error}")
        return report
    if _is_reparse_point(root_info):
        report.add("reparse_point", str(root), "a raiz do pacote não pode ser reparse point")
        return report
    if not stat_module.S_ISDIR(root_info.st_mode):
        report.add("package_missing", str(root), "raiz do pacote ausente ou não é diretório")
        return report

    audited_files = list(_walk_package(root, report, distribution=distribution))
    entries = _load_manifest(root, report)
    trusted_vendor_files = _audit_manifest_entries(root, report, entries, audited_files)
    for path, _info in audited_files:
        relative = _relative_name(root, path)
        _audit_content(
            report,
            path,
            relative,
            scan_credentials=relative.casefold() not in trusted_vendor_files,
        )
    _audit_licenses(root, report, audited_files)
    _audit_required_app_files(root, report, required=distribution == "public")
    if distribution == "private":
        _audit_private_dataset(root, report)
    if distribution == "public" or (root / _EXTENSION_DIRECTORY).exists() or (root / "app").is_dir():
        _audit_extension(root, report, audited_files)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_root", type=Path)
    parser.add_argument("--distribution", choices=("public", "private"), default="public")
    try:
        parsed = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    except SystemExit as error:
        return int(error.code)
    report = audit_package(parsed.package_root, distribution=parsed.distribution)
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
