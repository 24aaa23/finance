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

from run_pipeline_v2_kg.dataset_batch import QUESTION_TYPE_SHEETS, question_type_slug
from run_pipeline_v2_kg.retry_batch import read_retry_report, failed_retry_rows
from run_pipeline_v2_kg.input_paths import add_input_arguments, input_arguments
from run_pipeline_v2_kg.run_identity import sha256_file

TYPES = tuple(question_type_slug(sheet) for sheet in QUESTION_TYPE_SHEETS)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--type", choices=TYPES)
    mode.add_argument("--status", action="store_true", help="Show counts for all eight types; no API calls or writes.")
    parser.add_argument("--output-root", type=Path, default=EXPERIMENT_DIR / "pipeline_output_kg_v11")
    parser.add_argument("--questions", type=Path,
                        help="Original question manifest, if stored outside the output folder.")
    add_input_arguments(parser)
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
    manifest_path = Path(str(report) + ".manifest.json")
    for path in (report, manifest_path, args.kg_data, args.ontology, args.env_file):
        if not path.is_file():
            parser.error(f"Required file does not exist: {path}")
    saved_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    questions = args.questions or folder / "input_questions.jsonl"
    if not args.questions and not questions.is_file():
        # Direct launches may use dataset CSVs rather than a generated cohort.
        # Only an exact saved hash authorizes reuse; do not reconstruct inputs.
        expected = saved_manifest.get("input_files", {}).get("questions", {}).get("sha256")
        if not expected:
            parser.error("Original question manifest is not recorded; provide --questions and a valid source/data manifest.")
        candidates = [EXPERIMENT_DIR / "pipeline_output_kg" / args.type / "input_questions.jsonl"]
        candidates += sorted((EXPERIMENT_DIR / "datatset").glob("*.csv"))
        candidates += sorted((EXPERIMENT_DIR / "dataset").glob("*.csv"))
        matches = [path for path in candidates if path.is_file() and sha256_file(path) == expected]
        if not matches:
            parser.error("Cannot locate the original question manifest by its saved hash; supply --questions.")
        questions = matches[0]
    if not questions.is_file():
        parser.error(f"Original question manifest does not exist: {questions}; supply --questions.")
    expected = saved_manifest.get("input_files", {}).get("questions", {}).get("sha256")
    if expected and sha256_file(questions) != expected:
        parser.error("Question manifest differs from the saved run; use the original --questions file.")
    _, rows = read_retry_report(report)
    failures = failed_retry_rows(rows)
    print(f"[SELECT] {args.type}: {len(failures)} errors to retry; {len(rows) - len(failures)} rows retained.", flush=True)
    if args.dry_run or not failures:
        return 0
    config = saved_manifest["configuration"]
    command = [sys.executable, "-B", str(PIPELINE_DIR / "run.py"),
               *input_arguments(args), "--env-file", str(args.env_file.resolve()),
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
