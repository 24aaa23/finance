import copy
import ast
import contextlib
import io
import json
import sqlite3
import unittest

from support import FakeClient, load, registry, nx, SOURCE


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.ops = registry()
        self.execute = load("execution").execute_spec
        self.compile = load("spec_runtime").compile_spec

    def run_plan(self, spec, rows, schema=None, ops=None):
        return self.execute(spec, {"raw": rows}, ops or self.ops, dataset_schemas={"raw": schema} if schema else None)

    def test_parallel_scalar_measures_then_formula(self):
        spec = {"final_measures": [
            {"operation": "sum", "input_column": "a", "output_column": "sa", "input": "previous"},
            {"operation": "sum", "input_column": "b", "output_column": "sb", "input": "previous"}],
            "final_steps": [{"operator": "Math_Compute", "expression": "sa + sb", "output_column": "total"}],
            "projection": ["total"]}
        rows, log = self.run_plan(spec, [{"a": 10, "b": 1}, {"a": 20, "b": 2}])
        self.assertEqual(rows, [{"total": 33}])
        self.assertFalse(load("execution").execution_errors(log))

    def test_having_filter_and_order_preserved(self):
        spec = {"final_group_by": ["group"], "final_measures": [
            {"operation": "sum", "input_column": "value", "output_column": "total"}],
            "final_steps": [
                {"operator": "Filter_Aggregate", "operation": "filter", "filters": [{"field": "total", "operator": ">", "value": 10}]},
                {"operator": "Order_By", "order_by": [{"column": "total", "direction": "DESC"}], "limit": 1}],
            "projection": ["group", "total"]}
        rows, log = self.run_plan(spec, [{"group": "a", "value": 7}, {"group": "a", "value": 8}, {"group": "b", "value": 2}])
        self.assertEqual(rows, [{"group": "a", "total": 15}])

    def test_no_implicit_rounding(self):
        rows, _ = self.run_plan({"final_steps": [{"operator": "Math_Compute", "expression": "a / b", "output_column": "r"}]}, [{"a": 1, "b": 3}])
        self.assertEqual(rows[0]["r"], 1 / 3)

    def test_group_nulls_multiple_measures(self):
        spec = {"final_group_by": ["g"], "final_measures": [
            {"operation": "sum", "input_column": "v", "output_column": "s"},
            {"operation": "count", "input_column": "v", "output_column": "n"}]}
        rows, log = self.run_plan(spec, [{"g": None, "v": 2}, {"g": None, "v": 3}])
        self.assertEqual(rows, [{"g": None, "s": 5, "n": 2}])

    def test_count_null_distinct_and_rows(self):
        data = [{"v": None}, {"v": 4}, {"v": 4}]
        for operation, target, expected in [("count", "v", 2), ("count_distinct", "v", 1), ("count", "*", 3)]:
            result = self.ops["Filter_Aggregate"]({"data": data, "strict_spec": True, "operation": operation, "target_column": target, "output_column": "n"})
            self.assertEqual(result["data"], [{"n": expected}])

    def test_empty_scalar_aggregates(self):
        for operation, target, expected in [("count", "*", 0), ("count", "v", 0), ("sum", "v", None), ("avg", "v", None)]:
            result = self.ops["Filter_Aggregate"]({"data": [], "input_schema": ["v"], "strict_spec": True, "operation": operation, "target_column": target, "output_column": "n"})
            self.assertEqual(result["data"], [{"n": expected}])

    def test_empty_grouped_aggregate(self):
        result = self.ops["Filter_Aggregate"]({"data": [], "input_schema": ["g", "v"], "operation": "sum", "target_column": "v", "output_column": "s", "group_by": ["g"]})
        self.assertEqual(result["data"], [])
        self.assertNotIn("error", result)

    def test_dropped_raw_field_rejected(self):
        spec = {"steps": [{"id": "s", "operator": "Filter_Aggregate", "operation": "sum", "target_column": "v", "output_column": "total"},
                           {"operator": "Math_Compute", "input": "s", "expression": "v * 2", "output_column": "bad"}]}
        self.assertTrue(self.compile(spec, {"raw": ["v"]})["contract_errors"])

    def test_projection_cannot_select_preaggregate_fields(self):
        spec = {"final_measures": [{"operation": "sum", "input_column": "v", "output_column": "total"}], "projection": ["v"]}
        self.assertTrue(self.compile(spec, {"raw": ["v"]})["contract_errors"])

    def test_output_column_can_retain_input_name(self):
        rows, log = self.run_plan({"final_measures": [{"operation": "sum", "input_column": "v", "output_column": "v"}]}, [{"v": 2}, {"v": 4}])
        self.assertEqual(rows, [{"v": 6}])

    def test_compilation_idempotent(self):
        spec = {"steps": [{"operator": "Math_Compute", "expression": "v * 2", "output_column": "d"}]}
        first = self.compile(spec, {"raw": ["v"]})
        second = self.compile(first, {"raw": ["v"]})
        self.assertEqual(first, second)

    def test_schema_metadata_does_not_silently_project_rows(self):
        rows, log = self.run_plan({"steps": [], "output_schema": ["id"]}, [{"id": 1, "v": 2}])
        self.assertEqual(rows, [{"id": 1, "v": 2}])

    def test_unknown_operator_and_bypass_are_errors(self):
        for spec in [{"steps": [{"operator": "MadeUp"}]},
                     {"steps": [{"operator": "Math_Compute", "expression": "v * 2", "output_column": "d"}], "output": "raw"}]:
            self.assertTrue(self.compile(spec, {"raw": ["v"]})["contract_errors"])

    def test_runtime_error_not_empty_success(self):
        ops = {**self.ops, "Math_Compute": lambda inputs: {"data": [], "error": "synthetic operator failure"}}
        rows, log = self.run_plan({"steps": [{"operator": "Math_Compute", "expression": "v * 2", "output_column": "d"}]}, [{"v": 2}], ops=ops)
        self.assertEqual(rows, [])
        self.assertIn("synthetic operator failure", log[-1]["error"])

    def test_unused_retrieval_is_visible_without_becoming_execution_error(self):
        result = self.compile({"final_output": "a"}, {"a": ["id"], "b": ["id"]})
        self.assertFalse(result["contract_errors"])
        self.assertTrue(result["plan_warnings"])
        self.assertTrue(self.compile({"final_output": "missing"}, {"a": ["id"]})["contract_errors"])

    def test_unsafe_expressions_rejected(self):
        for expression in ["__import__('os')", "a.__class__", "[x for x in a]", "open('x')"]:
            result = self.ops["Math_Compute"]({"data": [{"a": 1}], "expression": expression, "output_column": "x"})
            self.assertIn("error", result)

    def test_math_null_zero_and_exact_fields(self):
        result = self.ops["Math_Compute"]({"data": [{"a": None, "b": 0}, {"a": 2, "b": 0}], "expression": "a / b", "output_column": "r", "strict_spec": True})
        self.assertEqual([row["r"] for row in result["data"]], [None, None])
        result = self.ops["Math_Compute"]({"data": [{"Amount": 2}], "expression": "amount * 2", "output_column": "r", "strict_spec": True})
        self.assertIn("error", result)

    def test_sort_numeric_multi_key(self):
        result = self.ops["Order_By"]({"data": [{"v": "2", "name": "z"}, {"v": "10", "name": "b"}, {"v": "10", "name": "a"}],
            "order_by": [{"column": "v", "direction": "DESC"}, {"column": "name", "direction": "ASC"}], "limit": 2, "strict_spec": True})
        self.assertEqual([r["name"] for r in result["data"]], ["a", "b"])

    def test_invalid_order_does_not_return_head(self):
        for fields in [{"column": "missing"}, {"column": "v", "direction": "sideways"}, {"column": "v", "limit": -1}]:
            self.assertIn("error", self.ops["Order_By"]({"data": [{"v": 2}], "strict_spec": True, **fields}))

    def test_exact_predicate_literals(self):
        result = self.ops["Filter_Aggregate"]({"data": [{"action": "Rebalance Sell"}, {"action": "Sell"}], "operation": "filter",
            "filters": [{"field": "action", "operator": "=", "value": "Rebalance Sell"}], "strict_spec": True})
        self.assertEqual(result["data"], [{"action": "Rebalance Sell"}])

    def test_null_filter_three_valued_logic(self):
        result = self.ops["Filter_Aggregate"]({"data": [{"v": None}, {"v": 2}], "filters": [{"field": "v", "operator": "!=", "value": 3}], "strict_spec": True})
        self.assertEqual(result["data"], [{"v": 2}])

    def test_boolean_predicates_against_sql(self):
        data = [{"x": None, "y": 1}, {"x": 2, "y": 0}, {"x": 3, "y": 1}, {"x": 4, "y": 0}]
        predicate = {"not": {"any": [{"field": "x", "operator": "=", "value": 2}, {"field": "y", "operator": "=", "value": 1}]}}
        rows, log = self.run_plan({"steps": [{"operator": "Filter_Aggregate", "operation": "filter", "filters": [predicate]}]}, data)
        with sqlite3.connect(":memory:") as db:
            db.execute("CREATE TABLE t(x,y)")
            db.executemany("INSERT INTO t VALUES (?,?)", [(r["x"], r["y"]) for r in data])
            expected = [dict(zip(["x", "y"], row)) for row in db.execute("SELECT x,y FROM t WHERE NOT (x=2 OR y=1)")]
        self.assertEqual(rows, expected)

    def test_grouped_aggregates_against_sql(self):
        data = [{"g": g, "v": value} for g, value in [(None, None), (None, 2), ("a", 2), ("a", 2), ("a", 3), ("b", None)]]
        spec = {"final_group_by": ["g"], "final_measures": [
            {"operation": op, "input_column": target, "output_column": output}
            for op, target, output in [("sum", "v", "s"), ("avg", "v", "a"), ("count", "v", "n"), ("count_distinct", "v", "d"), ("count", "*", "r")]]}
        rows, log = self.run_plan(spec, data)
        with sqlite3.connect(":memory:") as db:
            db.execute("CREATE TABLE t(g,v)")
            db.executemany("INSERT INTO t VALUES (?,?)", [(r["g"], r["v"]) for r in data])
            expected = [dict(zip(["g", "s", "a", "n", "d", "r"], row)) for row in db.execute("SELECT g,SUM(v),AVG(v),COUNT(v),COUNT(DISTINCT v),COUNT(*) FROM t GROUP BY g")]
        self.assertEqual(sorted(rows, key=lambda r: str(r["g"])), sorted(expected, key=lambda r: str(r["g"])))

    def test_distinct_precedes_top_k(self):
        rows, log = self.run_plan({"distinct_on": ["id"], "final_steps": [{"operator": "Order_By", "column": "v", "direction": "DESC", "limit": 2}]},
                                 [{"id": 1, "v": 9}, {"id": 1, "v": 9}, {"id": 2, "v": 8}])
        self.assertEqual([r["id"] for r in rows], [1, 2])

    def test_empty_date_transformation_retains_schema(self):
        rows, log = self.run_plan({"steps": [{"operator": "Date_Extract", "input_column": "date", "part": "month", "output_column": "month"}]}, [], ["date"])
        self.assertEqual(rows, [])
        self.assertFalse(load("execution").execution_errors(log))

    def test_explicit_limit_without_order(self):
        rows, log = self.run_plan({"final_steps": [{"operator": "Order_By", "limit": 1}]}, [{"v": 2}, {"v": 1}])
        self.assertEqual(rows, [{"v": 2}])

    def test_typed_numeric_filter(self):
        result = self.ops["Filter_Aggregate"]({"data": [{"v": "10"}, {"v": "2"}], "strict_spec": True,
             "filters": [{"field": "v", "operator": "=", "value": "10", "value_type": "number"}]})
        self.assertEqual(result["data"], [{"v": "10"}])

    def test_unbound_rdf_value_is_null_not_empty_string(self):
        path = SOURCE / "non_llm_operators/fuseki.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        function = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == "parse_fuseki_sparql_json")
        from typing import Any, Dict
        env = {"Any": Any, "Dict": Dict}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), env)
        payload = {"head": {"vars": ["id", "label"]}, "results": {"bindings": [{"id": {"value": "a"}}]}}
        self.assertEqual(env[function.name](payload), [{"id": "a", "label": None}])


