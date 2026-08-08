from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class PDFPage:
    page_no: int
    text: str


@dataclass
class PDFDocument:
    filename: str
    pages: List[PDFPage]

    @property
    def full_text(self) -> str:
        return "\n".join(page.text for page in self.pages)


def read_pdf(path: str | Path) -> PDFDocument:
    """Read PDF text using PyMuPDF. PyMuPDF package imports as fitz."""
    try:
        import fitz  # PyMuPDF
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "PyMuPDF is missing. Install it with: python -m pip install PyMuPDF"
        ) from exc

    path = Path(path)
    pages: List[PDFPage] = []
    with fitz.open(str(path)) as doc:
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text") or ""
            pages.append(PDFPage(page_no=i, text=text))
    return PDFDocument(filename=path.name, pages=pages)
