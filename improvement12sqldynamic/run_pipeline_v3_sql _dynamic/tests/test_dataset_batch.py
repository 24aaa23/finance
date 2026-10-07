import json
import csv
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from support import SOURCE

from run_pipeline_v3_sql.dataset_batch import prepare_question_type_manifests, question_type_slug
from run_pipeline_v3_sql.reporting import write_jsonl_atomic


class DatasetBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_prepare_manifest_uses_full_json_answer_and_sheet_folder(self):
        workbook = self.root / "questions.xlsx"
        frame = pd.DataFrame([{
            "global_question_id": "batch:Q-1", "question_id": "Q-1", "question": "List all records.",
            "ground_truth_answer": '{"_truncated_to": 50}', "query_type": "Filtered List",
        }])
        with pd.ExcelWriter(workbook) as writer:
            frame.to_excel(writer, sheet_name="Benchmark", index=False)
        answers = self.root / "answers.json"
        answers.write_text(json.dumps({"Q-1": [{"id": 1}, {"id": 2}]}), encoding="utf-8")

        manifests = prepare_question_type_manifests(workbook, answers, self.root / "output", ["Benchmark"])
        manifest = manifests["Benchmark"]
        record = json.loads(manifest.read_text(encoding="utf-8").strip())
        self.assertEqual(manifest.parent.name, "benchmark")
        self.assertEqual(record["dataset_type"], "Benchmark")
        self.assertEqual(record["ground_truth_source"], "full_answer_json")
        self.assertEqual(json.loads(record["ground_truth_answer"]), [{"id": 1}, {"id": 2}])
        with (manifest.parent / "input_questions.csv").open(encoding="utf-8", newline="") as handle:
            archived = next(csv.DictReader(handle))
        self.assertEqual(archived["Sample Row ID"], "batch:Q-1")
        self.assertEqual(json.loads(archived["Ground Truth"]), [{"id": 1}, {"id": 2}])
        original = manifest.read_bytes()
        answers.write_text(json.dumps({"Q-1": [{"id": 999}]}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Inputs changed"):
            prepare_question_type_manifests(workbook, answers, self.root / "output", ["Benchmark"])
        self.assertEqual(manifest.read_bytes(), original)

    def test_slug_and_jsonl_report_keep_large_values(self):
        self.assertEqual(question_type_slug("At-Risk Critical"), "at_risk_critical")
        output = self.root / "result.jsonl"
        large_answer = json.dumps([{"value": "x" * 40000}])
        write_jsonl_atomic(output, [{"Ground Truth": large_answer, "New Pipeline Result": large_answer}])
        record = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(record["pipeline_result_json"][0]["value"], "x" * 40000)


if __name__ == "__main__":
    unittest.main()
