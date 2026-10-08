"""Failures must remain visible across retrieval, compilation and reporting."""
import contextlib
import io
import json
import sqlite3
import unittest

from support import FakeClient, load, registry


class FinalReviewTests(unittest.TestCase):
    def test_existence_filters_preserve_left_multiplicity_and_sql_nulls(self):
        data = {"a": [{"id": 1}, {"id": 1}, {"id": 2}, {"id": None}, {"id": None}],
                "b": [{"id": 1}, {"id": None}]}
        for operator, sql_op in [("Set_Intersect", "EXISTS"), ("Set_Difference", "NOT EXISTS")]:
            spec = {"final_steps": [{"operator": operator, "inputs": ["a", "b"],
                    "left_on": ["id"], "right_on": ["id"], "distinct": False, "nulls_equal": False}]}
            actual, log = load("execution").execute_spec(spec, data, registry())
            self.assertFalse(load("execution").execution_errors(log))
            with sqlite3.connect(":memory:") as db:
                for table in data:
                    db.execute(f"CREATE TABLE {table}(id)")
                    db.executemany(f"INSERT INTO {table} VALUES (?)", [(row["id"],) for row in data[table]])
                expected = [{"id": row[0]} for row in db.execute(f"SELECT a.id FROM a WHERE {sql_op} (SELECT 1 FROM b WHERE b.id=a.id)")]
            self.assertEqual(actual, expected)

    def test_invalid_decomposition_cannot_become_successful_default_branch(self):
        for payload in ["not json", {}, {"selected_decomposition": {"subquestions": []}}]:
            result = load("llm_operators.decompose").semantic_decompose_question(
                {"query": "compare records", "global_schema": {"Record": {}}}, FakeClient(payload))
            self.assertTrue(result["selected_decomposition"]["contract_errors"])

    def test_unknown_decomposition_source_fails_before_retrieval(self):
        result = load("llm_operators.decompose").semantic_decompose_question(
            {"global_schema": {"Record": {}}}, FakeClient({"subquestions": [{"id": "a", "source_class": "Invented"}]}))
        self.assertTrue(any("source_class" in reason for reason in result["selected_decomposition"]["contract_errors"]))

    def test_malformed_connection_list_is_not_discarded_silently(self):
        result = load("llm_operators.decompose")._cleanup_decomposition({
            "subquestions": [{"id": "a", "source_class": "Record"}],
            "answer_requirements": {"joins": {"left_branch": "a"}}}, "query", [])
        self.assertTrue(result["selected_decomposition"]["contract_errors"])

    def test_raw_scan_rejects_population_changing_modifiers_and_aggregates(self):
        queries = ["SELECT DISTINCT ?id WHERE {?id ?p ?o}",
                   "SELECT ?id WHERE {?id ?p ?o} LIMIT 1",
                   "SELECT ?id WHERE {?id ?p ?o} OFFSET 1",
                   "SELECT (COUNT(?s) AS ?id) WHERE {?s ?p ?o}",
                   "SELECT ?id WHERE {{SELECT ?id WHERE {?id ?p ?o} LIMIT 2}}"]
        for query in queries:
            with self.subTest(query=query):
                result = load("llm_operators.pre_scan_validate").semantic_pre_scan_validate(
                    {"sparql": query, "retrieval_spec": {"fields": ["id"]}}, FakeClient("unused"))
                self.assertFalse(result["pre_scan_validation"]["is_valid"])

    def test_projection_does_not_require_presence_of_each_measure(self):
        schema = {"Record": {"subject_field": "subject", "columns": [
            {"name": "subject", "datatype": "resource_iri"},
            {"name": "first", "datatype": "numeric"}, {"name": "second", "datatype": "numeric"}]}}
        result = load("llm_operators.query_spec").semantic_build_query_spec(
            {"query": "average both measures", "global_schema": schema}, FakeClient({
                "retrieval_specs": [{"class": "Record", "fields": ["subject", "first", "second"], "optional_fields": [], "filters": []}]}))
        spec = result["query_spec"]
        self.assertFalse(spec["contract_errors"])
        self.assertCountEqual(spec["retrieval_specs"][0]["optional_fields"], ["first", "second"])

    def test_rdf_date_metadata_corrects_filter_type_without_changing_boundary(self):
        schema = {"Record": {"subject_field": "subject", "columns": [
            {"name": "subject", "datatype": "resource_iri"},
            {"name": "at", "datatype": "categorical_string", "rdf_datatypes": ["http://www.w3.org/2001/XMLSchema#date"]}]}}
        spec = {"retrieval_specs": [{"class": "Record", "fields": ["at"],
            "filters": [{"field": "at", "operator": ">=", "value": "2025-01-01", "value_type": "string"}]}]}
        load("llm_operators.query_spec")._normalize_rdf_fields(spec, schema)
        self.assertEqual(spec["retrieval_specs"][0]["filters"], [
            {"field": "at", "operator": ">=", "value": "2025-01-01", "value_type": "date"}])

    def run_pipeline(self, columns):
        ops = registry()
        seen = {}
        executed = "SELECT ?subject ?value WHERE {?subject <urn:actual> ?value}"
        def validate(inputs):
            seen.update(inputs)
            return {"validation": {"is_valid": None, "status": "not_requested"}, "data": inputs["data"]}
        ops.update({
            "Query_Spec": lambda inputs: {"query_spec": {"retrieval_specs": [{"fields": ["subject", "value"]}]}},
            "Generate": lambda inputs: {"sparql": "SELECT * WHERE {?subject ?p ?value}"},
            "Pre_Scan_Validate": lambda inputs: {"pre_scan_validation": {"is_valid": True}},
            "Scan": lambda inputs: {"status": "success", "data": [], "columns": columns, "sparql": executed},
            "Processing_Spec": load("llm_operators.processing_spec").semantic_build_processing_spec,
            "Final_Spec": lambda inputs: {"final_spec": load("spec_runtime").compile_spec(
                {"final_steps": [], "projection": ["value"]}, {"a_processed": ["subject", "value"]})},
            "Validate": validate,
            "Explain": lambda inputs: {"final_answer": json.dumps(inputs.get("data", []))},
        })
        decomposition = {"subquestions": [{"id": "a", "source_class": "Record", "question": "source task"}]}
        dag = load("planner").AdvancedAOPPlanner(None, ops).plan_optimal_dag_from_decomposition("original", decomposition)
        with contextlib.redirect_stdout(io.StringIO()):
            result = load("executor").AOPExecutor(ops, None).execute_dag(dag, "original", decomposition,
                initial_context={"retrieved_tables": ["Record"]})
        return result, seen, executed

    def test_actual_scan_query_and_retrieved_classes_reach_review_and_trace(self):
        result, seen, executed = self.run_pipeline(["subject", "value"])
        self.assertTrue(result["trace"]["final_output_produced"])
        self.assertEqual(result["trace"]["retrieved_classes"], ["Record"])
        self.assertEqual(result["trace"]["executed_sparqls"][0]["sparql"], executed)
        self.assertEqual(seen["branch_evidence"][0]["executed_sparql"], executed)
        self.assertEqual(seen["branch_evidence"][0]["question"], "source task")

    def test_empty_scan_with_missing_column_is_not_filled_with_invented_schema(self):
        result, seen, _ = self.run_pipeline(["subject"])
        self.assertEqual(result["trace"]["failure_stage"], "Execution")
        self.assertFalse(result["trace"]["final_output_produced"])
        self.assertFalse(seen)


if __name__ == "__main__":
    unittest.main()
