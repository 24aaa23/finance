"""Neowealth hybrid raw run: native DuckDB and matching RDF, Gemini API."""
import importlib.util
from pathlib import Path
import sys
import csv
import copy
import hashlib
import json
csv.field_size_limit(10_000_000)
BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
spec = importlib.util.spec_from_file_location('neowealth_gemini', ROOT / 'ablations/gemini_3_8_flash/run_raw.py')
gemini = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gemini)
launcher = gemini.launcher
launcher.BASE = BASE
launcher.SOURCES = {
    'SQLITE_DB_PATH': ROOT / 'neowealth.duckdb',
    'INPUT_SAMPLE_FILE': ROOT / 'data/benchmarks/neowealth_test.csv',
    'SCHEMA_FILE': ROOT / 'kg_output_neowealth/neowealth_schema.ttl',
    'INSTANCE_FILE': ROOT / 'kg_output_neowealth/neowealth_kg.ttl',
}
original_environment = launcher.build_environment

def environment(args, parent):
    env, output, experiment = original_environment(args, parent)
    env.update(INPUT_SAMPLE_SHEET='', GROUND_TRUTH_OVERRIDE_FILE='', RDF_ALIAS_MAP_FILE='',
               DOMAIN_INTRO_FILE='', BUSINESS_RULES_FILE='', DOMAIN_CONTEXT_REQUIRED='',
               SEMANTIC_CATALOG_FILE='')
    return env, output, experiment

def check_resume(output, manifest):
    raw = output / 'raw_pipeline.csv'
    previous = output / 'run_manifest.json'
    if not raw.exists() or not raw.stat().st_size:
        return
    if not previous.is_file():
        raise ValueError('Existing raw report has no manifest; refusing to mix untracked results')
    old = json.loads(previous.read_text())
    old_config = copy.deepcopy(old['configuration'])
    new_config = copy.deepcopy(manifest['configuration'])
    # Question concurrency changes scheduling only, not the per-question DAG.
    for configuration in (old_config, new_config):
        configuration['settings'].pop('TEST_MAX_WORKERS', None)
    # Recognize only the one-line startup health-check fix; preserve prior answers.
    core_key = 'src/script_diff_llm/pipeline/core_pipeline.py'
    core_path = ROOT / core_key
    corrected = core_path.read_text()
    legacy = corrected.replace('        check_fuseki_health(FUSEKI_ENDPOINT, FUSEKI_SCAN_TIMEOUT_SECONDS)',
                               '        check_fuseki_health()')
    legacy_hash = hashlib.sha256(legacy.encode()).hexdigest()
    if old_config['implementation'].get(core_key) == legacy_hash:
        old_config['implementation'][core_key] = new_config['implementation'][core_key]
    if old_config != new_config:
        raise ValueError('Run inputs/model/pipeline changed. Only query worker count may change when resuming; use a fresh run tag for other changes.')
    with raw.open(newline='') as handle:
        saved = sum(1 for _ in csv.DictReader(handle))
    before = old['configuration']['settings']['TEST_MAX_WORKERS']
    after = manifest['configuration']['settings']['TEST_MAX_WORKERS']
    print(f'[RESUME] Found {saved} saved rows in {raw}; query workers {before} -> {after}. Existing runner resume/retry rules apply.', flush=True)


launcher.build_environment = environment
launcher.check_resume = check_resume
if __name__ == '__main__':
    gemini.load_gemini_env()
    argv = sys.argv[1:]
    if '--limit' not in argv:
        with launcher.SOURCES['INPUT_SAMPLE_FILE'].open() as f:
            count = sum(1 for _ in csv.DictReader(f))
        argv += ['--limit', str(count)]
    if '--dag-workers' not in argv:
        argv += ['--dag-workers','1']
    if '--fuseki-endpoint' not in argv:
        argv += ['--fuseki-endpoint','http://127.0.0.1:3031/neowealth/query']
    raise SystemExit(launcher.main(['gemini_3_8_flash','without_context', *argv]))
