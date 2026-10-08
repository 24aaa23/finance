"""Exercise real SQLite reads and read-only/timeout boundaries without API calls."""

import hashlib
from contextlib import closing
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("_sqlite_backend_tests", SOURCE / "sqlite_backend.py")
backend = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backend)


class SQLiteBackendTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.db = Path(self.directory.name) / "test # database.db"
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.executescript('''
                CREATE TABLE records (record_id TEXT, value REAL, note TEXT);
                INSERT INTO records VALUES ('duplicate', 1.5, NULL), ('duplicate', 1.5, NULL), ('other', NULL, 'text');
                CREATE TABLE parent (id INTEGER PRIMARY KEY, label TEXT UNIQUE);
                CREATE TABLE child (a TEXT NOT NULL, b INTEGER, parent_id INTEGER REFERENCES parent(id), UNIQUE(a,b));
                CREATE UNIQUE INDEX partial_key ON records(record_id) WHERE record_id = 'other';
            ''')

    def tearDown(self):
        self.directory.cleanup()

    def test_rows_preserve_duplicates_null_and_native_scalar_types(self):
        sql = 'SELECT record_id, value, note, 7 AS integer_value FROM records ORDER BY rowid'
        result = backend.execute_sql_on_sqlite(sql, self.db)
        self.assertEqual(result["status"], "success", result)
        self.assertEqual(result["row_count"], 3)
        self.assertEqual(result["data"][0], result["data"][1])
        self.assertIsNone(result["data"][0]["note"])
        self.assertIsNone(result["data"][2]["value"])
        self.assertIsInstance(result["data"][0]["value"], float)
        self.assertIsInstance(result["data"][0]["integer_value"], int)
        self.assertEqual(result["sql"], result["sparql"])

    def test_schema_reports_only_declared_keys(self):
        schema = backend.load_sqlite_schema(self.db)
        self.assertEqual(schema["records"]["primary_keys"], [])
        self.assertEqual(schema["records"]["unique_keys"], [])
        self.assertEqual(schema["parent"]["primary_keys"], ["id"])
        self.assertIn(["label"], schema["parent"]["unique_keys"])
        self.assertIn(["a", "b"], schema["child"]["unique_keys"])
        self.assertEqual(schema["child"]["foreign_keys"][0]["target_table"], "parent")
        self.assertEqual(schema["child"]["foreign_keys"][0]["columns"], ["parent_id"])
        columns = {column["name"]: column for column in schema["records"]["columns"]}
        self.assertEqual(columns["value"]["datatype"], "numeric")
        self.assertEqual(columns["note"]["datatype"], "categorical_string")
        self.assertTrue(columns["note"]["nullable"])
        self.assertFalse(schema["child"]["columns"][0]["nullable"])

    def test_generated_sql_cannot_mutate_or_attach(self):
        initial_hash = hashlib.sha256(self.db.read_bytes()).hexdigest()
        attacks = [
            "DELETE FROM records", "UPDATE records SET value=99", "DROP TABLE records",
            "CREATE TABLE extra (a)", "CREATE TEMP TABLE extra (a)",
            "INSERT INTO records VALUES ('new', 2, 'bad') RETURNING *",
            "WITH x AS (SELECT 1) DELETE FROM records RETURNING *",
            "PRAGMA query_only=OFF", "PRAGMA writable_schema=ON", "PRAGMA table_info(records)",
            "ATTACH DATABASE ':memory:' AS extra", "VACUUM", "BEGIN", "COMMIT",
            "SELECT load_extension('nonexistent')", "SELECT writefile('bad', 'bad')",
            "SELECT * FROM records; DELETE FROM records", "SELECT * FROM pragma_table_info('records')",
        ]
        for sql in attacks:
            with self.subTest(sql=sql):
                result = backend.execute_sql_on_sqlite(sql, self.db)
                self.assertEqual(result["status"], "error", result)
                self.assertEqual(result["failed_sql"], result["failed_sparql"])
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), initial_hash)

    def test_validation_compiles_without_executing_and_times_out_execution(self):
        sql = "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n) SELECT sum(x) FROM n"
        validation = backend.validate_sql_on_sqlite(sql, self.db, timeout_seconds=0.1)
        self.assertTrue(validation["is_valid"], validation)
        result = backend.execute_sql_on_sqlite(sql, self.db, timeout_seconds=0.02)
        self.assertEqual(result["status"], "error", result)
        self.assertIn("timed out", result["error_message"])
        self.assertEqual(result["timeout_seconds"], 0.02)
        self.assertEqual(backend.execute_sql_on_sqlite("SELECT COUNT(*) AS n FROM records", self.db)["data"], [{"n": 3}])

    def test_validation_rejects_unknown_schema_and_writes(self):
        for sql in ("SELECT missing FROM records", "SELECT * FROM absent", "DELETE FROM records", "PRAGMA query_only=OFF"):
            with self.subTest(sql=sql):
                self.assertFalse(backend.validate_sql_on_sqlite(sql, self.db)["is_valid"])

    def test_missing_database_is_not_created(self):
        missing = Path(self.directory.name) / "missing.db"
        self.assertEqual(backend.execute_sql_on_sqlite("SELECT 1", missing)["status"], "error")
        with self.assertRaises(RuntimeError):
            backend.check_sqlite_health(missing)
        self.assertFalse(missing.exists())

    def test_comments_and_literals_are_not_mistaken_for_commands(self):
        result = backend.execute_sql_on_sqlite("/* DELETE FROM records */ SELECT 'DROP TABLE records; --' AS note", self.db)
        self.assertEqual(result["status"], "success", result)
        self.assertEqual(result["data"], [{"note": "DROP TABLE records; --"}])

    def test_duplicate_output_names_cannot_silently_lose_columns(self):
        result = backend.execute_sql_on_sqlite("SELECT 1 AS value, 2 AS value", self.db)
        self.assertEqual(result["status"], "error")
        self.assertIn("unique alias", result["error_message"])

    def test_requested_database_schema_and_counts_without_mutation(self):
        db = SOURCE.parents[1] / "experiment_week1" / "improvement6" / "wealth_management_diverse.db"
        self.assertTrue(db.is_file(), f"Requested database is missing: {db}")
        digest = hashlib.sha256(db.read_bytes()).hexdigest()
        backend.check_sqlite_health(db)
        expected = {
            "ATOM_ENTITY_INVESTOR_PROFILE_001": 1550,
            "ATOM_ENTITY_PORTFOLIO_HEALTH_001": 1550,
            "ATOM_EVENT_REBALANCING_ACTION_001": 6192,
            "ATOM_EVENT_SCENARIO_REBALANCING_001": 1549,
            "ATOM_ENTITY_PORTFOLIO_HOLDING_001": 15102,
            "ATOM_ENTITY_SECTOR_ALLOCATION_001": 3038,
            "ATOM_ENTITY_INVESTMENT_GOAL_001": 4865,
            "ATOM_EVENT_CASH_FLOW_001": 7828,
        }
        schema = backend.load_sqlite_schema(db)
        self.assertEqual(set(schema), set(expected))
        for table, count in expected.items():
            self.assertEqual(schema[table]["primary_keys"], [])
            self.assertEqual(schema[table]["unique_keys"], [])
            self.assertEqual(schema[table]["backend"], "sqlite")
            result = backend.execute_sql_on_sqlite(f'SELECT COUNT(*) AS n FROM "{table}"', db)
            self.assertEqual(result["data"], [{"n": count}])
        self.assertEqual(hashlib.sha256(db.read_bytes()).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main()
