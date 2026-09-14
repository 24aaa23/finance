"""Regression checks for failures observed in the completed v3 rerun."""
import sqlite3
import unittest

from support import load, registry


class TypedExpressionTests(unittest.TestCase):
    def setUp(self):
        self.math = load("non_llm_operators.math_compute").pre_programmed_math_compute

    def compute(self, expression, data, schema=None):
        result = self.math({"data": data, "input_schema": schema or [], "strict_spec": True,
                            "expression": expression, "output_column": "result"})
        self.assertNotIn("error", result)
        return result["data"]

    def test_text_field_reference_copies_labels_and_nulls(self):
        data = [{"rdfs_label": "Long-term growth"}, {"rdfs_label": None}, {"rdfs_label": "001"}]
        for expression in ["column('rdfs_label')", "rdfs_label"]:
            self.assertEqual([row["result"] for row in self.compute(expression, data)],
                             ["Long-term growth", None, "001"])

    def test_text_coalesce_and_nullif_match_sql(self):
        data = [("", "Fallback"), (None, "Secondary"), ("Primary", "Unused"), (None, None)]
        with sqlite3.connect(":memory:") as db:
            db.execute("CREATE TABLE labels(primary_label TEXT, secondary_label TEXT)")
            db.executemany("INSERT INTO labels VALUES (?, ?)", data)
            expected = [row[0] for row in db.execute(
                "SELECT coalesce(nullif(primary_label, ''), secondary_label, 'Unknown') FROM labels")]
        rows = [{"primary_label": left, "secondary_label": right} for left, right in data]
        actual = self.compute("coalesce(nullif(primary_label, ''), secondary_label, 'Unknown')", rows)
        self.assertEqual([row["result"] for row in actual], expected)

    def test_numeric_strings_are_converted_only_for_arithmetic(self):
        data = [{"left": "12.5", "right": "2"}, {"left": None, "right": "3"}]
        self.assertEqual([row["result"] for row in self.compute("left + right", data)], [14.5, None])
        self.assertEqual([row["result"] for row in self.compute("left", data)], ["12.5", None])

    def test_non_numeric_arithmetic_does_not_concatenate_strings(self):
        for expression in ["a + b", "a * 2", "abs(a)", "-a", "round(a, 2)"]:
            result = self.math({"data": [{"a": "Investor", "b": "Name"}], "expression": expression})
            self.assertIn("Non-numeric", result.get("error", ""))

    def test_all_null_and_zero_divisors_match_sql(self):
        data = [(None, None), (None, 0), (2, 0), (6, 2)]
        with sqlite3.connect(":memory:") as db:
            db.execute("CREATE TABLE amounts(a REAL, b REAL)")
            db.executemany("INSERT INTO amounts VALUES (?, ?)", data)
            expected = [row[0] for row in db.execute("SELECT a / b FROM amounts")]
        actual = self.compute("a / b", [{"a": a, "b": b} for a, b in data])
        self.assertEqual([row["result"] for row in actual], expected)
        self.assertEqual(self.compute("a / b", [{"a": None, "b": None}])[0]["result"], None)

    def test_null_literal_and_empty_typed_relation(self):
        self.assertEqual(self.compute("coalesce(a, None)", [{"a": None}])[0]["result"], None)
        self.assertEqual(self.compute("column('label')", [], ["label"]), [])

    def test_compiled_text_alias_executes_without_numeric_coercion(self):
        spec = {"final_steps": [{"operator": "Math_Compute", "expression": "column('rdfs_label')",
                                 "output_column": "scenario_name"}], "projection": ["scenario_name"]}
        result, log = load("execution").execute_spec(
            spec, {"raw": [{"rdfs_label": "Stressed market"}]}, registry())
        self.assertFalse(load("execution").execution_errors(log))
        self.assertEqual(result, [{"scenario_name": "Stressed market"}])


class ChainedJoinTests(unittest.TestCase):
    def setUp(self):
        self.relational = load("relational")

    def test_three_branches_preserve_colliding_columns_and_sql_multiplicity(self):
        datasets = [[{"key": 1, "subject_iri": "Investor/1"}],
                    [{"key": 1, "subject_iri": "Holding/1"}, {"key": 1, "subject_iri": "Holding/2"}],
                    [{"key": 1, "subject_iri": "Scenario/1"}]]
        result = self.relational.integrate({"branch_data_lists": datasets, "join_key": "key"})
        self.assertNotIn("error", result)
        with sqlite3.connect(":memory:") as db:
            for name, records in zip(["investors", "holdings", "scenarios"], datasets):
                db.execute(f"CREATE TABLE {name}(key INTEGER, subject_iri TEXT)")
                db.executemany(f"INSERT INTO {name} VALUES (?, ?)",
                               [(row["key"], row["subject_iri"]) for row in records])
            expected = list(db.execute("SELECT investors.key, investors.subject_iri, holdings.subject_iri, "
                                       "scenarios.subject_iri FROM investors JOIN holdings USING(key) "
                                       "JOIN scenarios USING(key)"))
        fields = ["key", "subject_iri", "subject_iri_right", "subject_iri_right_2"]
        self.assertEqual(result["output_schema"], fields)
        self.assertEqual([tuple(row[field] for field in fields) for row in result["data"]], expected)

    def test_existing_right_suffix_column_is_preserved(self):
        result = self.relational.integrate({"join_key": "id", "branch_data_lists": [
            [{"id": 1, "name": "Left", "name_right": "Existing"}], [{"id": 1, "name": "Right"}]]})
        self.assertNotIn("error", result)
        self.assertEqual(result["data"], [{"id": 1, "name": "Left", "name_right": "Existing", "name_right_2": "Right"}])

    def test_suffix_allocation_reserves_original_names_from_both_inputs(self):
        left, right, fields = self.relational.join_column_maps(
            ["id", "name"], ["id", "name", "name_right"], ["id"], ["id"])
        self.assertEqual(left, {"id": "id", "name": "name"})
        self.assertEqual(right, {"id": "id", "name": "name_right_2", "name_right": "name_right"})
        self.assertEqual(fields, ["id", "name", "name_right_2", "name_right"])

    def test_empty_outer_join_retains_unique_schema(self):
        fields = ["id", "subject_iri"]
        result = self.relational.integrate({"branch_data_lists": [[], [], [{"id": 1, "subject_iri": "Third"}]],
                                           "branch_schemas": [fields, fields, fields], "join_key": "id", "join_type": "outer"})
        self.assertNotIn("error", result)
        self.assertEqual(result["data"], [{"id": 1, "subject_iri": None,
                                          "subject_iri_right": None, "subject_iri_right_2": "Third"}])

    def test_compiled_chained_join_uses_the_same_output_names(self):
        spec = {"merge_steps": [
            {"operator": "Integrate", "inputs": ["a", "b"], "join_key": "id", "output": "ab"},
            {"operator": "Integrate", "inputs": ["ab", "c"], "join_key": "id", "output": "abc"}],
            "projection": ["id", "subject_iri", "subject_iri_right", "subject_iri_right_2"]}
        datasets = {name: [{"id": 1, "subject_iri": name.upper()}] for name in ["a", "b", "c"]}
        result, log = load("execution").execute_spec(spec, datasets, registry())
        self.assertFalse(load("execution").execution_errors(log))
        self.assertEqual(result, [{"id": 1, "subject_iri": "A",
                                   "subject_iri_right": "B", "subject_iri_right_2": "C"}])


if __name__ == "__main__":
    unittest.main()
