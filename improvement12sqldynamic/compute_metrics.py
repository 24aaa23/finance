"""Compute one AOP run's accuracy, token latency, inference cost and efficiency."""
import argparse
from collections import Counter, defaultdict
import csv
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
SEMANTIC = {"MATCH", "MISMATCH", "PARTIAL", "OTHER"}
_limit = sys.maxsize
while True:
    try:
        csv.field_size_limit(_limit)
        break
    except OverflowError:
        _limit //= 10


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def numeric(value):
    if value is None or str(value).strip() == "":
        return None
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"Invalid non-negative measurement: {value!r}")
    return number


def total(rows, field):
    values = [numeric(row.get(field)) for row in rows]
    return sum(values) if values and all(value is not None for value in values) else None


def measured_total(rows, field):
    return sum(value for row in rows if (value := numeric(row.get(field))) is not None)


def ratio(numerator, denominator, factor=1):
    return numerator / denominator * factor if numerator is not None and denominator else None


def calculate(rows, prices, graded=False):
    statuses = Counter(str(row.get("New Status", "")).strip().upper() for row in rows)
    pending = sum(not row.get("Direct LLM Grading Path") for row in rows) if graded else len(rows)
    accuracy_ready = graded and not pending
    inputs, outputs = total(rows, "Generation Input Tokens"), total(rows, "Generation Output Tokens")
    seconds, execution = total(rows, "Generation Latency Seconds"), total(rows, "Elapsed Seconds")
    input_cost = inputs * prices["input_usd_per_million"] / 1e6 if inputs is not None else None
    output_cost = outputs * prices["output_usd_per_million"] / 1e6 if outputs is not None else None
    cost = input_cost + output_cost if input_cost is not None and output_cost is not None else None
    return {"Questions": len(rows), "MATCH": statuses["MATCH"], "MISMATCH": statuses["MISMATCH"],
        "PARTIAL": statuses["PARTIAL"], "OTHER / ERROR": sum(n for status, n in statuses.items() if status not in {"MATCH", "MISMATCH", "PARTIAL"}),
        "Ungraded Questions": pending, "Accuracy (%)": ratio(statuses["MATCH"], len(rows), 100) if accuracy_ready else None,
        "Generation Input Tokens": inputs, "Generation Output Tokens": outputs,
        "Measured Input Tokens": measured_total(rows, "Generation Input Tokens"),
        "Measured Output Tokens": measured_total(rows, "Generation Output Tokens"),
        "Generation Latency Seconds": seconds, "Seconds per Output Token": ratio(seconds, outputs),
        "Milliseconds per Output Token": ratio(seconds, outputs, 1000),
        "Input Cost (USD)": input_cost, "Output Cost (USD)": output_cost,
        "Inference Cost (USD)": cost, "Average Cost per Question (USD)": ratio(cost, len(rows)),
        "Total Execution Seconds": execution,
        "Execution Efficiency (MATCH per second)": ratio(statuses["MATCH"], execution) if accuracy_ready else None,
        "Model Calls": total(rows, "Model Calls"), "Failed Model Calls": total(rows, "Failed Model Calls"),
        "Calls Missing Token Usage": total(rows, "Calls Missing Token Usage"),
        "Grader API Failures": sum(row.get("Direct LLM Grading Path") == "direct_llm_grader_exception" for row in rows)}


def write_csv(path, rows, fields=None):
    fields = fields or list(rows[0])
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def groups(rows, field, prices, graded):
    partitions = defaultdict(list)
    for row in rows:
        partitions[row.get(field) or "<blank>"].append(row)
    names = ("Questions", "MATCH", "MISMATCH", "PARTIAL", "OTHER / ERROR", "Ungraded Questions", "Accuracy (%)")
    return [{field: key, **{name: value for name, value in calculate(group, prices, graded).items() if name in names}}
            for key, group in sorted(partitions.items())]


def display(value):
    if value is None:
        return "Not available"
    if isinstance(value, float):
        return f"{value:.9f}".rstrip("0").rstrip(".")
    return str(value)


def markdown_table(rows):
    fields = list(rows[0])
    return ["| " + " | ".join(fields) + " |", "|" + "---|" * len(fields)] + [
        "| " + " | ".join(display(row.get(field)).replace("|", "\\|") for field in fields) + " |" for row in rows]


