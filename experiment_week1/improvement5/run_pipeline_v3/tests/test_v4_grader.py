"""Final-answer grading preserves execution status and never grades branch scans."""
import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


SOURCE = Path(__file__).resolve().parents[1] / "grade_final_answers.py"
SPEC = importlib.util.spec_from_file_location("_v4_final_answer_grader_tests", SOURCE)
grader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(grader)


class FinalAnswerGraderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.input_path = Path(self.temp.name) / "raw.csv"
        self.output_path = Path(self.temp.name) / "graded.csv"

    def row(self, row_id="a", answer="[]", status="PIPELINE_SUCCESS"):
        return {
            "Sample Row ID": row_id,
            "Question": "Which records meet the conditions?",
            "Ground Truth": "[]",
            "New Pipeline Result": answer,
            "New Status": status,
            "Comparison / Comments": "Execution report metadata",
            "Scan Raw Rows": '[{"unprocessed": 999}]',
        }

    def write_rows(self, rows):
        with self.input_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def read_rows(self):
        with self.output_path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    def run_grader(self, model="test-grader", client=None):
        return grader.regrade_existing_report(str(self.input_path), str(self.output_path), client or object(), model)

    def test_final_answer_selection_preserves_empty_answer_and_ignores_raw_rows(self):
        self.assertEqual(grader.final_answer_for_grading(self.row()), "[]")
        row = self.row(answer='[{"total": 12}]')
        self.assertEqual(grader.final_answer_for_grading(row), '[{"total": 12}]')

    def test_missing_or_blank_final_answer_is_explicit_error(self):
        with self.assertRaisesRegex(ValueError, "requires New Pipeline Result"):
            grader.final_answer_for_grading({"Scan Raw Rows": "[]"})
        with self.assertRaisesRegex(ValueError, "empty New Pipeline Result"):
            grader.final_answer_for_grading(self.row(answer="  "))
        with self.assertRaisesRegex(ValueError, "structured JSON"):
            grader.final_answer_for_grading(self.row(answer="ERROR: no final result"))

    def test_grades_final_answer_without_overwriting_execution_status(self):
        self.write_rows([self.row()])
        with patch.object(grader, "direct_llm_grade_row", return_value={"status": "MATCH", "reason": "Both answers are empty."}) as mocked:
            self.run_grader()
        self.assertEqual(mocked.call_args.kwargs["final_answer"], "[]")
        actual = self.read_rows()[0]
        self.assertEqual(actual["New Status"], "PIPELINE_SUCCESS")
        self.assertEqual(actual["Execution Status"], "PIPELINE_SUCCESS")
        self.assertEqual(actual["Grade Status"], "MATCH")
        self.assertEqual(actual["Comparison / Comments"], "Execution report metadata")

    def test_every_non_success_execution_counts_as_mismatch_with_original_errors(self):
        statuses = ["QUERY_SPEC_ERROR", "FINAL_SPEC_ERROR", "DECOMPOSITION_ERROR", "TRANSIENT_ERROR", "CRASH", "FUTURE_STAGE_ERROR"]
        self.write_rows([self.row(str(index), answer="ERROR: " + status, status=status)
                         for index, status in enumerate(statuses)])
        original = self.input_path.read_bytes()
        with patch.object(grader, "direct_llm_grade_row") as mocked:
            self.run_grader()
        mocked.assert_not_called()
        actual = self.read_rows()
        self.assertEqual([row["New Status"] for row in actual], statuses)
        self.assertEqual([row["Execution Status"] for row in actual], statuses)
        self.assertEqual([row["New Pipeline Result"] for row in actual], ["ERROR: " + status for status in statuses])
        self.assertTrue(all(row["Grade Status"] == "MISMATCH" for row in actual))
        self.assertTrue(all(row["Direct LLM Grading Path"] == "execution_failure_as_mismatch" for row in actual))
        self.assertTrue(all("No LLM comparison" in row["Grade Reason"] for row in actual))
        self.assertEqual(self.input_path.read_bytes(), original)

    def test_resume_replaces_legacy_skips_without_regrading_unchanged_answers(self):
        self.write_rows([self.row("failed", status="FINAL_SPEC_ERROR"), self.row("ok")])
        with patch.object(grader, "direct_llm_grade_row", return_value={"status": "PARTIAL", "reason": "Some values differ."}):
            self.run_grader()
        saved = self.read_rows()
        saved[0].update({"Grade Status": "SKIPPED_EXECUTION_FAILURE",
                         "Grade Reason": "Legacy skipped execution", "Direct LLM Grading Path": "preserved_execution_status"})
        with self.output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(saved[0]))
            writer.writeheader()
            writer.writerows(saved)
        with patch.object(grader, "direct_llm_grade_row") as mocked:
            self.run_grader()
            first = self.read_rows()
            self.run_grader()
        mocked.assert_not_called()
        self.assertEqual([row["Grade Status"] for row in first], ["MISMATCH", "PARTIAL"])
        self.assertEqual(first[1], saved[1])
        self.assertEqual(first, self.read_rows())

    def test_recovered_pipeline_failure_gets_a_fresh_answer_grade(self):
        self.write_rows([self.row("recovered", status="FINAL_SPEC_ERROR")])
        with patch.object(grader, "direct_llm_grade_row") as mocked:
            self.run_grader()
        mocked.assert_not_called()
        self.write_rows([self.row("recovered", status="PIPELINE_SUCCESS")])
        with patch.object(grader, "direct_llm_grade_row", return_value={"status": "MATCH"}) as mocked:
            self.run_grader()
        mocked.assert_called_once()
        self.assertEqual(self.read_rows()[0]["Grade Status"], "MATCH")
        self.assertEqual(self.read_rows()[0]["Direct LLM Grading Path"], "direct_llm_semantic_judgment")

    def test_missing_required_report_columns_fail_before_grading(self):
        row = self.row()
        del row["New Pipeline Result"]
        self.write_rows([row])
        with patch.object(grader, "direct_llm_grade_row") as mocked:
            with self.assertRaisesRegex(ValueError, "missing required columns: New Pipeline Result"):
                self.run_grader()
        mocked.assert_not_called()
        self.assertFalse(self.output_path.exists())

    def test_blank_success_output_is_not_replaced_by_raw_data(self):
        self.write_rows([self.row(answer="")])
        with patch.object(grader, "direct_llm_grade_row") as mocked:
            self.run_grader()
        mocked.assert_not_called()
        self.assertEqual(self.read_rows()[0]["Grade Status"], "INVALID_PIPELINE_OUTPUT")

    def test_api_failure_preserves_execution_and_has_separate_grade_status(self):
        self.write_rows([self.row()])
        with patch.object(grader, "direct_llm_grade_row", side_effect=RuntimeError("rate limit exceeded")):
            self.run_grader()
        actual = self.read_rows()[0]
        self.assertEqual(actual["New Status"], "PIPELINE_SUCCESS")
        self.assertEqual(actual["Grade Status"], "RATE_LIMIT_ERROR")

    def test_resume_matches_input_after_reordering_but_regrades_changed_answer(self):
        first, second = self.row("a"), self.row("b", answer='[{"id": "b"}]')
        self.write_rows([first, second])
        with patch.object(grader, "direct_llm_grade_row", return_value={"status": "MATCH"}) as mocked:
            self.run_grader()
            self.write_rows([second, first])
            self.run_grader()
            self.assertEqual(mocked.call_count, 2)
            first["New Pipeline Result"] = '[{"id": "a"}]'
            self.write_rows([second, first])
            self.run_grader()
            self.assertEqual(mocked.call_count, 3)
            self.assertEqual(mocked.call_args.kwargs["final_answer"], first["New Pipeline Result"])

    def test_resume_regrades_when_model_changes(self):
        self.write_rows([self.row()])
        with patch.object(grader, "direct_llm_grade_row", return_value={"status": "MATCH"}) as mocked:
            self.run_grader("first-model")
            self.run_grader("second-model")
        self.assertEqual(mocked.call_count, 2)

    def test_resume_regrades_legacy_or_changed_policy_then_reuses_current_grade(self):
        self.write_rows([self.row()])
        with patch.object(grader, "direct_llm_grade_row", return_value={"status": "MATCH"}) as mocked:
            self.run_grader()
            for old_policy in (None, "strict_v1", "mc_diverse_extra_null_groups_v1"):
                with self.subTest(policy=old_policy):
                    saved = self.read_rows()[0]
                    if old_policy is None:
                        saved.pop("Grading Policy")
                    else:
                        saved["Grading Policy"] = old_policy
                    with self.output_path.open("w", encoding="utf-8", newline="") as handle:
                        writer = csv.DictWriter(handle, fieldnames=list(saved))
                        writer.writeheader()
                        writer.writerow(saved)
                    calls = mocked.call_count
                    self.run_grader()
                    self.assertEqual(mocked.call_count, calls + 1)
                    self.assertEqual(self.read_rows()[0]["Grading Policy"], grader.GRADING_POLICY_VERSION)
                    self.run_grader()
                    self.assertEqual(mocked.call_count, calls + 1)
            with patch.object(grader, "GRADING_POLICY_VERSION", "future_policy"):
                calls = mocked.call_count
                self.run_grader()
                self.assertEqual(mocked.call_count, calls + 1)

    def test_all_categories_and_filenames_receive_identical_grading_instructions(self):
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(choices=[
            SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=json.dumps({
                "status": "MATCH", "reason": "All required metrics match; extra unnamed label is harmless."
            })))
        ])
        answer = '[{"custom_label": "A", "metric": 10}, {"custom_label": null, "metric": 2}]'
        for category in ("ARC", "BSQ", "EC", "MC", "MC_diverse", "RC", "SQA", "TT", "WM"):
            with self.subTest(category=category):
                self.input_path = Path(self.temp.name) / f"{category}_v3.csv"
                self.output_path = Path(self.temp.name) / f"{category}_graded.csv"
                row = self.row(answer=answer)
                row.update({"Category": category, "Source CSV": f"{category}.csv",
                            "Question": "What is the metric for each named group?",
                            "Ground Truth": '[{"custom_label": "A", "metric": 10}]'})
                self.write_rows([row])
                original = self.input_path.read_bytes()
                self.run_grader(client=client)
                actual = self.read_rows()[0]
                self.assertEqual(actual["Grading Policy"], grader.GRADING_POLICY_VERSION)
                self.assertEqual(actual["New Pipeline Result"], answer)
                self.assertEqual(actual["Category"], category)
                self.assertEqual(self.input_path.read_bytes(), original)
        requests = client.chat.completions.create.call_args_list
        self.assertEqual(len(requests), 9)
        self.assertTrue(all(call.kwargs == requests[0].kwargs for call in requests))
        prompt = requests[0].kwargs["messages"][1]["content"]
        self.assertIn(answer, prompt)

    def test_nulls_do_not_rewrite_answers_or_override_semantic_verdicts(self):
        cases = [
            ("extra_label", '[{"label": "A", "value": 5}]',
             '[{"label": "A", "value": 5}, {"label": null, "value": 7}]', "MATCH"),
            ("missing_group", '[{"label": null, "value": 5}]', '[]', "MISMATCH"),
            ("null_metric", '[{"label": "A", "value": 0}]',
             '[{"label": "A", "value": null}]', "PARTIAL"),
            ("null_winner", '[{"label": "A", "value": 5}]',
             '[{"label": null, "value": 7}]', "MISMATCH"),
            ("literal_label", '[{"label": null, "value": 5}]',
             '[{"label": "Unknown", "value": 5}]', "PARTIAL"),
        ]
        rows = []
        for row_id, truth, answer, _ in cases:
            row = self.row(row_id, answer=answer)
            row["Ground Truth"] = truth
            rows.append(row)
        self.write_rows(rows)
        with patch.object(grader, "direct_llm_grade_row", side_effect=[
            {"status": status} for _, _, _, status in cases
        ]) as mocked:
            self.run_grader()
        self.assertEqual([r["Grade Status"] for r in self.read_rows()], [c[3] for c in cases])
        for call, (_, truth, answer, _) in zip(mocked.call_args_list, cases):
            self.assertEqual(call.kwargs["ground_truth"], truth)
            self.assertEqual(call.kwargs["final_answer"], answer)

    def test_authentication_failure_stops_calls_and_resumes_pending_rows(self):
        self.write_rows([self.row(str(i)) for i in range(4)])
        with patch.object(grader, "direct_llm_grade_row", side_effect=[
            {"status": "MATCH"}, RuntimeError("Error code: 401 invalid_api_key")
        ]) as mocked:
            with self.assertRaises(grader.GraderAuthenticationError):
                self.run_grader()
        self.assertEqual(mocked.call_count, 2)
        self.assertEqual([r["Grade Status"] for r in self.read_rows()],
                         ["MATCH", "AUTHENTICATION_ERROR", "PENDING_GRADING", "PENDING_GRADING"])
        with patch.object(grader, "direct_llm_grade_row", return_value={"status": "PARTIAL"}) as mocked:
            self.run_grader()
        self.assertEqual(mocked.call_count, 3)
        self.assertEqual(self.read_rows()[0]["Grade Status"], "MATCH")

    def test_authentication_stop_preserves_later_cached_grades(self):
        first, second = self.row("a"), self.row("b")
        self.write_rows([first, second])
        with patch.object(grader, "direct_llm_grade_row", return_value={"status": "MATCH"}):
            self.run_grader()
        first["New Pipeline Result"] = '[{"changed": 1}]'
        self.write_rows([first, second])
        with patch.object(grader, "direct_llm_grade_row", side_effect=RuntimeError("invalid_api_key")) as mocked:
            with self.assertRaises(grader.GraderAuthenticationError):
                self.run_grader()
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(self.read_rows()[1]["Grade Status"], "MATCH")

    def test_authentication_classification_uses_http_status(self):
        error = RuntimeError("Unauthorized")
        error.status_code = 401
        self.assertEqual(grader.classify_grader_exception(error), "AUTHENTICATION_ERROR")

    def test_batch_jobs_use_existing_terra_destinations(self):
        jobs = grader.report_jobs(True, self.temp.name, grader.DEFAULT_LLM_GRADER_MODEL)
        self.assertEqual(len(jobs), 3)
        self.assertEqual([Path(raw).name for raw, _ in jobs], list(grader.V4_BATCH_INPUTS))
        for raw, output in jobs:
            self.assertEqual(Path(output).name, f"graded_{Path(raw).stem}_terra.csv")

    def test_batch_dry_run_validates_all_files_without_client_or_writes(self):
        self.write_rows([self.row()])
        for name in grader.V4_BATCH_INPUTS:
            (Path(self.temp.name) / name).write_bytes(self.input_path.read_bytes())
        with patch.object(grader, "build_openai_grader_client") as client, patch.object(grader, "load_local_env_file"):
            grader.main(["--all-v4", "--output-dir", self.temp.name, "--dry-run"])
        client.assert_not_called()
        self.assertEqual(list(Path(self.temp.name).glob("graded_*.csv")), [])

    def test_mixed_status_rows_keep_all_grade_columns(self):
        self.write_rows([self.row("failure", status="FINAL_SPEC_ERROR"), self.row("success")])
        with patch.object(grader, "direct_llm_grade_row", return_value={"status": "MISMATCH", "reason": "Different records", "evidence": {"missing": ["x"]}}):
            self.run_grader()
        actual = self.read_rows()[1]
        self.assertEqual(actual["Grade Reason"], "Different records")
        self.assertIn('"missing": ["x"]', actual["Direct LLM Evidence"])
        self.assertEqual(actual["Grade Status"], "MISMATCH")


if __name__ == "__main__":
    unittest.main()
