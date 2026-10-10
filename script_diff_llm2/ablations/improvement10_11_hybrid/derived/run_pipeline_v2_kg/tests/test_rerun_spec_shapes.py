"""Regression coverage for JSON declaration shapes observed in the failed rerun.

Use small independent rows so successful compilation must also preserve the
requested filter/join/aggregate result. No benchmark answers enter production.
"""

import unittest

from support import load, registry


class RerunSpecShapeTests(unittest.TestCase):
    def setUp(self):
        self.compile = load("spec_runtime").compile_spec
        self.execute = load("execution").execute_spec
        self.ops = registry()

    def run_spec(self, spec, datasets):
        rows, log = self.execute(spec, datasets, self.ops)
        self.assertEqual(load("execution").execution_errors(log), [])
        return rows

    def test_recorded_filter_without_operation_and_parallel_counts(self):
        spec = {
            "pre_steps": [{"id": "nonnull", "operator": "Filter_Aggregate", "inputs": ["q1_processed"],
                           "filters": [{"field": "kind", "operator": "is_not_null"}]}],
            "final_measures": [
                {"operation": "count_rows", "input_column": "*", "output_column": "n", "input": "nonnull", "group_by": ["kind"]},
                {"operation": "sum", "input_column": "amount", "output_column": "total", "input": "nonnull", "group_by": ["kind"]}],
            "projection": ["kind", "n", "total"],
        }
        rows = self.run_spec(spec, {"q1_processed": [{"kind": "A", "amount": 2}, {"kind": "A", "amount": 3}, {"kind": None, "amount": 100}]})
        self.assertEqual(rows, [{"kind": "A", "n": 2, "total": 5}])

    def test_filter_alias_and_empty_aggregations_preserve_filter_before_count(self):
        for operator in ("Filter", "Filter_Aggregate"):
            for operation in ({}, {"operation": "filter"}):
                with self.subTest(operator=operator, operation=operation):
                    spec = {"final_steps": [
                        {"id": "positive", "operator": operator, "input": "raw", **operation,
                         "filters": [{"field": "amount", "operator": ">", "value": 0}],
                         "group_by": [], "aggregations": []},
                        {"operator": "Filter_Aggregate", "input": "positive", "operation": "count_rows",
                         "input_column": "*", "output_column": "n"}], "projection": ["n"]}
                    rows = self.run_spec(spec, {"raw": [{"amount": 2}, {"amount": -3}, {"amount": None}]})
                    self.assertEqual(rows, [{"n": 1}])
                    compiled = self.compile(spec, {"raw": ["amount"]})
                    self.assertEqual(compiled, self.compile(compiled, {"raw": ["amount"]}))

    def test_empty_aggregate_or_conflicting_filter_is_still_rejected(self):
        for step in (
            {"operator": "Filter_Aggregate", "aggregations": []},
            {"operator": "Filter_Aggregate", "operation": "sum", "aggregations": []},
            {"operator": "Filter", "operation": "sum", "input_column": "amount", "output_column": "n"},
            {"operator": "Filter", "condition": "amount > 0"},
            {"operator": "Filter", "filters": [], "aggregations": [
                {"operation": "sum", "input_column": "amount", "output_column": "n"}]},
            {"operator": "Filter_Aggregate", "operation": "filter", "group_by": ["amount"], "aggregations": []},
        ):
            with self.subTest(step=step):
                self.assertTrue(self.compile({"steps": [step]}, {"raw": ["amount"]})["contract_errors"])

    def test_nested_interpretation_keeps_structured_grouping_and_field_owners(self):
        contract = {"group_by": [{"table": "Owners", "column": "segment"}],
                    "bindings": [{"phrase": "segment", "table": "Owners", "column": "segment", "rule_ids": []}]}
        spec = {"answer_requirements": {"group_by": ["segment"], "query_understanding": contract},
                "steps": []}
        normalized = load("spec_contracts").normalize_spec(spec)
        self.assertEqual(normalized["answer_requirements"]["query_understanding"], contract)
        self.assertEqual(normalized.get("normalization_errors", []), [])
        normalized["answer_requirements"]["query_understanding"]["group_by"].clear()
        self.assertTrue(contract["group_by"])

    def test_recorded_join_aliases_follow_named_step(self):
        spec = {
            "merge_steps": [{"step_id": "joined", "operator": "Integrate", "left_branch": "q1_processed", "right_branch": "q2_processed",
                             "left_key": "owner", "right_key": "id", "type": "inner"}],
            "final_measures": [{"id": "agg", "operation": "sum", "input_column": "amount", "output_column": "total", "input": "joined", "group_by": ["name"]}],
            "final_steps": [{"operator": "Order_By", "input": "agg", "column": "total", "direction": "DESC", "limit": 1}],
            "projection": ["name", "total"],
        }
        rows = self.run_spec(spec, {"q1_processed": [{"owner": 1, "amount": 2}, {"owner": 1, "amount": 3}, {"owner": 2, "amount": 4}],
                                    "q2_processed": [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]})
        self.assertEqual(rows, [{"name": "A", "total": 5}])

    def test_recorded_type_operator_and_output_branch(self):
        spec = {"merge_steps": [{"type": "Set_Intersect", "left_branch": "a", "right_branch": "b", "on": "id", "output_branch": "matches"}],
                "final_steps": [{"operation": "Distinct", "input_dataset": "matches", "distinct_on": ["id"], "output_dataset": "answer"}],
                "final_output": "answer", "projection": ["id"]}
        self.assertEqual(self.run_spec(spec, {"a": [{"id": 1}, {"id": 1}, {"id": 2}], "b": [{"id": 1}, {"id": 3}]}), [{"id": 1}])

    def test_recorded_explicit_measure_merge_has_no_extra_terminal(self):
        spec = {
            "merge_steps": [
                {"id": "left_join", "operator": "Integrate", "left": "owners", "right": "left_values", "join_key": ["id"]},
                {"id": "right_join", "operator": "Integrate", "left": "owners", "right": "right_values", "join_key": ["id"]}],
            "final_measures": [
                {"id": "left_avg", "operation": "avg", "input": "left_join", "input_column": "x", "output_column": "avg_x", "group_by": ["group"]},
                {"id": "right_avg", "operation": "avg", "input": "right_join", "input_column": "y", "output_column": "avg_y", "group_by": ["group"]}],
            "final_steps": [{"id": "combined", "operator": "Integrate", "left": "left_avg", "right": "right_avg", "join_key": ["group"], "join_type": "outer"}],
            "projection": ["group", "avg_x", "avg_y"],
        }
        rows = self.run_spec(spec, {"owners": [{"id": 1, "group": "g"}], "left_values": [{"id": 1, "x": 2}, {"id": 1, "x": 4}],
                                    "right_values": [{"id": 1, "y": 10}]})
        self.assertEqual(rows, [{"group": "g", "avg_x": 3, "avg_y": 10}])

    def test_recorded_merge_depends_on_pre_steps_aggregations(self):
        spec = {
            "merge_steps": [{"id": "combined", "operation": "Integrate", "left": "sum_a", "right": "sum_b", "on": ["id"]}],
            "pre_steps": [
                {"id": "sum_a", "operation": "Filter_Aggregate", "input": "a", "group_by": ["id"],
                 "aggregations": [{"operation": "sum", "input_column": "x", "output_column": "sx"}]},
                {"id": "sum_b", "operator": "Filter_Aggregate", "input": "b", "group_by": ["id"],
                 "aggregates": [{"operation": "sum", "input_column": "y", "output_column": "sy"}]}],
            "final_steps": [{"operation": "Math_Compute", "expression": "sx + sy", "output_column": "total"}],
            "projection": ["id", "total"],
        }
        rows = self.run_spec(spec, {"a": [{"id": 1, "x": 2}, {"id": 1, "x": 3}], "b": [{"id": 1, "y": 4}, {"id": 1, "y": 6}]})
        self.assertEqual(rows, [{"id": 1, "total": 15}])

    def test_multiple_nested_aggregates_use_same_rows_and_keep_null_group(self):
        spec = {"steps": [{"id": "agg", "operator": "Filter_Aggregate", "group_by": ["g"], "aggregations": [
                    {"aggregation": "sum", "input_column": "v", "output_column": "total"},
                    {"function": "count", "input_column": "v", "output_column": "n"}]}], "output": "agg"}
        rows = self.run_spec(spec, {"raw": [{"g": None, "v": 2}, {"g": None, "v": None}, {"g": None, "v": 4}]})
        self.assertEqual(rows, [{"g": None, "total": 6, "n": 2}])

    def test_canonical_aliases_recompile_idempotently(self):
        spec = {"steps": [{"step_id": "filtered", "operation": "filter", "input_dataset": "raw",
                           "filter": {"field": "v", "operator": ">", "value": 2}, "output_dataset": "answer"}], "output": "answer"}
        first = self.compile(spec, {"raw": ["v"]})
        self.assertEqual(first["contract_errors"], [])
        self.assertEqual(first, self.compile(first, {"raw": ["v"]}))
        self.assertEqual(self.run_spec(spec, {"raw": [{"v": 1}, {"v": 3}]}), [{"v": 3}])

    def test_unknown_operator_and_dataset_are_still_rejected(self):
        for spec in [
            {"steps": [{"operator": "Guess", "filters": []}]},
            {"steps": [{"filters": []}]},
            {"steps": [{"operation": "Distinct", "input_dataset": "missing"}]},
            {"merge_steps": [{"operator": "Integrate", "on": ["id"]}]}]:
            compiled = self.compile(spec, {"a": ["id"], "b": ["id"]})
            self.assertTrue(compiled["contract_errors"])
            self.assertTrue(all("operator" in step for step in compiled["execution_steps"]))

    def test_conflicting_aliases_are_not_silently_selected(self):
        compiled = self.compile({"steps": [{"operator": "Distinct", "input": "raw", "input_dataset": "other"}]}, {"raw": ["id"], "other": ["id"]})
        self.assertTrue(any("Conflicting step fields" in error for error in compiled["contract_errors"]))

    def test_unknown_aggregation_and_dependency_cycle_remain_errors(self):
        for spec in [
            {"steps": [{"operator": "Filter_Aggregate", "aggregations": [{"operation": "invent_sum", "output_column": "n"}]}]},
            {"merge_steps": [{"id": "a", "operator": "Distinct", "input": "b"}],
             "pre_steps": [{"id": "b", "operator": "Distinct", "input": "a"}]}]:
            self.assertTrue(self.compile(spec, {"raw": ["v"]})["contract_errors"])


if __name__ == "__main__":
    unittest.main()
