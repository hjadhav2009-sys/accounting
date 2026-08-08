import unittest
import xml.etree.ElementTree as ET

import pandas as pd

from apps.bank_to_tally_xml.engine import build_xml


class XmlWellFormedTests(unittest.TestCase):
    def test_special_characters_are_escaped_and_xml_is_well_formed(self):
        df = pd.DataFrame([{
            "Txn Date": "01/08/2026",
            "Description": "A & B <transfer>",
            "Mapped Ledger": "Sales & Returns",
            "Deposit": 10,
            "Withdrawal": 0,
        }])
        xml = build_xml(df, {"bank_ledger": "Bank & Co", "voucher_number_prefix": "T-"})
        ET.fromstring(xml)
        self.assertIn("A &amp; B &lt;transfer&gt;", xml)


if __name__ == "__main__":
    unittest.main()
