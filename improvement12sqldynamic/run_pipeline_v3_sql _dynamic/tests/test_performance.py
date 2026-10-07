import json
import csv
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from support import load

performance = load("performance")


class PerformanceTests(unittest.TestCase):
    def test_csv_accounting_repeated_saves_and_resume_keep_unique_safe_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "_telemetry"
            for index in range(2):
                timing = performance.RunTiming()
                timing.enable_output_records(folder)
                client = timing.client(SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
                    create=lambda **request: SimpleNamespace(usage={"prompt_tokens": 10, "completion_tokens": 2})))))
                with timing.question("q" + str(index)):
                    client.chat.completions.create(model="offline", messages=[{"content": "PRIVATE_PROMPT"}])
                timing.save(root / "summary.json", "completed")
                timing.save(root / "summary.json", "completed")
            with (root / "model_calls.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(len({row["call_id"] for row in rows}), 2)
            self.assertEqual({row["query_id"] for row in rows}, {"q0", "q1"})
            self.assertNotIn("PRIVATE_PROMPT", (root / "model_calls.csv").read_text())
            with (folder / (timing.run_id + ".questions.csv")).open(encoding="utf-8", newline="") as handle:
                self.assertEqual(next(csv.DictReader(handle))["query_id"], "q1")
    def test_output_events_survive_failure_without_summary_and_do_not_leak_prompts(self):
        with tempfile.TemporaryDirectory() as folder:
            timing = performance.RunTiming()
            timing.enable_output_records(Path(folder) / "_telemetry", mode="pipeline")
            def create(**kwargs):
                raise TimeoutError("PRIVATE_ERROR")
            client = timing.client(SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
            with self.assertRaises(TimeoutError), timing.question("q1"):
                client.chat.completions.create(model="offline", messages=[{"content": "PRIVATE_PROMPT"}])
            text = timing.events_path.read_text()
            records = [json.loads(line) for line in text.splitlines()]
            self.assertEqual([r["event"] for r in records],
                             ["run_started", "question_started", "call_started", "call_finished", "question_finished"])
            self.assertEqual(records[2]["call_id"], records[3]["call_id"])
            self.assertEqual(records[3]["status"], "error")
            self.assertEqual(records[3]["model"], "offline")
            self.assertNotIn("PRIVATE", text)
            self.assertFalse(timing.output_summary_path.exists())
            timing.save(Path(folder) / "runtime.json", "failed")
            summary = json.loads(timing.output_summary_path.read_text())
            self.assertEqual(summary["run_id"], timing.run_id)
            self.assertEqual(len(summary["llm_calls"]), 1)

    def test_per_question_metrics_exclude_startup_and_keep_missing_usage_unknown(self):
        timing = performance.RunTiming()
        timing.llm_calls.append({"status": "success", "model": "offline", "seconds": 100,
                                 "prompt_tokens": 1000, "completion_tokens": 1000})
        timing.llm_calls.extend([
            {"status": "success", "model": "offline", "seconds": 2,
             "prompt_tokens": 100, "completion_tokens": 20, "cached_prompt_tokens": 50},
            {"status": "success", "model": "offline", "seconds": 3,
             "prompt_tokens": 200, "completion_tokens": 40, "cached_prompt_tokens": 0},
        ])
        metrics = timing.report_metrics(1)
        self.assertEqual(metrics["Generation Input Tokens"], 300)
        self.assertEqual(metrics["Generation Output Tokens"], 60)
        self.assertEqual(metrics["Generation Latency Seconds"], 5)
        self.assertEqual(metrics["Cached Input Tokens"], 50)
        self.assertEqual(metrics["Model Calls"], 2)
        timing.llm_calls.append({"status": "error", "model": "offline", "seconds": 4})
        metrics = timing.report_metrics(1)
        self.assertIsNone(metrics["Generation Input Tokens"])
        self.assertIsNone(metrics["Generation Output Tokens"])
        self.assertEqual(metrics["Generation Latency Seconds"], 9)
        self.assertEqual(metrics["Calls Missing Token Usage"], 1)
        self.assertEqual(metrics["Failed Model Calls"], 1)

    def test_wall_clock_accounts_for_startup_waits_io_and_finalization(self):
        now = [10.0]
        timing = performance.RunTiming(started=0.0, clock=lambda: now[0])
        timing.ready()
        with timing.question("new-row") as question:
            with timing.stage("memory_wait"):
                now[0] += 3
            with timing.stage("Scan"):
                now[0] += 5
            question["processing_seconds"] = 5
            with timing.stage("report_writes"):
                now[0] += 2
        now[0] += 4
        timing.metadata["resumed_rows"] = 100
        snapshot = timing.snapshot("completed")
        self.assertEqual(snapshot["wall_clock_seconds"], 24)
        self.assertEqual(snapshot["startup_seconds"], 10)
        self.assertEqual(snapshot["current_run_query_seconds"], 5)
        self.assertEqual(snapshot["current_run_cycle_seconds"], 10)
        self.assertEqual(len(snapshot["questions"]), 1)
        self.assertEqual(snapshot["questions"][0]["llm_calls"], 0)

    def test_request_latency_includes_internal_retries_and_reports_usage(self):
        now = [0.0]
        timing = performance.RunTiming(clock=lambda: now[0])
        usage = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
                 "prompt_tokens_details": {"cached_tokens": 80}}
        response = SimpleNamespace(usage=usage)
        received = []

        def create(**kwargs):
            received.append(kwargs)
            now[0] += 7  # SDK request, including any internal retries/backoff.
            return response

        client = timing.client(SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
        request = {"model": "offline", "messages": [{"role": "user", "content": "PRIVATE_PROMPT"}]}
        with timing.question("q1"):
            with timing.stage("Query_Spec"):
                self.assertIs(client.chat.completions.create(**request), response)
        self.assertEqual(received, [request])
        call = timing.llm_calls[0]
        self.assertEqual((call["stage"], call["seconds"], call["cached_prompt_tokens"]), ("Query_Spec", 7, 80))
        self.assertEqual(timing.questions[0]["llm_seconds"], 7)
        self.assertNotIn("PRIVATE_PROMPT", json.dumps(timing.snapshot("completed")))

    def test_failed_calls_are_measured_and_original_error_propagates(self):
        now = [0.0]
        timing = performance.RunTiming(clock=lambda: now[0])

        def create(**kwargs):
            now[0] += 9
            raise TimeoutError("PRIVATE_ERROR")

        client = timing.client(SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
        with self.assertRaises(TimeoutError), timing.stage("Domain"):
            client.chat.completions.create(messages=[])
        self.assertEqual(timing.llm_calls[0]["seconds"], 9)
        self.assertEqual(timing.llm_calls[0]["status"], "error")
        self.assertEqual(timing.stage_name.get(), "unattributed")
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "timing.json"
            timing.save(path, "failed")
            data = json.loads(path.read_text())
            self.assertEqual(data["status"], "failed")
            self.assertNotIn("PRIVATE_ERROR", path.read_text())

    def test_missing_cache_token_usage_remains_unknown(self):
        timing = performance.RunTiming()
        response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=10))
        client = timing.client(SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: response))))
        client.chat.completions.create(messages=[])
        self.assertIsNone(timing.llm_calls[0]["cached_prompt_tokens"])
        self.assertEqual(timing.llm_calls[0]["prompt_tokens"], 10)

    def test_delay_rejects_nonfinite_and_negative_values(self):
        for value in ("-1", "nan", "inf", "-inf"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                performance.query_delay(value)
        self.assertEqual(performance.query_delay("0"), 0)
        self.assertEqual(performance.query_delay("0.25"), 0.25)

    def test_business_prompt_is_cached_without_losing_or_mutating_rules(self):
        context = load("business_context")
        original = context.load_business_rule_pack()
        try:
            pack = {"rules": [{"id": "K1", "text": "Keep signed values.", "fields": []}]}
            context.configure_business_context(pack)
            prompt = context.business_context_prompt()
            self.assertEqual(json.loads(prompt), pack)
            self.assertIs(prompt, context.business_context_prompt())
            pack["rules"].clear()
            context.load_business_rule_pack()["rules"].clear()
            self.assertTrue(json.loads(context.business_context_prompt())["rules"])
            context.configure_business_context({"rules": []})
            self.assertEqual(json.loads(context.business_context_prompt()), {"rules": []})
        finally:
            context.configure_business_context(original)
