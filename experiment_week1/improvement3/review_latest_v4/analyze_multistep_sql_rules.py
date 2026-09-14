from __future__ import annotations

import csv
import html
import json
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[3]
WORKBOOK = (
    ROOT
    / "query_specs_improevemnt"
    / "improvement1"
    / "dataset"
    / "verification_results_v2_sql_correct_442.xlsx"
)
OUT_DIR = Path(__file__).resolve().parent
RULEBOOK = OUT_DIR / "MULTISTEP_SQL_RULEBOOK.md"
PER_QUESTION_CSV = OUT_DIR / "multistep_sql_interpretation.csv"
SUMMARY_JSON = OUT_DIR / "multistep_sql_rules_summary.json"


NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


TABLE_LABELS = {
    "ATOM_ENTITY_INVESTOR_PROFILE_001": "investor profile / comparison dimension",
    "ATOM_ENTITY_INVESTMENT_GOAL_001": "investment goal fact",
    "ATOM_ENTITY_PORTFOLIO_HEALTH_001": "portfolio health metric",
    "ATOM_ENTITY_PORTFOLIO_HOLDING_001": "portfolio holding fact",
    "ATOM_ENTITY_SECTOR_ALLOCATION_001": "sector allocation fact",
    "ATOM_EVENT_CASH_FLOW_001": "cash-flow event fact",
    "ATOM_EVENT_REBALANCING_ACTION_001": "rebalancing action event fact",
    "ATOM_EVENT_SCENARIO_REBALANCING_001": "scenario rebalancing event fact",
}


METRIC_RULES = [
    (r"SUM\(current_value-cost\)", "holding gain", "SUM(current_value - cost) at investor grain"),
    (r"SUM\(current_value\)", "holding value", "SUM(current_value) at investor grain"),
    (r"AVG\(returns_pct\)", "holding return", "AVG(returns_pct) at investor grain"),
    (r"SUM\(dividends\)", "dividends", "SUM(dividends) at investor grain"),
    (r"SUM\(taxes_paid\)", "taxes paid", "SUM(taxes_paid) at investor grain"),
    (r"AVG\(progress_pct\)", "goal progress", "AVG(progress_pct) at investor grain"),
    (r"AVG\(shortfall\)", "goal shortfall", "AVG(shortfall) at investor grain"),
    (r"AVG\(avg_sharpe_ratio\)", "goal sharpe", "AVG(avg_sharpe_ratio) at investor grain"),
    (r"AVG\(avg_volatility_pct\)", "goal volatility", "AVG(avg_volatility_pct) at investor grain"),
    (r"AVG\(time_to_goal_months\)", "time to goal", "AVG(time_to_goal_months) at investor grain"),
    (r"MAX\(allocation_pct\)", "allocation concentration", "MAX(allocation_pct) at investor grain"),
    (r"AVG\(allocation_pct\)", "allocation average", "AVG(allocation_pct) at investor grain"),
    (r"SUM\(total_investment\)", "sector investment", "SUM(total_investment) at investor grain"),
    (r"SUM\(amount\)", "net cash flow", "SUM(amount) at investor grain"),
    (r"SUM\(CASE WHEN amount > 0", "cash inflow", "SUM positive amount, else 0"),
    (r"-SUM\(CASE WHEN amount < 0", "cash outflow", "-SUM negative amount, else 0"),
    (r"date >= '2025-01-01'", "2025 cash flow", "CASE date window before investor aggregation"),
    (
        r"AVG\(target_allocation_pct-current_allocation_pct\)",
        "rebalancing gap",
        "AVG(target_allocation_pct - current_allocation_pct) at investor grain",
    ),
    (
        r"SUM\(amount\) AS total_rebalance_amount",
        "rebalancing amount",
        "SUM(amount) at investor grain",
    ),
    (
        r"AVG\(new_allocation_pct-current_allocation_pct\)",
        "scenario change",
        "AVG(new_allocation_pct - current_allocation_pct) at investor grain",
    ),
    (
        r"MAX\(new_allocation_pct-current_allocation_pct\)",
        "max scenario change",
        "MAX(new_allocation_pct - current_allocation_pct) at investor grain",
    ),
]


