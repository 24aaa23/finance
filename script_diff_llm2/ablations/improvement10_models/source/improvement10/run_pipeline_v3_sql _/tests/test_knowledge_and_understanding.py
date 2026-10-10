import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from support import FakeClient, load

knowledge = load("knowledge")
understanding = load("query_understanding")
coverage = load("knowledge_coverage")
SCHEMA = {"Accounts": {"columns": [{"name": "id"}, {"name": "group"}, {"name": "amount"}],
                       "sample": "ROW_SECRET", "path": "PATH_SECRET", "column_stats": "STATS_SECRET"}}
DOCS = [{"id": "rules", "content": "Use SUM(amount) per account."}]
PACK = {"rules": [{"id": "K1", "text": DOCS[0]["content"], "citations": [
    {"source": "rules", "quote": DOCS[0]["content"]}], "fields": [{"table": "Accounts", "column": "amount"}]}],
    "conflicts": [], "source_review": {"rules": "reviewed"}, "coverage": {"rules:0001": {"rule_ids": ["K1"]}}}


def contract():
    return {"bindings": [{"phrase": "accounts", "table": "Accounts", "column": "id", "rule_ids": []}],
            "metrics": [], "filters": [], "group_by": [], "required_projection": ["id"],
            "order_by": [], "limit": None, "population": "accounts", "null_policy": "unspecified", "ambiguities": []}


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {"DOMAIN_COMPILATION_MODE": "improvement7"})
        environment.start()
        self.addCleanup(environment.stop)

    def test_retrieval_index_remains_physical_column_names_only(self):
        metadata = load("sql_metadata")
        self.assertEqual(metadata.get_lightweight_table_index(SCHEMA),
                         {"Accounts": ["id", "group", "amount"]})

    def test_cache_reuse_invalidation_and_payload_boundary(self):
        with tempfile.TemporaryDirectory() as folder:
            client = FakeClient(PACK)
            first, identity = knowledge.compile_knowledge(DOCS, SCHEMA, client, "offline", folder)
            second, same = knowledge.compile_knowledge(DOCS, SCHEMA, client, "offline", folder)
            self.assertEqual(first, second)
            self.assertEqual(identity, same)
            self.assertEqual(len(client.calls), 1)
            payload = json.dumps(client.calls)
            for marker in ("ROW_SECRET", "PATH_SECRET", "STATS_SECRET"):
                self.assertNotIn(marker, payload)
            _, changed = knowledge.compile_knowledge(DOCS, SCHEMA, client, "other-model", folder)
            self.assertNotEqual(identity, changed)
            self.assertEqual(len(client.calls), 2)

    def test_reject_rewritten_formula_and_unknown_field(self):
        bad = copy.deepcopy(PACK)
        bad["rules"][0]["text"] = "Use AVG(amount) per account."
        with self.assertRaisesRegex(ValueError, "exactly"):
            knowledge.validate_pack(bad, DOCS, SCHEMA)
        bad = copy.deepcopy(PACK)
        bad["rules"][0]["fields"][0]["column"] = "made_up"
        with self.assertRaisesRegex(ValueError, "Unknown schema"):
            knowledge.validate_pack(bad, DOCS, SCHEMA)

    def test_conflicts_missing_sources_and_unmatched_citations_rejected(self):
        for change in ({"conflicts": ["Unresolved formula"]}, {"source_review": {}}):
            with self.assertRaises(ValueError):
                knowledge.validate_pack({**PACK, **change}, DOCS, SCHEMA)
        bad = copy.deepcopy(PACK)
        bad["rules"][0]["text"] = "MC125-051 answer"
        with self.assertRaisesRegex(ValueError, "exactly"):
            knowledge.validate_pack(bad, DOCS, SCHEMA)

    def test_yaml_annotations_cannot_override_physical_keys(self):
        documents = [{"id": "yaml/a.yaml", "parsed": {"identity": {"id": "Accounts", "description": "Account owners"},
            "primary_keys": ["amount"], "attributes": [{"name": "group", "description": "Owner group"},
            {"name": "invented", "description": "not stored"}]}}]
        result = knowledge.annotate_schema(SCHEMA, documents)
        self.assertNotIn("primary_keys", result["Accounts"])
        self.assertEqual(len(result["Accounts"]["columns"]), 3)
        self.assertNotIn("description", SCHEMA["Accounts"])

    def test_one_formula_cannot_cover_a_whole_rule_or_missing_sources(self):
        bad = copy.deepcopy(PACK)
        bad["rules"][0]["text"] = "SUM(amount)"
        bad["rules"][0]["citations"][0]["quote"] = "SUM(amount)"
        with self.assertRaisesRegex(ValueError, "incomplete"):
            knowledge.validate_pack(bad, DOCS, SCHEMA)
        documents = DOCS + [{"id": "domain", "content": "Preserve nulls."}]
        bad = copy.deepcopy(PACK)
        bad["source_review"]["domain"] = "reviewed"
        with self.assertRaisesRegex(ValueError, "every source section"):
            knowledge.validate_pack(bad, documents, SCHEMA)

    def test_coverage_rejects_unknown_rules_and_unsupported_exclusions(self):
        for entry in ({"rule_ids": ["K999"]}, {"exclude": ""}, {"reviewed": True},
                      {"exclude": "irrelevant", "rule_ids": ["K1"]}):
            bad = copy.deepcopy(PACK)
            bad["coverage"]["rules:0001"] = entry
            with self.assertRaises(ValueError):
                knowledge.validate_pack(bad, DOCS, SCHEMA)

    def test_headers_and_table_rows_are_not_silently_dropped(self):
        content = "# Exclude null scores\n\nUse AVG(amount).\n\n| Rule | Meaning |\n| --- | --- |\n| A | Keep signed amounts |\n"
        sections = coverage.source_sections([{"id": "rules", "content": content}])
        self.assertEqual(len(sections), 4)
        self.assertTrue(any(s["text"] == "# Exclude null scores" for s in sections))
        for section in sections:
            self.assertEqual(section["text"], content[section["start"]:section["end"]])

    def test_exclusions_are_logged_without_blocking_fresh_or_cached_runs(self):
        documents = DOCS + [{"id": "notes", "content": "Document provenance note."}]
        pack = copy.deepcopy(PACK)
        pack["source_review"]["notes"] = "reviewed"
        pack["coverage"]["notes:0001"] = {"exclude": "Document provenance note, not a business rule."}
        with tempfile.TemporaryDirectory() as folder:
            client = FakeClient(pack)
            draft, identity = knowledge.compile_knowledge(documents, SCHEMA, client, "offline", folder)
            self.assertEqual(len(client.calls), 1)
            report = coverage.coverage_report(draft, documents, identity, knowledge.digest(draft))
            self.assertEqual(len(report["excluded_sections"]), 1)
            self.assertTrue((Path(folder) / (identity + ".coverage.json")).is_file())
            cached_pack, _ = knowledge.compile_knowledge(documents, SCHEMA, None, "offline", folder)
            self.assertEqual(cached_pack, draft)
            self.assertEqual(list(Path(folder).glob("*.approval.json")), [])
            self.assertEqual(json.loads((Path(folder) / (identity + ".coverage.json")).read_text()), report)
            # Removing approval must not remove cache-integrity checks.
            cache_path = Path(folder) / (identity + ".json")
            cached = json.loads(cache_path.read_text())
            cached["pack"]["coverage"]["notes:0001"]["exclude"] = "Changed omission justification"
            cache_path.write_text(json.dumps(cached), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Invalid knowledge cache identity"):
                knowledge.compile_knowledge(documents, SCHEMA, None, "offline", folder)

    def test_rejection_retries_with_missing_coverage_feedback(self):
        client = FakeClient({key: value for key, value in PACK.items() if key != "coverage"})
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "Domain compilation failed"):
                knowledge.compile_knowledge(DOCS, SCHEMA, client, "offline", folder)
            self.assertEqual(len(client.calls), 3)
            self.assertIn("coverage", json.loads(client.calls[1]["messages"][1]["content"])["validation_feedback"])
            self.assertEqual(list(Path(folder).glob("*.json")), [])