def write_reports(output, input_path=None, config_path=None, allow_partial=False):
    output = Path(output).resolve()
    config = json.loads(Path(config_path or ROOT / "metrics_config.json").read_text(encoding="utf-8"))
    for field in ("input_usd_per_million", "output_usd_per_million"):
        config[field] = numeric(config[field])
        if config[field] is None:
            raise ValueError(f"Specify {field} in metrics_config.json.")
    raw_path = output / "raw_pipeline.csv"
    if not raw_path.is_file() and (output / "raw_pipeline_v9.csv").is_file():
        raw_path = output / "raw_pipeline_v9.csv"
    source = Path(input_path) if input_path else output / "graded_pipeline.csv"
    if not source.is_file() and not input_path:
        source = raw_path
    rows = read_csv(source)
    inputs = read_csv(output / "input_questions.csv")
    reference = {row["Sample Row ID"]: row for row in inputs}
    ids = [row.get("Sample Row ID", "") for row in rows]
    if len(reference) != len(inputs) or len(set(ids)) != len(ids) or any(not value for value in ids):
        raise ValueError("Input/report question IDs must be unique and nonempty.")
    unexpected = set(ids) - set(reference)
    missing = set(reference) - set(ids)
    if unexpected or (missing and not allow_partial):
        raise ValueError(f"Report does not cover the dataset: {len(missing)} missing, {len(unexpected)} unexpected IDs. Use --allow-partial for an incomplete run.")
    for row in rows:
        if row.get("Question") != reference[row["Sample Row ID"]]["Question"]:
            raise ValueError(f"Question differs from the archived input: {row['Sample Row ID']}")
    if source.resolve() != raw_path.resolve() and raw_path.is_file():
        raw_records = {row["Sample Row ID"]: row for row in read_csv(raw_path)}
        for row in rows:
            raw = raw_records.get(row["Sample Row ID"])
            if raw is None or any(row.get(field, "") != raw.get(field, "") for field in
                                  ("Question", "Ground Truth", "New Pipeline Result", "Timing Run ID")):
                raise ValueError("Grading is stale relative to the raw run; grade the current raw report into a new output file.")
    targets = {row.get("Target Model") for row in rows if row.get("Target Model")}
    if targets and targets != {config["model_id"]}:
        raise ValueError(f"Target model differs from pricing configuration: {sorted(targets)}")
    graded = bool(rows and "Direct LLM Grading Path" in rows[0])
    values = calculate(rows, config, graded)
    values.update({"Expected Dataset Questions": len(inputs), "Missing Dataset Questions": len(missing)})
    units = {"Accuracy (%)": "%", "Generation Latency Seconds": "s", "Total Execution Seconds": "s",
             "Seconds per Output Token": "s/token", "Milliseconds per Output Token": "ms/token",
             "Execution Efficiency (MATCH per second)": "MATCH/s", "Average Cost per Question (USD)": "USD/question"}
    metric_rows = [{"Metric": key, "Value": value, "Unit": "USD" if "(USD)" in key else units.get(key, "count"),
                    "Scope": "saved per-question attempts; startup/grader excluded",
                    "Availability": "available" if value is not None else "ungraded, missing usage, or zero denominator"}
                   for key, value in values.items()]
    write_csv(output / "metrics.csv", metric_rows)
    query_groups, category_groups = groups(rows, "Query Type", config, graded), groups(rows, "Dataset Type", config, graded)
    fields = ["Questions", "MATCH", "MISMATCH", "PARTIAL", "OTHER / ERROR", "Ungraded Questions", "Accuracy (%)"]
    write_csv(output / "grading_by_query_type.csv", query_groups, ["Query Type", *fields])
    write_csv(output / "grading_by_category.csv", category_groups, ["Dataset Type", *fields])
    calls_path = output / "model_calls.csv"
    all_calls = read_csv(calls_path) if calls_path.is_file() else []
    if len({row["call_id"] for row in all_calls}) != len(all_calls):
        raise ValueError("Duplicate model-call IDs in telemetry.")
    startup = [row for row in all_calls if not row.get("query_id")]
    overhead = [{"Scope": label, "Model Calls": len(calls),
        "Input Tokens": total(calls, "prompt_tokens"), "Output Tokens": total(calls, "completion_tokens"),
        "Measured Input Tokens": measured_total(calls, "prompt_tokens"),
        "Measured Output Tokens": measured_total(calls, "completion_tokens"),
        "Model Seconds": measured_total(calls, "seconds"),
        "Calls Missing Usage": sum(numeric(row.get("prompt_tokens")) is None or numeric(row.get("completion_tokens")) is None for row in calls)}
        for label, calls in (("startup only", startup), ("all pipeline requests across saved runs/attempts", all_calls))]
    write_csv(output / "model_usage_summary.csv", overhead)
    result = {"pipeline": config["pipeline"], "model": config["model_id"], "source": source.name,
              "graded": graded, "complete_dataset": not missing, "metrics": values, "pricing": config}
    (output / "metrics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = [f"# {config['pipeline']} metrics", "", f"Model: `{config['model_id']}`. Source: `{source.name}`.", "",
        f"Dataset coverage: {len(rows)}/{len(inputs)} questions. Accuracy is {'graded' if graded else 'pending grading'}.", "",
        "## Metrics", "", *markdown_table([{"Metric": key, "Value": value} for key, value in values.items()]), "",
        "## By query type", "", *(markdown_table(query_groups) if query_groups else ["No completed rows."]), "",
        "## By dataset category", "", *(markdown_table(category_groups) if category_groups else ["No completed rows."]), "",
        "## Definitions and scope", "",
        "- Accuracy = MATCH / total saved questions * 100; ungraded accuracy is unavailable.",
        "- Token latency = summed model-request seconds / total output tokens; this includes request overhead and SDK retries.",
        "- Inference cost = input tokens * input price / 1M + output tokens * output price / 1M.",
        "- Average cost = inference cost / questions.",
        "- Execution efficiency = MATCH / summed per-question Elapsed Seconds, rather than concurrent wall-clock time.",
        "- AOP call counts vary by question. All planning, consultation and repair calls within each saved attempt are included.",
        "- Startup knowledge compilation and previous/retried attempts are shown separately in model_usage_summary.csv and model_calls.csv.",
        "- Missing provider usage stays unknown; partial measured totals are not complete totals or verified billing.",
        "- These summaries exclude the separate grader's tokens and cost.", f"- Pricing: {config['pricing_note']}", ""]
    if values["Grader API Failures"]:
        lines.extend(["Grader API failures are counted as non-MATCH outcomes in the requested formula; resolve those failures before treating this as a reliable accuracy estimate.", ""])
    (output / "metrics.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Metrics saved in {output}; {len(rows)}/{len(inputs)} questions; "
          f"accuracy: {display(values['Accuracy (%)'])}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs" / "full_run")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    write_reports(args.output_dir, args.input, args.config, args.allow_partial)


if __name__ == "__main__":
    main()
