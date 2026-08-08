import unittest

import pandas as pd

from apps.bank_to_tally_xml.engine import build_xml, group_pattern_from_description, map_ledger


class BankEngineTests(unittest.TestCase):
    def test_narration_grouping_removes_transaction_ids(self):
        self.assertEqual(group_pattern_from_description("UPI/123456/MERCHANT NAME"), "MERCHANT NAME")
        self.assertEqual(group_pattern_from_description("NEFT-ABC123- CUSTOMER NAME"), "CUSTOMER NAME")

    def test_blank_pattern_never_matches(self):
        payload = {"settings": {"unmatched_ledger": "Suspense"}, "rules": [{"narration_pattern": "", "ledger": "Wrong"}]}
        self.assertEqual(map_ledger("anything", payload), ("Suspense", "UNMATCHED_TO_SUSPENSE"))

    def test_receipt_and_payment_xml_entries_balance(self):
        df = pd.DataFrame([
            {"Txn Date": "01/08/2026", "Description": "Receipt", "Mapped Ledger": "Sales", "Deposit": 100, "Withdrawal": 0},
            {"Txn Date": "02/08/2026", "Description": "Payment", "Mapped Ledger": "Expense", "Deposit": 0, "Withdrawal": 40},
        ])
        xml = build_xml(df, {"bank_ledger": "Test Bank", "voucher_number_prefix": "BANK-"})

        self.assertIn('<VOUCHER VCHTYPE="Receipt"', xml)
        self.assertIn('<VOUCHER VCHTYPE="Payment"', xml)
        self.assertIn("<VOUCHERNUMBER>BANK-0001</VOUCHERNUMBER>", xml)
        self.assertIn("<AMOUNT>100.00</AMOUNT>", xml)
        self.assertIn("<AMOUNT>-100.00</AMOUNT>", xml)
        self.assertIn("<AMOUNT>-40.00</AMOUNT>", xml)
        self.assertIn("<AMOUNT>40.00</AMOUNT>", xml)


if __name__ == "__main__":
    unittest.main()
