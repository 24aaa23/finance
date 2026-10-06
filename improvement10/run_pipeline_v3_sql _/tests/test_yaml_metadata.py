"""YAML schema loading must not consult the database or infer constraints."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

from support import SOURCE, load

metadata = load("sql_metadata")


class YamlMetadataTests(unittest.TestCase):
    def write(self, folder, name, document):
        (Path(folder) / name).write_text(yaml.safe_dump(document), encoding="utf-8")

    def table(self):
        return {"identity": {"id": "Accounts"}, "attributes": [
            {"name": "id", "type": "string", "description": "Unique identifier"},
            {"name": "amount", "type": "decimal"}, {"name": "date", "type": "date"}]}

    def test_schema_uses_yaml_only_and_does_not_infer_constraints(self):
        with tempfile.TemporaryDirectory() as folder:
            doc = self.table()
            doc["derived_attributes"] = [{"name": "computed"}]
            doc["sample"] = "ROW_SECRET"
            self.write(folder, "accounts.yml", doc)
            with patch("sqlite3.connect", side_effect=AssertionError("Database access forbidden")):
                schema = metadata.load_yaml_metadata(folder)
                self.assertEqual(schema, metadata.load_sqlite_metadata("missing.db", folder))
            table = schema["Accounts"]
            self.assertEqual(table["primary_keys"], [])
            self.assertEqual(table["unique_keys"], [])
            self.assertEqual(table["foreign_keys"], [])
            self.assertNotIn("nullable", table["columns"][0])
            self.assertEqual(table["columns"][1]["datatype"], "numeric")
            self.assertEqual(table["columns"][2]["sqlite_type"], "TEXT")
            self.assertEqual(metadata.get_lightweight_table_index(schema),
                             {"Accounts": ["id", "amount", "date"]})
            self.assertNotIn("ROW_SECRET", str(schema))
            self.assertNotIn("ddl", table)
            with self.assertRaisesRegex(ValueError, "disabled"):
                metadata.load_sqlite_metadata("missing.db")

    def test_explicit_keys_and_context_tables(self):
        with tempfile.TemporaryDirectory() as folder:
            accounts = self.table()
            accounts["primary_keys"] = ["id"]
            accounts["unique_keys"] = [["id", "date"]]
            accounts["attributes"][0]["nullable"] = False
            self.write(folder, "accounts.yaml", accounts)
            context = {"identity": {"id": "Labels", "subtype": "Context"},
                       "attributes": [{"name": "account_id", "type": "string"}],
                       "foreign_keys": [{"columns": ["account_id"], "target_table": "Accounts",
                                         "target_columns": ["id"]}]}
            self.write(folder, "labels.yaml", context)
            self.assertNotIn("Labels", metadata.load_yaml_metadata(folder))
            context["schema"] = {"physical": True}
            self.write(folder, "labels.yaml", context)
            schema = metadata.load_yaml_metadata(folder)
            self.assertEqual(schema["Accounts"]["primary_keys"], ["id"])
            self.assertFalse(schema["Accounts"]["columns"][0]["nullable"])
            self.assertEqual(schema["Labels"]["foreign_keys"][0]["target_columns"], ["id"])
            context["foreign_keys"][0]["target_columns"] = ["unknown"]
            self.write(folder, "labels.yaml", context)
            with self.assertRaisesRegex(ValueError, "unknown column"):
                metadata.load_yaml_metadata(folder)

    def test_invalid_schema_is_rejected_without_database_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "No YAML"):
                metadata.load_yaml_metadata(folder)
            for change in ({"attributes": [{"name": "id"}]},
                           {"attributes": [{"name": "id", "type": "unknown"}]},
                           {"primary_keys": ["unknown"]},
                           {"schema": {"physical": "false"}}):
                with self.subTest(change=change):
                    self.write(folder, "accounts.yaml", {**self.table(), **change})
                    with self.assertRaisesRegex(ValueError, "accounts.yaml"):
                        metadata.load_yaml_metadata(folder)
            self.write(folder, "accounts.yaml", self.table())
            self.write(folder, "duplicate.yml", self.table())
            with self.assertRaisesRegex(ValueError, "Duplicate table"):
                metadata.load_yaml_metadata(folder)

    def test_supplied_folder_and_offline_cli_need_no_database(self):
        folder = SOURCE.parent / "table_medatada"
        with patch("sqlite3.connect", side_effect=AssertionError("Database access forbidden")):
            schema = metadata.load_yaml_metadata(folder)
        self.assertEqual(len(schema), 8)
        self.assertEqual(sum(len(t["columns"]) for t in schema.values()), 70)
        result = subprocess.run([sys.executable, "-B", str(SOURCE / "run.py"),
                                 "--check-inputs", "--yaml-dir", str(folder)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("8 tables", result.stdout)


if __name__ == "__main__":
    unittest.main()
