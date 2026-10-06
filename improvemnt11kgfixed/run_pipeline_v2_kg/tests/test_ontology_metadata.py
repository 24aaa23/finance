from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from support import SOURCE, load


class OntologyMetadataTests(unittest.TestCase):
    def test_real_ontology_maps_documented_attribute_to_queryable_property(self):
        root = SOURCE.parent
        schema = load("kg_metadata").load_kg_metadata(root / "kg_output_fixed/wealth_management_diverse_schema.ttl",
            root / "kg_output_fixed/wealth_management_diverse_kg.ttl", root / ".runtime/kg_metadata")
        self.assertEqual(len(schema), 22)
        holding = schema["PortfolioHolding"]
        self.assertEqual(holding["instance_count"], 15102)
        column = next(c for c in holding["columns"] if c["name"] == "currentValue")
        self.assertEqual(column["ontology_attribute"], "current_value")
        self.assertIn("market value", column["synonyms"])
        self.assertEqual(holding["subject_field"], "subject_iri")
        self.assertNotIn("PrimitiveAttribute", schema)

    def test_knowledge_schema_excludes_instance_counts_but_includes_rdf_bindings(self):
        schema = {"Items": {"backend": "rdf", "class_iri": "urn:Items", "subject_field": "subject_iri",
                  "instance_count": 4, "sample_rows": ["ROW_SECRET"],
                  "columns": [{"name": "value", "predicate_iri": "urn:value", "rdf_datatypes": ["urn:type"]}]}}
        physical = load("knowledge").physical_schema(schema)
        changed = deepcopy(schema)
        changed["Items"]["instance_count"] = 99
        self.assertEqual(physical, load("knowledge").physical_schema(changed))
        self.assertNotIn("sample_rows", physical["Items"])
        self.assertEqual(physical["Items"]["columns"][0]["predicate_iri"], "urn:value")

    def test_documents_are_exact_ontology_domain_and_rules_and_iri_is_not_private_path(self):
        root = SOURCE.parent
        documents = load("knowledge").load_documents(root / "domain_intro_latest.prompt",
            root / "business_rules_addendum.md", root / "kg_output_fixed/wealth_management_diverse_schema.ttl")
        self.assertEqual([d["id"] for d in documents], ["domain", "rules", "ontology"])
        self.assertIn("wm:hasDerivedAttribute", documents[2]["content"])
        self.assertIsNone(load("knowledge").PRIVATE_TEXT.search("https://wealth.example.org/ontology/"))
        self.assertIsNotNone(load("knowledge").PRIVATE_TEXT.search("C:/private/data"))

    def test_profile_invalidation_tracks_structure_and_supplied_data_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ontology = root / "schema.ttl"
            data = root / "data.ttl"
            ontology.write_text('@prefix owl: <http://www.w3.org/2002/07/owl#> . <urn:Items> a owl:Class .')
            data.write_text('<urn:row:1> a <urn:Items> ; <urn:value> 3 .')
            loader = load("kg_metadata").load_kg_metadata
            first = loader(ontology, data, root / "cache")
            self.assertEqual(first, loader(ontology, data, root / "cache"))
            data.write_text(data.read_text() + '\n<urn:row:2> a <urn:Items> ; <urn:new> "x" .')
            second = loader(ontology, data, root / "cache")
            self.assertEqual(second["Items"]["instance_count"], 2)
            self.assertIn("new", second["Items"]["property_iris"])
