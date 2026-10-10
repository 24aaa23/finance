"""Main hybrid Gemini 3.8 Flash experiment through Google Gemini API, raw only."""
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
launcher.MODELS = {'gemini_3_8_flash': ('gemini-3.8-flash', 'GEMINI_BASE_URL', 'google')}
original_environment = launcher.build_environment
original_manifest = launcher.manifest_for


def load_gemini_env():
    path = BASE / 'gemini.env'
    if not path.exists():
        return
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:].strip()
        key, sep, value = line.partition('=')
        if not sep or not key.strip().startswith('GEMINI_'):
            raise ValueError('gemini.env must contain only GEMINI_* assignments')
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        else:
            value = value.split('#', 1)[0].strip()
        if value:
            os.environ.setdefault(key.strip(), value)


def inference_url(value):
    url = urlsplit(value.strip())
    if (url.scheme != 'https' or url.netloc != 'generativelanguage.googleapis.com'
            or url.path.rstrip('/') != '/v1beta/openai' or url.query or url.fragment):
        raise ValueError('GEMINI_BASE_URL must be https://generativelanguage.googleapis.com/v1beta/openai/')
    return urlunsplit((url.scheme, url.netloc, '/v1beta/openai/', '', ''))


def environment(args, parent):
    args.base_url = inference_url(args.base_url or parent.get('GEMINI_BASE_URL')
                                  or 'https://generativelanguage.googleapis.com/v1beta/openai/')
    args.model_id = args.model_id or parent.get('GEMINI_MODEL') or 'gemini-3.8-flash'
    if not args.dry_run and not parent.get('GEMINI_API_KEY'):
        raise RuntimeError('Set GEMINI_API_KEY in gemini.env or the environment')
    env, output, experiment = original_environment(args, parent)
    env['PIPELINE_BACKEND_MODE'] = 'hybrid'
    return env, output, experiment


def manifest(args, env, experiment):
    result = original_manifest(args, env, experiment)
    result['configuration']['provider'] = 'google-openai-compatible'
    result['configuration']['backend_mode'] = 'hybrid'
    result['configuration']['launcher_sha256'] = launcher.file_hash(Path(__file__))
    result['signature'] = hashlib.sha256(json.dumps(result['configuration'], sort_keys=True).encode()).hexdigest()
    return result


launcher.build_environment = environment
launcher.manifest_for = manifest


def main():
    load_gemini_env()
    launcher.load_local_env_file()
    if '--check-connection' in sys.argv[1:]:
        if len(sys.argv) != 2:
            raise ValueError('Run --check-connection on its own')
        from openai import OpenAI
        endpoint = os.getenv('GEMINI_BASE_URL') or 'https://generativelanguage.googleapis.com/v1beta/openai/'
        deployment = os.getenv('GEMINI_MODEL') or 'gemini-3.8-flash'
        key = os.getenv('GEMINI_API_KEY')
        if not key:
            raise RuntimeError('Set GEMINI_API_KEY in gemini.env first')
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
        argv += ['--workers', '4']
    if '--dag-workers' not in argv:
        argv += ['--dag-workers', '1']
    return launcher.main(['gemini_3_8_flash', *argv])


if __name__ == '__main__':
    raise SystemExit(main())
