"""Business documentation must enrich SQL context without inventing schema."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import rdflib

from support import SOURCE, load


class SQLMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = SOURCE.parent / "wealth_management_diverse.db"
        cls.schema_file = SOURCE.parent / "kg_output_fixed/wealth_management_diverse_schema.ttl"
        cls.physical = load("sqlite_backend").load_sqlite_schema(cls.database)
        with contextlib.redirect_stdout(io.StringIO()):
            cls.enriched = load("sql_metadata").load_sqlite_metadata(cls.database, cls.schema_file)

    def test_all_physical_tables_and_columns_receive_documentation_without_schema_changes(self):
        self.assertEqual(set(self.enriched), set(self.physical))
        self.assertNotIn("ATOM_CONTEXT_ASSET_CLASS_001", self.enriched)
        for name, original in self.physical.items():
            with self.subTest(table=name):
                enriched = self.enriched[name]
                self.assertTrue(enriched["description"])
                self.assertTrue(enriched["documentation_source"])
                for key, value in original.items():
                    if key != "columns":
                        self.assertEqual(enriched[key], value)
                self.assertEqual(len(enriched["columns"]), len(original["columns"]))
                for before, after in zip(original["columns"], enriched["columns"]):
                    self.assertTrue(after["description"], before["name"])
                    for key, value in before.items():
                        self.assertEqual(after[key], value)

    def test_sql_annotations_match_source_documentation_used_by_kg(self):
        graph = rdflib.Graph().parse(str(self.schema_file), format="turtle")
        wm = rdflib.Namespace("https://wealth.example.org/ontology/")
        desc = rdflib.URIRef("http://purl.org/dc/terms/description")
        for table, details in self.enriched.items():
            source = next(graph.subjects(wm.primitiveId, rdflib.Literal(table)))
            self.assertEqual(details["description"], str(graph.value(source, desc) or ""))
            attrs = {str(graph.value(attr, wm.attributeName)): attr
                     for attr in graph.objects(source, wm.hasPrimitiveAttribute)}
            for column in details["columns"]:
                attr = attrs[column["source_column"]]
                self.assertEqual(column["description"], str(graph.value(attr, desc) or ""))
                self.assertEqual(column["synonyms"], sorted(map(str, graph.objects(attr, wm.synonym))))
                self.assertEqual(column["allowed_values"], sorted(map(str, graph.objects(attr, wm.allowedValue))))
            expected_metrics = [{"name": str(graph.value(attr, wm.derivedName) or graph.value(attr, rdflib.RDFS.label) or ""),
                                 "description": str(graph.value(attr, desc) or "")}
                                for attr in graph.objects(source, wm.hasDerivedAttribute)]
            self.assertEqual(details["derived_metrics"], expected_metrics)

    def test_missing_or_invalid_documentation_is_not_silently_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "schema.ttl"
            with self.assertRaises(FileNotFoundError):
                load("sql_metadata").load_sqlite_metadata(self.database, path)
            path.write_text("not valid turtle", encoding="utf-8")
            with self.assertRaises(rdflib.plugins.parsers.notation3.BadSyntax):
                load("sql_metadata").load_sqlite_metadata(self.database, path)


if __name__ == "__main__":
    unittest.main()
