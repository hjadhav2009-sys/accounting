from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pandas as pd


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PDF_CORE_ROOT = REPOSITORY_ROOT / "apps" / "pdf_to_excel_core"


@contextmanager
def _pdf_core_import_path() -> Iterator[None]:
    original = list(sys.path)
    try:
        sys.path.insert(0, str(PDF_CORE_ROOT))
        yield
    finally:
        sys.path[:] = original


class LegacyPdfToExcelService:
    def parse_text(
        self,
        template: str,
        text: str,
        source_file: str,
        force_18_hsn: str = "73269099",
        ignore_zero_taxable: bool = True,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        with _pdf_core_import_path():
            from extractor.parsers import parse_by_template

            return parse_by_template(template, text, source_file, force_18_hsn, ignore_zero_taxable)


class LegacyMarketplaceService:
    def parse_pdf(self, path: str | Path, company: str, original_name: str | None = None) -> pd.DataFrame:
        from apps.marketplace_pdf_to_tally.engine import parse_marketplace_pdf

        return parse_marketplace_pdf(path, company, original_name)

    def build_xml(self, rows: pd.DataFrame, company: str, export_review: bool = False) -> str:
        from apps.marketplace_pdf_to_tally.engine import build_xml

        return build_xml(rows, company, export_review=export_review)


class LegacyBankStatementService:
    def load(self, path: str | Path):
        from apps.bank_to_tally_xml.engine import load_statement

        return load_statement(path)

    def build_xml(self, rows: pd.DataFrame, settings: dict[str, Any]) -> str:
        from apps.bank_to_tally_xml.engine import build_xml

        return build_xml(rows, settings)


class LegacyTallyXmlService:
    def __init__(self) -> None:
        self.marketplace = LegacyMarketplaceService()
        self.bank = LegacyBankStatementService()


class LegacyExcelExportService:
    def export(self, rows: list[dict[str, Any]], item_rows: list[dict[str, Any]], output_path: str | Path) -> Path:
        with _pdf_core_import_path():
            from rules.excel_rules import export_excel

            return export_excel(rows, item_rows, output_path)
