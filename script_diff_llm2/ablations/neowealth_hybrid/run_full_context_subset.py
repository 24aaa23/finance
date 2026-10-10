"""Run only the frozen partial/mismatch subset with complete supplied context."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('full_subset_neo',BASE/'run_raw.py')
neo=importlib.util.module_from_spec(spec);spec.loader.exec_module(neo)
launcher=neo.launcher
argv=sys.argv[1:]
i=argv.index('--subset');subset=Path(argv[i+1]).resolve();del argv[i:i+2]
i=argv.index('--context-bundle');bundle=Path(argv[i+1]).resolve();del argv[i:i+2]
launcher.SOURCES['INPUT_SAMPLE_FILE']=subset
original_environment=launcher.build_environment
original_manifest=launcher.manifest_for
original_execute=launcher.execute_raw

def environment(args,parent):
    env,output,experiment=original_environment(args,parent)
    env['NEOWEALTH_FULL_CONTEXT_BUNDLE']=str(bundle)
    # Full context is injected by the isolated entry adapter, not limited extraction.
    env.update(DOMAIN_INTRO_FILE='',BUSINESS_RULES_FILE='',DOMAIN_CONTEXT_REQUIRED='',DOMAIN_CONTEXT_APPROVAL_FILE='')
    return env,output,experiment

def manifest(args,env,experiment):
    result=original_manifest(args,env,experiment)
    config=result['configuration']
    config.update(full_context_bundle_sha256=launcher.file_hash(bundle),
                  full_context_adapter_sha256=launcher.file_hash(BASE/'full_context_entry.py'),
                  full_context_launcher_sha256=launcher.file_hash(Path(__file__)),
                  context_preparation='All source documents, no quarantine/truncation; per-request injection')
    result['signature']=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
    return result

def execute(command,env,output):
    command[2]=str(BASE/'full_context_entry.py')
    return original_execute(command,env,output)
launcher.build_environment=environment;launcher.manifest_for=manifest;launcher.execute_raw=execute
neo.gemini.load_gemini_env()
with subset.open() as f:count=sum(1 for _ in csv.DictReader(f))
if '--limit' not in argv:argv+=['--limit',str(count)]
if '--dag-workers' not in argv:argv+=['--dag-workers','1']
if '--fuseki-endpoint' not in argv:argv+=['--fuseki-endpoint','http://127.0.0.1:3031/neowealth/query']
raise SystemExit(launcher.main(['gemini_3_8_flash','with_context',*argv]))
