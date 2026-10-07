"""Prepare and run improvement12sqldynamic questions in one local output folder."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
PIPELINE = ROOT / "run_pipeline_v3_sql _dynamic"


def inside_root(path):
    path = Path(path).expanduser().resolve()
    if path != ROOT and ROOT not in path.parents:
        raise ValueError(f"Keep experiment inputs/outputs inside {ROOT}: {path}")
    return path


def _save_manifest(path, text):
    payload = text.encode("utf-8")
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError(f"Inputs changed: {path}. Use a fresh output folder to preserve this run.")
        return
    path.write_bytes(payload)


def prepare_dataset(workbook, answers, output):
    import pandas as pd
    sys.path.insert(0, str(PIPELINE))
    from _bootstrap import bootstrap
    bootstrap()
    from run_pipeline_v3_sql.dataset_batch import QUESTION_TYPE_SHEETS, load_full_answer_overrides
    overrides = load_full_answer_overrides(answers)
    records, source_records, seen, seen_source_ids = [], [], set(), set()
    category_counts = {}
    used_overrides = set()
    with pd.ExcelFile(workbook) as excel:
        for sheet in QUESTION_TYPE_SHEETS:
            frame = pd.read_excel(excel, sheet_name=sheet, dtype=object)
            frame = frame.where(pd.notna(frame), "")
            required = {"global_question_id", "question_id", "question", "ground_truth_answer"}
            if not required <= set(frame.columns):
                raise ValueError(f"Missing dataset columns in {sheet}: {sorted(required - set(frame.columns))}")
            category_counts[sheet] = len(frame)
            for raw in frame.to_dict(orient="records"):
                raw = {key: value.item() if hasattr(value, "item") else value for key, value in raw.items()}
                question_id, source_id = str(raw["global_question_id"]), str(raw["question_id"])
                if not question_id or question_id in seen or not source_id or source_id in seen_source_ids:
                    raise ValueError(f"Missing or duplicate question ID: {question_id} / {source_id}")
                if not str(raw["question"]).strip():
                    raise ValueError(f"Empty question: {question_id}")
                seen.add(question_id)
                seen_source_ids.add(source_id)
                answer = overrides[source_id] if source_id in overrides else raw["ground_truth_answer"]
                if source_id in overrides:
                    used_overrides.add(source_id)
                if isinstance(answer, str):
                    try:
                        answer = json.loads(answer)
                    except json.JSONDecodeError as error:
                        raise ValueError(f"Invalid ground truth JSON for {question_id}") from error
                if not isinstance(answer, (list, dict)):
                    raise ValueError(f"Ground truth must be structured JSON: {question_id}")
                source = "full_answer_json" if source_id in overrides else "excel"
                ground_truth = json.dumps(answer, ensure_ascii=False)
                records.append({"Sample Row ID": question_id, "Source Question ID": source_id,
                    "Question": str(raw["question"]), "Ground Truth": ground_truth,
                    "Ground Truth Source": source, "Difficulty": raw.get("difficulty", ""),
                    "Category": raw.get("category", ""), "Query Type": raw.get("query_type", ""),
                    "Source CSV": raw.get("source_csv", ""), "Dataset Type": sheet,
                    "Reference SQL": raw.get("sql_query", ""), "Tables Used": raw.get("tables_used", ""),
                    "Number of Tables Used": raw.get("number_of_tables_used", "")})
                source_records.append({**raw, "dataset_type": sheet, "ground_truth_answer": ground_truth,
                                       "ground_truth_source": source})
    if set(overrides) != used_overrides:
        raise ValueError(f"Full-answer JSON has IDs absent from the workbook: {sorted(set(overrides) - used_overrides)}")
    output.mkdir(parents=True, exist_ok=True)
    manifest = output / "input_questions.jsonl"
    _save_manifest(manifest, "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records))
    for name, rows in (("input_questions.csv", records), ("dataset_source.csv", source_records)):
        import io
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        _save_manifest(output / name, buffer.getvalue())
    summary = {"questions": len(records), "categories": category_counts, "full_answer_overrides": len(used_overrides),
               "workbook_sha256": hashlib.sha256(workbook.read_bytes()).hexdigest(),
               "full_answers_sha256": hashlib.sha256(answers.read_bytes()).hexdigest()}
    _save_manifest(output / "dataset_manifest.json", json.dumps(summary, indent=2) + "\n")
    return manifest, summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs" / "full_run")
    parser.add_argument("--workbook", type=Path, default=ROOT / "datatset" / "wealth_management_1000_test_set_questions.xlsx")
    parser.add_argument("--full-answers", type=Path, default=ROOT / "datatset" / "216_questions_full_results.json")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Prepare/validate all inputs without model calls.")
    mode.add_argument("--prepare-knowledge", action="store_true", help="Prepare inputs and the full-run knowledge cache, then stop.")
    mode.add_argument("--resume-crashes-and-pending", action="store_true", help="Retain saved results and run only crashes/unattempted questions.")
    mode.add_argument("--retry-errors-in-place", action="store_true", help="Retry all saved execution failures, preserving successes.")
    parser.add_argument("--limit", type=int, default=0, help="0 runs every question; use a separate folder for smoke tests.")
    args = parser.parse_args(argv)
    if args.limit < 0:
        parser.error("--limit must be non-negative")
    output = inside_root(args.output_dir)
    manifest, summary = prepare_dataset(inside_root(args.workbook), inside_root(args.full_answers), output)
    print(f"Prepared {summary['questions']} questions, {len(summary['categories'])} categories, "
          f"{summary['full_answer_overrides']} full-answer overrides. Output: {output}", flush=True)
    environment = os.environ.copy()
    environment.update(PIPELINE_ENV_FILE=str(ROOT / ".env"), PIPELINE_ENV_OVERRIDE="0",
        KNOWLEDGE_CACHE_DIR=str(output / "knowledge_cache"), KNOWLEDGE_CACHE_FILE="",
        PIPELINE_RUNTIME_DIR=str(output / "runtime"), TEST_QUERY_OFFSET="0", TEST_MAX_WORKERS="1",
        QUERY_SHUFFLE_SEED="", RETRY_QUERY_SPEC_ERRORS_ONLY="0", RESULT_JSONL_FILE=str(output / "raw_pipeline.jsonl"),
        DEBUG_JSONL_FILE=str(output / "raw_pipeline_debug.jsonl"), PYTHONDONTWRITEBYTECODE="1",
        DOMAIN_COMPILATION_MODE="simple", BEDROCK_GPT_OSS_MODEL="openai.gpt-oss-120b-1:0")
    command = [sys.executable, "-u", "-B", str(PIPELINE / "run.py"), "--env-file", str(ROOT / ".env"),
        "--db", str(ROOT / "wealth_management_diverse.db"), "--yaml-dir", str(ROOT / "table_medatada"),
        "--domain-intro", str(ROOT / "domain_intro_latest.prompt"), "--business-rules", str(ROOT / "business_rules_addendum.md"),
        "--questions", str(manifest), "--output", str(output / "raw_pipeline.csv"), "--limit", str(args.limit),
        "--knowledge-mode", "simple", "--agent-consultation", "on"]
    if args.check:
        command.append("--check-inputs")
    elif args.prepare_knowledge:
        command.append("--prepare-knowledge")
    elif args.resume_crashes_and_pending:
        command.append("--resume-crashes-and-pending")
    elif args.retry_errors_in_place:
        command.append("--retry-errors-in-place")
    result = subprocess.run(command, env=environment, cwd=ROOT, check=False)
    if not args.check and not args.prepare_knowledge and (output / "raw_pipeline.csv").is_file():
        from compute_metrics import write_reports
        write_reports(output, input_path=output / "raw_pipeline.csv", allow_partial=True)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
