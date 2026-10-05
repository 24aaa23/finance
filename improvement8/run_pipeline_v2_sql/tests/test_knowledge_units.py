import copy
import io
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
units_module = load("knowledge_units")
progress = load("knowledge_progress")
SCHEMA = {"Items": {"columns": [{"name": "amount"}]}}


class FragmentTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"DOMAIN_COMPILATION_MODE": "chunked"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.output = patch.object(progress.sys, "__stdout__", io.StringIO())
        self.output.start()
        self.addCleanup(self.output.stop)

    def response(self, units, selected):
        return {"rules": [{"id": "K1", "unit_ids": selected, "fields": []}] if selected else [],
                "conflicts": [], "excluded_units": {u["id"]: "Evaluation commentary omitted; policy retained."
                    for u in units if u["selectable"] and u["id"] not in selected}}

    def test_real_failed_paragraph_preserves_line_breaks_and_derives_partial_coverage(self):
        documents = knowledge.load_documents(SOURCE.parent / "domain_intro_latest.prompt",
                                            SOURCE.parent / "business_rules_addendum.md",
                                            SOURCE.parent / "table_medatada")
        source_chunk = next(c for c in chunks.make_chunks(documents, 6000)
                            if any(s["id"] == "rules:0013" for s in c["sections"]))
        section = next(s for s in source_chunk["sections"] if s["id"] == "rules:0013")
        text = section["text"]
        docs = [{"id": "rules", "content": text}]
        chunk = chunks.make_chunks(docs, 6000)[0]
        units = units_module.extraction_units(chunk)
        end = text.index("*(Resolves")
        selected = [u["id"] for u in units if u["end"] <= end]
        value = self.response(units, selected)
        pack = chunks.materialize_selections(value, chunk)
        knowledge.validate_pack(pack, docs, SCHEMA)
        self.assertEqual(pack["rules"][0]["text"], text[:end].rstrip())
        self.assertIn("category,\nsector_focus", pack["rules"][0]["text"])
        self.assertIn("a\nrow-pooled metric", pack["rules"][0]["text"])
        self.assertIn("exclude", pack["coverage"]["rules:0001"])
        self.assertIn("Retained source fragments in K1", pack["coverage"]["rules:0001"]["exclude"])
        self.assertNotIn("EC-4T-013", pack["rules"][0]["text"])

    def test_units_partition_all_real_sources_without_changing_or_losing_text(self):
        docs = knowledge.load_documents(SOURCE.parent / "domain_intro_latest.prompt",
                                        SOURCE.parent / "business_rules_addendum.md", SOURCE.parent / "table_medatada")
        for chunk in chunks.make_chunks(docs, 6000):
            sources = {d["id"]: d["content"] for d in chunk["documents"]}
            units = units_module.extraction_units(chunk)
            self.assertEqual(len(units), len({u["id"] for u in units}))
            for section in chunk["sections"]:
                observed = bytearray(len(section["text"]))
                for unit in (u for u in units if u["section_id"] == section["id"]):
                    self.assertEqual(unit["text"], sources[unit["source"]][unit["start"]:unit["end"]])
                    for pos in range(unit["start"] - section["start"], unit["end"] - section["start"]):
                        observed[pos] += 1
                    if unit["selectable"]:
                        self.assertIsNone(knowledge.BENCHMARK_ID.search(unit["text"]))
                self.assertTrue(all(observed[i] == 1 for i, ch in enumerate(section["text"]) if not ch.isspace()))

    def test_table_formula_keeps_inline_code_and_metric_name(self):
        text = "| Metric | SQA-3T-018 | `RS + (100 - LS) + (100 - DS)` | Keep. |"
        docs = [{"id": "rules", "content": text}]
        chunk = chunks.make_chunks(docs, 6000)[0]
        units = units_module.extraction_units(chunk)
        selected = [u["id"] for u in units if u["selectable"]]
        pack = units_module.materialize_units(self.response(units, selected), chunk)
        knowledge.validate_pack(pack, docs, SCHEMA)
        self.assertIn("Metric", pack["rules"][0]["text"])
        self.assertIn("`RS + (100 - LS) + (100 - DS)`", pack["rules"][0]["text"])
        self.assertNotIn("SQA-3T-018", pack["rules"][0]["text"])
        code_docs = [{"id": "rules", "content": "| Formula | `A | B` |"}]
        code_units = units_module.extraction_units(chunks.make_chunks(code_docs, 6000)[0])
        self.assertTrue(any("`A | B`" in u["text"] for u in code_units))

    def test_missing_excluded_unknown_and_forbidden_units_fail_closed(self):
        docs = [{"id": "rules", "content": "Use signed amounts. Historical EC-4T-013 result."}]
        chunk = chunks.make_chunks(docs, 6000)[0]
        units = units_module.extraction_units(chunk)
        value = self.response(units, [units[0]["id"]])
        missing = copy.deepcopy(value)
        del missing["excluded_units"][next(iter(missing["excluded_units"]))]
        with self.assertRaisesRegex(ValueError, "Missing:"):
            units_module.materialize_units(missing, chunk)
        for unit_id in [next(u["id"] for u in units if not u["selectable"]),
                        next(iter(value["excluded_units"])), "unknown-id"]:
            invalid = copy.deepcopy(value)
            invalid["rules"][0]["unit_ids"].append(unit_id)
            with self.assertRaises(ValueError):
                units_module.materialize_units(invalid, chunk)
        invalid = copy.deepcopy(value)
        invalid["excluded_units"]["unknown-id"] = "Omit"
        with self.assertRaisesRegex(ValueError, "Unknown excluded"):
            units_module.materialize_units(invalid, chunk)

    def test_new_request_contract_compiles_and_reuses_final_cache(self):
        docs = [{"id": "domain", "content": "Use signed amounts. Keep missing values."}]
        requests = []
        def create(**request):
            requests.append(request)
            payload = json.loads(request["messages"][1]["content"])
            units = payload["extraction_units"]
            value = self.response(units, [u["id"] for u in units])
            return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop",
                                   message=SimpleNamespace(content=json.dumps(value)))])
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with tempfile.TemporaryDirectory() as folder:
            pack, identity = knowledge.compile_knowledge(docs, SCHEMA, client, "offline", Path(folder) / "cache")
            cached, same = knowledge.compile_knowledge(docs, SCHEMA, None, "offline", Path(folder) / "cache")
            self.assertEqual((cached, same), (pack, identity))
            self.assertEqual(len(requests), 1)
            self.assertEqual(pack["rules"][0]["text"], docs[0]["content"])
            self.assertEqual(pack["coverage"], {"domain:0001": {"rule_ids": ["K1"]}})
