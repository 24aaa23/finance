import unittest

from script_diff_llm.pipeline.dag.planner import build_subquery_dag, fallback_backend_for_query
from script_diff_llm.pipeline.semantic_contract import (
    iri_local_name,
    normalize_semantic_result,
    normalize_result_iris,
    set_operation_key,
    validate_aggregation_shape,
    validate_semantic_result,
)
from script_diff_llm.pipeline.specification import (
    cleanup_query_spec,
    semantic_build_query_spec,
    spec_is_analytic_without_measures,
)


def _normalize(value):
    import re
    return re.sub(r"[^a-z0-9.]+", " ", str(value).lower()).strip()


class QuerySpecCleanupTest(unittest.TestCase):
    def test_grouped_comparative_promotes_final_average(self):
        spec = {
            "query_type": "comparative",
            "base_entity": "ATOM_ENTITY_INVESTOR_PROFILE_001",
            "entity_key": "investor_id",
            "grain": {"pre_aggregate_by": ["investor_id"], "final_group_by": []},
            "group_by": [{"output_name": "segment", "field": "segment"}],
            "measures": [
                {
                    "output_name": "total_holding_value",
                    "per_entity_operation": "SUM",
                    "final_operation": "SUM",
                }
            ],
            "output_schema": ["segment", "total_holding_value"],
            "required_classes": ["ATOM_ENTITY_INVESTOR_PROFILE_001"],
            "execution_strategy": "preaggregate_sparql",
        }
        cleaned = cleanup_query_spec(
            spec,
            "Across profile segment, how does holding value compare?",
            ["ATOM_ENTITY_INVESTOR_PROFILE_001"],
            _normalize,
        )
        measure = cleaned["measures"][0]
        self.assertEqual(measure["final_operation"], "AVG")
        self.assertEqual(measure["output_name"], "avg_holding_value")
        self.assertIn("avg_holding_value", cleaned["output_schema"])

    def test_band_query_marks_bucket_strategy(self):
        spec = {
            "query_type": "comparative",
            "grain": {"pre_aggregate_by": [], "final_group_by": []},
            "group_by": [{"output_name": "goal_match_pct_band", "field": "goalMatchPct"}],
            "measures": [],
            "required_classes": [],
            "execution_strategy": "single_sparql",
        }
        cleaned = cleanup_query_spec(
            spec,
            "Compare average risk score across goal_match_pct bands.",
            [],
            _normalize,
        )
        self.assertEqual(cleaned["group_by"][0]["bucket_strategy"], "three_band_33_66")

    def test_shortfall_measure_prefers_average_not_sum(self):
        spec = {
            "query_type": "comparative",
            "base_entity": "ATOM_ENTITY_INVESTOR_PROFILE_001",
            "entity_key": "investor_id",
            "grain": {"pre_aggregate_by": ["investor_id"], "final_group_by": ["risk_tolerance"]},
            "group_by": [{"output_name": "risk_tolerance", "field": "risk_tolerance"}],
            "measures": [
                {
                    "output_name": "total_shortfall",
                    "field": "shortfall",
                    "per_entity_operation": "SUM",
                    "final_operation": "SUM",
                }
            ],
            "output_schema": ["risk_tolerance", "total_shortfall"],
            "required_classes": [],
            "execution_strategy": "preaggregate_sparql",
        }
        cleaned = cleanup_query_spec(
            spec,
            "Across risk_tolerance, how does shortfall compare?",
            [],
            _normalize,
        )
        measure = cleaned["measures"][0]
        self.assertEqual(measure["per_entity_operation"], "AVG")
        self.assertEqual(measure["final_operation"], "AVG")
        self.assertEqual(measure["output_name"], "avg_shortfall")

    def test_entity_returning_query_keeps_identity_outputs(self):
        spec = {
            "query_type": "ranking",
            "base_entity": "investor",
            "entity_key": "investor_id",
            "grain": {"pre_aggregate_by": ["investor_id"], "final_group_by": []},
            "group_by": [],
            "measures": [{"output_name": "risk_pressure_score"}],
            "output_schema": ["risk_pressure_score"],
            "required_classes": ["ATOM_ENTITY_INVESTOR_PROFILE_001"],
            "execution_strategy": "preaggregate_sparql",
        }
        cleaned = cleanup_query_spec(
            spec,
            "Which ten investors have the highest risk pressure score?",
            ["ATOM_ENTITY_INVESTOR_PROFILE_001"],
            _normalize,
            schema_kind="sql",
        )
        self.assertEqual(cleaned["output_schema"][:3], ["investor_id", "investor_name", "risk_pressure_score"])

    def test_month_and_profile_group_are_inferred(self):
        spec = {
            "query_type": "aggregation",
            "base_entity": "CashFlow",
            "entity_key": "cashFlowId",
            "grain": {"pre_aggregate_by": ["cashFlowId"], "final_group_by": []},
            "group_by": [],
            "measures": [{"output_name": "monthly_net_cash_flow", "source_class": "CashFlow", "field": "amount"}],
            "output_schema": ["monthly_net_cash_flow"],
            "required_classes": ["CashFlow"],
            "execution_strategy": "single_sparql",
        }
        cleaned = cleanup_query_spec(
            spec,
            "For each profile risk_tolerance, what is the monthly net cash flow?",
            ["CashFlow", "RiskTolerance"],
            _normalize,
            schema_kind="kg",
        )
        self.assertEqual(cleaned["group_by"][0]["output_name"], "month")
        self.assertEqual(cleaned["group_by"][1]["output_name"], "risk_tolerance")
        self.assertIn("month", cleaned["output_schema"])
        self.assertIn("risk_tolerance", cleaned["output_schema"])
        self.assertIn("Investor", cleaned["required_classes"])
        self.assertNotIn("date", cleaned["output_schema"])

    def test_grouped_money_aggregation_is_not_forced_to_average_without_compare_wording(self):
        spec = {
            "query_type": "aggregation",
            "base_entity": "ATOM_EVENT_CASH_FLOW_001",
            "entity_key": "investor_id",
            "grain": {"pre_aggregate_by": ["investor_id", "month"], "final_group_by": ["risk_tolerance", "month"]},
            "group_by": [
                {"output_name": "risk_tolerance", "field": "risk_tolerance"},
                {"output_name": "month", "field": "date"},
            ],
            "measures": [
                {
                    "output_name": "monthly_net_cash_flow",
                    "field": "amount",
                    "per_entity_operation": "SUM",
                    "final_operation": "SUM",
                }
            ],
            "output_schema": ["risk_tolerance", "month", "monthly_net_cash_flow"],
            "required_classes": ["ATOM_EVENT_CASH_FLOW_001", "ATOM_ENTITY_INVESTOR_PROFILE_001"],
            "execution_strategy": "preaggregate_sparql",
        }
        cleaned = cleanup_query_spec(
            spec,
            "For each profile risk_tolerance, what is the monthly net cash flow?",
            ["ATOM_EVENT_CASH_FLOW_001", "ATOM_ENTITY_INVESTOR_PROFILE_001"],
            _normalize,
            schema_kind="sql",
        )
        measure = cleaned["measures"][0]
        self.assertEqual(measure["output_name"], "monthly_net_cash_flow")
        self.assertEqual(measure["final_operation"], "SUM")

    def test_cash_flow_formula_is_simplified_to_signed_sum(self):
        spec = {
            "query_type": "aggregation",
            "base_entity": "ATOM_EVENT_CASH_FLOW_001",
            "entity_key": "investor_id",
            "grain": {"pre_aggregate_by": ["investor_id", "month"], "final_group_by": ["risk_tolerance", "month"]},
            "group_by": [
                {"output_name": "risk_tolerance", "field": "risk_tolerance"},
                {"output_name": "month", "field": "date"},
            ],
            "measures": [
                {
                    "output_name": "net_cash_flow",
                    "source_class": "ATOM_EVENT_CASH_FLOW_001",
                    "field": "amount",
                    "formula": "SUM(CASE WHEN type = 'inflow' THEN amount ELSE -amount END)",
                    "formula_fields": ["amount", "type"],
                    "per_entity_operation": "SUM",
                    "final_operation": "SUM",
                }
            ],
            "output_schema": ["risk_tolerance", "month", "net_cash_flow"],
            "required_classes": ["ATOM_EVENT_CASH_FLOW_001", "ATOM_ENTITY_INVESTOR_PROFILE_001"],
            "execution_strategy": "preaggregate_sparql",
        }
        cleaned = cleanup_query_spec(
            spec,
            "For each profile risk_tolerance, what is the monthly net cash flow?",
            ["ATOM_EVENT_CASH_FLOW_001", "ATOM_ENTITY_INVESTOR_PROFILE_001"],
            _normalize,
            schema_kind="sql",
        )
        measure = cleaned["measures"][0]
        self.assertIsNone(measure["formula"])
        self.assertEqual(measure["formula_fields"], [])

    def test_bucket_queries_do_not_preserve_null_group(self):
        spec = {
            "query_type": "comparative",
            "grain": {"pre_aggregate_by": [], "final_group_by": []},
            "group_by": [{"output_name": "goal_match_pct_band", "field": "goalMatchPct"}],
            "measures": [],
            "required_classes": [],
            "execution_strategy": "single_sparql",
        }
        cleaned = cleanup_query_spec(
            spec,
            "Compare average risk score across goal_match_pct bands.",
            [],
            _normalize,
        )
        self.assertFalse(cleaned.get("preserve_null_groups", False))


