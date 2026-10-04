"""Offline audit of saved outputs; never imported by the runtime pipeline."""
import argparse
import collections
import csv
import hashlib
import json
import sqlite3
import statistics
from pathlib import Path

csv.field_size_limit(100_000_000)
ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "outputs/openai_gpt_oss_120b/all/test1000"
OUT = Path(__file__).resolve().parent
RUN = BASE / "generic_no_rules_v2_20261003"


def read(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def counts(rows, column="New Status"):
    return dict(collections.Counter(row[column] for row in rows))


def cross(pairs):
    return {" -> ".join(key): count for key, count in collections.Counter(pairs).items()}


def error_tags(errors):
    checks = {
        "unknown_source": lambda e: "Unknown source:" in e or "Unknown base_entity:" in e or ": unknown source " in e,
        "unsupported_requirement_words": lambda e: "unsupported terms" in e,
        "planned_output_absent": lambda e: e.startswith("Planned output"),
        "invalid_ledger_reference": lambda e: "Invalid requirement implementation" in e,
        "unsupported_operator": lambda e: "unsupported operator" in e,
        "unresolved": lambda e: e.startswith("Unresolved requirements"),
        "empty_output_schema": lambda e: "output_schema must contain" in e,
        "unknown_field_operand": lambda e: "is not in" in e or "unknown formula operand" in e,
        "missing_ledger_implementation": lambda e: "Requirement has no implementation" in e,
        "literal_coverage": lambda e: "Filter value" in e,
        "derived_expression_required": lambda e: "derived measure needs an expression" in e,
        "derived_operand_misclassified": lambda e: "unknown or self-referencing formula operand" in e,
        "population_filter_contract": lambda e: "population_filters:" in e,
        "unknown_output_alias": lambda e: "Unknown output column:" in e,
    }
    return [name for name, check in checks.items() if any(check(error) for error in errors)]


def main(replay_sql=False):
    raw_path, grade_path = RUN / "raw_pipeline.csv", RUN / "graded_pipeline_tera.csv"
    raw, graded = read(raw_path), read(grade_path)
    previous_path = BASE / "generic_no_rules_v1_20261003/graded_pipeline_tera.csv"
    failed_path = BASE / "rerun_20261003_023143/raw_pipeline.csv"
    previous, failed = read(previous_path), read(failed_path)
    by_raw = {row["Sample Row ID"]: row for row in raw}
    by_grade = {row["Sample Row ID"]: row for row in graded}
    by_previous = {row["Sample Row ID"]: row for row in previous}
    if len(by_raw) != len(raw) or len(by_grade) != len(graded) or set(by_raw) != set(by_grade):
        raise ValueError("Duplicate IDs or inconsistent raw/graded coverage")
    family, backend, incidence, single_tag = {}, {}, collections.Counter(), collections.Counter()
    warning_grades, empty_grades = collections.Counter(), collections.Counter()
    diagnostic_rows = []
    for row in raw:
        row_id = row["Sample Row ID"]
        grade, old = by_grade[row_id], by_previous.get(row_id, {})
        family.setdefault(row["Source CSV"], collections.Counter())[grade["New Status"]] += 1
        traces = json.loads(row["Node Traces"] or "{}")
        backends = {node.get("backend", "") for node in traces.values()}
        backend_name = next(iter(backends)) if len(backends) == 1 else "mixed"
        backend.setdefault(backend_name, collections.Counter())[grade["New Status"]] += 1
        errors = list(dict.fromkeys(error for node in traces.values() for error in node.get("contract_errors", [])))
        tags = error_tags(errors)
        incidence.update(tags)
        if len(tags) == 1 and row["Failure Stage"] == "Q1:Query_Spec_Contract":
            single_tag.update(tags)
        warnings = list(dict.fromkeys(error for node in traces.values() for error in node.get("contract_warnings", [])))
        if row["New Status"] == "PIPELINE_SUCCESS":
            if warnings:
                warning_grades[grade["New Status"]] += 1
            if row["New Pipeline Result"].startswith("No data") or row["New Pipeline Result"] in ("", "[]"):
                empty_grades[grade["New Status"]] += 1
        diagnostic_rows.append({
            "id": row_id, "question": row["Question"], "family": row["Source CSV"],
            "raw_status": row["New Status"], "grade": grade["New Status"],
            "previous_grade": old.get("New Status", ""), "backend": backend_name,
            "failure_stage": row["Failure Stage"], "error_tags": json.dumps(tags),
            "contract_errors": json.dumps(errors), "contract_warnings": json.dumps(warnings),
            "grader_reason": grade["Original Grade Reason"], "elapsed_seconds": row["Elapsed Seconds"],
            "queries": json.dumps({name: node.get("generated_sql") or node.get("generated_sparql", "")
                                   for name, node in traces.items()}),
        })
    elapsed = sorted(float(row["Elapsed Seconds"]) for row in raw)
    slow = [row for row in raw if float(row["Elapsed Seconds"]) > 300]
    summary = {
        "raw_rows": len(raw), "graded_rows": len(graded), "unique_ids": len(by_grade),
        "versions": counts(raw, "Pipeline Version"), "raw_statuses": counts(raw), "grades": counts(graded),
        "raw_grade_transitions": cross((row["New Status"], by_grade[row["Sample Row ID"]]["New Status"]) for row in raw),
        "failure_stages": counts(raw, "Failure Stage"),
        "families": {name: dict(counter) for name, counter in family.items()},
        "backends": {name: dict(counter) for name, counter in backend.items()},
        "previous_grades": counts(previous),
        "paired_question_text_changes": sum(by_previous[row["Sample Row ID"]]["Question"] != row["Question"]
                                            for row in graded if row["Sample Row ID"] in by_previous),
        "paired_reference_text_changes": sum(by_previous[row["Sample Row ID"]]["Ground Truth"] != row["Ground Truth"]
                                             for row in graded if row["Sample Row ID"] in by_previous),
        "node_count_distribution": dict(collections.Counter(len(json.loads(row["Node Traces"] or "{}")) for row in raw)),
        "paired_previous_transitions": cross((by_previous[row["Sample Row ID"]]["New Status"], row["New Status"])
                                             for row in graded if row["Sample Row ID"] in by_previous),
        "previous_failed_raw_transitions": cross((row["New Status"], by_raw[row["Sample Row ID"]]["New Status"])
                                                 for row in failed if row["Sample Row ID"] in by_raw),
        "recovered_dag_success_grades": dict(collections.Counter(by_grade[row["Sample Row ID"]]["New Status"]
            for row in failed if row["New Status"] == "DAG_NODE_ERROR"
            and by_raw[row["Sample Row ID"]]["New Status"] == "PIPELINE_SUCCESS")),
        "contract_error_incidence_overlapping": dict(incidence),
        "contract_single_tag_rows": dict(single_tag),
        "successful_warning_grades": dict(warning_grades), "successful_empty_grades": dict(empty_grades),
        "latency": {"mean_seconds": statistics.mean(elapsed), "median_seconds": statistics.median(elapsed),
                    "p95_seconds": elapsed[int(.95 * (len(elapsed) - 1))],
                    "p99_seconds": elapsed[int(.99 * (len(elapsed) - 1))],
                    "sum_seconds": sum(elapsed), "over300_rows": len(slow),
                    "over300_sum_seconds": sum(float(row["Elapsed Seconds"]) for row in slow)},
        "file_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in (raw_path, grade_path, previous_path, failed_path)},
    }
    previous_raw = {row['Sample Row ID']: row for row in read(BASE / 'generic_no_rules_v1_20261003/raw_pipeline.csv')}
    older = read(BASE / 'graded_pipeline_openai_gpt_oss_120b_all_test1000_rerun_grader2.csv')
    summary.update({
        'raw_v1_v2_transitions': cross((previous_raw[row['Sample Row ID']]['New Status'], row['New Status']) for row in raw),
        'v1_failure_recoveries': dict(collections.Counter(by_grade[row['Sample Row ID']]['New Status'] for row in raw
            if previous_raw[row['Sample Row ID']]['New Status'] != 'PIPELINE_SUCCESS' and row['New Status'] == 'PIPELINE_SUCCESS')),
        'v1_match_losses_by_v2_stage': dict(collections.Counter(row['Failure Stage'] or 'executed' for row in raw
            if by_previous[row['Sample Row ID']]['New Status'] == 'MATCH' and by_grade[row['Sample Row ID']]['New Status'] != 'MATCH')),
        'older637_transitions': cross((row['New Status'], by_grade[row['Sample Row ID']]['New Status']) for row in older),
        'raw_grade_differences': {column: sum(row[column] != by_grade[row['Sample Row ID']][column] for row in raw)
            for column in ('Question', 'Ground Truth', 'New Pipeline Result', 'Node Traces', 'Pipeline Version')},
        'grader_policy': {column: counts(graded, column) for column in ('Grading Policy', 'Direct LLM Grader Model', 'Grader Label', 'Direct LLM Grading Path')},
        'formula_contract_rows': sum(any('derived measure needs an expression' in e or 'unknown or self-referencing formula operand' in e
            for e in json.loads(row['contract_errors'])) for row in diagnostic_rows),
        'family_stages': {family: counts([row for row in raw if row['Source CSV'] == family], 'Failure Stage') for family in family},
    })
    if replay_sql:
        db = ROOT / "historical_models/openai.gpt-oss-120b-aman/all/train/wealth_management_diverse.db"
        with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as connection:
            connection.row_factory = sqlite3.Row
            queries = {
                "gold_fields": "SELECT 'investment_type' AS field,COUNT(*) AS n FROM ATOM_ENTITY_PORTFOLIO_HOLDING_001 WHERE investment_type='Gold' UNION ALL SELECT 'investment_name',COUNT(*) FROM ATOM_ENTITY_PORTFOLIO_HOLDING_001 WHERE investment_name='Gold'",
                "cash_types": "SELECT type,COUNT(*) AS n FROM ATOM_EVENT_CASH_FLOW_001 GROUP BY type",
                "credit_card_sign": "SELECT SUM(amount) AS stored_sum,SUM(CASE WHEN type='inflow' THEN amount ELSE -amount END) AS invented_case_sum FROM ATOM_EVENT_CASH_FLOW_001 WHERE source='Credit Card'",
                "gold_returns": "SELECT AVG(returns_pct) AS stored_average,AVG(100.0*(current_value-cost)/NULLIF(cost,0)) AS computed_average,COUNT(*) AS eligible_rows FROM ATOM_ENTITY_PORTFOLIO_HOLDING_001 WHERE investment_type='Gold' AND cost IS NOT NULL AND current_value IS NOT NULL",
                "EC125-2T-029": "SELECT p.segment,h.sector,COUNT(DISTINCT p.investor_id) AS investor_count FROM ATOM_ENTITY_INVESTOR_PROFILE_001 p JOIN ATOM_ENTITY_PORTFOLIO_HOLDING_001 h USING(investor_id) GROUP BY p.segment,h.sector",
                "EC125-2T-043": "SELECT p.category,h.sector,COUNT(DISTINCT p.investor_id) AS investor_count FROM ATOM_ENTITY_INVESTOR_PROFILE_001 p JOIN ATOM_ENTITY_PORTFOLIO_HOLDING_001 h USING(investor_id) GROUP BY p.category,h.sector",
                "EC125-3T-022": "SELECT p.time_horizon,COUNT(DISTINCT p.investor_id) AS investor_count FROM ATOM_ENTITY_INVESTOR_PROFILE_001 p JOIN ATOM_ENTITY_PORTFOLIO_HOLDING_001 h USING(investor_id) JOIN ATOM_ENTITY_INVESTMENT_GOAL_001 g USING(investor_id) WHERE h.investment_type='Mutual Fund' AND g.investment_goal='Growth' GROUP BY p.time_horizon",
            }
            replay = {}
            short_ids = {row["Sample Row ID"].split(":")[-1]: row for row in graded}
            for name, query in queries.items():
                result = [dict(row) for row in connection.execute(query)]
                item = {"query": query, "rows": result}
                if name in short_ids:
                    reference = json.loads(short_ids[name]["Ground Truth"])
                    canonical = lambda rows: sorted(json.dumps(row, sort_keys=True) for row in rows)
                    item["exact_reference_match"] = canonical(result) == canonical(reference)
                replay[name] = item
            summary["read_only_sql_replays"] = replay
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    with (OUT / "row_diagnostics.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(diagnostic_rows[0]))
        writer.writeheader()
        writer.writerows(diagnostic_rows)
    print(json.dumps({"rows": len(raw), "grades": summary["grades"], "report_dir": str(OUT)}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay-sql", action="store_true")
    main(parser.parse_args().replay_sql)
