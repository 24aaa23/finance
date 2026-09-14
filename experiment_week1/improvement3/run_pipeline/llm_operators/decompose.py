"""Decompose operator for the improvement3 decompose-first pipeline."""

from ..common import (
    Any,
    Dict,
    LOCAL_MODEL,
    api_logger,
    json,
)
from ..clients import build_llm_messages
from ..utils import parse_llm_json


def _cleanup_decomposition(raw_decomposition: Any, query: str, retrieved_tables: list) -> Dict[str, Any]:
    if isinstance(raw_decomposition, list):
        raw_decomposition = {
            "decomposition_candidates": raw_decomposition,
            "selected_decomposition": raw_decomposition[0] if raw_decomposition else {},
        }
    if not isinstance(raw_decomposition, dict):
        raw_decomposition = {}

    candidates = raw_decomposition.get("decomposition_candidates", [])
    if not isinstance(candidates, list):
        candidates = []

    selected = raw_decomposition.get("selected_decomposition", {})
    if not isinstance(selected, dict):
        selected = candidates[0] if candidates and isinstance(candidates[0], dict) else {}

    subquestions = selected.get("subquestions", [])
    if not isinstance(subquestions, list):
        subquestions = []
    if not subquestions:
        subquestions = [
            {
                "id": "q1",
                "question": query,
                "purpose": "Answer the original question as one KG retrieval branch.",
                "depends_on": [],
            }
        ]

    cleaned_subquestions = []
    for index, subquestion in enumerate(subquestions, 1):
        if not isinstance(subquestion, dict):
            subquestion = {"question": str(subquestion)}
        cleaned_subquestions.append({
            "id": str(subquestion.get("id") or f"q{index}"),
            "question": str(subquestion.get("question") or query),
            "purpose": str(subquestion.get("purpose") or ""),
            "depends_on": subquestion.get("depends_on", []) if isinstance(subquestion.get("depends_on", []), list) else [],
        })

    merge_strategy = selected.get("merge_strategy") or selected.get("merge_plan") or {}
    if not isinstance(merge_strategy, dict):
        merge_strategy = {}
    merge_strategy.setdefault("required", len(cleaned_subquestions) > 1)
    merge_strategy.setdefault("operator", "Integrate" if len(cleaned_subquestions) > 1 else None)
    merge_strategy.setdefault("join_key", None)
    merge_strategy.setdefault("reason", None)

    selected["subquestions"] = cleaned_subquestions
    selected["merge_strategy"] = merge_strategy
    selected.setdefault("required_classes", retrieved_tables)
    selected.setdefault("reason", "Selected decomposition normalized by Decompose cleanup.")

    return {
        "decomposition_candidates": candidates,
        "selected_decomposition": selected,
    }


def semantic_decompose_question(inputs: Dict[str, Any], client: Any, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    """
    Operator: Decompose
    Creates multiple decomposition candidates and selects one before DAG planning.
    """

    query = inputs.get("query", "")
    retrieved_tables = inputs.get("retrieved_tables", [])
    global_schema = inputs.get("global_schema", {})
    schema_details = {
        cls: global_schema[cls]
        for cls in retrieved_tables
        if cls in global_schema
    } or global_schema

    prompt = f"""
You are the Decompose operator for an Agent-Oriented Pipeline.

Break the original user question into smaller KG-answerable questions BEFORE DAG planning.
Generate exactly 3 decomposition candidates, compare them, and select the best one.

Original User Question:
{query}

Retrieved Classes:
{retrieved_tables}

Schema Details:
{json.dumps(schema_details, indent=2)}

Rules:
- Do not write SPARQL.
- Do not create a DAG here.
- Each subquestion should be answerable by a simple Query_Spec -> Generate -> Scan branch.
- Keep aggregation, ranking, formulas, set logic, and merging for downstream operators.
- Prefer 1 subquestion for simple lookup questions.
- Use 2 or more subquestions only when the original question genuinely needs separate retrievals.
- Use only existing merge/operator names: Filter_Aggregate, Math_Compute, Order_By,
  Set_Intersect, Set_Union, Set_Difference, Integrate.
- Return only valid JSON.

Output JSON exactly like this:
{{
  "decomposition_candidates": [
    {{
      "id": "candidate_1",
      "subquestions": [
        {{
          "id": "q1",
          "question": "small KG-answerable question",
          "purpose": "why this branch is needed",
          "depends_on": []
        }}
      ],
      "merge_strategy": {{
        "required": false,
        "operator": null,
        "join_key": null,
        "reason": null
      }},
      "reason": "short reason"
    }}
  ],
  "selected_decomposition_id": "candidate_1",
  "selected_decomposition": {{
    "id": "candidate_1",
    "subquestions": [],
    "merge_strategy": {{
      "required": false,
      "operator": null,
      "join_key": null,
      "reason": null
    }},
    "reason": "why selected"
  }}
}}
"""

    api_logger.log_call(query, "Decompose")
    request = {
        "model": model,
        "messages": build_llm_messages("decompose", prompt),
    }
    if not model.lower().startswith("gpt-5"):
        request["temperature"] = 0.2
    response = client.chat.completions.create(**request)

    parsed = parse_llm_json(
        response.choices[0].message.content,
        {},
        "Decompose",
    )
    cleaned = _cleanup_decomposition(parsed, query, retrieved_tables)
    return cleaned
