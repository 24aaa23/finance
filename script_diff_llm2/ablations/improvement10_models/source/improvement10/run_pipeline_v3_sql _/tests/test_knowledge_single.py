import ast
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from support import FakeClient, SOURCE, load
from test_knowledge_and_understanding import DOCS, SCHEMA, PACK

knowledge = load("knowledge")
single = load("knowledge_single")
progress = load("knowledge_progress")


class SingleCompilerTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"DOMAIN_COMPILATION_MODE": "improvement7"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.output = patch.object(progress.sys, "__stdout__", io.StringIO())
        self.output.start()
        self.addCleanup(self.output.stop)

    def test_prompt_and_payload_follow_improvement7_whole_document_contract(self):
        self.assertIn("including examples", single.COMPILATION_PROMPT)
        self.assertIn("Cite exact substrings", single.COMPILATION_PROMPT)
        docs = DOCS + [{"id": "domain", "content": "Keep signed values."}]
        pack = copy.deepcopy(PACK)
        pack["rules"].append({"id": "K2", "text": docs[1]["content"], "fields": [],
                              "citations": [{"source": "domain", "quote": docs[1]["content"]}]})
        pack["source_review"]["domain"] = "reviewed"
        pack["coverage"]["domain:0001"] = {"rule_ids": ["K2"]}
        client = FakeClient(pack)
        with tempfile.TemporaryDirectory() as folder:
            compiled, identity = knowledge.compile_knowledge(docs, SCHEMA, client, "offline", folder)
            cached, same = knowledge.compile_knowledge(docs, SCHEMA, None, "offline", folder)
            self.assertEqual((compiled, identity), (cached, same))
            self.assertEqual(compiled, pack)
            self.assertEqual(len(client.calls), 1)
            payload = json.loads(client.calls[0]["messages"][1]["content"])
            self.assertEqual(set(payload), {"schema", "documents", "sections", "validation_feedback"})
            self.assertEqual(payload["documents"], docs)
            self.assertEqual(len(payload["sections"]), 2)
            self.assertNotIn("ROW_SECRET", json.dumps(payload))
            self.assertNotIn("extraction_units", payload)

    def test_mode_change_does_not_reuse_whole_document_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            knowledge.compile_knowledge(DOCS, SCHEMA, FakeClient(PACK), "offline", folder)
            with patch.dict(os.environ, {"DOMAIN_COMPILATION_MODE": "chunked"}):
                with self.assertRaisesRegex(ValueError, "No knowledge cache"):
                    knowledge.compile_knowledge(DOCS, SCHEMA, None, "offline", folder)
            with patch.dict(os.environ, {"DOMAIN_COMPILATION_MODE": "typo"}):
                with self.assertRaisesRegex(ValueError, "must be simple, improvement7 or chunked"):
                    knowledge.compile_knowledge(DOCS, SCHEMA, FakeClient(PACK), "offline", folder)