class SemanticContractValidationTest(unittest.TestCase):
    def test_detects_missing_bucketization(self):
        query_spec = {
            "group_by": [{"output_name": "goal_match_pct_band", "field": "goalMatchPct", "bucket_strategy": "three_band_33_66"}],
            "output_schema": ["goal_match_pct_band", "avg_risk_score"],
        }
        data = [
            {"goal_match_pct_band": "62.5", "avg_risk_score": "10.0"},
            {"goal_match_pct_band": "82.7", "avg_risk_score": "12.0"},
            {"goal_match_pct_band": "50.8", "avg_risk_score": "11.0"},
            {"goal_match_pct_band": "89.3", "avg_risk_score": "15.0"},
        ]
        result = validate_semantic_result(
            "How do scores compare across goal_match_pct bands?",
            query_spec,
            data,
        )
        self.assertFalse(result["is_valid"])
        self.assertIn("bucket", result["reason"].lower())

    def test_detects_unsorted_ranking(self):
        query_spec = {
            "entity_key": "investor_id",
            "group_by": [],
            "output_schema": ["investor_id", "risk_pressure_score"],
            "ranking": {"required": True, "metric": "risk_pressure_score", "direction": "desc", "limit": 3},
        }
        data = [
            {"investor_id": "INV-1", "risk_pressure_score": "10"},
            {"investor_id": "INV-2", "risk_pressure_score": "12"},
            {"investor_id": "INV-3", "risk_pressure_score": "8"},
        ]
        result = validate_semantic_result(
            "Which three investors have the highest risk pressure score?",
            query_spec,
            data,
        )
        self.assertFalse(result["is_valid"])
        self.assertIn("not sorted", result["reason"].lower())

    def test_detects_missing_identity_in_ranking_result(self):
        query_spec = {
            "entity_key": "investor_id",
            "group_by": [],
            "output_schema": ["risk_pressure_score"],
            "ranking": {"required": True, "metric": "risk_pressure_score", "direction": "desc", "limit": 3},
        }
        data = [
            {"risk_pressure_score": "10"},
            {"risk_pressure_score": "9"},
            {"risk_pressure_score": "8"},
        ]
        result = validate_semantic_result(
            "Which three investors have the highest risk pressure score?",
            query_spec,
            data,
        )
        self.assertFalse(result["is_valid"])
        self.assertIn("identity column", result["reason"].lower())

    def test_detects_date_leak_in_month_level_query(self):
        query_spec = {
            "month_grain": True,
            "output_schema": ["risk_tolerance", "month", "net_cash_flow"],
            "group_by": [{"output_name": "risk_tolerance"}, {"output_name": "month"}],
        }
        data = [
            {"risk_tolerance": "Aggressive", "date": "2021-04-29", "month": "2021-04", "net_cash_flow": "9037.0"},
        ]
        result = validate_semantic_result(
            "For each profile risk_tolerance, what is the monthly net cash flow?",
            query_spec,
            data,
        )
        self.assertFalse(result["is_valid"])
        self.assertIn("raw date", result["reason"].lower())

    def test_normalizes_bucket_rows_and_drops_null_bucket(self):
        query_spec = {
            "group_by": [{"output_name": "goal_match_pct_band", "field": "goalMatchPct", "bucket_strategy": "three_band_33_66"}],
            "preserve_null_groups": False,
        }
        data = [
            {"goal_match_pct_band": None, "avg_risk_score": 50},
            {"goal_match_pct_band": "Low", "avg_risk_score": 44},
            {"goal_match_pct_band": "Medium", "avg_risk_score": 51},
            {"goal_match_pct_band": "High", "avg_risk_score": 56},
        ]
        normalized = normalize_semantic_result(
            "Compare average risk score across goal_match_pct bands.",
            query_spec,
            data,
        )
        self.assertEqual(len(normalized), 3)
        self.assertEqual(
            [row["goal_match_pct_band"] for row in normalized],
            ["goal match < 33", "goal match 33-66", "goal match >= 67"],
        )

    def test_reshapes_missing_count_rows(self):
        data = [{
            "missing_investment_type": 755,
            "missing_sector": 755,
            "missing_segment": 755,
            "missing_category": 755,
        }]
        normalized = normalize_semantic_result(
            "How many holdings are missing each required classification field: investment_type, sector, segment, and category?",
            {},
            data,
        )
        self.assertEqual(
            normalized,
            [
                {"field_name": "investment_type", "missing_count": 755},
                {"field_name": "sector", "missing_count": 755},
                {"field_name": "segment", "missing_count": 755},
                {"field_name": "category", "missing_count": 755},
            ],
        )