class RelationalTests(unittest.TestCase):
    def setUp(self):
        self.rel = load("relational")

    def test_inner_join_empty_branch(self):
        result = self.rel.integrate({"branch_data_lists": [[{"id": 1}], []], "branch_schemas": [["id"], ["id", "v"]], "join_key": ["id"]})
        self.assertEqual(result["data"], [])

    def test_left_join_empty_branch(self):
        result = self.rel.integrate({"branch_data_lists": [[{"id": 1}], []], "branch_schemas": [["id"], ["id", "v"]], "join_key": ["id"], "join_type": "left"})
        self.assertEqual(result["data"], [{"id": 1, "v": None}])

    def test_composite_keys_do_not_collapse_null_positions(self):
        result = self.rel.set_operation({"branch_data_lists": [[{"a": None, "b": "x"}], [{"a": "x", "b": None}]], "join_key": ["a", "b"]}, "Set_Intersect")
        self.assertEqual(result["data"], [])

    def test_sql_join_nulls_and_explicit_group_nulls(self):
        args = {"branch_data_lists": [[{"id": None, "a": 1}], [{"id": None, "b": 2}]], "join_key": "id"}
        self.assertEqual(self.rel.integrate(args)["data"], [])
        self.assertEqual(len(self.rel.integrate({**args, "nulls_equal": True})["data"]), 1)

    def test_join_preserves_multiplicity(self):
        args = {"branch_data_lists": [[{"id": 1, "a": i} for i in range(3)], [{"id": 1, "b": i} for i in range(4)]], "join_key": "id"}
        self.assertEqual(len(self.rel.integrate(args)["data"]), 12)
        self.assertIn("error", self.rel.integrate({**args, "cardinality": "one_to_one"}))

    def test_set_difference_deduplicates(self):
        result = self.rel.set_operation({"branch_data_lists": [[{"id": 1}, {"id": 1}, {"id": 2}], [{"id": 2}]], "join_key": "id"}, "Set_Difference")
        self.assertEqual(result["data"], [{"id": 1}])

    def test_missing_composite_key_is_error(self):
        result = self.rel.integrate({"branch_data_lists": [[{"id": 1, "g": 1}], [{"id": 1}]], "join_key": ["id", "g"]})
        self.assertIn("error", result)

    def test_differently_named_set_keys(self):
        result = self.rel.set_operation({"branch_data_lists": [[{"id": 1}], [{"owner": 1}]], "left_on": ["id"], "right_on": ["owner"]}, "Set_Intersect")
        self.assertEqual(result["data"], [{"id": 1}])


