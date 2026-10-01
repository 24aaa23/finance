"""Prepare and run workbook question types sequentially, one pipeline at a time."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parents[1]
EXPERIMENT_DIR = PIPELINE_DIR.parent
sys.path.insert(0, str(EXPERIMENT_DIR))

from run_pipeline_v2.dataset_batch import (
    QUESTION_TYPE_SHEETS,
    load_full_answer_overrides,
    prepare_question_type_manifests,
    question_type_slug,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=EXPERIMENT_DIR / "datatset" / "wealth_management_1000_test_set_questions.xlsx")
    parser.add_argument("--full-answers", type=Path, default=EXPERIMENT_DIR / "datatset" / "216_questions_full_results.json")
    parser.add_argument("--output-root", type=Path, default=EXPERIMENT_DIR / "pipelien_output" / "run_v5_memory_safe")
    parser.add_argument("--workers", type=int, choices=[1], default=1,
                        help="Only one question worker is supported on this workstation.")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=EXPERIMENT_DIR / ".env",
        help="Environment file used for every child pipeline process (defaults to improvement6/.env).",
    )
    parser.add_argument("--type", dest="types", action="append", choices=QUESTION_TYPE_SHEETS,
                        help="Workbook sheet/type to run. Repeat for multiple types; omit for all eight, processed sequentially.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum questions per type; 0 means all 125.")
    parser.add_argument("--offset", type=int, default=0, help="Starting row offset inside every selected type.")
    parser.add_argument("--prepare-only", action="store_true", help="Create per-type JSONL manifests without invoking the pipeline.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.dataset = args.dataset.resolve()
    args.full_answers = args.full_answers.resolve()
    args.output_root = args.output_root.resolve()
    args.env_file = args.env_file.resolve()
    selected = tuple(args.types or QUESTION_TYPE_SHEETS)
    if args.limit < 0 or args.offset < 0:
        raise SystemExit("--limit and --offset must be non-negative.")
    if not args.env_file.is_file():
        raise SystemExit(f"Environment file does not exist: {args.env_file}")
    if args.prepare_only:
        manifests = prepare_question_type_manifests(args.dataset, args.full_answers, args.output_root, selected)
        override_count = len(load_full_answer_overrides(args.full_answers))
        print(f"Prepared {len(manifests)} type manifests; full-answer source contains {override_count} question overrides.")
        for sheet, manifest in manifests.items():
            print(f"  {sheet}: {manifest}")
        return

    # Release pandas/openpyxl and workbook allocations before starting a pipeline.
    # The supervising process stays stdlib-only even with eight terminals.
    preparation = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:], "--prepare-only"],
        check=False,
    )
    if preparation.returncode:
        raise SystemExit(preparation.returncode)
    manifests = {sheet: args.output_root / question_type_slug(sheet) / "input_questions.jsonl"
                 for sheet in selected}

    def process_environment(sheet: str, manifest: Path) -> dict[str, str]:
        type_dir = args.output_root / question_type_slug(sheet)
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
            "PIPELINE_ENV_OVERRIDE": "1",
        })
        return environment

    failures: list[str] = []
    for sheet, manifest in manifests.items():
        print(f"\n=== Running {sheet} ({manifest}) ===")
        completed = subprocess.run(
            [sys.executable, str(PIPELINE_DIR / "run.py")],
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
    main()
