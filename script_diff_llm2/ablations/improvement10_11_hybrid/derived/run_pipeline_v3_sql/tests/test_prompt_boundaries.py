"""Capture model requests and ensure database observations remain local."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from support import FakeClient, SOURCE, load


def annotated_schema():
    return {"Accounts": {"description": "Account owners", "primary_keys": ["id"],
        "columns": [{"name": "id", "sqlite_type": "TEXT", "description": "Account identifier",
                     "sample_values": ["COLUMN_VALUE_SECRET"]},
                    {"name": "amount", "sqlite_type": "REAL"}],
        "sample": [{"id": "ROW_VALUE_SECRET"}], "row_count": "COUNT_SECRET",
        "column_stats": "STATS_SECRET", "path": "DATABASE_PATH_SECRET",
        "ground_truth": "GROUND_TRUTH_SECRET"}}


class PromptBoundaryTests(unittest.TestCase):
    def assert_safe(self, calls):
        payload = json.dumps(calls)
        for marker in ("ROW_VALUE_SECRET", "COUNT_SECRET",
                       "STATS_SECRET", "DATABASE_PATH_SECRET", "GROUND_TRUTH_SECRET"):
            self.assertNotIn(marker, payload)

    def test_final_spec_receives_yaml_definitions_and_contracts_without_observations(self):
        branch = {"id": "source", "branch_id": "q1", "question": "Read account amounts",
                  "fields": ["id", "amount"], "sample": [{"id": "ROW_VALUE_SECRET"}],
                  "row_count": "COUNT_SECRET", "column_stats": "STATS_SECRET",
                  "retrieval_specs": [{"class": "Accounts", "fields": ["id", "amount"],
                    "filters": [{"field": "amount", "operator": ">", "value": 10}]}]}
        client = FakeClient({"final_steps": [], "projection": ["id", "amount"]})
        result = load("llm_operators.final_spec").semantic_build_final_spec(
            {"query": "List accounts with amount above 10", "processed_datasets": [branch],
             "global_schema": annotated_schema(), "data": [{"id": "ROW_VALUE_SECRET"}]}, client)
        self.assertFalse(result["final_spec"]["contract_errors"])
        self.assert_safe(client.calls)
        prompt = json.dumps(client.calls)
        for definition in ("Account owners", "Account identifier", "REAL", "primary_keys", "filters"):
            self.assertIn(definition, prompt)
        self.assertIn("COLUMN_VALUE_SECRET", prompt)
        for key in ('"sample"', '"row_count"', '"column_stats"'):
            self.assertNotIn(key, client.calls[0]["messages"][0]["content"])

    def test_decompose_and_query_spec_strip_unapproved_schema_metadata(self):
        request = {"consultation_request": {"agent": "domain", "topic": "metric_definition"}}
        for module, function in (("decompose", "semantic_decompose_question"),
                                 ("query_spec", "semantic_build_query_spec")):
            with self.subTest(operator=module):
                client = FakeClient(request)
                result = getattr(load("llm_operators." + module), function)(
                    {"query": "List accounts", "global_schema": annotated_schema(),
                     "schema_details": annotated_schema(), "retrieved_tables": ["Accounts"],
                     "agent_consultation_enabled": True, "agent_consultation_available": True}, client)
                self.assertEqual(result, request)
                self.assert_safe(client.calls)
                self.assertIn("Account identifier", json.dumps(client.calls))

    def test_generate_fallback_and_refine_do_not_receive_database_observations(self):
        for module, function in (("generate", "semantic_generate_sparql"), ("refine", "semantic_refine")):
            with self.subTest(operator=module):
                client = FakeClient('SELECT "id" FROM "Accounts"')
                operator = load("llm_operators." + module)
                inputs = {"query": "List accounts", "global_schema": annotated_schema(),
                          "retrieval_spec": {"class": "Accounts", "fields": ["id"]},
                          "failed_sparql": 'SELECT "id" FROM "Accounts"', "error_message": "syntax error"}
                if module == "generate":
                    with patch.object(operator, "render_raw_sql", return_value=None):
                        getattr(operator, function)(inputs, client, "offline")
                else:
                    getattr(operator, function)(inputs, client, "offline")
                self.assertEqual(len(client.calls), 1)
                self.assert_safe(client.calls)

    def test_supplied_yaml_is_preserved_exactly_with_examples_and_annotations(self):
        knowledge = load("knowledge")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "domain.prompt").write_text("Accounts identify owners.", encoding="utf-8")
            (root / "rules.md").write_text("Preserve signed amounts.", encoding="utf-8")
            (root / "accounts.yaml").write_text(
                "identity:\n  id: Accounts\n  description: Account owners\n"
                "sample_rows:\n  - id: ROW_VALUE_SECRET\n"
                "attributes:\n  - name: id\n    type: string\n"
                "    sample_values: [COLUMN_VALUE_SECRET]\n"
                "    description: Account identifier\n", encoding="utf-8")
            with patch("sqlite3.connect", side_effect=AssertionError("No database access permitted")):
                documents = knowledge.load_documents(root / "domain.prompt", root / "rules.md", root)
                schema = load("sql_metadata").load_yaml_metadata(root)
            yaml_doc = next(doc for doc in documents if doc["id"] == "yaml/accounts.yaml")
            self.assertEqual(yaml_doc["content"], (root / "accounts.yaml").read_text(encoding="utf-8"))
            self.assertIn("ROW_VALUE_SECRET", json.dumps(documents))
            self.assertIn("COLUMN_VALUE_SECRET", json.dumps(documents))
            self.assertIn("Account identifier", json.dumps(documents))
            knowledge.validate_documents(documents)
            annotated = knowledge.annotate_schema(schema, documents)
            self.assertEqual(annotated["Accounts"]["yaml_metadata"], yaml_doc["parsed"])
            self.assertEqual(annotated["Accounts"]["columns"][0]["sample_values"], ["COLUMN_VALUE_SECRET"])
            profiles, _ = load("llm_operators.final_spec")._branch_context(
                [{"id": "source", "fields": ["id"], "retrieval_specs": [{"class": "Accounts"}]}], annotated)
            self.assertIn("ROW_VALUE_SECRET", json.dumps(profiles[0]["yaml_metadata"]))

    def test_legacy_calculation_paths_never_send_rows_or_observed_metadata(self):
        client = FakeClient({})
        result = load("llm_operators.integrate").semantic_integrate(
            {"query": "Combine records", "branch_1_output": {"id": "ROW_VALUE_SECRET"},
             "branch_2_output": {"value": "COLUMN_VALUE_SECRET"}}, client)
        self.assertTrue(result["error"])
        self.assertEqual(client.calls, [])
        for module, function in (("filter_aggregate", "semantic_filter_aggregate"),
                                 ("order_by", "semantic_order_by")):
            client = FakeClient({})
            getattr(load("llm_operators." + module), function)(
                {"query": "List accounts", "schema_details": annotated_schema()}, client)
            self.assertEqual(len(client.calls), 1)
            self.assert_safe(client.calls)

    def test_review_and_formatting_do_not_call_models_even_with_legacy_opt_ins(self):
        client = FakeClient({"is_valid": True})
        data = [{"id": "ROW_VALUE_SECRET", "amount": 42, "missing": None}]
        with patch.dict(os.environ, {"FINAL_SEMANTIC_REVIEW": "1", "DETERMINISTIC_EXPLAIN": "0"}):
            result = load("llm_operators.validate").semantic_validate(
                {"query": "List accounts", "data": data, "semantic_review": True}, client)
            answer = load("llm_operators.explain").semantic_explain_results(
                {"query": "List accounts", "data": data}, client)
        self.assertEqual(result["validation"]["status"], "not_requested")
        self.assertEqual(json.loads(answer["final_answer"]), data)
        self.assertEqual(client.calls, [])

    def test_supplied_rule_content_is_not_filtered_from_compiler_requests_or_rule_packs(self):
        knowledge, single = load("knowledge"), load("knowledge_single")
        for text in ("See EC-4T-013.", "The table has 50 rows.", "77 of 1550 investors lack scores.",
                     "Expected answer: 42", "Historical evaluation commentary."):
            with self.subTest(text=text):
                docs = [{"id": "rules", "content": text}]
                knowledge.validate_documents(docs)
                pack = single.normalize_simple_pack({"rules": [{"text": text, "sources": ["rules"]}]}, docs, {})
                self.assertEqual(knowledge.prompt_pack(pack)["rules"][0]["text"], text)
                client = FakeClient({"rules": [{"text": text, "sources": ["rules"]}]})
                with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"DOMAIN_COMPILATION_MODE": "simple"}):
                    compiled, _ = knowledge.compile_knowledge(docs, {}, client, "offline", folder)
                self.assertEqual(compiled["rules"][0]["text"], text)
                self.assertEqual(json.loads(client.calls[0]["messages"][1]["content"])["documents"], docs)

    def test_original_default_documents_and_launch_package_are_v3(self):
        paths = load("input_paths").resolve_input_paths({})
        documents = load("knowledge").load_documents(
            paths["DOMAIN_INTRO_FILE"], paths["BUSINESS_RULES_FILE"], paths["TABLE_METADATA_DIR"])
        self.assertEqual(Path(paths["BUSINESS_RULES_FILE"]), SOURCE.parent / "business_rules_addendum.md")
        rules_doc = next(doc for doc in documents if doc["id"] == "rules")
        self.assertEqual(rules_doc["content"], (SOURCE.parent / "business_rules_addendum.md").read_text(encoding="utf-8-sig"))
        self.assertTrue(any("risk_pressure_score" in doc["content"] for doc in documents))
        self.assertIn("sample_values", json.dumps(documents))
        import run_pipeline_v3_sql
        self.assertEqual(Path(run_pipeline_v3_sql.__file__).parent, SOURCE)