class PlanningTests(unittest.TestCase):
    def test_final_builder_keeps_having(self):
        payload = {"final_group_by": ["g"], "final_measures": [{"operation": "sum", "input_column": "v", "output_column": "total"}],
                   "final_steps": [{"operator": "Filter_Aggregate", "operation": "filter", "filters": [{"field": "total", "operator": ">", "value": 10}]}]}
        result = load("llm_operators.final_spec").semantic_build_final_spec({"processed_datasets": [{"id": "a", "fields": ["g", "v"]}]}, FakeClient(payload))["final_spec"]
        self.assertFalse(result["contract_errors"])
        self.assertEqual(result["execution_steps"][-1]["operation"], "filter")

    def test_processing_pass_through_preserves_population(self):
        payload = {"steps": [], "output": "raw", "entity_grain": []}
        result = load("llm_operators.processing_spec").semantic_build_processing_spec({"data": [{"v": 1}], "subquestion_id": "q1"}, FakeClient(payload))["processing_spec"]
        self.assertFalse(result["contract_errors"])
        self.assertEqual(result["compiled_output_schema"], ["v"])

    def test_bad_json_is_not_silent_valid_plan(self):
        for module, function, key in [("final_spec", "semantic_build_final_spec", "final_spec")]:
            result = getattr(load("llm_operators." + module), function)({}, FakeClient("invalid json"))[key]
            self.assertTrue(result["contract_errors"])

    def test_validator_rejects_error_before_call(self):
        client = FakeClient({"is_valid": True})
        result = load("llm_operators.validate").semantic_validate({"data": [], "execution_errors": [{"error": "broken"}]}, client)
        self.assertFalse(result["validation"]["is_valid"])
        self.assertEqual(len(client.calls), 0)

    def test_empty_answer_is_not_auto_approved(self):
        client = FakeClient({"is_valid": False, "reason": "missing condition", "repair_stage": "Decompose"})
        result = load("llm_operators.validate").semantic_validate({"query": "Which records?", "semantic_review": True, "data": [], "query_spec": {"query_type": "set_logic"}}, client)
        self.assertFalse(result["validation"]["is_valid"])
        self.assertEqual(len(client.calls), 1)

    def test_global_predicate_is_not_silently_changed(self):
        spec = {"branch_id": "q1", "retrieval_specs": [{"class": "Thing", "fields": ["id", "action"], "filters": [{"field": "action", "operator": "=", "value": "B"}]}]}
        decomposition = {"answer_requirements": {"predicates": [{"id": "p1", "source_class": "Thing", "branch_ids": ["q1"], "field": "action", "operator": "=", "value": "A"}]}}
        errors = load("llm_operators.query_spec")._answer_requirement_errors(spec, decomposition, {"Thing": {"columns": ["id", "action"]}})
        self.assertTrue(errors)

    def test_decomposition_preserves_metric_weighting(self):
        raw = {"selected_decomposition": {"subquestions": [{"id": "q", "source_class": "Thing", "question": "x", "requirement_ids": ["p"]}],
                "answer_requirements": {"metrics": [{"output_column": "m", "population": "facts", "weighting": "by observation"}], "predicates": [{"id": "p", "value": "Exact Literal"}]}}}
        cleaned = load("llm_operators.decompose")._cleanup_decomposition(copy.deepcopy(raw), "original", [])
        req = cleaned["selected_decomposition"]["answer_requirements"]
        self.assertEqual(req["metrics"][0]["weighting"], "by observation")
        self.assertEqual(req["predicates"][0]["value"], "Exact Literal")

    def test_empty_query_spec_is_rejected(self):
        spec = {"retrieval_specs": [{"class": "Thing", "fields": [], "entity_key": []}]}
        self.assertTrue(load("spec_contracts").validate_query_spec_contract(spec, {"Thing": {"columns": ["id"]}}))


