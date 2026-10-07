"""Dynamic and original recovery budgets, with real compilers and no model API."""
from copy import deepcopy
import contextlib
import importlib.util
import io
import json
import unittest
from unittest.mock import patch

from support import FakeClient, PACKAGE, SOURCE, load
from test_dynamic_dag import candidate, operators, schema_for


def original_executor():
    if not (SOURCE.parent / "run_pipeline_v3_sql _" / "executor.py").is_file():
        # Portable copies compare against this executor's unchanged fixed-DAG path.
        return load("executor").AOPExecutor
    spec = importlib.util.spec_from_file_location(
        PACKAGE + ".original_executor", SOURCE.parent / "run_pipeline_v3_sql _" / "executor.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.AOPExecutor


class DynamicRepairTests(unittest.TestCase):
    def setUp(self):
        self.branches = [{"id": "q", "source_class": "Record", "question": "Read records",
                          "required_fields": ["id", "value"], "retrieval_grain": ["id"]}]
        self.decomposition = {"subquestions": self.branches, "answer_requirements": {}}
        self.schema = schema_for({"Record": ["id", "value"]})
        self.rows = {"q": [{"id": 1, "value": "SECRET_BAD_NUMBER"}]}
        self.bad_math = [{"id": "bad", "operator": "Math_Compute", "input": "q_processing_spec",
                          "expression": "column('value') + 1", "output_column": "answer"}]

    def run_case(self, dynamic=True, repair_plans=None, processing_failures=0, good_initial=False):
        ops, counts = operators(self.rows)
        seen = {"Final_Spec": [], "Scan": [], "Processing_Spec": []}
        client = FakeClient({})
        scan, processing = ops["Scan"], ops["Processing_Spec"]
        def scan_count(inputs):
            seen["Scan"].append(deepcopy(inputs))
            return scan(inputs)
        def process(inputs):
            seen["Processing_Spec"].append(deepcopy(inputs))
            if len(seen["Processing_Spec"]) <= processing_failures:
                return {"processing_spec": load("spec_runtime").compile_spec({
                    "steps": [{"operator": "Invented", "input": "raw"}],
                    "projection": ["id", "value"]}, {"raw": ["id", "value"]})}
            return processing(inputs)
        def final(inputs):
            seen["Final_Spec"].append(deepcopy(inputs))
            source = inputs["processed_datasets"][0]["id"]
            plans = repair_plans or ["good"]
            chosen = plans[min(len(seen["Final_Spec"]) - 1, len(plans) - 1)]
            if isinstance(chosen, dict):
                payload = deepcopy(chosen)
            elif chosen == "compile_error":
                payload = {"final_steps": [], "projection": ["invented"]}
            else:
                payload = {"final_steps": [{"id": "answer_step", "operator": "Math_Compute", "input": source,
                           "expression": "column('value') + 1" if chosen == "runtime_error" else "column('id') + 1",
                           "output_column": "answer"}], "projection": ["answer"]}
            client.value = payload
            return load("llm_operators.final_spec").semantic_build_final_spec(
                {**inputs, "global_schema": self.schema}, client)
        ops.update(Scan=scan_count, Processing_Spec=process, Final_Spec=final)
        if dynamic:
            steps = deepcopy(self.bad_math)
            if good_initial:
                steps[0]["expression"] = "column('id') + 1"
            dag = load("dynamic_dag").validate_candidate(
                candidate(self.branches, steps, "bad", ["answer"]), self.decomposition, self.schema, ops)
            executor = load("executor").AOPExecutor
        else:
            with contextlib.redirect_stdout(io.StringIO()):
                dag = load("planner").AdvancedAOPPlanner(None, ops).plan_optimal_dag_from_decomposition(
                    "Calculate answer", self.decomposition)
            executor = original_executor()
        with contextlib.redirect_stdout(io.StringIO()):
            result = executor(ops, None, self.schema).execute_dag(dag, "Calculate answer", self.decomposition)
        return result, seen, counts, client

    def test_successful_upfront_plan_needs_no_final_model_call(self):
        result, seen, counts, _ = self.run_case(good_initial=True)
        self.assertEqual(json.loads(result["final_answer"]), [{"answer": 2}])
        self.assertEqual(seen["Final_Spec"], [])
        self.assertEqual(counts["Math_Compute"], 1)
        self.assertEqual(result["trace"]["dynamic_calculation_attempts"], 1)

    def test_recovery_on_fourth_attempt_matches_original_budget_and_feedback(self):
        for dynamic in (True, False):
            plans = ["compile_error", "compile_error", "good"]
            if not dynamic:
                plans.insert(0, "runtime_error")
            with self.subTest(dynamic=dynamic):
                result, seen, _, client = self.run_case(dynamic, plans)
                self.assertEqual(json.loads(result["final_answer"]), [{"answer": 2}])
                self.assertEqual(len(seen["Final_Spec"]), 3 if dynamic else 4)
                self.assertEqual(len(seen["Scan"]), 1)
                repairs = seen["Final_Spec"] if dynamic else seen["Final_Spec"][1:]
                self.assertEqual([json.loads(i["spec_feedback"])["attempt"] for i in repairs], [1, 2, 3])
                feedback = json.loads(repairs[0]["spec_feedback"])
                failure = feedback["failed_steps"][0]
                self.assertEqual(failure["operator"], "Math_Compute")
                self.assertEqual(failure["code"], "OPERATOR_ERROR")
                source = repairs[0]["processed_datasets"][0]["id"]
                self.assertEqual(failure["input_schemas"], {source: ["id", "value"]})
                if dynamic:
                    self.assertEqual(failure["step"], feedback["step_ids"]["bad"])
                    self.assertEqual(result["trace"]["dynamic_calculation_attempts"], 4)
                self.assertNotIn("SECRET_BAD_NUMBER", json.dumps(client.calls))

    def test_persistent_runtime_failure_stops_after_four_total_attempts(self):
        for dynamic in (True, False):
            with self.subTest(dynamic=dynamic):
                result, seen, counts, _ = self.run_case(dynamic, ["runtime_error"])
                self.assertEqual(len(seen["Final_Spec"]), 3 if dynamic else 4)
                self.assertEqual(counts["Math_Compute"], 4)
                self.assertEqual(result["trace"]["failure_stage"], "Final_Spec")
                self.assertFalse(result["trace"]["final_output_produced"])
                self.assertEqual(len(seen["Scan"]), 1)
                self.assertEqual([r["attempt"] for r in result["trace"]["repair_log"]
                                  if r["stage"] == "Final_Spec"], [1, 2, 3, 4])
                self.assertEqual(result["trace"]["repair_log"][-1]["action"], "stop")

    def test_processing_recovers_on_third_attempt_without_rescan(self):
        for dynamic in (True, False):
            with self.subTest(dynamic=dynamic):
                result, seen, _, _ = self.run_case(dynamic, processing_failures=2, good_initial=True)
                self.assertTrue(result["trace"]["final_output_produced"])
                self.assertEqual(len(seen["Processing_Spec"]), 3)
                self.assertEqual(len(seen["Scan"]), 1)
                retries = seen["Processing_Spec"][1:]
                self.assertEqual([json.loads(i["spec_feedback"])["attempt"] for i in retries], [1, 2])
                self.assertIn("processing_spec", result["trace"]["processing_specs"][-1])

    def test_processing_persistent_failure_stops_after_three_attempts(self):
        for dynamic in (True, False):
            with self.subTest(dynamic=dynamic):
                result, seen, _, _ = self.run_case(dynamic, processing_failures=10)
                self.assertEqual(len(seen["Processing_Spec"]), 3)
                self.assertEqual(len(seen["Scan"]), 1)
                self.assertEqual(seen["Final_Spec"], [])
                self.assertEqual(result["trace"]["failure_stage"], "Processing_Spec")
                self.assertEqual(result["trace"]["repair_log"][-1]["action"], "stop")

    def test_missing_retrieval_routes_to_existing_upstream_repair(self):
        missing = [{"source_class": "Other", "field": "needed"}]
        result, seen, _, _ = self.run_case(repair_plans=[{"missing_requirements": missing}])
        self.assertEqual(len(seen["Final_Spec"]), 1)
        self.assertEqual(result["trace"]["repair_stage"], "Decompose")
        self.assertEqual(result["trace"]["final_spec"]["missing_requirements"], missing)
        self.assertEqual(result["trace"]["repair_log"][-1]["action"], "repair_upstream")

    def test_output_contract_failure_also_uses_repair_budget(self):
        finish = load("dynamic_execution").finish_output
        def fail_output(*args, **kwargs):
            result, _ = finish(*args, **kwargs)
            return result, ["Final projection failed its output contract"]
        with patch.object(load("dynamic_execution"), "finish_output", side_effect=fail_output):
            result, seen, counts, _ = self.run_case(good_initial=True)
        self.assertEqual(json.loads(result["final_answer"]), [{"answer": 2}])
        self.assertEqual(len(seen["Final_Spec"]), 1)
        self.assertEqual(counts["Math_Compute"], 2)
        self.assertEqual(len(seen["Scan"]), 1)
        self.assertEqual(result["trace"]["dynamic_calculation_attempts"], 2)

    def test_repair_replaces_dependencies_and_skips_failed_plan_descendants(self):
        branches = [{"id": name, "source_class": name.upper(), "required_fields": ["id", "value"]}
                    for name in ["a", "b"]]
        schema = schema_for({"A": ["id", "value"], "B": ["id", "value"]})
        decomposition = {"subquestions": branches, "answer_requirements": {}}
        ops, counts = operators({"a": [{"id": 1, "value": "bad"}], "b": [{"id": 1, "value": 10}]})
        scans, repairs = [], []
        scan = ops["Scan"]
        def retrieve(inputs):
            scans.append(inputs["subquestion_id"])
            return scan(inputs)
        def repair(inputs):
            repairs.append(deepcopy(inputs))
            self.assertEqual(set(scans), {"a", "b"})
            return load("llm_operators.final_spec").semantic_build_final_spec(
                {**inputs, "global_schema": schema}, FakeClient({"final_steps": [
                    {"id": "different_join", "operator": "Integrate", "inputs": ["a_processing_spec", "b_processing_spec"],
                     "left_on": ["id"], "right_on": ["id"], "join_type": "inner"},
                    {"id": "different_math", "operator": "Math_Compute", "input": "different_join",
                     "expression": "column('id') + column('value_right')", "output_column": "answer"}],
                    "projection": ["answer"]}))
        ops.update(Scan=retrieve, Final_Spec=repair)
        steps = [
            {"id": "prefix", "operator": "Math_Compute", "input": "a_processing_spec",
             "expression": "column('id') + 100", "output_column": "scratch"},
            {"id": "bad", "operator": "Math_Compute", "input": "prefix",
             "expression": "column('value') + 1", "output_column": "answer"},
            {"id": "old_join", "operator": "Integrate", "inputs": ["bad", "b_processing_spec"],
             "left_on": ["id"], "right_on": ["id"], "join_type": "inner"}]
        dag = load("dynamic_dag").validate_candidate(candidate(branches, steps, "old_join", ["answer"]),
                                                     decomposition, schema, ops)
        original_graph = list(dag.edges)
        with contextlib.redirect_stdout(io.StringIO()):
            result = load("executor").AOPExecutor(ops, None, schema).execute_dag(dag, "Compute answer", decomposition)
        self.assertEqual(json.loads(result["final_answer"]), [{"answer": 11}])
        self.assertEqual(scans, ["a", "b"])
        self.assertEqual(len(repairs), 1)
        self.assertEqual(counts["Integrate"], 1)  # Only the new join; old descendant was skipped.
        self.assertEqual(counts["Math_Compute"], 3)  # Prefix, failure, new expression.
        self.assertEqual(list(dag.edges), original_graph)
        self.assertEqual(len(result["trace"]["dynamic_execution_log"]), 2)
        feedback = json.loads(repairs[0]["spec_feedback"])
        failure = feedback["failed_steps"][0]
        self.assertEqual(failure["step"], feedback["step_ids"]["bad"])
        self.assertEqual(failure["inputs"], [feedback["step_ids"]["prefix"]])
        self.assertEqual(result["trace"]["dynamic_calculation_attempts"], 2)

    def test_service_error_in_repair_propagates_without_additional_repairs(self):
        builder = load("llm_operators.final_spec")
        with patch.object(builder, "semantic_build_final_spec", side_effect=RuntimeError("rate_limit_exceeded")) as call:
            with self.assertRaisesRegex(RuntimeError, "rate_limit_exceeded"):
                self.run_case()
        self.assertEqual(call.call_count, 1)


if __name__ == "__main__":
    unittest.main()
