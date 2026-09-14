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
    requirements = selected.get("answer_requirements", {})
    if not isinstance(requirements, dict):
        requirements = {}
    # These are schema-facing names, not a second plan.  They make the original
    # answer shape available to the existing Query_Spec and Final_Spec contracts.
    requirements["required_projection"] = [
        str(field) for field in requirements.get("required_projection", [])
        if isinstance(field, (str, int, float)) and str(field).strip()
    ]
    requirements["group_by"] = [
        str(field) for field in requirements.get("group_by", [])
        if isinstance(field, (str, int, float)) and str(field).strip()
    ]
    requirements["metrics"] = [
        metric for metric in requirements.get("metrics", []) if isinstance(metric, dict)
    ]
    requirements["preserve_null_groups"] = bool(requirements.get("preserve_null_groups", False))
    requirements["requires_distinct_entities"] = bool(requirements.get("requires_distinct_entities", False))
    requirements["required_branch_ids"] = [item["id"] for item in cleaned_subquestions]
    selected["answer_requirements"] = requirements
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
    decomposition_feedback = inputs.get("decomposition_feedback", "")
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
- A Query_Spec branch retrieves exactly one source class. When facts come from different
  source classes, create one source-focused subquestion per class and condition.
- Use only existing merge/operator names: Filter_Aggregate, Math_Compute, Order_By,
  Set_Intersect, Set_Union, Set_Difference, Integrate.
- Add answer_requirements using exact schema field names where available. This is a
  compact answer-shape checklist, not an execution plan: include required_projection
  (raw display/entity fields), group_by, metrics (operation, input_column, and output_column
  when applicable), preserve_null_groups, and requires_distinct_entities. Every selected
  subquestion is a required condition and is checked downstream.
- Return only valid JSON.

Repair feedback from a previous decomposition, if any:
{decomposition_feedback}

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
      "answer_requirements": {{
        "required_projection": ["schema field names required in the final answer"],
        "group_by": ["schema grouping fields"],
        "metrics": [{{"operation": "count|sum|avg|min|max", "input_column": "raw metric field", "output_column": "final metric field"}}],
        "preserve_null_groups": false,
        "requires_distinct_entities": false
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
    "answer_requirements": {{
      "required_projection": [], "group_by": [], "metrics": [],
      "preserve_null_groups": false, "requires_distinct_entities": false
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
