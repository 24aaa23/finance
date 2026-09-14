"""Run GPT-5.6 Terra LLM Grader on the 3 V4 report files.

Usage:
    python grade_v4_3_files_terra.py             # Grade all 3 files
    python grade_v4_3_files_terra.py --file 1    # Grade only file 1 (v4_simple_success_55.csv)
    python grade_v4_3_files_terra.py --file 2    # Grade only file 2 (v4_simple_non_success_part1_69.csv)
    python grade_v4_3_files_terra.py --file 3    # Grade only file 3 (v4_simple_non_success_part2_68.csv)
    python grade_v4_3_files_terra.py --combine   # Combine already graded files and print summary
"""

import argparse
import os
import sys
import time
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# Force load the valid OPENAI_API_KEY from local .env (overwriting any stale system env var)
def force_load_local_env():
    env_file = os.path.join(SCRIPT_DIR, ".env")
    if os.path.exists(env_file):
        with open(env_file, encoding="utf-8-sig") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                value = value.strip().strip('"').strip("'")
                os.environ[key.strip()] = value  # Direct override

force_load_local_env()

from run_pipeline_v4.grade_final_answers import (
    DEFAULT_LLM_GRADER_MODEL,
    build_openai_grader_client,
    regrade_existing_report,
)

OUTPUT_DIR = os.path.join(SCRIPT_DIR, "pipelien_output")

FILES_TO_GRADE = [
    {
        "id": 1,
        "name": "v4_simple_success_55",
        "raw_csv": os.path.join(OUTPUT_DIR, "v4_simple_success_55.csv"),
        "graded_csv": os.path.join(OUTPUT_DIR, "graded_v4_simple_success_55_terra.csv"),
        "expected_rows": 55,
    },
    {
        "id": 2,
        "name": "v4_simple_non_success_part1_69",
        "raw_csv": os.path.join(OUTPUT_DIR, "v4_simple_non_success_part1_69.csv"),
        "graded_csv": os.path.join(OUTPUT_DIR, "graded_v4_simple_non_success_part1_69_terra.csv"),
        "expected_rows": 69,
    },
    {
        "id": 3,
        "name": "v4_simple_non_success_part2_68",
        "raw_csv": os.path.join(OUTPUT_DIR, "v4_simple_non_success_part2_68.csv"),
        "graded_csv": os.path.join(OUTPUT_DIR, "graded_v4_simple_non_success_part2_68_terra.csv"),
        "expected_rows": 68,
    },
]

FILES_TO_GRADE_LATEST = [
    {
        "id": 1,
        "name": "v4_latest_success_55",
        "raw_csv": os.path.join(OUTPUT_DIR, "v4_latest_success_55.csv"),
        "graded_csv": os.path.join(OUTPUT_DIR, "graded_v4_latest_success_55_terra.csv"),
        "expected_rows": 55,
    },
    {
        "id": 2,
        "name": "v4_latest_non_success_part1_69",
        "raw_csv": os.path.join(OUTPUT_DIR, "v4_latest_non_success_part1_69.csv"),
        "graded_csv": os.path.join(OUTPUT_DIR, "graded_v4_latest_non_success_part1_69_terra.csv"),
        "expected_rows": 69,
    },
    {
        "id": 3,
        "name": "v4_latest_non_success_part2_68",
        "raw_csv": os.path.join(OUTPUT_DIR, "v4_latest_non_success_part2_68.csv"),
        "graded_csv": os.path.join(OUTPUT_DIR, "graded_v4_latest_non_success_part2_68_terra.csv"),
        "expected_rows": 68,
    },
]

COMBINED_GRADED_CSV = os.path.join(OUTPUT_DIR, "graded_v4_all_192_combined_terra.csv")


def print_summary_table(df: pd.DataFrame, title: str = "GRADING SUMMARY") -> None:
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)
    total_rows = len(df)
    print(f"Total Rows: {total_rows}")

    if "New Status" in df.columns:
        print("\n[Execution Pipeline Status]")
        for status, count in df["New Status"].value_counts().items():
            pct = (count / total_rows) * 100
            print(f"  {status:<25}: {count:>4} ({pct:>5.1f}%)")

    if "Grade Status" in df.columns:
        print("\n[Direct LLM Grader Status (GPT-5.6 Terra)]")
        for status, count in df["Grade Status"].value_counts().items():
            pct = (count / total_rows) * 100
            print(f"  {status:<25}: {count:>4} ({pct:>5.1f}%)")

        evaluated = df[df["Grade Status"].isin(["MATCH", "PARTIAL", "MISMATCH", "OTHER"])]
        if len(evaluated) > 0:
            print(f"\n[Among Evaluated Final Answers ({len(evaluated)}/{total_rows})]")
            for status in ["MATCH", "PARTIAL", "MISMATCH", "OTHER"]:
                cnt = (evaluated["Grade Status"] == status).sum()
                pct = (cnt / len(evaluated)) * 100
                print(f"  {status:<15}: {cnt:>4} ({pct:>5.1f}%)")
    print("=" * 60 + "\n")


