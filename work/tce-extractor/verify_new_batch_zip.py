"""Verify the newly collected batch without changing its source archive."""
import json
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[2]
archive = root / "outputs/TCE-Acervo-Atualizado-227-2026-09-05.zip"
destination = root / "tmp/verify-new-batch-227"
with zipfile.ZipFile(archive) as bundle:
    assert bundle.testzip() is None, "CRC failure"
    names = bundle.namelist()
    assert not any("backups-acervo" in n or "perfil-navegador" in n for n in names)
    assert sum(n.endswith("/processo.json") for n in names) == 227
    assert sum(n.endswith("/evento.json") for n in names) == 5236
    assert sum(n.lower().endswith(".pdf") for n in names) == 4532
    data = json.loads(bundle.read("acervo-tce/dados-complementar-ato.json"))
    assert data["batch"]["process_count"] == 227
    assert len(data["records"]) == 235
    html = bundle.read("acervo-tce/complementar-ato.html").decode("utf-8")
    assert "3503f45755894391a2e51dbda7a124d2" in html
    assert not destination.exists(), "Do not overwrite extraction"
    for name in names:
        path = (destination / name).resolve()
        assert path.is_relative_to(destination.resolve())
    bundle.extractall(destination)
print(json.dumps({"zip_crc":"ok", "processes":227, "events":5236,
                  "pdfs":4532, "records":235, "backup_excluded":True,
                  "extracted":str(destination)}))
