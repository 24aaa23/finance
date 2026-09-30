"""Offline checks for the direct grader's narrow unnamed-group exception."""
import copy
import csv
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "grade_openai_gpt_oss_120b_all_train_direct_llm_gpt_5_6_TERA.py"
SPEC = importlib.util.spec_from_file_location("_direct_mc_null_grader_tests", SOURCE)
grader = importlib.util.module_from_spec(SPEC)
with patch.dict(os.environ):
    SPEC.loader.exec_module(grader)


class NullPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.input_path = Path(self.temp.name) / "MC_diverse_v2_graded.csv"
        self.output_path = Path(self.temp.name) / "new" / "null_policy.csv"
        self.reference = [{"group_value": "Moderate", "metric": 12.34}]
        self.answer = [{"riskTolerance": "Moderate", "average": 12.3401},
                       {"riskTolerance": None, "average": 99}]

    def candidate(self, question="For each risk tolerance, show the average return."):
        return grader.null_group_candidate(question, json.dumps(self.reference), json.dumps(self.answer))

    def row(self, row_id="MC-244", category="Multi-step comparative (diverse)"):
        return {"Sample Row ID": row_id, "Category": category,
                "Question": "For each risk tolerance, show the average return.",
                "Ground Truth": json.dumps(self.reference), "New Pipeline Result": json.dumps(self.answer),
                "New Status": "PARTIAL", "Comparison / Comments": "Only the extra null group is wrong.",
                "Direct LLM Evidence": json.dumps({"main_missing_or_wrong_parts": ["Extra null group"]}),
                "Direct LLM Grading Path": "direct_llm_semantic_judgment", "Direct LLM Grader Model": "test"}

    def approved(self):
        return {"status": "MATCH", "reason": "Named groups and values are correct.", "evidence": {},
                "null_policy_checks": {key: True for key in grader.NULL_REVIEW_CHECKS}}

    def write(self, rows, path=None):
        path = path or self.input_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def read(self):
        with self.output_path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    def run_grader(self, model="test"):
        grader.regrade_existing_report(str(self.input_path), str(self.output_path), object(), model)

    def test_only_mc_diverse_uses_policy(self):
        self.assertTrue(grader.is_mc_diverse(self.row(), "mixed.csv"))
        self.assertTrue(grader.is_mc_diverse({}, "MC_diverse_v2.csv"))
        self.assertFalse(grader.is_mc_diverse(self.row(category="Multi-step comparative"), str(self.input_path)))
        self.assertFalse(grader.is_mc_diverse({}, "MC_v2.csv"))
        self.assertFalse(grader.is_mc_diverse(self.row(category="Temporal"), "TT_v2.csv"))

    def test_candidate_preserves_answer_and_reports_only_null_labels(self):
        original = copy.deepcopy(self.answer)
        self.assertEqual(self.candidate(), {"group_field": "riskTolerance", "row_indices": [1]})
        self.assertEqual(self.answer, original)

    def test_required_null_group_is_not_ignored(self):
        self.reference.append({"group_value": None, "metric": 99})
        self.assertIsNone(self.candidate())

    def test_missing_winner_and_missing_named_group_are_not_excused(self):
        self.answer = self.answer[1:]
        self.assertIsNone(self.candidate("Which risk tolerance has the highest return?"))
        self.assertIsNone(self.candidate())

    def test_top_k_and_overall_questions_stay_strict(self):
        for question in ("Show the top 5 risk groups.", "Which risk group has the highest return?",
                         "Compare each group with the overall average across all investors.",
                         "Show missing groups and their averages."):
            with self.subTest(question=question):
                self.assertIsNone(self.candidate(question))

    def test_literal_null_strings_are_not_treated_as_json_null(self):
        for label in ("NULL", "None", "Unknown", ""):
            with self.subTest(label=label):
                self.answer[1]["riskTolerance"] = label
                self.assertIsNone(self.candidate())

    def test_duplicate_or_extra_named_groups_are_not_excused(self):
        for label in ("Moderate", "Aggressive"):
            with self.subTest(label=label):
                self.answer.append({"riskTolerance": label, "average": 10})
                self.assertIsNone(self.candidate())
                self.answer.pop()

    def test_missing_group_key_does_not_count_as_null(self):
        del self.answer[1]["riskTolerance"]
        self.assertIsNone(self.candidate())

    def test_segment_label_alias_is_supported(self):
        self.answer = [{"segment_label": row["riskTolerance"], "average": row["average"]} for row in self.answer]
        self.assertEqual(self.candidate()["group_field"], "segment_label")

    def test_truncated_prompt_cannot_approve_adjustment(self):
        answer = json.dumps(self.answer)
        self.assertIsNone(grader.null_group_candidate("Show groups", json.dumps(self.reference), answer + " " * 60000))

    def test_malformed_and_empty_answers_stay_strict(self):
        for answer in ("bad json", "{}", "[]", '[null]'):
            with self.subTest(answer=answer):
                self.assertIsNone(grader.null_group_candidate("Show groups", json.dumps(self.reference), answer))

    def test_upgrade_preserves_original_grade_and_original_data(self):
        source = self.row()
        self.write([source])
        before = self.input_path.read_bytes()
        with patch.object(grader, "direct_llm_grade_row", return_value=self.approved()) as mocked:
            self.run_grader()
        result = self.read()[0]
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(mocked.call_args.kwargs["scan_raw_rows"], source["New Pipeline Result"])
        self.assertEqual(result["New Status"], "MATCH")
        self.assertEqual(result["Original Grade"], "PARTIAL")
        self.assertEqual(result["Original Grade Evidence"], source["Direct LLM Evidence"])
        self.assertEqual(result["Null Policy Status"], "adjusted")
        self.assertEqual(result["New Pipeline Result"], source["New Pipeline Result"])
        self.assertEqual(before, self.input_path.read_bytes())

    def test_match_without_all_boolean_checks_cannot_upgrade(self):
        for bad_value in (False, "true", 1, None):
            with self.subTest(bad_value=bad_value):
                row = self.row(str(bad_value))
                self.write([row])
                review = self.approved()
                review["null_policy_checks"]["named_metrics_correct"] = bad_value
                with patch.object(grader, "direct_llm_grade_row", return_value=review):
                    self.run_grader()
                self.assertEqual(self.read()[0]["New Status"], "PARTIAL")
                self.assertEqual(self.read()[0]["Null Policy Status"], "retained")

    def test_wrong_metric_and_ordering_stay_partial(self):
        for check in ("named_metrics_correct", "ordering_correct", "no_population_or_denominator_effect"):
            with self.subTest(check=check):
                self.write([self.row(check)])
                review = self.approved()
                review["null_policy_checks"][check] = False
                with patch.object(grader, "direct_llm_grade_row", return_value=review):
                    self.run_grader()
                self.assertEqual(self.read()[0]["New Status"], "PARTIAL")

    def test_null_metric_in_named_group_is_sent_to_reviewer_unchanged(self):
        self.answer[0]["average"] = None
        row = self.row()
        self.write([row])
        review = self.approved()
        review["null_policy_checks"]["named_metrics_correct"] = False
        with patch.object(grader, "direct_llm_grade_row", return_value=review) as mocked:
            self.run_grader()
        self.assertIsNone(json.loads(mocked.call_args.kwargs["scan_raw_rows"])[0]["average"])
        self.assertEqual(self.read()[0]["New Status"], "PARTIAL")

    def test_raw_input_gets_strict_grade_before_null_review(self):
        row = self.row()
        row["New Status"] = "PIPELINE_SUCCESS"
        self.write([row])
        with patch.object(grader, "direct_llm_grade_row", side_effect=[
            {"status": "PARTIAL", "reason": "Extra null group.", "evidence": {}}, self.approved()
        ]) as mocked:
            self.run_grader()
        self.assertEqual(mocked.call_count, 2)
        self.assertNotIn("null_review", mocked.call_args_list[0].kwargs)
        self.assertIn("null_review", mocked.call_args_list[1].kwargs)
        self.assertEqual(self.read()[0]["Original Grade"], "PARTIAL")

    def test_mc_and_tt_do_not_get_null_review(self):
        for category in ("Multi-step comparative", "Temporal"):
            with self.subTest(category=category):
                self.write([self.row(category=category)])
                with patch.object(grader, "direct_llm_grade_row") as mocked:
                    self.run_grader()
                mocked.assert_not_called()
                self.assertEqual(self.read()[0]["New Status"], "PARTIAL")
                self.assertEqual(self.read()[0]["Grading Policy"], "strict_v1")

    def test_initial_match_needs_no_review(self):
        row = self.row()
        row["New Status"] = "MATCH"
        self.write([row])
        with patch.object(grader, "direct_llm_grade_row") as mocked:
            self.run_grader()
        mocked.assert_not_called()
        self.assertEqual(self.read()[0]["Original Grade"], "MATCH")

    def test_changed_model_regrades_instead_of_reusing_old_verdict(self):
        self.write([self.row()])
        with patch.object(grader, "direct_llm_grade_row", return_value={"status": "MATCH", "reason": "Reviewed.", "evidence": {}}) as mocked:
            self.run_grader("different_model")
        self.assertEqual(mocked.call_count, 1)
        self.assertNotIn("null_review", mocked.call_args.kwargs)
        self.assertEqual(self.read()[0]["Direct LLM Grader Model"], "different_model")

    def test_legacy_output_does_not_skip_policy_review(self):
        row = self.row()
        self.write([row])
        self.write([row], self.output_path)
        with patch.object(grader, "direct_llm_grade_row", return_value=self.approved()) as mocked:
            self.run_grader()
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(self.read()[0]["Original Grade"], "PARTIAL")

    def test_raw_review_failure_reuses_successful_strict_grade_on_retry(self):
        row = self.row()
        row["New Status"] = "PIPELINE_SUCCESS"
        self.write([row])
        with patch.object(grader, "direct_llm_grade_row", side_effect=[
            {"status": "PARTIAL", "reason": "Strict baseline.", "evidence": {}}, RuntimeError("rate limit")
        ]):
            self.run_grader()
        with patch.object(grader, "direct_llm_grade_row", return_value=self.approved()) as mocked:
            self.run_grader()
        self.assertEqual(mocked.call_count, 1)
        self.assertIn("null_review", mocked.call_args.kwargs)
        self.assertEqual(self.read()[0]["Original Grade Reason"], "Strict baseline.")

    def test_resume_uses_input_identity_and_policy_not_row_position(self):
        a, b = self.row("a"), self.row("b")
        self.write([a, b])
        with patch.object(grader, "direct_llm_grade_row", return_value=self.approved()) as mocked:
            self.run_grader()
            self.write([b, a])
            self.run_grader()
            self.assertEqual(mocked.call_count, 2)
            a["New Pipeline Result"] = a["New Pipeline Result"].replace("12.3401", "12.3402")
            self.write([b, a])
            self.run_grader()
            self.assertEqual(mocked.call_count, 3)
            with patch.object(grader, "NULL_POLICY_VERSION", "new_policy"):
                self.run_grader()
            self.assertEqual(mocked.call_count, 5)

    def test_review_failure_keeps_strict_grade_and_retries(self):
        row = self.row()
        self.write([row])
        with patch.object(grader, "direct_llm_grade_row", side_effect=RuntimeError("rate limit")):
            self.run_grader()
        first = self.read()[0]
        self.assertEqual(first["New Status"], "PARTIAL")
        self.assertEqual(first["Null Policy Status"], "review_error")
        with patch.object(grader, "direct_llm_grade_row", return_value=self.approved()) as mocked:
            self.run_grader()
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(self.read()[0]["New Status"], "MATCH")

    def test_in_place_output_is_rejected(self):
        self.write([self.row()])
        with self.assertRaisesRegex(ValueError, "separate output"):
            grader.regrade_existing_report(str(self.input_path), str(self.input_path), object(), "test")

    def test_review_prompt_requires_full_answer_and_original_verdict(self):
        calls = []

        def create(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=json.dumps(self.approved())))])

        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        row = self.row()
        grader.direct_llm_grade_row(row["Question"], row["Ground Truth"], row["New Pipeline Result"], client, "test",
                                    null_review={"original_grade": {"status": "PARTIAL"}})
        prompt = calls[0]["messages"][1]["content"]
        self.assertIn("COMPLETE, UNMODIFIED", prompt)
        self.assertIn(row["New Pipeline Result"], prompt)
        self.assertIn("wrong populations", prompt)
        self.assertIn("null_policy_checks", prompt)


if __name__ == "__main__":
    unittest.main()
