"""Prepare and run workbook question types sequentially, one pipeline at a time."""

from __future__ import annotations

import time

BATCH_STARTED = time.perf_counter()

import argparse
import os
import subprocess
import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parents[1]
EXPERIMENT_DIR = PIPELINE_DIR.parent
sys.path.insert(0, str(EXPERIMENT_DIR))

sys.path.insert(0, str(PIPELINE_DIR))
from _bootstrap import bootstrap
bootstrap()
from run_pipeline_v3_sql.dataset_batch import (
    QUESTION_TYPE_SHEETS,
    load_full_answer_overrides,
    prepare_question_type_manifests,
    question_type_slug,
)
from run_pipeline_v3_sql.input_paths import add_input_arguments, input_arguments


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--full-answers", type=Path)
    add_input_arguments(parser)
    parser.add_argument("--query-understanding", choices=["on", "off"], default="on")
    parser.add_argument("--contract-checks", choices=["on", "off"], default="on")
    parser.add_argument("--agent-consultation", choices=["on", "off"], default="on")
    from run_pipeline_v3_sql.performance import query_delay
    parser.add_argument("--query-delay", type=query_delay, default=None)
    parser.add_argument("--output-root", type=Path, default=EXPERIMENT_DIR / "pipelien_output_sql_v3")
    parser.add_argument("--workers", type=int, choices=[1], default=1,
                        help="Only one question worker is supported on this workstation.")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=EXPERIMENT_DIR / ".env",
        help="Credential file for child processes; explicit launch settings take precedence.",
    )
    parser.add_argument("--type", dest="types", action="append", choices=QUESTION_TYPE_SHEETS,
                        help="Workbook sheet/type to run. Repeat for multiple types; omit for all eight, processed sequentially.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum questions per type; 0 means all 125.")
    parser.add_argument("--offset", type=int, default=0, help="Starting row offset inside every selected type.")
    parser.add_argument("--prepare-only", action="store_true", help="Create per-type JSONL manifests without invoking the pipeline.")
    parser.add_argument("--retry-query-spec-errors", action="store_true",
                        help="Rerun only saved QUERY_SPEC_ERROR questions into <type>/query_spec_retry; preserve original reports.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.retry_query_spec_errors and not args.dataset:
        raise SystemExit("--dataset is required unless retrying saved failures.")
    args.dataset = args.dataset.resolve() if args.dataset else None
    args.full_answers = args.full_answers.resolve() if args.full_answers else None
    args.db = args.db.resolve()
    args.output_root = args.output_root.resolve()
    args.env_file = args.env_file.resolve()
    selected = tuple(args.types or QUESTION_TYPE_SHEETS)
    if args.limit < 0 or args.offset < 0:
        raise SystemExit("--limit and --offset must be non-negative.")
    if args.retry_query_spec_errors and (args.limit or args.offset):
        raise SystemExit("Error-only retries use the saved failed-question cohort; omit --limit and --offset.")
    if not args.env_file.is_file():
        raise SystemExit(f"Environment file does not exist: {args.env_file}")
    if args.retry_query_spec_errors:
        from run_pipeline_v3_sql.retry_batch import prepare_query_spec_retry
        from run_pipeline_v3_sql.runtime_guard import report_lock
        manifests = {}
        for sheet in selected:
            source_dir = args.output_root / question_type_slug(sheet)
            retry_dir = source_dir / "query_spec_retry"
            with report_lock(source_dir / "raw_pipeline_v9.csv"), report_lock(retry_dir / "raw_pipeline_v9.csv"):
                manifest, count = prepare_query_spec_retry(source_dir / "raw_pipeline_v9.csv", retry_dir)
            if count:
                manifests[sheet] = manifest
                print(f"[RETRY] {sheet}: {count} original Query_Spec failures; report: {retry_dir / 'raw_pipeline_v9.csv'}")
            else:
                print(f"[SKIP] {sheet}: no QUERY_SPEC_ERROR rows.")
        if args.prepare_only:
            return
    elif args.prepare_only:
        manifests = prepare_question_type_manifests(args.dataset, args.full_answers, args.output_root, selected)
        override_count = len(load_full_answer_overrides(args.full_answers))
        print(f"Prepared {len(manifests)} type manifests; full-answer source contains {override_count} question overrides.")
        for sheet, manifest in manifests.items():
            print(f"  {sheet}: {manifest}")
        return

    # Release pandas/openpyxl and workbook allocations before starting a pipeline.
    # The supervising process stays stdlib-only even with eight terminals.
    if not args.retry_query_spec_errors:
        preparation = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:], "--prepare-only"],
            check=False,
        )
        if preparation.returncode:
            raise SystemExit(preparation.returncode)
        manifests = {sheet: args.output_root / question_type_slug(sheet) / "input_questions.jsonl"
                     for sheet in selected}

    def process_environment(sheet: str, manifest: Path) -> dict[str, str]:
        type_dir = manifest.parent
        report = type_dir / "raw_pipeline_v9.csv"
        environment = os.environ.copy()
        environment.update({
            "INPUT_QUERY_FILE": str(manifest),
            "TEST_QUERY_LIMIT": str(args.limit),
            "TEST_QUERY_OFFSET": str(args.offset),
            # Match the v3 launchers: one query at a time in one pipeline.
            "TEST_MAX_WORKERS": "1",
            "PIPELINE_OUTPUT_DIR": str(type_dir),
            "REPORT_FILE": str(report),
            "RESULT_JSONL_FILE": str(type_dir / "raw_pipeline_v9.jsonl"),
            "DEBUG_JSONL_FILE": str(type_dir / "raw_pipeline_v9_debug.jsonl"),
            "PIPELINE_ENV_FILE": str(args.env_file),
            "PIPELINE_ENV_OVERRIDE": "0",
            "RETRY_QUERY_SPEC_ERRORS_ONLY": "1" if args.retry_query_spec_errors else "0",
        })
        return environment

    failures: list[str] = []
    for sheet, manifest in manifests.items():
        print(f"\n=== Running {sheet} ({manifest}) ===")
        completed = subprocess.run(
            [sys.executable, str(PIPELINE_DIR / "run.py"), *input_arguments(args),
             "--questions", str(manifest), "--output", str(manifest.parent / "raw_pipeline_v9.csv"),
             "--limit", str(args.limit), "--query-understanding", args.query_understanding,
             "--contract-checks", args.contract_checks, "--agent-consultation", args.agent_consultation]
            + (["--query-delay", str(args.query_delay)] if args.query_delay is not None else []),
            cwd=PIPELINE_DIR,
            env=process_environment(sheet, manifest),
            check=False,
        )
        if completed.returncode:
            failures.append(sheet)
            print(f"[FAILED] {sheet} exited with code {completed.returncode}.")
            # Do not repeatedly launch more processes after a failed or blocked run.
            break
        else:
            print(f"[COMPLETE] {sheet}")
    if failures:
        raise SystemExit(f"Pipeline failed for: {', '.join(failures)}")


if __name__ == "__main__":
    try:
        main()
    finally:
        print(f"[TIME] Batch wall-clock including manifest preparation and child processes: {time.perf_counter() - BATCH_STARTED:.3f}s", flush=True)
