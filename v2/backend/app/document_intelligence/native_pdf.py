from __future__ import annotations

import re
from decimal import Decimal

from .models import (
    BoundingBox, DocumentPage, ErrorCode, ExtractedTable, ExtractionMethod,
    ExtractionQuality, ImageRegion, QualityAssessment, TableCell, TableRow,
    TextBlock, TextSpan,
)
from .security import DocumentSecurityError, ResourceLimits


def _box(values, width: float, height: float) -> BoundingBox:
    x0, y0, x1, y1 = (max(0.0, float(value)) for value in values)
    return BoundingBox(min(x0, width), min(y0, height), min(x1, width), min(y1, height), width, height)


class NativePdfExtractor:
    engine = "PyMuPDF"

    def extract(self, content: bytes, limits: ResourceLimits = ResourceLimits()) -> tuple[DocumentPage, ...]:
        import pymupdf

        try:
            document = pymupdf.open(stream=content, filetype="pdf")
        except Exception as exc:
            raise DocumentSecurityError(ErrorCode.PDF_CORRUPT, "PDF cannot be opened safely") from exc
        try:
            if document.needs_pass:
                raise DocumentSecurityError(ErrorCode.PDF_PASSWORD_PROTECTED, "PDF requires a password")
            if document.page_count > limits.maximum_pages:
                raise DocumentSecurityError(ErrorCode.PAGE_LIMIT_EXCEEDED, "PDF exceeds the configured page limit")
            pages: list[DocumentPage] = []
            for page_index, page in enumerate(document, start=1):
                width, height = float(page.rect.width), float(page.rect.height)
                page_dict = page.get_text("dict", sort=True)
                blocks: list[TextBlock] = []
                images: list[ImageRegion] = []
                reading_order = 0
                for raw_block in page_dict.get("blocks", []):
                    if raw_block.get("type") == 1:
                        if raw_block.get("bbox"):
                            images.append(ImageRegion(_box(raw_block["bbox"], width, height), len(images)))
                        continue
                    spans: list[TextSpan] = []
                    lines: list[str] = []
                    for line in raw_block.get("lines", []):
                        line_parts: list[str] = []
                        for span in line.get("spans", []):
                            text = str(span.get("text") or "")
                            if not text:
                                continue
                            spans.append(TextSpan(text, _box(span["bbox"], width, height), str(span.get("font") or ""),
                                                  float(span.get("size") or 0), int(span.get("flags") or 0), reading_order))
                            reading_order += 1
                            line_parts.append(text)
                        if line_parts:
                            lines.append("".join(line_parts))
                    block_text = "\n".join(lines)
                    if block_text and raw_block.get("bbox"):
                        blocks.append(TextBlock(block_text, _box(raw_block["bbox"], width, height), tuple(spans), len(blocks)))
                tables: list[ExtractedTable] = []
                try:
                    finder = page.find_tables()
                    for table_index, table in enumerate(finder.tables):
                        extracted = table.extract()
                        rows = tuple(TableRow(row_index, tuple(TableCell(str(value or ""), row_index, column_index)
                                                                    for column_index, value in enumerate(row)))
                                     for row_index, row in enumerate(extracted))
                        tables.append(ExtractedTable(table_index, rows, _box(table.bbox, width, height)))
                except Exception:
                    # Table detection is optional evidence; text blocks remain authoritative input.
                    pass
                text = page.get_text("text", sort=True) or ""
                pages.append(DocumentPage(page_index, width, height, text, tuple(blocks), tuple(tables), tuple(images)))
            return tuple(pages)
        finally:
            document.close()


class ExtractionQualityAssessor:
    def assess(self, pages: tuple[DocumentPage, ...]) -> QualityAssessment:
        page_count = max(1, len(pages))
        text = "\n".join(page.text for page in pages)
        characters = len(text.strip())
        blank_pages = sum(not page.text.strip() for page in pages)
        numeric_tokens = len(re.findall(r"(?<!\w)[+-]?[\d,]+(?:\.\d+)?%?", text))
        tokens = max(1, len(re.findall(r"\S+", text)))
        garbled = text.count("\ufffd") + sum(1 for char in text if ord(char) < 32 and char not in "\n\r\t")
        short_lines = sum(1 for line in text.splitlines() if 0 < len(line.strip()) <= 2)
        lines = max(1, len([line for line in text.splitlines() if line.strip()]))
        page_area = sum(page.width * page.height for page in pages) or Decimal("1")
        block_area = sum((block.bounding_box.x1 - block.bounding_box.x0) * (block.bounding_box.y1 - block.bounding_box.y0)
                         for page in pages for block in page.blocks)
        density = Decimal(characters) / Decimal(page_count)
        blank_ratio = Decimal(blank_pages) / Decimal(page_count)
        numeric_density = Decimal(numeric_tokens) / Decimal(tokens)
        garbled_ratio = Decimal(garbled) / Decimal(max(1, len(text)))
        fragmentation = Decimal(short_lines) / Decimal(lines)
        coverage = min(Decimal("1"), Decimal(str(block_area)) / Decimal(str(page_area)))
        signals: list[str] = []
        if characters < 20 * page_count:
            signals.append("very_low_text")
        if blank_ratio >= Decimal("0.5"):
            signals.append("many_blank_pages")
        if garbled_ratio > Decimal("0.02"):
            signals.append("garbled_text")
        if fragmentation > Decimal("0.4"):
            signals.append("fragmented_lines")
        if "very_low_text" in signals or "many_blank_pages" in signals:
            status = ExtractionQuality.OCR_REQUIRED
        elif signals or density < 50:
            status = ExtractionQuality.DEGRADED
        else:
            status = ExtractionQuality.GOOD
        return QualityAssessment(status, characters, density, blank_ratio, numeric_density,
                                 garbled_ratio, fragmentation, coverage, tuple(signals))
