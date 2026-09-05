"""Classify one temporary TCE PDF URL by native text, without OCR or persistence."""

from __future__ import annotations

import json

from targeted_collection import download_url, identify_target_document


def main(argv: list[str] | None = None) -> dict[str, object]:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--title", default="")
    args = parser.parse_args(argv)

    identified = identify_target_document(
        event=args.event,
        title=args.title,
        pdf_bytes=download_url(args.url),
    )
    return {
        "status": identified.status,
        "kind": identified.kind,
        "native_text_chars": identified.native_text_chars,
        "metadata_title": identified.metadata_title,
    }


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False))
