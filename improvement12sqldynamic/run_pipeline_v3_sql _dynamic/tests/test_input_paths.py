"""Input isolation must hold across working directories and launcher children."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from support import SOURCE, load

paths = load("input_paths")


class InputPathTests(unittest.TestCase):
    def test_default_cli_ignores_stale_environment_from_another_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            environment = os.environ.copy()
            environment.update({key: str(SOURCE / "obsolete") for key in paths.INPUT_ENV_KEYS})
            result = subprocess.run([sys.executable, "-B", str(SOURCE / "run.py"), "--check-inputs"],
                                    cwd=folder, env=environment, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("8 tables", result.stdout)
        for _, key, filename in paths.INPUTS:
            self.assertIn(f"[INPUT] {key}: {SOURCE.parent / filename}", result.stdout)

    def test_replacement_documents_are_used_without_reading_database_schema(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "metadata").mkdir()
            (root / "metadata" / "items.yaml").write_text(
                "identity:\n  id: ReplacementItems\nattributes:\n  - name: label\n    type: string\n",
                encoding="utf-8")
            (root / "intro.prompt").write_text("Replacement domain.", encoding="utf-8")
            (root / "rules.md").write_text("Preserve duplicate labels.", encoding="utf-8")
            result = subprocess.run([sys.executable, "-B", str(SOURCE / "run.py"), "--check-inputs",
                                     "--db", "absent.db", "--yaml-dir", "metadata",
                                     "--domain-intro", "intro.prompt", "--business-rules", "rules.md"],
                                    cwd=root, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Validated 3 documents, 1 tables, 1 YAML table matches", result.stdout)

    def test_inputs_inside_package_are_rejected(self):
        for key in paths.INPUT_ENV_KEYS:
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "outside run_pipeline_v3_sql"):
                paths.resolve_input_paths({key: SOURCE / "old_inputs"})

    def test_child_arguments_preserve_all_replacement_paths(self):
        parser = argparse.ArgumentParser()
        paths.add_input_arguments(parser)
        with tempfile.TemporaryDirectory() as folder:
            arguments = []
            for option, _, filename in paths.INPUTS:
                arguments.extend(["--" + option, str(Path(folder) / filename)])
            args = parser.parse_args(arguments)
            child = parser.parse_args(paths.input_arguments(args))
            environment = {}
            paths.configure_input_paths(child, environment)
            self.assertEqual(environment, {key: str((Path(folder) / filename).resolve())
                                           for _, key, filename in paths.INPUTS})

    def test_credential_file_cannot_redirect_knowledge_or_database(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            env_file = root / "credentials.env"
            env_file.write_text("\n".join(f"{key}={SOURCE / 'obsolete'}" for key in paths.INPUT_ENV_KEYS)
                                + "\nINPUT_TEST_SETTING=loaded\n", encoding="utf-8")
            environment = {key: value for key, value in os.environ.items() if key not in paths.INPUT_ENV_KEYS}
            environment.update(PIPELINE_ENV_FILE=str(env_file), PIPELINE_OUTPUT_DIR=str(root),
                               REPORT_FILE=str(root / "report.csv"), PIPELINE_ENV_OVERRIDE="1")
            code = ("import sys, json, os; sys.path.insert(0, sys.argv[1]); "
                    "from _bootstrap import bootstrap; bootstrap(); "
                    "from run_pipeline_v3_sql import common; "
                    "print(json.dumps({key: getattr(common, key) for key in common.INPUT_ENV_KEYS})); "
                    "assert os.environ['INPUT_TEST_SETTING'] == 'loaded'")
            result = subprocess.run([sys.executable, "-B", "-c", code, str(SOURCE)],
                                    cwd=root, env=environment, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), paths.resolve_input_paths({}))
