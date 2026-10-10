"""Opt-in checks against the project-local graph; no model requests.

Set KG_TEST_ENDPOINT to the read-only Fuseki query URL to run these checks.
"""
import os
import unittest
from support import SOURCE, load


@unittest.skipUnless(os.getenv("KG_TEST_ENDPOINT"), "Live KG endpoint not selected")
class LiveKGTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.endpoint = os.environ["KG_TEST_ENDPOINT"]
        cls.backend = load("kg_backend")
        cls.schema = load("kg_metadata").load_kg_metadata(
            SOURCE.parent / "kg_output_fixed/wealth_management_diverse_schema.ttl",
            SOURCE.parent / "kg_output_fixed/wealth_management_diverse_kg.ttl",
            SOURCE.parent / ".runtime/kg_metadata")

    def scan(self, source, fields, filters=None):
        retrieval = {"class": source, "fields": ["subject_iri", *fields], "entity_key": ["subject_iri"],
                     "optional_fields": fields, "filters": filters or []}
        query = load("raw_query").render_raw_query(retrieval, self.schema)
        result = self.backend.execute_sparql(query, self.endpoint)
        self.assertEqual(result["status"], "success", result)
        return result

    def oracle(self, query):
        result = self.backend.execute_sparql(query, self.endpoint)
        self.assertEqual(result["status"], "success", result)
        return result["data"]

    def test_endpoint_populations_match_all_local_domain_classes(self):
        self.backend.check_kg_health(self.endpoint, self.schema)

    def test_numeric_filter_and_sum_match_direct_graph_calculation(self):
        rows = self.scan("PortfolioHolding", ["currentValue"],
                         [{"field": "currentValue", "operator": ">", "value": 1000000}])["data"]
        expected = self.oracle('SELECT (COUNT(*) AS ?n) (SUM(?v) AS ?total) WHERE { ?s a <https://wealth.example.org/ontology/PortfolioHolding> ; <https://wealth.example.org/ontology/currentValue> ?v . FILTER(?v > 1000000) }')[0]
        self.assertEqual(len(rows), expected["n"])
        self.assertAlmostEqual(sum(row["currentValue"] for row in rows), expected["total"], places=4)

    def test_date_window_matches_graph_and_returns_iso_dates(self):
        rows = self.scan("PortfolioHolding", ["purchaseDate"],
            [{"field": "purchaseDate", "operator": "between", "value": ["2024-01-01", "2024-12-31"]}])["data"]
        expected = self.oracle('PREFIX xsd: <http://www.w3.org/2001/XMLSchema#> SELECT (COUNT(*) AS ?n) WHERE { ?s a <https://wealth.example.org/ontology/PortfolioHolding> ; <https://wealth.example.org/ontology/purchaseDate> ?date . FILTER(?date >= "2024-01-01"^^xsd:date && ?date <= "2024-12-31"^^xsd:date) }')[0]
        self.assertEqual(len(rows), expected["n"])
        self.assertTrue(all("2024-01-01" <= row["purchaseDate"] <= "2024-12-31" for row in rows))

    def test_actual_iri_links_match_investor_identity_and_literal_ids(self):
        investors = self.scan("Investor", ["investorId"])["data"]
        by_subject = {row["subject_iri"]: row["investorId"] for row in investors}
        holdings = self.scan("PortfolioHolding", ["heldByInvestor", "investorId"])["data"]
        self.assertEqual(len(holdings), 15102)
        self.assertTrue(all(by_subject[row["heldByInvestor"]] == row["investorId"] for row in holdings))

    def test_empty_query_is_success_with_declared_columns(self):
        result = self.scan("Investor", ["investorId"],
                           [{"field": "investorId", "operator": "=", "value": "__KG_TEST_ABSENT__"}])
        self.assertEqual(result["data"], [])
        self.assertEqual(result["columns"], ["subject_iri", "investorId"])