class FallbackPlannerTest(unittest.TestCase):
    def test_aggregation_query_falls_back_to_sql(self):
        self.assertEqual(
            fallback_backend_for_query("Across risk_tolerance, how do rebalancing amount and cash flow compare?"),
            "SQL",
        )
        dag = build_subquery_dag("Across risk_tolerance, how do rebalancing amount and cash flow compare?", [])
        self.assertEqual(dag.nodes["Q1"]["backend"], "SQL")

    def test_entity_lookup_falls_back_to_kg(self):
        self.assertEqual(
            fallback_backend_for_query("Which investors have Conservative risk tolerance and a Short-term horizon?"),
            "KG",
        )


class QuerySpecRepairTest(unittest.TestCase):
    class _FakeResponse:
        def __init__(self, content):
            self.choices = [type("Choice", (), {"message": type("Message", (), {"content": content})()})()]

    class _FakeClient:
        def __init__(self, outputs):
            self._outputs = list(outputs)
            self.chat = type("Chat", (), {"completions": self})()

        def create(self, **kwargs):
            del kwargs
            return QuerySpecRepairTest._FakeResponse(self._outputs.pop(0))

    def test_query_spec_repair_retries_after_malformed_json(self):
        client = self._FakeClient([
            "not json",
            '{"query_type":"comparative","base_entity":"Investor","entity_key":"investorId","join_policy":"inner_join","grain":{"pre_aggregate_by":["investorId"],"final_group_by":["segment"]},"group_by":[{"output_name":"segment","source_class":"Investor","field":"segment"}],"filters":[],"measures":[{"output_name":"avg_cash_flow","source_class":"CashFlow","field":"amount","formula":null,"formula_fields":[],"per_entity_operation":"SUM","final_operation":"AVG","requires_distinct":false}],"ranking":{"required":false,"metric":null,"direction":null,"limit":null},"required_classes":["Investor","CashFlow"],"execution_strategy":"preaggregate_sparql","output_schema":["segment","avg_cash_flow"],"reason":"ok"}',
        ])
        result = semantic_build_query_spec(
            {
                "query": "Across segment, how does cash flow compare?",
                "root_query": "Across segment, how does cash flow compare?",
                "retrieved_tables": ["Investor", "CashFlow"],
                "global_schema": {"Investor": {}, "CashFlow": {}},
            },
            client,
            "stub-model",
            parse_json_fn=lambda raw, default, context: __import__("json").loads(raw) if raw.strip().startswith("{") else default,
            normalize_for_compare_fn=_normalize,
            log_call_fn=lambda query, op: None,
        )
        self.assertEqual(result["query_spec"]["query_type"], "comparative")
        self.assertEqual(result["query_spec"]["measures"][0]["final_operation"], "AVG")


