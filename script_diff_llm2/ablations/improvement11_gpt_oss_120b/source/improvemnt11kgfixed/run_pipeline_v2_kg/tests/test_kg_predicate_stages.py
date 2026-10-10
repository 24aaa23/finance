"""KG retrieval must not apply a declared aggregate condition to raw rows."""

from copy import deepcopy
import unittest

from support import FakeClient, load


class KGPredicateStageTests(unittest.TestCase):
    def setUp(self):
        from kg_fixture import schema_for
        self.schema = schema_for("CashFlow", {"id": "numeric", "amount": "numeric"})
        self.condition = {"id": "net_negative", "source_class": "CashFlow", "branch_ids": ["cash"],
                          "field": "amount", "operator": "<", "value": 0, "stage": "final"}
        self.decomposition = {"answer_requirements": {"predicates": [self.condition]}}
        self.retrieval = {"id": "cash", "class": "CashFlow", "entity_key": ["subject_iri"],
                          "fields": ["subject_iri", "id", "amount"], "filters": []}

    def build(self, filters, decomposition=None):
        retrieval = {**deepcopy(self.retrieval), "filters": filters}
        return load("llm_operators.query_spec").semantic_build_query_spec({
            "query": "Retrieve cash flow inputs for the net calculation", "global_schema": self.schema,
            "subquestion": {"id": "cash", "source_class": "CashFlow"},
            "decomposition": decomposition or self.decomposition,
        }, FakeClient({"id": "cash", "retrieval_specs": [retrieval]}))["query_spec"]

    def test_negative_net_requirement_cannot_drop_positive_input_transactions(self):
        from kg_fixture import graph_for, execute_local
        result = self.build([{"field": "amount", "operator": "<", "value": 0}])
        self.assertTrue(any("moves downstream predicate" in error for error in result["contract_errors"]))
        result = self.build([])
        self.assertEqual(result["contract_errors"], [])
        query = load("raw_query").render_raw_query(result["retrieval_specs"][0], self.schema)
        graph = graph_for("CashFlow", [{"id": 1, "amount": 100}, {"id": 2, "amount": -30}])
        self.assertEqual(sum(row["amount"] for row in execute_local(graph, query)), 70)

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
