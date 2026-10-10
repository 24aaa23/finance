import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "scripts" / "compare_results.py"
spec = importlib.util.spec_from_file_location("result_comparison", path)
comparison = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)


class ComparisonTests(unittest.TestCase):
    def test_pairing_uses_ids_and_excludes_unpaired_rows_from_accuracy(self):
        a = {"1": {"Grade Status": "MATCH"}, "2": {"Grade Status": "MATCH"}, "3": {"Grade Status": "MATCH"}}
        b = {"2": {"Grade Status": "PARTIAL"}, "1": {"Grade Status": "MATCH"}}
        result = comparison.compare(a, b)
        self.assertEqual(result["both_correct"], 1)
        self.assertEqual(result["paraphrased_match_pct"], 50)
        self.assertEqual(result["only_normal"], 1)
        self.assertEqual(result["regression_ids"], ["2"])
