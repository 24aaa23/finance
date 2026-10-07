"""Upfront selection and real operator execution, without paid model calls."""
from collections import Counter
from copy import deepcopy
import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import types
import unittest
from unittest.mock import patch

from support import FakeClient, load, registry


def schema_for(tables):
    return {name: {"backend": "sqlite", "sql_table": name,
        "columns": [{"name": field, "source_column": field} for field in fields]}
        for name, fields in tables.items()}


def candidate(branches, steps=None, output=None, projection=None):
    nodes, edges = [], []
    for branch in branches:
        previous = None
        for operator in load("dynamic_dag").RETRIEVAL:
            name = branch["id"] + "_" + operator.lower()
            inputs = {"subquestion_id": branch["id"]}
            if operator == "Query_Spec":
                inputs["required_fields"] = list(branch["required_fields"])
            nodes.append({"id": name, "operator": operator, "inputs": inputs})
            if previous:
                edges.append({"source": previous, "target": name})
            previous = name
    for step in steps or []:
        params = {key: deepcopy(value) for key, value in step.items() if key not in {"id", "operator"}}
        nodes.append({"id": step["id"], "operator": step["operator"], "inputs": params})
        selected = step.get("inputs", [step.get("input")])
        edges.extend({"source": parent, "target": step["id"]} for parent in selected)
    output = output or previous
    nodes.extend([{"id": "validate", "operator": "Validate", "inputs": {}},
                  {"id": "explain", "operator": "Explain", "inputs": {}}])
    edges.extend([{"source": output, "target": "validate"}, {"source": "validate", "target": "explain"}])
    return {"nodes": nodes, "edges": edges, "final_output": output,
            "projection": projection or ["value"], "selected_reason": "explicit test candidate"}


def operators(rows, missing_fields=None):
    ops = registry()
    counts = Counter()
    def query_spec(inputs):
        counts["Query_Spec"] += 1
        branch = inputs["subquestion"]
        fields = list(branch["required_fields"])
        if missing_fields:
            fields = [field for field in fields if field not in missing_fields]
        return {"query_spec": {"retrieval_specs": [{"id": branch["id"], "class": branch["source_class"],
                                                  "fields": fields, "filters": []}]}}
    ops.update({"Query_Spec": query_spec,
        "Generate": lambda inputs: {"sparql": "SELECT declared fields"},
        "Pre_Scan_Validate": lambda inputs: {"pre_scan_validation": {"is_valid": True}},
        "Scan": lambda inputs: {"status": "success", "data": deepcopy(rows[inputs["subquestion_id"]]),
                                 "columns": list(inputs["subquestion"]["required_fields"])},
        "Processing_Spec": load("llm_operators.processing_spec").semantic_build_processing_spec,
        "Final_Spec": lambda inputs: (_ for _ in ()).throw(AssertionError("No second final planner call")),
        "Validate": lambda inputs: load("llm_operators.validate").semantic_validate(inputs, None),
        "Explain": lambda inputs: load("llm_operators.explain").semantic_explain_results(inputs, None)})
    for name, operation in list(ops.items()):
        if name in load("dynamic_dag").CALCULATIONS:
            def counted(inputs, op=operation, name=name):
                counts[name] += 1
                return op(inputs)
            ops[name] = counted
    return ops, counts


class QueueClient:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        value = self.responses.pop(0)
        content = value if isinstance(value, str) else json.dumps(value)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(finish_reason="stop",
            message=types.SimpleNamespace(content=content))])


