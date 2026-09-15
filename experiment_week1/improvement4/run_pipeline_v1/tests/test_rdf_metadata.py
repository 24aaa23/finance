"""Subject identity and standard RDF labels work without domain-specific class lists."""
import contextlib
import io
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import rdflib

from support import FakeClient, PACKAGE, common, load


class RdfMetadataTests(unittest.TestCase):
    def setUp(self):
        self.graph = rdflib.Graph().parse(data='''
            @prefix ex: <https://sample.invalid/> .
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
            ex:Category a owl:Class .
            ex:Item a owl:Class .
            ex:a a ex:Category ; rdfs:label "Alpha" .
            ex:b a ex:Category .
            ex:item a ex:Item ; ex:category ex:a ; ex:at "2025-01-01"^^xsd:date .
        ''', format="turtle")
        utils = sys.modules[PACKAGE + ".utils"]
        def local_name(value):
            return str(value).rsplit("#", 1)[-1].rsplit("/", 1)[-1]
        fake_fuseki = types.ModuleType(PACKAGE + ".non_llm_operators.fuseki")
        def metadata_query(query, endpoint, timeout):
            # Execute the actual loader's metadata query on an independent RDF
            # graph, rather than returning a hardcoded metadata response.
            result = self.graph.query(query)
            return {"status": "success", "data": [
                {str(key): str(value) for key, value in row.asdict().items()} for row in result]}
        fake_fuseki.execute_sparql_on_fuseki = metadata_query
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(common, "ALIAS_MAP_FILE", "", create=True))
            stack.enter_context(patch.object(common, "FUSEKI_ENDPOINT", "offline", create=True))
            stack.enter_context(patch.object(common, "FUSEKI_METADATA_TIMEOUT_SECONDS", 1, create=True))
            stack.enter_context(patch.object(utils, "local_name", local_name, create=True))
            stack.enter_context(patch.object(utils, "load_rdf_id_alias_map", lambda *args: {}, create=True))
            stack.enter_context(patch.dict(sys.modules, {fake_fuseki.__name__: fake_fuseki}))
            folder = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            schema = folder / "schema.ttl"
            self.graph.serialize(destination=str(schema), format="turtle")
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            self.metadata = load("schema_loader").load_rdf_knowledge_graph(str(schema), "unused.ttl")

    def test_metadata_exposes_real_label_and_subject_identity(self):
        category = self.metadata["Category"]
        self.assertEqual(category["class_iri"], "https://sample.invalid/Category")
        self.assertEqual(category["subject_field"], "subject_iri")
        columns = {col["name"]: col for col in category["columns"]}
        self.assertEqual(columns["rdfs_label"]["predicate_iri"], str(rdflib.RDFS.label))
        self.assertNotIn("predicate_iri", columns["subject_iri"])
        self.assertNotIn("label_field", self.metadata["Item"])
        self.assertEqual(self.metadata["Item"]["property_iris"]["category"], "https://sample.invalid/category")

    def test_date_physical_datatype_survives_metadata_loading(self):
        column = next(col for col in self.metadata["Item"]["columns"] if col["name"] == "at")
        self.assertEqual(column["rdf_datatypes"], ["http://www.w3.org/2001/XMLSchema#date"])

    def test_query_spec_accepts_rdf_label_and_adds_subject_key(self):
        result = load("llm_operators.query_spec").semantic_build_query_spec({
            "query": "List categories and their labels", "retrieved_tables": ["Category"],
            "global_schema": self.metadata,
        }, FakeClient({"retrieval_specs": [{"class": "Category", "fields": ["rdfs:label"],
                                            "optional_fields": ["rdfs:label"], "filters": []}]}))["query_spec"]
        self.assertFalse(result["contract_errors"])
        retrieval = result["retrieval_specs"][0]
        self.assertEqual(retrieval["entity_key"], ["subject_iri"])
        self.assertEqual(retrieval["fields"], ["rdfs_label", "subject_iri"])
        self.assertEqual(retrieval["optional_fields"], ["rdfs_label"])

    def test_rdf_subject_label_binding_preserves_unlabeled_nodes(self):
        query = '''SELECT ?subject_iri ?rdfs_label WHERE {
            ?subject_iri a <https://sample.invalid/Category> .
            OPTIONAL { ?subject_iri <http://www.w3.org/2000/01/rdf-schema#label> ?rdfs_label }
        }'''
        rows = [{str(key): str(value) if value is not None else None for key, value in zip(row.labels, row)}
                for row in self.graph.query(query)]
        self.assertCountEqual(rows, [{"subject_iri": "https://sample.invalid/a", "rdfs_label": "Alpha"},
                                     {"subject_iri": "https://sample.invalid/b", "rdfs_label": None}])

    def test_bad_json_cannot_become_an_unfiltered_subject_scan(self):
        result = load("llm_operators.query_spec").semantic_build_query_spec({
            "query": "Only matching categories", "retrieved_tables": ["Category"],
            "global_schema": self.metadata,
        }, FakeClient("invalid json"))["query_spec"]
        self.assertTrue(result["contract_errors"])


if __name__ == "__main__":
    unittest.main()