class UnderstandingTests(unittest.TestCase):
    def test_only_schema_and_knowledge_reach_new_agent(self):
        client = FakeClient(contract())
        result = understanding.understand_query("List accounts", SCHEMA, knowledge.prompt_pack(PACK), client, "offline")
        self.assertEqual(result, contract())
        self.assertEqual(len(client.calls), 1)
        payload = json.dumps(client.calls)
        for marker in ("ROW_SECRET", "PATH_SECRET", "STATS_SECRET"):
            self.assertNotIn(marker, payload)

    def test_ambiguity_retries_then_records_base_pipeline_fallback(self):
        value = contract()
        value["ambiguities"] = ["Owner is unclear"]
        client = FakeClient(value)
        diagnostics = {}
        result = understanding.understand_query("List accounts", SCHEMA, PACK, client, "offline", diagnostics=diagnostics)
        self.assertEqual(result, {})
        self.assertEqual(len(client.calls), 3)
        self.assertEqual(diagnostics["status"], "base_pipeline_fallback")
        self.assertEqual(diagnostics["attempts"], 3)
        self.assertEqual(len(diagnostics["validation_errors"]), 3)
        value = contract()
        value["bindings"][0]["phrase"] = "not in question"
        with self.assertRaises(ValueError):
            understanding.validate_interpretation(value, "List accounts", SCHEMA, PACK)

    def test_malformed_json_falls_back_but_transport_errors_propagate(self):
        client = FakeClient("not JSON")
        self.assertEqual(understanding.understand_query("List accounts", SCHEMA, PACK, client, "offline"), {})
        self.assertEqual(len(client.calls), 3)

        class UnavailableClient(FakeClient):
            def create(self, **kwargs):
                raise ConnectionError("Service unavailable")

        with self.assertRaises(ConnectionError):
            understanding.understand_query("List accounts", SCHEMA, PACK, UnavailableClient({}), "offline")

    def test_filter_evidence_repairs_case_and_spacing_without_dropping_conditions(self):
        value = contract()
        value["filters"] = [{"phrase": "HIGH_AMOUNT", "description": "amount > 10",
                             "operands": [{"table": "Accounts", "column": "amount"}], "stage": "final"}]
        client = FakeClient(value)
        result = understanding.understand_query("List accounts with high amount", SCHEMA, PACK, client, "offline")
        self.assertEqual(result["filters"][0]["phrase"], "high amount")
        self.assertEqual(result["filters"][0]["description"], "amount > 10")
        self.assertEqual(len(client.calls), 1)
        value["filters"][0]["phrase"] = "a different condition"
        with self.assertRaisesRegex(ValueError, "Filter evidence"):
            understanding.validate_interpretation(value, "List accounts with high amount", SCHEMA, PACK)

    def test_qualified_output_contract_gets_repair_feedback_before_final_planning(self):
        value = contract()
        value["required_projection"] = ["Accounts.id"]
        client = FakeClient(value)
        self.assertEqual(understanding.understand_query("List accounts", SCHEMA, PACK, client, "offline"), {})
        self.assertEqual(len(client.calls), 3)
        self.assertIn("unqualified", json.loads(client.calls[1]["messages"][1]["content"])["validation_feedback"])

    def test_resolved_model_caveats_are_repaired_before_validation(self):
        value = contract()
        value["bindings"].append({"phrase": "not exact evidence", "table": "Accounts", "column": "group", "rule_ids": ["R1"]})
        value["metrics"] = [{"output": "mean_amount", "definition": "Average amount", "operands": [
            {"table": "Accounts", "column": "amount"}, {"table": "Accounts", "column": None}],
            "inner_aggregation": "avg", "outer_aggregation": "none", "entity_keys": [
                {"table": "Accounts", "column": None}], "units": "unspecified", "rule_ids": ["R1"]}]
        value["ambiguities"] = [
            "The term is not explicitly defined; interpreted as amount > 10.",
            "Whether NULL values should be considered outside the allowed set.",
        ]
        result = understanding.understand_query("List accounts with amount > 10 outside the allowed set", SCHEMA, PACK, FakeClient(value), "offline")
        self.assertEqual(result["ambiguities"], [])
        self.assertEqual(result["bindings"], [contract()["bindings"][0]])
        self.assertEqual(result["metrics"][0]["operands"], [{"table": "Accounts", "column": "amount"}])
        self.assertEqual(result["metrics"][0]["entity_keys"], [])
        self.assertEqual(result["metrics"][0]["rule_ids"], [])

    def test_query_understanding_repairs_binding_phrases_and_retries(self):
        repaired_phrase = contract()
        repaired_phrase["bindings"] = [{"phrase": "avg_amount", "table": "Accounts", "column": "amount", "rule_ids": []}]
        result = understanding.understand_query("Show average amount for accounts", SCHEMA, PACK, FakeClient(repaired_phrase), "offline")
        self.assertEqual(result["bindings"][0]["phrase"], "amount")

        class SequenceClient(FakeClient):
            def __init__(self, values):
                super().__init__(values[0])
                self.values = list(values)

            def create(self, **kwargs):
                self.calls.append(kwargs)
                value = self.values[min(len(self.calls) - 1, len(self.values) - 1)]
                content = value if isinstance(value, str) else json.dumps(value)
                return type("Response", (), {"choices": [type("Choice", (), {
                    "message": type("Message", (), {"content": content})()
                })()]})()

        first = contract()
        first["ambiguities"] = ["Owner is unclear"]
        client = SequenceClient([first, contract()])
        self.assertEqual(understanding.understand_query("List accounts", SCHEMA, PACK, client, "offline"), contract())
        self.assertEqual(len(client.calls), 2)
        self.assertIn("Unresolved question meaning", json.loads(client.calls[1]["messages"][1]["content"])["validation_feedback"])

    def test_contract_survives_decomposition_and_checks_owners(self):
        decomposition = {"answer_requirements": {}, "subquestions": [], "contract_errors": []}
        understanding.apply_contract(decomposition, contract())
        self.assertIn("Accounts.id", decomposition["contract_errors"][0])
        self.assertEqual(decomposition["answer_requirements"]["query_understanding"], contract())
        decomposition["answer_requirements"]["query_understanding"]["bindings"].clear()
        self.assertTrue(contract()["bindings"])

    def test_output_and_ranking_checks(self):
        value = contract()
        value["limit"] = 10
        value["order_by"] = [{"column": "id", "direction": "ASC"}]
        self.assertTrue(understanding.final_contract_errors({"projection": [], "final_steps": []}, value))
        spec = {"projection": ["id"], "final_steps": [{"operator": "Order_By", "order_by": value["order_by"], "limit": 10}]}
        self.assertEqual(understanding.final_contract_errors(spec, value), [])

    def test_compiled_outer_aggregation_preserves_mean_not_sum(self):
        value = contract()
        value["required_projection"] = ["mean_amount"]
        value["metrics"] = [{"output": "mean_amount", "outer_aggregation": "avg"}]
        compiler = load("spec_runtime")
        for operation in ("avg", "sum"):
            spec = compiler.compile_spec({
                "final_steps": [{"operator": "Filter_Aggregate", "input": "Accounts",
                                 "aggregations": [{"operation": operation,
                                     "input_column": "amount", "output_column": "mean_amount"}]}],
                "projection": ["mean_amount"],
            }, {"Accounts": ["id", "amount"]})
            self.assertEqual(spec["contract_errors"], [])
            errors = understanding.final_contract_errors(spec, value)
            if operation == "avg":
                self.assertEqual(errors, [])
            else:
                self.assertTrue(any("outer aggregation avg" in error for error in errors))

    def test_grouping_checked_for_every_supported_aggregate_shape(self):
        value = contract()
        value.update(required_projection=["total"], group_by=[{"table": "Accounts", "column": "group"}])
        compiler = load("spec_runtime")
        for group in ("group", "region"):
            measure = {"operation": "sum", "input_column": "amount", "output_column": "total"}
            plans = [
                {"final_measures": [measure], "final_group_by": [group]},
                {"final_steps": [{"operator": "Filter_Aggregate", "group_by": [group], **measure}]},
                {"final_steps": [{"operator": "Filter_Aggregate", "group_by": [group], "aggregations": [measure]}]},
            ]
            for plan in plans:
                with self.subTest(group=group, plan=plan):
                    spec = compiler.compile_spec({**plan, "projection": ["total"]},
                                                 {"Accounts": ["group", "region", "amount"]})
                    self.assertEqual(spec["contract_errors"], [])
                    errors = understanding.final_contract_errors(spec, value)
                    self.assertEqual(bool(errors), group != "group", errors)

    def test_inner_entity_grain_does_not_replace_outer_group_grain(self):
        value = contract()
        value.update(required_projection=["mean_total"], group_by=[{"table": "Accounts", "column": "group"}])
        spec = load("spec_runtime").compile_spec({"pre_steps": [
            {"id": "entities", "operator": "Filter_Aggregate", "input": "Accounts", "group_by": ["id", "group"],
             "operation": "sum", "input_column": "amount", "output_column": "entity_total"}],
            "final_measures": [{"operation": "avg", "input_column": "entity_total", "output_column": "mean_total"}],
            "final_group_by": ["group"], "projection": ["mean_total"]}, {"Accounts": ["id", "group", "amount"]})
        self.assertEqual(spec["contract_errors"], [])
        self.assertEqual(understanding.final_contract_errors(spec, value), [])

    def test_trailing_tiebreak_allowed_but_requested_priorities_preserved(self):
        value = contract()
        value.update(order_by=[{"column": "amount", "direction": "DESC"}, {"column": "group", "direction": "ASC"}], limit=5)
        for order, valid in ((["amount desc", "group asc", "id asc"], True),
                             (["amount desc", "id asc", "group asc"], False),
                             (["amount asc", "group asc"], False),
                             (["amount desc"], False)):
            spec = load("spec_runtime").compile_spec({"final_steps": [{"operator": "Order_By", "order_by": order, "limit": "5"}],
                                                       "projection": ["id"]}, {"Accounts": ["id", "amount", "group"]})
            self.assertEqual(spec["contract_errors"], [])
            self.assertEqual(not understanding.final_contract_errors(spec, value), valid)


if __name__ == "__main__":
    unittest.main()
