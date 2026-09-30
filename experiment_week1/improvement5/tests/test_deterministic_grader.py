"""Offline regression checks for grading integrity, resume, and parallel output."""
import csv
import importlib.util
import json
import os
from decimal import Decimal
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


SOURCE = Path(__file__).resolve().parents[1] / "grade_openai_gpt_oss_120b_all_train.py"
SPEC = importlib.util.spec_from_file_location("_deterministic_grader_tests", SOURCE)
grader = importlib.util.module_from_spec(SPEC)
with patch.dict(os.environ):
    SPEC.loader.exec_module(grader)


class FakeHTTPError(Exception):
    def __init__(self, status_code):
        self.status_code = status_code
        super().__init__("rejected SECRET_MUST_NOT_BE_LOGGED")


def response(value, finish_reason="stop"):
    content = value if isinstance(value, str) else json.dumps(value)
    return SimpleNamespace(choices=[SimpleNamespace(
        finish_reason=finish_reason, message=SimpleNamespace(content=content)
    )])


def client_with(*replies):
    return SimpleNamespace(base_url="offline", chat=SimpleNamespace(
        completions=SimpleNamespace(create=Mock(side_effect=replies))
    ))


def contract(columns=None, identities=None, mode="row_set"):
    return {"required_columns": columns or ["n"], "identity_columns": identities or [],
            "comparison_mode": mode, "order_matters": mode == "ordered", "multiplicity_matters": False}


class ComparisonTests(unittest.TestCase):
    def compare(self, expected, actual, spec=None, mapping=None):
        return grader.deterministic_benchmark_status(
            json.dumps(expected), json.dumps(actual), spec or contract(), mapping
        )

    def test_rounds_only_once_through_full_comparison(self):
        result = self.compare([{"n": 49.25}], [{"n": 49.254604335202075}])
        self.assertEqual(result["status"], "MATCH")
        self.assertEqual(self.compare([{"n": 49.25}], [{"n": 49.2551}])["status"], "MISMATCH")

    def test_counts_and_large_integers_are_exact(self):
        for expected, actual in [(10, 11), (10.0, 10.1), (9007199254740992, 9007199254740993)]:
            with self.subTest(expected=expected):
                self.assertEqual(self.compare([{"n": expected}], [{"n": actual}])["status"], "MISMATCH")
        self.assertEqual(self.compare([{"n": 10}], [{"n": "10.0"}])["status"], "MATCH")

    def test_numeric_strings_and_scientific_precision_are_preserved(self):
        self.assertTrue(grader.benchmark_values_equal("0.00000012", "0.000000124"))
        self.assertFalse(grader.benchmark_values_equal("0.00000012", "0.00000013"))
        self.assertEqual(grader.normalize_benchmark_value("49.254604335202075"), Decimal("49.254604335202075"))
        self.assertEqual(grader.benchmark_decimal_precision(1.2e-7), 8)

    def test_null_labels_and_booleans_are_not_reinterpreted(self):
        for actual in ["NULL", "None", "Unknown", "", "4+ goals", 0]:
            self.assertFalse(grader.benchmark_values_equal(None, actual))
        self.assertFalse(grader.benchmark_values_equal(True, 1))
        self.assertFalse(grader.benchmark_values_equal(False, 0))
        self.assertEqual(self.compare([{"n": None}], [{}])["status"], "MISMATCH")

    def test_verified_count_alias_grades_matching_values(self):
        spec = contract(["sector", "allocation_record_count"], ["sector"], "grouped")
        expected = [{"sector": "Technology", "allocation_record_count": 13},
                    {"sector": "Pharma", "allocation_record_count": 2}]
        actual = [{"sector": "Pharma", "record_count": 2}, {"sector": "Technology", "record_count": 13}]
        client = client_with(response(spec))
        result = grader.grade_json_result_deterministically("Count records by sector", json.dumps(expected), json.dumps(actual), client, "offline")
        self.assertEqual(result["status"], "MATCH")
        self.assertEqual(result["column_mapping_status"], "heuristic_column_alignment")
        self.assertEqual(client.chat.completions.create.call_count, 1)
        actual[0]["record_count"] = 3
        mapping = {"record_count": "allocation_record_count"}
        self.assertNotEqual(self.compare(expected, actual, spec, mapping)["status"], "MATCH")

    def test_alias_does_not_reuse_a_required_source_column(self):
        spec = contract(["holding_count", "negative_holding_count"])
        mapping = grader.infer_heuristic_column_mapping(spec, ["holding_count"])
        self.assertEqual(mapping, {})

    def test_unknown_and_conflicting_mappings_are_rejected(self):
        for mapping in [{"wrong": "n"}, {"actual": "invented"}, {"actual": 1},
                        {"actual": "n", "other": "n"}]:
            with self.subTest(mapping=mapping), self.assertRaises(grader.GraderOutputError):
                grader.validate_column_mapping(mapping, ["actual", "other"], ["n"])
        with self.assertRaises(grader.GraderOutputError):
            grader.validate_column_mapping({"actual": "n"}, ["actual", "n"], ["n"])

    def test_grouping_order_and_missing_values_are_still_checked(self):
        spec = contract(["group", "n"], ["group"], "ordered")
        expected = [{"group": "A", "n": 1}, {"group": "B", "n": 2}]
        self.assertNotEqual(self.compare(expected, expected[::-1], spec)["status"], "MATCH")
        self.assertNotEqual(self.compare(expected, [{"group": "A"}], spec)["status"], "MATCH")

    def test_truncated_reference_handling_is_unchanged(self):
        reference = json.dumps({"rows": [{"n": 1}], "_included_rows": 1, "_total_rows": 10})
        client = client_with()
        result = grader.grade_pipeline_result("test", reference, '[{"n":1}]', "", client, "offline")
        self.assertEqual(result["status"], "OTHER")
        self.assertEqual(result["grading_path"], "truncated_ground_truth_wrapper")
        client.chat.completions.create.assert_not_called()


