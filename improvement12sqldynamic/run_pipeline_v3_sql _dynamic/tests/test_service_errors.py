"""Provider failures stop planning without consuming more candidate requests."""
import contextlib
import difflib
import importlib.util
import io
import types
import unicodedata
import unittest
from unittest.mock import patch

from support import PACKAGE, SOURCE, load, registry


def actual_utils():
    spec = importlib.util.spec_from_file_location(PACKAGE + ".service_test_utils", SOURCE / "utils.py")
    module = importlib.util.module_from_spec(spec)
    with patch.object(load("common"), "difflib", difflib, create=True), \
            patch.object(load("common"), "unicodedata", unicodedata, create=True):
        spec.loader.exec_module(module)
    return module


class ProviderError(RuntimeError):
    def __init__(self, message, status_code=None, code=None):
        super().__init__(message)
        self.status_code, self.code = status_code, code


class ServiceErrorTests(unittest.TestCase):
    def setUp(self):
        self.utils = actual_utils()

    def test_logged_429_is_retryable_and_not_exhausted_quota(self):
        error = ProviderError("Error code: 429 - {'error': {'code': 'rate_limit_exceeded', "
                              "'message': 'Request quota reached; too many requests'}}")
        self.assertTrue(self.utils.is_rate_limit_error(error))
        self.assertTrue(self.utils.is_transient_connection_error(error))
        self.assertFalse(self.utils.is_quota_exhaustion_error(error))

    def test_sdk_attributes_recognize_throttling_with_generic_messages(self):
        for error in [ProviderError("Request failed", status_code=429),
                      ProviderError("Request failed", code="rate_limit_exceeded"),
                      ProviderError("Request failed", code="ThrottlingException")]:
            with self.subTest(error=error.__dict__):
                self.assertTrue(self.utils.is_transient_connection_error(error))
                self.assertFalse(self.utils.is_quota_exhaustion_error(error))

    def test_depleted_credits_have_priority_over_http_429(self):
        for message in ["insufficient_quota", "You exceeded your current quota",
                        "credit_balance_exhausted", "no credits remaining"]:
            error = ProviderError(message, status_code=429)
            with self.subTest(message=message):
                self.assertTrue(self.utils.is_quota_exhaustion_error(error))
                self.assertFalse(self.utils.is_rate_limit_error(error))
                self.assertFalse(self.utils.is_transient_connection_error(error))

    def test_semantic_and_local_errors_are_not_service_failures(self):
        for message in ["Final projection omits interpreted outputs", "no valid DAG",
                        "unknown column", "permission denied"]:
            self.assertFalse(self.utils.is_transient_connection_error(RuntimeError(message)))

    def test_planner_propagates_throttling_on_first_call(self):
        error = ProviderError("Too many requests", status_code=429)
        calls = []
        def request(**kwargs):
            calls.append(kwargs)
            raise error
        client = types.SimpleNamespace(chat=types.SimpleNamespace(
            completions=types.SimpleNamespace(create=request)))
        planner = load("planner").AdvancedAOPPlanner(client, registry())
        with patch.object(load("utils"), "is_quota_exhaustion_error",
                          self.utils.is_quota_exhaustion_error, create=True), \
                patch.object(load("utils"), "is_transient_connection_error",
                             self.utils.is_transient_connection_error, create=True), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ProviderError):
            planner.plan_optimal_dag_from_decomposition("Read values", {"subquestions": []})
        self.assertEqual(len(calls), 1)
        self.assertEqual(planner.last_planning["candidates"][0]["status"], "interrupted")
        self.assertFalse(planner.last_planning["fallback"])


if __name__ == "__main__":
    unittest.main()
