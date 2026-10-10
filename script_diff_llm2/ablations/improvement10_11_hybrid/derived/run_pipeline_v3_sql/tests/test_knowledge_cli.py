"""Knowledge preparation has no interactive approval command."""
import subprocess
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from support import SOURCE, load


class KnowledgeCliTests(unittest.TestCase):
    def test_help_offers_preparation_without_approval(self):
        result = subprocess.run([sys.executable, "-B", str(SOURCE / "run.py"), "--help"],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--prepare-knowledge", result.stdout)
        self.assertIn("--knowledge-mode", result.stdout)
        self.assertIn("improvement7", result.stdout)
        self.assertNotIn("--approve-knowledge", result.stdout)

    def test_dedicated_script_help_without_model_calls(self):
        result = subprocess.run([sys.executable, "-B", str(SOURCE / "prepare_knowledge.py"), "--help"],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--yaml-dir", result.stdout)
        self.assertIn("--business-rules", result.stdout)
        self.assertNotIn("source copy", result.stdout)

    def test_script_forwards_inputs_and_clears_selected_cache(self):
        preparation = load("prepare_knowledge")
        with patch.dict(preparation.os.environ, {"KNOWLEDGE_CACHE_FILE": "old.json"}), \
                patch.object(preparation.subprocess, "run", return_value=SimpleNamespace(returncode=7)) as run:
            result = preparation.main(["--env-file", "credentials.env", "--yaml-dir", "custom yaml"])
            self.assertEqual(result, 7)
            arguments = run.call_args.args[0]
            self.assertEqual(arguments[4:7], ["--prepare-knowledge", "--knowledge-mode", "simple"])
            self.assertEqual(arguments[7:], ["--env-file", "credentials.env", "--yaml-dir", "custom yaml"])
            self.assertEqual(run.call_args.kwargs["env"]["KNOWLEDGE_CACHE_FILE"], "")
            self.assertEqual(preparation.os.environ["KNOWLEDGE_CACHE_FILE"], "old.json")

    def test_creation_script_rejects_cache_selection(self):
        preparation = load("prepare_knowledge")
        with patch.object(preparation.subprocess, "run") as run:
            for arguments in (["--knowledge-cache", "old.json"], ["--knowledge-cache=old.json"]):
                with self.assertRaisesRegex(SystemExit, "creates a cache"):
                    preparation.main(arguments)
            run.assert_not_called()
