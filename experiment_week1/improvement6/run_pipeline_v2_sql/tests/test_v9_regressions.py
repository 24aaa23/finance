"""Independent SQL/RDF witnesses for failures diagnosed in the saved V7 run."""
import copy
import sqlite3
import tempfile
from pathlib import Path
import unittest

import rdflib

from support import FakeClient, load, registry


class V9OperatorTests(unittest.TestCase):
    def execute(self, rows, steps, fields=None):
        schema = fields or list(rows[0])
        plan = load("spec_runtime").compile_spec({"final_steps": steps}, {"raw": schema})
        self.assertFalse(plan["contract_errors"], plan["contract_errors"])
        data, log = load("execution").execute_spec(plan, {"raw": rows}, registry(), dataset_schemas={"raw": schema})
        self.assertFalse(load("execution").execution_errors(log), log)
        return data, log

    def test_conditional_totals_match_sql_without_losing_entities(self):
        rows = [{"owner": "a", "amount": 10}, {"owner": "a", "amount": -3},
                {"owner": "b", "amount": -7}, {"owner": "c", "amount": None}, {"owner": "d", "amount": 0}]
        actual, _ = self.execute(rows, [
            {"operator": "Math_Compute", "expression": "where(amount > 0, amount, 0)", "output_column": "positive"},
            {"operator": "Math_Compute", "expression": "where(amount < 0, -amount, 0)", "output_column": "negative"},
            {"operator": "Filter_Aggregate", "group_by": ["owner"], "aggregations": [
                {"operation": "sum", "input_column": "positive", "output_column": "inflow"},
                {"operation": "sum", "input_column": "negative", "output_column": "outflow"}]}])
        with sqlite3.connect(":memory:") as db:
            db.execute("create table f(owner, amount)")
            db.executemany("insert into f values (?, ?)", [(r["owner"], r["amount"]) for r in rows])
            expected = [dict(zip(["owner", "inflow", "outflow"], r)) for r in db.execute(
                "select owner, sum(case when amount > 0 then amount else 0 end), sum(case when amount < 0 then -amount else 0 end) from f group by owner")]
        self.assertCountEqual(actual, expected)

    def test_conditionals_have_sql_null_and_boolean_semantics(self):
        rows = [{"n": None, "kind": "A"}, {"n": 1, "kind": None}, {"n": 3, "kind": "A"}, {"n": 8, "kind": "B"}]
        actual, _ = self.execute(rows, [{"operator": "Math_Compute", "expression": "where(not (n > 2 and kind == 'A'), 'yes', 'no')", "output_column": "flag"}])
        with sqlite3.connect(":memory:") as db:
            db.execute("create table f(n, kind)")
            db.executemany("insert into f values (?, ?)", [(r["n"], r["kind"]) for r in rows])
            expected = [r[0] for r in db.execute("select case when not (n > 2 and kind = 'A') then 'yes' else 'no' end from f")]
        self.assertEqual([r["flag"] for r in actual], expected)

    def test_conditional_empty_and_all_null_inputs(self):
        steps = [{"operator": "Math_Compute", "expression": "where(n > 0, n, 0)", "output_column": "v"}]
        self.assertEqual(self.execute([], steps, ["n"])[0], [])
        self.assertEqual(self.execute([{"n": None}], steps)[0], [{"n": None, "v": 0}])

    def test_conditional_language_still_rejects_python_execution(self):
        for expression in ("__import__('os')", "n.__class__", "[x for x in n]", "where(n, 1)"):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                load("non_llm_operators.math_compute").expression_columns(expression)

    def test_null_presence_mistake_from_live_plan_is_repaired(self):
        module = load("non_llm_operators.math_compute")
        with self.assertRaisesRegex(ValueError, "presence tests"):
            module.expression_columns("where(n != null, n - 1, null)")
        rows, _ = self.execute([{"n": None}, {"n": 3}], [{"operator": "Math_Compute",
            "expression": "where(is_not_null(n), n - 1, null)", "output_column": "v"}])
        self.assertEqual([r["v"] for r in rows], [None, 2])

    def test_bucket_else_null_and_order_match_sql(self):
        rows = [{"n": v} for v in (None, -1, 0, 9, 10, 15, 20, 21)]
        actual, _ = self.execute(rows, [{"operator": "Bucket", "input_column": "n", "output_column": "band",
            "rules": [{"label": None, "max": 0}, {"label": "low", "max": 10, "max_inclusive": "false"},
                      {"label": "mid", "min": 10, "max": 20}], "default": "high"}])
        with sqlite3.connect(":memory:") as db:
            db.execute("create table f(n)")
            db.executemany("insert into f values (?)", [(r["n"],) for r in rows])
            expected = [r[0] for r in db.execute("select case when n <= 0 then null when n < 10 then 'low' when n between 10 and 20 then 'mid' else 'high' end from f")]
        self.assertEqual([r["band"] for r in actual], expected)

    def test_complete_profiles_do_not_infer_uniqueness_from_samples(self):
        rows = [{"key": k} for k in ("a", "b", "c", "a", None)]
        self.assertEqual(load("data_profile").column_stats(rows, ["key"])["key"],
                         {"null_count": 1, "distinct_non_null": 3, "max_multiplicity": 2})

    def test_join_diagnostics_expose_fanout_and_actual_cardinality(self):
        args = {"branch_data_lists": [[{"k": "a"}, {"k": "a"}, {"k": None}],
                                      [{"k": "a"}, {"k": "a"}, {"k": "b"}]], "join_key": ["k"], "join_type": "left"}
        result = load("relational").integrate(args)
        stats = result["join_diagnostics"][0]
        self.assertEqual((stats["many_to_many_keys"], stats["output_rows"], stats["unmatched_left_rows"], stats["unmatched_right_rows"]), (1, 5, 1, 1))
        self.assertIn("violates", load("relational").integrate({**args, "cardinality": "one_to_one"})["error"])

    def test_group_merge_nulls_require_explicit_null_safe_equality(self):
        args = {"branch_data_lists": [[{"group": None, "a": 3}], [{"group": None, "b": 5}]], "join_key": ["group"], "join_type": "outer"}
        self.assertEqual(len(load("relational").integrate(args)["data"]), 2)
        self.assertEqual(load("relational").integrate({**args, "nulls_equal": True})["data"], [{"group": None, "a": 3, "b": 5}])


