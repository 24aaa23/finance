"""Run a frozen Neowealth error subset with explicitly supplied database context."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('neowealth_subset_base', BASE / 'run_raw.py')
neo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(neo)
launcher = neo.launcher
argv = sys.argv[1:]
index = argv.index('--subset')
subset = Path(argv[index+1]).resolve()
del argv[index:index+2]
launcher.SOURCES['INPUT_SAMPLE_FILE'] = subset
original_environment = launcher.build_environment
original_manifest = launcher.manifest_for
original_execute = launcher.execute_raw

def environment(args, parent):
    env, output, experiment = original_environment(args, parent)
    env.update(DOMAIN_INTRO_FILE='', BUSINESS_RULES_FILE=str(neo.ROOT / '01_domain_and_business_rules.md'),
               DOMAIN_CONTEXT_REQUIRED='1', DOMAIN_CONTEXT_CACHE_DIR=str(BASE / 'context_cache/neowealth_gemini'),
               DOMAIN_CONTEXT_APPROVAL_FILE=args.approval_file or '')
    return env, output, experiment


def manifest(args, env, experiment):
    result = original_manifest(args, env, experiment)
    result['configuration']['context_subset_adapter_sha256'] = launcher.file_hash(Path(__file__))
    result['configuration']['session_adapter_sha256'] = launcher.file_hash(BASE / 'context_entry.py')
    result['signature'] = hashlib.sha256(json.dumps(result['configuration'],sort_keys=True).encode()).hexdigest()
    return result


def execute(command, env, output):
    command[2] = str(BASE / 'context_entry.py')
    return original_execute(command, env, output)

launcher.build_environment = environment
launcher.manifest_for = manifest
launcher.execute_raw = execute
neo.gemini.load_gemini_env()
with subset.open() as f:
    count = sum(1 for _ in csv.DictReader(f))
if '--limit' not in argv: argv += ['--limit',str(count)]
if '--dag-workers' not in argv: argv += ['--dag-workers','1']
if '--fuseki-endpoint' not in argv: argv += ['--fuseki-endpoint','http://127.0.0.1:3031/neowealth/query']
raise SystemExit(launcher.main(['gemini_3_8_flash','with_context', *argv]))
