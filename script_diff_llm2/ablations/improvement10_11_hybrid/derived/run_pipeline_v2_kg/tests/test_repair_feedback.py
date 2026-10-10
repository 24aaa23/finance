"""Offline recovery checks using the real builders, compiler, and executor."""
import contextlib
from copy import deepcopy
import io
import json
import sqlite3
import unittest
from unittest.mock import patch

from support import FakeClient, load, registry


class RepairFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.fields = ["subject", "amount", "label"]
        self.rows = [{"subject": "urn:record:1", "amount": 8, "label": "Sample"}]
        self.schema = {
            "Record": {"subject_field": "subject", "class_iri": "urn:Record", "columns": [
                {"name": "subject", "datatype": "resource_iri", "type": "Subject"},
                {"name": "amount", "datatype": "numeric", "predicate_iri": "urn:amount"},
                {"name": "label", "datatype": "categorical_string", "predicate_iri": "urn:label"}]},
            "Unrelated": {"columns": [{"name": "other", "predicate_iri": "urn:other"}]},
        }
        self.retrieval = {"id": "source", "retrieval_specs": [{"id": "source", "class": "Record",
            "entity_key": ["subject"], "fields": self.fields, "filters": []}], "output_schema": self.fields}
        self.lookup = {"final_steps": [], "projection": ["amount"]}

    def run_flow(self, plans=None, scan_failures=None, retrievals=None):
        plans, scan_failures, retrievals = plans or [self.lookup], scan_failures or [], retrievals or [self.retrieval]
        seen = {name: [] for name in ["Final_Spec", "Query_Spec", "Scan", "Refine", "Generate"]}
        final_client = FakeClient({})

        def build_final(inputs):
            seen["Final_Spec"].append(deepcopy(inputs))
            final_client.value = plans[min(len(seen["Final_Spec"]) - 1, len(plans) - 1)]
            return load("llm_operators.final_spec").semantic_build_final_spec(
                {**inputs, "global_schema": self.schema}, final_client)

        def build_query(inputs):
            seen["Query_Spec"].append(deepcopy(inputs))
            payload = retrievals[min(len(seen["Query_Spec"]) - 1, len(retrievals) - 1)]
            return load("llm_operators.query_spec").semantic_build_query_spec(
                {**inputs, "global_schema": self.schema}, FakeClient(payload))

        def scan(inputs):
            seen["Scan"].append(deepcopy(inputs))
            if len(seen["Scan"]) <= len(scan_failures):
                return scan_failures[len(seen["Scan"]) - 1]
            return {"status": "success", "data": self.rows, "columns": self.fields, "sparql": inputs["sparql"]}

        def query_text(stage, inputs):
            seen[stage].append(deepcopy(inputs))
            return {"sparql": "SELECT ?subject ?amount ?label WHERE {}"}

        ops = {**registry(),
            "Query_Spec": build_query, "Final_Spec": build_final, "Scan": scan,
            "Generate": lambda inputs: query_text("Generate", inputs),
            "Refine": lambda inputs: query_text("Refine", inputs),
            "Pre_Scan_Validate": lambda inputs: {"pre_scan_validation": {"is_valid": True}},
            "Processing_Spec": load("llm_operators.processing_spec").semantic_build_processing_spec,
            "Validate": lambda inputs: {"validation": {"is_valid": True}, "data": inputs["data"]},
            "Explain": lambda inputs: {"final_answer": json.dumps(inputs.get("data", []))},
        }
        decomposition = {"subquestions": [{"id": "source", "source_class": "Record", "question": "Read records"}]}
        dag = load("planner").AdvancedAOPPlanner(None, ops).plan_optimal_dag_from_decomposition("Read amount", decomposition)
        with contextlib.redirect_stdout(io.StringIO()):
            result = load("executor").AOPExecutor(ops, None, self.schema).execute_dag(
                dag, "Read amount", decomposition, initial_context={"retrieved_tables": ["Record"]})
        return result, seen, final_client

    def test_runtime_failure_reaches_retry_with_real_step_and_input_columns(self):
        broken = {"final_steps": [{"id": "calculated", "operator": "Math_Compute",
                                  "expression": "label + 1", "output_column": "answer"}],
                  "projection": ["answer"]}
        fixed = deepcopy(broken)
        fixed["final_steps"][0]["expression"] = "column('amount')"
        result, seen, _ = self.run_flow([broken, fixed])
        self.assertEqual(json.loads(result["final_answer"]), [{"answer": 8}])
        feedback = json.loads(seen["Final_Spec"][1]["spec_feedback"])
        failure = feedback["failed_steps"][0]
        self.assertEqual(failure["operator"], "Math_Compute")
        self.assertEqual(failure["inputs"], ["source_processed"])
        self.assertEqual(failure["input_schemas"], {"source_processed": self.fields})
        self.assertEqual(failure["step"], feedback["step_ids"]["calculated"])
        self.assertEqual(failure["code"], "OPERATOR_ERROR")
        self.assertIn("Non-numeric", failure["error"])
        self.assertEqual(seen["Final_Spec"][1]["previous_final_spec"]["projection"], ["answer"])
        self.assertEqual(len(seen["Scan"]), 1)

    def test_compile_errors_can_recover_on_fourth_attempt_without_rescanning(self):
        invalid = {"final_steps": [], "projection": ["invented"]}
        result, seen, _ = self.run_flow([invalid, invalid, invalid, self.lookup])
        self.assertTrue(result["trace"]["final_output_produced"])
        self.assertEqual(len(seen["Final_Spec"]), 4)
        self.assertEqual(len(seen["Scan"]), 1)
        for attempt, inputs in enumerate(seen["Final_Spec"][1:], 1):
            feedback = json.loads(inputs["spec_feedback"])
            self.assertEqual(feedback["attempt"], attempt)
            self.assertEqual(feedback["available_schemas"]["source_processed"], self.fields)
            self.assertTrue(any("invented" in error for error in feedback["errors"]))

    def test_persistent_final_failure_stops_after_four_attempts(self):
        result, seen, _ = self.run_flow([{"final_steps": [], "projection": ["invented"]}])
        self.assertEqual(len(seen["Final_Spec"]), 4)
        self.assertFalse(result["trace"]["final_output_produced"])
        self.assertEqual(result["trace"]["failure_stage"], "Final_Spec")
        self.assertEqual(result["trace"]["repair_log"][-1]["action"], "stop")

    def test_missing_retrieval_preserves_failed_plan_before_upstream_repair(self):
        missing = [{"source_class": "Connector", "field": "reference"}]
        result, seen, _ = self.run_flow([{"missing_requirements": missing}])
        self.assertEqual(len(seen["Final_Spec"]), 1)
        self.assertEqual(result["trace"]["repair_stage"], "Decompose")
        self.assertEqual(result["trace"]["final_spec"]["missing_requirements"], missing)
        self.assertEqual(result["trace"]["repair_log"][-1]["spec"]["missing_requirements"], missing)

    def test_query_spec_retry_gets_previous_contract_and_structured_errors(self):
        broken = deepcopy(self.retrieval)
        broken["retrieval_specs"][0]["fields"] = self.fields + ["invented"]
        result, seen, _ = self.run_flow(retrievals=[broken, self.retrieval])
        self.assertTrue(result["trace"]["final_output_produced"])
        retry = seen["Query_Spec"][1]
        feedback = json.loads(retry["spec_feedback"])
        self.assertEqual(feedback["stage"], "Query_Spec")
        self.assertTrue(any("invented" in error for error in feedback["errors"]))
        self.assertIn("invented", retry["previous_query_spec"]["retrieval_specs"][0]["fields"])

    def test_scan_repairs_receive_source_properties_without_a_local_graph(self):
        for kind in ["syntax", "unknown_term", "missing_sparql"]:
            with self.subTest(kind=kind):
                failure = {"status": "error", "error_message": "bad query",
                           "failed_sparql": '' if kind == "missing_sparql" else 'SELECT * WHERE { ?s <urn:bad> "O\'Brien" }'}
                if kind == "unknown_term":
                    failure["unknown_terms"] = ["urn:bad"]
                result, seen, _ = self.run_flow(scan_failures=[failure])
                self.assertTrue(result["trace"]["final_output_produced"])
                if kind == "unknown_term":
                    feedback = json.loads(seen["Query_Spec"][1]["spec_feedback"])
                    self.assertIn("previous_query_spec", seen["Query_Spec"][1])
                elif kind == "syntax":
                    feedback = json.loads(seen["Refine"][0]["logic_feedback"])
                    self.assertEqual(seen["Refine"][0]["schema_details"], {"Record": self.schema["Record"]})
                else:
                    feedback = json.loads(seen["Generate"][1]["logic_feedback"])
                self.assertEqual(feedback["source_schema"], {"Record": self.schema["Record"]})
                self.assertEqual(len(seen["Scan"]), 2)


