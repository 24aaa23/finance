import re
import json
from typing import Any, Callable

from script_diff_llm.pipeline.domain_context import append_domain_context, relevant_domain_entries


def _ensure_domain_coverage(query: str, parsed: Any) -> dict[str, Any]:
    """Legacy name: preserve single-node scope without domain keyword rules."""
    if isinstance(parsed, list):
        parsed = {"nodes": parsed}
    if not isinstance(parsed, dict) or not isinstance(parsed.get("nodes"), list):
        return {"nodes": []}
    nodes = parsed["nodes"]
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str) or not node["id"]:
            return {"nodes": []}
        if not isinstance(node.get("inputs", []), list) or not isinstance(node.get("outputs", []), list):
            return {"nodes": []}
        if any(not isinstance(item, dict) for item in node.get("inputs", []) + node.get("outputs", [])):
            return {"nodes": []}
    if len(nodes) == 1 and isinstance(nodes[0], dict) and nodes[0].get("operator", "Subquery") == "Subquery":
        nodes[0] = {**nodes[0], "description": query}
    elif len(nodes) > 1:
        # The model may split a question, but it must be able to point each
        # backend node at source text. A fabricated or unquoted scope is not
        # safe to execute as an independent subquery.
        normalized_query = " ".join(str(query).casefold().split())
        for node in nodes:
            if node.get("operator", "Subquery") != "Subquery":
                continue
            clauses = node.get("scope_clauses")
            if not isinstance(clauses, list) or not clauses or any(
                not isinstance(clause, str)
                or not clause.strip()
                or " ".join(clause.casefold().split()) not in normalized_query
                for clause in clauses
            ):
                return {"nodes": []}
    # Dates belong to the predicates that mention them, not every event node.
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
- Do not introduce abstract intermediate nodes when the final answer target is already an entity and can be retrieved directly.
- Assign each requested condition and output to a node using scope_clauses quoted verbatim from the question. Keep date filters on the clauses they modify; do not copy every year to every branch.
- Preserve the user's domain terms, literals, predicates, and temporal scope. Do not expand ambiguous terms using world knowledge or invent definitions for stored metrics.
- Ground interpretations in the available schema below. A single-node plan must retain the original question verbatim as its description.
- For queries asking which entities violate a rule, have no matching related record, are missing something, or satisfy a direct anti-condition, prefer a single anti-join style subquery over a multi-node DAG unless different backends are genuinely required.
- Use set operators only when the user query truly requires combining independently meaningful result sets.
- Do not decompose a direct anti-join or existence test into upstream "all X", "all Y", then a downstream recomputation if one direct filtered subquery would preserve semantics better.
- If downstream nodes depend on upstream outputs, the downstream descriptions must explicitly refine or transform those outputs rather than restating the original broad query.
- Every declared output field should correspond to something a backend can realistically emit. Avoid invented semantic names when a simple physical key, label, group field, or metric alias is enough.

User Query: "{query}"
Available Schema (runtime metadata, not examples or reference answers):
{json.dumps(inputs.get('schema_context', {}), ensure_ascii=False)}

Output ONLY a JSON object representing the DAG with this exact structure:
{{
  "nodes": [
    {{
      "id": "Q1",
      "description": "Natural language description of this subquery",
      "operator": "Subquery",
      "backend": "SQL",
      "inputs": [
         {{
           "name": "input_field_name",
           "source": "Q0.output_field_name",
           "type": "entity_id[]"
         }}
      ],
      "scope_clauses": ["verbatim clause(s) from the question assigned to this node"],
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
    prompt = append_domain_context(prompt, relevant_domain_entries(
        inputs.get("domain_context"), query, terminology_only=True,
    ))
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
