import unittest

from script_diff_llm.backends.sql import (
    _deterministic_group_count_sql,
    _deterministic_profile_group_sql,
)
from script_diff_llm.pipeline.decomposition import _ensure_domain_coverage


class DeterministicProfileCompilerTest(unittest.TestCase):
    def test_compiles_entity_then_group_aggregation(self):
        schema = {
            "ATOM_ENTITY_INVESTOR_PROFILE_001": {
                "column_names": ["investor_id", "risk_tolerance"],
            },
            "ATOM_EVENT_CASH_FLOW_001": {
                "column_names": ["investor_id", "amount"],
            },
        }
        spec = {
            "entity_key": "investor_id",
            "join_policy": "left_join",
            "fanout_control": {"required": True},
            "preserve_null_groups": True,
            "group_by": [{
                "output_name": "risk_tolerance",
                "source_class": "ATOM_ENTITY_INVESTOR_PROFILE_001",
                "field": "risk_tolerance",
            }],
            "filters": [],
            "measures": [{
                "output_name": "avg_net_cash_flow",
                "source_class": "ATOM_EVENT_CASH_FLOW_001",
                "field": "amount",
                "per_entity_operation": "SUM",
                "final_operation": "AVG",
            }],
        }
        sql = _deterministic_profile_group_sql({"query_spec": spec, "sql_schema": schema})
        self.assertIn('SUM("amount") AS "avg_net_cash_flow"', sql)
        self.assertIn('AVG(metric_source_0."avg_net_cash_flow")', sql)
        self.assertIn("LEFT JOIN metric_source_0", sql)

    def test_compiles_categorical_and_semantic_bucket_count(self):
        schema = {
            "ATOM_ENTITY_INVESTOR_PROFILE_001": {
                "column_names": ["investor_id", "risk_tolerance"],
            },
            "ATOM_ENTITY_PORTFOLIO_HEALTH_001": {
                "column_names": ["investor_id", "risk_score"],
            },
        }
        spec = {
            "entity_key": "investor_id",
            "join_policy": "inner_join",
            "drop_null_bucket_groups": True,
            "group_by": [
                {
                    "output_name": "risk_tolerance",
                    "source_class": "ATOM_ENTITY_INVESTOR_PROFILE_001",
                    "field": "risk_tolerance",
                },
                {
                    "output_name": "risk_band",
                    "source_class": "ATOM_ENTITY_PORTFOLIO_HEALTH_001",
                    "field": "risk_score",
                    "bucket_strategy": "semantic_thresholds",
                    "bucket_boundaries": [40, 70],
                    "bucket_labels": ["Low", "Moderate", "High"],
                },
            ],
            "filters": [],
            "measures": [{
                "output_name": "investor_count",
                "source_class": "ATOM_ENTITY_INVESTOR_PROFILE_001",
                "field": "investor_id",
                "per_entity_operation": "COUNT",
                "requires_distinct": True,
            }],
        }
        sql = _deterministic_group_count_sql({"query_spec": spec, "sql_schema": schema})
        self.assertIn('g1."risk_score" <= 40', sql)
        self.assertIn("THEN 'Moderate'", sql)
        self.assertIn('COUNT(DISTINCT g0."investor_id")', sql)
        self.assertNotIn('g0."risk_tolerance" IS NOT NULL', sql)


class DecompositionCoverageTest(unittest.TestCase):
    def test_incomplete_multi_domain_plan_falls_back_to_complete_sql(self):
        parsed = {"nodes": [{
            "id": "Q1",
            "description": "Find investors with cash-flow transactions in 2025",
            "operator": "Subquery",
            "backend": "SQL",
            "inputs": [],
            "outputs": [],
        }]}
        result = _ensure_domain_coverage(
            "Which investors both purchased a holding and had a cash-flow transaction during 2025?",
            parsed,
        )
        self.assertEqual(len(result["nodes"]), 1)
        self.assertIn("purchased a holding", result["nodes"][0]["description"])
        self.assertEqual(result["nodes"][0]["backend"], "SQL")

    def test_shared_year_is_propagated_to_each_event_subquery(self):
        parsed = {"nodes": [
            {
                "id": "Q1", "description": "Investors who purchased a holding",
                "operator": "Subquery", "backend": "KG", "inputs": [], "outputs": [],
            },
            {
                "id": "Q2", "description": "Investors with a cash-flow transaction during 2025",
                "operator": "Subquery", "backend": "SQL", "inputs": [], "outputs": [],
            },
        ]}
        result = _ensure_domain_coverage(
            "Which investors purchased a holding and had cash flow during 2025?",
            parsed,
        )
        self.assertIn("during 2025", result["nodes"][0]["description"])


if __name__ == "__main__":
    unittest.main()
