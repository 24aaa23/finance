"""Exercise deterministic SQL retrieval against SQLite, without LLM calls."""
import sqlite3
import unittest

from support import load

raw_sql = load("raw_sql")


class RawSqlTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.execute('CREATE TABLE observations (id INTEGER, name TEXT, amount REAL, at TEXT)')
        self.db.executemany('INSERT INTO observations VALUES (?, ?, ?, ?)', [
            (1, "O'Brien -- /* literal */", 1.5, "2025-01-01"),
            (1, "O'Brien -- /* literal */", 1.5, "2025-01-01"),
            (2, None, 2.5, "2025-02-01"),
            (3, "100%_literal", None, "2025-03-01"),
            (4, "other", -3, None),
        ])
        self.schema = {"observations": {
            "backend": "sqlite", "sql_table": "observations", "primary_keys": [],
            "columns": [{"name": name, "datatype": kind} for name, kind in
                        [("id", "integer"), ("name", "text"), ("amount", "numeric"), ("at", "date")]],
        }}

    def query(self, filters=None, **kwargs):
        return raw_sql.render_raw_sql({"class": "observations", "fields": ["id", "name", "amount", "at"],
                                       "optional_fields": ["name", "amount", "at"], "filters": filters or [], **kwargs}, self.schema)

    def ids(self, filters):
        return [row[0] for row in self.db.execute(self.query(filters))]

    def test_projection_preserves_duplicates_and_nulls_with_exact_aliases(self):
        cursor = self.db.execute(self.query())
        self.assertEqual([column[0] for column in cursor.description], ["id", "name", "amount", "at"])
        rows = cursor.fetchall()
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0], rows[1])
        self.assertIsNone(rows[2][1])
        self.assertIsNone(rows[3][2])

    def test_escaped_literals_cannot_change_the_query(self):
        self.assertEqual(self.ids([{"field": "name", "value": "O'Brien -- /* literal */"}]), [1, 1])
        self.assertEqual(self.ids([{"field": "name", "value": "x' OR 1=1 --"}]), [])
        self.assertEqual(self.ids([{"field": "name", "operator": "contains", "value": "%_"}]), [3])

    def test_null_comparisons_and_three_valued_not(self):
        self.assertEqual(self.ids([{"field": "name", "operator": "=", "value": None}]), [2])
        self.assertEqual(self.ids([{"field": "name", "operator": "!=", "value": None}]), [1, 1, 3, 4])
        self.assertEqual(self.ids([{"not": {"field": "amount", "value": 1.5}}]), [2, 4])
        self.assertEqual(self.ids([{"field": "amount", "operator": "not in", "value": [1.5, None]}]), [])
        self.assertEqual(self.ids([{"field": "amount", "operator": "in", "value": [1.5, None]}]), [1, 1])

    def test_numeric_date_and_empty_set_filters(self):
        self.assertEqual(self.ids([{"field": "amount", "operator": "between", "value": ["1.5", "2.5"]}]), [1, 1, 2])
        self.assertEqual(self.ids([{"field": "at", "operator": ">=", "value": "2025-02-01"}]), [2, 3])
        self.assertEqual(self.ids([{"field": "amount", "operator": "<", "value": "-2.5"}]), [4])
        self.assertEqual(self.ids([{"field": "amount", "operator": "in", "value": []}]), [])
        self.assertEqual(self.ids([{"field": "amount", "operator": "not_in", "value": []}]), [1, 1, 2, 3, 4])

    def test_nested_and_or_not_and_explicit_logic(self):
        filters = [{"all": [
            {"any": [{"field": "name", "operator": "is_null"}, {"field": "amount", "operator": "<", "value": 0}]},
            {"not": {"field": "id", "value": 4}},
        ]}]
        self.assertEqual(self.ids(filters), [2])
        for key in ("conditions", "filters"):
            self.assertEqual(self.ids([{key: [{"field": "id", "value": 2}, {"field": "id", "value": 3}], "logic": "or"}]), [2, 3])

    def test_invalid_names_and_nonfinite_numbers_fail_closed(self):
        for changes in ({"class": "Observations"}, {"class": "observations; DROP TABLE observations"},
                        {"fields": ["missing"]}, {"fields": ["COUNT(*)"]},
                        {"optional_fields": ["missing"]}, {"entity_key": ["missing"]}, {"limit": 1}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.query(**changes)
        for value in (float("nan"), float("inf"), "NaN", "Infinity", "1e999", "1 OR 1=1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.query([{"field": "amount", "value": value}])
        for item in ({"field": "missing", "value": 1}, {"field": "name", "value": "a\x00b"},
                     {"field": "id", "operator": "like", "value": "%"}, {"any": []},
                     {"field": "id", "operator": "in", "value": "branch_1"}):
            with self.subTest(item=item), self.assertRaises(ValueError):
                self.query([item])

    def test_exact_schema_names_can_contain_quotes_or_spaces(self):
        self.db.execute('CREATE TABLE "weird table" ("say""hi" TEXT)')
        self.db.execute('INSERT INTO "weird table" VALUES (?)', ("safe",))
        schema = {"weird table": {"backend": "sqlite", "sql_table": "weird table", "columns": [{"name": 'say"hi'}]}}
        query = raw_sql.render_raw_sql({"class": "weird table", "fields": ['say"hi']}, schema)
        self.assertEqual(self.db.execute(query).fetchall(), [("safe",)])

    def test_canonical_tokens_ignore_only_whitespace_comments_keyword_case(self):
        query = self.query([{"field": "name", "value": "O'Brien -- /* literal */"}])
        formatted = query.replace("SELECT", "select\n/* comment */").replace(" FROM ", "\nfrom -- comment\n")
        self.assertEqual(raw_sql.canonical_sql_tokens(query), raw_sql.canonical_sql_tokens(formatted))
        self.assertNotEqual(raw_sql.canonical_sql_tokens(query), raw_sql.canonical_sql_tokens(query.replace("Brien", "BRIEN")))
        self.assertNotEqual(raw_sql.canonical_sql_tokens(query), raw_sql.canonical_sql_tokens(query.replace('"name"', '"Name"')))
        self.assertNotEqual(raw_sql.canonical_sql_tokens(query), raw_sql.canonical_sql_tokens(query + "; DELETE FROM observations"))
        for text in ("SELECT 'unclosed", 'SELECT "unclosed', "SELECT /* unclosed", "SELECT @parameter", "SELECT \x00"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                raw_sql.canonical_sql_tokens(text)


if __name__ == "__main__":
    unittest.main()
