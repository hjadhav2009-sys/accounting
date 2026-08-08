import tempfile
import unittest
from pathlib import Path

import pandas as pd

from tests.parsers.test_pdf_to_excel_parsers import SUJAL_SYNTHETIC_TEXT
from extractor.parsers import parse_by_template
from apps.pdf_to_excel_core.rules.excel_rules import OUTPUT_COLUMNS, export_excel


class ExcelExportTests(unittest.TestCase):
    def test_export_has_stable_columns_and_sheets(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "synthetic.xlsx"
            export_excel([{"DATE": "01-08-2026", "RATE": "18", "TAXABLE": 100, "QTY": 1}], [{"description": "Synthetic"}], out)
            sheets = pd.read_excel(out, sheet_name=None)

        self.assertEqual(list(sheets["GST Data"].columns), OUTPUT_COLUMNS)
        self.assertIn("Item Details", sheets)

    def test_parser_to_excel_preserves_numeric_quantity_and_gst_buckets(self):
        gst_rows, item_rows = parse_by_template(
            "sujal_tax_invoice", SUJAL_SYNTHETIC_TEXT, "synthetic_sujal.txt"
        )
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "synthetic_golden.xlsx"
            export_excel(gst_rows, item_rows, out)
            exported = pd.read_excel(out, sheet_name="GST Data")

        self.assertTrue(pd.api.types.is_numeric_dtype(exported["TAXABLE"]))
        self.assertTrue(pd.api.types.is_numeric_dtype(exported["QTY"]))
        self.assertEqual(set(exported["RATE"]), {3, 18})
        self.assertEqual(float(exported["QTY"].sum()), 420.0)
        self.assertEqual(float(exported["TAXABLE"].sum()), 4400.0)


if __name__ == "__main__":
    unittest.main()
