"""Translate the pipeline's OpenAI chat interface to Bedrock Converse HTTP.

Only request/response formats change. The original SDK retains timeout/retry
handling, and system/user text is passed verbatim. No model calls at import time.
"""
import json
import time
from urllib.parse import quote

import httpx
from openai import OpenAI


class ConverseTransport(httpx.BaseTransport):
    def __init__(self, endpoint, inner=None):
        self.endpoint = endpoint.rstrip('/')
        self.inner = inner or httpx.HTTPTransport()

    def handle_request(self, request):
        payload = json.loads(request.content)
        allowed = {'model', 'messages', 'temperature', 'top_p', 'max_tokens', 'max_completion_tokens', 'stop', 'stream'}
        unsupported = set(payload) - allowed
        if unsupported:
            raise ValueError('Unsupported Converse request parameters: ' + ', '.join(sorted(unsupported)))
        if payload.get('stream'):
            raise ValueError('The existing non-streaming pipeline is required')
        body = {'messages': []}
        system = []
        for message in payload['messages']:
            content = message.get('content')
            if not isinstance(content, str):
                raise ValueError('This adapter supports the pipeline text-only messages')
            if message['role'] == 'system':
                system.append({'text': content})
            elif message['role'] in ('user', 'assistant'):
                body['messages'].append({'role': message['role'], 'content': [{'text': content}]})
            else:
                raise ValueError('Unsupported message role: ' + message['role'])
        if system:
            body['system'] = system
        inference = {}
        for key, target in [('temperature', 'temperature'), ('top_p', 'topP'),
                            ('max_tokens', 'maxTokens'), ('max_completion_tokens', 'maxTokens')]:
            if key in payload:
                inference[target] = payload[key]
        if payload.get('stop'):
            inference['stopSequences'] = [payload['stop']] if isinstance(payload['stop'], str) else payload['stop']
        if inference:
            body['inferenceConfig'] = inference
        native = httpx.Request('POST', f"{self.endpoint}/model/{quote(payload['model'], safe='')}/converse",
                               headers={'Authorization': request.headers['authorization'],
                                        'Content-Type': 'application/json', 'Accept': 'application/json'},
                               json=body, extensions=request.extensions)
        response = self.inner.handle_request(native)
        try:
            data = response.read()
            headers = dict(response.headers)
            status = response.status_code
        finally:
            response.close()
        if status >= 400:
            return httpx.Response(status, content=data, request=request)
        result = json.loads(data)
        text = ''.join(block.get('text', '') for block in result['output']['message']['content'])
        stop = result.get('stopReason')
        finish = {'end_turn': 'stop', 'stop_sequence': 'stop', 'max_tokens': 'length',
                  'content_filtered': 'content_filter', 'guardrail_intervened': 'content_filter'}.get(stop)
        if finish is None:
            raise ValueError('Unexpected Converse stop reason: ' + str(stop))
        usage = result.get('usage') or {}
        converted_usage = None
        if 'inputTokens' in usage and 'outputTokens' in usage:
            converted_usage = {'prompt_tokens': usage['inputTokens'], 'completion_tokens': usage['outputTokens'],
                               'total_tokens': usage.get('totalTokens', usage['inputTokens'] + usage['outputTokens']),
                               'prompt_tokens_details': {'cached_tokens': usage.get('cacheReadInputTokens', 0)}}
        answer = {'id': headers.get('x-amzn-requestid', 'bedrock-converse'), 'object': 'chat.completion',
                  'created': int(time.time()), 'model': payload['model'],
                  'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': text}, 'finish_reason': finish}],
                  'usage': converted_usage}
        return httpx.Response(status, json=answer, request=request)

    def close(self):
        self.inner.close()


def build_client(*, api_key, base_url, max_retries=5, timeout=90.0):
    return OpenAI(api_key=api_key, base_url=base_url, max_retries=max_retries, timeout=timeout,
                  http_client=httpx.Client(transport=ConverseTransport(base_url), timeout=timeout))
