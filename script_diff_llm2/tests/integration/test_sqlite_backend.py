import unittest

from script_diff_llm.config.paths import default_sqlite_db_path


class SqliteBackendIntegrationTest(unittest.TestCase):
    def test_sqlite_db_contains_expected_atom_tables(self):
        import sqlite3

        conn = sqlite3.connect(default_sqlite_db_path())
        try:
            rows = conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table' AND name LIKE 'ATOM_%'
                ORDER BY name
                """
            ).fetchall()
        finally:
            conn.close()
        tables = [row[0] for row in rows]
        self.assertEqual(len(tables), 8)
        self.assertIn("ATOM_ENTITY_INVESTOR_PROFILE_001", tables)
        self.assertIn("ATOM_EVENT_CASH_FLOW_001", tables)


if __name__ == "__main__":
    unittest.main()

