"""Offline checks for the full dataset, accounting, grading and metric formulas."""
import csv
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "run_pipeline_v3_sql _"))
from _bootstrap import bootstrap
bootstrap()
import run_all
import compute_metrics as metrics
from run_pipeline_v3_sql.performance import RunTiming


class DatasetTests(unittest.TestCase):
    def test_all_1000_questions_and_216_lossless_answers_are_archived_and_resume_is_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            manifest, summary = run_all.prepare_dataset(
                ROOT / "datatset/wealth_management_1000_test_set_questions.xlsx",
                ROOT / "datatset/216_questions_full_results.json", output)
            self.assertEqual(summary["questions"], 1000)
            self.assertEqual(summary["full_answer_overrides"], 216)
            self.assertEqual(set(summary["categories"].values()), {125})
            rows = metrics.read_csv(output / "input_questions.csv")
            overrides = json.loads((ROOT / "datatset/216_questions_full_results.json").read_text())
            for row in rows:
                if row["Source Question ID"] in overrides:
                    self.assertEqual(json.loads(row["Ground Truth"]), overrides[row["Source Question ID"]])
                    self.assertEqual(row["Ground Truth Source"], "full_answer_json")
            self.assertTrue(any(len(row["Ground Truth"]) > 32767 for row in rows))
            before = manifest.read_bytes()
            run_all.prepare_dataset(ROOT / "datatset/wealth_management_1000_test_set_questions.xlsx",
                                    ROOT / "datatset/216_questions_full_results.json", output)
            self.assertEqual(manifest.read_bytes(), before)
            self.assertTrue(all(row["Reference SQL"] for row in rows))

    def test_one_child_process_uses_only_local_experiment_paths(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory, patch.object(run_all.subprocess, "run") as run:
            run.return_value = SimpleNamespace(returncode=0)
            self.assertEqual(run_all.main(["--check", "--output-dir", directory]), 0)
            self.assertEqual(run.call_count, 1)
            command, environment = run.call_args.args[0], run.call_args.kwargs["env"]
            self.assertEqual(command[command.index("--limit") + 1], "0")
            self.assertEqual(command[command.index("--questions") + 1], str(Path(directory) / "input_questions.jsonl"))
            self.assertTrue(all(str(ROOT) in value for value in [environment["PIPELINE_ENV_FILE"],
                environment["KNOWLEDGE_CACHE_DIR"], environment["PIPELINE_RUNTIME_DIR"]]))
            self.assertEqual(environment["TEST_QUERY_OFFSET"], "0")


class MetricsTests(unittest.TestCase):
    prices = {"input_usd_per_million": .15, "output_usd_per_million": .60}

    def rows(self, graded=True):
        rows = [{"Sample Row ID": "q1", "Question": "First question", "New Status": "MATCH",
                 "Generation Input Tokens": "10", "Generation Output Tokens": "5", "Generation Latency Seconds": "2",
                 "Elapsed Seconds": "6", "Model Calls": "2", "Failed Model Calls": "0", "Calls Missing Token Usage": "0",
                 "Query Type": "Lookup", "Dataset Type": "Benchmark", "Target Model": "openai.gpt-oss-120b-1:0"},
                {"Sample Row ID": "q2", "Question": "Second question", "New Status": "MISMATCH",
                 "Generation Input Tokens": "20", "Generation Output Tokens": "5", "Generation Latency Seconds": "3",
                 "Elapsed Seconds": "4", "Model Calls": "3", "Failed Model Calls": "0", "Calls Missing Token Usage": "0",
                 "Query Type": "Aggregate", "Dataset Type": "Batch Status", "Target Model": "openai.gpt-oss-120b-1:0"}]
        if graded:
            for row in rows:
                row["Direct LLM Grading Path"] = "direct_llm_semantic_judgment"
        return rows

    def test_requested_formulas_use_all_question_calls_and_actual_totals(self):
        value = metrics.calculate(self.rows(), self.prices, graded=True)
        self.assertEqual(value["Accuracy (%)"], 50)
        self.assertEqual(value["Seconds per Output Token"], .5)
        self.assertEqual(value["Milliseconds per Output Token"], 500)
        self.assertAlmostEqual(value["Inference Cost (USD)"], .0000105)
        self.assertAlmostEqual(value["Average Cost per Question (USD)"], .00000525)
        self.assertEqual(value["Execution Efficiency (MATCH per second)"], .1)
        self.assertEqual(value["Model Calls"], 5)

    def test_ungraded_and_missing_usage_are_not_reported_as_zero_accuracy_or_zero_cost(self):
        rows = self.rows(False)
        rows[0]["Generation Input Tokens"] = ""
        value = metrics.calculate(rows, self.prices, graded=False)
        self.assertIsNone(value["Accuracy (%)"])
        self.assertIsNone(value["Inference Cost (USD)"])
        self.assertEqual(value["Measured Input Tokens"], 20)
        for row in rows:
            row["Generation Output Tokens"] = "0"
        self.assertIsNone(metrics.calculate(rows, self.prices)["Seconds per Output Token"])

    def test_reports_validate_coverage_and_write_metric_and_category_csvs(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            rows = self.rows()
            metrics.write_csv(output / "input_questions.csv", rows)
            metrics.write_csv(output / "graded_pipeline.csv", rows)
            result = metrics.write_reports(output)
            self.assertEqual(result["metrics"]["Accuracy (%)"], 50)
            self.assertTrue((output / "metrics.csv").is_file())
            self.assertEqual(len(metrics.read_csv(output / "grading_by_category.csv")), 2)
            metrics.write_csv(output / "graded_pipeline.csv", rows[:1])
            with self.assertRaisesRegex(ValueError, "missing"):
                metrics.write_reports(output)
            self.assertFalse(metrics.write_reports(output, allow_partial=True)["complete_dataset"])


class AccountingTests(unittest.TestCase):
    def test_success_and_failure_usage_is_saved_in_csv_without_prompt_or_error_text(self):
        replies = iter([SimpleNamespace(usage={"prompt_tokens": 10, "completion_tokens": 5}), TimeoutError("PRIVATE_ERROR")])
        def create(**request):
            result = next(replies)
            if isinstance(result, Exception):
                raise result
            return result
        timing = RunTiming()
        client = timing.client(SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            timing.enable_output_records(root / "_telemetry")
            with timing.question("q1"):
                client.chat.completions.create(model="offline", messages=[{"content": "PRIVATE_PROMPT"}])
                with self.assertRaises(TimeoutError):
                    client.chat.completions.create(model="offline", messages=[])
            timing.save(root / "summary.json", "failed")
            calls = metrics.read_csv(root / "model_calls.csv")
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0]["prompt_tokens"], "10")
            self.assertEqual(calls[1]["prompt_tokens"], "")
            self.assertEqual(calls[1]["status"], "error")
            self.assertNotIn("PRIVATE_PROMPT", (root / "model_calls.csv").read_text())
            self.assertNotIn("PRIVATE_ERROR", (root / "model_calls.csv").read_text())
            self.assertTrue(list((root / "_telemetry").glob("*.questions.csv")))


class GraderTests(unittest.TestCase):
    def test_execution_errors_are_preserved_and_successes_are_graded_with_usage_and_safe_resume(self):
        import grade_results as grader
        usage = SimpleNamespace(prompt_tokens=50, completion_tokens=10)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw:
            SimpleNamespace(usage=usage, choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(
                content=json.dumps({"status": "MATCH", "reason": "same answer", "evidence": {}})))]))))
        with tempfile.TemporaryDirectory() as directory:
            raw, output = Path(directory) / "raw.csv", Path(directory) / "graded.csv"
            rows = [{"Sample Row ID": "q1", "Question": "Failed question", "Ground Truth": "[]",
                     "New Pipeline Result": "Error", "New Status": "QUERY_SPEC_ERROR", "Generation Input Tokens": ""},
                    {"Sample Row ID": "q2", "Question": "Successful question", "Ground Truth": "[{\"n\":1}]",
                     "New Pipeline Result": "[{\"n\":1}]", "New Status": "PIPELINE_SUCCESS", "Generation Input Tokens": "100"}]
            metrics.write_csv(raw, rows)
            grader.regrade_existing_report(str(raw), str(output), client, "gpt-5-mini")
            result = metrics.read_csv(output)
            self.assertEqual(result[0]["New Status"], "QUERY_SPEC_ERROR")
            self.assertEqual(result[0]["Generation Input Tokens"], "")
            self.assertEqual(result[1]["New Status"], "MATCH")
            self.assertEqual(result[1]["Pipeline Execution Status"], "PIPELINE_SUCCESS")
            self.assertEqual(result[1]["Grader Input Tokens"], "50")
            grader.regrade_existing_report(str(raw), str(output), None, "gpt-5-mini")
            rows[1]["New Pipeline Result"] = "[]"
            metrics.write_csv(raw, rows)
            with self.assertRaisesRegex(ValueError, "Resume input changed"):
                grader.regrade_existing_report(str(raw), str(output), client, "gpt-5-mini")


if __name__ == "__main__":
    unittest.main()
