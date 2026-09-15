"""Exercise V10 entrypoints and the examples actually sent to the model."""
import contextlib
import io
import os
from pathlib import Path
import runpy
import sqlite3
import sys
import types
import unittest
from unittest.mock import Mock, patch

import rdflib

from support import FakeClient, SOURCE, load


class V10EntrypointTests(unittest.TestCase):
    def test_direct_launcher_calls_v10_from_another_working_directory(self):
        main = types.ModuleType("run_pipeline_v10.main")
        main.main = Mock()
        old_path, old_cwd = sys.path[:], Path.cwd()
        try:
            os.chdir(SOURCE / "tests")
            with patch.dict(sys.modules, {main.__name__: main}):
                runpy.run_path(str(SOURCE / "run.py"), run_name="__main__")
            main.main.assert_called_once_with()
        finally:
            sys.path[:] = old_path
            os.chdir(old_cwd)

    def test_default_configuration_uses_v10_outputs_and_existing_inputs(self):
        # Import the actual configuration without reading local credentials or
        # creating output folders. No clients are constructed by common.py.
        with patch.dict(os.environ, {}, clear=True), \
                patch("os.path.exists", return_value=False), patch("os.makedirs"):
            config = runpy.run_path(str(SOURCE / "common.py"))
        self.assertEqual(config["PIPELINE_VERSION"], "aop-improvement3-v10")
        self.assertEqual(Path(config["OUTPUT_DIR"]), SOURCE / "outputs")
        self.assertEqual(Path(config["REPORT_FILE"]), SOURCE / "outputs" / "raw_pipeline_v10.csv")
        for name in ("SCHEMA_FILE", "INSTANCE_FILE", "INPUT_SAMPLE_FILE"):
            with self.subTest(setting=name):
                self.assertTrue(Path(config[name]).is_file(), config[name])


class V10RetrievalPromptTests(unittest.TestCase):
    def setUp(self):
        self.schema = {"Record": {"class_iri": "urn:Record", "subject_field": "record", "columns": [
            {"name": "record", "datatype": "resource_iri", "type": "Subject"},
            {"name": "value", "predicate_iri": "urn:value", "datatype": "number"},
            {"name": "label", "predicate_iri": "urn:label", "datatype": "string"},
        ]}}
        self.retrieval = {"class": "Record", "entity_key": ["record"],
                          "fields": ["record", "value", "label"], "filters": []}
        client = FakeClient("SELECT ?record ?value WHERE { ?record a <urn:Record> }")
        with patch.object(load("utils"), "repair_sparql_for_query", lambda text, query: text, create=True):
            generate = load("llm_operators.generate").semantic_generate_sparql
        with contextlib.redirect_stdout(io.StringIO()):
            generate({"query": "Read records", "retrieved_tables": ["Record"],
                      "global_schema": self.schema, "retrieval_spec": self.retrieval}, client, "offline")
        self.prompt = client.calls[0]["messages"][0]["content"]
        self.rows = [("urn:a", 5), ("urn:b", 10), ("urn:c", 20), ("urn:d", None)]
        self.graph = rdflib.Graph()
        for record, value in self.rows:
            self.graph.add((rdflib.URIRef(record), rdflib.RDF.type, rdflib.URIRef("urn:Record")))
            if value is not None:
                self.graph.add((rdflib.URIRef(record), rdflib.URIRef("urn:value"), rdflib.Literal(value)))

    def test_actual_prompt_filter_examples_match_sql(self):
        # Parse and execute the f-string's output, not a separately retyped prompt.
        # Wrong FILTER placement retains failing rows and is caught by the oracle.
        cases = {"Range": "value > 10", "Missing": "value IS NULL", "Present": "value IS NOT NULL"}
        with sqlite3.connect(":memory:") as db:
            db.execute("CREATE TABLE records(record TEXT, value REAL)")
            db.executemany("INSERT INTO records VALUES (?, ?)", self.rows)
            for label, condition in cases.items():
                with self.subTest(example=label):
                    pattern = self.prompt.split("\n  " + label + ": ", 1)[1].split("\n", 1)[0]
                    query = "SELECT ?record ?value WHERE { ?record a <urn:Record> . " + pattern + " }"
                    actual = [(str(row.record), row.value.toPython() if row.value is not None else None)
                              for row in self.graph.query(query)]
                    expected = list(db.execute("SELECT record, value FROM records WHERE " + condition))
                    self.assertCountEqual(actual, expected)

    def test_optional_normalization_preserves_range_and_null_predicates(self):
        for predicate in ({"field": "value", "operator": ">", "value": 10, "value_type": "number"},
                          {"field": "value", "operator": "is_null", "value": None, "value_type": "null"},
                          {"field": "value", "operator": "is_not_null", "value": None, "value_type": "null"}):
            with self.subTest(predicate=predicate):
                client = FakeClient({"retrieval_specs": [{**self.retrieval, "filters": [predicate]}]})
                result = load("llm_operators.query_spec").semantic_build_query_spec({
                    "query": "Read records with the requested condition", "retrieved_tables": ["Record"],
                    "global_schema": self.schema}, client)["query_spec"]
                self.assertFalse(result["contract_errors"])
                retrieval = result["retrieval_specs"][0]
                self.assertTrue({"value", "label"}.issubset(retrieval["optional_fields"]))
                self.assertNotIn("record", retrieval["optional_fields"])
                self.assertEqual(retrieval["filters"], [predicate])


if __name__ == "__main__":
    unittest.main()