class DynamicDAGTests(unittest.TestCase):
    def setUp(self):
        self.branches = [{"id": "q", "source_class": "Record", "question": "raw rows",
                          "required_fields": ["id", "value"], "retrieval_grain": ["id"]}]
        self.decomposition = {"subquestions": self.branches, "answer_requirements": {}}
        self.schema = schema_for({"Record": ["id", "value"]})
        self.ops, self.counts = operators({"q": [{"id": 1, "value": 3}, {"id": 1, "value": None}]})
        self.payload = candidate(self.branches)

    def build(self, payload):
        return load("dynamic_dag").validate_candidate(payload, self.decomposition, self.schema, self.ops)

    def execute(self, dag, rows=None, schema=None, decomposition=None, ops=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return load("executor").AOPExecutor(ops or self.ops, None, schema or self.schema).execute_dag(
                dag, "original question", decomposition or self.decomposition)

    def test_lookup_preserves_duplicates_and_nulls_without_final_llm(self):
        original = deepcopy(self.decomposition)
        result = self.execute(self.build(self.payload))
        self.assertEqual(json.loads(result["final_answer"]), [{"value": 3}, {"value": None}])
        self.assertTrue(result["trace"]["final_output_produced"])
        self.assertEqual(self.decomposition, original)

    def test_compiler_expands_measures_and_executes_each_once(self):
        payload = candidate(self.branches, [{"id": "measures", "operator": "Filter_Aggregate",
            "input": "q_processing_spec", "group_by": [], "aggregations": [
                {"operation": "sum", "input_column": "value", "output_column": "total"},
                {"operation": "count", "input_column": "value", "output_column": "n"}]}],
            "measures", ["total", "n"])
        dag = self.build(payload)
        self.assertIn("Combine_Scalars", [data["operator"] for _, data in dag.nodes(data=True)])
        result = self.execute(dag)
        self.assertEqual(json.loads(result["final_answer"]), [{"total": 3, "n": 1}])
        self.assertEqual(self.counts["Filter_Aggregate"], 2)
        self.assertEqual(len(result["trace"]["dynamic_execution_log"]), 3)

    def test_distinct_runs_before_limit_and_rounding_remains_local(self):
        self.ops, self.counts = operators({"q": [{"id": 1, "value": 3.141}, {"id": 1, "value": 3.141},
                                               {"id": 2, "value": 2.11}]})
        payload = candidate(self.branches, [{"id": "sort", "operator": "Order_By", "input": "q_processing_spec",
            "order_by": [{"column": "value", "direction": "DESC"}], "limit": 2}], "sort")
        payload.update(distinct_on=["value"], rounding=1)
        result = self.execute(self.build(payload))
        self.assertEqual(json.loads(result["final_answer"]), [{"value": 3.1}, {"value": 2.1}])
        sequence = result["trace"]["operator_sequence"]
        self.assertLess(sequence.index("Distinct"), sequence.index("Order_By"))
        self.assertEqual(self.counts["Order_By"], 1)

    def test_final_distinct_does_not_reroute_an_earlier_branch_sort(self):
        branches = [{"id": "a", "source_class": "A", "required_fields": ["id", "value"]},
                    {"id": "b", "source_class": "B", "required_fields": ["id", "value"]}]
        schema = schema_for({"A": ["id", "value"], "B": ["id", "value"]})
        decomposition = {"subquestions": branches, "answer_requirements": {}}
        steps = [
            {"id": "sum_a", "operator": "Filter_Aggregate", "input": "a_processing_spec",
             "operation": "sum", "target_column": "value", "output_column": "total", "group_by": ["id"]},
            {"id": "sum_b", "operator": "Filter_Aggregate", "input": "b_processing_spec",
             "operation": "sum", "target_column": "value", "output_column": "total", "group_by": ["id"]},
            {"id": "sort_a", "operator": "Order_By", "input": "sum_a",
             "column": "total", "direction": "DESC", "limit": 1},
            {"id": "join", "operator": "Integrate", "inputs": ["sort_a", "sum_b"],
             "join_key": ["id"], "join_type": "inner"}]
        payload = candidate(branches, steps, "join", ["id", "total", "total_right"])
        payload["distinct_on"] = ["id"]
        rows = {"a": [{"id": 1, "value": 100}, {"id": 2, "value": 1}],
                "b": [{"id": 1, "value": 1}, {"id": 2, "value": 100}]}
        ops, _ = operators(rows)
        dag = load("dynamic_dag").validate_candidate(payload, decomposition, schema, ops)
        result = self.execute(dag, schema=schema, decomposition=decomposition, ops=ops)
        self.assertEqual(json.loads(result["final_answer"]), [{"id": 1, "total": 100, "total_right": 1}])
        sequence = result["trace"]["operator_sequence"]
        self.assertLess(sequence.index("Order_By"), sequence.index("Integrate"))
        self.assertLess(sequence.index("Integrate"), sequence.index("Distinct"))

    def test_conflicting_singular_and_plural_inputs_are_rejected(self):
        payload = candidate(self.branches, [{"id": "math", "operator": "Math_Compute",
            "input": "q_processing_spec", "inputs": ["q_processing_spec"],
            "expression": "column('value')", "output_column": "copy"}], "math", ["copy"])
        with self.assertRaisesRegex(ValueError, "either input or inputs"):
            self.build(payload)

    def test_rejects_ghost_edges_cycles_duplicate_ids_and_crosswired_branches(self):
        mutations = []
        ghost = deepcopy(self.payload)
        ghost["edges"].append({"source": "ghost", "target": "validate"})
        mutations.append(ghost)
        cycle = deepcopy(self.payload)
        cycle["edges"].append({"source": "q_scan", "target": "q_generate"})
        mutations.append(cycle)
        duplicate = deepcopy(self.payload)
        duplicate["nodes"].append(deepcopy(duplicate["nodes"][0]))
        mutations.append(duplicate)
        missing_branch = deepcopy(self.payload)
        missing_branch["nodes"][1]["inputs"]["subquestion_id"] = "unknown"
        mutations.append(missing_branch)
        for payload in mutations:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.build(payload)

    def test_rejects_unknown_fields_operators_and_runtime_data_overrides(self):
        for mutation in ("field", "operator", "data", "source"):
            payload = deepcopy(self.payload)
            if mutation == "field":
                payload["nodes"][0]["inputs"]["required_fields"].append("invented")
            elif mutation == "operator":
                payload["nodes"][0]["operator"] = "Invented"
            elif mutation == "source":
                payload["nodes"][0]["inputs"]["global_schema"] = {}
            else:
                payload["nodes"][1]["inputs"]["data"] = [{"value": 999}]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.build(payload)

    def test_invalid_math_columns_and_implicit_input_fail_before_scan(self):
        for step in [{"id": "math", "operator": "Math_Compute", "input": "q_processing_spec",
                      "expression": "column('missing') + 1", "output_column": "result"},
                     {"id": "sort", "operator": "Order_By", "input": "q_processing_spec", "column": "missing"}]:
            with self.subTest(step=step), self.assertRaises(ValueError):
                self.build(candidate(self.branches, [step], step["id"], ["result"]))

    def test_missing_required_scan_columns_is_execution_failure(self):
        self.ops["Scan"] = lambda inputs: {"status": "success", "data": [], "columns": ["id"]}
        result = self.execute(self.build(self.payload))
        self.assertEqual(result["trace"]["failure_stage"], "Execution")
        self.assertFalse(result["trace"]["final_output_produced"])

    def test_query_spec_repairs_missing_upfront_operands(self):
        self.ops, _ = operators({"q": []}, missing_fields={"value"})
        result = self.execute(self.build(self.payload))
        self.assertEqual(result["trace"]["failure_stage"], "Query_Spec")
        self.assertIn("Upfront DAG requires", result["trace"]["validation_reason"])

    def test_typed_empty_input_remains_successful(self):
        self.ops, _ = operators({"q": []})
        result = self.execute(self.build(self.payload))
        self.assertEqual(result["final_answer"], "[]")
        self.assertTrue(result["trace"]["final_output_produced"])

    def test_real_sqlite_retrieval_and_contract_checks_feed_upfront_math(self):
        payload = candidate(self.branches, [{"id": "math", "operator": "Math_Compute",
            "input": "q_processing_spec", "expression": "column('value') * 2", "output_column": "doubled"}],
            "math", ["id", "doubled"])
        with tempfile.TemporaryDirectory() as temporary:
            db_path = Path(temporary) / "records.sqlite"
            with contextlib.closing(sqlite3.connect(db_path)) as db:
                db.execute("CREATE TABLE Record(id,value)")
                db.executemany("INSERT INTO Record VALUES (?,?)", [(1, 3), (1, 3), (2, None)])
                db.commit()
            def query_spec(inputs):
                return load("llm_operators.query_spec").semantic_build_query_spec(
                    {**inputs, "global_schema": self.schema}, FakeClient({"retrieval_specs": [
                        {"id": "q", "class": "Record", "fields": ["id", "value"], "filters": [], "entity_key": ["id"]}]}))
            self.ops.update({"Query_Spec": query_spec,
                "Generate": lambda inputs: load("llm_operators.generate").semantic_generate_sparql(
                    {**inputs, "global_schema": self.schema}, FakeClient("must not be called"), "offline"),
                "Pre_Scan_Validate": lambda inputs: load("llm_operators.pre_scan_validate").semantic_pre_scan_validate(
                    {**inputs, "global_schema": self.schema, "sqlite_db_path": str(db_path)}, None),
                "Scan": lambda inputs: load("non_llm_operators.scan").pre_programmed_scan(
                    {**inputs, "sqlite_db_path": str(db_path)})})
            result = self.execute(self.build(payload))
        self.assertEqual(json.loads(result["final_answer"]), [
            {"id": 1, "doubled": 6}, {"id": 1, "doubled": 6}, {"id": 2, "doubled": None}])
        self.assertEqual(self.counts["Math_Compute"], 1)
        self.assertTrue(result["trace"]["pre_scan_validation_is_valid"])

    def test_upfront_schema_is_stable_when_query_spec_returns_extra_columns(self):
        self.ops["Scan"] = lambda inputs: {"status": "success", "columns": ["id", "value", "extra"],
            "data": [{"id": 1, "value": 3, "extra": "unused"}]}
        result = self.execute(self.build(self.payload))
        self.assertEqual(result["trace"]["branch_profiles"][0]["fields"], ["id", "value"])
        self.assertEqual(json.loads(result["final_answer"]), [{"value": 3}])

    def test_runtime_bad_numeric_data_exhausts_bounded_calculation_repairs(self):
        self.ops, _ = operators({"q": [{"id": 1, "value": "not numeric"}]})
        payload = candidate(self.branches, [{"id": "sum", "operator": "Filter_Aggregate",
            "input": "q_processing_spec", "operation": "sum", "target_column": "value",
            "output_column": "total", "group_by": []}], "sum", ["total"])
        repairs = []
        def fail_repair(inputs):
            repairs.append(deepcopy(inputs))
            return {"final_spec": {"contract_errors": ["Numeric data remains invalid"]}}
        self.ops["Final_Spec"] = fail_repair
        result = self.execute(self.build(payload))
        self.assertEqual(result["trace"]["failure_stage"], "Final_Spec")
        self.assertFalse(result["trace"]["final_output_produced"])
        self.assertEqual(len(repairs), 3)
        self.assertEqual(result["trace"]["dynamic_calculation_attempts"], 4)

    def test_semantic_projection_contract_rejected_before_scan(self):
        decomposition = deepcopy(self.decomposition)
        decomposition["answer_requirements"]["query_understanding"] = {
            "required_projection": ["id", "value"], "limit": None, "order_by": [], "group_by": [], "metrics": []}
        with self.assertRaisesRegex(ValueError, "projection omits"):
            load("dynamic_dag").validate_candidate(self.payload, decomposition, self.schema, self.ops)

    def test_specialist_can_revise_interpretation_before_any_scan(self):
        class Session:
            def run(self, stage, operation, inputs):
                raise load("consultation").InterpretationRevised("changed meaning")
        planner = load("planner").AdvancedAOPPlanner(FakeClient(self.payload), self.ops, global_schema=self.schema)
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(load("consultation").InterpretationRevised):
            planner.plan_optimal_dag_from_decomposition("question", self.decomposition, consultation_session=Session())

    def test_evaluator_receives_specialist_advice_used_in_generation(self):
        class Session:
            advice = [{"topic": "metric_definition", "rules": [{"text": "Approved rule: use the recorded value."}]}]
            def run(self, stage, operation, inputs):
                return operation({**inputs, "agent_consultation_enabled": True,
                    "agent_consultation_available": True, "agent_consultation_context": self.advice})
        client = QueueClient([self.payload, {"reward_score": 0.95}, self.payload, self.payload])
        planner = load("planner").AdvancedAOPPlanner(client, self.ops, global_schema=self.schema)
        with contextlib.redirect_stdout(io.StringIO()):
            planner.plan_optimal_dag_from_decomposition("show values", self.decomposition, consultation_session=Session())
        for index in (0, 1):
            self.assertIn("Approved rule: use the recorded value.", client.calls[index]["messages"][-1]["content"])

    def test_three_model_candidates_select_cheapest_high_reward(self):
        sort = candidate(self.branches, [{"id": "sort", "operator": "Order_By", "input": "q_processing_spec",
                                         "column": "value"}], "sort")
        math = candidate(self.branches, [{"id": "math", "operator": "Math_Compute", "input": "q_processing_spec",
                                         "expression": "column('value')", "output_column": "copy"}], "math", ["copy"])
        client = QueueClient([sort, {"reward_score": 0.99}, self.payload, {"reward_score": 0.91},
                              math, {"reward_score": 0.95}])
        planner = load("planner").AdvancedAOPPlanner(client, self.ops, global_schema=self.schema)
        with contextlib.redirect_stdout(io.StringIO()):
            dag = planner.plan_optimal_dag_from_decomposition("show values", self.decomposition)
        self.assertFalse(dag.graph["planning"]["fallback"])
        self.assertEqual(dag.graph["planning"]["selected_candidate"], 2)
        self.assertEqual(len(client.calls), 6)
        self.assertIn("COMPLETE DAG", client.calls[1]["messages"][-1]["content"])
        self.assertEqual(json.loads(self.execute(dag)["final_answer"]), [{"value": 3}, {"value": None}])

    def test_below_threshold_selects_highest_reward_and_deduplicates(self):
        sort = candidate(self.branches, [{"id": "sort", "operator": "Order_By", "input": "q_processing_spec",
                                         "column": "value"}], "sort")
        duplicate = deepcopy(self.payload)
        duplicate["selected_reason"] = "different prose is not a different graph"
        client = QueueClient([self.payload, {"reward_score": 0.6}, sort, {"reward_score": 0.8}, duplicate])
        planner = load("planner").AdvancedAOPPlanner(client, self.ops, global_schema=self.schema)
        with contextlib.redirect_stdout(io.StringIO()):
            dag = planner.plan_optimal_dag_from_decomposition("show values", self.decomposition)
        self.assertEqual(dag.graph["planning"]["selected_candidate"], 2)
        self.assertEqual(dag.graph["planning"]["candidates"][-1]["status"], "duplicate")

    def test_bad_evaluator_does_not_fabricate_reward(self):
        client = QueueClient([self.payload, {"reward_score": float("nan")}, self.payload, self.payload])
        planner = load("planner").AdvancedAOPPlanner(client, self.ops, global_schema=self.schema)
        with contextlib.redirect_stdout(io.StringIO()):
            dag = planner.plan_optimal_dag_from_decomposition("show values", self.decomposition)
        self.assertIsNone(dag.graph["planning"]["reward_score"])
        self.assertIn("evaluation_unavailable", dag.graph["planning"]["selection_rule"])

    def test_renamed_duplicate_graph_is_not_scored_again(self):
        renamed = deepcopy(self.payload)
        mapping = {node["id"]: "renamed_" + node["id"] for node in renamed["nodes"]}
        for node in renamed["nodes"]:
            node["id"] = mapping[node["id"]]
        for edge in renamed["edges"]:
            edge["source"], edge["target"] = mapping[edge["source"]], mapping[edge["target"]]
        renamed["final_output"] = mapping[renamed["final_output"]]
        client = QueueClient([{"dag": self.payload}, {"reward_score": 0.95}, renamed, self.payload])
        planner = load("planner").AdvancedAOPPlanner(client, self.ops, global_schema=self.schema)
        with contextlib.redirect_stdout(io.StringIO()):
            dag = planner.plan_optimal_dag_from_decomposition("show values", self.decomposition)
        self.assertEqual(len(client.calls), 4)
        self.assertEqual([entry["status"] for entry in dag.graph["planning"]["candidates"]],
                         ["selected", "duplicate", "duplicate"])

    def test_quota_failure_uses_runner_stop_without_more_candidate_calls(self):
        class BrokenClient(FakeClient):
            def create(self, **kwargs):
                self.calls.append(kwargs)
                raise RuntimeError("quota exhausted")
        client = BrokenClient(None)
        planner = load("planner").AdvancedAOPPlanner(client, self.ops, global_schema=self.schema)
        with contextlib.redirect_stdout(io.StringIO()), patch.object(load("utils"), "is_quota_exhaustion_error",
                lambda exc: "quota" in str(exc), create=True), self.assertRaisesRegex(RuntimeError, "quota"):
            planner.plan_optimal_dag_from_decomposition("question", self.decomposition)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(planner.last_planning["candidates"][0]["status"], "interrupted")

    def test_bad_candidates_have_bounded_logged_fallback(self):
        client = FakeClient("not JSON")
        planner = load("planner").AdvancedAOPPlanner(client, self.ops, global_schema=self.schema)
        with contextlib.redirect_stdout(io.StringIO()), patch.dict(os.environ, {"DAG_PLANNER_MAX_ROUNDS": "2"}):
            dag = planner.plan_optimal_dag_from_decomposition("show values", self.decomposition)
        self.assertTrue(dag.graph["planning"]["fallback"])
        self.assertEqual(len(client.calls), 6)
        self.assertNotIn("dynamic_plan", dag.graph)

    def test_replans_before_fallback_with_validation_feedback(self):
        client = QueueClient([{}, {}, {}, self.payload, {"reward_score": 0.95}, self.payload, self.payload])
        planner = load("planner").AdvancedAOPPlanner(client, self.ops, global_schema=self.schema)
        with contextlib.redirect_stdout(io.StringIO()):
            dag = planner.plan_optimal_dag_from_decomposition("show values", self.decomposition)
        self.assertEqual(dag.graph["planning"]["selected_round"], 2)
        self.assertIn("nonempty nodes list", client.calls[3]["messages"][-1]["content"])

    def test_ordered_join_operands_match_independent_sql_despite_edge_order(self):
        branches = [
            {"id": "f", "source_class": "Fact", "question": "facts", "required_fields": ["owner", "amount"]},
            {"id": "p", "source_class": "Person", "question": "people", "required_fields": ["id", "name"]}]
        schema = schema_for({"Fact": ["owner", "amount"], "Person": ["id", "name"]})
        decomposition = {"subquestions": branches, "answer_requirements": {}}
        steps = [
            {"id": "sum", "operator": "Filter_Aggregate", "input": "f_processing_spec",
             "operation": "sum", "target_column": "amount", "output_column": "total", "group_by": ["owner"]},
            {"id": "join", "operator": "Integrate", "inputs": ["sum", "p_processing_spec"],
             "left_on": ["owner"], "right_on": ["id"], "join_type": "left"},
            {"id": "sort", "operator": "Order_By", "input": "join", "column": "total", "direction": "DESC"}]
        payload = candidate(branches, steps, "sort", ["owner", "name", "total"])
        payload["edges"].reverse()
        rows = {"f": [{"owner": "a", "amount": 2}, {"owner": "a", "amount": 3},
                      {"owner": "b", "amount": None}, {"owner": "orphan", "amount": 4}],
                "p": [{"id": "a", "name": "Alpha"}, {"id": "b", "name": "Beta"}]}
        ops, counts = operators(rows)
        dag = load("dynamic_dag").validate_candidate(payload, decomposition, schema, ops)
        result = self.execute(dag, schema=schema, decomposition=decomposition, ops=ops)
        with sqlite3.connect(":memory:") as db:
            db.execute("CREATE TABLE Fact(owner,amount)")
            db.execute("CREATE TABLE Person(id,name)")
            db.executemany("INSERT INTO Fact VALUES (?,?)", [(r["owner"], r["amount"]) for r in rows["f"]])
            db.executemany("INSERT INTO Person VALUES (?,?)", [(r["id"], r["name"]) for r in rows["p"]])
            expected = [dict(zip(["owner", "name", "total"], r)) for r in db.execute(
                "WITH sums AS (SELECT owner,SUM(amount) total FROM Fact GROUP BY owner) "
                "SELECT owner,name,total FROM sums LEFT JOIN Person ON owner=id ORDER BY total DESC")]
        self.assertEqual(json.loads(result["final_answer"]), expected)
        self.assertEqual(counts["Integrate"], 1)
        self.assertEqual(counts["Filter_Aggregate"], 1)
        self.assertEqual(counts["Order_By"], 1)

        # A genuinely different valid graph can join a unique dimension first.
        early_steps = [
            {"id": "early_join", "operator": "Integrate", "inputs": ["f_processing_spec", "p_processing_spec"],
             "left_on": ["owner"], "right_on": ["id"], "join_type": "left"},
            {"id": "sum", "operator": "Filter_Aggregate", "input": "early_join",
             "operation": "sum", "target_column": "amount", "output_column": "total", "group_by": ["owner", "name"]},
            {"id": "sort", "operator": "Order_By", "input": "sum", "column": "total", "direction": "DESC"}]
        early = candidate(branches, early_steps, "sort", ["owner", "name", "total"])
        early_dag = load("dynamic_dag").validate_candidate(early, decomposition, schema, ops)
        early_result = self.execute(early_dag, schema=schema, decomposition=decomposition, ops=ops)
        self.assertEqual(json.loads(early_result["final_answer"]), expected)
        self.assertNotEqual([data["operator"] for _, data in dag.nodes(data=True)],
                            [data["operator"] for _, data in early_dag.nodes(data=True)])


if __name__ == "__main__":
    unittest.main()