class V9RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.schema = {"Fact": {"class_iri": "urn:Fact", "subject_field": "id", "columns": [
            {"name": "id", "datatype": "resource_iri"},
            {"name": "n", "datatype": "numeric", "predicate_iri": "urn:n"},
            {"name": "at", "datatype": "date", "predicate_iri": "urn:at", "rdf_datatypes": [str(rdflib.XSD.date)]}]}}
        self.retrieval = {"class": "Fact", "entity_key": ["id"], "fields": ["id", "n", "at"], "optional_fields": ["n", "at"], "filters": []}
        self.graph = rdflib.Graph().parse(data='''@prefix e: <urn:> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
            e:a a e:Fact; e:n 4; e:at "2025-01-01"^^xsd:date .
            e:b a e:Fact; e:n 12; e:at "2024-12-31"^^xsd:date . e:c a e:Fact .''', format="turtle")

    def query(self, filters):
        query = load("raw_query").render_raw_query({**self.retrieval, "filters": filters}, self.schema)
        return {str(row.id) for row in self.graph.query(query)}, query

    def test_optional_numeric_filter_controls_population(self):
        self.assertEqual(self.query([{"field": "n", "operator": ">", "value": 10}])[0], {"urn:b"})

    def test_null_and_or_keep_missing_properties(self):
        self.assertEqual(self.query([{"field": "n", "operator": "is_null"}])[0], {"urn:c"})
        self.assertEqual(self.query([{"any": [{"field": "n", "operator": "is_null"}, {"field": "n", "operator": ">", "value": 10}]}])[0], {"urn:b", "urn:c"})

    def test_physical_date_type_wins_over_string_annotation(self):
        self.assertEqual(self.query([{"field": "at", "operator": ">=", "value": "2025-01-01", "value_type": "string"}])[0], {"urn:a"})

    def test_pre_scan_rejects_changed_column_and_filter_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "facts.db"
            with sqlite3.connect(path) as db:
                db.execute("CREATE TABLE Fact (id TEXT, n REAL, at TEXT)")
            db.close()
            schema = load("sqlite_backend").load_sqlite_schema(path)
            retrieval = {**self.retrieval, "filters": [{"field": "n", "operator": ">", "value": 10}]}
            query = load("raw_sql").render_raw_sql(retrieval, schema)
            check = load("llm_operators.pre_scan_validate").semantic_pre_scan_validate
            for text, valid in [(query, True), (query.replace('"n" > 10', '"at" > 10'), False),
                                (query.replace('"n" > 10', '"n" > 10 OR "n" IS NULL'), False)]:
                with self.subTest(valid=valid):
                    result = check({"sparql": text, "retrieval_spec": retrieval, "global_schema": schema,
                                    "sqlite_db_path": str(path)}, FakeClient({}))
                    self.assertEqual(result["pre_scan_validation"]["is_valid"], valid)

    def test_bad_filter_reaches_query_spec_error_before_generate(self):
        spec = {"retrieval_specs": [{**self.retrieval, "filters": [{"field": "n", "operator": "in", "value": "q2.id"}]}]}
        self.assertTrue(load("spec_contracts").validate_query_spec_contract(spec, self.schema))

    def test_declared_operands_are_retained_without_requiring_bound_values(self):
        spec = {"id": "q1", "retrieval_specs": [{"class": "Fact", "fields": ["id"]}]}
        decomposition = {"subquestions": [{"id": "q1", "source_class": "Fact", "required_fields": ["n", "at"]}]}
        self.assertFalse(load("connections").retain_connection_keys(spec, decomposition, self.schema))
        self.assertEqual(spec["retrieval_specs"][0]["optional_fields"], ["n", "at"])
        self.assertEqual(spec["output_schema"], ["id", "n", "at"])
        decomposition["subquestions"][0]["required_fields"] = ["invented"]
        self.assertTrue(load("connections").retain_connection_keys(spec, decomposition, self.schema))

    def test_semantic_context_and_assumptions_reach_final_plan(self):
        client = FakeClient({"projection": ["n"], "assumptions": ["Observation weighting"]})
        result = load("llm_operators.final_spec").semantic_build_final_spec({
            "processed_datasets": [{"id": "q1", "fields": ["id", "n"], "column_stats": {"n": {"null_count": 1}},
                                    "retrieval_specs": [{"class": "Fact"}]}], "global_schema": self.schema,
            "answer_requirements": {"calculation_notes": "Use signed differences from the owning source"}}, client)
        prompt = client.calls[0]["messages"][0]["content"]
        self.assertIn("signed differences from the owning source", prompt)
        self.assertIn('"predicate_iri": "urn:n"', prompt)
        self.assertIn('"null_count": 1', prompt)
        self.assertEqual(result["final_spec"]["assumptions"], ["Observation weighting"])

    def test_documentation_uses_explicit_source_ownership_not_global_field_names(self):
        graph = rdflib.Graph().parse(data='''
            @prefix wm: <https://wealth.example.org/ontology/> .
            @prefix d: <http://purl.org/dc/terms/> . @prefix e: <urn:> .
            e:s1 a wm:Primitive; wm:primitiveId "SOURCE1"; d:description "First source";
                wm:hasPrimitiveAttribute e:a1; wm:hasDerivedAttribute e:delta .
            e:s2 a wm:Primitive; wm:primitiveId "SOURCE2"; wm:hasPrimitiveAttribute e:a2 .
            e:a1 wm:attributeName "raw_value"; d:description "Value before adjustment"; wm:allowedValue "A" .
            e:a2 wm:attributeName "raw_value"; d:description "Unrelated measurement" .
            e:delta wm:derivedName "change"; d:description "After minus before" .
        ''', format="turtle")
        metadata = {"Record": {"source_tables": ["SOURCE1"], "columns": [{"name": "rawValue"}]},
                    "Other": {"source_tables": ["SOURCE2"], "columns": [{"name": "rawValue"}]}}
        result = load("schema_annotations").attach_schema_annotations(graph, metadata)
        self.assertEqual(result["Record"]["columns"][0]["description"], "Value before adjustment")
        self.assertEqual(result["Other"]["columns"][0]["description"], "Unrelated measurement")
        self.assertEqual(result["Record"]["derived_metrics"], [{"name": "change", "description": "After minus before"}])
        self.assertNotIn("change", [c["name"] for c in result["Record"]["columns"]])


if __name__ == "__main__":
    unittest.main()