def combine_graded_files() -> None:
    dfs = []
    for item in FILES_TO_GRADE:
        graded_path = item["graded_csv"]
        if os.path.exists(graded_path):
            try:
                df = pd.read_csv(graded_path, dtype=str, keep_default_na=False)
                df["Source File"] = item["name"]
                dfs.append(df)
            except Exception as e:
                print(f"[WARN] Error reading {graded_path}: {e}")
    if dfs:
        combined = pd.concat(dfs, ignore_index=True)
        combined.to_csv(COMBINED_GRADED_CSV, index=False, encoding="utf-8")
        print(f"[SUCCESS] Combined report saved: {COMBINED_GRADED_CSV} ({len(combined)} rows)")
        print_summary_table(combined, "COMBINED 192-QUERY BENCHMARK SUMMARY")
    else:
        print("[WARN] No graded files available to combine yet.")


def grade_file(item: dict, grader_client, model: str) -> None:
    raw_path = item["raw_csv"]
    graded_path = item["graded_csv"]
    name = item["name"]

    if not os.path.exists(raw_path):
        print(f"[ERROR] Raw CSV file not found: {raw_path}")
        return

    try:
        raw_df = pd.read_csv(raw_path, dtype=str, keep_default_na=False)
        row_count = len(raw_df)
    except Exception as e:
        print(f"[ERROR] Cannot read {raw_path}: {e}")
        return

    # If the graded file currently contains only errors (e.g. from a prior 401 auth crash), reset it
    if os.path.exists(graded_path):
        try:
            prev_df = pd.read_csv(graded_path, dtype=str, keep_default_na=False)
            valid_grades = prev_df["Grade Status"].isin(["MATCH", "PARTIAL", "MISMATCH", "OTHER", "SKIPPED_EXECUTION_FAILURE"]).sum()
            if valid_grades == 0:
                print(f"[INFO] Removing previous broken report containing only API errors: {graded_path}")
                os.remove(graded_path)
        except Exception:
            pass

    print("\n" + "#" * 60)
    print(f"GRADING [{item['id']}/3]: {name}")
    print(f"Input : {raw_path} ({row_count}/{item['expected_rows']} rows)")
    print(f"Output: {graded_path}")
    print(f"Model : {model}")
    print("#" * 60)

    start_time = time.perf_counter()
    regrade_existing_report(raw_path, graded_path, grader_client, model)
    elapsed = time.perf_counter() - start_time

    print(f"[DONE] Completed in {elapsed:.1f}s")
    if os.path.exists(graded_path):
        graded_df = pd.read_csv(graded_path, dtype=str, keep_default_na=False)
        print_summary_table(graded_df, f"SUMMARY: {name}")


def main():
    parser = argparse.ArgumentParser(description="Grade V4 pipeline output using GPT-5.6 Terra")
    parser.add_argument("--file", type=int, choices=[1, 2, 3], help="Grade specific file (1, 2, or 3)")
    parser.add_argument("--latest", action="store_true", help="Grade the v4_latest_* files instead of v4_simple_*")
    parser.add_argument("--combine", action="store_true", help="Only combine already graded reports and print summary")
    parser.add_argument("--model", type=str, default=DEFAULT_LLM_GRADER_MODEL, help="Grader model name")
    args = parser.parse_args()

    if args.combine:
        combine_graded_files()
        return

    active_key = os.environ.get("OPENAI_API_KEY", "")
    key_preview = (active_key[:8] + "..." + active_key[-4:]) if len(active_key) > 12 else "None"

    print("\n" + "=" * 60)
    print("STARTING GPT-5.6 TERRA GRADER ON V4 PIPELINE FILES")
    print(f"Grader Model: {args.model}")
    print(f"API Key Used: {key_preview} (from local .env)")
    print("=" * 60)

    grader_client = build_openai_grader_client()

    targets = FILES_TO_GRADE_LATEST if args.latest else FILES_TO_GRADE
    if args.file:
        targets = [f for f in targets if f["id"] == args.file]

    for item in targets:
        grade_file(item, grader_client, args.model)

    if not args.file or len(targets) == len(FILES_TO_GRADE):
        combine_graded_files()


if __name__ == "__main__":
    main()