class ConnectorSchemaTests(unittest.TestCase):
    def setUp(self):
        self.schema = {
            "Sale": {"columns": [{"name": "customer_ref"}]},
            "Region": {"columns": [{"name": "label"}]},
            "Customer": {"backend": "rdf", "class_iri": "urn:Customer", "subject_field": "customer_id", "columns": [
                {"name": "customer_id", "datatype": "categorical_string"},
                {"name": "region_ref", "datatype": "categorical_string", "predicate_iri": "urn:region_ref"}]},
            "Unrelated": {"columns": [{"name": "unused"}]},
        }
        self.retrieval = {"id": "connector", "class": "Customer", "entity_key": ["customer_id"],
                          "fields": ["customer_id", "region_ref"], "filters": []}
        self.inputs = {"query": "Sales by region", "retrieved_tables": ["Sale", "Region"],
                       "global_schema": self.schema,
                       "subquestion": {"id": "connector", "source_class": "Customer"}}

    def assert_connector_schema(self, client):
        prompt = client.calls[0]["messages"][0]["content"]
        supplied = json.loads(prompt.split("\nSchema: ", 1)[1].split("\n", 1)[0])
        self.assertEqual(supplied["Customer"], self.schema["Customer"])
        self.assertEqual(set(supplied), {"Customer"})

    def test_query_spec_includes_added_connector_even_with_explicit_pruned_schema(self):
        for explicit in [False, True]:
            with self.subTest(explicit_schema=explicit):
                inputs = deepcopy(self.inputs)
                if explicit:
                    inputs["schema_details"] = {name: self.schema[name] for name in inputs["retrieved_tables"]}
                before = deepcopy(inputs)
                client = FakeClient({"id": "connector", "retrieval_specs": [self.retrieval]})
                result = load("llm_operators.query_spec").semantic_build_query_spec(inputs, client)
                self.assertFalse(result["query_spec"]["contract_errors"])
                self.assert_connector_schema(client)
                self.assertEqual(inputs, before)

    def test_generate_includes_added_connector_from_either_contract_input(self):
        with patch.object(load("utils"), "repair_sparql_for_query", lambda text, query: text, create=True):
            generate = load("llm_operators.generate").semantic_generate_sparql
        for explicit in [False, True]:
            with self.subTest(explicit_retrieval=explicit):
                inputs = {**deepcopy(self.inputs), "query_spec": {"retrieval_specs": [self.retrieval]}}
                if explicit:
                    inputs["retrieval_spec"] = self.retrieval
                before = deepcopy(inputs)
                client = FakeClient("SELECT ?customer_id ?region_ref WHERE {}")
                with contextlib.redirect_stdout(io.StringIO()):
                    result = generate(inputs, client, "offline")
                self.assertEqual(client.calls, [])
                self.assertIn("a <urn:Customer>", result["sparql"])
                self.assertIn("<urn:region_ref> ?region_ref", result["sparql"])
                self.assertEqual(inputs, before)


