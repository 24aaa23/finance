"""Error-only retry selection, resume and launcher routing; no live API calls."""

import contextlib
import csv
import importlib
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from support import load


class QuerySpecRetryTests(unittest.TestCase):
    def test_portable_resume_reads_category_jsonl_with_actual_dataset_count(self):
        runner = importlib.import_module("run_pipeline_v3_sql.scripts.resume_442")
        from run_pipeline_v3_sql.run_identity import sha256_file
        questions = self.source.parent / "input_questions.jsonl"
        questions.write_text("\n".join(json.dumps({"global_question_id": str(i)}) for i in range(5)), encoding="utf-8")
        database = self.root / "test.db"
        database.write_bytes(b"local database")
        Path(str(self.source) + ".manifest.json").write_text(json.dumps({"input_files": {
            "questions": {"sha256": sha256_file(questions)}, "sqlite_database": {"sha256": sha256_file(database)}}}), encoding="utf-8")
        _, _, pending, expected, new_count = runner.selection(self.source, questions, database)
        self.assertEqual(expected, 5)
        self.assertEqual([row["Sample Row ID"] for row in pending], ["4"])
        self.assertEqual(new_count, 1)
        with patch.object(runner.subprocess, "run") as call, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main(["--type", "benchmark", "--output-root", str(self.root),
                "--report-name", self.source.name, "--db", str(database), "--dry-run"]), 0)
            call.assert_not_called()
    def test_resume_442_launcher_dry_run_and_original_input_hash_guard(self):
        runner = importlib.import_module("run_pipeline_v3_sql.scripts.resume_442")
        from run_pipeline_v3_sql.run_identity import sha256_file
        dataset = self.root / "dataset"
        dataset.mkdir()
        questions = dataset / "WM.csv"
        questions.write_text("global_question_id\n0\n1\n2\n3\n4\n", encoding="utf-8")
        database = self.root / "test.db"
        database.write_bytes(b"original database")
        manifest = {"input_files": {"questions": {"sha256": sha256_file(questions)},
                                   "sqlite_database": {"sha256": sha256_file(database)}}}
        Path(str(self.source) + ".manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        argv = ["--type", "benchmark", "--output-root", str(self.root),
                "--report-name", self.source.name, "--questions-root", str(dataset), "--db", str(database)]
        before = self.source.read_bytes()
        with patch.object(runner.subprocess, "run") as call, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main(argv + ["--dry-run"]), 0)
            call.assert_not_called()
            self.assertEqual(self.source.read_bytes(), before)
            database.write_bytes(b"changed database")
            with self.assertRaisesRegex(ValueError, "sqlite_database changed"):
                runner.main(argv)
            call.assert_not_called()
        self.assertEqual(list(self.source.parent.glob("backup_before_retry_*")), [])

    def test_resume_crashes_selects_only_service_failures_and_missing_ids(self):
        module = load("retry_batch")
        statuses = ["PIPELINE_SUCCESS", "CRASH", "TRANSIENT_ERROR", "QUOTA_EXHAUSTED",
                    "EXECUTION_ERROR", "FINAL_SPEC_ERROR", "QUERY_SPEC_ERROR"]
        saved = [{"Sample Row ID": str(i), "New Status": status} for i, status in enumerate(statuses)]
        source = [{"Sample Row ID": str(i)} for i in range(9)]
        self.assertEqual([row["Sample Row ID"] for row in module.crash_and_pending_records(saved, source)],
                         ["1", "2", "3", "7", "8"])
        self.assertEqual([row["New Status"] for row in saved], statuses)

    def test_resume_rejects_duplicate_or_foreign_ids(self):
        select = load("retry_batch").crash_and_pending_records
        with self.assertRaises(ValueError):
            select([], [{"Sample Row ID": "1"}] * 2)
        with self.assertRaises(ValueError):
            select([{"Sample Row ID": "foreign", "New Status": "CRASH"}], [{"Sample Row ID": "1"}])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "benchmark" / "raw_pipeline_v9.csv"
        self.source.parent.mkdir()
        self.retry_dir = self.source.parent / "query_spec_retry"
        self.module = load("retry_batch")
        self.rows = [{"Sample Row ID": str(index), "Question": "Read records",
                      "Ground Truth": '[{"text":"' + "x" * 70000 + '"}]', "New Status": status}
                     for index, status in enumerate(["PIPELINE_SUCCESS", "QUERY_SPEC_ERROR", "SCAN_ERROR", "QUERY_SPEC_ERROR"])]
        self.write_source()

    def write_source(self):
        with self.source.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(self.rows[0]))
            writer.writeheader()
            writer.writerows(self.rows)

    def test_only_saved_query_spec_errors_are_selected_and_original_preserved(self):
        before = self.source.read_bytes()
        path, count = self.module.prepare_query_spec_retry(self.source, self.retry_dir)
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(count, 2)
        self.assertEqual([r["Sample Row ID"] for r in records], ["1", "3"])
        self.assertEqual(records[0]["Ground Truth"], self.rows[1]["Ground Truth"])
        self.assertEqual(self.source.read_bytes(), before)
        self.assertTrue(records[0]["Retry Source SHA256"])
        frozen = path.read_bytes()
        self.rows.append({**self.rows[1], "Sample Row ID": "new"})
        self.write_source()
        self.assertEqual(self.module.prepare_query_spec_retry(self.source, self.retry_dir)[1], 2)
        self.assertEqual(path.read_bytes(), frozen)

    def test_no_errors_does_not_create_a_retry_run(self):
        self.rows = [self.rows[0]]
        self.write_source()
        path, count = self.module.prepare_query_spec_retry(self.source, self.retry_dir)
        self.assertEqual(count, 0)
        self.assertFalse(path.exists())

    def test_resume_retries_only_query_spec_and_keeps_unfinished_rows(self):
        records = [dict(row) for row in self.rows]
        self.assertEqual(self.module.completed_retry_ids(records), {"0", "2"})
        self.module.replace_retry_result(records, {**records[1], "New Status": "PIPELINE_SUCCESS"})
        self.assertEqual(len(records), 4)
        self.assertEqual(records[3]["New Status"], "QUERY_SPEC_ERROR")
        self.assertEqual(self.module.completed_retry_ids(records), {"0", "1", "2"})

    def test_duplicate_ids_are_rejected(self):
        self.rows.append(dict(self.rows[1]))
        self.write_source()
        with self.assertRaisesRegex(ValueError, "unique"):
            self.module.prepare_query_spec_retry(self.source, self.retry_dir)

    def test_in_place_selection_keeps_successes_and_unrecognized_statuses(self):
        self.rows += [{**self.rows[0], "Sample Row ID": str(index + 10), "New Status": status}
                      for index, status in enumerate(["FINAL_SPEC_ERROR", "QUERY_UNDERSTANDING_ERROR", "MISMATCH", ""])]
        self.write_source()
        fields, rows = self.module.read_retry_report(self.source)
        self.assertEqual(rows, self.rows)
        self.assertEqual(fields, list(self.rows[0]))
        selected = self.module.failed_retry_rows(rows)
        self.assertEqual([r["Sample Row ID"] for r in selected], ["1", "2", "3", "10", "11"])

    def test_in_place_backup_and_mixed_provenance_allow_code_changes(self):
        previous = {"run_identity": "old_code", "input_files": {
            "questions": {"sha256": "questions"}, "sqlite_database": {"sha256": "database"}}}
        manifest_path = Path(str(self.source) + ".manifest.json")
        manifest_path.write_text(json.dumps(previous), encoding="utf-8")
        debug = self.source.with_name("raw_pipeline_v9_debug.csv")
        debug.write_text("original debug", encoding="utf-8")
        before = self.source.read_bytes()
        result = self.module.prepare_in_place_retry(self.source, {**previous, "run_identity": "new_code"}, ["1", "2", "3"], [debug])
        backup = Path(result["retry_history"][-1]["backup_directory"])
        self.assertEqual((backup / self.source.name).read_bytes(), before)
        self.assertEqual((backup / debug.name).read_text(), "original debug")
        self.assertEqual(json.loads((backup / manifest_path.name).read_text()), previous)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertTrue(result["mixed_results"])
        self.assertEqual(result["retry_history"][-1]["selected_ids"], ["1", "2", "3"])
        self.assertEqual(json.loads(manifest_path.read_text()), result)

    def test_in_place_changed_database_or_questions_is_rejected_before_backup(self):
        previous = {"run_identity": "old", "input_files": {
            "questions": {"sha256": "q"}, "sqlite_database": {"sha256": "db"}}}
        manifest_path = Path(str(self.source) + ".manifest.json")
        manifest_path.write_text(json.dumps(previous), encoding="utf-8")
        for name in ("questions", "sqlite_database"):
            changed = {**previous, "input_files": {**previous["input_files"], name: {"sha256": "changed"}}}
            with self.assertRaisesRegex(ValueError, "unchanged"):
                self.module.prepare_in_place_retry(self.source, changed, ["1"])
        self.assertEqual(list(self.source.parent.glob("backup_before_retry_*")), [])
        self.assertEqual(json.loads(manifest_path.read_text()), previous)

    def test_in_place_launcher_targets_existing_csv_and_restores_feature_switches(self):
        runner = importlib.import_module("run_pipeline_v3_sql.scripts.retry_failed_in_place")
        db, env_file = self.root / "test.db", self.root / "empty.env"
        db.touch()
        env_file.touch()
        (self.source.parent / "input_questions.jsonl").write_text("{}", encoding="utf-8")
        Path(str(self.source) + ".manifest.json").write_text(json.dumps({"configuration": {
            "query_understanding": True, "contract_checks": True, "agent_consultation": False}}), encoding="utf-8")
        argv = ["--type", "benchmark", "--output-root", str(self.root), "--db", str(db), "--env-file", str(env_file)]
        with patch.object(runner.subprocess, "run", return_value=types.SimpleNamespace(returncode=0)) as run:
            self.assertEqual(runner.main(argv + ["--dry-run"]), 0)
            run.assert_not_called()
            self.assertEqual(runner.main(argv), 0)
        command = run.call_args.args[0]
        self.assertIn("--retry-errors-in-place", command)
        self.assertEqual(Path(command[command.index("--output") + 1]).resolve(), self.source.resolve())
        self.assertEqual(command[command.index("--agent-consultation") + 1], "off")
        self.assertEqual(Path(run.call_args.kwargs["env"]["RESULT_JSONL_FILE"]).resolve(), self.source.with_suffix(".jsonl").resolve())

    def test_in_place_launcher_finds_external_dataset_by_hash_and_rejects_changes(self):
        runner = importlib.import_module("run_pipeline_v3_sql.scripts.retry_failed_in_place")
        dataset = self.root / "dataset"
        dataset.mkdir()
        original = dataset / "original.csv"
        original.write_text("Question,Ground Truth\nRead records,[]\n", encoding="utf-8")
        (dataset / "unrelated.csv").write_text("different cohort", encoding="utf-8")
        digest = load("run_identity").sha256_file(original)
        Path(str(self.source) + ".manifest.json").write_text(json.dumps({"configuration": {},
            "input_files": {"questions": {"sha256": digest}}}), encoding="utf-8")
        db, env_file = self.root / "test.db", self.root / "empty.env"
        db.touch()
        env_file.touch()
        argv = ["--type", "benchmark", "--output-root", str(self.root), "--db", str(db),
                "--env-file", str(env_file)]
        with patch.object(runner, "EXPERIMENT_DIR", self.root), \
             patch.object(runner.subprocess, "run", return_value=types.SimpleNamespace(returncode=0)) as run:
            self.assertEqual(runner.main(argv + ["--dry-run"]), 0)
            run.assert_not_called()
            self.assertEqual(runner.main(argv), 0)
            command = run.call_args.args[0]
            self.assertEqual(Path(command[command.index("--questions") + 1]).resolve(), original.resolve())
            original.write_text("modified cohort", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as rejected:
                runner.main(argv + ["--dry-run"])
            self.assertEqual(rejected.exception.code, 2)

    def test_launcher_uses_retry_manifest_and_separate_reports_without_workbook(self):
        experiment = Path(__file__).resolve().parents[2]
        with patch.object(sys, "path", [str(experiment), *sys.path]):
            runner = importlib.import_module("run_pipeline_v3_sql.scripts.run_question_types_v2")
            guard = importlib.import_module("run_pipeline_v3_sql.runtime_guard")
        env_file = self.root / "empty.env"
        env_file.write_text("", encoding="utf-8")
        argv = ["runner", "--type", "Benchmark", "--output-root", str(self.root),
                "--env-file", str(env_file), "--db", str(self.root / "test.db"), "--retry-query-spec-errors"]
        with patch.object(sys, "argv", argv), patch.object(guard, "report_lock", side_effect=lambda path: contextlib.nullcontext()), \
             patch.object(runner.subprocess, "run", return_value=types.SimpleNamespace(returncode=0)) as run, \
             patch.object(runner, "prepare_question_type_manifests") as workbook:
            runner.main()
        workbook.assert_not_called()
        run.assert_called_once()
        environment = run.call_args.kwargs["env"]
        self.assertEqual(Path(environment["INPUT_QUERY_FILE"]).resolve(), (self.retry_dir / "input_questions.jsonl").resolve())
        self.assertEqual(Path(environment["REPORT_FILE"]).resolve(), (self.retry_dir / "raw_pipeline_v9.csv").resolve())
        self.assertEqual(environment["RETRY_QUERY_SPEC_ERRORS_ONLY"], "1")
