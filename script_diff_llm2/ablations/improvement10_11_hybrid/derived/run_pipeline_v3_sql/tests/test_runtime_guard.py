import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from support import SOURCE

from run_pipeline_v3_sql import runtime_guard as guard


class RuntimeGuardTests(unittest.TestCase):
    def test_separate_reports_can_run_together_and_same_report_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(guard, "RUNTIME_DIR", Path(tmp)):
            with guard.report_lock(Path(tmp) / "first.csv"):
                with guard.report_lock(Path(tmp) / "second.csv"):
                    pass
                with self.assertRaisesRegex(RuntimeError, "writing this report"):
                    with guard.report_lock(Path(tmp) / "first.csv"):
                        self.fail("Duplicate writer acquired the lock")

    def test_crashed_process_releases_report_lock(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(guard, "RUNTIME_DIR", Path(tmp)):
            code = (
                "import sys,time; from pathlib import Path; "
                "from _bootstrap import bootstrap; bootstrap(); "
                "from run_pipeline_v3_sql import runtime_guard as g; "
                "g.RUNTIME_DIR=Path(sys.argv[1]); "
                "ctx=g.report_lock(Path(sys.argv[1])/'test.csv'); ctx.__enter__(); "
                "print('ready',flush=True); time.sleep(30)"
            )
            child = subprocess.Popen(
                [sys.executable, "-c", code, tmp], cwd=SOURCE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            try:
                self.assertEqual(child.stdout.readline().strip(), "ready")
                with self.assertRaises(RuntimeError):
                    with guard.report_lock(Path(tmp) / "test.csv"):
                        pass
            finally:
                child.kill()
                child.communicate(timeout=10)
            with guard.report_lock(Path(tmp) / "test.csv"):
                pass

    def test_waits_for_both_physical_and_commit_headroom(self):
        with patch.object(guard, "available_memory_mb", side_effect=[
            (127, 4096), (1024, 1023), (1024, 4096),
        ]), patch.object(guard.time, "sleep") as sleep, patch.object(guard, "progress") as progress:
            guard.wait_for_memory()
        self.assertEqual(sleep.call_count, 2)
        self.assertIn("[PAUSED]", progress.call_args_list[0].args[0])
        self.assertIn("resuming", progress.call_args_list[-1].args[0])

    def test_launcher_import_does_not_load_pandas(self):
        script = SOURCE / "scripts/run_question_types_v2.py"
        code = (
            "import runpy,sys; runpy.run_path(sys.argv[1],run_name='inspect_launcher'); "
            "assert 'pandas' not in sys.modules; "
            "import os; assert os.environ['OPENBLAS_NUM_THREADS']=='1'"
        )
        completed = subprocess.run([sys.executable, "-c", code, str(script)],
                                   capture_output=True, text=True, timeout=20)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    @unittest.skipUnless(os.name == "nt", "Windows memory API")
    def test_real_memory_probe(self):
        physical, commit = guard.available_memory_mb()
        self.assertGreater(physical, 0)
        self.assertGreater(commit, 0)


if __name__ == "__main__":
    unittest.main()