def read_xlsx_rows(path: Path) -> list[dict[str, str]]:
    with zipfile.ZipFile(path) as zf:
        shared = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root.findall("x:si", NS):
                parts = []
                for text in si.findall(".//x:t", NS):
                    parts.append(text.text or "")
                shared.append("".join(parts))

        sheet = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
        raw_rows: list[dict[str, str]] = []
        for row in sheet.findall(".//x:sheetData/x:row", NS):
            values: dict[str, str] = {}
            for cell in row.findall("x:c", NS):
                ref = cell.attrib.get("r", "")
                col = re.sub(r"\d+", "", ref)
                value_node = cell.find("x:v", NS)
                inline_node = cell.find("x:is/x:t", NS)
                if cell.attrib.get("t") == "s" and value_node is not None:
                    value = shared[int(value_node.text or "0")]
                elif inline_node is not None:
                    value = inline_node.text or ""
                elif value_node is not None:
                    value = value_node.text or ""
                else:
                    value = ""
                values[col] = value
            raw_rows.append(values)

    headers = raw_rows[0]
    col_to_name = {col: name for col, name in headers.items()}
    rows = []
    for raw in raw_rows[1:]:
        rows.append({col_to_name.get(col, col): value for col, value in raw.items()})
    return rows


def normalize_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip().rstrip(";")


def sql_tables(sql: str) -> list[str]:
    return sorted(set(re.findall(r"\bATOM_[A-Z0-9_]+_\d{3}\b", sql)))


def cte_names(sql: str) -> list[str]:
    if not normalize_sql(sql).upper().startswith("WITH "):
        return []
    return re.findall(r"(?:WITH|,)\s*([a-z][a-z0-9_]*)\s+AS\s*\(", sql, flags=re.I)


def all_group_by_clauses(sql: str) -> list[str]:
    clauses = []
    pattern = re.compile(
        r"\bGROUP\s+BY\s+(.+?)(?=\s+(?:HAVING|ORDER\s+BY|LIMIT|SELECT|WITH)\b|[),;]|$)",
        flags=re.I,
    )
    for match in pattern.finditer(normalize_sql(sql)):
        clauses.append(match.group(1).strip())
    return clauses


def final_group_by(sql: str) -> str:
    clauses = all_group_by_clauses(sql)
    return clauses[-1] if clauses else ""


def final_select_group(sql: str) -> str:
    match = re.search(r"\bSELECT\s+(.+?)\s+AS\s+group_value\b", normalize_sql(sql), flags=re.I)
    return match.group(1).strip() if match else ""


def join_summary(sql: str) -> str:
    normalized = normalize_sql(sql)
    joins = re.findall(r"\b((?:LEFT|RIGHT|FULL|INNER|CROSS)\s+)?JOIN\s+([^ ]+)\s+[^ ]+\s+ON\s+(.+?)(?=\s+(?:JOIN|WHERE|GROUP|ORDER|HAVING|LIMIT)\b|$)", normalized, flags=re.I)
    if not joins:
        return ""
    parts = []
    for kind, target, condition in joins:
        join_type = (kind.strip().upper() or "INNER") + " JOIN"
        parts.append(f"{join_type} {target} ON {condition.strip()}")
    return " | ".join(parts)


def aggregate_functions(sql: str) -> list[str]:
    return sorted(set(func.upper() for func in re.findall(r"\b(SUM|AVG|COUNT|MAX|MIN)\s*\(", sql, flags=re.I)))


def metric_rules(sql: str) -> list[str]:
    compact = normalize_sql(sql)
    hits = []
    for pattern, label, rule in METRIC_RULES:
        if re.search(pattern, compact, flags=re.I):
            hits.append(f"{label}: {rule}")
    return hits


