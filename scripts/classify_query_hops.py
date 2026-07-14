import argparse
import os
import re
from collections import deque
from typing import Any

import pandas as pd


BASE_DIR = "/DATAAMAN/financial"
DEFAULT_INPUT = os.path.join(BASE_DIR, "AOP_Analysis_2.xlsx")
FALLBACK_INPUT = os.path.join(BASE_DIR, "AOP_Analysis_2_status_not_match.xlsx")
OUTPUT_DIR = os.path.join(BASE_DIR, "Pipeline_Outputs")
DEFAULT_SHEET = "All_Queries"
DEFAULT_SPARQL_COLUMN = "Generated SPARQL"


CLASS_KEYWORDS = {
    "InvestorProfile": [
        "investor", "investors", "profile", "risk profile", "risk tolerance",
        "time horizon", "sector focus", "preferred sector", "preferred segment",
        "preferred category", "liquidity rating",
    ],
    "PortfolioHolding": [
        "holding", "holdings", "portfolio", "investment cost", "current value",
        "taxes", "tax", "dividend income", "dividends", "returns", "category",
        "segment", "investment type", "asset", "etf",
    ],
    "InvestmentGoal": [
        "goal", "goals", "target amount", "progress", "shortfall",
        "sharpe", "volatility", "annual return", "post tax return",
    ],
    "CashFlow": [
        "cash flow", "transaction", "transactions", "sip", "swp", "withdrawal",
        "deposit", "amount", "source", "dividend transaction", "inflow", "outflow",
    ],
    "SectorAllocation": [
        "sector allocation", "allocation percentage", "allocation pct",
        "allocated sector", "actual portfolio", "sector has", "sector with",
        "total investment", "sector's current allocation",
    ],
    "PortfolioHealth": [
        "portfolio health", "health status", "health score", "liquidity score",
        "diversification score", "goal match", "risk score",
    ],
    "RebalancingAction": [
        "rebalancing action", "rebalancing actions", "rebalance", "buy recommendation",
        "sell recommendation", "underweight", "overweight", "drift", "target allocation",
        "current allocation", "deviates", "deviation",
    ],
    "ScenarioRebalancing": [
        "scenario", "interest rate hike", "affected by", "affected assets",
        "market crash", "inflation", "stress",
    ],
    "InvestmentType": [
        "investment type", "corporate bond", "aif", "reit", "equity", "debt",
        "mutual fund", "bond",
    ],
    "AssetClass": [
        "asset class", "category", "categories", "equity", "debt", "hybrid",
    ],
    "Sector": [
        "sector", "sectors", "technology", "private equity", "government",
        "banking", "healthcare", "automobile",
    ],
    "Segment": [
        "segment", "large cap", "mid cap", "small cap", "private equity",
    ],
}


