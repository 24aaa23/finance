"""Knowledge preparation has no interactive approval command."""
import subprocess
import sys
import unittest

from support import SOURCE


class KnowledgeCliTests(unittest.TestCase):
    def test_help_offers_preparation_without_approval(self):
        result = subprocess.run([sys.executable, "-B", str(SOURCE / "run.py"), "--help"],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--prepare-knowledge", result.stdout)
        self.assertNotIn("--approve-knowledge", result.stdout)
