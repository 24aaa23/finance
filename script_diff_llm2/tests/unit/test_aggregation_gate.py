"""The aggregation-shape gate must drive regeneration, not just annotate a trace.

Exercises the real AOPExecutor SQL path with stubbed operators so the retry
behaviour around a fan-out violation is pinned down: a flat-join query must be
rejected and regenerated, and the node must still execute rather than fail hard
if the generator never complies.
"""
import unittest
from unittest import mock

import networkx as nx

from script_diff_llm.pipeline.dag.executor import AOPExecutor

FANOUT_SPEC = {
    "query_type": "comparative",
    "entity_key": "investor_id",
    "group_by": [{"output_name": "time_horizon", "field": "time_horizon"}],
    "measures": [{"output_name": "avg_progress_pct", "per_entity_operation": "AVG", "final_operation": "AVG"}],
    "output_schema": ["time_horizon", "avg_progress_pct"],
    "grain": {"pre_aggregate_by": ["investor_id"], "final_group_by": ["time_horizon"]},
    "fanout_control": {"required": True, "pre_aggregate_by": ["investor_id"]},
}

FLAT_SQL = ("SELECT p.time_horizon, AVG(g.progress_pct) AS avg_progress_pct "
            "FROM prof p JOIN goal g ON p.investor_id = g.investor_id GROUP BY p.time_horizon")
STAGED_SQL = ("WITH g AS (SELECT investor_id, AVG(progress_pct) v FROM goal GROUP BY investor_id) "
              "SELECT p.time_horizon, AVG(g.v) AS avg_progress_pct FROM prof p "
              "LEFT JOIN g ON p.investor_id = g.investor_id GROUP BY p.time_horizon")
ROWS = [{"time_horizon": "Long-term", "avg_progress_pct": 40.22},
        {"time_horizon": "Short-term", "avg_progress_pct": 39.66}]


def _executor(registry=None):
    return AOPExecutor(
        operator_registry={"Query_Spec": lambda i: {"query_spec": FANOUT_SPEC},
                           "_generate_model": "stub", **(registry or {})},
        rdf_graph=None,
        llm_client=object(),
    )


class AggregationGateTest(unittest.TestCase):
    def _run(self, sql_sequence):
        generated = list(sql_sequence)
        calls = {"generate": 0, "llm_pre_scan": 0}

        def fake_generate(inputs, client, model):
            index = min(calls["generate"], len(generated) - 1)
            calls["generate"] += 1
            return {"sql": generated[index], "reasoning": ""}

        def fake_pre_scan(inputs, client, model):
            calls["llm_pre_scan"] += 1
            return {"pre_scan_validation": {"is_valid": True, "severity": "valid", "reason": "Valid"}}

        with mock.patch("script_diff_llm.pipeline.dag.executor.sql_pipeline") as sql_stub:
            sql_stub.semantic_generate_sql.side_effect = fake_generate
            sql_stub.semantic_pre_scan_validate_sql.side_effect = fake_pre_scan
            sql_stub.pre_programmed_scan_sql.return_value = {
                "status": "success", "row_count": len(ROWS), "data": list(ROWS), "error_message": "",
            }
            result = _executor()._run_sql_subquery("Q1", "compare across time_horizon", "compare across time_horizon", {}, {})
        return result, calls

    def test_flat_join_is_regenerated_and_staged_sql_accepted(self):
        result, calls = self._run([FLAT_SQL, STAGED_SQL])
        self.assertEqual(result["status"], "success")
        self.assertGreaterEqual(calls["generate"], 2, "gate should have forced a regeneration")
        self.assertEqual(result["trace"]["generated_sql"], STAGED_SQL)
        stages = [a["stage"] for a in result["trace"]["attempts"]]
        self.assertIn("Aggregation_Shape_Check_SQL", stages)

    def test_persistent_flat_join_still_executes_with_a_warning(self):
        """A fan-out warning is a quality signal, not a reason to lose the answer."""
        result, calls = self._run([FLAT_SQL])
        self.assertEqual(result["status"], "success")
        self.assertEqual(
            [{"time_horizon": row["time_horizon"], "avg_progress_pct": row["avg_progress_pct"]}
             for row in result["data"]],
            ROWS,
        )
        self.assertIn("two-level aggregation", result["trace"]["aggregation_shape_warning"])

    def test_compliant_sql_is_not_regenerated(self):
        result, calls = self._run([STAGED_SQL])
        self.assertEqual(result["status"], "success")
        self.assertEqual(calls["generate"], 1)
        self.assertEqual(calls["llm_pre_scan"], 1, "LLM pre-scan should still run when the shape is fine")
        self.assertNotIn("aggregation_shape_warning", result["trace"])
