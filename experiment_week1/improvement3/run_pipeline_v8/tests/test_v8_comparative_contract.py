"""Exercise semantic regressions with independent SQL and real operator execution."""
import unittest

from support import FakeClient, load, registry
import test_comparative_steps as fixtures


class V8ComparativeContractTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ComparativeStepsTests("runTest")
        self.fixture.setUp()
        self.schemas = self.fixture.schemas
        self.plan = {
            "final_steps": self.fixture.summaries() + [{
                "operator": "Filter_Aggregate", "input": "joined", "group_by": ["category"],
                "aggregations": [
                    {"operation": "avg", "input_column": "total", "output_column": "avg_total"},
                    {"operation": "avg", "input_column": "rating", "output_column": "avg_rating"}]}],
            "projection": ["category", "avg_total", "avg_rating"],
            "comparative_contract_required": True,
            "comparative_contract": {
                "version": 1,
                "dimensions": [{"source": "people", "column": "category", "output_column": "category"}],
                "required_population": ["people", "sales", "ratings"],
                "metrics": [
                    {"source": "sales", "source_columns": ["value"], "source_grain": ["owner"],
                     "inner_aggregate": "sum", "outer_aggregate": "avg", "output_column": "avg_total"},
                    {"source": "ratings", "source_columns": ["score"], "source_grain": ["owner"],
                     "inner_aggregate": "avg", "outer_aggregate": "avg", "output_column": "avg_rating"}]}}

    def compile(self):
        return load("spec_runtime").compile_spec(self.plan, self.schemas)

    def errors(self):
        return "\n".join(self.compile()["contract_errors"])

    def test_two_level_metrics_match_sql_with_unequal_records_nulls_and_missing_participant(self):
        plan = self.compile()
        self.assertFalse(plan["contract_errors"], plan["contract_errors"])
        actual, log = load("execution").execute_spec(plan, self.fixture.data, registry(), dataset_schemas=self.schemas)
        self.assertFalse(load("execution").execution_errors(log), log)
        expected = self.fixture.sql('''WITH s AS (SELECT owner,SUM(value) total FROM sales GROUP BY owner),
            r AS (SELECT owner,AVG(score) rating FROM ratings GROUP BY owner)
            SELECT category,AVG(total) avg_total,AVG(rating) avg_rating
            FROM people p JOIN s ON p.id=s.owner JOIN r ON p.id=r.owner GROUP BY category''')
        key = lambda row: str(row["category"])
        self.assertEqual(sorted(actual, key=key), sorted(expected, key=key))

    def test_actual_keys_and_display_aliases_do_not_need_a_global_spelling(self):
        self.plan["final_steps"].append({"operator": "Math_Compute", "expression": "column('category')", "output_column": "display"})
        self.plan["projection"][0] = "display"
        self.plan["comparative_contract"]["dimensions"][0]["output_column"] = "display"
        self.assertFalse(self.errors())

    def test_wrong_inner_average_cannot_replace_total(self):
        self.plan["final_steps"][0]["operation"] = "avg"
        self.assertIn("needs sum per source entity", self.errors())

    def test_maximum_is_distinct_from_average(self):
        self.plan["comparative_contract"]["metrics"][0]["inner_aggregate"] = "max"
        self.assertIn("needs max per source entity", self.errors())
        self.plan["final_steps"][0]["operation"] = "max"
        self.assertFalse(self.errors())

    def test_sibling_summary_cannot_certify_raw_metric_path(self):
        # Keep the summary participating in the answer, but also join raw sales.
        self.plan["final_steps"].insert(4, {"id": "raw_again", "operator": "Integrate", "inputs": ["joined", "sales"], "left_on": ["id"], "right_on": ["owner"]})
        self.plan["final_steps"][-1]["input"] = "raw_again"
        self.plan["final_steps"][-1]["aggregations"][0]["input_column"] = "value"
        self.assertIn("sibling summary", self.errors())

    def test_wrong_metric_source_is_rejected(self):
        self.plan["comparative_contract"]["metrics"][0].update(source="ratings", source_columns=["score"])
        self.assertIn("different source columns", self.errors())

    def test_wrong_dimension_owner_is_rejected(self):
        self.schemas["sales"].append("category")
        self.plan["comparative_contract"]["dimensions"][0]["source"] = "sales"
        self.assertIn("retain provenance", self.errors())

    def test_omitted_metric_projection_is_rejected(self):
        self.plan["projection"].remove("avg_rating")
        self.assertIn("missing from the projection", self.errors())

    def test_wrong_outer_operation_is_rejected(self):
        self.plan["final_steps"][-1]["aggregations"][0]["operation"] = "sum"
        self.assertIn("declared outer aggregate avg", self.errors())

    def test_left_join_does_not_establish_required_participation(self):
        self.plan["final_steps"][3]["join_type"] = "left"
        self.assertIn("required population", self.errors())

    def test_separate_group_averages_cannot_claim_a_shared_population(self):
        # First metric computed before ratings participate, then joined to ratings.
        self.plan["final_steps"] = [
            self.plan["final_steps"][0], self.plan["final_steps"][2],
            {"id": "early", "operator": "Filter_Aggregate", "input": "ps", "group_by": ["category"], "operation": "avg", "input_column": "total", "output_column": "avg_total"},
            {"id": "rp", "operator": "Integrate", "inputs": ["people", "ratings"], "left_on": ["id"], "right_on": ["owner"]},
            {"id": "rg", "operator": "Filter_Aggregate", "input": "rp", "group_by": ["category"], "operation": "avg", "input_column": "score", "output_column": "avg_rating"},
            {"operator": "Integrate", "inputs": ["early", "rg"], "join_key": ["category"]}]
        self.assertIn("required population", self.errors())

    def test_single_fact_dimension_comparison_can_use_raw_average(self):
        self.schemas.pop("ratings")
        self.plan["final_steps"] = [
            {"id": "ps", "operator": "Integrate", "inputs": ["people", "sales"], "left_on": ["id"], "right_on": ["owner"]},
            {"operator": "Filter_Aggregate", "group_by": ["category"], "operation": "avg", "input_column": "value", "output_column": "avg_total"}]
        self.plan["projection"].remove("avg_rating")
        contract = self.plan["comparative_contract"]
        contract["metrics"] = [contract["metrics"][0]]
        contract["metrics"][0]["inner_aggregate"] = "none"
        contract["required_population"] = ["people", "sales"]
        self.assertFalse(self.errors())

    def test_missing_contract_is_repairable_error(self):
        self.plan.pop("comparative_contract")
        self.assertIn("declare the comparison", self.errors())

    def test_scoped_prompt_requires_contract_even_if_model_omits_it(self):
        self.plan.pop("comparative_contract")
        self.plan.pop("comparative_contract_required")
        branches = [{"id": name, "fields": fields} for name, fields in self.schemas.items()]
        client = FakeClient(self.plan)
        result = load("llm_operators.final_spec").semantic_build_final_spec({
            "original_query": "Across region, how do spend and ratings compare using three related tables?",
            "processed_datasets": branches}, client)["final_spec"]
        self.assertTrue(result["comparative_contract_required"])
        self.assertIn("declare the comparison", " ".join(result["contract_errors"]))

    def test_two_table_and_ordinary_questions_are_not_forced_into_two_levels(self):
        needs = load("comparative_contract").needs_comparative_contract
        self.assertFalse(needs("Across category, how do values compare using two related tables?"))
        self.assertFalse(needs("List customers with the largest payments"))

    def test_bad_contract_shapes_return_errors(self):
        for replacement in [[], {"version": 2}, {"version": 1, "metrics": [None]}, {"version": 1, "metrics": [{}], "dimensions": [None]}]:
            with self.subTest(replacement=replacement):
                self.plan["comparative_contract"] = replacement
                self.assertTrue(self.errors())

    def test_compilation_keeps_contract_and_is_idempotent(self):
        first = self.compile()
        second = load("spec_runtime").compile_spec(first, self.schemas)
        self.assertEqual(first, second)

    def test_summary_cardinality_is_checked_against_actual_records(self):
        self.plan["final_steps"][2]["validate"] = "one_to_one"
        self.fixture.data["people"].append({"id": "a", "category": "Y"})
        plan = self.compile()
        self.assertFalse(plan["contract_errors"])
        _, log = load("execution").execute_spec(plan, self.fixture.data, registry(), dataset_schemas=self.schemas)
        self.assertIn("unique join keys", str(load("execution").execution_errors(log)))

    def test_missing_source_request_is_not_masked_by_missing_contract(self):
        client = FakeClient({"missing_requirements": [{"source_class": "Customers", "field": "region"}]})
        result = load("llm_operators.final_spec").semantic_build_final_spec({
            "original_query": "Across region, how do spend and ratings compare using three related tables?",
            "processed_datasets": [{"id": "sales", "fields": ["value"]}]}, client)["final_spec"]
        self.assertEqual(result["repair_stage"], "Query_Spec")
        self.assertNotIn("declare the comparison", " ".join(result["contract_errors"]))


if __name__ == "__main__":
    unittest.main()
