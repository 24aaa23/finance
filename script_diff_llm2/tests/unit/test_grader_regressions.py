import importlib.util
import unittest
from pathlib import Path


def _load_grader_module():
    repo_root = Path(__file__).resolve().parents[2]
    grader_path = repo_root / "historical_models" / "openai.gpt-oss-120b-aman" / "all" / "train" / "grade_openai_gpt_oss_120b_all_train.py"
    spec = importlib.util.spec_from_file_location("gpt_oss_grader", grader_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


grader = _load_grader_module()


class GraderRegressionTest(unittest.TestCase):
    def test_parse_benchmark_json_payload_unwraps_rows_wrapper(self):
        wrapped = '{"rows":[{"investor_id":"INV-001"}],"_included_rows":1,"_total_rows":1,"_full_result_sha256":"x"}'
        ok, rows, meta = grader.parse_benchmark_json_payload(wrapped)
        self.assertTrue(ok)
        self.assertEqual(rows, [{"investor_id": "INV-001"}])
        self.assertTrue(meta["wrapped_rows"])
        self.assertFalse(meta["truncated"])

    def test_truncated_ground_truth_wrapper_is_marked_other(self):
        ground_truth = (
            '{"rows":[{"investor_id":"INV-001","investor_name":"Arjun"}],'
            '"_included_rows":50,"_total_rows":990,"_full_result_sha256":"x"}'
        )
        actual = '[{"investor_id":"INV-001","investor_name":"Arjun"}]'
        result = grader.grade_pipeline_result(
            "Which investors satisfy the query?",
            ground_truth,
            actual,
            actual,
            client=None,
            model="stub",
        )
        self.assertEqual(result["status"], "OTHER")
        self.assertEqual(result["grading_path"], "truncated_ground_truth_wrapper")
        self.assertTrue(result["deterministic_evidence"]["truncated_ground_truth"])

    def test_list_values_are_normalized_hashably(self):
        normalized = grader.normalize_benchmark_value(["INV-001", "INV-002"])
        self.assertEqual(normalized, ("inv001", "inv002"))
        key = grader.build_identity_key({"related_ids": ["INV-001", "INV-002"]}, ["related_ids"])
        self.assertEqual(key, (("inv001", "inv002"),))

    def test_index_rows_by_identity_accepts_list_identity_values(self):
        rows = [
            {"related_ids": ["INV-001", "INV-002"], "score": 1},
            {"related_ids": ["INV-003"], "score": 2},
        ]
        indexed, missing = grader.index_rows_by_identity(rows, ["related_ids"])
        self.assertFalse(missing)
        self.assertEqual(len(indexed), 2)


if __name__ == "__main__":
    unittest.main()