class PlanningContextTests(unittest.TestCase):
    def test_large_repair_feedback_is_complete_json_in_model_prompt(self):
        feedback = {"errors": ["Missing field " + "x" * 5000], "available_schemas": {"raw": ["value"]}}
        client = FakeClient({"projection": ["value"]})
        load("llm_operators.final_spec").semantic_build_final_spec({
            "processed_datasets": [{"id": "raw", "fields": ["value"]}],
            "spec_feedback": json.dumps(feedback)}, client)
        prompt = client.calls[0]["messages"][0]["content"]
        supplied = prompt.split("Repair errors, if any: ", 1)[1].split("\nPrevious plan, if any:", 1)[0]
        sanitized = json.loads(supplied)
        self.assertEqual(sanitized["available_schemas"], feedback["available_schemas"])
        self.assertEqual(sanitized["errors"], ["schema_reference_error"])
        self.assertNotIn("x" * 5000, supplied)

    def test_unselected_connector_fields_and_reference_targets_reach_decompose(self):
        schema = {
            "Sale": {"columns": [{"name": "customer_ref", "datatype": "object_reference (points to: Customer)"}]},
            "Region": {"columns": [{"name": "label"}]},
            "Customer": {"subject_field": "customer_id", "columns": [
                {"name": "customer_id", "datatype": "resource_iri"},
                {"name": "region_ref", "datatype": "object_reference (points to: Region)"}]},
        }
        client = FakeClient({})
        load("llm_operators.decompose").semantic_decompose_question(
            {"query": "Sales by region", "retrieved_tables": ["Sale", "Region"], "global_schema": schema}, client)
        prompt = client.calls[0]["messages"][0]["content"]
        catalogue = prompt.split("Other available sources (fields and relationships for needed connectors): ", 1)[1].split("\n", 1)[0]
        self.assertEqual(json.loads(catalogue), {"Customer": schema["Customer"]})

    def test_worked_comparison_plan_matches_sql_with_unequal_counts_and_nulls(self):
        datasets = {
            "Payments": [{"customer_ref": customer, "amount": amount} for customer, amount in
                         [("a", 10), ("a", 20), ("b", 90), ("b", None), ("c", 500), ("d", 12)]],
            "Reviews": [{"customer_ref": customer, "score": score} for customer, score in
                        [("a", 2), ("a", 4), ("b", 9), ("b", None), ("d", None)]],
            "Customers": [{"customer_id": customer, "region": region} for customer, region in
                          [("a", "north"), ("b", "north"), ("c", "north"), ("d", None)]],
        }
        schemas = {name: list(rows[0]) for name, rows in datasets.items()}
        declared_plan = {"final_steps": [
            {"id": "spend", "operator": "Filter_Aggregate", "input": "Payments", "group_by": ["customer_ref"],
             "aggregations": [{"operation": "sum", "input_column": "amount", "output_column": "customer_spend"}]},
            {"id": "scores", "operator": "Filter_Aggregate", "input": "Reviews", "group_by": ["customer_ref"],
             "aggregations": [{"operation": "avg", "input_column": "score", "output_column": "customer_score"}]},
            {"id": "metrics", "operator": "Integrate", "inputs": ["spend", "scores"], "left_on": ["customer_ref"], "right_on": ["customer_ref"], "join_type": "inner"},
            {"id": "profiles", "operator": "Integrate", "inputs": ["metrics", "Customers"], "left_on": ["customer_ref"], "right_on": ["customer_id"], "join_type": "inner"},
            {"operator": "Filter_Aggregate", "input": "profiles", "group_by": ["region"], "aggregations": [
                {"operation": "avg", "input_column": "customer_spend", "output_column": "mean_spend"},
                {"operation": "avg", "input_column": "customer_score", "output_column": "mean_score"}]}],
            "projection": ["region", "mean_spend", "mean_score"]}
        client = FakeClient(declared_plan)
        result = load("llm_operators.final_spec").semantic_build_final_spec(
            {"processed_datasets": [{"id": name, "fields": fields} for name, fields in schemas.items()]}, client)
        prompt = client.calls[0]["messages"][0]["content"]
        self.assertNotIn("Worked example", prompt)
        plan = result["final_spec"]
        actual, log = load("execution").execute_spec(plan, datasets, registry(), dataset_schemas=schemas)
        self.assertFalse(load("execution").execution_errors(log))
        with sqlite3.connect(":memory:") as db:
            db.execute("CREATE TABLE payments(customer_ref TEXT, amount REAL)")
            db.execute("CREATE TABLE reviews(customer_ref TEXT, score REAL)")
            db.execute("CREATE TABLE customers(customer_id TEXT, region TEXT)")
            for name, rows in datasets.items():
                db.executemany(f"INSERT INTO {name} VALUES (?, ?)", [tuple(row.values()) for row in rows])
            expected = [dict(zip(["region", "mean_spend", "mean_score"], row)) for row in db.execute("""
                WITH spend AS (SELECT customer_ref, SUM(amount) AS total FROM payments GROUP BY customer_ref),
                     scores AS (SELECT customer_ref, AVG(score) AS score FROM reviews GROUP BY customer_ref)
                SELECT c.region, AVG(p.total), AVG(r.score)
                FROM spend p JOIN scores r ON p.customer_ref = r.customer_ref
                JOIN customers c ON p.customer_ref = c.customer_id GROUP BY c.region
            """)]
        self.assertCountEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
