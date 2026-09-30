"""Regressions for failed v3 contracts, using independent synthetic records."""
from copy import deepcopy
import json
import unittest

from support import FakeClient, load, registry


class FailureRepairTests(unittest.TestCase):
    def setUp(self):
        self.schema = {"Reading": {"subject_field": "record", "columns": [
            {"name": name} for name in ["record", "owner", "score", "band"]]}}
        self.branches = [{"id": "readings", "fields": ["record", "owner", "score", "band"],
                          "retrieval_specs": [{"class": "Reading"}]}]
        self.term = {"source_class": "Reading", "operand_fields": ["score"],
                     "entity_key": "owner", "inner_aggregation": "sum"}
        self.metric = {"output_column": "mean_total", "source_class": None,
                       "operand_fields": [], "components": [self.term],
                       "entity_key": "owner", "inner_aggregation": "sum",
                       "outer_aggregation": "avg", "group_owner": "Reading"}
        self.plan = {"final_steps": [
            {"id": "totals", "operator": "Filter_Aggregate", "group_by": ["owner", "band"],
             "operation": "sum", "target_column": "score", "output_column": "total"},
            {"operator": "Filter_Aggregate", "group_by": ["band"], "operation": "avg",
             "target_column": "total", "output_column": "mean_total"}],
            "projection": ["band", "mean_total"]}

    def build(self, plan=None, metric=None):
        client = FakeClient(self.plan if plan is None else plan)
        result = load("llm_operators.final_spec").semantic_build_final_spec({
            "processed_datasets": self.branches, "global_schema": self.schema,
            "answer_requirements": {"metrics": [self.metric if metric is None else metric]}}, client)
        return result["final_spec"], client

    def run_plan(self, plan, datasets):
        rows, log = load("execution").execute_spec(plan, datasets, registry())
        self.assertFalse(load("execution").execution_errors(log), log)
        return rows

    def test_components_do_not_require_a_phantom_none_source(self):
        spec, _ = self.build()
        self.assertEqual(spec["contract_errors"], [])
        data = [{"record": i, "owner": owner, "score": score, "band": None}
                for i, (owner, score) in enumerate([("a", 10), ("a", 30), ("b", 100)])]
        self.assertEqual(self.run_plan(spec, {"readings": data}), [{"band": None, "mean_total": 70}])

    def test_components_still_reject_pooled_averages(self):
        plan = {"final_steps": [{"operator": "Filter_Aggregate", "group_by": ["band"],
                "operation": "avg", "target_column": "score", "output_column": "mean_total"}]}
        self.term["inner_aggregation"] = "avg"
        spec, _ = self.build(plan)
        self.assertIn("component avg per Reading.owner", " ".join(spec["contract_errors"]))

    def test_outer_aggregate_cannot_double_as_component_inner_aggregate(self):
        plan = {"final_steps": [{"operator": "Filter_Aggregate", "group_by": ["owner"],
                "operation": "avg", "target_column": "score", "output_column": "mean_total"}]}
        self.term["inner_aggregation"] = "avg"
        spec, _ = self.build(plan)
        self.assertIn("component avg per Reading.owner", " ".join(spec["contract_errors"]))

    def test_wrong_component_operation_is_still_rejected(self):
        self.plan["final_steps"][0]["operation"] = "max"
        spec, _ = self.build()
        self.assertIn("component sum per Reading.owner", " ".join(spec["contract_errors"]))

    def test_unknown_sources_fields_and_unowned_operands_repair_upstream(self):
        mutations = [
            {"source_class": None, "components": []},
            {"operand_fields": ["score"]},
            {"components": [{**self.term, "source_class": "Missing"}]},
            {"components": [{**self.term, "operand_fields": ["invented"]}]},
            {"inner_aggregation": "sum(score)"},
        ]
        for change in mutations:
            with self.subTest(change=change):
                metric = {**self.metric, **change}
                spec, client = self.build(metric=metric)
                self.assertEqual(spec["repair_stage"], "Decompose")
                self.assertTrue(spec["contract_errors"])
                self.assertFalse(client.calls)

    def test_wrong_group_owner_is_repaired_before_final_model_call(self):
        self.schema["Person"] = {"columns": ["owner", "band"]}
        self.metric["group_owner"] = "Person"
        spec, client = self.build()
        self.assertEqual(spec["repair_stage"], "Decompose")
        self.assertIn("group_owner Person", " ".join(spec["contract_errors"]))
        self.assertFalse(client.calls)
        self.metric["group_owner"] = "Reading"
        self.assertEqual(self.build()[0]["contract_errors"], [])

    def test_decompose_rejects_group_owner_without_source_branch(self):
        self.schema["Person"] = {"columns": ["owner", "band"]}
        self.metric["group_owner"] = "Person"
        payload = {"subquestions": [{"id": "r", "source_class": "Reading"}],
                   "answer_requirements": {"metrics": [self.metric]}}
        client = FakeClient(payload)
        result = load("llm_operators.decompose").semantic_decompose_question({
            "query": "Average score totals by score band", "global_schema": self.schema,
            "previous_decomposition": payload, "decomposition_feedback": "Repair group source"}, client)
        errors = result["selected_decomposition"]["contract_errors"]
        self.assertIn("group_owner Person", " ".join(errors))
        prompt = client.calls[0]["messages"][0]["content"]
        prior = prompt.split("Previous decomposition to repair, if any: ", 1)[1].split("\n", 1)[0]
        self.assertEqual(json.loads(prior), payload)

    def test_contract_conflicts_and_missing_sources_return_to_decompose(self):
        for field, value in [("contract_conflicts", ["Group is based on the score, not Person"]),
                             ("missing_requirements", [{"source_class": "Person", "field": "band"}])]:
            with self.subTest(field=field):
                spec, client = self.build({field: value})
                self.assertEqual(spec["repair_stage"], "Decompose")
                self.assertEqual(spec[field], value)
                self.assertNotIn("execution_steps", spec)
                self.assertEqual(len(client.calls), 1)

    def test_aggregation_aliases_match_compiled_lineage(self):
        self.term["inner_aggregation"] = "mean"
        self.metric["outer_aggregation"] = "average"
        self.plan["final_steps"][0]["operation"] = "avg"
        self.assertEqual(self.build()[0]["contract_errors"], [])

    def test_disjoint_case_filters_are_not_anded_in_one_scan(self):
        check = load("semantic_contracts").predicate_errors
        inflow = {"field": "kind", "operator": "in", "value": ["credit", "deposit"]}
        outflow = {"field": "kind", "operator": "in", "value": ["debit", "withdrawal"]}
        self.assertIn("Contradictory allowed values", " ".join(check([inflow, outflow])))
        self.assertEqual(check([{"any": [inflow, outflow]}]), [])
        self.assertEqual(check([inflow, {**outflow, "value": ["deposit", "withdrawal"]}]), [])
        requirements = {"predicates": [{**p, "source_class": "Reading", "stage": "final"}
                                        for p in [inflow, outflow]]}
        self.assertEqual(load("semantic_contracts").decomposition_predicate_errors(
            requirements, [{"id": "r", "source_class": "Reading"}]), [])

    def test_empty_aggregate_list_does_not_disable_an_explicit_filter(self):
        plan = {"final_steps": [{"id": "non_null", "operator": "Filter_Aggregate",
                "operation": "filter", "filters": [{"field": "x", "operator": "is_not_null"}],
                "aggregations": []}], "final_output": "non_null"}
        self.assertEqual(self.run_plan(plan, {"raw": [{"x": None}, {"x": 0}, {"x": 2}]}), [{"x": 0}, {"x": 2}])
        plan["final_steps"][0].update(operation="sum", filters=[])
        self.assertTrue(load("spec_runtime").compile_spec(plan, {"raw": ["x"]})["contract_errors"])

    def test_same_key_multi_input_join_retains_all_groups(self):
        plan = {"final_steps": [{"operator": "Integrate", "inputs": ["a", "b", "c"],
                "left_on": ["group"], "right_on": ["group"], "join_type": "outer",
                "cardinality": "one_to_one", "nulls_equal": True}]}
        data = {"a": [{"group": None, "x": 1}], "b": [{"group": None, "y": 2}],
                "c": [{"group": None, "z": 3}, {"group": "extra", "z": 4}]}
        self.assertCountEqual(self.run_plan(plan, data), [
            {"group": None, "x": 1, "y": 2, "z": 3}, {"group": "extra", "x": None, "y": None, "z": 4}])
        spec = load("spec_runtime").compile_spec(plan, {k: list(v[0]) for k, v in data.items()})
        self.assertEqual(spec, load("spec_runtime").compile_spec(spec, {k: list(v[0]) for k, v in data.items()}))

    def test_multi_input_join_with_different_keys_or_conflicts_still_fails(self):
        base = {"operator": "Integrate", "inputs": ["a", "b", "c"], "left_on": ["id"], "right_on": ["other"]}
        for change in [{}, {"right_on": ["id"], "join_key": ["other"]}]:
            with self.subTest(change=change):
                spec = load("spec_runtime").compile_spec({"final_steps": [{**base, **change}]},
                                                        {k: ["id", "other"] for k in ["a", "b", "c"]})
                self.assertTrue(spec["contract_errors"])

    def test_copy_projects_without_removing_duplicates_or_nulls(self):
        plan = {"final_steps": [{"id": "base", "operator": "Copy", "input": "raw",
                "output_columns": ["id", "label"]}], "final_output": "base"}
        data = [{"id": 1, "label": None, "extra": 7}, {"id": 1, "label": None, "extra": 8}]
        before = deepcopy(data)
        self.assertEqual(self.run_plan(plan, {"raw": data}), [{"id": 1, "label": None}] * 2)
        self.assertEqual(data, before)
        rows, log = load("execution").execute_spec(plan, {"raw": []}, registry(),
                                                  dataset_schemas={"raw": ["id", "label", "extra"]})
        self.assertEqual(rows, [])
        self.assertFalse(load("execution").execution_errors(log))
        plan["final_steps"][0]["output_columns"].append("unknown")
        self.assertTrue(load("spec_runtime").compile_spec(plan, {"raw": ["id", "label", "extra"]})["contract_errors"])

    def test_copy_preserves_metric_lineage(self):
        self.plan["final_steps"].insert(0, {"operator": "Copy", "input": "readings",
                                           "output_columns": ["owner", "score", "band"]})
        self.assertEqual(self.build()[0]["contract_errors"], [])

    def test_copy_preserves_identity_type_checks(self):
        schema = {name: {"subject_field": "id", "columns": ["id"]} for name in ["Person", "Event"]}
        profiles = [{"id": name, "source_class": name, "fields": ["id"]} for name in schema]
        plan = {"final_steps": [
            {"id": "people", "operator": "Copy", "input": "Person", "output_columns": ["id"]},
            {"operator": "Integrate", "inputs": ["people", "Event"], "join_key": ["id"]}]}
        spec = load("spec_runtime").compile_spec(plan, {name: ["id"] for name in schema})
        self.assertEqual(spec["contract_errors"], [])
        self.assertIn("different entity classes", " ".join(
            load("semantic_contracts").final_semantic_errors(spec, profiles, schema, {})))

    def test_declared_compiler_names_do_not_collide_with_expanded_steps(self):
        plan = {"final_steps": [
            {"id": "__spec_step_1", "operator": "Filter_Aggregate", "input": "raw",
             "group_by": ["owner", "band"], "aggregations": [
                 {"operation": "count_rows", "output_column": "n"},
                 {"operation": "avg", "input_column": "score", "output_column": "mean"}]},
            {"id": "__spec_step_2", "operator": "Filter_Aggregate", "input": "__spec_step_1",
             "group_by": ["band"], "aggregations": [
                 {"operation": "sum", "input_column": "n", "output_column": "n"},
                 {"operation": "avg", "input_column": "mean", "output_column": "score"}]}],
            "final_output": "__spec_step_2"}
        data = [{"owner": owner, "band": None, "score": score}
                for owner, score in [("a", 10), ("a", 30), ("b", 100)]]
        spec = load("spec_runtime").compile_spec(plan, {"raw": list(data[0])})
        self.assertEqual(spec["contract_errors"], [])
        self.assertEqual(self.run_plan(spec, {"raw": data}), [{"band": None, "n": 3, "score": 60}])
        self.assertEqual(spec, load("spec_runtime").compile_spec(spec, {"raw": list(data[0])}))
        self.assertFalse({s["id"] for s in spec["execution_steps"]} & {"__spec_step_1", "__spec_step_2"})

    def test_generated_names_also_avoid_original_dataset_ids(self):
        plan = {"final_steps": [{"id": "copy", "operator": "Copy", "output_columns": ["x"]}]}
        self.assertEqual(self.run_plan(plan, {"__spec_step_1": [{"x": 4}]}), [{"x": 4}])

    def test_expanded_aggregate_ids_are_reserved_before_compiling(self):
        plan = {"final_steps": [{"id": "summary", "operator": "Filter_Aggregate", "aggregations": [
            {"id": "__spec_step_2", "operation": "sum", "input_column": "x", "output_column": "total"},
            {"id": "__spec_step_1", "operation": "count", "input_column": "x", "output_column": "n"}]}]}
        self.assertEqual(self.run_plan(plan, {"raw": [{"x": 4}, {"x": None}]}), [{"total": 4, "n": 1}])

    def test_true_duplicate_and_forward_reference_still_fail(self):
        for steps in [
            [{"id": "same", "operator": "Copy", "input": "raw"},
             {"id": "same", "operator": "Copy", "input": "same"}],
            [{"id": "first", "operator": "Copy", "input": "__spec_step_2"},
             {"id": "__spec_step_2", "operator": "Copy", "input": "raw"}],
        ]:
            with self.subTest(steps=steps):
                spec = load("spec_runtime").compile_spec({"final_steps": steps}, {"raw": ["x"]})
                self.assertTrue(spec["contract_errors"])

    def test_parallel_aggregate_expressions_keep_shared_input_and_null_groups(self):
        plan = {"final_steps": [{"operator": "Filter_Aggregate", "input": "raw",
            "group_by": ["band"], "aggregations": [
                {"operation": "avg", "input_column": "coalesce(score, 0)", "output_column": "with_zero"},
                {"operation": "avg", "input_column": "where(kind == 'keep', score, null)", "output_column": "selected"},
                {"operation": "avg", "input_column": "score", "output_column": "plain"},
                {"operation": "count_rows", "input_column": "*", "output_column": "n"}]}]}
        data = [{"band": None, "kind": kind, "score": score}
                for kind, score in [("keep", 10), ("other", 30), ("keep", None)]]
        spec = load("spec_runtime").compile_spec(plan, {"raw": list(data[0])})
        self.assertEqual(spec["contract_errors"], [])
        self.assertEqual(self.run_plan(spec, {"raw": data}), [
            {"band": None, "with_zero": 40 / 3, "selected": 10, "plain": 20, "n": 3}])
        self.assertEqual(spec, load("spec_runtime").compile_spec(spec, {"raw": list(data[0])}))

    def test_aggregate_expression_keeps_filters_and_avoids_field_collision(self):
        plan = {"final_steps": [{"operator": "Filter_Aggregate", "operation": "sum",
            "input_column": "score * 2", "output_column": "total",
            "filters": [{"field": "__aggregate_value", "operator": "=", "value": 1}]}]}
        data = [{"score": 5, "__aggregate_value": 1}, {"score": 100, "__aggregate_value": 0}]
        self.assertEqual(self.run_plan(plan, {"raw": data}), [{"total": 10}])

    def test_aggregate_filters_run_before_expression_evaluation(self):
        plan = {"final_steps": [{"operator": "Filter_Aggregate", "operation": "sum",
            "input_column": "score * 2", "output_column": "total",
            "filters": [{"field": "keep", "operator": "=", "value": True}]}]}
        data = [{"score": "5", "keep": True}, {"score": "not a number", "keep": False}]
        self.assertEqual(self.run_plan(plan, {"raw": data}), [{"total": 10}])

    def test_aggregate_expression_preserves_lineage_and_wrong_operation_rejection(self):
        self.plan["final_steps"][0]["target_column"] = "coalesce(score, 0)"
        self.assertEqual(self.build()[0]["contract_errors"], [])
        self.plan["final_steps"][0]["operation"] = "max"
        self.assertIn("component sum", " ".join(self.build()[0]["contract_errors"]))

    def test_aggregate_expression_rejects_unknown_and_unsafe_operands(self):
        for target in ["missing", "coalesce(missing, 0)", "score.sum()", "__import__('os')", "score[0]"]:
            with self.subTest(target=target):
                plan = {"final_steps": [{"operator": "Filter_Aggregate", "operation": "sum",
                         "input_column": target, "output_column": "total"}]}
                spec = load("spec_runtime").compile_spec(plan, {"raw": ["score"]})
                self.assertTrue(spec["contract_errors"])

    def test_exact_field_name_takes_precedence_over_expression_syntax(self):
        plan = {"final_steps": [{"operator": "Filter_Aggregate", "operation": "sum",
                 "input_column": "score * 2", "output_column": "total"}]}
        self.assertEqual(self.run_plan(plan, {"raw": [{"score * 2": 7, "score": 100}]}), [{"total": 7}])

    def test_query_spec_rejects_source_drift_even_with_scoped_prompt(self):
        self.schema["Person"] = {"columns": ["owner", "band"]}
        client = FakeClient({"retrieval_specs": [{"class": "Reading", "entity_key": ["record"],
                                                  "fields": ["record", "score"], "filters": []}]})
        result = load("llm_operators.query_spec").semantic_build_query_spec({
            "query": "Scores by person band", "global_schema": self.schema,
            "retrieved_tables": ["Reading", "Person"],
            "subquestion": {"id": "people", "source_class": "Person"}}, client)["query_spec"]
        self.assertIn("changed assigned source class Person to Reading", " ".join(result["contract_errors"]))
        prompt = client.calls[0]["messages"][0]["content"]
        schema = json.loads(prompt.split("\nSchema: ", 1)[1].split("\n", 1)[0])
        self.assertEqual(set(schema), {"Person"})
        self.assertIn('"class":"Person"', prompt)

    def test_complete_branch_contract_uses_assigned_source_without_model(self):
        branch = {"id": "r", "source_class": "Reading", "required_fields": ["score", "band"],
                  "requirement_ids": ["p"], "retrieval_contract_complete": True}
        requirements = {"predicates": [
            {"id": "p", "source_class": "Reading", "branch_ids": ["r"],
             "field": "score", "operator": ">=", "value": 0, "stage": "scan", "value_type": "number"},
            {"id": "elsewhere", "source_class": "Reading", "branch_ids": ["other"],
             "field": "score", "operator": "<", "value": -10, "stage": "scan"}],
            "joins": [{"left_branch": "r", "right_branch": "people", "left_on": ["owner"], "right_on": ["id"]}]}
        client = FakeClient({"retrieval_specs": [{"class": "Wrong"}]})
        self.schema["Person"] = {"subject_field": "id", "columns": ["id"]}
        result = load("llm_operators.query_spec").semantic_build_query_spec({
            "subquestion": branch, "global_schema": self.schema,
            "decomposition": {"answer_requirements": requirements,
                              "subquestions": [branch, {"id": "people", "source_class": "Person"}]}}, client)["query_spec"]
        self.assertFalse(client.calls)
        self.assertEqual(result["construction"], "declared_branch_contract")
        self.assertEqual(result["contract_errors"], [])
        retrieval = result["retrieval_specs"][0]
        self.assertEqual(retrieval["class"], "Reading")
        self.assertEqual(retrieval["entity_key"], ["record"])
        self.assertEqual(set(retrieval["fields"]), {"record", "score", "band", "owner"})
        self.assertEqual(set(retrieval["optional_fields"]), {"score", "band", "owner"})
        self.assertEqual(retrieval["filters"], [{"field": "score", "operator": ">=", "value": 0, "value_type": "number"}])

    def test_complete_branch_contract_keeps_final_predicates_out_of_scan(self):
        branch = {"id": "r", "source_class": "Reading", "required_fields": ["score"],
                  "retrieval_contract_complete": True}
        requirements = {"predicates": [{"source_class": "Reading", "field": "band",
                         "operator": "=", "value": "high", "stage": "final"}], "joins": []}
        client = FakeClient({})
        spec = load("llm_operators.query_spec").semantic_build_query_spec({
            "subquestion": branch, "global_schema": self.schema,
            "decomposition": {"answer_requirements": requirements}}, client)["query_spec"]
        self.assertFalse(client.calls)
        self.assertEqual(spec["contract_errors"], [])
        self.assertIn("band", spec["retrieval_specs"][0]["fields"])
        self.assertEqual(spec["retrieval_specs"][0]["filters"], [])

    def test_complete_branch_contract_still_validates_fields_and_contradictions(self):
        branch = {"id": "r", "source_class": "Reading", "required_fields": ["missing"],
                  "retrieval_contract_complete": True}
        predicates = [{"source_class": "Reading", "field": "band", "operator": "=", "value": value}
                      for value in ["high", "low"]]
        client = FakeClient({})
        spec = load("llm_operators.query_spec").semantic_build_query_spec({
            "subquestion": branch, "global_schema": self.schema,
            "decomposition": {"answer_requirements": {"predicates": predicates, "joins": []}}}, client)["query_spec"]
        self.assertFalse(client.calls)
        self.assertIn("missing", " ".join(spec["contract_errors"]))
        self.assertIn("Contradictory", " ".join(spec["contract_errors"]))

    def test_incomplete_or_logical_contracts_keep_model_path(self):
        build = load("llm_operators.query_spec")._declared_raw_contract
        branch = {"id": "r", "source_class": "Reading", "required_fields": ["score"],
                  "retrieval_contract_complete": True}
        for changed, requirements in [
            ({"retrieval_contract_complete": False}, {"predicates": [], "joins": []}),
            ({}, {}),
            ({"requirement_ids": ["missing"]}, {"predicates": [], "joins": []}),
            ({}, {"predicates": [{"any": [{"field": "score", "operator": ">", "value": 1}]}], "joins": []}),
        ]:
            with self.subTest(changed=changed, requirements=requirements):
                self.assertIsNone(build({**branch, **changed}, {"answer_requirements": requirements}, self.schema))


if __name__ == "__main__":
    unittest.main()
