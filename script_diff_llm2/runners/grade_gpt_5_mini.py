#!/usr/bin/env python3
"""Grade an existing raw CSV with GPT-5 Mini using unchanged scoring logic."""
import argparse
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from script_diff_llm.evaluation.parallel_grading import parallel_regrade


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--save-every', type=int, default=1)
    parser.add_argument('--base-url')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    if args.workers < 1 or args.save_every < 1:
        parser.error('workers and save-every must be positive')
    if not args.raw.is_file():
        parser.error(f'Missing raw report: {args.raw}')
    if args.raw.resolve() == args.output.resolve():
        parser.error('raw and output must differ')
    print(f'Raw: {args.raw.resolve()}\nOutput: {args.output.resolve()}\nModel: gpt-5-mini\nWorkers: {args.workers}')
    if args.dry_run:
        return 0
    spec = importlib.util.spec_from_file_location('existing_mini_grader', ROOT / 'grade_openai_gpt_oss_120b_all_train_direct_llm_gpt_5_6_TERA.py')
    grader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(grader)
    grader.LLM_GRADER_MODEL = 'gpt-5-mini'
    grader.OUTPUT_DIR = str(args.output.resolve().parent)
    grader.RAW_REPORT_FILE = str(args.raw.resolve())
    grader.REPORT_FILE = str(args.output.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    grader.api_logger = grader.APILogger()
    if args.base_url:
        import os
        os.environ['OPENAI_BASE_URL'] = args.base_url
    client = grader.build_openai_grader_client()
    try:
        parallel_regrade(grader, args.raw, args.output, client, 'gpt-5-mini',
                         workers=args.workers, save_every=args.save_every)
    finally:
        grader.api_logger.save()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
