"""Read-only diagnosis of saved V4 reports and selected local Fuseki populations.

Reference SQL is evaluation evidence only; this script is not imported by inference.
"""
import collections
import csv
import hashlib
import json
from decimal import Decimal
from pathlib import Path
import sqlite3
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent / "pipelien_output"
SOURCE = HERE.parent / "run_pipeline_v4"
WORKBOOK = ROOT / "query_specs_improevemnt/improvement1/dataset/verification_results_v2_sql_correct_442.xlsx"
csv.field_size_limit(100_000_000)


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def references():
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(WORKBOOK) as archive:
        strings = ["".join(item.itertext()) for item in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall("m:si", ns)] if "xl/sharedStrings.xml" in archive.namelist() else []
        result = []
        for row in ET.fromstring(archive.read("xl/worksheets/sheet1.xml")).findall("m:sheetData/m:row", ns):
            values = {}
            for cell in row:
                key = "".join(filter(str.isalpha, cell.attrib["r"]))
                values[key] = strings[int(cell.find("m:v", ns).text)] if cell.attrib.get("t") == "s" else "".join(cell.itertext())
            result.append(values)
        headers = result.pop(0)
        return [{headers[k]: v for k, v in row.items()} for row in result]


def query(sparql):
    request = urllib.request.Request("http://127.0.0.1:3030/wealth/query",
        data=urllib.parse.urlencode({"query": "PREFIX wm: <https://wealth.example.org/ontology/>\n" + sparql}).encode(),
        headers={"Accept": "application/sparql-results+json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    return [{key: value["value"] for key, value in row.items()} for row in payload["results"]["bindings"]]


def canonical(rows):
    return sorted(json.dumps(row, sort_keys=True, ensure_ascii=False) for row in rows)


def numeric_crosschecks(reference):
    results = {}
    goals = query("SELECT ?s ?label ?p ?a ?v WHERE {?s a wm:InvestmentGoal . OPTIONAL {?s wm:investmentGoal ?label} OPTIONAL {?s wm:progressPct ?p} OPTIONAL {?s wm:shortfall ?a} OPTIONAL {?s wm:avgVolatilityPct ?v}}")
    cash = query("SELECT ?s ?label ?a WHERE {?s a wm:CashFlow . OPTIONAL {?s wm:amount ?a} OPTIONAL {?s wm:hasCashFlowType ?t . ?t <http://www.w3.org/2000/01/rdf-schema#label> ?label}}")
    for question_id, data in [("MC-001", goals), ("WM-1T-013", cash)]:
        groups = collections.defaultdict(list)
        for row in data:
            groups[row.get("label")].append(row)
        output = []
        for label, items in groups.items():
            row = {"investment_goal" if question_id == "MC-001" else "type": label}
            measures = [("p", "avg_progress_pct"), ("a", "avg_shortfall"), ("v", "avg_volatility_pct")] if question_id == "MC-001" else [("a", "total_amount")]
            for field, alias in measures:
                values = [Decimal(item[field]) for item in items if field in item]
                total = sum(values)
                row[alias] = float(round(total / len(values) if question_id == "MC-001" else total, 2)) if values else None
            if question_id != "MC-001":
                row["transaction_count"] = len(items)
            output.append(row)
        expected = json.loads(next(row["ground_truth_answer"] for row in reference.values() if row["question_id"] == question_id))
        results[question_id] = {"rows": output, "exact_match_after_rounding": canonical(output) == canonical(expected)}
    return results


def comparative_sql_crosschecks(reference):
    # Explicit mappings below belong ONLY to diagnosis of the supplied SQL. They
    # are not a proposed inference rule or a production class-name mapping.
    sources = {
        "ATOM_ENTITY_INVESTOR_PROFILE_001": ("Investor", [("investor_id", "investorId", "TEXT"), ("category", "category", "TEXT")]),
        "ATOM_ENTITY_PORTFOLIO_HOLDING_001": ("PortfolioHolding", [("investor_id", "investorId", "TEXT")] + [(sql, rdf, "REAL") for sql, rdf in [("current_value", "currentValue"), ("cost", "cost"), ("returns_pct", "returnsPct"), ("dividends", "dividends"), ("taxes_paid", "taxesPaid")]]),
        "ATOM_ENTITY_INVESTMENT_GOAL_001": ("InvestmentGoal", [("investor_id", "investorId", "TEXT")] + [(sql, rdf, "REAL") for sql, rdf in [("progress_pct", "progressPct"), ("shortfall", "shortfall"), ("avg_sharpe_ratio", "avgSharpeRatio"), ("avg_volatility_pct", "avgVolatilityPct"), ("time_to_goal_months", "timeToGoalMonths")]]),
        "ATOM_ENTITY_PORTFOLIO_HEALTH_001": ("PortfolioHealth", [("investor_id", "investorId", "TEXT"), ("risk_score", "riskScore", "REAL"), ("liquidity_score", "liquidityScore", "REAL")]),
    }
    results = {"source_rows": {}}
    with sqlite3.connect(":memory:") as database:
        database.row_factory = sqlite3.Row
        for table, (cls, fields) in sources.items():
            bindings = " ".join(f"OPTIONAL {{?s wm:{rdf} ?{sql}}}" for sql, rdf, _ in fields)
            data = query("SELECT ?s " + " ".join("?" + field[0] for field in fields) + f" WHERE {{?s a wm:{cls} . {bindings}}}")
            if len(data) != len({row["s"] for row in data}):
                raise ValueError("Multivalued RDF properties require explicit row reconstruction: " + table)
            database.execute(f"CREATE TABLE {table} (" + ", ".join(sql + " " + kind for sql, _, kind in fields) + ")")
            database.executemany(f"INSERT INTO {table} VALUES (" + ",".join("?" for _ in fields) + ")", [tuple(row.get(sql) for sql, _, _ in fields) for row in data])
            results["source_rows"][table] = len(data)
        for question_id in ("MC-006", "MC-035"):
            ref = next(row for row in reference.values() if row["question_id"] == question_id)
            output = [dict(row) for row in database.execute(ref["sql_query"])]
            results[question_id] = {"rows": output, "exact_match_after_rounding": canonical(output) == canonical(json.loads(ref["ground_truth_answer"]))}
    return results


def main():
    graded = [row for path in sorted(REPORTS.glob("graded_v4_simple*terra.csv")) for row in rows(path)]
    debug = [row for path in sorted(REPORTS.glob("v4_simple*_debug.csv")) for row in rows(path)]
    reference = {row["global_question_id"]: row for row in references()}
    selected_ids = {"WM-1T-013", "WM-2T-002", "MC-001", "MC-002", "MC-006", "MC-035", "MC-068"}
    evidence = {
        "scope": "Saved 192-question V4 run; local database probes are current-state checks, not an end-to-end rerun.",
        "total": len(graded), "unique_ids": len({row["Sample Row ID"] for row in graded}),
        "execution": dict(collections.Counter(row["New Status"] for row in graded)),
        "grades": dict(collections.Counter(row["Grade Status"] for row in graded)),
        "comparative_grades": dict(collections.Counter(row["Grade Status"] for row in graded if ":MC-" in row["Sample Row ID"])),
        "missing_retrieval_final_failures": sum(row["New Status"] == "FINAL_SPEC_ERROR" and "Missing retrieval:" in row["Validation Reason"] for row in debug),
        "sources": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(REPORTS.glob("*v4_simple*.csv"))},
        "source_manifest_checks": {}, "cases": [], "local_probes": {},
    }
    for path in sorted(REPORTS.glob("v4_simple*.manifest.json")):
        manifest = json.loads(path.read_text())
        evidence["source_manifest_checks"][path.name] = [name for name, expected in manifest["source_files"].items()
            if not (SOURCE / name).exists() or hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() != expected]
    for row in debug:
        if row["Sample Row ID"].split(":")[-1] not in selected_ids:
            continue
        case = {key: row[key] for key in ("Sample Row ID", "Question", "New Status", "Debug Retrieved Classes", "Debug Subquestions", "Debug SPARQL", "Debug Final Spec")}
        case["reference"] = reference.get(row["Sample Row ID"])
        evidence["cases"].append(case)
    probes = {
        "goal_population": "SELECT (COUNT(?s) AS ?all_rows) (COUNT(?p) AS ?progress_present) (COUNT(?a) AS ?shortfall_present) (COUNT(?v) AS ?volatility_present) WHERE { ?s a wm:InvestmentGoal . OPTIONAL {?s wm:progressPct ?p} OPTIONAL {?s wm:shortfall ?a} OPTIONAL {?s wm:avgVolatilityPct ?v} }",
        "goal_complete_cases": "SELECT (COUNT(?s) AS ?complete_rows) WHERE { ?s a wm:InvestmentGoal; wm:progressPct ?p; wm:shortfall ?a; wm:avgVolatilityPct ?v . }",
        "goal_independent_averages": "SELECT ?label (AVG(?p) AS ?progress) (AVG(?a) AS ?shortfall) (AVG(?v) AS ?volatility) WHERE { ?s a wm:InvestmentGoal . OPTIONAL {?s wm:investmentGoal ?label} OPTIONAL {?s wm:progressPct ?p} OPTIONAL {?s wm:shortfall ?a} OPTIONAL {?s wm:avgVolatilityPct ?v} } GROUP BY ?label",
        "cashflow_population": "SELECT (COUNT(?s) AS ?all_rows) (COUNT(?a) AS ?amount_present) (COUNT(?t) AS ?type_present) WHERE { ?s a wm:CashFlow . OPTIONAL {?s wm:amount ?a} OPTIONAL {?s wm:hasCashFlowType ?t} }",
        "cashflow_raw_counts": "SELECT ?label (COUNT(?s) AS ?n) (SUM(?a) AS ?amount) WHERE { ?s a wm:CashFlow . OPTIONAL {?s wm:amount ?a} OPTIONAL {?s wm:hasCashFlowType ?t . ?t <http://www.w3.org/2000/01/rdf-schema#label> ?label} } GROUP BY ?label",
        "investor_link_types": "SELECT DISTINCT ?p ?target WHERE {?s a wm:Investor; ?p ?o . ?o a ?target}",
        "investor_categories": "SELECT ?category (COUNT(?s) AS ?n) WHERE {?s a wm:Investor . OPTIONAL {?s wm:category ?category}} GROUP BY ?category",
        "date_datatype": "SELECT ?dtype (COUNT(?v) AS ?n) WHERE {?s a wm:CashFlow; wm:date ?v . BIND(DATATYPE(?v) AS ?dtype)} GROUP BY ?dtype",
        "date_string_comparison": 'SELECT (COUNT(?s) AS ?n) WHERE {?s a wm:CashFlow; wm:date ?v . FILTER(?v >= "2025-01-01"^^<http://www.w3.org/2001/XMLSchema#string> && ?v <= "2025-12-31"^^<http://www.w3.org/2001/XMLSchema#string>)}',
        "date_typed_comparison": 'SELECT (COUNT(?s) AS ?n) WHERE {?s a wm:CashFlow; wm:date ?v . FILTER(?v >= "2025-01-01"^^<http://www.w3.org/2001/XMLSchema#date> && ?v < "2026-01-01"^^<http://www.w3.org/2001/XMLSchema#date>)}',
    }
    for name, sparql in probes.items():
        try:
            evidence["local_probes"][name] = {"sparql": sparql, "rows": query(sparql)}
        except Exception as exc:
            evidence["local_probes"][name] = {"sparql": sparql, "error": str(exc)}
    for name, check in [("python_numeric_crosschecks", numeric_crosschecks), ("comparative_sql_crosschecks", comparative_sql_crosschecks)]:
        try:
            evidence[name] = check(reference)
        except Exception as exc:
            evidence[name] = {"error": str(exc)}
    (HERE / "evidence.json").write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({key: value for key, value in evidence.items() if key not in {"cases", "sources"}}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
