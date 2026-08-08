import gc
import tempfile
import unittest
from pathlib import Path

from shared import database as db


class DatabaseRuleTests(unittest.TestCase):
    def setUp(self):
        self._old_path = db.DB_PATH
        self._temp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self._temp.name) / "business_rules.test.db"
        db.reset_db_cache()
        db.init_db(force=True)
        db.save_company({"name": "Test Company", "tally_company_name": "Test Books"})

    def tearDown(self):
        db.DB_PATH = self._old_path
        db.reset_db_cache()
        # sqlite3.Connection context managers commit/rollback but do not close.
        # Collect leaked temporary connections before Windows removes the fixture.
        gc.collect()
        self._temp.cleanup()

    def test_company_lookup_normalizes_surrounding_whitespace(self):
        self.assertEqual(db.company("  Test   Company ")["tally_company_name"], "Test Books")

    def test_party_lookup_normalizes_newlines_case_and_tabs(self):
        db.upsert_party_ledger("Test Company", " Amazon\n", "Known Amazon Party\n")
        self.assertEqual(db.party_ledger("Test Company", "AMAZON\t"), "Known Amazon Party")

    def test_known_party_never_becomes_suspense(self):
        for platform in ("amazon", "flipkart", "meesho", "myntra", "valmo"):
            self.assertNotEqual(db.party_ledger("Test Company", platform).lower(), "suspense")

    def test_all_supported_match_types_and_company_precedence(self):
        rows = [
            {"tool": "bank", "platform": "", "pattern": "EXACT PAYMENT", "ledger": "Equals Ledger", "match_type": "equals"},
            {"tool": "bank", "platform": "", "pattern": "PREFIX", "ledger": "Starts Ledger", "match_type": "starts_with"},
            {"tool": "bank", "platform": "", "pattern": r"INV-\d{4}", "ledger": "Regex Ledger", "match_type": "regex"},
            {"tool": "bank", "platform": "", "pattern": "market", "ledger": "Contains Ledger", "match_type": "smart_contains"},
        ]
        db.replace_table("ledger_mappings", "Test Company", rows)

        self.assertEqual(db.map_ledger("Test Company", "bank", "", "EXACT PAYMENT")[0], "Equals Ledger")
        self.assertEqual(db.map_ledger("Test Company", "bank", "", "PREFIX transfer")[0], "Starts Ledger")
        self.assertEqual(db.map_ledger("Test Company", "bank", "", "reference INV-1234")[0], "Regex Ledger")
        self.assertEqual(db.map_ledger("Test Company", "bank", "", "market settlement")[0], "Contains Ledger")

    def test_blank_mapping_is_not_saved(self):
        before = len(db.df_table("ledger_mappings", "Test Company"))
        db.add_mapping("Test Company", "bank", "", " \n\t ", "Some Ledger")
        after = len(db.df_table("ledger_mappings", "Test Company"))
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
