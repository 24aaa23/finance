"""Saved-run failure shapes, using synthetic data and no service calls."""
from copy import deepcopy
import contextlib
import io
import json
import unittest

from support import FakeClient, load, registry
import test_v8_comparative_contract as fixtures


class V8RepairSimplificationTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.V8ComparativeContractTests("runTest")
        fixture.setUp()
        self.plan = fixture.plan
        self.schemas = fixture.schemas
        self.data = fixture.fixture.data
        self.builder = load("llm_operators.final_spec")
        self.inputs = {
            "original_query": "Across category, how do average total sales and average customer ratings compare using three related tables?",
            "processed_datasets": [{"id": name, "branch_id": name + "_branch", "fields": fields,
                                    "retrieval_specs": [{"class": name.title()}]}
                                   for name, fields in self.schemas.items()]}

    def build(self, response, previous=None):
        client = FakeClient(response)
        inputs = deepcopy(self.inputs)
        if previous is not None:
            inputs["previous_final_spec"] = previous
        result = self.builder.semantic_build_final_spec(inputs, client)["final_spec"]
        return result, client.calls[0]["messages"][0]["content"]

    def missing_contract(self):
        plan = deepcopy(self.plan)
        plan.pop("comparative_contract")
        return self.build(plan)[0]

    def test_missing_metadata_retry_ignores_proposed_calculation_rewrite(self):
        previous = self.missing_contract()
        changed = deepcopy(self.plan)
        changed["final_steps"][0]["operation"] = "avg"
        changed["projection"] = ["category"]
        fixed, prompt = self.build(changed, previous)
        self.assertFalse(fixed["contract_errors"], fixed["contract_errors"])
        self.assertEqual(fixed["final_steps"], previous["final_steps"])
        self.assertEqual(fixed["projection"], previous["projection"])
        self.assertEqual(fixed["response_diagnostics"]["repair_scope"], "contract_only")
        self.assertIn("Do not return replacement steps", prompt)
        actual, log = load("execution").execute_spec(fixed, self.data, registry(), dataset_schemas=self.schemas)
        self.assertFalse(load("execution").execution_errors(log))
        expected, _ = load("execution").execute_spec(self.plan, self.data, registry(), dataset_schemas=self.schemas)
        self.assertEqual(actual, expected)

    def test_metadata_only_response_completes_the_existing_plan(self):
        fixed, _ = self.build({"comparative_contract": self.plan["comparative_contract"]}, self.missing_contract())
        self.assertFalse(fixed["contract_errors"])
        self.assertEqual(fixed["projection"], self.plan["projection"])

    def test_real_executor_reuses_scans_during_metadata_repair(self):
        first = deepcopy(self.plan)
        first.pop("comparative_contract")
        responses = [first, {"comparative_contract": self.plan["comparative_contract"]}]
        client = FakeClient(first)
        calls, scans = [], []

        def final(inputs):
            calls.append(deepcopy(inputs))
            client.value = responses[min(len(calls) - 1, 1)]
            return self.builder.semantic_build_final_spec(inputs, client)

        def query(inputs):
            name = inputs["subquestion_id"]
            return {"query_spec": {"id": name, "retrieval_specs": [{"class": name.title(), "fields": self.schemas[name]}]}}

        def scan(inputs):
            name = inputs["subquestion_id"]
            scans.append(name)
            return {"data": self.data[name], "columns": self.schemas[name], "status": "success"}

        ops = {**registry(), "Query_Spec": query,
               "Generate": lambda inputs: {"sparql": "SELECT * WHERE {}"},
               "Pre_Scan_Validate": lambda inputs: {"pre_scan_validation": {"is_valid": True}},
               "Scan": scan,
               "Processing_Spec": load("llm_operators.processing_spec").semantic_build_processing_spec,
               "Final_Spec": final,
               "Validate": lambda inputs: {"validation": {"is_valid": True}, "data": inputs["data"]},
               "Explain": lambda inputs: {"final_answer": json.dumps(inputs.get("data", []))}}
        decomposition = {"subquestions": [{"id": name, "question": "Read records", "source_class": name.title()} for name in self.schemas]}
        question = self.inputs["original_query"]
        dag = load("planner").AdvancedAOPPlanner(None, ops).plan_optimal_dag_from_decomposition(question, decomposition)
        with contextlib.redirect_stdout(io.StringIO()):
            result = load("executor").AOPExecutor(ops, None).execute_dag(dag, question, decomposition)
        self.assertTrue(result["trace"]["final_output_produced"], result["trace"])
        self.assertEqual(len(calls), 2)
        self.assertCountEqual(scans, list(self.schemas))
        self.assertEqual(result["trace"]["final_spec"]["response_diagnostics"]["repair_scope"], "contract_only")
        expected, _ = load("execution").execute_spec(self.plan, self.data, registry(), dataset_schemas=self.schemas)
        self.assertEqual(json.loads(result["final_answer"]), expected)

    def test_malformed_metadata_keeps_previous_steps_and_still_fails(self):
        previous = self.missing_contract()
        for response in ["not JSON", {"projection": ["invented"]}, {"comparative_contract": []}]:
            with self.subTest(response=response):
                result, _ = self.build(response, previous)
                self.assertEqual(result["final_steps"], previous["final_steps"])
                self.assertTrue(result["contract_errors"])

    def test_wrong_calculation_gets_full_repair_after_metadata_is_added(self):
        bad = deepcopy(self.plan)
        bad.pop("comparative_contract")
        bad["final_steps"][0]["operation"] = "avg"
        first, _ = self.build(bad)
        second, _ = self.build({"comparative_contract": self.plan["comparative_contract"]}, first)
        self.assertIn("needs sum per source entity", " ".join(second["contract_errors"]))
        third, prompt = self.build(self.plan, second)
        self.assertFalse(third["contract_errors"])
        self.assertNotIn("Add that object only", prompt)

    def test_unknown_field_error_does_not_freeze_calculation(self):
        broken = deepcopy(self.plan)
        broken["final_steps"][0]["input_column"] = "invented"
        first, _ = self.build(broken)
        repaired, prompt = self.build(self.plan, first)
        self.assertFalse(repaired["contract_errors"])
        self.assertNotIn("Add that object only", prompt)

    def test_prompt_example_includes_a_compilable_contract(self):
        _, prompt = self.build(self.plan)
        example_text = prompt.split("These are separate sources; region belongs to Customers.\n", 1)[1]
        example, _ = json.JSONDecoder().raw_decode(example_text)
        self.assertIn("comparative_contract", example)
        compiled = load("spec_runtime").compile_spec(example, {
            "Customers": ["customer_iri", "region"], "Payments": ["customer_ref", "amount"],
            "Reviews": ["customer_ref", "score"]})
        self.assertFalse(compiled["contract_errors"], compiled["contract_errors"])
        format_line = next(line for line in prompt.splitlines() if line.startswith("Use this single format"))
        self.assertIn("comparative_contract", format_line)

    def test_contract_source_aliases_use_same_mapping_as_plan(self):
        plan = deepcopy(self.plan)
        contract = plan["comparative_contract"]
        contract["required_population"] = ["People", "sales_branch", "Ratings"]
        contract["dimensions"][0]["source"] = "people_branch"
        contract["metrics"][0]["source"] = "Sales"
        contract["metrics"][1]["source"] = "ratings_branch"
        before = deepcopy(plan)
        fixed, _ = self.build(plan)
        self.assertEqual(plan, before)
        self.assertFalse(fixed["contract_errors"], fixed["contract_errors"])
        self.assertEqual(fixed["comparative_contract"]["metrics"][0]["source"], "sales")

    def test_ambiguous_class_alias_is_not_guessed(self):
        self.inputs["processed_datasets"].append({"id": "other_sales", "fields": ["owner", "value"],
                                                "retrieval_specs": [{"class": "Sales"}]})
        self.plan["comparative_contract"]["metrics"][0]["source"] = "Sales"
        result, _ = self.build(self.plan)
        self.assertEqual(result["comparative_contract"]["metrics"][0]["source"], "Sales")
        self.assertIn("actual source table", " ".join(result["contract_errors"]))

    def test_row_count_metadata_accepts_source_identity_and_counts_nulls(self):
        self.plan["final_steps"][0].update(operation="count_rows", input_column="*")
        self.plan["comparative_contract"]["metrics"][0].update(inner_aggregate="count_rows", source_columns=["owner"])
        result, _ = self.build(self.plan)
        self.assertFalse(result["contract_errors"], result["contract_errors"])
        actual, _ = load("execution").execute_spec(result, self.data, registry(), dataset_schemas=self.schemas)
        category = next(row for row in actual if row["category"] == "X")
        self.assertEqual(category["avg_total"], 1.5)  # two sales for a, one for b

    def test_count_rows_does_not_certify_count_nullable_values(self):
        self.plan["final_steps"][0].update(operation="count", input_column="value")
        self.plan["comparative_contract"]["metrics"][0].update(inner_aggregate="count_rows")
        result, _ = self.build(self.plan)
        self.assertIn("needs count_rows per source entity", " ".join(result["contract_errors"]))

    def test_outer_none_has_actionable_error_without_accepting_wrong_plan(self):
        self.plan["comparative_contract"]["metrics"][0]["outer_aggregate"] = "none"
        result, _ = self.build(self.plan)
        self.assertIn("For one grouping, use inner_aggregate='none'", " ".join(result["contract_errors"]))

    def test_reserved_step_names_are_renamed_with_references(self):
        self.plan["final_steps"][0]["id"] = "__spec_step_9"
        self.plan["final_steps"][2]["inputs"][1] = "__spec_step_9"
        result, _ = self.build(self.plan)
        self.assertFalse(result["contract_errors"], result["contract_errors"])
        self.assertFalse(result["final_steps"][0]["id"].startswith("__spec_step_"))
        self.assertEqual(result["final_steps"][0]["id"], result["final_steps"][2]["inputs"][1])

    def test_malformed_steps_are_compiler_errors_not_normalizer_exceptions(self):
        result, _ = self.build({"final_steps": 42, "projection": []})
        self.assertIn("final_steps must be a list", " ".join(result["contract_errors"]))

    def test_schema_spelling_normalization_preserves_literal_values(self):
        payload = {"selected_decomposition": {
            "subquestions": [{"id": "q1", "source_class": "Sales Record", "question": "Find Sales Record"}],
            "answer_requirements": {"predicates": [{"source_class": "Sales Record", "field": "label", "value": "Sales Record"}]}}}
        result = load("llm_operators.decompose").semantic_decompose_question({
            "query": "Find Sales Record", "global_schema": {"SalesRecord": {}}, "retrieved_tables": ["SalesRecord"]},
            FakeClient(payload))["selected_decomposition"]
        self.assertFalse(result["contract_errors"], result["contract_errors"])
        self.assertEqual(result["subquestions"][0]["source_class"], "SalesRecord")
        self.assertEqual(result["answer_requirements"]["source_classes"], ["SalesRecord"])
        predicate = result["answer_requirements"]["predicates"][0]
        self.assertEqual(predicate["source_class"], "SalesRecord")
        self.assertEqual(predicate["value"], "Sales Record")

    def test_ambiguous_catalogue_spelling_is_rejected(self):
        payload = {"subquestions": [{"id": "q1", "source_class": "sales record"}]}
        result = load("llm_operators.decompose").semantic_decompose_question({
            "global_schema": {"SalesRecord": {}, "Sales_Record": {}}}, FakeClient(payload))["selected_decomposition"]
        self.assertTrue(result["contract_errors"])
        self.assertEqual(result["subquestions"][0]["source_class"], "sales record")


if __name__ == "__main__":
    unittest.main()
