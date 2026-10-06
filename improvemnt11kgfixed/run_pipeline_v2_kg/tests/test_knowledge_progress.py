import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from support import load
from test_knowledge_and_understanding import DOCS, SCHEMA, PACK

progress_module = load("knowledge_progress")
knowledge = load("knowledge")


class KnowledgeProgressTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {"DOMAIN_COMPILATION_MODE": "improvement7"})
        environment.start()
        self.addCleanup(environment.stop)

    def test_wrapped_complete_responses_preserve_citation_text(self):
        obj = {"rules": [{"text": '<think>literal source text</think> "quoted"\npath \\ value'}]}
        encoded = json.dumps(obj)
        for response in (encoded, '\ufeff' + encoded,
                         '<think>Reasoning with {example}</think>\n' + encoded,
                         '<reasoning>Thinking</reasoning>\n<thought>More</thought>\n```JSON\n' + encoded + '\n```',
                         'Here is the rule pack:\n```json\n' + encoded + '\n```\nDone.',
                         'Here is the result:\n' + encoded + '\nDone.'):
            with self.subTest(response=response):
                self.assertEqual(progress_module.parse_complete_pack(response), obj)

    def test_no_recovery_of_partial_ambiguous_or_invalid_json(self):
        for response in ('{"rules": [{"id":"K1"}',
                         'Here is JSON: {"rules": [{"id":"K1"},',
                         '{"rules": []} {"rules": [1]}',
                         '<think>Unclosed reasoning {"rules": []}',
                         '```json\n{"rules": []}',
                         '[{"rules": []}]',
                         '{"rules": [],}',
                         '{"text":"bad\\q"}',
                         '{"text":"unescaped\nnewline"}'):
            with self.subTest(response=response), self.assertRaises(ValueError):
                progress_module.parse_complete_pack(response)
        with self.assertRaisesRegex(ValueError, r"line 1, column"):
            progress_module.parse_complete_pack('{"rules": [],}')

    def test_bad_json_is_saved_and_precise_error_is_sent_on_retry(self):
        from types import SimpleNamespace
        attempts = []
        invalid = '{"rules": [],}'
        def create(**request):
            attempts.append(request)
            content = invalid if len(attempts) == 1 else '<think>Inspect documents</think>\n' + json.dumps(PACK)
            return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=content))])
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with tempfile.TemporaryDirectory() as folder, patch.object(progress_module.sys, "__stdout__", io.StringIO()):
            pack, _ = knowledge.compile_knowledge(DOCS, SCHEMA, client, "offline", Path(folder) / "cache")
            self.assertEqual(pack, PACK)
            files = list((Path(folder) / "logs").glob("*.rejected.json"))
            self.assertEqual(len(files), 1)
            saved = json.loads(files[0].read_text())
            self.assertEqual(saved["content"], invalid)
            self.assertIn("line 1, column", saved["error"])
            self.assertIn("line 1, column", json.loads(attempts[1]["messages"][1]["content"])["validation_feedback"])
            self.assertIn("one valid JSON object", attempts[0]["messages"][0]["content"])

    def test_rejects_nested_fragment_of_truncated_response(self):
        with self.assertRaisesRegex(ValueError, "complete JSON"):
            progress_module.parse_complete_pack('{"rules": [{"id": "K1"},')
        self.assertEqual(progress_module.parse_complete_pack('```json\n{"rules": []}\n```'), {"rules": []})

    def test_waiting_reports_liveness_and_stops_on_failure(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(progress_module.sys, "__stdout__", io.StringIO()):
            progress = progress_module.KnowledgeProgress(Path(folder) / "cache", interval=0.01)
            signaled = threading.Event()
            original = progress.emit

            def emit(event, message, **details):
                original(event, message, **details)
                if event == "waiting":
                    signaled.set()

            with patch.object(progress, "emit", side_effect=emit):
                with self.assertRaisesRegex(RuntimeError, "private details"):
                    with progress.waiting(1):
                        self.assertTrue(signaled.wait(2))
                        raise RuntimeError("private details")
            text = progress.path.read_text()
            events = [json.loads(line)["event"] for line in text.splitlines()]
            self.assertIn("waiting", events)
            self.assertEqual(events[-1], "request_failed")
            self.assertNotIn("private details", text)
            self.assertFalse(any(t.name == "knowledge-progress" for t in threading.enumerate()))

    def test_truncated_response_retries_before_accepting_complete_pack(self):
        from types import SimpleNamespace
        attempts = []

        def create(**request):
            attempts.append(request)
            return SimpleNamespace(choices=[SimpleNamespace(
                finish_reason="length" if len(attempts) == 1 else "stop",
                message=SimpleNamespace(content=json.dumps(PACK)))])

        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with tempfile.TemporaryDirectory() as folder, patch.object(progress_module.sys, "__stdout__", io.StringIO()):
            pack, identity = knowledge.compile_knowledge(DOCS, SCHEMA, client, "offline", Path(folder) / "cache")
            self.assertEqual(pack, PACK)
            self.assertEqual(len(attempts), 2)
            self.assertIn("output limit", attempts[1]["messages"][1]["content"])
            logs = list((Path(folder) / "logs").glob("knowledge_*.jsonl"))
            records = [json.loads(line) for line in logs[0].read_text().splitlines()]
            self.assertIn("validation_failed", [r["event"] for r in records])
            self.assertEqual(records[-1]["event"], "saved")
            self.assertTrue((Path(folder) / "cache" / (identity + ".json")).is_file())
