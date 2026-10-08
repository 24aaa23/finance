import copy
import io
import itertools
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from support import SOURCE, load

knowledge = load("knowledge")
chunks = load("knowledge_chunks")
coverage = load("knowledge_coverage")
progress = load("knowledge_progress")
SCHEMA = {"Items": {"columns": [{"name": "amount"}]}}
DOCS = [{"id": "domain", "content": "# Totals\n\n" + "Keep signed amounts. " * 12 + "\n\n" + "Include all owners. " * 12},
        {"id": "rules", "content": "Preserve missing values. " * 12}]


class CompilerClient:
    def __init__(self, fail_source=None, conflict=False):
        self.calls = []
        self.fail_source = fail_source
        self.conflict = conflict
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **request):
        self.calls.append(request)
        payload = json.loads(request["messages"][1]["content"])
        if "documents" in payload:
            rules = [{"id": f"K{i}", "text": doc["content"], "fields": [],
                      "citations": [{"source": doc["id"], "quote": doc["content"]}]}
                     for i, doc in enumerate(payload["documents"], 1)]
            by_source = {r["citations"][0]["source"]: r["id"] for r in rules}
            value = {"rules": rules, "conflicts": [],
                     "source_review": {d["id"]: "reviewed" for d in payload["documents"]},
                     "coverage": {s["id"]: {"rule_ids": [by_source[s["source"]]]} for s in payload["sections"]}}
            if any(d["id"] == self.fail_source for d in payload["documents"]):
                value["coverage"] = {}
        else:
            value = {"reviewed_rule_ids": [r["id"] for r in payload["rules"]],
                     "superseded": [], "conflicts": ["Contradictory definitions"] if self.conflict else []}
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop",
                               message=SimpleNamespace(content=json.dumps(value)))])


