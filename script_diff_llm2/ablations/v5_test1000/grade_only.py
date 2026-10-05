#!/usr/bin/env python3
"""Explicit manual GPT-5 Mini grading using the existing grader unchanged."""
import argparse
import importlib.util
from pathlib import Path
import sys

from run_raw import BASE, CONDITIONS, MODELS, ROOT


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model', choices=MODELS)
    parser.add_argument('condition', choices=CONDITIONS)
    parser.add_argument('--run-tag', default='run_01')
    parser.add_argument('--base-url', help='Optional grader API endpoint override')
    parser.add_argument('--workers', type=int, default=1, help='Bounded grading concurrency; 1 uses the original sequential runner')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    if args.workers < 1:
        parser.error('--workers must be positive')
    import re
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', args.run_tag):
        parser.error('--run-tag must be a simple directory name')
    output = BASE / 'runs' / args.model / args.condition / args.run_tag
    raw = output / 'raw_pipeline.csv'
    graded = output / 'graded_pipeline_gpt_5_mini.csv'
    print(f'Raw input: {raw}\nGraded output: {graded}\nGrader model: gpt-5-mini')
    if args.dry_run:
        return 0
    if not raw.is_file():
        raise FileNotFoundError(f'Raw report missing: {raw}')
    grader_path = ROOT / 'grade_openai_gpt_oss_120b_all_train_direct_llm_gpt_5_6_TERA.py'
    spec = importlib.util.spec_from_file_location('ablation_existing_grader', grader_path)
    grader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(grader)
    # Set these after its local .env loader so older defaults cannot replace them.
    grader.LLM_GRADER_MODEL = 'gpt-5-mini'
    grader.OUTPUT_DIR = str(output)
    grader.RAW_REPORT_FILE = str(raw)
    grader.REPORT_FILE = str(graded)
    grader.api_logger = grader.APILogger()
    if args.base_url:
        import os
        os.environ['OPENAI_BASE_URL'] = args.base_url
    client = grader.build_openai_grader_client()
    try:
        if args.workers == 1:
            grader.regrade_existing_report(str(raw), str(graded), client, 'gpt-5-mini')
        else:
            sys.path.insert(0, str(ROOT / 'src'))
            from script_diff_llm.evaluation.parallel_grading import parallel_regrade
            parallel_regrade(grader, raw, graded, client, 'gpt-5-mini', workers=args.workers)
    finally:
        grader.api_logger.save()
    print(f'Graded report saved: {graded}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
