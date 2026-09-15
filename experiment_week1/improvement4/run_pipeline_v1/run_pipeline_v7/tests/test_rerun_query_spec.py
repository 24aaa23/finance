"""Real rerun failure shapes, with domain-independent synthetic field names."""

import unittest

from support import FakeClient, load


class RerunQuerySpecTests(unittest.TestCase):
    def setUp(self):
        self.query_spec = load("llm_operators.query_spec")
        self.schema = {"Record": {"columns": ["id", "category", "amount", "code"]}}

    def build(self, retrieval, requirements=None):
        client = FakeClient({"id": "source", "retrieval_specs": [retrieval]})
        return self.query_spec.semantic_build_query_spec({
            "query": "Retrieve the branch's raw records.",
            "subquestion": {"id": "source", "source_class": "Record"},
            "retrieved_tables": ["Record"],
            "global_schema": self.schema,
            "decomposition": {"answer_requirements": requirements or {}},
        }, client)["query_spec"]

    def test_optional_selection_and_entity_key_survive_separate_lists(self):
        spec = self.build({
            "class": "Record", "entity_key": ["id"], "fields": ["amount"],
            "optional_fields": ["category", "amount"], "filters": [],
        }, {"group_by": ["category"], "preserve_null_groups": True})
        self.assertEqual(spec["contract_errors"], [])
        self.assertEqual(spec["retrieval_specs"][0]["fields"], ["amount", "id", "category"])
        self.assertEqual(spec["retrieval_specs"][0]["optional_fields"], ["amount", "category"])

    def test_unknown_optional_field_still_fails_schema_validation(self):
        spec = self.build({
            "class": "Record", "entity_key": ["id"], "fields": ["id"],
            "optional_fields": ["invented"], "filters": [],
        })
        self.assertTrue(any("field is not on Record: invented" in error for error in spec["contract_errors"]))

    def test_cleanup_preserves_optional_missing_value_during_scan_contract(self):
        original = {
            "retrieval_specs": [{"class": "Record", "entity_key": "id", "fields": ["id"],
                                 "optional_fields": [["category"]], "filters": []}],
        }
        once = self.query_spec.cleanup_query_spec(original, "", ["Record"])
        twice = self.query_spec.cleanup_query_spec(once, "", ["Record"])
        self.assertEqual(once["retrieval_specs"], twice["retrieval_specs"])
        self.assertEqual(once["retrieval_specs"][0]["optional_fields"], ["category"])
        self.assertEqual(original["retrieval_specs"][0]["fields"], ["id"])

    def predicate_spec(self, expected, actual):
        return self.build({
            "class": "Record", "entity_key": ["id"], "fields": ["id"], "filters": [actual],
        }, {"predicates": [{"source_class": "Record", "branch_ids": ["source"], **expected}]})

    def test_number_literal_representation_does_not_change_predicate(self):
        spec = self.predicate_spec(
            {"field": "amount", "operator": "<", "value": "5"},
            {"field": "amount", "operator": "<", "value": 5.0, "value_type": "number"},
        )
        self.assertEqual(spec["contract_errors"], [])

    def test_null_operator_spellings_do_not_change_predicate(self):
        spec = self.predicate_spec(
            {"field": "amount", "operator": "is not null", "value": None},
            {"field": "amount", "operator": "is_not_null"},
        )
        self.assertEqual(spec["contract_errors"], [])

    def test_actual_predicate_changes_are_still_rejected(self):
        for actual in [
            {"field": "amount", "operator": "<=", "value": 5, "value_type": "number"},
            {"field": "amount", "operator": "<", "value": 6, "value_type": "number"},
        ]:
            with self.subTest(actual=actual):
                spec = self.predicate_spec({"field": "amount", "operator": "<", "value": "5"}, actual)
                self.assertTrue(any("drops or changes required predicate" in error for error in spec["contract_errors"]))

    def test_categorical_literals_keep_exact_spelling(self):
        spec = self.predicate_spec(
            {"field": "code", "operator": "=", "value": "005"},
            {"field": "code", "operator": "=", "value": "5", "value_type": "string"},
        )
        self.assertTrue(any("drops or changes required predicate" in error for error in spec["contract_errors"]))

    def test_other_branch_predicate_is_not_required_here(self):
        spec = self.build({"class": "Record", "entity_key": ["id"], "fields": ["id"], "filters": []}, {
            "predicates": [{"source_class": "Record", "branch_ids": ["other"],
                            "field": "amount", "operator": ">", "value": 100}],
        })
        self.assertEqual(spec["contract_errors"], [])


if __name__ == "__main__":
    unittest.main()
