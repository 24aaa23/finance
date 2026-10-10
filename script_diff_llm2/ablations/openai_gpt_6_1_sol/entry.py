"""Local request compatibility adapter; leaves shared pipeline files unchanged."""
import os
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))


def compatible_request(request):
    request = dict(request)
    if request.get('model') == 'gpt-6.1-sol':
        for field in ('temperature', 'top_p', 'top_logprobs', 'logprobs'):
            request.pop(field, None)
        if 'max_tokens' in request:
            request.setdefault('max_completion_tokens', request.pop('max_tokens'))
        request['reasoning_effort'] = os.environ.get('SOL_REASONING_EFFORT', 'medium')
    return request


def main():
    if len(sys.argv) != 2:
        raise SystemExit('Expected experiment config path')
    # Configure before core_pipeline's import-time configuration is evaluated.
    os.environ['EXPERIMENT_CONFIG'] = sys.argv[1]
    from script_diff_llm.llm import clients
    original_factory = clients.build_model_client

    def build_client(**kwargs):
        client = original_factory(**kwargs)
        create = client.chat.completions.create

        def adapted_create(**request):
            return create(**compatible_request(request))

        client.chat.completions.create = adapted_create
        return client

    clients.build_model_client = build_client
    runpy.run_path(str(ROOT / 'runners/train/run_pipeline.py'), run_name='__main__')


if __name__ == '__main__':
    main()