def row_interpretation(row: dict[str, str]) -> dict[str, str]:
    sql = normalize_sql(row.get("sql_query", ""))
    tables = sql_tables(sql)
    ctes = cte_names(sql)
    groups = all_group_by_clauses(sql)
    final_group = final_group_by(sql)
    final_select = final_select_group(sql)
    funcs = aggregate_functions(sql)
    metrics = metric_rules(sql)
    has_cte_investor_grain = bool(ctes) and bool(
        re.search(r"\bGROUP\s+BY\s+investor_id\b", sql, flags=re.I)
    )
    final_avg_of_cte_metrics = bool(re.search(r"\bAVG\([a-z]+\.[a-z0-9_]+\)", sql, flags=re.I))
    case_logic = "yes" if re.search(r"\bCASE\s+WHEN\b", sql, flags=re.I) else "no"
    one_line = []
    if has_cte_investor_grain:
        one_line.append("pre-aggregate fact/event tables to investor_id")
    if final_group:
        one_line.append(f"final comparison groups by {final_group}")
    if final_avg_of_cte_metrics:
        one_line.append("final metric averages investor-level CTE outputs")
    if case_logic == "yes":
        one_line.append("conditional CASE is part of metric definition")
    if not one_line:
        one_line.append("direct grouped comparative query")

    return {
        "global_question_id": row.get("global_question_id", ""),
        "question_id": row.get("question_id", ""),
        "source_csv": row.get("source_csv", ""),
        "question": row.get("question", ""),
        "tables_used_declared": row.get("tables_used", ""),
        "tables_in_sql": "; ".join(tables),
        "table_meanings": "; ".join(TABLE_LABELS.get(t, t) for t in tables),
        "cte_names": "; ".join(ctes),
        "all_group_by": "; ".join(groups),
        "final_select_group": final_select,
        "final_group_by": final_group,
        "aggregate_functions": "; ".join(funcs),
        "case_logic": case_logic,
        "join_summary": join_summary(sql),
        "metric_rules_seen": "; ".join(metrics),
        "authoring_rule": "; ".join(one_line),
        "sql_reason": row.get("sql_reason", ""),
        "sql_query": sql,
    }


def markdown_table(rows: list[list[str]]) -> str:
    escaped = []
    for row in rows:
        escaped.append([cell.replace("|", "\\|") for cell in row])
    header = "| " + " | ".join(escaped[0]) + " |"
    sep = "| " + " | ".join("---" for _ in escaped[0]) + " |"
    body = ["| " + " | ".join(row) + " |" for row in escaped[1:]]
    return "\n".join([header, sep, *body])


