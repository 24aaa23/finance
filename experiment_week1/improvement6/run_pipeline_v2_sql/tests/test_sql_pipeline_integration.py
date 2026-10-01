"""Exercise the complete SQL pipeline locally with scripted model responses."""
import contextlib
import csv
import hashlib
import importlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

EXPERIMENT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(EXPERIMENT))
from run_pipeline_v2_sql import common, main, raw_query, runtime_guard
from run_pipeline_v2_sql.raw_sql import render_raw_sql
from run_pipeline_v2_sql.sqlite_backend import load_sqlite_schema
from run_pipeline_v2_sql.llm_operators.pre_scan_validate import semantic_pre_scan_validate
from run_pipeline_v2_sql.spec_contracts import validate_query_spec_contract

DATABASE = EXPERIMENT / "wealth_management_diverse.db"
INVESTORS = "ATOM_ENTITY_INVESTOR_PROFILE_001"
HOLDINGS = "ATOM_ENTITY_PORTFOLIO_HOLDING_001"


class ScriptedClient:
    """Only model responses are scripted; all operators and database work are real."""
    def __init__(self):
        self.calls = []
        self.prompts = []
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.create))

    def create(self, **request):
        system = request["messages"][0]["content"]
        prompt = request["messages"][-1]["content"]
        role = next(key for key in ("retrieve", "decompose", "query_spec", "final_spec", "validate")
                    if common.ROLE_PROMPTS[key] == system)
        self.calls.append(role)
        self.prompts.append((role, prompt))
        if role == "retrieve":
            payload = [INVESTORS, HOLDINGS]
        elif role == "decompose":
            payload = {"selected_decomposition": {
                "subquestions": [
                    {"id": "profiles", "source_class": INVESTORS, "question": "All investor IDs and risk groups",
                     "required_fields": ["investor_id", "risk_tolerance"], "retrieval_grain": ["investor_id"]},
                    {"id": "holdings", "source_class": HOLDINGS, "question": "All holding IDs, investor IDs and costs",
                     "required_fields": ["holding_id", "investor_id", "cost"], "retrieval_grain": ["holding_id"]},
                ],
                "answer_requirements": {
                    "joins": [{"left_branch": "holdings", "right_branch": "profiles",
                               "left_on": ["investor_id"], "right_on": ["investor_id"]}],
                    "group_by": ["risk_tolerance"], "preserve_null_groups": True,
                    "required_projection": ["risk_tolerance", "total_cost"],
                },
            }}
        elif role == "query_spec":
            branch = json.loads(prompt.split("Active branch: ", 1)[1].splitlines()[0])
            fields = branch["required_fields"]
            payload = {"id": branch["id"], "retrieval_specs": [{
                "id": branch["id"], "class": branch["source_class"], "fields": fields,
                "entity_key": branch["retrieval_grain"], "optional_fields": fields, "filters": [],
            }], "output_schema": fields}
        elif role == "final_spec":
            payload = {"final_steps": [
                {"id": "joined", "operator": "Integrate", "inputs": ["holdings_processed", "profiles_processed"],
                 "left_on": ["investor_id"], "right_on": ["investor_id"], "join_type": "inner"},
                {"id": "totals", "operator": "Filter_Aggregate", "input": "joined",
                 "group_by": ["risk_tolerance"], "preserve_null_groups": True,
                 "aggregations": [{"operation": "sum", "input_column": "cost", "output_column": "total_cost"}]},
            ], "projection": ["risk_tolerance", "total_cost"]}
        else:
            payload = {"is_valid": True, "reason": "Scripted review for offline integration"}
        return types.SimpleNamespace(choices=[types.SimpleNamespace(
            message=types.SimpleNamespace(content=json.dumps(payload)))])


class SQLPipelineIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = load_sqlite_schema(DATABASE)

    def test_error_only_retry_main_resumes_without_rerunning_successes(self):
        from run_pipeline_v2_sql.retry_batch import prepare_query_spec_retry
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "original.csv"
            original_rows = [{"Sample Row ID": key, "Question": key, "Ground Truth": "[]", "New Status": status}
                             for key, status in [("success", "PIPELINE_SUCCESS"), ("retry1", "QUERY_SPEC_ERROR"),
                                                 ("other", "SCAN_ERROR"), ("retry2", "QUERY_SPEC_ERROR")]]
            with source.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(original_rows[0]))
                writer.writeheader()
                writer.writerows(original_rows)
            before = source.read_bytes()
            retry_dir = root / "retry"
            questions, _ = prepare_query_spec_retry(source, retry_dir)
            report = retry_dir / "raw_pipeline_v9.csv"
            executed = []

            class Executor:
                def execute_dag(self, dag, query, **kwargs):
                    executed.append(query)
                    return {"trace": {"final_output_produced": True, "final_operator_data": [{"id": query}]}}

            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.dict(common.os.environ, {
                    "INPUT_QUERY_FILE": str(questions), "RESULT_JSONL_FILE": str(retry_dir / "raw_pipeline_v9.jsonl"),
                    "DEBUG_JSONL_FILE": str(retry_dir / "raw_pipeline_v9_debug.jsonl"),
                    "RETRY_QUERY_SPEC_ERRORS_ONLY": "1", "FINAL_SEMANTIC_REVIEW": "0",
                }))
                for name, value in {"REPORT_FILE": str(report), "TEST_QUERY_LIMIT": 0, "TEST_QUERY_OFFSET": 0,
                                    "SQLITE_DB_PATH": str(DATABASE)}.items():
                    stack.enter_context(patch.object(main, name, value))
                stack.enter_context(patch.object(main, "build_gpt_oss_client", return_value=object()))
                stack.enter_context(patch.object(main, "semantic_retrieve", return_value={"retrieved_tables": []}))
                stack.enter_context(patch.object(main, "semantic_decompose_question", return_value={"selected_decomposition": {}}))
                stack.enter_context(patch.object(main, "AdvancedAOPPlanner", return_value=types.SimpleNamespace(
                    plan_optimal_dag_from_decomposition=lambda *args: main.nx.DiGraph())))
                stack.enter_context(patch.object(main, "AOPExecutor", return_value=Executor()))
                stack.enter_context(patch.object(main.api_logger, "save"))
                stack.enter_context(patch.object(main.time, "sleep"))
                stack.enter_context(patch.object(runtime_guard, "wait_for_memory"))
                stack.enter_context(patch.object(runtime_guard, "progress"))
                stack.enter_context(patch("socket.create_connection", side_effect=AssertionError("Network forbidden")))
                stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                main._main()
                self.assertEqual(executed, ["retry1", "retry2"])
                with report.open(encoding="utf-8", newline="") as handle:
                    rows = list(csv.DictReader(handle))
                preserved = dict(rows[0])
                rows[1]["New Status"] = "QUERY_SPEC_ERROR"
                with report.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(rows)
                executed.clear()
                main._main()
                self.assertEqual(executed, ["retry2"])
                with report.open(encoding="utf-8", newline="") as handle:
                    final = list(csv.DictReader(handle))
                self.assertEqual(len(final), 2)
                self.assertEqual(final[0], preserved)
                self.assertTrue(all(row["New Status"] == "PIPELINE_SUCCESS" for row in final))
                executed.clear()
                main._main()
                self.assertEqual(executed, [])
            self.assertEqual(source.read_bytes(), before)

    def test_query_spec_uses_sql_validation_and_rejects_invalid_filters(self):
        retrieval = {"class": HOLDINGS, "fields": ["holding_id", "cost"], "entity_key": ["holding_id"],
                     "filters": [{"field": "cost", "operator": "unsupported", "value": 10}]}
        errors = validate_query_spec_contract({"retrieval_specs": [retrieval]}, self.schema)
        self.assertTrue(any("Unsupported raw filter" in error for error in errors), errors)

    def test_pre_scan_rejects_changed_population_and_calculations(self):
        retrieval = {"class": HOLDINGS, "fields": ["holding_id", "cost"], "entity_key": ["holding_id"],
                     "optional_fields": ["cost"], "filters": []}
        query = render_raw_sql(retrieval, self.schema)
        self.assertEqual(raw_query.render_raw_query(retrieval, self.schema), query)
        inputs = {"retrieval_spec": retrieval, "global_schema": self.schema, "sqlite_db_path": str(DATABASE)}
        self.assertTrue(semantic_pre_scan_validate({**inputs, "sparql": query}, None)["pre_scan_validation"]["is_valid"])
        for changed in (query + ' WHERE "cost" IS NOT NULL', query + " LIMIT 1",
                        query.replace("SELECT ", "SELECT DISTINCT ", 1),
                        query.replace('"cost" AS "cost"', 'SUM("cost") AS "cost"')):
            self.assertFalse(semantic_pre_scan_validate({**inputs, "sparql": changed}, None)["pre_scan_validation"]["is_valid"])

    def test_complete_main_uses_business_metadata_and_sql_without_fuseki(self):
        checksum = hashlib.sha256(DATABASE.read_bytes()).hexdigest()
        with sqlite3.connect(DATABASE.resolve().as_uri() + "?mode=ro", uri=True) as connection:
            expected = dict(connection.execute(
                f'SELECT p.risk_tolerance, SUM(h.cost) FROM "{HOLDINGS}" h '
                f'JOIN "{INVESTORS}" p ON h.investor_id=p.investor_id GROUP BY p.risk_tolerance'))
        client = ScriptedClient()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            questions = root / "questions.jsonl"
            questions.write_text(json.dumps({
                "Sample Row ID": "sql-integration-1",
                "Question": "For each investor risk_tolerance group, sum all holding costs. Include NULL risk groups and preserve duplicates.",
                "Ground Truth": "[]",
            }) + "\n", encoding="utf-8")
            report = root / "report.csv"
            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.dict(common.os.environ, {
                    "INPUT_QUERY_FILE": str(questions), "RESULT_JSONL_FILE": str(root / "results.jsonl"),
                    "DEBUG_JSONL_FILE": str(root / "debug.jsonl"), "FINAL_SEMANTIC_REVIEW": "0",
                }))
                for name, value in {"REPORT_FILE": str(report), "TEST_QUERY_LIMIT": 1, "TEST_QUERY_OFFSET": 0,
                                    "SQLITE_DB_PATH": str(DATABASE)}.items():
                    stack.enter_context(patch.object(main, name, value))
                stack.enter_context(patch.object(main, "build_gpt_oss_client", return_value=client))
                stack.enter_context(patch.object(main.api_logger, "save"))
                stack.enter_context(patch.object(runtime_guard, "wait_for_memory"))
                stack.enter_context(patch.object(runtime_guard, "progress"))
                # The small documentation schema is allowed; instance graphs are not.
                import rdflib
                original_parse = rdflib.Graph.parse
                parsed_sources = []
                def schema_only(graph, source, *args, **kwargs):
                    self.assertEqual(Path(source).resolve(), Path(main.SCHEMA_FILE).resolve())
                    parsed_sources.append(source)
                    return original_parse(graph, source, *args, **kwargs)
                stack.enter_context(patch.object(rdflib.Graph, "parse", schema_only))
                stack.enter_context(patch("socket.create_connection", side_effect=AssertionError("Network forbidden")))
                fuseki = importlib.import_module("run_pipeline_v2_sql.non_llm_operators.fuseki")
                stack.enter_context(patch.object(fuseki, "execute_sparql_on_fuseki", side_effect=AssertionError("Fuseki forbidden")))
                stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                main._main()
            with report.open(encoding="utf-8", newline="") as handle:
                row = next(csv.DictReader(handle))
            with (root / "report_debug.csv").open(encoding="utf-8", newline="") as handle:
                debug = next(csv.DictReader(handle))
            self.assertEqual(row["New Status"], "PIPELINE_SUCCESS", debug.get("Debug Exception") or debug)
            actual = {item["risk_tolerance"]: item["total_cost"] for item in json.loads(row["New Pipeline Result"])}
            self.assertEqual(set(actual), set(expected))
            for key in actual:
                if expected[key] is None:
                    self.assertIsNone(actual[key])
                else:
                    self.assertAlmostEqual(float(actual[key]), expected[key], delta=1e-5)
            operators = debug["Debug DAG Sequence"].split(" -> ")
            self.assertEqual(operators, ["Query_Spec"] * 2 + ["Generate"] * 2 + ["Pre_Scan_Validate"] * 2
                             + ["Scan"] * 2 + ["Processing_Spec"] * 2 + ["Final_Spec", "Validate", "Explain"])
            executed = json.loads(debug["Debug SPARQL"])
            self.assertEqual(len(executed), 2)
            self.assertTrue(all(item["sparql"].startswith("SELECT ") and " FROM " in item["sparql"] for item in executed))
            manifest = json.loads(Path(str(report) + ".manifest.json").read_text())
            self.assertEqual(set(manifest["input_files"]), {"questions", "sqlite_database", "business_metadata_schema"})
            self.assertEqual(manifest["input_files"]["business_metadata_schema"]["sha256"],
                             hashlib.sha256(Path(main.SCHEMA_FILE).read_bytes()).hexdigest())
            self.assertEqual(manifest["configuration"]["scan_backend"], "sqlite")
        self.assertEqual(client.calls, ["retrieve", "decompose", "query_spec", "query_spec", "final_spec"])
        self.assertEqual(len(parsed_sources), 1)
        for role, prompt in client.prompts:
            if role in ("decompose", "query_spec", "final_spec"):
                with self.subTest(role=role):
                    self.assertIn("risk appetite", prompt)
                    self.assertIn('"allowed_values": ["Aggressive", "Conservative", "Moderate"]', prompt)
                    self.assertIn("Investor's risk tolerance classification", prompt)
        self.assertEqual(checksum, hashlib.sha256(DATABASE.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
