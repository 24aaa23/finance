"""Compare multilevel execution with independent SQL on unequal populations."""
import sqlite3
import unittest

from support import FakeClient, load, registry


class ComparativeStepsTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            "people": [{"id": "a", "category": "X"}, {"id": "b", "category": "X"},
                       {"id": "c", "category": None}, {"id": "d", "category": "X"}],
            "sales": [{"owner": "a", "value": 10}, {"owner": "a", "value": 30},
                      {"owner": "b", "value": 100}, {"owner": "c", "value": 20},
                      {"owner": "c", "value": None}, {"owner": "d", "value": 999}],
            "ratings": [{"owner": "a", "score": 1}, {"owner": "a", "score": 3},
                        {"owner": "b", "score": 9}, {"owner": "c", "score": None}],
        }
        self.schemas = {"people": ["id", "category"], "sales": ["owner", "value"], "ratings": ["owner", "score"]}

    def sql(self, statement):
        with sqlite3.connect(":memory:") as db:
            db.row_factory = sqlite3.Row
            for name, fields in self.schemas.items():
                db.execute(f"CREATE TABLE {name} (" + ",".join(fields) + ")")
                db.executemany(f"INSERT INTO {name} VALUES (" + ",".join("?" for _ in fields) + ")",
                               [tuple(row.get(field) for field in fields) for row in self.data[name]])
            return [dict(row) for row in db.execute(statement)]

    def execute(self, steps, projection):
        plan = load("spec_runtime").compile_spec({"final_steps": steps, "projection": projection}, self.schemas)
        self.assertFalse(plan["contract_errors"], plan["contract_errors"])
        actual, log = load("execution").execute_spec(plan, self.data, registry(), dataset_schemas=self.schemas)
        self.assertFalse(load("execution").execution_errors(log), log)
        return actual, log

    def comparative_contract(self):
        return {
            "kind": "multi_step_comparative",
            "source_grain_before_join": ["owner"],
            "final_output_grain": ["category"],
            "metric_contracts": [
                {"metric": "sales total", "source_branch_ids": ["sales"],
                 "inner_aggregate": "sum", "outer_aggregate": "avg",
                 "output_column": "avg_total", "requires_pre_aggregation": True},
                {"metric": "rating", "source_branch_ids": ["ratings"],
                 "inner_aggregate": "avg", "outer_aggregate": "avg",
                 "output_column": "avg_rating", "requires_pre_aggregation": True},
            ],
        }

    def summaries(self):
        return [
            {"id": "s", "operator": "Filter_Aggregate", "input": "sales", "group_by": ["owner"],
             "operation": "sum", "input_column": "value", "output_column": "total"},
            {"id": "r", "operator": "Filter_Aggregate", "input": "ratings", "group_by": ["owner"],
             "operation": "avg", "input_column": "score", "output_column": "rating"},
            {"id": "ps", "operator": "Integrate", "inputs": ["people", "s"], "left_on": ["id"], "right_on": ["owner"], "join_type": "inner"},
            {"id": "joined", "operator": "Integrate", "inputs": ["ps", "r"], "left_on": ["id"], "right_on": ["owner"], "join_type": "inner"},
        ]

    def test_summarize_join_then_group_matches_sql_without_fanout(self):
        steps = self.summaries() + [{"operator": "Filter_Aggregate", "input": "joined", "group_by": ["category"],
                 "aggregations": [{"operation": "avg", "input_column": "total", "output_column": "avg_total"},
                                  {"operation": "avg", "input_column": "rating", "output_column": "avg_rating"}]}]
        actual, log = self.execute(steps, ["category", "avg_total", "avg_rating"])
        expected = self.sql('''WITH s AS (SELECT owner,SUM(value) total FROM sales GROUP BY owner),
            r AS (SELECT owner,AVG(score) rating FROM ratings GROUP BY owner)
            SELECT category,AVG(total) avg_total,AVG(rating) avg_rating FROM people p
            JOIN s ON p.id=s.owner JOIN r ON p.id=r.owner GROUP BY category''')
        self.assertCountEqual(actual, expected)
        self.assertIn({"category": "X", "avg_total": 70.0, "avg_rating": 5.5}, actual)
        self.assertEqual([entry["row_count"] for entry in log if entry.get("operator") == "Integrate"][:2], [4, 3])

    def test_multistep_contract_accepts_sql_style_two_stage_plan(self):
        steps = self.summaries() + [{"operator": "Filter_Aggregate", "input": "joined", "group_by": ["category"],
                 "aggregations": [{"operation": "avg", "input_column": "total", "output_column": "avg_total"},
                                  {"operation": "avg", "input_column": "rating", "output_column": "avg_rating"}]}]
        plan = load("spec_runtime").compile_spec({
            "semantic_contract": self.comparative_contract(),
            "final_steps": steps,
            "projection": ["category", "avg_total", "avg_rating"],
        }, self.schemas)
        self.assertFalse(plan["contract_errors"], plan["contract_errors"])

    def test_multistep_contract_rejects_raw_fact_join_before_summary(self):
        steps = [
            {"id": "ps", "operator": "Integrate", "inputs": ["people", "sales"], "left_on": ["id"], "right_on": ["owner"]},
            {"id": "joined", "operator": "Integrate", "inputs": ["ps", "ratings"], "left_on": ["id"], "right_on": ["owner"]},
            {"operator": "Filter_Aggregate", "input": "joined", "group_by": ["category"],
             "aggregations": [{"operation": "avg", "input_column": "value", "output_column": "avg_total"},
                              {"operation": "avg", "input_column": "score", "output_column": "avg_rating"}]},
        ]
        plan = load("spec_runtime").compile_spec({
            "semantic_contract": self.comparative_contract(),
            "final_steps": steps,
            "projection": ["category", "avg_total", "avg_rating"],
        }, self.schemas)
        self.assertTrue(any("must be aggregated" in error for error in plan["contract_errors"]), plan["contract_errors"])

    def test_multistep_contract_rejects_wrong_final_group(self):
        steps = self.summaries() + [{"operator": "Filter_Aggregate", "input": "joined", "group_by": ["id"],
                 "aggregations": [{"operation": "avg", "input_column": "total", "output_column": "avg_total"},
                                  {"operation": "avg", "input_column": "rating", "output_column": "avg_rating"}]}]
        plan = load("spec_runtime").compile_spec({
            "semantic_contract": self.comparative_contract(),
            "final_steps": steps,
            "projection": ["id", "avg_total", "avg_rating"],
        }, self.schemas)
        self.assertTrue(any("final_output_grain" in error or "final output grain" in error for error in plan["contract_errors"]),
                        plan["contract_errors"])

    def test_summary_formula_and_ranking_happen_after_merges(self):
        steps = self.summaries() + [
            {"operator": "Math_Compute", "input": "joined", "expression": "total - rating", "output_column": "pressure"},
            {"operator": "Order_By", "order_by": [{"column": "pressure", "direction": "DESC", "nulls": "last"}], "limit": 2}]
        actual, _ = self.execute(steps, ["id", "pressure"])
        expected = self.sql('''WITH s AS (SELECT owner,SUM(value) total FROM sales GROUP BY owner),
            r AS (SELECT owner,AVG(score) rating FROM ratings GROUP BY owner)
            SELECT p.id,total-rating pressure FROM people p JOIN s ON p.id=s.owner
            JOIN r ON p.id=r.owner ORDER BY pressure DESC NULLS LAST LIMIT 2''')
        self.assertEqual(actual, expected)

    def test_entity_and_category_summary_preserves_both_keys(self):
        self.data = {"events": [{"owner": "a", "kind": "x", "v": 2}, {"owner": "a", "kind": "y", "v": 3},
                                {"owner": "a", "kind": "x", "v": 4}, {"owner": "b", "kind": "x", "v": 8},
                                {"owner": "b", "kind": None, "v": 10}],
                     "ratings": self.data["ratings"]}
        self.schemas = {"events": ["owner", "kind", "v"], "ratings": ["owner", "score"]}
        steps = [{"id": "e", "operator": "Filter_Aggregate", "input": "events", "group_by": ["owner", "kind"],
                  "operation": "sum", "input_column": "v", "output_column": "total"},
                 self.summaries()[1],
                 {"id": "j", "operator": "Integrate", "inputs": ["e", "r"], "left_on": ["owner"], "right_on": ["owner"]},
                 {"operator": "Filter_Aggregate", "input": "j", "group_by": ["kind"], "aggregations": [
                     {"operation": "avg", "input_column": "total", "output_column": "avg_total"},
                     {"operation": "avg", "input_column": "rating", "output_column": "avg_rating"}]}]
        actual, _ = self.execute(steps, ["kind", "avg_total", "avg_rating"])
        expected = self.sql('''WITH e AS (SELECT owner,kind,SUM(v) total FROM events GROUP BY owner,kind),
            r AS (SELECT owner,AVG(score) rating FROM ratings GROUP BY owner)
            SELECT kind,AVG(total) avg_total,AVG(rating) avg_rating FROM e JOIN r ON e.owner=r.owner GROUP BY kind''')
        self.assertCountEqual(actual, expected)

    def test_final_planner_receives_branch_meaning_and_declared_connections(self):
        client = FakeClient({"final_steps": [], "final_output": "a", "projection": ["owner"]})
        connection = {"left_branch": "facts", "right_branch": "people", "left_on": ["owner"], "right_on": ["id"]}
        result = load("llm_operators.final_spec").semantic_build_final_spec({
            "processed_datasets": [{"id": "a", "branch_id": "facts", "question": "source responsibility marker",
                                    "fields": ["owner"], "retrieval_specs": [{"class": "Fact"}]}],
            "answer_requirements": {"joins": [connection], "predicates": []}}, client)
        self.assertFalse(result["final_spec"]["contract_errors"])
        prompt = client.calls[0]["messages"][0]["content"]
        self.assertIn("source responsibility marker", prompt)
        self.assertIn('"right_branch": "people"', prompt)

    def test_final_planner_carries_semantic_contract_into_compiler(self):
        contract = {
            "kind": "multi_step_comparative",
            "source_grain_before_join": ["owner"],
            "final_output_grain": ["category"],
            "metric_contracts": [
                {"source_branch_ids": ["sales"], "output_column": "avg_total",
                 "outer_aggregate": "avg", "requires_pre_aggregation": True}
            ],
        }
        payload = {"final_steps": [{"operator": "Filter_Aggregate", "input": "sales", "group_by": ["owner"],
                                   "operation": "sum", "input_column": "value", "output_column": "total"},
                                  {"operator": "Integrate", "inputs": ["people", "sales_summary"],
                                   "left_on": ["id"], "right_on": ["owner"]}],
                   "projection": ["category", "avg_total"]}
        client = FakeClient(payload)
        result = load("llm_operators.final_spec").semantic_build_final_spec({
            "processed_datasets": [
                {"id": "people", "fields": ["id", "category"], "retrieval_specs": [{"class": "People"}]},
                {"id": "sales", "fields": ["owner", "value"], "retrieval_specs": [{"class": "Sales"}]},
            ],
            "answer_requirements": {"semantic_contract": contract},
        }, client)["final_spec"]
        self.assertEqual(result["semantic_contract"]["kind"], "multi_step_comparative")

    def test_final_planner_maps_contract_branch_ids_to_processed_datasets(self):
        contract = {
            "kind": "multi_step_comparative",
            "source_grain_before_join": ["owner"],
            "final_output_grain": ["category"],
            "metric_contracts": [
                {"source_branch_ids": ["q_sales"], "output_column": "avg_total",
                 "outer_aggregate": "avg", "requires_pre_aggregation": True},
                {"source_branch_ids": ["q_rating"], "output_column": "avg_rating",
                 "outer_aggregate": "avg", "requires_pre_aggregation": True},
            ],
        }
        payload = {"final_steps": [
            {"id": "sales_by_owner", "operator": "Filter_Aggregate", "input": "q_sales_processed",
             "group_by": ["owner"], "operation": "sum", "input_column": "value", "output_column": "total"},
            {"id": "rating_by_owner", "operator": "Filter_Aggregate", "input": "q_rating_processed",
             "group_by": ["owner"], "operation": "avg", "input_column": "score", "output_column": "rating"},
            {"id": "people_sales", "operator": "Integrate", "inputs": ["q_people_processed", "sales_by_owner"],
             "left_on": ["id"], "right_on": ["owner"], "join_type": "inner"},
            {"id": "joined", "operator": "Integrate", "inputs": ["people_sales", "rating_by_owner"],
             "left_on": ["id"], "right_on": ["owner"], "join_type": "inner"},
            {"operator": "Filter_Aggregate", "input": "joined", "group_by": ["category"], "aggregations": [
                {"operation": "avg", "input_column": "total", "output_column": "avg_total"},
                {"operation": "avg", "input_column": "rating", "output_column": "avg_rating"}]}],
            "projection": ["category", "avg_total", "avg_rating"]}
        result = load("llm_operators.final_spec").semantic_build_final_spec({
            "query": "Across category, how do sales and ratings compare using two related tables?",
            "processed_datasets": [
                {"id": "q_people_processed", "branch_id": "q_people", "fields": ["id", "category"], "retrieval_specs": [{"class": "People"}]},
                {"id": "q_sales_processed", "branch_id": "q_sales", "fields": ["owner", "value"], "retrieval_specs": [{"class": "Sales"}]},
                {"id": "q_rating_processed", "branch_id": "q_rating", "fields": ["owner", "score"], "retrieval_specs": [{"class": "Rating"}]},
            ],
            "answer_requirements": {"semantic_contract": contract},
        }, FakeClient(payload))["final_spec"]
        self.assertFalse(result["contract_errors"], result["contract_errors"])
        metric_sources = result["semantic_contract"]["metric_contracts"]
        self.assertEqual(metric_sources[0]["source_branch_ids"], ["q_sales_processed"])

    def test_paired_changes_are_calculated_before_averaging(self):
        self.data = {"changes": [{"owner": "a", "before": 10, "after": 20},
                                  {"owner": "a", "before": None, "after": 100},
                                  {"owner": "a", "before": 30, "after": None},
                                  {"owner": "b", "before": None, "after": 8}]}
        self.schemas = {"changes": ["owner", "before", "after"]}
        actual, _ = self.execute([
            {"id": "d", "operator": "Math_Compute", "input": "changes",
             "expression": "after - before", "output_column": "change"},
            {"operator": "Filter_Aggregate", "input": "d", "group_by": ["owner"],
             "operation": "avg", "input_column": "change", "output_column": "avg_change"},
        ], ["owner", "avg_change"])
        expected = self.sql('SELECT owner,AVG(after-before) avg_change FROM changes GROUP BY owner')
        self.assertCountEqual(actual, expected)
        self.assertIn({"owner": "a", "avg_change": 10.0}, actual)

    def test_maximum_and_mean_stay_distinct_before_group_comparison(self):
        steps = self.summaries()
        steps[0].update(operation="max", output_column="peak")
        steps += [{"operator": "Filter_Aggregate", "input": "joined", "group_by": ["category"],
                   "aggregations": [
                       {"operation": "avg", "input_column": "peak", "output_column": "avg_peak"},
                       {"operation": "avg", "input_column": "rating", "output_column": "avg_rating"}]}]
        actual, _ = self.execute(steps, ["category", "avg_peak", "avg_rating"])
        expected = self.sql('''WITH s AS (SELECT owner,MAX(value) peak FROM sales GROUP BY owner),
            r AS (SELECT owner,AVG(score) rating FROM ratings GROUP BY owner)
            SELECT category,AVG(peak) avg_peak,AVG(rating) avg_rating FROM people p
            JOIN s ON p.id=s.owner JOIN r ON p.id=r.owner GROUP BY category''')
        self.assertCountEqual(actual, expected)

    def test_signed_totals_preserve_one_sided_zero_and_null_only_entities(self):
        self.data = {"flows": [{"owner": "a", "amount": 10}, {"owner": "a", "amount": -3},
                               {"owner": "b", "amount": -5}, {"owner": "c", "amount": None},
                               {"owner": "d", "amount": 0}, {"owner": "e", "amount": 7}]}
        self.schemas = {"flows": ["owner", "amount"]}
        # Positive/negative parts use existing arithmetic. CASE syntax is not
        # supported; filtering before grouping would wrongly lose some owners.
        actual, _ = self.execute([
            {"id": "positive", "operator": "Math_Compute", "input": "flows",
             "expression": "(abs(coalesce(amount, 0)) + coalesce(amount, 0)) / 2", "output_column": "inflow"},
            {"id": "signed", "operator": "Math_Compute", "input": "positive",
             "expression": "(abs(coalesce(amount, 0)) - coalesce(amount, 0)) / 2", "output_column": "outflow"},
            {"operator": "Filter_Aggregate", "input": "signed", "group_by": ["owner"], "aggregations": [
                {"operation": "sum", "input_column": "inflow", "output_column": "inflow"},
                {"operation": "sum", "input_column": "outflow", "output_column": "outflow"}]}],
            ["owner", "inflow", "outflow"])
        expected = self.sql('''SELECT owner,
            SUM(CASE WHEN amount>0 THEN amount ELSE 0 END) inflow,
            -SUM(CASE WHEN amount<0 THEN amount ELSE 0 END) outflow
            FROM flows GROUP BY owner''')
        self.assertCountEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
