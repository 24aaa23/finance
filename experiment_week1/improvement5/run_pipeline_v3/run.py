"""Run improvement5 v3 with a category name or legacy environment settings."""
from pathlib import Path
import argparse
import datetime
import os
import sys


def configure_run(argv=None):
    parser = argparse.ArgumentParser(description="Run one improvement5 v3 dataset.")
    parser.add_argument("dataset", nargs="?", choices=["ARC", "BSQ", "EC", "MC", "MC_diverse", "RC", "SQA", "TT", "WM"])
    parser.add_argument("--limit", type=int, default=0, help="0 = all rows")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.limit < 0 or args.offset < 0 or args.workers < 1:
        parser.error("limit/offset must be nonnegative and workers must be positive")
    if args.dataset:
        base = Path(__file__).resolve().parent.parent
        source = base / "dataset" / (args.dataset + ".csv")
        if not source.is_file():
            parser.error(f"Dataset not found: {source}")
        output = base / "pipeline_output_v3"
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        settings = {"INPUT_QUERY_CSV": str(source), "PIPELINE_OUTPUT_DIR": str(output),
                    "REPORT_FILE": str(output / f"{args.dataset}_v3_{stamp}.csv"),
                    "TEST_QUERY_LIMIT": str(args.limit), "TEST_QUERY_OFFSET": str(args.offset),
                    "TEST_MAX_WORKERS": str(args.workers),
                    "GPT_OSS_LLM_GRADER_PIPELINE_VERSION": "aop-improvement5-v3",
                    "BUSINESS_RULE_PACK_FILE": str(Path(__file__).with_name("business_rule_pack.json"))}
        print(f"Input: {source}\nOutput: {settings['REPORT_FILE']}\nLimit: {args.limit or 'all'}")
        if not args.dry_run:
            os.environ.update(settings)
    elif args.dry_run or args.limit or args.offset or args.workers != 1:
        parser.error("Select a dataset when using command-line run options")
    return not args.dry_run


if __name__ == "__main__" and configure_run():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from run_pipeline_v3.main import main
    main()
