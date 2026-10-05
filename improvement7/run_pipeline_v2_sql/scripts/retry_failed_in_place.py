"""Retry saved execution failures in their existing reports, one type per terminal."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import sys


PIPELINE_DIR = Path(__file__).resolve().parents[1]
EXPERIMENT_DIR = PIPELINE_DIR.parent
sys.path.insert(0, str(EXPERIMENT_DIR))

from run_pipeline_v2_sql.dataset_batch import QUESTION_TYPE_SHEETS, question_type_slug
from run_pipeline_v2_sql.retry_batch import read_retry_report, failed_retry_rows

TYPES = tuple(question_type_slug(sheet) for sheet in QUESTION_TYPE_SHEETS)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--type", choices=TYPES)
    mode.add_argument("--status", action="store_true", help="Show counts for all eight types; no API calls or writes.")
    parser.add_argument("--output-root", type=Path, default=EXPERIMENT_DIR / "pipelien_output_sql")
    parser.add_argument("--db", type=Path, default=EXPERIMENT_DIR / "wealth_management_diverse.db")
    parser.add_argument("--env-file", type=Path, default=EXPERIMENT_DIR / ".env")
    parser.add_argument("--dry-run", action="store_true", help="Show selection without changing files or calling models.")
    args = parser.parse_args(argv)
    root = args.output_root.resolve()
    if args.status:
        print(f"{'Type':<25} {'Saved':>7} {'Success':>8} {'Errors':>7}")
        total = Counter()
        for name in TYPES:
            path = root / name / "raw_pipeline_v9.csv"
            if not path.is_file():
                print(f"{name:<25} missing report")
                continue
            _, rows = read_retry_report(path)
            counts = dict(saved=len(rows), success=sum(r["New Status"].strip().upper() == "PIPELINE_SUCCESS" for r in rows),
                          errors=len(failed_retry_rows(rows)))
            total.update(counts)
            print(f"{name:<25} {counts['saved']:>7} {counts['success']:>8} {counts['errors']:>7}")
        print(f"{'TOTAL':<25} {total['saved']:>7} {total['success']:>8} {total['errors']:>7}")
        return 0
    folder = root / args.type
    report = folder / "raw_pipeline_v9.csv"
    questions = folder / "input_questions.jsonl"
    manifest_path = Path(str(report) + ".manifest.json")
    for path in (report, questions, manifest_path, args.db, args.env_file):
        if not path.is_file():
            parser.error(f"Required file does not exist: {path}")
    _, rows = read_retry_report(report)
    failures = failed_retry_rows(rows)
    print(f"[SELECT] {args.type}: {len(failures)} errors to retry; {len(rows) - len(failures)} rows retained.", flush=True)
    if args.dry_run or not failures:
        return 0
    config = json.loads(manifest_path.read_text(encoding="utf-8"))["configuration"]
    command = [sys.executable, "-B", str(PIPELINE_DIR / "run.py"),
               "--db", str(args.db.resolve()), "--env-file", str(args.env_file.resolve()),
               "--questions", str(questions), "--output", str(report), "--retry-errors-in-place"]
    for option in ("query_understanding", "contract_checks", "agent_consultation"):
        command += ["--" + option.replace("_", "-"), "on" if config.get(option, option != "agent_consultation") else "off"]
    command += ["--query-delay", str(config.get("query_delay_seconds", 0))]
    environment = os.environ.copy()
    environment.update(RESULT_JSONL_FILE=str(report.with_suffix(".jsonl")),
                       DEBUG_JSONL_FILE=str(folder / "raw_pipeline_v9_debug.jsonl"),
                       TEST_QUERY_OFFSET="0", TEST_MAX_WORKERS="1")
    return subprocess.run(command, env=environment, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