class ChunkTests(unittest.TestCase):
    def test_supplied_business_rule_section_may_be_selected_with_reference_notes(self):
        documents = knowledge.load_documents(SOURCE.parent / "domain_intro_latest.prompt",
                                            SOURCE.parent / "business_rules_addendum.md",
                                            SOURCE.parent / "table_medatada")
        chunk = next(c for c in chunks.make_chunks(documents, 6000)
                     if any("EC-4T-013" in s["text"] for s in c["sections"]))
        section = next(s for s in chunk["sections"] if "EC-4T-013" in s["text"])
        self.assertEqual(chunks.excerpt_only_sections(chunk), [])
        selection = {"rules": [{"id": "K1", "section_ids": [section["id"]], "excerpts": [], "fields": []}],
                     "conflicts": [], "coverage": {s["id"]: {"exclude": "Other sections outside this test"}
                                                     for s in chunk["sections"]}}
        pack = chunks.materialize_selections(selection, chunk)
        self.assertEqual(pack["rules"][0]["text"], section["text"])
        self.assertIn("EC-4T-013", pack["rules"][0]["text"])
        selection["rules"][0].update(section_ids=[], excerpts=[{"section_id": section["id"], "quote": section["text"]}])
        self.assertEqual(chunks.materialize_selections(selection, chunk)["rules"][0]["text"], section["text"])

    def test_supplied_source_notes_remain_available_in_chunked_compilation(self):
        docs = [{"id": "rules", "content": "Use signed amounts. Benchmark EC-4T-013 was corrected."}]
        class SourceClient(CompilerClient):
            def create(self, **request):
                self.calls.append(request)
                payload = json.loads(request["messages"][1]["content"])
                self_test.assertEqual(payload["documents"], docs)
                self_test.assertEqual(payload["excerpt_only_sections"], [])
                value = {"rules": [{"id": "K1", "fields": [], "section_ids": ["rules:0001"], "excerpts": []}],
                         "conflicts": [], "coverage": {"rules:0001": {"rule_ids": ["K1"]}}}
                return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=json.dumps(value)))])
        self_test = self
        with tempfile.TemporaryDirectory() as folder:
            client = SourceClient()
            pack, _ = knowledge.compile_knowledge(docs, SCHEMA, client, "offline", Path(folder) / "cache")
            self.assertEqual(len(client.calls), 1)
            self.assertEqual(pack["rules"][0]["text"], docs[0]["content"])

    def test_section_selection_copies_source_unicode_and_punctuation_exactly(self):
        docs = [{"id": "domain", "content": '# Keep \u2022 signs\n\nUse \u201cnet\u201d values\u2014preserve signs.\nNext line.'}]
        chunk = chunks.make_chunks(docs, 6000)[0]
        selection = {"rules": [{"id": "K1", "section_ids": [s["id"] for s in chunk["sections"]],
                                 "excerpts": [], "fields": []}], "conflicts": [],
                     "coverage": {s["id"]: {"rule_ids": ["K1"]} for s in chunk["sections"]}}
        pack = chunks.materialize_selections(selection, chunk)
        knowledge.validate_pack(pack, docs, SCHEMA)
        self.assertEqual(pack["rules"][0]["text"], "\n".join(s["text"] for s in chunk["sections"]))
        self.assertTrue(all(c["source"] == "domain" for c in pack["rules"][0]["citations"]))
        selection["rules"][0]["section_ids"] = ["rules:0001"]
        with self.assertRaisesRegex(ValueError, "Unknown target"):
            chunks.materialize_selections(selection, chunk)

    def test_excerpt_does_not_claim_full_coverage_or_allow_modified_quote(self):
        docs = [{"id": "domain", "content": '# Use net returns. Historical test commentary.'}]
        chunk = chunks.make_chunks(docs, 6000)[0]
        selection = {"rules": [{"id": "K1", "section_ids": [], "fields": [],
                                  "excerpts": [{"section_id": "domain:0001", "quote": "Use net returns."}]}],
                     "conflicts": [], "coverage": {"domain:0001": {"rule_ids": ["K1"]}}}
        with self.assertRaisesRegex(ValueError, "incomplete"):
            knowledge.validate_pack(chunks.materialize_selections(selection, chunk), docs, SCHEMA)
        selection["coverage"]["domain:0001"] = {"exclude": "Mixed historical commentary; reusable policy extracted."}
        knowledge.validate_pack(chunks.materialize_selections(selection, chunk), docs, SCHEMA)
        selection["rules"][0]["excerpts"][0]["quote"] = "Use gross returns."
        with self.assertRaisesRegex(ValueError, "exactly match"):
            chunks.materialize_selections(selection, chunk)

    def test_selection_response_compiles_and_resumes_as_normal_cache(self):
        class SelectingClient(CompilerClient):
            def create(self, **request):
                self.calls.append(request)
                payload = json.loads(request["messages"][1]["content"])
                sections = payload["sections"]
                value = {"rules": [{"id": f"K{i}", "section_ids": [s["id"]], "excerpts": [], "fields": []}
                                   for i, s in enumerate(sections, 1)], "conflicts": [],
                         "coverage": {s["id"]: {"rule_ids": [f"K{i}"]} for i, s in enumerate(sections, 1)}}
                return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=json.dumps(value)))])
        docs = [{"id": "domain", "content": "Preserve signed values."}]
        with tempfile.TemporaryDirectory() as folder:
            client = SelectingClient()
            pack, identity = knowledge.compile_knowledge(docs, SCHEMA, client, "offline", Path(folder) / "cache")
            cached, same = knowledge.compile_knowledge(docs, SCHEMA, None, "offline", Path(folder) / "cache")
            self.assertEqual((cached, same), (pack, identity))
            self.assertEqual(len(client.calls), 1)
            self.assertEqual(pack["rules"][0]["citations"], [{"source": "domain", "quote": docs[0]["content"]}])

    def setUp(self):
        self.environment = patch.dict(os.environ, {"DOMAIN_COMPILATION_MODE": "chunked",
                                                  "DOMAIN_CHUNK_CHARS": "300", "DOMAIN_REVIEW_CHARS": "100000"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.output = patch.object(progress.sys, "__stdout__", io.StringIO())
        self.output.start()
        self.addCleanup(self.output.stop)

    def test_real_inputs_keep_all_sections_once_and_yaml_whole(self):
        root = SOURCE.parent
        documents = knowledge.load_documents(root / "domain_intro_latest.prompt", SOURCE / "knowledge_inputs/business_rules_addendum.md",
                                             root / "table_medatada")
        parts = chunks.make_chunks(documents, 6000)
        original = {s["id"]: s for s in coverage.source_sections(documents)}
        observed = []
        for part in parts:
            docs = {d["id"]: d["content"] for d in part["documents"]}
            for section in part["sections"]:
                observed.append(section["id"])
                self.assertEqual(section["text"], original[section["id"]]["text"])
                self.assertEqual(section["text"], docs[section["source"]][section["start"]:section["end"]])
        self.assertEqual(len(observed), len(set(observed)))
        self.assertEqual(set(observed), set(original))
        for doc in documents:
            if doc["id"].startswith("yaml/"):
                self.assertEqual(sum(any(d["id"] == doc["id"] for d in p["documents"]) for p in parts), 1)

    def test_table_and_formula_paragraph_are_atomic(self):
        formula = "Rate = SUM(amount) / COUNT(*)\nWhere amount preserves its sign."
        table = "| Policy | Meaning |\n|---|---|\n| X | Keep all owners |\n| Y | Keep nulls |"
        docs = [{"id": "domain", "content": "# Formula\n\n" + formula + "\n\n" + table + "\n\nEnd."}]
        parts = chunks.make_chunks(docs, 50)
        self.assertTrue(any(formula in p["documents"][0]["content"] for p in parts))
        self.assertTrue(any(table in p["documents"][0]["content"] for p in parts))
        with self.assertRaisesRegex(ValueError, "too large"):
            chunks.make_chunks([{"id": "domain", "content": "x" * 13000}], 50)

    def test_resume_reuses_valid_chunks_then_review_and_final_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "cache"
            first = CompilerClient(fail_source="rules")
            with self.assertRaisesRegex(ValueError, "Domain compilation failed"):
                knowledge.compile_knowledge(DOCS, SCHEMA, first, "offline", root)
            self.assertEqual(list(root.glob("*.json")), [])
            self.assertEqual(len(list((root / "parts").rglob("chunk_*.json"))), 2)
            resumed = CompilerClient()
            pack, identity = knowledge.compile_knowledge(DOCS, SCHEMA, resumed, "offline", root)
            self.assertEqual(len(resumed.calls), 2)  # Last chunk, then global review.
            self.assertEqual(json.loads(resumed.calls[0]["messages"][1]["content"])["documents"][0]["id"], "rules")
            knowledge.validate_pack(pack, DOCS, SCHEMA)
            cached, same = knowledge.compile_knowledge(DOCS, SCHEMA, None, "offline", root)
            self.assertEqual(cached, pack)
            self.assertEqual(same, identity)
            changed = copy.deepcopy(DOCS)
            changed[0]["content"] += " Updated definition."
            with self.assertRaisesRegex(ValueError, "No knowledge cache"):
                knowledge.compile_knowledge(changed, SCHEMA, None, "offline", root)

    def test_checkpoint_corruption_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "cache"
            with self.assertRaises(ValueError):
                knowledge.compile_knowledge(DOCS, SCHEMA, CompilerClient(fail_source="rules"), "offline", root)
            part = next((root / "parts").rglob("chunk_*.json"))
            value = json.loads(part.read_text())
            value["value"]["rules"][0]["text"] = "tampered"
            part.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "Invalid knowledge checkpoint"):
                knowledge.compile_knowledge(DOCS, SCHEMA, CompilerClient(), "offline", root)

    def test_global_conflict_blocks_final_cache_but_retains_chunks(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "cache"
            with self.assertRaisesRegex(ValueError, "cross-document conflicts"):
                knowledge.compile_knowledge(DOCS, SCHEMA, CompilerClient(conflict=True), "offline", root)
            self.assertEqual(list(root.glob("*.json")), [])
            self.assertEqual(len(list((root / "parts").rglob("chunk_*.json"))), 3)
            resumed = CompilerClient()
            knowledge.compile_knowledge(DOCS, SCHEMA, resumed, "offline", root)
            self.assertEqual(len(resumed.calls), 1)  # Only review is repeated.

    def test_large_review_covers_every_rule_pair(self):
        rules = [{"id": f"K{i}", "text": "policy " * 30, "fields": [],
                  "citations": [{"source": "domain", "quote": "policy"}]} for i in range(8)]
        jobs = chunks.review_jobs(rules, 1400)
        pairs = set()
        for job in jobs:
            self.assertLessEqual(len(json.dumps(job, ensure_ascii=True)), 1400)
            pairs.update(tuple(sorted(p)) for p in itertools.combinations([r["id"] for r in job], 2))
        self.assertEqual(pairs, {tuple(sorted(p)) for p in itertools.combinations([r["id"] for r in rules], 2)})

    def test_addendum_supersession_is_validated_and_audited(self):
        docs = [{"id": "domain", "content": "Use gross returns."}, {"id": "rules", "content": "Correction: use net returns instead of gross returns."}]
        packs = []
        for doc in docs:
            packs.append({"rules": [{"id": "K1", "text": doc["content"], "fields": [],
                                      "citations": [{"source": doc["id"], "quote": doc["content"]}]}],
                          "conflicts": [], "source_review": {doc["id"]: "reviewed"},
                          "coverage": {doc["id"] + ":0001": {"rule_ids": ["K1"]}}})
        pack = chunks.merge_packs(packs, docs)
        job = chunks.review_jobs(pack["rules"], 10000)[0]
        decision = {"reviewed_rule_ids": ["K1", "K2"], "conflicts": [],
                    "superseded": [{"rule_id": "K1", "by_rule_id": "K2", "reason": "Explicit correction to return definition."}]}
        chunks.validate_review(decision, job)
        final = chunks.apply_reviews(pack, [decision])
        knowledge.validate_pack(final, docs, SCHEMA)
        self.assertEqual([r["id"] for r in final["rules"]], ["K2"])
        self.assertIn("K1 replaced by K2", final["coverage"]["domain:0001"]["exclude"])
        bad = copy.deepcopy(decision)
        bad["superseded"][0].update(rule_id="K2", by_rule_id="K1")
        with self.assertRaisesRegex(ValueError, "addendum"):
            chunks.validate_review(bad, job)
        bad = {**decision, "reviewed_rule_ids": ["K1"]}
        with self.assertRaisesRegex(ValueError, "every supplied"):
            chunks.validate_review(bad, job)

    def test_empty_nonrule_chunk_allowed_but_empty_final_pack_rejected(self):
        docs = [{"id": "notes", "content": "Historical commentary."}]
        empty = {"rules": [], "conflicts": [], "source_review": {"notes": "reviewed"},
                 "coverage": {"notes:0001": {"exclude": "Non-rule historical commentary."}}}
        knowledge.validate_pack(empty, docs, SCHEMA, allow_empty=True)
        with self.assertRaisesRegex(ValueError, "no rules"):
            knowledge.validate_pack(empty, docs, SCHEMA)
        empty["coverage"] = {}
        with self.assertRaisesRegex(ValueError, "every source section"):
            knowledge.validate_pack(empty, docs, SCHEMA, allow_empty=True)
