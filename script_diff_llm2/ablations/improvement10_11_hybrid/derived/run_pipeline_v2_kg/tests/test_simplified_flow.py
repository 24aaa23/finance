"""Regressions for unnecessary gates found in the September 12 rerun."""
import contextlib
import io
import json
import sqlite3
import unittest

import networkx as nx

from support import FakeClient, load, registry


class SimplifiedFlowTests(unittest.TestCase):
    def build_final(self, payload, schemas, requirements=None):
        return load("llm_operators.final_spec").semantic_build_final_spec({
            "original_query": "Compute the requested grouped result",
            "processed_datasets": [{"id": key, "fields": fields} for key, fields in schemas.items()],
            "answer_requirements": requirements or {},
        }, FakeClient(payload))["final_spec"]

    def test_processing_needs_no_model_and_keeps_duplicates_and_nulls(self):
        client = FakeClient("invalid model JSON must never be requested")
        rows = [{"id": "a", "value": None}, {"id": "a", "value": None}]
        spec = load("llm_operators.processing_spec").semantic_build_processing_spec({
            "data": rows, "input_schema": ["id", "value"], "subquestion_id": "source",
            "subquestion": {"retrieval_grain": ["id"]},
        }, client)["processing_spec"]
        data, log = load("execution").execute_spec(spec, {"raw": rows}, registry(), "lookup")
        self.assertEqual(data, rows)
        self.assertFalse(load("execution").execution_errors(log))
        self.assertEqual(client.calls, [])

    def test_empty_scan_keeps_its_schema_without_a_model(self):
        spec = load("llm_operators.processing_spec").semantic_build_processing_spec({
            "data": [], "input_schema": ["id", "nullable_label"], "subquestion_id": "source",
        })["processing_spec"]
        self.assertEqual(spec["compiled_output_schema"], ["id", "nullable_label"])
        self.assertFalse(spec["contract_errors"])

    def test_aggregate_inputs_are_not_required_answer_columns(self):
        rows = [{"kind": "a", "amount": 4}, {"kind": "a", "amount": None},
                {"kind": "b", "amount": 7}, {"kind": None, "amount": 9}]
        payload = {"final_group_by": ["kind"], "final_measures": [
            {"operation": "count_rows", "input_column": "*", "output_column": "n"},
            {"operation": "sum", "input_column": "amount", "output_column": "total_amount"}],
            "projection": ["kind", "n", "total_amount"]}
        spec = self.build_final(payload, {"source": ["kind", "amount"]},
                                {"required_projection": ["kind", "amount"], "group_by": ["kind"]})
        self.assertFalse(spec["contract_errors"])
        data, log = load("execution").execute_spec(spec, {"source": rows}, registry(), "count and total by kind")
        self.assertFalse(load("execution").execution_errors(log))
        with sqlite3.connect(":memory:") as db:
            db.execute("create table facts(kind text, amount real)")
            db.executemany("insert into facts values (?, ?)", [(r["kind"], r["amount"]) for r in rows])
            expected = [dict(zip(["kind", "n", "total_amount"], row))
                        for row in db.execute("select kind, count(*), sum(amount) from facts group by kind")]
        self.assertCountEqual(data, expected)

    def test_per_branch_computation_and_having_only_metric(self):
        schemas = {"payments": ["owner", "amount"], "progress": ["owner", "score"]}
        payload = {"merge_steps": [
            {"operator": "Filter_Aggregate", "input": "payments", "output": "totals",
             "operation": "sum", "target_column": "amount", "output_column": "total", "group_by": ["owner"]},
            {"operator": "Filter_Aggregate", "input": "progress", "output": "averages",
             "operation": "avg", "target_column": "score", "output_column": "avg_score", "group_by": ["owner"]},
            {"operator": "Integrate", "inputs": ["totals", "averages"], "join_key": ["owner"]}],
            "final_steps": [{"operator": "Filter_Aggregate", "operation": "filter",
                             "filters": [{"field": "avg_score", "operator": ">", "value": 50}]}],
            "projection": ["owner", "total"]}
        spec = self.build_final(payload, schemas, {"required_projection": ["owner"],
            "metrics": [{"output_column": "avg_score"}], "group_by": ["owner", "total"]})
        self.assertFalse(spec["contract_errors"])
        rows = {"payments": [{"owner": "a", "amount": 2}, {"owner": "a", "amount": 3}, {"owner": "b", "amount": 8}],
                "progress": [{"owner": "a", "score": 60}, {"owner": "a", "score": 80}, {"owner": "b", "score": 20}]}
        data, log = load("execution").execute_spec(spec, rows, registry(), "totals for owners whose average score exceeds 50")
        self.assertFalse(load("execution").execution_errors(log))
        self.assertEqual(data, [{"owner": "a", "total": 5}])

    def test_unknown_final_column_is_still_an_error(self):
        spec = self.build_final({"final_steps": [], "projection": ["invented"]}, {"source": ["id"]})
        self.assertTrue(spec["contract_errors"])

    def test_explicit_row_count_with_named_column_includes_nulls(self):
        payload = {"final_measures": [
            {"operation": "count_rows", "input_column": "id", "output_column": "rows"},
            {"operation": "count", "input_column": "id", "output_column": "bound"},
            {"operation": "count_distinct", "input_column": "id", "output_column": "unique"}]}
        spec = self.build_final(payload, {"source": ["id"]})
        self.assertFalse(spec["contract_errors"])
        data, log = load("execution").execute_spec(spec, {"source": [{"id": "a"}, {"id": "a"}, {"id": None}]}, registry())
        self.assertFalse(load("execution").execution_errors(log))
        self.assertEqual(data, [{"rows": 3, "bound": 2, "unique": 1}])

    def run_lookup(self, approve=True):
        rows = [{"record_id": "REC-91", "display_name": "Sample Name"}]
        fields = list(rows[0])
        ops = registry()
        calculation_client = FakeClient({"final_steps": [], "projection": ["display_name"]})
        processing_client = FakeClient("not used")
        validation_client = FakeClient({"is_valid": approve, "reason": "checked question" if approve else "wrong requested meaning",
                                        "repair_stage": "Final_Spec"})
        def forbidden_critic(inputs):
            self.fail("The redundant branch semantic critic must not be called")
        ops.update({
            "Query_Spec": lambda inputs: {"query_spec": {"retrieval_specs": [{"fields": fields}], "contract_errors": []}},
            "Query_Spec_Validate": forbidden_critic,
            "Generate": lambda inputs: {"sparql": "SELECT ?record_id ?display_name WHERE {}"},
            "Pre_Scan_Validate": lambda inputs: {"pre_scan_validation": {"is_valid": True}},
            "Scan": lambda inputs: {"data": rows, "columns": fields, "status": "success", "row_count": 1},
            "Processing_Spec": lambda inputs: load("llm_operators.processing_spec").semantic_build_processing_spec(inputs, processing_client),
            "Final_Spec": lambda inputs: load("llm_operators.final_spec").semantic_build_final_spec(inputs, calculation_client),
            "Validate": lambda inputs: load("llm_operators.validate").semantic_validate({**inputs, "semantic_review": True}, validation_client),
            "Explain": lambda inputs: {"final_answer": json.dumps(inputs.get("data", []))},
        })
        order = ["Query_Spec", "Generate", "Pre_Scan_Validate", "Scan", "Processing_Spec", "Final_Spec", "Validate", "Explain"]
        dag = nx.DiGraph()
        for op in order:
            dag.add_node(op, operator=op, explicit_inputs={"subquestion_id": "q1"} if op in order[:5] else {})
        dag.add_edges_from(zip(order, order[1:]))
        with contextlib.redirect_stdout(io.StringIO()):
            result = load("executor").AOPExecutor(ops, None).execute_dag(dag, "What is the name of record REC-91?",
                {"subquestions": [{"id": "q1", "question": "retrieve record name"}],
                 "answer_requirements": {"required_projection": fields, "distinct_on": ["record_id"]}})
        self.assertFalse(processing_client.calls)
        return result, calculation_client, validation_client

    def test_lookup_with_actual_builders_reaches_final_validation(self):
        result, calculation, validation = self.run_lookup()
        self.assertEqual(json.loads(result["final_answer"]), [{"display_name": "Sample Name"}])
        self.assertIsNone(result["trace"]["validation_is_valid"])
        self.assertTrue(result["trace"]["final_output_produced"])
        self.assertEqual(len(calculation.calls), 1)
        self.assertEqual(len(validation.calls), 0)

    def test_semantically_rejected_lookup_is_preserved_with_rejected_review(self):
        result, calculation, validation = self.run_lookup(approve=False)
        self.assertIsNone(result["trace"]["validation_is_valid"])
        self.assertTrue(result["trace"]["final_output_produced"])
        self.assertEqual(result["trace"]["failure_stage"], "")
        self.assertEqual(result["trace"]["answer_review_status"], "disabled_by_prompt_policy")
        self.assertEqual(len(validation.calls), 0)


if __name__ == "__main__":
    unittest.main()
