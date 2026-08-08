import sys
import unittest
from pathlib import Path


PDF_CORE = Path(__file__).resolve().parents[2] / "apps" / "pdf_to_excel_core"
sys.path.insert(0, str(PDF_CORE))

from extractor.parsers import detect_template, parse_by_template  # noqa: E402


SUJAL_SYNTHETIC_TEXT = """
Tax Invoice
Invoice No. : 2600000122
Date : 01-08-2026
Bill To
Synthetic Buyer
GSTIN : 24AAAAA0000A1Z5
Ship To
Taxable amount
Item Name
HSN
Quantity
Unit
Unit Price
GST
Amount
1
Synthetic low-rate item
7113
400
PCS
10
120 (3%)
4120
2
Synthetic standard-rate item
7326
20
PCS
20
72 (18%)
472
Total
"""


class PdfToExcelParserTests(unittest.TestCase):
    def test_template_detection(self):
        self.assertEqual(detect_template(SUJAL_SYNTHETIC_TEXT), "sujal_tax_invoice")
        self.assertEqual(
            detect_template("Stock Transfer Invoice\nInvoice Id: ST-1\nCommercial Value\nIGST"),
            "flipkart_stock_transfer",
        )
        self.assertEqual(detect_template("unrecognized document"), "unknown")

    def test_sujal_quantity_and_mixed_gst_regression(self):
        gst_rows, item_rows = parse_by_template(
            "sujal_tax_invoice", SUJAL_SYNTHETIC_TEXT, "synthetic_sujal.txt"
        )

        self.assertEqual(len(item_rows), 2)
        self.assertEqual(sum(row["qty"] for row in item_rows), 420)
        self.assertEqual(sum(row["QTY"] for row in gst_rows), 420)
        self.assertEqual({row["RATE"] for row in gst_rows}, {"3", "18"})
        self.assertEqual(sum(row["TAXABLE"] for row in gst_rows), 4400)

    def test_unknown_template_produces_no_rows(self):
        self.assertEqual(parse_by_template("unknown", "anything", "unknown.txt"), ([], []))


if __name__ == "__main__":
    unittest.main()
