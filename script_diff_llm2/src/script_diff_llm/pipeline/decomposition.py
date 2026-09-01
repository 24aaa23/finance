from typing import Any, Callable


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
        if isinstance(parsed, list):
            return {"nodes": parsed}
        return parsed
    except Exception as error:
        print(f"   [!] Decompose API error: {error}")
        return {"nodes": []}
