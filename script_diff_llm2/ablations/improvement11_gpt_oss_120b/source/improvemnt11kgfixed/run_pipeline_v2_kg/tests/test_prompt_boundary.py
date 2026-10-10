"""Exercise actual outbound model messages with instance-data sentinels."""
from copy import deepcopy
import json
import os
import unittest
from unittest.mock import patch
from support import FakeClient, load

ROW = "PRIVATE_INSTANCE_ROW_918273"
COUNT = "PRIVATE_POPULATION_782341"
STATS = "PRIVATE_DISTRIBUTION_712834"


def schema():
    return {"Items": {"backend": "rdf", "class_iri": "urn:Items", "subject_field": "subject_iri",
            "instance_count": COUNT, "sample": [{"amount": ROW}], "column_stats": STATS,
            "columns": [{"name": "subject_iri", "datatype": "resource_iri"},
                        {"name": "amount", "datatype": "numeric", "predicate_iri": "urn:amount", "observed_values": [ROW]}]}}


class PromptBoundaryTests(unittest.TestCase):
    def assert_private_absent(self, client):
        payload = json.dumps(client.calls)
        for private in (ROW, COUNT, STATS):
            self.assertNotIn(private, payload)

    def test_retrieve_decompose_and_query_spec_strip_instance_metadata(self):
        clients = [FakeClient(["Items"]), FakeClient({}), FakeClient({})]
        load("llm_operators.retrieve").semantic_retrieve({"query": "List amounts", "table_index": schema()}, clients[0])
        load("llm_operators.decompose").semantic_decompose_question({"query": "List amounts", "global_schema": schema()}, clients[1])
        load("llm_operators.query_spec").semantic_build_query_spec({"query": "List amounts", "global_schema": schema(),
            "schema_details": schema(), "spec_feedback": json.dumps({"errors": ["Invalid numeric value " + ROW]})}, clients[2])
        for client in clients:
            self.assertTrue(client.calls)
            self.assert_private_absent(client)

    def test_final_planner_omits_rows_statistics_and_runtime_error_values(self):
        client = FakeClient({"projection": ["amount"]})
        branch = {"id": "a", "fields": ["subject_iri", "amount"], "sample": [{"amount": ROW}],
                  "row_count": COUNT, "column_stats": STATS,
                  "retrieval_specs": [{"class": "Items", "fields": ["subject_iri", "amount"], "sample": ROW}]}
        feedback = {"errors": ["Invalid numeric value " + ROW], "failed_steps": [{"step": "total", "operator": "Math_Compute",
                    "code": "MATH_ERROR", "error": ROW}], "available_schemas": {"a": ["subject_iri", "amount"]}}
        load("llm_operators.final_spec").semantic_build_final_spec({"global_schema": schema(), "processed_datasets": [branch],
            "spec_feedback": json.dumps(feedback), "data": [{"amount": ROW}], "branch_datasets": {"a": [{"amount": ROW}]}}, client)
        self.assert_private_absent(client)
        prompt = client.calls[0]["messages"][0]["content"]
        self.assertIn("calculation_error", prompt)
        self.assertNotIn('"row_count"', prompt)
        self.assertNotIn('"column_stats"', prompt)
        self.assertNotIn('"sample"', prompt)

    def test_post_scan_operator_planning_has_only_schema(self):
        for name, function in (("filter_aggregate", "semantic_filter_aggregate"), ("order_by", "semantic_order_by")):
            client = FakeClient({})
            getattr(load("llm_operators." + name), function)({"query": "List amounts", "schema_details": schema()}, client)
            self.assertTrue(client.calls)
            self.assert_private_absent(client)

    def test_model_review_and_explainer_flags_cannot_enable_row_transmission(self):
        client = FakeClient({"is_valid": True})
        data = [{"amount": ROW}]
        with patch.dict(os.environ, {"FINAL_SEMANTIC_REVIEW": "1", "DETERMINISTIC_EXPLAIN": "0"}):
            result = load("llm_operators.validate").semantic_validate({"data": data, "semantic_review": True}, client)
            answer = load("llm_operators.explain").semantic_explain_results({"data": data}, client)
        self.assertEqual(result["validation"]["status"], "disabled_by_prompt_policy")
        self.assertEqual(json.loads(answer["final_answer"]), data)
        self.assertEqual(client.calls, [])

    def test_integrate_cannot_fall_back_to_model_synthesis_of_rows(self):
        client = FakeClient("unused")
        result = load("llm_operators.integrate").semantic_integrate({"branch_1_output": {"amount": ROW}}, client)
        self.assertEqual(result["code"], "INTEGRATE_PLAN_REQUIRED")
        self.assertEqual(client.calls, [])

    def test_question_literals_and_declared_property_bindings_are_preserved(self):
        client = FakeClient({"retrieval_specs": [{"class": "Items", "fields": ["subject_iri", "amount"],
            "entity_key": ["subject_iri"], "filters": [{"field": "amount", "operator": ">", "value": 123}]}]})
        result = load("llm_operators.query_spec").semantic_build_query_spec({"query": "amount greater than 123", "global_schema": schema()}, client)
        self.assertEqual(result["query_spec"]["retrieval_specs"][0]["filters"][0]["value"], 123)
        self.assertIn("urn:amount", json.dumps(client.calls))
        self.assert_private_absent(client)

    def test_operator_prompts_have_no_hardcoded_financial_rules_or_worked_dataset(self):
        clients = [FakeClient({"final_steps": []}), FakeClient({})]
        load("llm_operators.final_spec").semantic_build_final_spec({"global_schema": schema()}, clients[0])
        load("llm_operators.decompose").semantic_decompose_question({"global_schema": schema()}, clients[1])
        payload = json.dumps([client.calls for client in clients]).lower()
        for text in ("scenario gap", "action gap", "worked example", "per-investor", "payments", "reviews", "customers"):
            self.assertNotIn(text, payload)

    def test_feedback_is_nonmutating_and_raw_error_text_stays_local(self):
        original = {"stage": "Final_Spec", "errors": [ROW], "failed_steps": [{"error": ROW,
                    "step": "s1", "code": "EXECUTION_ERROR", "input_schemas": {"a": ["amount"]}}]}
        before = deepcopy(original)
        safe = load("prompt_boundary").feedback_for_prompt(original)
        self.assertNotIn(ROW, safe)
        self.assertEqual(original, before)
