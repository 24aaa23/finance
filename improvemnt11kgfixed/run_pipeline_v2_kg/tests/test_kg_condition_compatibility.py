"""Regression coverage for the NULL/date failures observed in retrievals."""

from copy import deepcopy
import unittest

from support import FakeClient, load


class KGConditionCompatibilityTests(unittest.TestCase):
    def setUp(self):
        from kg_fixture import schema_for
        self.schema = {}
        for name in ("Records", "Other"):
            self.schema.update(schema_for(name, {"id": "numeric", "score": "numeric", "date": "date", "label": "categorical_string"}))

    def build(self, expected, actual, table="Records"):
        decomposition = {"answer_requirements": {"predicates": [
            {**expected, "id": "p1", "source_class": "Records", "branch_ids": ["q1"], "stage": "scan"}
        ]}}
        response = {"id": "q1", "retrieval_specs": [{"id": "q1", "class": table,
                    "entity_key": ["id"], "fields": ["id", "score", "date", "label"],
                    "filters": [actual]}]}
        result = load("llm_operators.query_spec").semantic_build_query_spec({
            "query": "Read matching records", "global_schema": self.schema,
            "subquestion": {"id": "q1", "source_class": "Records"},
            "decomposition": decomposition,
        }, FakeClient(response))["query_spec"]
        return result

    def test_observed_null_forms_pass_builder_and_execute_without_losing_rows(self):
        from kg_fixture import graph_for, execute_local
        graph = graph_for("Records", [
            {"id": 1, "score": None, "date": "2024-01-01", "label": "NULL"},
            {"id": 2, "score": 0, "date": "2024-01-02", "label": "x"},
            {"id": 3, "score": 5, "date": "2024-01-03", "label": None}])
        for operator, value, target in [("IS NOT", "NULL", "is_not_null"), ("IS NOT", None, "is_not_null"), ("IS", "NULL", "is_null")]:
            with self.subTest(operator=operator, value=value):
                result = self.build({"field": "score", "operator": operator, "value": value},
                                    {"field": "score", "operator": target, "value": None})
                self.assertEqual(result["contract_errors"], [])
                query = load("raw_query").render_raw_query(result["retrieval_specs"][0], self.schema)
                self.assertEqual(sorted(r["id"] for r in execute_local(graph, query)), [1] if target == "is_null" else [2, 3])

    def test_query_spec_legacy_null_syntax_is_normalized_too(self):
        result = self.build({"field": "score", "operator": "is_not_null", "value": None},
                            {"field": "score", "operator": "IS NOT", "value": "NULL"})
        self.assertEqual(result["contract_errors"], [])
        self.assertEqual(result["retrieval_specs"][0]["filters"][0]["operator"], "is_not_null")

    def test_between_string_and_array_agree_without_changing_endpoints(self):
        from kg_fixture import graph_for, execute_local
        graph = graph_for("Records", [{"id": 1, "date": "2024-01-01"}, {"id": 2, "date": "2024-12-31"}, {"id": 3, "date": "2025-01-01"}])
        for value in ["2024-01-01 AND 2024-12-31", "'2024-01-01' AND '2024-12-31'", "2024-01-01|2024-12-31"]:
            result = self.build({"field": "date", "operator": "BETWEEN", "value": value},
                                {"field": "date", "operator": "between", "value": ["2024-01-01", "2024-12-31"]})
            self.assertEqual(result["contract_errors"], [])
            query = load("raw_query").render_raw_query(result["retrieval_specs"][0], self.schema)
            self.assertEqual(sorted(r["id"] for r in execute_local(graph, query)), [1, 2])
        changed = self.build({"field": "date", "operator": "BETWEEN", "value": value},
                             {"field": "date", "operator": "between", "value": ["2024-01-02", "2024-12-31"]})
        self.assertTrue(any("drops or changes" in error for error in changed["contract_errors"]))

    def test_literal_null_stays_a_string_and_wrong_table_still_fails(self):
        normalize = load("conditions").normalize_condition
        predicate = {"field": "label", "operator": "=", "value": "NULL"}
        self.assertEqual(normalize(predicate), predicate)
        explicit_text = {"field": "label", "operator": "IS", "value": "NULL", "value_type": "string"}
        self.assertEqual(normalize(explicit_text), explicit_text)
        result = self.build(predicate, predicate, table="Other")
        self.assertTrue(any("changed assigned source" in error for error in result["contract_errors"]))
        result = self.build(predicate, {"field": "label", "operator": "is_null", "value": None})
        self.assertTrue(result["contract_errors"])

    def test_nested_conditions_preserve_scope_and_do_not_mutate_input(self):
        normalize = load("conditions").normalize_condition
        original = {"any": [{"field": "score", "operator": "IS NOT", "value": "NULL"},
                            {"not": {"field": "label", "operator": "=", "value": "NULL"}}]}
        saved = deepcopy(original)
        result = normalize(original)
        self.assertEqual(original, saved)
        self.assertEqual(result["any"][0]["operator"], "is_not_null")
        self.assertEqual(result["any"][1], original["any"][1])
        for value in ["A AND B", "2024-02-30 AND 2024-12-31", "2024-01-01 AND 2024-12-31 OR 1=1"]:
            predicate = {"field": "date", "operator": "BETWEEN", "value": value}
            self.assertEqual(normalize(predicate), predicate)

    def test_decompose_normalizes_requirements_before_query_spec(self):
        result = load("llm_operators.decompose")._cleanup_decomposition({
            "subquestions": [{"id": "q1", "source_class": "Records"}],
            "answer_requirements": {"predicates": [{"id": "p1", "field": "score", "operator": "IS NOT", "value": "NULL"}]},
        }, "Read records", ["Records"])
        predicate = result["selected_decomposition"]["answer_requirements"]["predicates"][0]
        self.assertEqual(predicate["operator"], "is_not_null")
        self.assertIsNone(predicate["value"])

    def test_unsupported_like_is_repaired_by_decompose_without_rewriting_it(self):
        predicate = {"id": "p1", "field": "date", "operator": "LIKE", "value": "2025%", "stage": "scan"}
        result = load("llm_operators.decompose")._cleanup_decomposition({
            "subquestions": [{"id": "q1", "source_class": "Records"}],
            "answer_requirements": {"predicates": [predicate]},
        }, "Net cash flow during calendar year 2025", ["Records"])["selected_decomposition"]
        self.assertTrue(any("Unsupported raw condition operator: like" in error for error in result["contract_errors"]))
        self.assertEqual(result["answer_requirements"]["predicates"][0], predicate)

    def test_early_shape_checks_accept_valid_operators_and_reject_ambiguous_ranges(self):
        errors = load("conditions").raw_condition_errors
        self.assertEqual(errors({"any": [
            {"field": "date", "operator": "between", "value": "2024-01-01|2024-12-31"},
            {"field": "score", "operator": "IS NOT", "value": "NULL"},
        ]}), [])
        self.assertTrue(errors({"field": "date", "operator": "between", "value": "2024 to 2025"}))
        self.assertTrue(errors({"field": "id", "operator": "in", "value": "1,2"}))
        self.assertTrue(errors({"any": []}))
        self.assertTrue(errors({"field": "label", "operator": "IS", "value": "NULL", "value_type": "string"}))
