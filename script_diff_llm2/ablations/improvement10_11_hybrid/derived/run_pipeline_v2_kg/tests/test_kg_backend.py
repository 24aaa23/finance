import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from support import load

backend = load("kg_backend")
XSD = backend.XSD


class KGBackendTests(unittest.TestCase):
    def test_typed_values_and_unbound_columns_preserve_rows(self):
        payload = {"head": {"vars": ["id", "n", "amount", "date", "flag", "missing"]},
                   "results": {"bindings": [{
                       "id": {"type": "uri", "value": "urn:row:1"},
                       "n": {"type": "literal", "datatype": XSD + "integer", "value": "3"},
                       "amount": {"type": "literal", "datatype": XSD + "decimal", "value": "12.5"},
                       "date": {"type": "literal", "datatype": XSD + "date", "value": "2024-01-01"},
                       "flag": {"type": "literal", "datatype": XSD + "boolean", "value": "false"}}]}}
        rows, fields = backend.parse_sparql_json(payload)
        self.assertEqual(rows, [{"id": "urn:row:1", "n": 3, "amount": 12.5,
                                "date": "2024-01-01", "flag": False, "missing": None}])
        self.assertEqual(fields, payload["head"]["vars"])

    def test_transport_preserves_empty_success_and_explicit_columns(self):
        payload = {"head": {"vars": ["id"]}, "results": {"bindings": []}}
        with patch.object(backend.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(payload).encode())) as request:
            result = backend.execute_sparql("SELECT ?id WHERE { ?id ?p ?o }", "http://localhost/query", 5)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"], [])
        self.assertEqual(result["columns"], ["id"])
        self.assertEqual(request.call_args.kwargs["timeout"], 5)

    def test_mutations_service_and_other_result_forms_never_reach_transport(self):
        for query in ["INSERT DATA { <urn:s> <urn:p> <urn:o> }", "DELETE WHERE { ?s ?p ?o }",
                      "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }",
                      "SELECT ?s WHERE { SERVICE <http://remote/query> { ?s ?p ?o } }"]:
            with self.subTest(query=query), patch.object(backend.urllib.request, "urlopen") as request:
                self.assertEqual(backend.execute_sparql(query, "http://localhost/query")["status"], "error")
                request.assert_not_called()

    def test_connection_timeout_and_malformed_response_are_errors(self):
        query = "SELECT ?s WHERE { ?s ?p ?o }"
        for failure in [TimeoutError("timed out"), urllib.error.URLError("connection refused")]:
            with patch.object(backend.urllib.request, "urlopen", side_effect=failure):
                result = backend.execute_sparql(query, "http://localhost/query")
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["failed_sparql"], query)
        with patch.object(backend.urllib.request, "urlopen", return_value=io.BytesIO(b"not JSON")):
            self.assertEqual(backend.execute_sparql(query, "http://localhost/query")["status"], "error")

    def test_wrong_or_empty_endpoint_population_rejected(self):
        metadata = {"Records": {"class_iri": "urn:Records", "instance_count": 2}}
        with patch.object(backend, "execute_sparql", return_value={"status": "success", "data": []}):
            with self.assertRaisesRegex(RuntimeError, "populations differ"):
                backend.check_kg_health("http://localhost/query", metadata)
