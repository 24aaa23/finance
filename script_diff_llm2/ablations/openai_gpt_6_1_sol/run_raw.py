"""Run the existing main hybrid pipeline on OpenAI GPT-6.1 Sol, raw only."""
import importlib.util
import os
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
spec = importlib.util.spec_from_file_location('hybrid_ablation_launcher', ROOT / 'ablations/v5_test1000/run_raw.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)
launcher.BASE = BASE
launcher.MODELS = {'gpt_6_1_sol': ('gpt-6.1-sol', 'OPENAI_BASE_URL', 'openai')}
original_environment = launcher.build_environment
original_manifest = launcher.manifest_for
original_execute = launcher.execute_raw


def environment(args, parent):
    args.base_url = args.base_url or parent.get('OPENAI_BASE_URL') or 'https://api.openai.com/v1'
    env, output, experiment = original_environment(args, parent)
    effort = parent.get('SOL_REASONING_EFFORT', 'medium')
    if effort not in {'low', 'medium', 'high', 'xhigh', 'max'}:
        raise ValueError('SOL_REASONING_EFFORT must be low, medium, high, xhigh or max')
    if args.model_id and args.model_id != 'gpt-6.1-sol':
        raise ValueError('This launcher is pinned to gpt-6.1-sol')
    if not args.dry_run and not env.get('OPENAI_API_KEY'):
        raise RuntimeError('OPENAI_API_KEY is required; export it or set it in the existing local .env')
    env.update(PIPELINE_BACKEND_MODE='hybrid', SOL_REASONING_EFFORT=effort)
    return env, output, experiment


def manifest(args, env, experiment):
    result = original_manifest(args, env, experiment)
    result['configuration']['reasoning_effort'] = env['SOL_REASONING_EFFORT']
    result['configuration']['backend_mode'] = 'hybrid'
    result['configuration']['transport'] = {
        name: launcher.file_hash(BASE / name) for name in ['entry.py', 'run_raw.py']}
    import hashlib
    import json
    result['signature'] = hashlib.sha256(json.dumps(result['configuration'], sort_keys=True).encode()).hexdigest()
    return result


def execute(command, env, output):
    command[2] = str(BASE / 'entry.py')
    return original_execute(command, env, output)


launcher.build_environment = environment
launcher.manifest_for = manifest
launcher.execute_raw = execute

if __name__ == '__main__':
    # Match the familiar condition-first command; default to the generic condition.
    argv = sys.argv[1:]
    if not argv or argv[0].startswith('-'):
        argv.insert(0, 'without_context')
    if '--workers' not in argv:
        argv += ['--workers', '2']
    if '--dag-workers' not in argv:
        argv += ['--dag-workers', '1']
    raise SystemExit(launcher.main(['gpt_6_1_sol', *argv]))