if __name__ == "__main__":
    unittest.main()


class TwoLevelAggregationGrainTest(unittest.TestCase):
    """Grouped comparatives must pre-aggregate per entity before grouping.

    A flat join from an entity table to one-to-many tables repeats each entity
    once per related record, so the final average is weighted by related-record
    counts. These tests pin the deterministic contract that prevents that.
    """

    def _spec(self, **overrides):
        spec = {
            "query_type": "comparative",
            "base_entity": "ATOM_ENTITY_INVESTOR_PROFILE_001",
            "entity_key": "investor_id",
            "grain": {"pre_aggregate_by": [], "final_group_by": []},
            "group_by": [{
                "output_name": "time_horizon",
                "source_class": "ATOM_ENTITY_INVESTOR_PROFILE_001",
                "field": "time_horizon",
            }],
            "measures": [
                {
                    "output_name": "avg_progress_pct",
                    "source_class": "ATOM_ENTITY_INVESTMENT_GOAL_001",
                    "field": "progress_pct",
                    "per_entity_operation": None,
                    "final_operation": "AVG",
                },
                {
                    "output_name": "avg_risk_score",
                    "source_class": "ATOM_ENTITY_PORTFOLIO_HEALTH_001",
                    "field": "risk_score",
                    "per_entity_operation": None,
                    "final_operation": "AVG",
                },
            ],
            "required_classes": ["ATOM_ENTITY_INVESTOR_PROFILE_001"],
            "execution_strategy": "preaggregate_sparql",
            "output_schema": ["time_horizon", "avg_progress_pct", "avg_risk_score"],
        }
        spec.update(overrides)
        return spec

    def test_measures_outside_group_table_force_entity_pre_aggregation(self):
        cleaned = cleanup_query_spec(
            self._spec(),
            "Across time_horizon, how do goal progress and health risk compare using three related tables?",
            ["ATOM_ENTITY_INVESTOR_PROFILE_001"],
            _normalize,
        )
        self.assertEqual(cleaned["grain"]["pre_aggregate_by"], ["investor_id"])
        self.assertTrue(cleaned["fanout_control"]["required"])
        for measure in cleaned["measures"]:
            self.assertEqual(measure["per_entity_operation"], "AVG")
            self.assertEqual(measure["final_operation"], "AVG")

    def test_additive_money_measure_sums_within_entity_then_averages_across(self):
        spec = self._spec(measures=[{
            "output_name": "holding_value",
            "source_class": "ATOM_ENTITY_PORTFOLIO_HOLDING_001",
            "field": "current_value",
            "per_entity_operation": None,
            "final_operation": "SUM",
        }])
        cleaned = cleanup_query_spec(
            spec,
            "Across time_horizon, how does holding value compare using two related tables?",
            ["ATOM_ENTITY_INVESTOR_PROFILE_001"],
            _normalize,
        )
        measure = cleaned["measures"][0]
        self.assertEqual(measure["per_entity_operation"], "SUM")
        self.assertEqual(measure["final_operation"], "AVG")
        self.assertEqual(measure["output_name"], "avg_holding_value")

    def test_single_table_grouping_is_left_alone(self):
        spec = self._spec(measures=[{
            "output_name": "avg_risk_score",
            "source_class": "ATOM_ENTITY_INVESTOR_PROFILE_001",
            "field": "risk_score",
            "per_entity_operation": None,
            "final_operation": "AVG",
        }])
        cleaned = cleanup_query_spec(
            spec,
            "Across time_horizon, what is the average risk score?",
            ["ATOM_ENTITY_INVESTOR_PROFILE_001"],
            _normalize,
        )
        self.assertEqual(cleaned["grain"]["pre_aggregate_by"], [])
        self.assertNotIn("fanout_control", cleaned)

    def test_concentration_measure_takes_entity_maximum(self):
        """Concentration is an entity's largest share, not the mean of its shares."""
        spec = self._spec(measures=[{
            "output_name": "allocation_concentration",
            "source_class": "ATOM_ENTITY_SECTOR_ALLOCATION_001",
            "field": "allocation_pct",
            "per_entity_operation": None,
            "final_operation": "AVG",
        }])
        cleaned = cleanup_query_spec(
            spec,
            "Across profile segment, how does allocation concentration compare using three related tables?",
            ["ATOM_ENTITY_INVESTOR_PROFILE_001"],
            _normalize,
        )
        measure = cleaned["measures"][0]
        self.assertEqual(measure["per_entity_operation"], "MAX")
        self.assertEqual(measure["final_operation"], "AVG")

    def test_rate_measure_still_averages_within_entity(self):
        spec = self._spec(measures=[{
            "output_name": "avg_progress_pct",
            "source_class": "ATOM_ENTITY_INVESTMENT_GOAL_001",
            "field": "progress_pct",
            "per_entity_operation": None,
            "final_operation": "AVG",
        }])
        cleaned = cleanup_query_spec(
            spec,
            "Across time_horizon, how does goal progress compare using two related tables?",
            ["ATOM_ENTITY_INVESTOR_PROFILE_001"],
            _normalize,
        )
        self.assertEqual(cleaned["measures"][0]["per_entity_operation"], "AVG")

    def test_explicit_total_query_keeps_sum(self):
        spec = self._spec(measures=[{
            "output_name": "total_holding_value",
            "source_class": "ATOM_ENTITY_PORTFOLIO_HOLDING_001",
            "field": "current_value",
            "per_entity_operation": "SUM",
            "final_operation": "SUM",
        }])
        cleaned = cleanup_query_spec(
            spec,
            "What is the total holding value by time_horizon?",
            ["ATOM_ENTITY_INVESTOR_PROFILE_001"],
            _normalize,
        )
        self.assertEqual(cleaned["measures"][0]["final_operation"], "SUM")


