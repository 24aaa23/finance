"""Main hybrid GPT-OSS 120B experiment through Azure OpenAI v1, raw only."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit, urlunsplit

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
spec = importlib.util.spec_from_file_location('hybrid_launcher', ROOT / 'ablations/v5_test1000/run_raw.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)
launcher.BASE = BASE
launcher.MODELS = {'gpt_oss_120b': ('gpt-oss-120b', 'AZURE_OPENAI_ENDPOINT', 'azure')}
original_environment = launcher.build_environment
original_manifest = launcher.manifest_for


def load_azure_env():
    path = BASE / 'azure.env'
    if not path.exists():
        return
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:].strip()
        key, sep, value = line.partition('=')
        if not sep or not key.strip().startswith('AZURE_'):
            raise ValueError('azure.env must contain only AZURE_* assignments')
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        else:
            value = value.split('#', 1)[0].strip()
        if value:
            os.environ.setdefault(key.strip(), value)


def inference_url(value):
    url = urlsplit(value.strip())
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('Use an HTTPS resource endpoint without credentials, query parameters or fragments')
    path = url.path.rstrip('/')
    if path not in {'', '/openai/v1'}:
        raise ValueError('Use the resource root or /openai/v1/ URL, not a Foundry project, /models, or legacy deployments URL')
    return urlunsplit((url.scheme, url.netloc, '/openai/v1/', '', ''))


def environment(args, parent):
    endpoint = args.base_url or parent.get('AZURE_OPENAI_ENDPOINT') or parent.get('AZURE_FOUNDRY_ENDPOINT')
    deployment = args.model_id or parent.get('AZURE_GPT_OSS_DEPLOYMENT')
    if not endpoint or not deployment:
        raise RuntimeError('Set AZURE_OPENAI_ENDPOINT (or AZURE_FOUNDRY_ENDPOINT) and AZURE_GPT_OSS_DEPLOYMENT in azure.env')
    if not args.dry_run and not parent.get('AZURE_OPENAI_API_KEY'):
        raise RuntimeError('Set AZURE_OPENAI_API_KEY in azure.env or the environment')
    args.base_url = inference_url(endpoint)
    args.model_id = deployment
    env, output, experiment = original_environment(args, parent)
    env['PIPELINE_BACKEND_MODE'] = 'hybrid'
    return env, output, experiment


def manifest(args, env, experiment):
    result = original_manifest(args, env, experiment)
    result['configuration']['provider'] = 'azure-openai-v1'
    result['configuration']['backend_mode'] = 'hybrid'
    result['configuration']['launcher_sha256'] = launcher.file_hash(Path(__file__))
    result['signature'] = hashlib.sha256(json.dumps(result['configuration'], sort_keys=True).encode()).hexdigest()
    return result


launcher.build_environment = environment
launcher.manifest_for = manifest


def main():
    load_azure_env()
    launcher.load_local_env_file()
    if '--check-connection' in sys.argv[1:]:
        if len(sys.argv) != 2:
            raise ValueError('Run --check-connection on its own')
        from openai import OpenAI
        endpoint = os.getenv('AZURE_OPENAI_ENDPOINT') or os.getenv('AZURE_FOUNDRY_ENDPOINT') or ''
        deployment = os.getenv('AZURE_GPT_OSS_DEPLOYMENT')
        key = os.getenv('AZURE_OPENAI_API_KEY')
        if not deployment or not key:
            raise RuntimeError('Set the Azure endpoint, deployment and API key first')
        client = OpenAI(api_key=key, base_url=inference_url(endpoint), max_retries=0, timeout=60)
        # This explicit option makes one small billed inference request, never a benchmark.
        response = client.chat.completions.create(model=deployment,
            messages=[{'role': 'user', 'content': 'Reply OK only.'}], max_tokens=256)
        print('Connection succeeded. Deployment:', deployment)
        print('Finish reason:', response.choices[0].finish_reason)
        print('Usage:', response.usage.model_dump() if response.usage else 'not reported')
        return 0
    argv = sys.argv[1:]
    if not argv or argv[0].startswith('-'):
        argv.insert(0, 'without_context')
    if '--workers' not in argv:
        argv += ['--workers', '2']
    if '--dag-workers' not in argv:
        argv += ['--dag-workers', '1']
    return launcher.main(['gpt_oss_120b', *argv])


if __name__ == '__main__':
    raise SystemExit(main())
