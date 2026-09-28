import re
from typing import Any, Callable


DOMAIN_MARKERS = {
    "profile": ("investor", "risk tolerance", "risk_tolerance", "time horizon", "segment", "category"),
    "holding": ("holding", "investment type", "purchase", "returns_pct", "dividend", "taxes paid"),
    "goal": ("goal", "shortfall", "progress_pct", "volatility", "sharpe"),
    "health": ("portfolio health", "risk score", "risk_score", "liquidity", "diversification", "goal match"),
    "cash_flow": ("cash flow", "cash-flow", "cashflow", "deposit", "withdrawal", "transaction"),
    "allocation": ("sector allocation", "allocation_pct", "allocation concentration", "sector investment"),
    "rebalancing": ("rebalanc", "manual override", "de-risking", "tactical", "action"),
    "scenario": ("scenario", "bear market", "bull market", "allocation change"),
}


def _mentioned_domains(text: str) -> set[str]:
    lowered = str(text or "").lower()
    return {
        domain
        for domain, markers in DOMAIN_MARKERS.items()
        if any(marker in lowered for marker in markers)
    }


def _fallback_single_sql(query: str, reason: str) -> dict[str, Any]:
    print(f"[WARN] {reason} Falling back to one complete SQL subquery.")
    return {
        "nodes": [{
            "id": "Q1",
            "description": query,
            "operator": "Subquery",
            "backend": "SQL",
            "inputs": [],
            "outputs": [],
        }]
    }


def _ensure_domain_coverage(query: str, parsed: Any) -> dict[str, Any]:
    if isinstance(parsed, list):
        parsed = {"nodes": parsed}
    if not isinstance(parsed, dict):
        return _fallback_single_sql(query, "Decomposition was not a JSON object.")
    nodes = parsed.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return parsed
    query_domains = _mentioned_domains(query)
    conjunctive = any(marker in f" {query.lower()} " for marker in [
        " and ", " both ", " also ", " as well as ", " using two ",
        " using three ", " using four ", " using five ",
    ])
    if len(query_domains) < 2 or not conjunctive:
        return parsed

    years = sorted(set(re.findall(r"\b(?:19|20)\d{2}\b", query)))
    if years and len(nodes) > 1:
        temporal_domains = {"holding", "goal", "cash_flow", "rebalancing", "scenario"}
        for node in nodes:
            if not isinstance(node, dict) or str(node.get("operator") or "Subquery") != "Subquery":
                continue
            description = str(node.get("description") or "")
            if not (_mentioned_domains(description) & temporal_domains):
                continue
            missing_years = [year for year in years if year not in description]
            if missing_years:
                node["description"] = (
                    description.rstrip(". ")
                    + f" during {', '.join(missing_years)}."
                )
    plan_text = " ".join(
        str(node.get("description") or "")
        for node in nodes
        if isinstance(node, dict) and str(node.get("operator") or "Subquery") == "Subquery"
    )
    covered = _mentioned_domains(plan_text)
    missing = sorted(query_domains - covered)
    if missing:
        return _fallback_single_sql(
            query,
            f"Decomposition omitted required domain(s): {', '.join(missing)}.",
        )
    return parsed


def semantic_decompose(
    inputs: dict[str, Any],
    client: Any,
    model: str,
    parse_json_fn: Callable[[str, Any, str], Any],
) -> dict[str, Any]:
    query = inputs.get("query", "")
    prompt = f"""
You are the Decompose operator. Your task is to decompose a natural language query into a set of executable subqueries that form a Directed Acyclic Graph (DAG).
The goal is to separate operations when they can be run on different backends (SQL vs KG) or when they can be run in parallel.
Available backends for subqueries: SQL, KG.
Use SQL for aggregation, ranking, or conventional relational filters.
Use KG for relationship traversal and multi-hop entity connections.

DECOMPOSITION RULES:
- Prefer the smallest correct DAG. If one subquery can answer the question directly, keep it as one node.
- Do not introduce abstract intermediate nodes (for example category-level or label-level nodes) when the final answer target is already investor-level and can be retrieved directly.
- For queries asking which entities violate a rule, have no matching related record, are missing something, or satisfy a direct anti-condition, prefer a single anti-join style subquery over a multi-node DAG unless different backends are genuinely required.
- Use set operators only when the user query truly requires combining independently meaningful result sets.
- Do not decompose a direct anti-join or existence test into upstream "all X", "all Y", then a downstream recomputation if one direct filtered subquery would preserve semantics better.
- If downstream nodes depend on upstream outputs, the downstream descriptions must explicitly refine or transform those outputs rather than restating the original broad query.
- Every declared output field should correspond to something a backend can realistically emit. Avoid invented semantic names when a simple key like investor_id or category is enough.

User Query: "{query}"

Output ONLY a JSON object representing the DAG with this exact structure:
{{
  "nodes": [
    {{
      "id": "Q1",
      "description": "Natural language description of this subquery",
      "operator": "Subquery", // Use 'Subquery' for backend queries, or a set operator like 'Set_Intersect', 'Set_Union'
      "backend": "SQL", // SQL or KG (leave empty if operator is a Set operator)
      "inputs": [
         {{
           "name": "input_field_name",
           "source": "Q0.output_field_name",
           "type": "entity_id[]"
         }}
      ],
      "outputs": [
         {{
           "name": "output_field_name",
           "type": "entity_id[]"
         }}
      ]
    }}
  ]
}}
Ensure the DAG is acyclic and all input sources match an upstream node's output. Do NOT split a single SQL-able aggregation into multiple nodes unless necessary.
"""
    request = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        response = client.chat.completions.create(**request)
        raw_text = response.choices[0].message.content
        parsed = parse_json_fn(raw_text, {"nodes": []}, "Decompose")
        return _ensure_domain_coverage(query, parsed)
    except Exception as error:
        print(f"   [!] Decompose API error: {error}")
        return {"nodes": []}
