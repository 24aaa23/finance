"""Offline regressions for the MC, MC_diverse and TT failure classes."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from support import FakeClient, SOURCE, load, registry


class V3ContractsTests(unittest.TestCase):
    def test_comparison_alternatives_do_not_become_and(self):
        check = load("semantic_contracts").predicate_errors
        equalities = [{"field": "horizon", "operator": "=", "value": value}
                      for value in ["Short-term", "Medium-term"]]
        self.assertTrue(check(equalities))
        self.assertTrue(check([{"all": [equalities[0], {"all": [equalities[1]]}]}]))
        self.assertFalse(check([{"any": equalities}]))
        self.assertFalse(check([{"not": {"all": equalities}}]))
        self.assertFalse(check([{"any": [{"all": equalities}, {"field": "horizon", "value": "Long-term"}]}]))
        self.assertFalse(check([{"field": "horizon", "operator": "in", "value": ["Short-term", "Medium-term"]}]))

    def test_decomposition_routes_impossible_predicates_to_repair(self):
        plan = {"subquestions": [{"id": "a", "source_class": "Profile"}],
                "answer_requirements": {"predicates": [
                    {"source_class": "Profile", "field": "risk", "operator": "=", "value": value,
                     "branch_ids": ["a"]} for value in ["Conservative", "Aggressive"]]}}
        result = load("llm_operators.decompose")._cleanup_decomposition(plan, "compare", [])
        self.assertIn("Contradictory", " ".join(result["selected_decomposition"]["contract_errors"]))
        plan["subquestions"].append({"id": "b", "source_class": "Profile"})
        plan["answer_requirements"]["predicates"][1]["branch_ids"] = ["b"]
        result = load("llm_operators.decompose")._cleanup_decomposition(plan, "both", [])
        self.assertFalse(result["selected_decomposition"]["contract_errors"])

    def test_null_comparison_fails_compile_but_presence_test_executes(self):
        compiler = load("spec_runtime").compile_spec
        plan = {"final_steps": [{"operator": "Filter_Aggregate", "operation": "filter",
                "filters": [{"field": "month", "operator": "!=", "value": None}]}]}
        self.assertIn("presence test", " ".join(compiler(plan, {"raw": ["month"]})["contract_errors"]))
        plan["final_steps"][0]["filters"][0]["operator"] = "is_not_null"
        rows, log = load("execution").execute_spec(plan, {"raw": [{"month": "2025-01"}, {"month": None}]}, registry())
        self.assertFalse(load("execution").execution_errors(log))
        self.assertEqual(rows, [{"month": "2025-01"}])

    def fixture(self):
        schema = {"Goal": {"subject_field": "goal", "columns": [
            {"name": "goal"}, {"name": "investor", "datatype": "object_reference (points to: Investor)"},
            {"name": "progress"}, {"name": "risk"}]}}
        profiles = [{"id": "goals", "source_class": "Goal", "fields": ["goal", "investor", "progress", "risk"]}]
        requirements = {"metrics": [{"output_column": "mean_progress", "source_class": "Goal",
            "operand_fields": ["progress"], "entity_key": "investor", "inner_aggregation": "avg", "outer_aggregation": "avg"}]}
        return schema, profiles, requirements

    def check(self, plan, profiles, schema, requirements):
        spec = load("spec_runtime").compile_spec(plan, {p["id"]: p["fields"] for p in profiles})
        self.assertFalse(spec["contract_errors"], spec["contract_errors"])
        return load("semantic_contracts").final_semantic_errors(spec, profiles, schema, requirements)

    def test_pooled_average_rejected_and_investor_first_average_correct(self):
        schema, profiles, requirements = self.fixture()
        pooled = {"final_steps": [{"operator": "Filter_Aggregate", "operation": "avg",
            "group_by": ["risk"], "target_column": "progress", "output_column": "mean_progress"}]}
        self.assertIn("per Goal.investor", " ".join(self.check(pooled, profiles, schema, requirements)))
        correct = {"final_steps": [
            {"operator": "Filter_Aggregate", "operation": "avg", "group_by": ["investor", "risk"],
             "target_column": "progress", "output_column": "investor_progress"},
            {"operator": "Filter_Aggregate", "operation": "avg", "group_by": ["risk"],
             "target_column": "investor_progress", "output_column": "mean_progress"}]}
        self.assertFalse(self.check(correct, profiles, schema, requirements))
        data = {"goals": [{"goal": str(i), "investor": investor, "risk": "Low", "progress": progress}
                          for i, (investor, progress) in enumerate([("A", 0), ("A", 100), ("B", 90)])]}
        rows, log = load("execution").execute_spec(correct, data, registry())
        self.assertFalse(load("execution").execution_errors(log))
        self.assertEqual(rows, [{"risk": "Low", "mean_progress": 70.0}])

    def test_wrong_metric_source_or_outer_operation_rejected(self):
        schema, profiles, requirements = self.fixture()
        plan = {"final_steps": [{"operator": "Filter_Aggregate", "operation": "sum",
                "target_column": "progress", "output_column": "mean_progress", "group_by": ["risk"]}]}
        requirements["metrics"][0]["source_class"] = "Other"
        errors = " ".join(self.check(plan, profiles, schema, requirements))
        self.assertIn("wrong source/operands", errors)
        self.assertIn("outer avg", errors)

    def test_grouping_by_raw_identity_is_not_investor_first(self):
        schema, profiles, requirements = self.fixture()
        plan = {"final_steps": [
            {"operator": "Filter_Aggregate", "operation": "avg", "group_by": ["goal", "investor", "risk"],
             "target_column": "progress", "output_column": "investor_progress"},
            {"operator": "Filter_Aggregate", "operation": "avg", "group_by": ["risk"],
             "target_column": "investor_progress", "output_column": "mean_progress"}]}
        self.assertIn("per Goal.investor", " ".join(self.check(plan, profiles, schema, requirements)))

    def test_composite_terms_survive_join_and_formula_lineage(self):
        schema = {source: {"subject_field": "record", "columns": [{"name": "record"},
                    {"name": "investor", "datatype": "object_reference (points to: Investor)"}, {"name": "amount"}]}
                  for source in ["Cash", "Action"]}
        profiles = [{"id": source, "source_class": source, "fields": ["record", "investor", "amount"]} for source in schema]
        plan = {"final_steps": [
            {"id": "cash", "operator": "Filter_Aggregate", "input": "Cash", "group_by": ["investor"],
             "operation": "sum", "target_column": "amount", "output_column": "ncf"},
            {"id": "action", "operator": "Filter_Aggregate", "input": "Action", "group_by": ["investor"],
             "operation": "sum", "target_column": "amount", "output_column": "reb"},
            {"operator": "Integrate", "inputs": ["cash", "action"], "join_key": "investor", "join_type": "inner"},
            {"operator": "Math_Compute", "expression": "ncf + reb", "output_column": "combined"}],
            "projection": ["investor", "combined"]}
        requirements = {"metrics": [{"output_column": "combined", "components": [
            {"source_class": source, "operand_fields": ["amount"], "entity_key": "investor", "inner_aggregation": "sum"}
            for source in schema]}]}
        self.assertFalse(self.check(plan, profiles, schema, requirements))
        plan["final_steps"][1]["operation"] = "avg"
        self.assertIn("component sum per Action.investor", " ".join(self.check(plan, profiles, schema, requirements)))

    def test_compiler_combines_same_input_entity_measures_safely(self):
        schema, profiles, _ = self.fixture()
        plan = {"final_steps": [{"operator": "Filter_Aggregate", "group_by": ["investor"], "aggregations": [
            {"operation": "sum", "input_column": "progress", "output_column": "total"},
            {"operation": "count", "input_column": "progress", "output_column": "n"}]}]}
        self.assertFalse(self.check(plan, profiles, schema, {}))

    def test_missing_entity_ids_cannot_be_explicitly_joined_as_equal(self):
        schema = {"Investor": {"subject_field": "id", "columns": [{"name": "id"}]}}
        profiles = [{"id": name, "source_class": "Investor", "fields": ["id"]} for name in ["a", "b"]]
        plan = {"final_steps": [{"operator": "Integrate", "inputs": ["a", "b"], "join_key": "id", "nulls_equal": True}]}
        self.assertIn("missing entity identities", " ".join(self.check(plan, profiles, schema, {})))

    def test_group_owner_cannot_be_an_unrelated_dimension(self):
        schema, profiles, requirements = self.fixture()
        schema["Investor"] = {"columns": [{"name": "risk"}]}
        requirements["metrics"][0]["group_owner"] = "Investor"
        requirements["metrics"][0]["inner_aggregation"] = "none"
        plan = {"final_steps": [{"operator": "Filter_Aggregate", "operation": "avg", "group_by": ["risk"],
                "target_column": "progress", "output_column": "mean_progress"}]}
        self.assertIn("wrong source", " ".join(self.check(plan, profiles, schema, requirements)))

    def test_final_join_rejects_different_entity_identity_domains(self):
        schema = {"Event": {"columns": [{"name": "action", "datatype": "object_reference (points to: Action)"}]},
                  "Scenario": {"columns": [{"name": "decision", "datatype": "object_reference (points to: Decision)"}]}}
        profiles = [{"id": "a", "source_class": "Event", "fields": ["action"]},
                    {"id": "b", "source_class": "Scenario", "fields": ["decision"]}]
        plan = {"final_steps": [{"operator": "Math_Compute", "input": "a", "expression": "column('action')", "output_column": "key", "id": "copy"},
                {"operator": "Integrate", "inputs": ["copy", "b"], "left_on": ["key"], "right_on": ["decision"]}]}
        self.assertIn("different entity classes", " ".join(self.check(plan, profiles, schema, {})))
        schema["Scenario"]["columns"][0]["datatype"] = "object_reference (points to: Action)"
        self.assertFalse(self.check(plan, profiles, schema, {}))

    def test_null_group_policy_is_separate_from_metric_presence(self):
        profiles = [{"id": "a", "source_class": "Profile", "fields": ["label", "score"]}]
        requirements = {"null_policy": {"label_groups": [{"field": "label", "policy": "exclude"}]}}
        only_score = {"operator": "Filter_Aggregate", "operation": "filter", "filters": [{"field": "score", "operator": "is_not_null"}]}
        order = {"operator": "Order_By", "order_by": [{"column": "score", "direction": "DESC"}], "limit": 1}
        label = {"operator": "Filter_Aggregate", "operation": "filter", "filters": [{"field": "label", "operator": "is_not_null"}]}
        self.assertTrue(self.check({"final_steps": [only_score, order]}, profiles, {}, requirements))
        self.assertTrue(self.check({"final_steps": [only_score, order, label]}, profiles, {}, requirements))
        self.assertFalse(self.check({"final_steps": [only_score, label, order]}, profiles, {}, requirements))
        requirements["null_policy"]["label_groups"][0]["policy"] = "keep"
        self.assertFalse(self.check({"final_steps": [only_score, order]}, profiles, {}, requirements))
        self.assertTrue(self.check({"final_steps": [only_score, label, order]}, profiles, {}, requirements))

    def test_metric_operands_are_retained_in_source_branch(self):
        plan = {"subquestions": [{"id": "a", "source_class": "Goal"}],
                "answer_requirements": {"metrics": [{"source_class": "Goal", "operand_fields": ["before", "after"], "entity_key": "investor"}]}}
        result = load("llm_operators.decompose")._cleanup_decomposition(plan, "change", [])
        self.assertCountEqual(result["selected_decomposition"]["subquestions"][0]["required_fields"], ["before", "after", "investor"])

    def test_count_rows_retains_source_for_per_investor_contract(self):
        schema, profiles, requirements = self.fixture()
        requirements["metrics"][0].update(operand_fields=["goal"], inner_aggregation="count_rows")
        plan = {"final_steps": [
            {"operator": "Filter_Aggregate", "operation": "count_rows", "target_column": "*",
             "group_by": ["investor", "risk"], "output_column": "n"},
            {"operator": "Filter_Aggregate", "operation": "avg", "target_column": "n",
             "group_by": ["risk"], "output_column": "mean_progress"}]}
        self.assertFalse(self.check(plan, profiles, schema, requirements))
        requirements["metrics"][0]["source_class"] = "Other"
        self.assertTrue(self.check(plan, profiles, schema, requirements))

    def test_left_join_preserves_left_label_presence_but_not_right(self):
        profiles = [{"id": name, "source_class": name, "fields": ["id", "label"]} for name in ["a", "b"]]
        plan = {"final_steps": [
            {"operator": "Filter_Aggregate", "input": "a", "id": "clean_a", "operation": "filter",
             "filters": [{"field": "label", "operator": "is_not_null"}]},
            {"operator": "Filter_Aggregate", "input": "b", "id": "clean_b", "operation": "filter",
             "filters": [{"field": "label", "operator": "is_not_null"}]},
            {"operator": "Integrate", "inputs": ["clean_a", "clean_b"], "join_key": "id", "join_type": "left"}]}
        requirements = {"null_policy": {"label_groups": [{"field": "label", "policy": "exclude"}]}}
        self.assertFalse(self.check(plan, profiles, {}, requirements))
        requirements["null_policy"]["label_groups"][0]["field"] = "label_right"
        self.assertTrue(self.check(plan, profiles, {}, requirements))
        plan["final_steps"][-1]["join_type"] = "right"
        self.assertFalse(self.check(plan, profiles, {}, requirements))

    def test_raw_presence_filter_satisfies_label_policy(self):
        profiles = [{"id": "a", "source_class": "Profile", "fields": ["label"], "retrieval_specs": [
            {"filters": [{"field": "label", "operator": "is_not_null"}]}]}]
        requirements = {"null_policy": {"label_groups": [{"field": "label", "policy": "exclude"}]}}
        self.assertFalse(self.check({"final_steps": []}, profiles, {}, requirements))
        profiles[0]["retrieval_specs"][0]["filters"] = [{"any": [
            {"field": "label", "operator": "is_not_null"}, {"field": "label", "operator": "is_null"}]}]
        self.assertTrue(self.check({"final_steps": []}, profiles, {}, requirements))

    def test_null_policy_and_operand_shape_errors_request_upstream_repair(self):
        cases = [{"null_policy": {"label_groups": None}},
                 {"null_policy": {"label_groups": [{"field": "label", "policy": {"keep": True}}]}},
                 {"metrics": [{"operand_fields": "amount"}]},
                 {"metrics": [{"operand_fields": None}]},
                 {"metrics": [{"components": ["bad"]}]},
                 {"metrics": [{"entity_key": ["investor"]}]},
                 {"metrics": [{"source_class": {"class": "Goal"}}]}]
        for requirements in cases:
            with self.subTest(requirements=requirements):
                plan = {"subquestions": [{"id": "a", "source_class": "Goal"}], "answer_requirements": requirements}
                result = load("llm_operators.decompose")._cleanup_decomposition(plan, "q", [])
                self.assertTrue(result["selected_decomposition"]["contract_errors"])
                client = FakeClient("must not be called")
                result = load("llm_operators.final_spec").semantic_build_final_spec(
                    {"answer_requirements": requirements}, client)
                self.assertEqual(result["final_spec"]["repair_stage"], "Decompose")
                self.assertFalse(client.calls)

    def test_final_builder_enforces_contract_and_passes_full_context(self):
        schema, profiles, requirements = self.fixture()
        branches = [{**p, "retrieval_specs": [{"class": p["source_class"]}]} for p in profiles]
        client = FakeClient({"final_steps": [{"operator": "Filter_Aggregate", "operation": "avg", "group_by": ["risk"],
            "target_column": "progress", "output_column": "mean_progress"}], "projection": ["risk", "mean_progress"]})
        result = load("llm_operators.final_spec").semantic_build_final_spec(
            {"processed_datasets": branches, "global_schema": schema, "answer_requirements": requirements}, client)
        self.assertTrue(result["final_spec"]["contract_errors"])
        self.assertIn('"inner_aggregation": "avg"', client.calls[0]["messages"][0]["content"])

    def test_rule_pack_band_boundaries_and_missing_values(self):
        pack = load("business_context").load_business_rule_pack()
        result = registry()["Bucket"]({"data": [{"x": x} for x in [None, 59.99, 60, 79.99, 80, 100]],
            "input_column": "x", "output_column": "band", "rules": pack["rules"]["goal_match_bands"]["bands"]})
        self.assertEqual([r["band"] for r in result["data"]], [None, "At risk", "Needs attention", "Needs attention", "On track", "On track"])
        self.assertIn("ALL", pack["rules"]["composite_scores"]["normalization_policy"]["population"])

    def test_rule_pack_change_invalidates_resume_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "runner.py").write_text("pass", encoding="utf-8")
            pack = root / "business_rule_pack.json"
            pack.write_text('{"version":1}', encoding="utf-8")
            identity = load("run_identity").build_run_identity
            first = identity(root, {}, {})[0]
            pack.write_text('{"version":2}', encoding="utf-8")
            self.assertNotEqual(first, identity(root, {}, {})[0])

    def test_all_nine_easy_commands_dry_run_without_api(self):
        for category in ["ARC", "BSQ", "EC", "MC", "MC_diverse", "RC", "SQA", "TT", "WM"]:
            result = subprocess.run([sys.executable, str(SOURCE / "run.py"), category, "--dry-run"],
                                    capture_output=True, text=True, cwd=SOURCE.parent)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("pipeline_output_v3", result.stdout)
            self.assertIn("Limit: all", result.stdout)

    def test_review_is_enabled_by_default_but_can_be_disabled(self):
        with patch.dict(os.environ, {}, clear=True):
            client = FakeClient({"is_valid": True, "reason": "checked"})
            result = load("llm_operators.validate").semantic_validate({"data": []}, client)
            self.assertTrue(result["validation"]["is_valid"])
            result = load("llm_operators.validate").semantic_validate({"data": [], "semantic_review": False}, client)
            self.assertEqual(result["validation"]["status"], "not_requested")
            self.assertEqual(len(client.calls), 1)


if __name__ == "__main__":
    unittest.main()
