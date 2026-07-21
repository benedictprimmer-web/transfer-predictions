"""Render the club-fit ReportLab PDF to PNG pages and a contact sheet.

Run:
    python3 scripts/render_club_fit_pdf.py
"""
from __future__ import annotations

from pathlib import Path

import fitz
from PIL import Image, ImageOps


REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "reports" / "club-fit"
PDF = OUT / "chelsea-arsenal-player-review.pdf"
RENDERED = OUT / "rendered-pages"


def main() -> int:
    RENDERED.mkdir(parents=True, exist_ok=True)
    for old in RENDERED.glob("page-*.pdf.png"):
        old.unlink()

    doc = fitz.open(PDF)
    rendered: list[Path] = []
    for i, page in enumerate(doc, 1):
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        path = RENDERED / f"page-{i:02d}.pdf.png"
        pix.save(path)
        rendered.append(path)

    thumbs = []
    for path in rendered:
        img = Image.open(path).convert("RGB")
        img.thumbnail((420, 595), Image.Resampling.LANCZOS)
        thumbs.append(ImageOps.expand(img, border=8, fill="#ffffff"))

    cols = 4
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 436, rows * 611), "#e7ebef")
    for idx, img in enumerate(thumbs):
        x = (idx % cols) * 436
        y = (idx // cols) * 611
        sheet.paste(img, (x, y))
    sheet.save(RENDERED / "contact-sheet.png")
    print(f"rendered_pages={len(rendered)}")
    print(RENDERED / "contact-sheet.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
