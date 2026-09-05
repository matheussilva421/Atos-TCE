"""Read-only integrity checks, then extraction to a fresh QA directory."""
import hashlib
import json
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[2]
release = root / "outputs/TCE-Atos-CORRIGIDO-QA-2026-09-05"
archive = release.with_suffix(".zip")
destination = root / "tmp/verify-release-integrated"
if destination.exists():
    raise SystemExit("Refusing to overwrite QA extraction")
with zipfile.ZipFile(archive) as bundle:
    assert bundle.testzip() is None, "ZIP CRC failure"
    names = bundle.namelist()
    for name in names:
        assert ".." not in Path(name).parts and not Path(name).is_absolute()
        assert not set(Path(name).parts) & {"profile", "backups-acervo", "qa-mcp-live"}
    for relative in ("app/reset_archive.py", "app/menu.ps1", "app/html_generator.py",
                     "extensao-complementar-ato/content/form-detector.js",
                     "extensao-complementar-ato/background/service-worker.js",
                     "extensao-complementar-ato/lib/matcher.js"):
        source = Path(__file__).parent / (relative.removeprefix("app/") if relative == "app/html_generator.py" else "portable/" + relative)
        assert bundle.read(relative) == source.read_bytes(), relative
    manifest = json.loads(bundle.read("extensao-complementar-ato/manifest.json"))
    assert manifest["version"] == "1.0.1"
    bundle.extractall(destination)
print(json.dumps({"crc": "ok", "source_parity": "ok", "extension": manifest["version"],
    "files": len(names), "processes": sum(n.endswith("/processo.json") for n in names),
    "events": sum(n.endswith("/evento.json") for n in names),
    "pdfs": sum(n.lower().endswith(".pdf") for n in names),
    "sha256": hashlib.file_digest(archive.open("rb"), "sha256").hexdigest(),
    "extracted": str(destination)}, ensure_ascii=False))
