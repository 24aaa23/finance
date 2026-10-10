from copy import deepcopy
import unittest

from support import load
from kg_fixture import schema_for, graph_for, execute_local


class RawKGTests(unittest.TestCase):
    def setUp(self):
        self.schema = schema_for("Records", {"id": "numeric", "name": "categorical_string",
                                             "amount": "numeric", "date": "date"})
        self.graph = graph_for("Records", [
            {"id": 1, "name": "O'Brien", "amount": 10, "date": "2024-01-01"},
            {"id": 2, "name": "O'Brien", "amount": 10, "date": "2024-12-31"},
            {"id": 3, "name": "NULL", "amount": None, "date": "2025-01-01"}])
        self.retrieval = {"class": "Records", "fields": ["subject_iri", "id", "name", "amount", "date"],
                          "entity_key": ["subject_iri"], "optional_fields": ["name", "amount", "date"], "filters": []}

    def rows(self, filters):
        retrieval = {**self.retrieval, "filters": filters}
        query = load("raw_query").render_raw_query(retrieval, self.schema)
        return sorted(execute_local(self.graph, query), key=lambda row: row["id"])

    def test_duplicates_remain_separate_subjects_and_missing_values_remain_none(self):
        rows = self.rows([])
        self.assertEqual([r["amount"] for r in rows], [10, 10, None])
        self.assertNotEqual(rows[0]["subject_iri"], rows[1]["subject_iri"])

    def test_typed_date_boundaries_and_numeric_comparison(self):
        rows = self.rows([{"field": "date", "operator": "between", "value": ["2024-01-01", "2024-12-31"]},
                          {"field": "amount", "operator": ">=", "value": 10}])
        self.assertEqual([r["id"] for r in rows], [1, 2])

    def test_null_presence_and_literal_null_are_different(self):
        for operator, ids in [("is_null", [3]), ("is_not_null", [1, 2])]:
            self.assertEqual([r["id"] for r in self.rows([{"field": "amount", "operator": operator}])], ids)
        self.assertEqual([r["id"] for r in self.rows([{"field": "name", "operator": "=", "value": "NULL"}])], [3])

    def test_nested_disjunction_keeps_unbound_rows_and_escaped_literals(self):
        self.assertEqual(len(self.rows([{"any": [
            {"field": "amount", "operator": "is_null"},
            {"field": "name", "operator": "=", "value": "O'Brien"}]}])), 3)

    def test_unknown_binding_and_invalid_range_are_rejected(self):
        bad = deepcopy(self.retrieval)
        bad["fields"].append("invented")
        self.assertIsNone(load("raw_query").render_raw_query(bad, self.schema))
        with self.assertRaises(ValueError):
            self.rows([{"field": "date", "operator": "between", "value": "bad range"}])

    def test_pre_scan_rejects_changed_population_and_field_projection(self):
        query = load("raw_query").render_raw_query(self.retrieval, self.schema)
        inputs = {"retrieval_spec": self.retrieval, "global_schema": self.schema, "sparql": query}
        validate = load("llm_operators.pre_scan_validate").semantic_pre_scan_validate
        self.assertTrue(validate(inputs)["pre_scan_validation"]["is_valid"])
        for changed in [query.replace("SELECT", "SELECT DISTINCT", 1), query + " LIMIT 1",
                        query.replace("urn:class:Records", "urn:class:Other")]:
            self.assertFalse(validate({**inputs, "sparql": changed})["pre_scan_validation"]["is_valid"])
