import unittest

from apps.pdf_to_excel_core.rules.gst_rules import combine_rows


class AccountingRuleTests(unittest.TestCase):
    def test_mixed_gst_rates_remain_separate(self):
        common = {
            "DATE": "01-08-2026",
            "INVOICE NO(Invoice Id).": "SYN-1",
            "GSTIN( from ship to )": "24AAAAA0000A1Z5",
            "TRADE NAME( from Ship To Shiv Jagdamba,)": "Synthetic Buyer",
            "Platform Name(Optional)": "",
            "GSTIN of e-commerce operator ( from  shipped from )": "",
        }
        rows = [
            {**common, "RATE": "3", "TAXABLE": 100.0, "HSN CODE": "7113", "QTY": 2},
            {**common, "RATE": "18", "TAXABLE": 200.0, "HSN CODE": "7326", "QTY": 3},
        ]

        result = combine_rows(rows)

        self.assertEqual({row["RATE"] for row in result}, {"3", "18"})
        self.assertEqual(sum(row["QTY"] for row in result), 5)
        self.assertEqual(sum(row["TAXABLE"] for row in result), 300)
        self.assertEqual(next(row for row in result if row["RATE"] == "18")["HSN CODE"], "73269099")

    def test_zero_taxable_rows_are_ignored_by_default(self):
        self.assertEqual(combine_rows([{"RATE": "18", "TAXABLE": 0, "QTY": 10}]), [])


if __name__ == "__main__":
    unittest.main()
