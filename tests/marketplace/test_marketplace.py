import unittest
from unittest.mock import patch

import pandas as pd

from apps.marketplace_pdf_to_tally.engine import build_xml, detect_doc_type, detect_platform


def row(doc_type="Tax Invoice", voucher_type="Purchase"):
    return {
        "Source PDF": "synthetic.pdf",
        "Platform": "amazon",
        "PDF Doc Type": doc_type,
        "Tally Voucher Type": voucher_type,
        "Invoice No": "INV-1",
        "Date": "20260801",
        "Mapped Ledger": "Synthetic Expense",
        "Taxable": 100.0,
        "CGST": 9.0,
        "SGST": 9.0,
        "IGST": 0.0,
        "Total": 118.0,
        "Status": "OK",
        "Import?": True,
    }


class MarketplaceTests(unittest.TestCase):
    def test_supplier_detection_specificity(self):
        self.assertEqual(detect_platform("MEESHO LIMITED", "invoice.pdf"), "meesho_limited")
        self.assertEqual(detect_platform("MEESHO TECHNOLOGIES PRIVATE LIMITED", "invoice.pdf"), "meesho_technologies")
        self.assertEqual(detect_platform("VALMO TRANSPORTATION PRIVATE LIMITED", "invoice.pdf"), "valmo")
        self.assertEqual(detect_platform("", "ADS-2627-20220.pdf"), "amazon")

    def test_credit_note_detection(self):
        self.assertEqual(detect_doc_type("Marketplace Credit Note"), "Credit Note")
        self.assertEqual(detect_doc_type("Marketplace Tax Invoice"), "Tax Invoice")

    @patch("apps.marketplace_pdf_to_tally.engine.db.voucher_rule")
    @patch("apps.marketplace_pdf_to_tally.engine.db.party_ledger")
    @patch("apps.marketplace_pdf_to_tally.engine.db.company")
    def test_purchase_xml_preserves_reference_and_balances(self, company, party, rule):
        company.return_value = {"tally_company_name": "Test Books", "cgst_ledger": "CGST", "sgst_ledger": "SGST", "igst_ledger": "IGST"}
        party.return_value = "Known Amazon Party"
        rule.return_value = {"tally_voucher_type": "Purchase", "sign_mode": "charge"}

        xml = build_xml(pd.DataFrame([row()]), "Test Company", export_review=False)

        self.assertIn("<VOUCHERTYPENAME>Purchase</VOUCHERTYPENAME>", xml)
        self.assertIn("<VOUCHERNUMBER>INV-1</VOUCHERNUMBER>", xml)
        self.assertIn("<REFERENCE>INV-1</REFERENCE>", xml)
        self.assertIn("<PARTYLEDGERNAME>Known Amazon Party</PARTYLEDGERNAME>", xml)
        self.assertIn("<AMOUNT>118.00</AMOUNT>", xml)
        self.assertIn("<AMOUNT>-100.00</AMOUNT>", xml)

    @patch("apps.marketplace_pdf_to_tally.engine.db.voucher_rule")
    @patch("apps.marketplace_pdf_to_tally.engine.db.party_ledger")
    @patch("apps.marketplace_pdf_to_tally.engine.db.company")
    def test_credit_note_generates_debit_note_signs(self, company, party, rule):
        company.return_value = {"tally_company_name": "Test Books"}
        party.return_value = "Known Amazon Party"
        rule.return_value = {"tally_voucher_type": "Debit Note", "sign_mode": "reverse"}

        xml = build_xml(pd.DataFrame([row("Credit Note", "Debit Note")]), "Test Company")

        self.assertIn("<VOUCHERTYPENAME>Debit Note</VOUCHERTYPENAME>", xml)
        self.assertIn("<AMOUNT>-118.00</AMOUNT>", xml)
        self.assertIn("<AMOUNT>100.00</AMOUNT>", xml)

    @patch("apps.marketplace_pdf_to_tally.engine.db.voucher_rule", return_value={"tally_voucher_type": "Purchase", "sign_mode": "charge"})
    @patch("apps.marketplace_pdf_to_tally.engine.db.party_ledger", return_value="Suspense")
    @patch("apps.marketplace_pdf_to_tally.engine.db.company", return_value={"tally_company_name": "Test Books"})
    def test_known_platform_with_suspense_party_is_blocked(self, *_):
        xml = build_xml(pd.DataFrame([row()]), "Test Company")
        self.assertNotIn("<VOUCHER ", xml)


if __name__ == "__main__":
    unittest.main()
