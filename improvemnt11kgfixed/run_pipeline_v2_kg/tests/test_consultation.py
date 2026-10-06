import importlib
import json
import unittest
from unittest.mock import patch

from support import FakeClient, load

c = importlib.import_module("run_pipeline_v2_kg.consultation")


class ConsultationTests(unittest.TestCase):
    def session(self):
        return c.ConsultationSession("List accounts", {}, [], {"rules": []}, None, "offline", {}, limit=5)

    def test_default_has_no_consultation_cap_across_operators(self):
        session = c.ConsultationSession("List accounts", {}, [], {"rules": []}, None, "offline", {})
        with patch.object(c, "consult_domain", return_value=[]) as domain, \
             patch.object(c, "understand_query", return_value={}) as understanding:
            for index in range(12):
                replies = iter([
                    {"consultation_request": {"agent": "domain" if index % 2 == 0 else "query_understanding",
                                              "topic": "population"}},
                    {"finished": True},
                ])
                def operator(inputs):
                    self.assertTrue(inputs["agent_consultation_available"])
                    return next(replies)
                result = session.run("Query_Spec" if index % 2 == 0 else "Final_Spec", operator, {})
                self.assertEqual(result, {"finished": True})
        self.assertIsNone(session.remaining)
        self.assertEqual(domain.call_count + understanding.call_count, 12)
        self.assertFalse(any(entry["status"] == "budget_exhausted" for entry in session.log))

    def test_disabled_prompt_is_unchanged(self):
        self.assertEqual(c.consultation_prompt({}), "")

    def test_planning_operators_return_explicit_requests_before_plan_validation(self):
        request = {"consultation_request": {"agent": "domain", "topic": "metric_definition"}}
        for module, function in (("decompose", "semantic_decompose_question"),
                                 ("query_spec", "semantic_build_query_spec"),
                                 ("final_spec", "semantic_build_final_spec")):
            with self.subTest(operator=module):
                client = FakeClient(request)
                result = getattr(load("llm_operators." + module), function)(
                    {"query": "List accounts", "agent_consultation_enabled": True,
                     "agent_consultation_available": True}, client, "offline")
                self.assertEqual(result, request)
                self.assertIn('"consultation_request"', client.calls[0]["messages"][0]["content"])

    def test_normal_operator_does_not_call_specialist(self):
        session = self.session()
        result = session.run("Final_Spec", lambda inputs: {"final_spec": {}}, {})
        self.assertEqual(result, {"final_spec": {}})
        self.assertEqual(session.log, [])
        self.assertEqual(session.remaining, 5)

    def test_bounded_requests_across_operator_retries(self):
        session = self.session()
        request = lambda inputs: {"consultation_request": {"agent": "domain", "topic": "population"}}
        with patch.object(c, "consult_domain", return_value=[{"text": "Approved rule"}]) as domain:
            result = session.run("Query_Spec", request, {})
            session.run("Query_Spec", request, {})
        self.assertEqual(domain.call_count, 5)
        self.assertIn("contract_errors", result["query_spec"])
        self.assertEqual(session.remaining, 0)

    def test_free_text_and_extra_payload_rejected_before_specialist(self):
        session = self.session()
        result = session.run("Decompose", lambda inputs: {"consultation_request": {
            "agent": "domain", "topic": "population", "rows": "ROW_SECRET"}}, {})
        self.assertTrue(result["selected_decomposition"]["contract_errors"])
        self.assertNotIn("ROW_SECRET", json.dumps(session.log))
        self.assertEqual(session.remaining, 5)

    def test_five_requests_shared_between_specialists_and_operators(self):
        session = self.session()
        with patch.object(c, "consult_domain", return_value=[]) as domain, \
             patch.object(c, "understand_query", return_value={}) as understanding:
            for index in range(5):
                responses = iter([
                    {"consultation_request": {"agent": "domain" if index % 2 == 0 else "query_understanding",
                                              "topic": "population"}},
                    {"finished": True},
                ])
                result = session.run("Decompose" if index % 2 == 0 else "Final_Spec",
                                     lambda inputs: next(responses), {})
                self.assertEqual(result, {"finished": True})
            result = session.run("Query_Spec", lambda inputs: {
                "consultation_request": {"agent": "query_understanding", "topic": "population"}}, {})
        self.assertEqual(domain.call_count, 3)
        self.assertEqual(understanding.call_count, 2)
        self.assertEqual(session.remaining, 0)
        self.assertTrue(result["query_spec"]["contract_errors"])

    def test_unavailable_specialist_keeps_original_context(self):
        session = self.session()
        def operator(inputs):
            if not inputs["agent_consultation_context"]:
                return {"consultation_request": {"agent": "domain", "topic": "population"}}
            return {"final_spec": {"projection": ["id"]}}
        with patch.object(c, "consult_domain", side_effect=ValueError("Uncited rule")):
            self.assertIn("final_spec", session.run("Final_Spec", operator, {}))
        self.assertEqual(session.log[0]["status"], "unavailable")

    def test_revised_meaning_requires_upstream_restart(self):
        session = self.session()
        request = lambda inputs: {"consultation_request": {"agent": "query_understanding", "topic": "interpretation"}}
        with patch.object(c, "understand_query", return_value={"population": "All accounts"}):
            with self.assertRaises(c.InterpretationRevised):
                session.run("Final_Spec", request, {"data": "ROW_SECRET"})
        self.assertEqual(session.interpretation, {"population": "All accounts"})
        self.assertEqual(session.log[0]["status"], "revised")

    def test_domain_call_is_cited_and_schema_only(self):
        text = "Preserve account identifiers."
        pack = {"rules": [{"id": "K1", "text": text, "fields": [],
                 "citations": [{"source": "rules", "quote": text}]}],
                "conflicts": [], "source_review": {"rules": "reviewed"}}
        client = FakeClient(pack)
        advice = c.consult_domain("List accounts", "population", [{"id": "rules", "content": text}],
            {"Accounts": {"columns": [{"name": "id"}], "sample": "ROW_SECRET", "path": "PATH_SECRET"}}, client, "offline")
        self.assertEqual(advice[0]["text"], text)
        for marker in ("ROW_SECRET", "PATH_SECRET"):
            self.assertNotIn(marker, json.dumps(client.calls))
