"""V4 model interface and honest execution/review separation."""
import copy
import unittest

from support import FakeClient, load, registry


class V4PlanningTests(unittest.TestCase):
    def execute(self, plan, rows, schemas=None):
        data, log = load("execution").execute_spec(plan, rows, registry(), dataset_schemas=schemas)
        self.assertFalse(load("execution").execution_errors(log), log)
        return data

    def test_single_steps_list_and_wrapped_plan_compile(self):
        branch = {"id": "a", "fields": ["name"]}
        for payload in [{"steps": [], "projection": ["name"]},
                        {"final_spec": {"final_steps": [], "projection": ["name"]}},
                        {"plan": {"steps": [], "projection": ["name"]}}]:
            with self.subTest(payload=payload):
                spec = load("llm_operators.final_spec").semantic_build_final_spec({
                    "processed_datasets": [branch]}, FakeClient(payload))["final_spec"]
                self.assertFalse(spec["contract_errors"])
                self.assertEqual(self.execute(spec, {"a": [{"name": "Label"}]}), [{"name": "Label"}])

    def test_invalid_model_response_is_retained_and_not_success(self):
        spec = load("llm_operators.final_spec").semantic_build_final_spec({
            "processed_datasets": [{"id": "a", "fields": ["name"]}]}, FakeClient("unusable response"))["final_spec"]
        self.assertTrue(spec["contract_errors"])
        self.assertEqual(spec["response_diagnostics"]["raw_response"], "unusable response")

    def test_dataset_class_alias_only_when_unambiguous(self):
        module = load("llm_operators.final_spec")
        branches = [{"id": "q1_processed", "branch_id": "q1", "retrieval_specs": [{"class": "Entity"}]}]
        spec = module.normalize_final_plan({"final_output": "Entity"}, branches)
        self.assertEqual(spec["final_output"], "q1_processed")
        branches.append({"id": "q2_processed", "branch_id": "q2", "retrieval_specs": [{"class": "Entity"}]})
        self.assertEqual(module.normalize_final_plan({"final_output": "Entity"}, branches)["final_output"], "Entity")
        self.assertEqual(module.normalize_final_plan({"final_output": "q2"}, branches)["final_output"], "q2_processed")

    def test_relationship_hints_use_declared_resource_key(self):
        schema = {"Fact": {"columns": [{"name": "owner", "datatype": "object_reference (points to: Person)"}]},
                  "Person": {"subject_field": "subject_iri"}}
        branches = [{"id": "facts", "fields": ["owner"], "retrieval_specs": [{"class": "Fact"}]},
                    {"id": "people", "fields": ["subject_iri", "literal_id"], "retrieval_specs": [{"class": "Person"}]}]
        profiles, hints = load("llm_operators.final_spec")._branch_context(branches, schema)
        self.assertEqual(hints, [{"inputs": ["facts", "people"], "left_on": ["owner"], "right_on": ["subject_iri"]}])
        self.assertIn("retrieval_specs", profiles[0])

    def test_aggregate_placeholder_uses_only_explicit_function(self):
        for key in ["agg", "agg_operation", "aggregation_function"]:
            spec = {"final_steps": [{"operator": "Filter_Aggregate", "operation": "aggregate", key: "sum",
                                     "target_column": "v", "output_column": "total"}]}
            self.assertEqual(self.execute(spec, {"source": [{"v": 2}, {"v": None}, {"v": 5}]}), [{"total": 7}])
        spec = {"final_steps": [{"operator": "Filter_Aggregate", "operation": "aggregate",
                                 "target_column": "v", "output_column": "total"}]}
        self.assertTrue(load("spec_runtime").compile_spec(spec, {"source": ["v"]})["contract_errors"])

    def test_single_expression_list_preserves_text(self):
        plan = {"final_steps": [{"operator": "Math_Compute", "expressions": [
            {"expression": "column('label')", "output_column": "display"}]}], "projection": ["display"]}
        self.assertEqual(self.execute(plan, {"source": [{"label": "Exact"}, {"label": None}]}),
                         [{"display": "Exact"}, {"display": None}])

    def test_explicit_equality_join_and_outer_spelling(self):
        plan = {"final_steps": [{"operator": "Integrate", "inputs": ["a", "b"],
                                 "join_key": "owner = id", "join_type": "left_outer"}], "projection": ["owner", "label"]}
        self.assertEqual(self.execute(plan, {"a": [{"owner": "x"}, {"owner": "y"}], "b": [{"id": "x", "label": "X"}]}),
                         [{"owner": "x", "label": "X"}, {"owner": "y", "label": None}])

    def test_null_constant_and_column_named_null_are_distinct(self):
        plan = {"final_steps": [{"operator": "Math_Compute", "expression": "null", "output_column": "missing"},
                                {"operator": "Math_Compute", "expression": "column('null')", "output_column": "value"}],
                "projection": ["missing", "value"]}
        self.assertEqual(self.execute(plan, {"source": [{"null": "label"}]}), [{"missing": None, "value": "label"}])

    def test_default_review_does_not_claim_correctness_or_call_model(self):
        client = FakeClient({"is_valid": True})
        result = load("llm_operators.validate").semantic_validate({"data": [], "semantic_review": False}, client)
        self.assertIsNone(result["validation"]["is_valid"])
        self.assertEqual(result["validation"]["status"], "not_requested")
        self.assertEqual(client.calls, [])

    def test_failed_review_is_unconfirmed_not_execution_error(self):
        result = load("llm_operators.validate").semantic_validate({"data": [{"x": 1}], "semantic_review": True}, FakeClient("bad JSON"))
        self.assertEqual(result["validation"]["status"], "disabled_by_prompt_policy")
        self.assertIsNone(result["validation"]["is_valid"])
        self.assertEqual(result["data"], [{"x": 1}])

    def test_logical_dependencies_do_not_block_independent_retrieval(self):
        raw = {"subquestions": [{"id": "a", "question": "all facts", "depends_on": []},
                                 {"id": "b", "question": "all owners", "depends_on": ["a"]}]}
        original = copy.deepcopy(raw)
        result = load("llm_operators.decompose")._cleanup_decomposition(raw, "owners with matching facts", [])
        selected = result["selected_decomposition"]
        self.assertFalse(selected["contract_errors"])
        self.assertEqual(selected["subquestions"][1]["logical_dependencies"], ["a"])
        self.assertEqual(selected["subquestions"][1]["depends_on"], [])
        self.assertEqual(selected["subquestions"][1]["question"], original["subquestions"][1]["question"])

    def test_dag_is_fixed_and_needs_no_model_decision(self):
        import networkx as nx
        client = FakeClient("must not be called")
        dag = load("planner").AdvancedAOPPlanner(client, {}).plan_optimal_dag_from_decomposition(
            "join two sources", {"subquestions": [{"id": "left"}, {"id": "right"}]})
        self.assertTrue(nx.is_directed_acyclic_graph(dag))
        self.assertEqual(len(list(dag.predecessors("final_spec"))), 2)
        self.assertEqual(sum(data["operator"] == "Final_Spec" for _, data in dag.nodes(data=True)), 1)
        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
