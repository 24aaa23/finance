"""SQL retrieval must not apply a declared aggregate condition to raw rows."""

from copy import deepcopy
import sqlite3
import unittest

from support import FakeClient, load


class SQLPredicateStageTests(unittest.TestCase):
    def setUp(self):
        self.schema = {"CashFlow": {"backend": "sqlite", "sql_table": "CashFlow", "columns": [
            {"name": "id", "datatype": "numeric"}, {"name": "amount", "datatype": "numeric"}]}}
        self.condition = {"id": "net_negative", "source_class": "CashFlow", "branch_ids": ["cash"],
                          "field": "amount", "operator": "<", "value": 0, "stage": "final"}
        self.decomposition = {"answer_requirements": {"predicates": [self.condition]}}
        self.retrieval = {"id": "cash", "class": "CashFlow", "entity_key": ["id"],
                          "fields": ["id", "amount"], "filters": []}

    def build(self, filters, decomposition=None):
        retrieval = {**deepcopy(self.retrieval), "filters": filters}
        return load("llm_operators.query_spec").semantic_build_query_spec({
            "query": "Retrieve cash flow inputs for the net calculation", "global_schema": self.schema,
            "subquestion": {"id": "cash", "source_class": "CashFlow"},
            "decomposition": decomposition or self.decomposition,
        }, FakeClient({"id": "cash", "retrieval_specs": [retrieval]}))["query_spec"]

    def test_negative_net_requirement_cannot_drop_positive_input_transactions(self):
        result = self.build([{"field": "amount", "operator": "<", "value": 0}])
        self.assertTrue(any("moves downstream predicate" in error for error in result["contract_errors"]))
        result = self.build([])
        self.assertEqual(result["contract_errors"], [])
        sql = load("raw_sql").render_raw_sql(result["retrieval_specs"][0], self.schema)
        with sqlite3.connect(":memory:") as db:
            db.execute('CREATE TABLE CashFlow (id INTEGER, amount REAL)')
            db.executemany('INSERT INTO CashFlow VALUES (?, ?)', [(1, 100), (2, -30)])
            self.assertEqual(sum(row[1] for row in db.execute(sql)), 70)

    def test_explicitly_required_raw_condition_is_still_allowed(self):
        decomposition = deepcopy(self.decomposition)
        decomposition["answer_requirements"]["predicates"].append({**self.condition, "id": "negative_transactions", "stage": "scan"})
        result = self.build([{"field": "amount", "operator": "<", "value": 0}], decomposition)
        self.assertEqual(result["contract_errors"], [])

    def test_unrelated_branch_cannot_authorize_premature_filter(self):
        decomposition = deepcopy(self.decomposition)
        decomposition["answer_requirements"]["predicates"].append({**self.condition, "id": "other_branch", "stage": "scan", "branch_ids": ["other"]})
        result = self.build([{"field": "amount", "operator": "<", "value": 0}], decomposition)
        self.assertTrue(any("moves downstream predicate" in error for error in result["contract_errors"]))

    def test_nested_raw_condition_does_not_bypass_stage_guard(self):
        result = self.build([{"all": [{"field": "amount", "operator": "<", "value": 0}]}])
        self.assertTrue(any("moves downstream predicate" in error for error in result["contract_errors"]))

    def test_downstream_input_must_still_be_selected(self):
        spec = {"id": "cash", "branch_id": "cash", "retrieval_specs": [{**self.retrieval, "fields": ["id"]}]}
        errors = load("llm_operators.query_spec")._answer_requirement_errors(spec, self.decomposition, self.schema)
        self.assertTrue(any("omits downstream predicate input" in error for error in errors))