class AggregationShapeValidationTest(unittest.TestCase):
    FANOUT_SPEC = {
        "fanout_control": {"required": True, "pre_aggregate_by": ["investor_id"]},
        "grain": {"pre_aggregate_by": ["investor_id"], "final_group_by": ["time_horizon"]},
    }

    def test_flat_join_is_rejected(self):
        sql = (
            "SELECT p.time_horizon, AVG(g.progress_pct) AS avg_progress_pct "
            "FROM ATOM_ENTITY_INVESTOR_PROFILE_001 p "
            "JOIN ATOM_ENTITY_INVESTMENT_GOAL_001 g ON p.investor_id = g.investor_id "
            "GROUP BY p.time_horizon"
        )
        check = validate_aggregation_shape(self.FANOUT_SPEC, sql)
        self.assertFalse(check["is_valid"])
        self.assertEqual(check["severity"], "repairable_warning")
        self.assertIn("investor_id", check["rewrite_hint"])

    def test_cte_staged_aggregation_is_accepted(self):
        sql = (
            "WITH g AS (SELECT investor_id, AVG(progress_pct) v "
            "FROM ATOM_ENTITY_INVESTMENT_GOAL_001 GROUP BY investor_id) "
            "SELECT p.time_horizon, AVG(g.v) FROM ATOM_ENTITY_INVESTOR_PROFILE_001 p "
            "LEFT JOIN g ON p.investor_id = g.investor_id GROUP BY p.time_horizon"
        )
        self.assertTrue(validate_aggregation_shape(self.FANOUT_SPEC, sql)["is_valid"])

    def test_derived_table_is_accepted(self):
        sql = "SELECT t.h, AVG(t.v) FROM (SELECT investor_id, SUM(x) v FROM a GROUP BY investor_id) t GROUP BY t.h"
        self.assertTrue(validate_aggregation_shape(self.FANOUT_SPEC, sql)["is_valid"])

    def test_sparql_subselect_is_accepted(self):
        sparql = (
            "SELECT ?th (AVG(?v) AS ?avg) WHERE { ?i wm:timeHorizon ?th . "
            "{ SELECT ?i (AVG(?p) AS ?v) WHERE { ?i wm:progressPct ?p } GROUP BY ?i } } GROUP BY ?th"
        )
        self.assertTrue(validate_aggregation_shape(self.FANOUT_SPEC, sparql)["is_valid"])

    def test_spec_without_fanout_requirement_is_not_checked(self):
        sql = "SELECT a, AVG(b) FROM t JOIN u ON 1 GROUP BY a"
        self.assertTrue(validate_aggregation_shape({"grain": {}}, sql)["is_valid"])

    def test_empty_query_is_not_flagged(self):
        self.assertTrue(validate_aggregation_shape(self.FANOUT_SPEC, "")["is_valid"])


