import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from support import FakeClient, load
from test_knowledge_and_understanding import DOCS, SCHEMA

knowledge = load("knowledge")
single = load("knowledge_single")
progress = load("knowledge_progress")
coverage = load("knowledge_coverage")


class ReviewingClient(FakeClient):
    def __init__(self, value, review=None):
        super().__init__(value)
        self.review = review or {"additions": [], "replacements": [], "conflicts": []}

    def create(self, **request):
        if request["messages"][0]["content"].startswith("Review reusable business knowledge"):
            original = self.value
            self.value = self.review
            try:
                return super().create(**request)
            finally:
                self.value = original
        return super().create(**request)


class SimpleCompilerTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {"DOMAIN_COMPILATION_MODE": "simple"})
        environment.start()
        self.addCleanup(environment.stop)
        output = patch.object(progress.sys, "__stdout__", io.StringIO())
        output.start()
        self.addCleanup(output.stop)

    def test_no_coverage_or_exact_quotes_required_and_optional_metadata_is_advisory(self):
        text = "Aggregate signed amounts per account, using SUM(amount). See EC-4T-013."
        value = {"rules": [{"id": "custom", "text": text,
                            "fields": [{"table": "Accounts", "column": "invented"},
                                       {"table": "Accounts", "column": "amount"}],
                            "citations": [{"source": "rules", "quote": "Use SUM(amount) per account."},
                                          {"source": "domain", "quote": "Wrong quote without line breaks."}]}],
                 "conflicts": ["Two documents disagree about a default; question definitions take precedence."]}
        client = ReviewingClient(value)
        with tempfile.TemporaryDirectory() as folder:
            pack, identity = knowledge.compile_knowledge(DOCS, SCHEMA, client, "offline", folder)
            cached, same = knowledge.compile_knowledge(DOCS, SCHEMA, None, "offline", folder)
            self.assertEqual((cached, same), (pack, identity))
            self.assertEqual(len(client.calls), 2)
            self.assertEqual(pack["rules"][0]["text"], text)
            self.assertEqual(pack["rules"][0]["id"], "K1")
            self.assertEqual(pack["rules"][0]["fields"], [{"table": "Accounts", "column": "amount"}])
            self.assertEqual(len(pack["rules"][0]["citations"]), 1)
            self.assertEqual(len(pack["validation_notes"]), 2)
            self.assertEqual(pack["review_status"], "completed")
            self.assertEqual(knowledge.prompt_pack(pack)["conflicts"], value["conflicts"])
            payload = json.loads(client.calls[0]["messages"][1]["content"])
            self.assertEqual(set(payload), {"schema", "documents", "validation_feedback"})
            report = coverage.coverage_report(pack, DOCS, identity, knowledge.digest(pack))
            self.assertFalse(report["coverage_checked"])
            self.assertEqual(report["excluded_sections"], [])
            path = Path(folder) / (identity + ".json")
            damaged = json.loads(path.read_text())
            damaged["pack"]["rules"][0]["text"] = "Altered cache"
            path.write_text(json.dumps(damaged))
            with self.assertRaisesRegex(ValueError, "Invalid knowledge cache identity"):
                knowledge.compile_knowledge(DOCS, SCHEMA, None, "offline", folder)

    def test_minimal_rules_and_malformed_optional_metadata_preserve_text(self):
        for value in ({"rules": ["Use signed SUM(amount)."]},
                      {"rules": [{"text": "Use signed SUM(amount).", "fields": "optional", "citations": None}]}):
            pack = single.normalize_simple_pack(value, DOCS, SCHEMA)
            self.assertEqual(pack["rules"][0]["text"], "Use signed SUM(amount).")
            self.assertEqual(single.normalize_simple_pack(pack, DOCS, SCHEMA), pack)

    def test_empty_or_unusable_rules_still_fail(self):
        for value in ({}, {"rules": []}, {"rules": [None]}, {"rules": [{"text": " "}]}):
            with self.assertRaises(ValueError):
                single.normalize_simple_pack(value, DOCS, SCHEMA)

    def test_review_adds_missing_source_rule_and_corrects_mapping_without_losing_draft(self):
        docs = [{"id": "domain", "content": "Aggregate signed amounts. Keep owners with no records."},
                {"id": "rules", "content": "Displayed withdrawal magnitude is -SUM(amount)."}]
        draft = {"rules": [{"text": "Aggregate signed amounts.", "sources": ["domain"]},
                           {"text": "A date rule refers to a documented conceptual date, not a stored column."}]}
        review = {"additions": [{"text": "Displayed withdrawal magnitude is -SUM(amount).", "sources": ["rules"]},
                                {"text": "Keep owners with no records.", "sources": ["domain"]}],
                  "replacements": [{"id": "K2", "text": "The conceptual date requires an explicitly supported derivation; no date column exists in this YAML."}],
                  "conflicts": ["Date mapping needs clarification."]}
        client = ReviewingClient(draft, review)
        with tempfile.TemporaryDirectory() as folder:
            pack, identity = knowledge.compile_knowledge(docs, SCHEMA, client, "offline", folder)
            self.assertEqual(len(client.calls), 2)
            self.assertEqual(len(pack["rules"]), 4)
            self.assertEqual(pack["rules"][0]["text"], draft["rules"][0]["text"])
            self.assertEqual(pack["rules"][1]["text"], review["replacements"][0]["text"])
            self.assertEqual(pack["rules"][2]["sources"], ["rules"])
            payload = json.loads(client.calls[1]["messages"][1]["content"])
            self.assertEqual(payload["documents"], docs)
            self.assertEqual(len(payload["draft"]["rules"]), 2)
            cached, same = knowledge.compile_knowledge(docs, SCHEMA, None, "offline", folder)
            self.assertEqual((cached, same), (pack, identity))
            self.assertEqual(knowledge.prompt_pack(pack)["conflicts"], review["conflicts"])

    def test_invalid_review_preserves_draft_with_visible_status(self):
        client = FakeClient({"rules": [{"text": "Preserve signed amounts."}]})
        with tempfile.TemporaryDirectory() as folder:
            pack, _ = knowledge.compile_knowledge(DOCS, SCHEMA, client, "offline", folder)
            self.assertEqual(pack["rules"][0]["text"], "Preserve signed amounts.")
            self.assertEqual(pack["review_status"], "unavailable")
            self.assertTrue(any("review unavailable" in note for note in pack["validation_notes"]))
            self.assertEqual(len(client.calls), 4)  # Draft plus three malformed-review attempts.

    def test_unknown_review_ids_and_source_ids_are_advisory_and_cannot_erase_rules(self):
        draft = single.normalize_simple_pack({"rules": [{"text": "Preserve signed amounts."}]}, DOCS, SCHEMA)
        value = {"additions": [{"text": "Additional documented rule.", "sources": ["rules", "unknown"]}],
                 "replacements": [{"id": "K999", "text": "Wrong replacement."}], "conflicts": []}
        pack = single.apply_simple_review(value, draft, DOCS, SCHEMA)
        self.assertEqual(pack["rules"][0]["text"], draft["rules"][0]["text"])
        self.assertEqual(pack["rules"][1]["sources"], ["rules"])
        self.assertTrue(any("unknown or duplicate rule ID" in note for note in pack["validation_notes"]))
        self.assertTrue(any("unknown optional source reference" in note for note in pack["validation_notes"]))