class HelperTests(unittest.TestCase):
    def test_authentication_and_rate_limit_failures_propagate(self):
        for code in [401, 403, 429, 500]:
            with self.subTest(code=code), self.assertRaises(grader.GraderAPIError) as caught:
                grader.infer_grading_contract("count", '[{"n":1}]', client_with(FakeHTTPError(code)), "offline")
            self.assertEqual(caught.exception.authentication_failed, code in {401, 403})
            self.assertNotIn("SECRET_MUST_NOT_BE_LOGGED", str(caught.exception))

    def test_invalid_requirement_output_never_falls_back_to_all_columns(self):
        invalid = ["not JSON", {}, contract(["invented"]), contract(["n"], ["other"]),
                   {**contract(), "order_matters": "false"}, {**contract(), "required_columns": []},
                   contract(["n"], [], "grouped")]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(grader.GraderOutputError):
                grader.infer_grading_contract("count", '[{"n":1}]', client_with(response(value)), "offline")

    def test_valid_contract_keeps_filter_only_columns_out(self):
        spec = contract(["investor_id"], ["investor_id"])
        result = grader.infer_grading_contract("Which investors exceed the threshold?",
            '[{"investor_id":"INV-1","investor_name":"Test","value":100}]', client_with(response(spec)), "offline")
        self.assertEqual(result, spec)

    def test_truncated_helper_response_is_an_error(self):
        with self.assertRaises(grader.GraderOutputError):
            grader.infer_grading_contract("count", '[{"n":1}]', client_with(response(contract(), "length")), "offline")

    def test_mapper_failure_and_retry_failure_propagate(self):
        for replies in [(FakeHTTPError(401),), (response({"column_mapping": {}}), FakeHTTPError(401))]:
            with self.subTest(replies=replies), self.assertRaises(grader.GraderAPIError):
                grader.infer_column_mapping("count", contract(), '[{"n":1}]', '[{"actual":1}]', {}, client_with(*replies), "offline")

    def test_invalid_mapper_output_and_fabricated_columns_are_errors(self):
        for replies in [(response("bad"), response("bad")),
                        (response({"column_mapping": {"absent": "n"}}),),
                        (response({"column_mapping": {"actual_pipeline_column": "ground_truth_column"}}),) * 2]:
            with self.subTest(replies=replies), self.assertRaises(grader.GraderOutputError):
                grader.infer_column_mapping("count", contract(), '[{"n":1}]', '[{"actual":1}]', {}, client_with(*replies), "offline")

    def test_valid_mapper_alias_reaches_comparison(self):
        client = client_with(response(contract()), response({"column_mapping": {"actual": "n"}}))
        result = grader.grade_json_result_deterministically("count", '[{"n":1}]', '[{"actual":1}]', client, "offline")
        self.assertEqual(result["status"], "MATCH")

    def test_partial_helper_mapping_preserves_verified_aliases(self):
        spec = contract(["sector", "allocation_record_count", "custom_metric"], ["sector"], "grouped")
        client = client_with(response(spec), response({"column_mapping": {"calculation": "custom_metric"}}))
        expected = '[{"sector":"A","allocation_record_count":2,"custom_metric":7}]'
        actual = '[{"sector":"A","record_count":2,"calculation":7}]'
        result = grader.grade_json_result_deterministically("Counts and metric by sector", expected, actual, client, "offline")
        self.assertEqual(result["status"], "MATCH")
        self.assertEqual(result["column_mapping"]["validated_column_mapping"],
                         {"record_count": "allocation_record_count", "calculation": "custom_metric"})

    def test_valid_empty_mapping_is_distinct_from_api_failure(self):
        client = client_with(response(contract()), response({"column_mapping": {}}), response({"column_mapping": {}}))
        result = grader.grade_json_result_deterministically("count", '[{"n":1}]', '[{"unrelated":1}]', client, "offline")
        self.assertEqual(result["status"], "MISMATCH")
        self.assertEqual(result["column_mapping_status"], "column_mapping_unresolved")


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.input = self.directory / "input.csv"
        self.output = self.directory / "new" / "graded.csv"
        self.rows = [self.row("q1"), self.row("q2")]
        self.write(self.rows)
        self.client = SimpleNamespace(base_url="offline")

    def row(self, identity):
        return {"Sample Row ID": identity, "Question": identity, "Ground Truth": '[{"n":1}]',
                "New Pipeline Result": '[{"n":1}]', "New Status": "PIPELINE_SUCCESS"}

    def write(self, rows, path=None):
        path = path or self.input
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def read(self):
        with self.output.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    def run_grader(self, model="offline"):
        return grader.regrade_existing_report(str(self.input), str(self.output), self.client, model)

    def success(self):
        return {"status": "MATCH", "grading_path": "offline-test", "reason": "test"}

    def test_authentication_failure_saves_once_and_stops(self):
        self.client = client_with(FakeHTTPError(401))
        with self.assertRaisesRegex(RuntimeError, "Run stopped"):
            self.run_grader()
        self.assertEqual(self.client.chat.completions.create.call_count, 1)
        saved = self.read()
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["New Status"], "GRADER_AUTH_ERROR")
        self.assertNotIn("SECRET_MUST_NOT_BE_LOGGED", self.output.read_text())
        self.assertFalse(Path(str(self.output) + ".lock").exists())

    def test_non_authentication_failures_have_distinct_retryable_status(self):
        error = grader.GraderAPIError("Requirement_Analyzer", FakeHTTPError(429))
        with patch.object(grader, "grade_pipeline_result", side_effect=[error, self.success()]):
            self.run_grader()
        self.assertEqual([r["New Status"] for r in self.read()], ["GRADER_API_ERROR", "MATCH"])
        with patch.object(grader, "grade_pipeline_result", return_value=self.success()) as call:
            self.run_grader()
            self.assertEqual(call.call_count, 1)

    def test_invalid_output_is_not_other_or_mismatch(self):
        with patch.object(grader, "grade_pipeline_result", side_effect=grader.GraderOutputError("Invalid contract")):
            self.run_grader()
        self.assertEqual({r["New Status"] for r in self.read()}, {"GRADER_OUTPUT_ERROR"})

    def test_reordered_rows_resume_by_id_without_calls(self):
        with patch.object(grader, "grade_pipeline_result", return_value=self.success()):
            self.run_grader()
        self.write(self.rows[::-1])
        with patch.object(grader, "grade_pipeline_result") as call:
            self.run_grader()
            call.assert_not_called()
        self.assertEqual([r["Sample Row ID"] for r in self.read()], ["q2", "q1"])

    def test_changed_question_reference_answer_and_status_invalidate_only_changed_row(self):
        with patch.object(grader, "grade_pipeline_result", return_value=self.success()):
            self.run_grader()
        for field in ["Question", "Ground Truth", "New Pipeline Result", "New Status"]:
            self.rows[0][field] += " changed"
            self.write(self.rows)
            with self.subTest(field=field), patch.object(grader, "grade_pipeline_result", return_value=self.success()) as call:
                self.run_grader()
                self.assertEqual(call.call_count, 1)

    def test_model_policy_code_and_endpoint_changes_invalidate_resume(self):
        with patch.object(grader, "grade_pipeline_result", return_value=self.success()):
            self.run_grader()
        for attribute in ["GRADER_POLICY_VERSION", "GRADER_CODE_SHA256"]:
            with self.subTest(attribute=attribute), patch.object(grader, attribute, "changed"), patch.object(grader, "grade_pipeline_result", return_value=self.success()) as call:
                self.run_grader()
                self.assertEqual(call.call_count, 2)
        with patch.object(grader, "grade_pipeline_result", return_value=self.success()) as call:
            self.run_grader("new-model")
            self.assertEqual(call.call_count, 2)
        self.client.base_url = "other-endpoint"
        with patch.object(grader, "grade_pipeline_result", return_value=self.success()) as call:
            self.run_grader("new-model")
            self.assertEqual(call.call_count, 2)

    def test_legacy_unversioned_results_are_not_reused(self):
        old = [{**r, "New Status": "MISMATCH", "Final Grading Path": "requirement_llm -> column_mapper_failed -> deterministic_final"} for r in self.rows]
        self.write(old, self.output)
        with patch.object(grader, "grade_pipeline_result", return_value=self.success()) as call:
            self.run_grader()
            self.assertEqual(call.call_count, 2)

    def test_duplicate_or_missing_ids_are_rejected_before_calls(self):
        for rows in [[self.rows[0], self.rows[0]], [{**self.rows[0], "Sample Row ID": ""}]]:
            self.write(rows)
            with patch.object(grader, "grade_pipeline_result") as call, self.assertRaises(ValueError):
                self.run_grader()
            call.assert_not_called()

    def test_source_cannot_be_overwritten(self):
        with self.assertRaises(ValueError):
            grader.regrade_existing_report(str(self.input), str(self.input), self.client)

    def test_preserves_execution_failures_without_semantic_grading(self):
        self.rows[0]["New Status"] = "FINAL_SPEC_ERROR"
        self.write(self.rows)
        with patch.object(grader, "grade_pipeline_result", return_value=self.success()) as call:
            self.run_grader()
            self.assertEqual(call.call_count, 1)
        self.assertEqual(self.read()[0]["New Status"], "FINAL_SPEC_ERROR")

    def test_atomic_replace_failure_preserves_previous_file(self):
        self.output.parent.mkdir(parents=True)
        self.output.write_text("original", encoding="utf-8")
        with patch.object(grader.os, "replace", side_effect=OSError("locked")), self.assertRaises(OSError):
            with grader.atomic_output(str(self.output)) as handle:
                handle.write("new content")
        self.assertEqual(self.output.read_text(), "original")
        self.assertEqual(list(self.output.parent.glob(".grader-*.tmp")), [])

    def test_concurrent_writer_is_blocked_and_lock_is_released(self):
        with grader.report_lock(str(self.output)):
            with self.assertRaisesRegex(RuntimeError, "locked"):
                self.run_grader()
        self.assertFalse(Path(str(self.output) + ".lock").exists())

    def test_future_valid_rows_survive_an_authentication_stop(self):
        with patch.object(grader, "grade_pipeline_result", return_value=self.success()):
            self.run_grader()
        self.rows[0]["Question"] = "changed"
        self.write(self.rows)
        with patch.object(grader, "grade_pipeline_result", side_effect=grader.GraderAPIError("test", FakeHTTPError(401))), self.assertRaises(RuntimeError):
            self.run_grader()
        self.assertEqual([r["New Status"] for r in self.read()], ["GRADER_AUTH_ERROR", "MATCH"])

    def test_logs_have_unique_names_and_atomic_valid_json(self):
        with patch.object(grader, "OUTPUT_DIR", str(self.directory)):
            first, second = grader.APILogger(), grader.APILogger()
        self.assertNotEqual(first.log_file, second.log_file)
        first.log_call("test", "Requirement_Analyzer")
        first.save()
        second.save()
        self.assertEqual(json.loads(Path(first.log_file).read_text())["test"]["total_calls"], 1)
        self.assertEqual(json.loads(Path(second.log_file).read_text()), {})


if __name__ == "__main__":
    unittest.main()
