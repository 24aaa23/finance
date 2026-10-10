"""Offline adapter tests; no inference requests are sent."""
import json
import unittest
from urllib.parse import unquote

import httpx
from openai import OpenAI, RateLimitError
from bedrock_converse import ConverseTransport


class ConverseTests(unittest.TestCase):
    def client(self, handler):
        return OpenAI(api_key='mock-key', base_url='https://example.invalid', max_retries=0,
                      http_client=httpx.Client(transport=ConverseTransport(
                          'https://example.invalid', httpx.MockTransport(handler))))

    def test_verbatim_messages_parameters_and_usage(self):
        def handler(request):
            self.assertIn('/model/us.meta.llama3-1-8b-instruct-v1:0/converse', unquote(str(request.url)))
            self.assertEqual(request.headers['authorization'], 'Bearer mock-key')
            body = json.loads(request.content)
            self.assertEqual(body['system'], [{'text': 'Exact system rules'}])
            self.assertEqual(body['messages'], [{'role': 'user', 'content': [{'text': 'Query café'}]}])
            self.assertEqual(body['inferenceConfig'], {'maxTokens': 4096, 'temperature': .2})
            return httpx.Response(200, json={'output': {'message': {'content': [{'text': '{"ok":true}'}]}},
                                             'stopReason': 'end_turn', 'usage': {'inputTokens': 13, 'outputTokens': 7, 'totalTokens': 20, 'cacheReadInputTokens': 2}})
        with self.client(handler) as client:
            result = client.chat.completions.create(model='us.meta.llama3-1-8b-instruct-v1:0',
                messages=[{'role': 'system', 'content': 'Exact system rules'}, {'role': 'user', 'content': 'Query café'}],
                max_tokens=4096, temperature=.2)
        self.assertEqual(result.choices[0].message.content, '{"ok":true}')
        self.assertEqual(result.choices[0].finish_reason, 'stop')
        self.assertEqual(result.usage.prompt_tokens, 13)
        self.assertEqual(result.usage.completion_tokens, 7)
        self.assertEqual(result.usage.prompt_tokens_details.cached_tokens, 2)

    def test_truncation_and_missing_usage(self):
        with self.client(lambda request: httpx.Response(200, json={
            'output': {'message': {'content': [{'text': '{'}]}}, 'stopReason': 'max_tokens'})) as client:
            result = client.chat.completions.create(model='test', messages=[{'role': 'user', 'content': 'question'}])
        self.assertEqual(result.choices[0].finish_reason, 'length')
        self.assertIsNone(result.usage)

    def test_quota_error_keeps_sdk_exception_type(self):
        with self.client(lambda request: httpx.Response(429, json={'message': 'Throttled'})) as client:
            with self.assertRaises(RateLimitError):
                client.chat.completions.create(model='test', messages=[{'role': 'user', 'content': 'question'}])


if __name__ == '__main__':
    unittest.main()