OPERATION_KEYWORDS = {
    "aggregation": [
        "count", "total", "sum", "average", "avg", "mean", "maximum", "minimum",
        "max", "min", "highest", "lowest", "largest", "smallest", "most", "least",
    ],
    "grouping": [
        "per", "grouped by", "by category", "by sector", "by segment",
        "by investment type", "categorised", "categorized", "for each",
    ],
    "filtering": [
        "where", "whose", "with", "for investor", "for investors", "below",
        "above", "exceeds", "under", "over", "in 2022", "last 12 months",
        "excluding", "without",
    ],
    "comparison": [
        "compare", "match", "matches", "versus", "vs", "difference",
        "deviates", "deviation", "between", "correlation", "relationship",
        "does", "do ",
    ],
    "temporal": [
        "in 2022", "in 2023", "last 12 months", "date", "year",
        "holding duration", "purchase date",
    ],
    "negation": [
        "no ", "not ", "never", "excluding", "without",
    ],
}


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def contains_any(text: str, phrases: list[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def detect_classes(question: str) -> list[str]:
    text = normalize_text(question)
    detected = []
    for class_name, phrases in CLASS_KEYWORDS.items():
        if contains_any(text, phrases):
            detected.append(class_name)

    # Reduce broad context classes when the fact table already carries the literal.
    if "PortfolioHolding" in detected and "AssetClass" in detected and "category" in text:
        detected = [c for c in detected if c != "AssetClass"]
    if "PortfolioHolding" in detected and "InvestmentType" in detected and "investment type" in text:
        detected = [c for c in detected if c != "InvestmentType"]
    if "SectorAllocation" in detected and "Sector" in detected:
        detected = [c for c in detected if c != "Sector"]

    return detected


def detect_operations(question: str) -> list[str]:
    text = normalize_text(question)
    operations = []
    for name, phrases in OPERATION_KEYWORDS.items():
        if contains_any(text, phrases):
            operations.append(name)
    return operations


def count_conditions(question: str) -> int:
    text = normalize_text(question)
    markers = [
        "where", "whose", "with", "and", "or", "below", "above", "exceeds",
        "under", "over", "for investor", "affected by", "moderate", "high",
        "conservative", "growth", "buy", "sell",
    ]
    return sum(1 for marker in markers if marker in text)


def classify_hops(question: str) -> dict[str, Any]:
    text = normalize_text(question)
    classes = detect_classes(question)
    operations = detect_operations(question)
    condition_count = count_conditions(question)

    has_aggregation = "aggregation" in operations
    has_grouping = "grouping" in operations
    has_comparison = "comparison" in operations
    has_temporal = "temporal" in operations
    has_scenario = "ScenarioRebalancing" in classes or "affected by" in text
    has_rebalancing = "RebalancingAction" in classes
    has_health = "PortfolioHealth" in classes

    class_count = len(classes)
    hop_count = 1
    reasons = []

    if class_count <= 1 and not has_aggregation and not has_comparison and not has_grouping:
        hop_count = 1
        reasons.append("Direct lookup from one detected entity/table.")
    else:
        if class_count >= 2 or has_aggregation or has_grouping:
            hop_count = max(hop_count, 2)
            reasons.append("Needs at least retrieval plus aggregation/group/filter or a join.")
        if class_count >= 3 or has_comparison or condition_count >= 2:
            hop_count = max(hop_count, 3)
            reasons.append("Combines multiple constraints, joins, or comparison logic.")

    multi_reasons = []
    if class_count >= 4:
        multi_reasons.append("four or more detected graph concepts")
    if has_scenario and has_health:
        multi_reasons.append("scenario condition plus portfolio health condition")
    if has_rebalancing and (has_comparison or has_aggregation or condition_count >= 2):
        multi_reasons.append("rebalancing drift/recommendation with derived comparison or aggregation")
    if has_comparison and has_aggregation and class_count >= 3:
        multi_reasons.append("comparison plus aggregation across several concepts")
    if contains_any(text, ["correlation", "relationship between", "compare the preferred", "matches their stated"]):
        multi_reasons.append("explicit cross-fact reasoning/comparison")

    if multi_reasons:
        hop_label = "multi-hop"
        estimated_hops = "4+"
        reasons.append("Multi-hop because it requires " + "; ".join(multi_reasons) + ".")
    elif hop_count == 1:
        hop_label = "1-hop"
        estimated_hops = "1"
    elif hop_count == 2:
        hop_label = "2-hop"
        estimated_hops = "2"
    else:
        hop_label = "3-hop"
        estimated_hops = "3"

    needs_derived_reasoning = bool(
        has_comparison
        or has_rebalancing
        or has_scenario
        or contains_any(text, ["duration", "deviation", "correlation", "match"])
    )

    return {
        "Hop Label": hop_label,
        "Estimated Hop Count": estimated_hops,
        "Detected Classes": ", ".join(classes) if classes else "",
        "Detected Operations": ", ".join(operations) if operations else "",
        "Condition Count": condition_count,
        "Needs Derived Reasoning": "yes" if needs_derived_reasoning else "no",
        "Hop Reason": " ".join(reasons),
    }


def strip_sparql_comments(sparql: str) -> str:
    return "\n".join(line.split("#", 1)[0] for line in str(sparql or "").splitlines())


def extract_where_body(sparql: str) -> str:
    text = strip_sparql_comments(sparql)
    first_brace = text.find("{")
    if first_brace == -1:
        return ""

    depth = 0
    for idx in range(first_brace, len(text)):
        char = text[idx]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[first_brace + 1:idx]
    return text[first_brace + 1:]


def clean_sparql_term(term: str) -> str:
    term = term.strip().rstrip(";,.")
    if term.endswith(")"):
        term = term.rstrip(")")
    return term


def parse_sparql_triples(sparql: str) -> list[tuple[str, str, str]]:
    body = extract_where_body(sparql)
    if not body:
        return []

    body = re.sub(r"\b(FILTER|BIND)\s*\([^)]*(?:\)[^)]*)*\)\s*\.?", "\n", body, flags=re.I)
    body = re.sub(r"\bVALUES\s+\?\w+\s*\{[^}]*\}", "\n", body, flags=re.I)
    body = re.sub(r"\b(OPTIONAL|MINUS|FILTER\s+NOT\s+EXISTS)\s*\{", "{", body, flags=re.I)
    body = body.replace("{", "\n").replace("}", "\n")

    triples = []
    statements = [stmt.strip() for stmt in re.split(r"\s*\.\s*", body) if stmt.strip()]

    for statement in statements:
        parts = [part.strip() for part in statement.split(";") if part.strip()]
        subject = None

        for idx, part in enumerate(parts):
            tokens = part.split()
            if idx == 0:
                if len(tokens) < 3:
                    continue
                subject, predicate, obj = tokens[0], tokens[1], " ".join(tokens[2:])
            else:
                if subject is None or len(tokens) < 2:
                    continue
                predicate, obj = tokens[0], " ".join(tokens[1:])

            subject = clean_sparql_term(subject)
            predicate = clean_sparql_term(predicate)
            obj = clean_sparql_term(obj)
            if subject and predicate and obj:
                triples.append((subject, predicate, obj))

    return triples


def is_variable(term: str) -> bool:
    return term.startswith("?")


def longest_shortest_path(adjacency: dict[str, set[str]]) -> int:
    if not adjacency:
        return 0

    longest = 0
    for start in adjacency:
        distances = {start: 0}
        queue = deque([start])
        while queue:
            node = queue.popleft()
            for neighbor in adjacency[node]:
                if neighbor not in distances:
                    distances[neighbor] = distances[node] + 1
                    queue.append(neighbor)
        if distances:
            longest = max(longest, max(distances.values()))
    return longest


def classify_hops_from_sparql(sparql: str) -> dict[str, Any]:
    triples = parse_sparql_triples(sparql)
    if not triples:
        return {
            "Hop Label": "",
            "Estimated Hop Count": "",
            "Detected Classes": "",
            "Detected Operations": "",
            "Condition Count": "",
            "Needs Derived Reasoning": "",
            "Hop Reason": "No parseable SPARQL triple patterns found.",
            "Hop Classification Source": "none",
            "SPARQL Triple Count": 0,
            "SPARQL Join Count": 0,
            "SPARQL Longest Variable Path": 0,
        }

    variables = set()
    class_terms = set()
    adjacency: dict[str, set[str]] = {}
    join_edges = set()

    for subject, predicate, obj in triples:
        if predicate in {"a", "rdf:type"}:
            class_terms.add(obj)

        subject_is_var = is_variable(subject)
        object_is_var = is_variable(obj)
        if subject_is_var:
            variables.add(subject)
            adjacency.setdefault(subject, set())
        if object_is_var:
            variables.add(obj)
            adjacency.setdefault(obj, set())

        if subject_is_var and object_is_var:
            left, right = sorted((subject, obj))
            join_edges.add((left, right))
            adjacency[subject].add(obj)
            adjacency[obj].add(subject)

    join_count = len(join_edges)
    variable_path = longest_shortest_path(adjacency)

    has_aggregation = bool(re.search(r"\b(COUNT|SUM|AVG|MIN|MAX)\s*\(", sparql or "", flags=re.I))
    has_grouping = bool(re.search(r"\bGROUP\s+BY\b", sparql or "", flags=re.I))
    has_filter = bool(re.search(r"\bFILTER\b|\bVALUES\b", sparql or "", flags=re.I))
    has_negation = bool(re.search(r"\bMINUS\b|FILTER\s+NOT\s+EXISTS", sparql or "", flags=re.I))
    has_optional = bool(re.search(r"\bOPTIONAL\b", sparql or "", flags=re.I))

    derived_ops = []
    if has_aggregation:
        derived_ops.append("aggregation")
    if has_grouping:
        derived_ops.append("grouping")
    if has_filter:
        derived_ops.append("filtering")
    if has_negation:
        derived_ops.append("negation")
    if has_optional:
        derived_ops.append("optional-pattern")

    if join_count == 0 and not has_aggregation and not has_grouping:
        hop_label = "1-hop"
        estimated_hops = "1"
        reason = "SPARQL has no variable-to-variable joins and no aggregation/grouping."
    elif join_count <= 1 and variable_path <= 1:
        hop_label = "2-hop"
        estimated_hops = "2"
        reason = "SPARQL has one joined variable edge or one derived operation."
    elif join_count <= 2 and variable_path <= 2:
        hop_label = "3-hop"
        estimated_hops = "3"
        reason = "SPARQL joins a chain of variables with path length up to 2."
    else:
        hop_label = "multi-hop"
        estimated_hops = "4+"
        reason = "SPARQL contains more than two joins or a longer variable path."

    if hop_label != "multi-hop" and len(class_terms) >= 4:
        hop_label = "multi-hop"
        estimated_hops = "4+"
        reason = "SPARQL touches four or more RDF classes."

    return {
        "Hop Label": hop_label,
        "Estimated Hop Count": estimated_hops,
        "Detected Classes": ", ".join(sorted(class_terms)),
        "Detected Operations": ", ".join(derived_ops),
        "Condition Count": int(has_filter) + int(has_negation) + int(has_optional),
        "Needs Derived Reasoning": "yes" if derived_ops else "no",
        "Hop Reason": reason,
        "Hop Classification Source": "sparql",
        "SPARQL Triple Count": len(triples),
        "SPARQL Join Count": join_count,
        "SPARQL Longest Variable Path": variable_path,
    }


def classify_row(row: pd.Series, sparql_column: str) -> dict[str, Any]:
    sparql = row.get(sparql_column, "") if sparql_column in row else ""
    if isinstance(sparql, str) and sparql.strip():
        sparql_label = classify_hops_from_sparql(sparql)
        if sparql_label["Hop Label"]:
            return sparql_label

    question_label = classify_hops(row.get("Question", ""))
    question_label["Hop Classification Source"] = "question_heuristic"
    question_label["SPARQL Triple Count"] = ""
    question_label["SPARQL Join Count"] = ""
    question_label["SPARQL Longest Variable Path"] = ""
    return question_label


def read_input_table(input_file: str, sheet_name: str) -> tuple[pd.DataFrame, str]:
    if input_file.lower().endswith(".csv"):
        return pd.read_csv(input_file), "csv"
    return read_question_sheet(input_file, sheet_name)


def read_question_sheet(input_file: str, sheet_name: str) -> tuple[pd.DataFrame, str]:
    """Read the requested sheet, falling back to the first sheet with a Question column."""
    xls = pd.ExcelFile(input_file)
    candidate_sheets = []

    if sheet_name and sheet_name.lower() != "auto":
        candidate_sheets.append(sheet_name)
    candidate_sheets.extend(sheet for sheet in xls.sheet_names if sheet not in candidate_sheets)

    for sheet in candidate_sheets:
        df = pd.read_excel(input_file, sheet_name=sheet)
        if "Question" in df.columns:
            return df, sheet

    raise ValueError(
        "Input workbook must contain a sheet with a 'Question' column. "
        f"Checked sheets: {', '.join(xls.sheet_names)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify questions as 1-hop, 2-hop, 3-hop, or multi-hop.")
    parser.add_argument("--input", default=os.getenv("HOP_INPUT_FILE") or DEFAULT_INPUT)
    parser.add_argument("--sheet", default=os.getenv("HOP_SHEET", DEFAULT_SHEET))
    parser.add_argument("--sparql-column", default=os.getenv("HOP_SPARQL_COLUMN", DEFAULT_SPARQL_COLUMN))
    parser.add_argument("--output-prefix", default=os.path.join(OUTPUT_DIR, "Query_Hop_Classification"))
    parser.add_argument("--limit", type=int, default=int(os.getenv("HOP_QUERY_LIMIT", "0")))
    args = parser.parse_args()

    input_file = args.input
    if not os.path.exists(input_file) and input_file == DEFAULT_INPUT:
        input_file = FALLBACK_INPUT
    if not os.path.exists(input_file):
        raise FileNotFoundError(input_file)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    df, sheet_used = read_input_table(input_file, args.sheet)
    if args.limit:
        df = df.head(args.limit).copy()
    if "Question" not in df.columns and args.sparql_column not in df.columns:
        raise ValueError(
            "Input must contain either a 'Question' column or "
            f"a '{args.sparql_column}' SPARQL column."
        )

    labels = [classify_row(row, args.sparql_column) for _, row in df.iterrows()]
    out_df = pd.concat([df.reset_index(drop=True), pd.DataFrame(labels)], axis=1)

    csv_path = f"{args.output_prefix}.csv"
    xlsx_path = f"{args.output_prefix}.xlsx"
    out_df.to_csv(csv_path, index=False)
    out_df.to_excel(xlsx_path, index=False)

    print(f"Input: {input_file}")
    print(f"Sheet: {sheet_used}")
    print(f"SPARQL column: {args.sparql_column if args.sparql_column in df.columns else 'not found; used question heuristic'}")
    print(f"Rows classified: {len(out_df)}")
    print("\nHop distribution:")
    print(out_df["Hop Label"].value_counts().to_string())
    print(f"\nSaved CSV:  {csv_path}")
    print(f"Saved XLSX: {xlsx_path}")


if __name__ == "__main__":
    main()
