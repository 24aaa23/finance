"""V3 source-context behavior with RDF execution boundaries."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from support import FakeClient, load


class V3KgContextTests(unittest.TestCase):
    def test_supplied_sources_are_exact_and_compiler_does_not_filter_their_content(self):
        knowledge = load("knowledge")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            contents = ["Original domain notes; 50 records. See EC-4T-013.",
                        "Original business formula: A - B. Example answer: 42.",
                        '@prefix owl: <http://www.w3.org/2002/07/owl#> . <urn:Items> a owl:Class .']
            paths = [root / name for name in ("domain.prompt", "rules.md", "ontology.ttl")]
            for path, content in zip(paths, contents):
                path.write_text(content, encoding="utf-8")
            documents = knowledge.load_documents(*paths)
            self.assertEqual([doc["content"] for doc in documents], contents)
            client = FakeClient({"rules": [{"text": contents[0], "sources": ["domain"]}]})
            with patch.dict(os.environ, {"DOMAIN_COMPILATION_MODE": "simple", "KNOWLEDGE_CACHE_FILE": ""}):
                pack, _ = knowledge.compile_knowledge(documents, {}, client, "offline", root / "cache")
            self.assertEqual(json.loads(client.calls[0]["messages"][1]["content"])["documents"], documents)
            self.assertEqual(pack["rules"][0]["text"], contents[0])

    def test_full_relevant_ontology_reaches_final_planner_without_live_values(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            ontology = root / "ontology.ttl"
            data = root / "data.ttl"
            ontology.write_text('''@prefix wm: <https://wealth.example.org/ontology/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix dct: <http://purl.org/dc/terms/> .
<urn:Items> a owl:Class .
<urn:primitive> a wm:Primitive ; wm:primitiveId "ItemsSource" ;
 wm:hasDerivedAttribute <urn:metric> ; wm:example "DOCUMENTED_EXAMPLE" .
<urn:metric> wm:derivedName "net" ; dct:description "A minus B" ;
 wm:formula "A - B" .''', encoding="utf-8")
            data.write_text('''@prefix wm: <https://wealth.example.org/ontology/> .
<urn:live:1> a <urn:Items> ; wm:sourceTable "ItemsSource" ;
 <urn:value> "PRIVATE_LIVE_VALUE" .''', encoding="utf-8")
            raw = load("kg_metadata").load_kg_metadata(ontology, data)
            self.assertEqual(raw["Items"]["derived_metrics"][0]["name"], "net")
            client = FakeClient({"final_steps": [], "projection": ["value"]})
            load("llm_operators.final_spec").semantic_build_final_spec({"query": "List values",
                "global_schema": raw, "processed_datasets": [{"id": "a", "fields": ["subject_iri", "value"],
                    "sample": [{"value": "PRIVATE_LIVE_VALUE"}], "row_count": 1,
                    "retrieval_specs": [{"class": "Items", "fields": ["subject_iri", "value"]}]}]}, client)
            prompt = json.dumps(client.calls)
            for definition in ("DOCUMENTED_EXAMPLE", "A - B", "urn:value", "ontology_metadata"):
                self.assertIn(definition, prompt)
            for private in ("PRIVATE_LIVE_VALUE", "urn:live:1", "instance_count", "row_count"):
                self.assertNotIn(private, prompt)

    def test_domain_consultation_uses_full_sources_and_never_instance_observations(self):
        docs = [{"id": "domain", "content": "Original notes include EC-4T-013."},
                {"id": "rules", "content": "Use A - B."}, {"id": "ontology", "content": "Original ontology."}]
        rule = {"id": "K1", "text": docs[0]["content"], "fields": [],
                "citations": [{"source": "domain", "quote": docs[0]["content"]}]}
        client = FakeClient({"rules": [rule], "conflicts": [],
                             "source_review": {doc["id"]: "reviewed" for doc in docs}})
        load("consultation").consult_domain("List items", "metric_definition", docs,
            {"Items": {"columns": [{"name": "value", "predicate_iri": "urn:value"}],
                       "sample_rows": ["PRIVATE_LIVE_VALUE"], "instance_count": 99}}, client, "offline")
        prompt = json.dumps(client.calls)
        self.assertIn("EC-4T-013", prompt)
        self.assertNotIn("PRIVATE_LIVE_VALUE", prompt)
        self.assertNotIn("instance_count", prompt)
