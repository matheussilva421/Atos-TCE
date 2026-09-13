import argparse
import json
import os
from pathlib import Path


def _read_object(path):
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON deve conter um objeto: {path}")
    return value


def _unique_process_keys(values, source):
    keys = []
    seen = set()
    for value in values:
        key = value.get("process_key") if isinstance(value, dict) else value
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"process_key inválido em {source}")
        key = key.strip()
        if key in seen:
            raise ValueError(f"process_key duplicado em {source}: {key}")
        seen.add(key)
        keys.append(key)
    if not keys:
        raise ValueError(f"coleção vazia em {source}")
    return keys


def write_process_collections(my_processes_order, sector_preview, output):
    order = _read_object(my_processes_order)
    preview = _read_object(sector_preview)
    my_keys = _unique_process_keys(order.get("process_keys", []), "Meus Processos")
    sector_keys = _unique_process_keys(
        preview.get("pending_processes", []), "Processos no Setor"
    )
    sector_interested = {}
    for item in preview.get("pending_processes", []):
        names = item.get("interested", []) if isinstance(item, dict) else []
        clean_names = []
        for name in names if isinstance(names, list) else []:
            clean = str(name).strip()
            if clean and clean not in clean_names:
                clean_names.append(clean)
        if clean_names:
            sector_interested[str(item["process_key"]).strip()] = clean_names
    payload = {
        "schema_version": 1,
        "default_collection": "sector_finalistic",
        "collections": [
            {
                "id": "my_processes",
                "label": "Meus Processos",
                "process_keys": my_keys,
            },
            {
                "id": "sector_finalistic",
                "label": "Processos no Setor",
                "process_keys": sector_keys,
                "interested_by_process": sector_interested,
            },
        ],
    }
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, destination)
    return payload


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Cria as visões ordenadas Meus Processos e Processos no Setor."
    )
    parser.add_argument("--my-processes-order", required=True)
    parser.add_argument("--sector-preview", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    payload = write_process_collections(
        args.my_processes_order, args.sector_preview, args.output
    )
    print(json.dumps({"collections": [
        {"id": item["id"], "count": len(item["process_keys"])}
        for item in payload["collections"]
    ]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