class ResultNormalizationTest(unittest.TestCase):
    def test_iri_reduces_to_local_name(self):
        self.assertEqual(iri_local_name("https://wealth.example.org/kg/investor/INV-003"), "INV-003")
        self.assertEqual(iri_local_name("http://example.org/ns#Aggressive"), "Aggressive")

    def test_non_iri_values_pass_through_untouched(self):
        for value in ["INV-003", "Large Cap", None, 42.5, True]:
            self.assertEqual(iri_local_name(value), value)

    def test_row_normalization_covers_every_cell(self):
        rows = [{"investor": "https://wealth.example.org/kg/investor/INV-003", "name": "Kavita", "score": 41.2}]
        self.assertEqual(
            normalize_result_iris(rows),
            [{"investor": "INV-003", "name": "Kavita", "score": 41.2}],
        )

    def test_set_operation_key_unifies_backend_id_shapes(self):
        keys = {
            set_operation_key("https://wealth.example.org/kg/investor/INV-003"),
            set_operation_key("INV-003"),
            set_operation_key("inv 003"),
        }
        self.assertEqual(len(keys), 1)


class MeasureRecoveryTest(unittest.TestCase):
    """An analytic question with no measures has no contract; retry once."""

    def test_detects_analytic_spec_without_measures(self):
        self.assertTrue(spec_is_analytic_without_measures(
            {"query_type": "comparative", "measures": []},
            "Across time_horizon, how do goal progress and risk compare?",
        ))

    def test_detects_via_question_wording_when_type_is_unset(self):
        self.assertTrue(spec_is_analytic_without_measures(
            {"query_type": "", "measures": []},
            "What is the average holding value per segment?",
        ))

    def test_spec_with_measures_is_not_flagged(self):
        self.assertFalse(spec_is_analytic_without_measures(
            {"query_type": "comparative", "measures": [{"output_name": "avg_x"}]},
            "how do x compare",
        ))

    def test_non_analytic_lookup_is_not_flagged(self):
        self.assertFalse(spec_is_analytic_without_measures(
            {"query_type": "point_lookup", "measures": []},
            "Which investors are in the Aggressive risk tolerance?",
        ))

    def _build(self, responses):
        calls = []

        class _Msg:
            def __init__(self, content): self.content = content

        class _Client:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kwargs):
                        calls.append(kwargs)
                        payload = responses[min(len(calls) - 1, len(responses) - 1)]
                        return type("R", (), {"choices": [type("C", (), {"message": _Msg(payload)})()]})()

        result = semantic_build_query_spec(
            {"query": "Across segment, how do holding value and risk compare?",
             "root_query": "Across segment, how do holding value and risk compare?",
             "retrieved_tables": ["ATOM_ENTITY_INVESTOR_PROFILE_001"],
             "schema_kind": "sql",
             "global_schema": {"ATOM_ENTITY_INVESTOR_PROFILE_001": {}}},
            _Client(), "stub-model",
            parse_json_fn=lambda raw, default, ctx: (__import__("json").loads(raw) if raw.strip().startswith("{") else default),
            normalize_for_compare_fn=_normalize,
            log_call_fn=lambda *a: None,
        )
        return result["query_spec"], calls

    def test_recovery_replaces_an_empty_measure_spec(self):
        empty = '{"query_type": "comparative", "measures": [], "group_by": [], "required_classes": [], "execution_strategy": "single_sql", "output_schema": []}'
        recovered = '{"query_type": "comparative", "measures": [{"output_name": "avg_holding_value", "source_class": "T", "field": "current_value", "per_entity_operation": "SUM", "final_operation": "AVG"}], "group_by": [], "required_classes": [], "execution_strategy": "single_sql", "output_schema": []}'
        spec, calls = self._build([empty, recovered])
        self.assertEqual(len(calls), 2, "should have issued exactly one recovery call")
        self.assertTrue(spec["measures"])
        self.assertTrue(spec.get("measure_recovery"))

    def test_failed_recovery_never_worsens_the_spec(self):
        empty = '{"query_type": "comparative", "measures": [], "group_by": [{"output_name": "segment", "field": "segment"}], "required_classes": [], "execution_strategy": "single_sql", "output_schema": ["segment"]}'
        spec, calls = self._build([empty, "not json at all"])
        self.assertEqual(spec["measures"], [])
        self.assertTrue(spec.get("measure_recovery_failed"))
        self.assertEqual([g["output_name"] for g in spec["group_by"]], ["segment"])


