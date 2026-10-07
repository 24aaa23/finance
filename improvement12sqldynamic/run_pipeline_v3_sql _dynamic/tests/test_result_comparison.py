import importlib.util
from pathlib import Path
import unittest
import tempfile
import csv

path = Path(__file__).resolve().parents[1] / "scripts" / "compare_results.py"
spec = importlib.util.spec_from_file_location("result_comparison", path)
comparison = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)


class ComparisonTests(unittest.TestCase):
    def test_reads_this_experiments_direct_grader_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            category = Path(directory) / "benchmark"
            category.mkdir()
            report = category / "graded_pipeline.csv"
            with report.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["Sample Row ID", "New Status", "Direct LLM Grading Path"])
                writer.writeheader()
                writer.writerow({"Sample Row ID": "1", "New Status": "MATCH", "Direct LLM Grading Path": "direct_llm_semantic_judgment"})
            result = comparison.read_results(Path(directory))
            self.assertEqual(result["1"]["Grade Status"], "MATCH")
    def test_pairing_uses_ids_and_excludes_unpaired_rows_from_accuracy(self):
        a = {"1": {"Grade Status": "MATCH"}, "2": {"Grade Status": "MATCH"}, "3": {"Grade Status": "MATCH"}}
        b = {"2": {"Grade Status": "PARTIAL"}, "1": {"Grade Status": "MATCH"}}
        result = comparison.compare(a, b)
        self.assertEqual(result["both_correct"], 1)
        self.assertEqual(result["paraphrased_match_pct"], 50)
        self.assertEqual(result["only_normal"], 1)
        self.assertEqual(result["regression_ids"], ["2"])
