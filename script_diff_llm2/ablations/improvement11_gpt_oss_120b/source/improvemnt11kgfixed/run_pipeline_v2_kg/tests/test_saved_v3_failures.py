"""Regressions for saved v3 failures; all model responses are offline fixtures."""
from copy import deepcopy
import json
import unittest

from support import FakeClient, load, registry


def interpretation():
    return {"bindings": [], "metrics": [], "filters": [], "group_by": [],
            "required_projection": ["id"], "order_by": [], "limit": None,
            "population": "records", "null_policy": "unspecified", "ambiguities": []}


class SavedFailureTests(unittest.TestCase):
    def test_rdf_source_retention_preserves_subject_identity_without_inventing_relationships(self):
        schema = {"People": {"subject_field": "subject_iri", "columns": [
                    {"name": "subject_iri"}, {"name": "label"}]},
                  "Orders": {"subject_field": "subject_iri", "columns": [{"name": "subject_iri"}]}}
        contract = interpretation()
        contract["bindings"] = [{"phrase": "label", "table": "People", "column": "label", "rule_ids": []}]
        selected = {"subquestions": [{"id": "q1", "source_class": "Orders", "required_fields": ["subject_iri"]}],
                    "answer_requirements": {"predicates": [], "joins": []}, "contract_errors": []}
        understanding = load("query_understanding")
        understanding.retain_contract_sources(selected, contract, schema)
        retained = selected["subquestions"][1]
        self.assertEqual(retained["retrieval_grain"], ["subject_iri"])
        self.assertEqual(retained["required_fields"], ["subject_iri", "label"])
        self.assertEqual(selected["answer_requirements"]["predicates"], [])
        self.assertEqual(selected["answer_requirements"]["joins"], [])
        before = deepcopy(selected)
        understanding.retain_contract_sources(selected, contract, schema)
        self.assertEqual(selected, before)

    def test_decompose_retains_a_missing_owner_without_hardcoded_table_names(self):
        schema = {name: {"columns": [{"name": "id"}, {"name": "value"}], "subject_field": "id"}
                  for name in ("People", "Orders")}
        contract = interpretation()
        contract["bindings"] = [{"phrase": "people", "table": "People", "column": "id", "rule_ids": []}]
        contract["filters"] = [{"phrase": "value above 10", "description": "value > 10",
                                "operands": [{"table": "Orders", "column": "value"}], "stage": "scan"}]
        response = {"selected_decomposition": {"subquestions": [
            {"id": "q1", "question": "Read order values", "source_class": "Orders", "required_fields": ["id"]}]}}
        result = load("llm_operators.decompose").semantic_decompose_question(
            {"query": "List people with order value above 10", "global_schema": schema,
             "retrieved_tables": ["Orders"], "query_understanding": contract}, FakeClient(response))
        selected = result["selected_decomposition"]
        self.assertEqual(selected["contract_errors"], [])
        self.assertEqual(selected["subquestions"][0]["required_fields"], ["id", "value"])
        self.assertEqual(selected["subquestions"][1]["source_class"], "People")
        self.assertEqual(selected["answer_requirements"]["required_branch_ids"], ["q1", "contract_source_1"])

    def test_invalid_contract_field_is_still_rejected(self):
        value = interpretation()
        value["group_by"] = [{"table": "Unknown", "column": "invented"}]
        selected = {"subquestions": [{"id": "q1", "source_class": "Known", "required_fields": ["id"]}],
                    "answer_requirements": {}, "contract_errors": []}
        understanding = load("query_understanding")
        understanding.retain_contract_sources(selected, value, {"Known": {"columns": [{"name": "id"}]}})
        understanding.apply_contract(selected, value)
        self.assertEqual(len(selected["subquestions"]), 1)
        self.assertIn("Unknown.invented", selected["contract_errors"][0])

    def test_field_comparison_requests_final_calculation_instead_of_bad_raw_query(self):
        predicate = {"field": "after", "operator": "<", "value": {"field_ref": "before"}}
        errors = load("conditions").raw_condition_errors(predicate)
        self.assertIn("stage=final", errors[0])
        self.assertEqual(load("conditions").raw_condition_errors({**predicate, "value": 0}), [])

    def test_query_spec_scope_is_one_table_and_source_switch_still_fails(self):
        schema = {name: {"backend": "rdf", "class_iri": "urn:" + name,
                        "columns": [{"name": "id"}], "subject_field": "id"}
                  for name in ("People", "Orders")}
        client = FakeClient({"id": "orders", "retrieval_specs": [
            {"id": "orders", "class": "Orders", "fields": ["id"], "entity_key": ["id"], "filters": []}]})
        result = load("llm_operators.query_spec").semantic_build_query_spec(
            {"query": "Retrieve people", "original_query": "People with orders",
             "subquestion": {"id": "people", "source_class": "People"},
             "retrieved_tables": ["People", "Orders"], "global_schema": schema}, client)
        prompt = client.calls[0]["messages"][0]["content"]
        supplied = json.loads(prompt.split("\nSchema: ", 1)[1].split("\n", 1)[0])
        self.assertEqual(set(supplied), {"People"})
        self.assertIn("Assigned source (immutable for this call): People", prompt)
        self.assertTrue(any("changed assigned source" in error for error in result["query_spec"]["contract_errors"]))

    def test_derived_group_alias_is_not_requested_as_a_database_column(self):
        value = interpretation()
        value.update(group_by=[{"table": "Measures", "column": "band"}],
                     required_projection=["band", "n"], metrics=[
            {"output": "band", "definition": "where(value < 10, 'low', 'high')",
             "operands": [{"table": "Measures", "column": "value"}],
             "inner_aggregation": "none", "outer_aggregation": "none", "entity_keys": [],
             "units": "label", "rule_ids": []},
            {"output": "n", "definition": "count records", "operands": [],
             "inner_aggregation": "none", "outer_aggregation": "count_rows", "entity_keys": [],
             "units": "count", "rule_ids": []}])
        schema = {"Measures": {"columns": [{"name": "value"}]}}
        understanding = load("query_understanding")
        self.assertEqual(understanding.validate_interpretation(value, "Group by band", schema, {"rules": []}), value)
        self.assertEqual(understanding.required_fields(value), {("Measures", "value")})
        plan = {"final_steps": [
            {"operator": "Math_Compute", "expression": "where(value < 10, 'low', 'high')", "output_column": "band"},
            {"operator": "Filter_Aggregate", "group_by": ["band"], "operation": "count_rows",
             "input_column": "*", "output_column": "n"}], "projection": ["band", "n"]}
        spec = load("spec_runtime").compile_spec(plan, {"raw": ["value"]})
        self.assertEqual(spec["contract_errors"], [])
        self.assertEqual(understanding.final_contract_errors(spec, value), [])
        data, log = load("execution").execute_spec(spec, {"raw": [{"value": 2}, {"value": 20}]}, registry())
        self.assertEqual(data, [{"band": "low", "n": 1}, {"band": "high", "n": 1}])
        self.assertEqual(load("execution").execution_errors(log), [])

    def test_distinct_label_plan_has_no_false_aggregate_grain_failure(self):
        value = interpretation()
        value.update(required_projection=["label"], metrics=[{"output": "label", "outer_aggregation": "distinct"}])
        plan = {"final_steps": [{"operator": "Filter_Aggregate", "group_by": ["label"],
                  "operation": "count_rows", "input_column": "*", "output_column": "unused_count"}],
                "projection": ["label"]}
        spec = load("spec_runtime").compile_spec(plan, {"raw": ["label"]})
        self.assertEqual(spec["contract_errors"], [])
        self.assertEqual(load("query_understanding").final_contract_errors(spec, value), [])
        data, log = load("execution").execute_spec(spec, {"raw": [{"label": "a"}, {"label": "a"}, {"label": "b"}]}, registry())
        self.assertEqual(data, [{"label": "a"}, {"label": "b"}])
        self.assertEqual(load("execution").execution_errors(log), [])

    def test_final_prompt_requires_existing_datasets_and_individual_expressions(self):
        client = FakeClient({"final_steps": [], "projection": ["value"]})
        load("llm_operators.final_spec").semantic_build_final_spec(
            {"query": "Read values", "processed_datasets": [{"id": "raw", "fields": ["value"]}]}, client)
        prompt = client.calls[0]["messages"][0]["content"]
        for requirement in ("Scan are ALREADY complete", "ONE expression and ONE output_column",
                            "not an expression", "reference does not make its source field unique"):
            self.assertIn(requirement, prompt)


if __name__ == "__main__":
    unittest.main()
