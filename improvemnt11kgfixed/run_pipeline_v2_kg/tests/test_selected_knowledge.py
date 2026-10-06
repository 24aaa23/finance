import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from support import FakeClient, load

knowledge = load("knowledge")
single = load("knowledge_single")
DOCS = [{"id": "rules", "content": "Keep signed values."}]
SCHEMA = {"Items": {"columns": [{"name": "amount"}]}}


class SelectedKnowledgeTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {"DOMAIN_COMPILATION_MODE": "simple", "KNOWLEDGE_CACHE_FILE": ""})
        environment.start()
        self.addCleanup(environment.stop)

    def save_cache(self, root):
        pack = single.normalize_simple_pack({"rules": [{"text": "Keep signed values.", "sources": ["rules"]}],
                                             "conflicts": []}, DOCS, SCHEMA)
        path = Path(root) / "selected.json"
        path.write_text(json.dumps({"identity": "older_compiler_identity", "pack_hash": knowledge.digest(pack),
                                    "pack": pack}), encoding="utf-8")
        os.environ["KNOWLEDGE_CACHE_FILE"] = str(path)
        return path, pack

    def test_explicit_selection_reuses_exact_rules_without_model_calls_or_rebuilding(self):
        with tempfile.TemporaryDirectory() as folder, patch("sys.stdout", io.StringIO()):
            path, original = self.save_cache(folder)
            before = path.read_bytes()
            client = FakeClient({})
            pack, identity = knowledge.compile_knowledge(DOCS, SCHEMA, client, "offline", Path(folder) / "unused")
            again, same = knowledge.compile_knowledge(DOCS, SCHEMA, None, "offline", Path(folder) / "unused")
            self.assertEqual(pack, original)
            self.assertEqual((again, same), (pack, identity))
            self.assertEqual(client.calls, [])
            self.assertEqual(path.read_bytes(), before)
            self.assertTrue(path.with_name(path.name + ".inputs.json").is_file())
            self.assertFalse((Path(folder) / "unused").exists())

    def test_changed_inputs_schema_model_and_cache_content_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder, patch("sys.stdout", io.StringIO()):
            path, _ = self.save_cache(folder)
            knowledge.compile_knowledge(DOCS, SCHEMA, None, "offline", folder)
            changed_docs = [{"id": "rules", "content": "Use different defaults."}]
            changed_schema = copy.deepcopy(SCHEMA)
            changed_schema["Items"]["columns"].append({"name": "other"})
            for docs, schema, model in [(changed_docs, SCHEMA, "offline"),
                                         (DOCS, changed_schema, "offline"), (DOCS, SCHEMA, "other-model")]:
                with self.assertRaisesRegex(ValueError, "inputs or model changed"):
                    knowledge.compile_knowledge(docs, schema, None, model, folder)
            saved = json.loads(path.read_text())
            saved["pack"]["rules"][0]["text"] = "Modified rule."
            path.write_text(json.dumps(saved))
            with self.assertRaisesRegex(ValueError, "Invalid selected knowledge cache hash"):
                knowledge.compile_knowledge(DOCS, SCHEMA, None, "offline", folder)

    def test_incompatible_metadata_does_not_silently_rewrite_selected_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            path, _ = self.save_cache(folder)
            saved = json.loads(path.read_text())
            saved["pack"]["rules"][0]["fields"] = [{"table": "Items", "column": "missing"}]
            saved["pack_hash"] = knowledge.digest(saved["pack"])
            path.write_text(json.dumps(saved))
            with self.assertRaisesRegex(ValueError, "incompatible"):
                knowledge.compile_knowledge(DOCS, SCHEMA, None, "offline", folder)
