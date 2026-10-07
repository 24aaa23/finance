"""Compare graded normal/paraphrased outputs without calling a model."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path


def read_results(path):
    csv.field_size_limit(100_000_000)
    paths = sorted(set(path.glob("*/graded_pipeline_v9_final_answers.csv")) |
                   set(path.glob("*/graded_pipeline.csv"))) if path.is_dir() else [path]
    result = {}
    for source in paths:
        with source.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = set(reader.fieldnames or [])
            modern = {"Sample Row ID", "New Status", "Direct LLM Grading Path"}.issubset(fields)
            if not {"Sample Row ID", "Grade Status"}.issubset(fields) and not modern:
                raise ValueError(f"Not a graded result file: {source}")
            for row in reader:
                if modern and "Grade Status" not in row:
                    row["Grade Status"] = row["New Status"]
                key = row["Sample Row ID"]
                if not key or key in result:
                    raise ValueError("Missing or duplicate question ID: " + key)
                result[key] = row
    if not result:
        raise ValueError("No graded results found.")
    return result


def compare(normal, paraphrased):
    keys = normal.keys() & paraphrased.keys()
    if not keys:
        raise ValueError("No matched question IDs.")
    transitions = Counter((normal[k]["Grade Status"], paraphrased[k]["Grade Status"]) for k in keys)
    return {"paired_questions": len(keys), "only_normal": len(normal.keys() - paraphrased.keys()),
            "only_paraphrased": len(paraphrased.keys() - normal.keys()),
            "normal_match_pct": 100 * sum(normal[k]["Grade Status"] == "MATCH" for k in keys) / len(keys),
            "paraphrased_match_pct": 100 * sum(paraphrased[k]["Grade Status"] == "MATCH" for k in keys) / len(keys),
            "both_correct": transitions[("MATCH", "MATCH")],
            "regression_ids": sorted(k for k in keys if normal[k]["Grade Status"] == "MATCH" and paraphrased[k]["Grade Status"] != "MATCH"),
            "transitions": {f"{a} -> {b}": n for (a, b), n in sorted(transitions.items())}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--normal", required=True, type=Path)
    parser.add_argument("--paraphrased", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(compare(read_results(args.normal), read_results(args.paraphrased)), indent=2))
