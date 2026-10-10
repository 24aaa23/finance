"""Regressions for saved v3 failures; all model responses are offline fixtures."""
from copy import deepcopy
import csv
import json
from pathlib import Path
import unittest

from support import FakeClient, SOURCE, load, registry


def interpretation():
    return {"bindings": [], "metrics": [], "filters": [], "group_by": [],
            "required_projection": ["id"], "order_by": [], "limit": None,
            "population": "records", "null_policy": "unspecified", "ambiguities": []}


class SavedFailureTests(unittest.TestCase):
    def test_all_saved_missing_owner_failures_retain_resolved_raw_sources(self):
        root = SOURCE.parent / "pipelien_output_sql_v3"
        if not root.exists():
            self.skipTest("Saved reports are optional local fixtures.")
        csv.field_size_limit(2**30)
        schema = load("sql_metadata").load_yaml_metadata(SOURCE.parent / "table_medatada")
        count = 0
        for path in root.glob("*/raw_pipeline_v9_debug.csv"):
            with path.open(encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    if row["New Status"] != "DECOMPOSITION_ERROR" or not row["Validation Reason"].startswith("Interpretation requires"):
                        continue
                    contract = json.loads(row["Debug Query Understanding"])
                    selected = {"subquestions": json.loads(row["Debug Subquestions"]),
                                "answer_requirements": json.loads(row["Debug Answer Requirements"]),
                                "contract_errors": []}
                    with self.subTest(question_id=row["Sample Row ID"]):
                        before = deepcopy(selected)
                        load("query_understanding").retain_contract_sources(selected, contract, schema)
                        load("query_understanding").apply_contract(selected, contract)
                        self.assertEqual(selected["contract_errors"], [])
                        self.assertEqual(selected["answer_requirements"]["joins"], before["answer_requirements"]["joins"])
                        self.assertEqual(selected["answer_requirements"]["predicates"], before["answer_requirements"]["predicates"])
                        for original, retained in zip(before["subquestions"], selected["subquestions"]):
                            self.assertEqual(retained["source_class"], original["source_class"])
                            self.assertTrue(set(original["required_fields"]).issubset(retained["required_fields"]))
                        again = deepcopy(selected)
                        load("query_understanding").retain_contract_sources(selected, contract, schema)
                        self.assertEqual(selected, again)
                    count += 1
        self.assertGreater(count, 0)

    def test_decompose_retains_a_missing_owner_without_hardcoded_table_names(self):
        schema = {name: {"columns": [{"name": "id"}, {"name": "value"}], "primary_keys": ["id"]}
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

    def test_field_comparison_requests_final_calculation_instead_of_bad_raw_sql(self):
        predicate = {"field": "after", "operator": "<", "value": {"field_ref": "before"}}
        errors = load("sql_conditions").raw_condition_errors(predicate)
        self.assertIn("stage=final", errors[0])
        self.assertEqual(load("sql_conditions").raw_condition_errors({**predicate, "value": 0}), [])

    def test_query_spec_scope_is_one_table_and_source_switch_still_fails(self):
        schema = {name: {"backend": "sqlite", "sql_table": name,
                        "columns": [{"name": "id"}], "primary_keys": ["id"]}
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
                            "not an expression", "foreign key does not make its source column unique"):
            self.assertIn(requirement, prompt)


if __name__ == "__main__":
    unittest.main()
