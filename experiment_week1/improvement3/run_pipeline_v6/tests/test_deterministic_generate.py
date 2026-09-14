import unittest

from support import FakeClient, load


class DeterministicGenerateTests(unittest.TestCase):
    def setUp(self):
        self.generate = load("llm_operators.generate")
        self.schema = {
            "Record": {
                "class_iri": "http://example.test/Record",
                "subject_field": "subject_iri",
                "property_iris": {
                    "amount": "http://example.test/amount",
                    "when": "http://example.test/when",
                    "label": "http://example.test/label",
                },
                "columns": [
                    {"name": "subject_iri"}, {"name": "amount"},
                    {"name": "when", "rdf_datatypes": ["http://www.w3.org/2001/XMLSchema#date"]},
                    {"name": "label"},
                ],
            }
        }

    def test_valid_contract_is_compiled_without_model(self):
        result = self.generate.semantic_generate_sparql({
            "query": "records",
            "global_schema": self.schema,
            "retrieval_spec": {
                "class": "Record", "fields": ["subject_iri", "amount", "when", "label"],
                "optional_fields": ["label"],
                "filters": [{"field": "amount", "operator": ">", "value": 10, "value_type": "number"},
                            {"field": "when", "operator": ">=", "value": "2025-01-01", "value_type": "date"}],
            },
        }, FakeClient("must not be called"), "test-model")
        query = result["sparql"]
        self.assertIn("PREFIX rdf:", query)
        self.assertIn("OPTIONAL", query)
        self.assertIn("?f_amount > 10", query)
        self.assertIn("^^<http://www.w3.org/2001/XMLSchema#date>", query)

    def test_incomplete_metadata_uses_model_fallback(self):
        client = FakeClient("SELECT * WHERE { ?s ?p ?o }")
        result = self.generate.semantic_generate_sparql({
            "query": "records", "global_schema": {"Record": {}},
            "retrieval_spec": {"class": "Record", "fields": ["subject_iri"]},
        }, client, "test-model")
        self.assertEqual(len(client.calls), 1)
        self.assertIn("SELECT", result["sparql"])

    def test_logical_filter_group_preserves_or(self):
        query = self.generate._compile_contract_sparql({
            "class": "Record", "fields": ["subject_iri", "amount", "label"],
            "filters": [{"logic": "or", "conditions": [
                {"field": "amount", "operator": ">", "value": 10, "value_type": "number"},
                {"field": "label", "operator": "=", "value": "priority", "value_type": "string"},
            ]}],
        }, self.schema)
        self.assertIn("||", query)
        self.assertNotIn("&&", query)


if __name__ == "__main__":
    unittest.main()
