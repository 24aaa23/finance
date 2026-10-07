"""Resume saved question-type reports; counts come from this experiment's input manifests."""
import argparse
import csv
import json
import math
from pathlib import Path
import subprocess
import sys

PIPELINE_DIR = Path(__file__).resolve().parents[1]
EXPERIMENT_DIR = PIPELINE_DIR.parent
sys.path.insert(0, str(PIPELINE_DIR))
from _bootstrap import bootstrap
bootstrap()
from run_pipeline_v3_sql.retry_batch import read_retry_report, crash_and_pending_records
from run_pipeline_v3_sql.run_identity import sha256_file
from run_pipeline_v3_sql.input_paths import add_input_arguments, input_arguments

DATASETS = {
    "benchmark": "WM", "at_risk_critical": "ARC", "batch_status": "BSQ",
    "enrichment_context": "EC", "multi_step_comparative": "MC",
    "reference_compliance": "RC", "scoring_quantitative": "SQA",
    "temporal_transaction": "TT",
}


def selection(report, questions, database):
    """Read and verify the saved cohort before authorizing any model call."""
    _, saved = read_retry_report(report)
    manifest = json.loads(Path(str(report) + ".manifest.json").read_text(encoding="utf-8"))
    for key, path in (("questions", questions), ("sqlite_database", database)):
        if manifest.get("input_files", {}).get(key, {}).get("sha256") != sha256_file(path):
            raise ValueError(f"{report}: original {key} changed; cannot resume these saved results.")
    with questions.open(encoding="utf-8-sig", newline="") as handle:
        source_rows = [json.loads(line) for line in handle if line.strip()] if questions.suffix.lower() == ".jsonl" else list(csv.DictReader(handle))
    records = [{"Sample Row ID": str(row.get("Sample Row ID", row.get("global_question_id", "")))} for row in source_rows]
    pending = crash_and_pending_records(saved, records)
    saved_ids = {row["Sample Row ID"] for row in saved}
    new_count = sum(row["Sample Row ID"] not in saved_ids for row in pending)
    return manifest, saved, pending, len(records), new_count


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--type", choices=tuple(DATASETS), help="One type; omit to run all eight sequentially.")
    parser.add_argument("--output-root", type=Path, default=EXPERIMENT_DIR / "outputs" / "question_types")
    parser.add_argument("--report-name", default="raw_pipeline_v9.csv")
    parser.add_argument("--questions-root", type=Path, help="Optional source manifest root; default is --output-root.")
    parser.add_argument("--env-file", type=Path, default=EXPERIMENT_DIR / ".env")
    parser.add_argument("--query-delay", type=float, default=0)
    parser.add_argument("--dry-run", action="store_true", help="Show selections without writes or API calls.")
    add_input_arguments(parser)
    args = parser.parse_args(argv)
    if not math.isfinite(args.query_delay) or args.query_delay < 0:
        parser.error("--query-delay must be finite and non-negative")
    if Path(args.report_name).name != args.report_name:
        parser.error("--report-name must be a filename, not a path")
    selected_types = [args.type] if args.type else list(DATASETS)
    jobs, total, queued = [], 0, 0
    # Preflight every selected report before launching the first child.
    for name in selected_types:
        report = (args.output_root / name / args.report_name).resolve()
        questions_root = args.questions_root or args.output_root
        questions = (questions_root / name / "input_questions.jsonl").resolve()
        if not questions.is_file():
            questions = (questions_root / (DATASETS[name] + ".csv")).resolve()
        manifest, saved, pending, expected, new_count = selection(report, questions, args.db)
        total += expected
        queued += len(pending)
        print(f"{name}: {len(saved)}/{expected} saved; {len(pending)-new_count} crashes to retry; "
              f"{new_count} unattempted; {len(saved)-(len(pending)-new_count)} saved rows retained.", flush=True)
        jobs.append((name, report, questions, manifest))
    print(f"Selected datasets: {total} questions; {queued} queued. Query delay: {args.query_delay:g}s.", flush=True)
    if args.dry_run:
        return 0
    for name, report, questions, manifest in jobs:
        # Re-read since another terminal may have finished work after preflight.
        _, _, pending, _, _ = selection(report, questions, args.db)
        if not pending:
            print(f"[SKIP] {name}: no crashes or unattempted questions.", flush=True)
            continue
        command = [sys.executable, "-u", "-B", str(PIPELINE_DIR / "run.py"),
                   *input_arguments(args), "--env-file", str(args.env_file.resolve()),
                   "--questions", str(questions), "--output", str(report),
                   "--resume-crashes-and-pending", "--query-delay", str(args.query_delay)]
        for option in ("query_understanding", "contract_checks", "agent_consultation"):
            command.extend(["--" + option.replace("_", "-"),
                            "on" if manifest.get("configuration", {}).get(option, True) else "off"])
        print(f"[RESUME] {name}", flush=True)
        result = subprocess.run(command, check=False)
        if result.returncode:
            return result.returncode
        _, _, remaining, _, _ = selection(report, questions, args.db)
        if remaining:
            print(f"[STOPPED] {name}: {len(remaining)} crashes/unattempted questions remain. "
                  "Resolve the service interruption, then rerun this same command.", flush=True)
            return 75
    print(f"[COMPLETE] Every selected question has a saved result ({total} total). "
          "Other execution errors were retained; answer correctness still requires grading.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