class ExecutorIntegrationTests(unittest.TestCase):
    def run_dag(self, empty=False, broken=False, semantic_repair=False, pre_reject=False, repair_broken=False):
        ops = registry()
        compile_spec = load("spec_runtime").compile_spec
        counts = {"Processing_Spec": 0, "Final_Spec": 0, "Validate": 0, "Scan": 0}
        def query_spec(inputs):
            return {"query_spec": {"retrieval_specs": [{"fields": ["id", "v"]}], "contract_errors": []}}
        def scan(inputs):
            counts["Scan"] += 1
            return {"data": [] if empty else [{"id": "a", "v": 2}, {"id": "b", "v": 3}], "columns": ["id", "v"], "status": "success", "row_count": 0 if empty else 2}
        def processing(inputs):
            counts["Processing_Spec"] += 1
            spec = {"steps": [], "output": "raw", "output_id": "q1_processed"}
            if broken:
                spec["steps"] = [{"operator": "Math_Compute", "expression": "v * 2", "output_column": "twice"}]
                spec.pop("output")
            return {"processing_spec": compile_spec(spec, {"raw": inputs["input_schema"]})}
        def final(inputs):
            counts["Final_Spec"] += 1
            spec = {"final_steps": [], "projection": ["id", "v"]}
            if semantic_repair and counts["Final_Spec"] > 1:
                spec["final_steps"] = [{"operator": "Filter_Aggregate", "operation": "filter", "filters": [{"field": "v", "operator": ">", "value": 2}]}]
                if repair_broken:
                    spec["final_steps"] = [{"operator": "Math_Compute", "expression": "missing * 2", "output_column": "v"}]
            return {"final_spec": compile_spec(spec, {"q1_processed": ["id", "v"]})}
        def validate(inputs):
            counts["Validate"] += 1
            valid = not semantic_repair or counts["Validate"] > 1
            return {"validation": {"is_valid": valid, "reason": "ok" if valid else "missing threshold", "repair_stage": "Final_Spec"}, "data": inputs["data"]}
        ops.update({"Query_Spec": query_spec, "Generate": lambda inputs: {"sparql": "SELECT ?id ?v WHERE {}"},
                    "Pre_Scan_Validate": lambda inputs: {"pre_scan_validation": {"is_valid": not pre_reject, "reason": "wrong field" if pre_reject else "ok"}},
                    "Scan": scan, "Processing_Spec": processing, "Final_Spec": final, "Validate": validate,
                    "Explain": lambda inputs: {"final_answer": json.dumps(inputs.get("data", []))}})
        if broken:
            ops["Math_Compute"] = lambda inputs: {"data": [], "error": "forced runtime failure"}
        dag = nx.DiGraph()
        order = ["Query_Spec", "Generate", "Pre_Scan_Validate", "Scan", "Processing_Spec", "Final_Spec", "Validate", "Explain"]
        for op in order:
            dag.add_node(op, operator=op, explicit_inputs={"subquestion_id": "q1"} if op in order[:5] else {})
        dag.add_edges_from(zip(order, order[1:]))
        with contextlib.redirect_stdout(io.StringIO()):
            result = load("executor").AOPExecutor(ops, None).execute_dag(dag, "original question", {"subquestions": [{"id": "q1", "question": "source rows"}], "answer_requirements": {}})
        return result, counts

    def test_complete_execution_and_final_identity(self):
        result, counts = self.run_dag()
        self.assertEqual(json.loads(result["final_answer"]), [{"id": "a", "v": 2}, {"id": "b", "v": 3}])
        self.assertTrue(result["trace"]["final_output_produced"])
        self.assertTrue(result["trace"]["validation_is_valid"])
        self.assertEqual(result["trace"]["failure_stage"], "")

    def test_valid_empty_result_stays_empty(self):
        result, counts = self.run_dag(empty=True)
        self.assertEqual(result["final_answer"], "[]")
        self.assertTrue(result["trace"]["final_output_produced"])
        self.assertEqual(counts["Scan"], 1)

    def test_processing_runtime_errors_get_targeted_retries(self):
        result, counts = self.run_dag(broken=True)
        self.assertEqual(result["trace"]["failure_stage"], "Processing_Spec")
        self.assertFalse(result["trace"]["final_output_produced"])
        self.assertEqual(counts["Processing_Spec"], 3)
        self.assertEqual(counts["Validate"], 0)

    def test_final_review_repairs_threshold_without_rescanning(self):
        result, counts = self.run_dag(semantic_repair=True)
        self.assertEqual(json.loads(result["final_answer"]), [{"id": "b", "v": 3}])
        self.assertEqual(counts["Scan"], 1)
        self.assertEqual(counts["Final_Spec"], 2)
        self.assertEqual(counts["Validate"], 2)
        self.assertTrue(result["trace"]["final_output_produced"])
        self.assertTrue(result["trace"]["validation_is_valid"])
        self.assertEqual(result["trace"]["failure_stage"], "")
        self.assertEqual(result["trace"]["answer_review_status"], "accepted")
        repair = result["trace"]["repair_log"][-1]
        self.assertEqual(repair["action"], "accepted")
        self.assertEqual(len(repair["original"]["data"]), 2)

    def test_broken_semantic_repair_rolls_back_rows_plan_and_status(self):
        result, counts = self.run_dag(semantic_repair=True, repair_broken=True)
        self.assertEqual(json.loads(result["final_answer"]), [{"id": "a", "v": 2}, {"id": "b", "v": 3}])
        self.assertEqual(counts["Scan"], 1)
        self.assertEqual(counts["Final_Spec"], 5)
        self.assertEqual(counts["Validate"], 1)
        self.assertEqual(result["trace"]["final_spec"]["final_steps"], [])
        self.assertEqual(result["trace"]["answer_review_status"], "rejected")
        self.assertEqual(result["trace"]["failure_stage"], "")
        self.assertTrue(result["trace"]["final_output_produced"])
        self.assertEqual(result["trace"]["repair_log"][-1]["action"], "kept_original")

    def test_pre_scan_rejection_cannot_fall_through(self):
        result, counts = self.run_dag(pre_reject=True)
        self.assertEqual(result["trace"]["failure_stage"], "Pre_Scan_Validate")
        self.assertEqual(counts["Scan"], 0)


if __name__ == "__main__":
    unittest.main()