class OutputSchemaPreservationTest(unittest.TestCase):
    """output_schema cleanup must merge, never replace.

    A regression let this refresh step discard any pre-populated output_schema
    entry that wasn't a group_by dimension or a measure output_name - silently
    dropping identity/filter columns (investor_id, investor_name) from the
    downstream SQL/SPARQL contract. Confirmed against a live 442-row benchmark
    run: this caused 25+ MATCH-graded rows to regress to MISMATCH because the
    generated query stopped selecting the identity columns grading required.
    """

    def test_identity_columns_outside_group_and_measures_survive_cleanup(self):
        spec = {
            "query_type": "point_lookup",
            "base_entity": "ATOM_ENTITY_INVESTOR_PROFILE_001",
            "entity_key": "investor_id",
            "grain": {"pre_aggregate_by": [], "final_group_by": []},
            "group_by": [],
            "measures": [{
                "output_name": "total_current_value",
                "source_class": "ATOM_ENTITY_PORTFOLIO_HOLDING_001",
                "field": "current_value",
                "per_entity_operation": "SUM",
                "final_operation": "SUM",
            }],
            "output_schema": ["investor_id", "investor_name", "total_current_value"],
            "required_classes": ["ATOM_ENTITY_INVESTOR_PROFILE_001"],
            "execution_strategy": "single_sql",
        }
        cleaned = cleanup_query_spec(
            spec,
            "Which investors have total current holding value above 10000000?",
            ["ATOM_ENTITY_INVESTOR_PROFILE_001"],
            _normalize,
        )
        self.assertEqual(
            cleaned["output_schema"],
            ["investor_id", "investor_name", "total_current_value"],
        )

    def test_measure_rename_during_cleanup_still_updates_output_schema(self):
        spec = {
            "query_type": "comparative",
            "base_entity": "ATOM_ENTITY_INVESTOR_PROFILE_001",
            "entity_key": "investor_id",
            "grain": {"pre_aggregate_by": ["investor_id"], "final_group_by": []},
            "group_by": [{"output_name": "segment", "field": "segment"}],
            "measures": [{
                "output_name": "total_holding_value",
                "source_class": "ATOM_ENTITY_PORTFOLIO_HOLDING_001",
                "field": "current_value",
                "per_entity_operation": "SUM",
                "final_operation": "SUM",
            }],
            "output_schema": ["segment", "total_holding_value"],
            "required_classes": ["ATOM_ENTITY_INVESTOR_PROFILE_001"],
            "execution_strategy": "preaggregate_sql",
        }
        cleaned = cleanup_query_spec(
            spec,
            "Across profile segment, how does holding value compare?",
            ["ATOM_ENTITY_INVESTOR_PROFILE_001"],
            _normalize,
        )
        self.assertIn("avg_holding_value", cleaned["output_schema"])
        self.assertNotIn("total_holding_value", cleaned["output_schema"])

    def test_multiple_identity_and_filter_columns_all_survive(self):
        spec = {
            "query_type": "set_logic",
            "base_entity": "ATOM_ENTITY_INVESTOR_PROFILE_001",
            "entity_key": "investor_id",
            "grain": {"pre_aggregate_by": [], "final_group_by": []},
            "group_by": [],
            "measures": [],
            "output_schema": ["investor_id", "investor_name", "risk_tolerance", "category"],
            "required_classes": ["ATOM_ENTITY_INVESTOR_PROFILE_001"],
            "execution_strategy": "single_sql",
        }
        cleaned = cleanup_query_spec(
            spec, "Which investors have Aggressive risk tolerance and Gold category?",
            ["ATOM_ENTITY_INVESTOR_PROFILE_001"], _normalize,
        )
        self.assertEqual(
            cleaned["output_schema"],
            ["investor_id", "investor_name", "risk_tolerance", "category"],
        )