def write_outputs(rows: list[dict[str, str]]) -> None:
    mc_rows = [row for row in rows if row.get("query_type") == "Multi-step Comparative"]
    interpreted = [row_interpretation(row) for row in mc_rows]

    table_counter = Counter()
    group_counter = Counter()
    aggregate_counter = Counter()
    cte_count = 0
    case_count = 0
    with_count = 0
    final_avg_cte_count = 0
    table_sets = Counter()

    for row in interpreted:
        tables = [t for t in row["tables_in_sql"].split("; ") if t]
        table_counter.update(tables)
        table_sets.update([" + ".join(tables)])
        if row["final_group_by"]:
            group_counter[row["final_group_by"]] += 1
        if row["cte_names"]:
            cte_count += 1
        if row["case_logic"] == "yes":
            case_count += 1
        if row["sql_query"].upper().startswith("WITH "):
            with_count += 1
        if "final metric averages investor-level CTE outputs" in row["authoring_rule"]:
            final_avg_cte_count += 1
        aggregate_counter.update([x for x in row["aggregate_functions"].split("; ") if x])

    with PER_QUESTION_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(interpreted[0].keys()))
        writer.writeheader()
        writer.writerows(interpreted)

    summary = {
        "workbook": str(WORKBOOK),
        "query_type": "Multi-step Comparative",
        "row_count": len(interpreted),
        "with_cte_count": with_count,
        "investor_grain_cte_count": cte_count,
        "case_metric_count": case_count,
        "final_avg_of_cte_metric_count": final_avg_cte_count,
        "tables": table_counter,
        "final_group_by": group_counter,
        "aggregate_functions": aggregate_counter,
        "table_sets": table_sets,
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    top_table_rows = [["SQL table", "Meaning", "Count"]]
    for table, count in table_counter.most_common():
        top_table_rows.append([table, TABLE_LABELS.get(table, ""), str(count)])

    group_rows = [["Final group by", "Count"]]
    for group, count in group_counter.most_common():
        group_rows.append([group, str(count)])

    set_rows = [["Table combination", "Count"]]
    for combo, count in table_sets.most_common(12):
        set_rows.append([combo, str(count)])

    examples = []
    for row in interpreted[:10]:
        examples.append(
            "\n".join(
                [
                    f"### {row['question_id']}",
                    "",
                    f"Question: {html.escape(row['question'])}",
                    "",
                    f"Authoring rule: {row['authoring_rule']}",
                    "",
                    f"Metric rules: {row['metric_rules_seen'] or 'none extracted'}",
                    "",
                    "```sql",
                    row["sql_query"],
                    "```",
                ]
            )
        )

    md = f"""# Multi-step Comparative SQL Rulebook

This file studies only the workbook rows where `query_type = Multi-step Comparative`.
It uses the ground-truth SQL as evidence for how the benchmark author translated
question text into computation. The purpose is to guide V4 decomposition and
validation with general rules, not to hardcode individual answers.

Source workbook: `{WORKBOOK}`

## Scope

- Rows analyzed: {len(interpreted)}
- SQL rows using `WITH` CTEs: {with_count}
- Rows with investor-level CTE aggregation: {cte_count}
- Rows with conditional `CASE` metric logic: {case_count}
- Rows where final metrics average pre-aggregated CTE outputs: {final_avg_cte_count}

## Core Translation Rules

1. Multi-step comparative SQL usually creates a two-stage computation.
   Fact/event sources are first reduced to `investor_id` in CTEs, then the final
   query compares investor groups such as risk tolerance or time horizon.

2. The final comparison group is explicit in both `SELECT ... AS group_value`
   and the final `GROUP BY`. V4 should require the intent decomposition's
   comparison entity or dimension to match this final output grain.

3. When a question compares multiple fact metrics, the SQL avoids raw fact-to-fact
   joins. It joins pre-aggregated investor-level CTEs, which prevents row
   multiplication.

4. Final group metrics often use `AVG(cte.metric)` over investor-level metrics.
   That means phrases like average holding value by risk tolerance are usually
   interpreted as average of each investor's total holding value, not average of
   raw holdings.

5. Metric names have benchmark-specific formulas, but they are reusable semantic
   formulas rather than question-specific answers. Examples include holding gain
   as `SUM(current_value - cost)`, allocation concentration as `MAX(allocation_pct)`,
   scenario change as `AVG(new_allocation_pct - current_allocation_pct)`, and
   rebalancing gap as `AVG(target_allocation_pct - current_allocation_pct)`.

6. Cash-flow metrics use signed amount rules. Net cash flow is `SUM(amount)`,
   inflow is positive amount only, and outflow is the negative of negative amounts.
   Date-scoped cash-flow metrics use `CASE` inside the investor-level aggregation.

7. The SQL uses inner joins for required sources in these rows. The implied
   eligibility is investors that have all required metric sources, after each
   source has been reduced to investor grain.

## Source Frequency

{markdown_table(top_table_rows)}

## Final Grouping Frequency

{markdown_table(group_rows)}

## Common Table Combinations

{markdown_table(set_rows)}

## How To Use This In V4

For multi-step comparative questions, add a SQL-style interpretation contract
between intent decomposition and execution decomposition:

```json
{{
  "comparison_dimension": "risk_tolerance | time_horizon | ...",
  "base_metric_sources": ["goal", "holding", "cash", "rebalance", "scenario"],
  "metric_formulas": ["SUM(current_value-cost)", "AVG(progress_pct)", "..."],
  "source_grain_before_join": "investor_id",
  "final_output_grain": "comparison_dimension",
  "eligibility_join_policy": "inner join required investor-level metric sources",
  "filter_scope": "inside source CTE for raw filters, HAVING/final filter for aggregate filters"
}}
```

The LLM should still infer the meaning. The deterministic validator should only
check structural consistency:

- every requested metric has a source and formula;
- each multi-row fact source is aggregated to investor grain before cross-source joins;
- the final group matches the comparison dimension;
- aggregate thresholds are applied after aggregation;
- raw filters are applied inside the relevant source CTE;
- cash-flow sign and date-window logic are explicit when requested.

## Per-question CSV

The full per-question extraction is saved in:

`{PER_QUESTION_CSV.name}`

## Sample Rows

{chr(10).join(examples)}
"""
    RULEBOOK.write_text(md, encoding="utf-8")


def main() -> None:
    rows = read_xlsx_rows(WORKBOOK)
    write_outputs(rows)
    print(f"Wrote {RULEBOOK}")
    print(f"Wrote {PER_QUESTION_CSV}")
    print(f"Wrote {SUMMARY_JSON}")


if __name__ == "__main__":
    main()
