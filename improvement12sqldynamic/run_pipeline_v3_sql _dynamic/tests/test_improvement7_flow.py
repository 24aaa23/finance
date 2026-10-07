"""Run the real runner/SQLite executor with staged model replies, never an API."""
import contextlib
import csv
import importlib
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from support import SOURCE

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class FlowTests(unittest.TestCase):
    def test_original_and_paraphrase_keep_contract_and_ground_truth_is_report_only(self):
        self.run_flow(False)

    def test_operator_specialists_restart_retrieval_without_rows_or_ground_truth(self):
        self.run_flow(True)

    def test_exhausted_understanding_continues_to_real_sqlite_result_and_logs_fallback(self):
        self.run_flow(False, invalid_understanding=True)

    def test_in_place_retry_replaces_only_failed_row_and_keeps_success_and_debug(self):
        self.run_flow(False, retry_in_place=True)

    def test_throttled_runner_saves_one_retryable_row_then_resume_completes_both(self):
        self.run_flow(False, throttle_once=True)

    def test_resume_crash_and_pending_keeps_success_and_backups_across_configuration_change(self):
        self.run_flow(False, resume_crash_pending=True)

    def run_flow(self, consultation, invalid_understanding=False, retry_in_place=False, throttle_once=False,
                 resume_crash_pending=False):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "test.db"
            with sqlite3.connect(database) as connection:
                connection.execute("CREATE TABLE Accounts (id TEXT PRIMARY KEY, amount REAL)")
                connection.execute("INSERT INTO Accounts VALUES ('ROW_MARKER', 42)")
            connection.close()
            domain = root / "domain.prompt"
            rules = root / "rules.md"
            metadata = root / "metadata"
            metadata.mkdir()
            domain.write_text("Accounts identify owners.", encoding="utf-8")
            rules.write_text("Preserve the requested account identifiers.", encoding="utf-8")
            (metadata / "accounts.yaml").write_text(
                "identity:\n  id: Accounts\n  description: Account owners\nattributes:\n"
                "  - name: id\n    type: string\n    description: Account identifier\n"
                "  - name: amount\n    type: decimal\n", encoding="utf-8")
            questions = root / "questions.jsonl"
            question_list = ["List accounts", "Show accounts"] + (["Read accounts"] if resume_crash_pending else [])
            questions.write_text("\n".join(json.dumps({"Sample Row ID": str(i), "Question": question,
                "Ground Truth": "GROUND_TRUTH_MARKER"}) for i, question in enumerate(question_list)), encoding="utf-8")
            calls = []
            final_calls = {}
            pending_throttle = [throttle_once]
            resolved_count = [0]

            def reply(**request):
                calls.append(request)
                system = request["messages"][0]["content"]
                if system.startswith(("Compile reusable", "You are the Domain Knowledge")):
                    result = {"rules": [{"id": "K1", "text": rules.read_text(), "citations": [
                        {"source": "rules", "quote": rules.read_text()}], "fields": []}], "conflicts": [],
                        "source_review": {"domain": "reviewed", "rules": "reviewed", "yaml/accounts.yaml": "reviewed"}}
                    if system.startswith("Compile reusable"):
                        payload = json.loads(request["messages"][1]["content"])
                        ids = {doc["id"]: f"K{i}" for i, doc in enumerate(payload["documents"], 1)}
                        result["rules"] = [{"id": ids[doc["id"]], "text": doc["content"], "fields": [],
                                            "citations": [{"source": doc["id"], "quote": doc["content"]}]}
                                           for doc in payload["documents"]]
                        if "sections" in payload:
                            result["coverage"] = {section["id"]: {"rule_ids": [ids[section["source"]]]}
                                                  for section in payload["sections"]}
                elif system.startswith("Review reusable business knowledge"):
                    result = {"additions": [], "replacements": [], "conflicts": []}
                elif system.startswith("Resolve this"):
                    resolved_count[0] += 1
                    if pending_throttle[0] or (resume_crash_pending and resolved_count[0] == 2):
                        pending_throttle[0] = False
                        raise RuntimeError("Error code: 429 - rate_limit_exceeded: Too many requests")
                    result = {"bindings": [{"phrase": "accounts", "table": "Accounts", "column": "id", "rule_ids": ["K1"]}],
                        "metrics": [], "filters": [], "group_by": [], "required_projection": ["id"], "order_by": [],
                        "limit": None, "population": "All accounts", "null_policy": "unspecified", "ambiguities": []}
                    if "consultation_context" in request["messages"][1]["content"]:
                        result["population"] = "All accounts; one row per account"
                    if invalid_understanding:
                        result["ambiguities"] = ["Owner is unclear"]
                elif system.startswith("Select exact"):
                    result = ["Accounts"]
                elif system.startswith("Split the question"):
                    result = {"selected_decomposition": {"subquestions": [{"id": "q1", "question": "Read account ids",
                        "source_class": "Accounts", "required_fields": ["id"], "retrieval_grain": ["id"]}],
                        "answer_requirements": {"predicates": [], "joins": [], "calculation_notes": "Return ids."}}}
                elif system.startswith("Describe one source"):
                    result = {"id": "q1", "retrieval_specs": [{"id": "q1", "class": "Accounts", "fields": ["id"],
                        "entity_key": ["id"], "optional_fields": [], "filters": []}], "output_schema": ["id"]}
                elif system.startswith("Build one executable"):
                    result = {"final_steps": [], "projection": ["id"], "assumptions": []}
                    if consultation:
                        question = "List accounts" if "List accounts" in request["messages"][1]["content"] else "Show accounts"
                        final_calls[question] = final_calls.get(question, 0) + 1
                        if final_calls[question] <= 2:
                            result = {"consultation_request": {
                                "agent": "domain" if final_calls[question] == 1 else "query_understanding",
                                "topic": "population"}}
                else:
                    raise AssertionError("Unexpected model stage: " + system[:100])
                return types.SimpleNamespace(choices=[types.SimpleNamespace(
                    message=types.SimpleNamespace(content=json.dumps(result)), finish_reason="stop")])

            client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=reply)))
            environment = {"PIPELINE_ENV_FILE": str(root / "no.env"), "PIPELINE_OUTPUT_DIR": str(root),
                           "REPORT_FILE": str(root / "run.csv"), "INPUT_QUERY_FILE": str(questions),
                           "SQLITE_DB_PATH": str(database), "RESUME_CRASHES_AND_PENDING": "0",
                           "RETRY_ERRORS_IN_PLACE": "0"}
            with patch.dict(os.environ, environment):
                main = importlib.import_module("run_pipeline_v3_sql.main")
                common = importlib.import_module("run_pipeline_v3_sql.common")
                timing = importlib.import_module("run_pipeline_v3_sql.performance").RunTiming()
                settings = {"SQLITE_DB_PATH": str(database), "DOMAIN_INTRO_FILE": str(domain),
                    "BUSINESS_RULES_FILE": str(rules), "TABLE_METADATA_DIR": str(metadata),
                    "KNOWLEDGE_CACHE_DIR": str(root / "cache"), "REPORT_FILE": str(root / "run.csv"),
                    "QUERY_UNDERSTANDING": True, "CONTRACT_CHECKS": True, "AGENT_CONSULTATION": consultation, "TEST_QUERY_LIMIT": 0,
                    "TEST_QUERY_OFFSET": 0, "GPT_OSS_MODEL": "offline"}
                with patch.multiple(main, **settings), patch.object(common, "SQLITE_DB_PATH", str(database)), \
                     patch.object(main, "build_gpt_oss_client", return_value=client), \
                     patch.object(main.time, "sleep"), patch("run_pipeline_v3_sql.runtime_guard.wait_for_memory"), \
                     patch.object(main.api_logger, "save"), contextlib.redirect_stdout(io.StringIO()):
                    main._main(timing=timing)
                if resume_crash_pending:
                    with (root / "run.csv").open(encoding="utf-8-sig", newline="") as handle:
                        saved = list(csv.DictReader(handle))
                    self.assertEqual([r["New Status"] for r in saved], ["PIPELINE_SUCCESS", "TRANSIENT_ERROR"])
                    with (root / "run_debug.csv").open(encoding="utf-8-sig", newline="") as handle:
                        saved_debug = list(csv.DictReader(handle))
                    before = (root / "run.csv").read_bytes()
                    manifest_path = root / "run.csv.manifest.json"
                    old_manifest = json.loads(manifest_path.read_text())
                    old_manifest["run_identity"] = "previous_code_and_delay"
                    old_manifest["configuration"]["query_delay_seconds"] = 30
                    manifest_path.write_text(json.dumps(old_manifest), encoding="utf-8")
                    resumed = importlib.import_module("run_pipeline_v3_sql.performance").RunTiming()
                    with patch.dict(os.environ, {"RESUME_CRASHES_AND_PENDING": "1", "QUERY_DELAY_SECONDS": "0"}), \
                         patch.multiple(main, **settings), patch.object(common, "SQLITE_DB_PATH", str(database)), \
                         patch.object(main, "build_gpt_oss_client", return_value=client), \
                         patch("run_pipeline_v3_sql.runtime_guard.wait_for_memory"), \
                         patch.object(main.api_logger, "save"), contextlib.redirect_stdout(io.StringIO()):
                        main._main(timing=resumed)
                    self.assertEqual(len(resumed.questions), 2)
                    with (root / "run.csv").open(encoding="utf-8-sig", newline="") as handle:
                        recovered = list(csv.DictReader(handle))
                    self.assertEqual([r["Sample Row ID"] for r in recovered], ["0", "1", "2"])
                    self.assertEqual([r["New Status"] for r in recovered], ["PIPELINE_SUCCESS"] * 3)
                    self.assertEqual(recovered[0], saved[0])
                    with (root / "run_debug.csv").open(encoding="utf-8-sig", newline="") as handle:
                        recovered_debug = list(csv.DictReader(handle))
                    self.assertEqual(recovered_debug[0], saved_debug[0])
                    updated = json.loads(manifest_path.read_text())
                    history = updated["retry_history"][-1]
                    self.assertEqual(history["mode"], "crashes_and_pending")
                    self.assertEqual(history["selected_ids"], ["1", "2"])
                    self.assertEqual(history["completed_ids"], ["1", "2"])
                    self.assertEqual((Path(history["backup_directory"]) / "run.csv").read_bytes(), before)
                    self.assertEqual(updated["configuration"]["query_delay_seconds"], 0)
                    return
                if throttle_once:
                    self.assertEqual(len(timing.questions), 1)
                    self.assertEqual(timing.metadata["stop_reason"], "transient_service_error")
                    with (root / "run.csv").open(encoding="utf-8-sig", newline="") as handle:
                        interrupted = list(csv.DictReader(handle))
                    self.assertEqual([r["New Status"] for r in interrupted], ["TRANSIENT_ERROR"])
                    self.assertEqual(interrupted[0]["Sample Row ID"], "0")
                    self.assertFalse(any(s["stage"] == "Scan" for s in timing.stages))
                    resumed = importlib.import_module("run_pipeline_v3_sql.performance").RunTiming()
                    with patch.multiple(main, **settings), patch.object(common, "SQLITE_DB_PATH", str(database)), \
                         patch.object(main, "build_gpt_oss_client", return_value=client), \
                         patch("run_pipeline_v3_sql.runtime_guard.wait_for_memory"), \
                         patch.object(main.api_logger, "save"), contextlib.redirect_stdout(io.StringIO()):
                        main._main(timing=resumed)
                    self.assertEqual(len(resumed.questions), 2)
                    with (root / "run.csv").open(encoding="utf-8-sig", newline="") as handle:
                        recovered = list(csv.DictReader(handle))
                    self.assertEqual([r["New Status"] for r in recovered], ["PIPELINE_SUCCESS"] * 2)
                    self.assertEqual([r["Sample Row ID"] for r in recovered], ["0", "1"])
                    return
                self.assertEqual(len(timing.questions), 2)
                self.assertTrue(all(q["llm_calls"] >= 5 for q in timing.questions))
                self.assertTrue(any(s["stage"] == "report_writes" for s in timing.stages))
                self.assertTrue(any(s["stage"] == "Scan" for s in timing.stages))
                self.assertFalse(any(s["stage"] == "query_delay" for s in timing.stages))
                self.assertFalse(timing.metadata["knowledge_cache_hit"])
                resumed_timing = importlib.import_module("run_pipeline_v3_sql.performance").RunTiming()
                with patch.multiple(main, **settings), patch.object(common, "SQLITE_DB_PATH", str(database)), \
                     patch.object(main, "build_gpt_oss_client", return_value=client), \
                     patch.object(main.api_logger, "save"), contextlib.redirect_stdout(io.StringIO()):
                    main._main(timing=resumed_timing)
                self.assertTrue(resumed_timing.metadata["knowledge_cache_hit"])
                self.assertEqual(resumed_timing.questions, [])
                self.assertEqual(resumed_timing.llm_calls, [])
                self.assertEqual(resumed_timing.metadata["resumed_rows"], 2)
                if retry_in_place:
                    with (root / "run.csv").open(encoding="utf-8-sig", newline="") as handle:
                        saved = list(csv.DictReader(handle))
                    saved[0]["New Status"] = "FINAL_SPEC_ERROR"
                    saved[0]["New Pipeline Result"] = "old failure"
                    for row in saved:
                        row["User Note"] = "Keep this value"
                    with (root / "run.csv").open("w", encoding="utf-8", newline="") as handle:
                        writer = csv.DictWriter(handle, fieldnames=list(saved[0]))
                        writer.writeheader()
                        writer.writerows(saved)
                    with (root / "run_debug.csv").open(encoding="utf-8-sig", newline="") as handle:
                        saved_debug = list(csv.DictReader(handle))
                    original_bytes = (root / "run.csv").read_bytes()
                    identity_file = root / "run.csv.manifest.json"
                    old_manifest = json.loads(identity_file.read_text())
                    old_manifest["run_identity"] = "previous_code"
                    identity_file.write_text(json.dumps(old_manifest), encoding="utf-8")
                    retry_timing = importlib.import_module("run_pipeline_v3_sql.performance").RunTiming()
                    with patch.dict(os.environ, {"RETRY_ERRORS_IN_PLACE": "1"}), \
                         patch.multiple(main, **settings), patch.object(common, "SQLITE_DB_PATH", str(database)), \
                         patch.object(main, "build_gpt_oss_client", return_value=client), \
                         patch("run_pipeline_v3_sql.runtime_guard.wait_for_memory"), \
                         patch.object(main.api_logger, "save"), contextlib.redirect_stdout(io.StringIO()):
                        main._main(timing=retry_timing)
                        before_noop = (root / "run.csv").read_bytes()
                        with patch.object(main, "build_gpt_oss_client", side_effect=AssertionError("No model needed")):
                            main._main()
                        self.assertEqual((root / "run.csv").read_bytes(), before_noop)
                    self.assertEqual(len(retry_timing.questions), 1)
                    with (root / "run.csv").open(encoding="utf-8-sig", newline="") as handle:
                        retried = list(csv.DictReader(handle))
                    self.assertEqual(len(retried), 2)
                    self.assertEqual(retried[1], saved[1])
                    self.assertEqual(retried[0]["New Status"], "PIPELINE_SUCCESS")
                    self.assertEqual(retried[0]["User Note"], "Keep this value")
                    with (root / "run_debug.csv").open(encoding="utf-8-sig", newline="") as handle:
                        retried_debug = list(csv.DictReader(handle))
                    self.assertEqual(retried_debug[1], saved_debug[1])
                    manifest = json.loads(identity_file.read_text())
                    self.assertEqual(manifest["retry_history"][-1]["selected_ids"], ["0"])
                    self.assertEqual(manifest["retry_history"][-1]["completed_ids"], ["0"])
                    backup = Path(manifest["retry_history"][-1]["backup_directory"])
                    self.assertEqual((backup / "run.csv").read_bytes(), original_bytes)
                    sidecar = [json.loads(line) for line in (root / "run.jsonl").read_text().splitlines()]
                    self.assertEqual([r["New Status"] for r in sidecar], ["PIPELINE_SUCCESS"] * 2)
            with (root / "run.csv").open(encoding="utf-8-sig", newline="") as handle:
                outputs = list(csv.DictReader(handle))
            self.assertEqual([r["New Status"] for r in outputs], ["PIPELINE_SUCCESS"] * 2, outputs)
            self.assertEqual([json.loads(r["New Pipeline Result"]) for r in outputs], [[{"id": "ROW_MARKER"}]] * 2)
            self.assertNotIn("GROUND_TRUTH_MARKER", json.dumps(calls))
            # Every rule remains present ahead of changing question text. Different
            # questions share a prefix without sharing answers or interpretations.
            for system_prefix, question_label in (
                ("Resolve this", '"question": '),
                ("Select exact", "Question: "),
                ("Split the question", "Question: "),
                ("Describe one source", "Original question: "),
                ("Build one executable", "Question: "),
            ):
                prompts = [r["messages"][1]["content"] for r in calls
                           if r["messages"][0]["content"].startswith(system_prefix)]
                prefixes = [p.split(question_label, 1)[0] for p in prompts]
                self.assertTrue(prefixes)
                self.assertTrue(all(p == prefixes[0] for p in prefixes))
                if system_prefix == "Select exact":
                    self.assertIn("Accounts", prefixes[0])
                else:
                    self.assertIn("Preserve the requested account identifiers.", prefixes[0])
                    self.assertIn("Accounts identify owners.", prefixes[0])
                    self.assertIn("Account identifier", prefixes[0])
            for request in calls:
                self.assertNotIn("ROW_MARKER", json.dumps(request))
                self.assertNotIn(str(database), json.dumps(request))
            with (root / "run_debug.csv").open(encoding="utf-8-sig", newline="") as handle:
                debug = list(csv.DictReader(handle))
            if invalid_understanding:
                self.assertTrue(all(json.loads(r["Debug Query Understanding"]) == {} for r in debug))
                diagnostics = [json.loads(r["Debug Understanding Attempts"]) for r in debug]
                self.assertTrue(all(d["status"] == "base_pipeline_fallback" and d["attempts"] == 3 for d in diagnostics))
                self.assertEqual(sum(r["messages"][0]["content"].startswith("Resolve this") for r in calls), 6)
            else:
                self.assertTrue(all(json.loads(r["Debug Query Understanding"])["bindings"] for r in debug))
            if consultation:
                self.assertEqual(final_calls, {"List accounts": 3, "Show accounts": 3})
                self.assertEqual(sum(r["messages"][0]["content"].startswith("Select exact") for r in calls), 4)
                self.assertTrue(all(json.loads(r["Debug Query Understanding"])["population"].endswith("one row per account") for r in debug))
                self.assertIn('"agent_consultations"', json.dumps(debug).replace('\\"', '"'))
            for request in calls:
                if not invalid_understanding and request["messages"][0]["content"].startswith(("Describe one source", "Build one executable")):
                    self.assertIn('"phrase": "accounts"', request["messages"][1]["content"])


if __name__ == "__main__":
    unittest.main()
