"""Run the scanned-PDF geometry gate with an explicitly selected OCR runtime."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw, ImageFont

from tce_extractor import extract_pdf_pages


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tesseract", type=Path, required=True)
    parser.add_argument("--tessdata", type=Path, required=True)
    args = parser.parse_args()
    if not args.tesseract.is_file() or not args.tessdata.is_dir():
        raise SystemExit("runtime OCR ausente")

    with TemporaryDirectory(prefix="tce-real-geometry-") as temporary:
        root = Path(temporary)
        image_path = root / "scan.png"
        pdf_path = root / "scan.pdf"
        image = Image.new("RGB", (1200, 220), "white")
        font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 52)
        ImageDraw.Draw(image).text((40, 70), "Cargo: PROFESSOR", fill="black", font=font)
        image.save(image_path)
        import fitz

        document = fitz.open()
        page = document.new_page(width=1200, height=220)
        page.insert_image(page.rect, filename=str(image_path))
        document.save(pdf_path)
        document.close()

        pages, geometry = extract_pdf_pages(
            pdf_path,
            tesseract=str(args.tesseract),
            tessdata_dir=args.tessdata,
            return_geometry=True,
        )

    text = " ".join(pages).upper()
    words = [word for page in geometry for word in page.get("words", [])]
    professor = next((word for word in words if "PROFESSOR" in str(word.get("text", "")).upper()), None)
    if "PROFESSOR" not in text or professor is None:
        raise AssertionError({"pages": pages, "geometry": geometry})
    rect = professor.get("rect")
    if not isinstance(rect, list) or len(rect) != 4 or not all(0 <= value <= 1 for value in rect):
        raise AssertionError({"word": professor})
    print(json.dumps({"method": geometry[0]["method"], "text": text, "word": professor}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
