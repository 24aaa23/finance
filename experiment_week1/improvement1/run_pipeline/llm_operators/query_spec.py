"""Query_Spec operator and its helpers."""

from ..common import (
    Any,
    Dict,
    LOCAL_MODEL,
    api_logger,
    json,
    re,
)
from ..clients import build_llm_messages
from ..utils import normalize_for_compare, parse_llm_json


def semantic_build_query_spec(inputs: Dict[str, Any], client: Any, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    """
    Operator: Query_Spec
    Convert the natural language question into a schema-grounded computation plan.
    This does not generate SPARQL; Generate uses this JSON as its contract.
    """

    query = inputs.get("query", "")
    retrieved_tables = inputs.get("retrieved_tables", [])

    schema_details = inputs.get("schema_details")
    if not schema_details:
        global_schema = inputs.get("global_schema", {})
        schema_details = {
            cls: global_schema[cls]
            for cls in retrieved_tables
            if cls in global_schema
        }
        if not schema_details:
            schema_details = global_schema

    prompt = f"""
You are the Query_Spec operator.

Your task is NOT to write SPARQL.
Your task is to convert the user question into a schema-grounded JSON computation plan.

User Query:
{query}

Retrieved Classes:
{retrieved_tables}

Schema Details:
{json.dumps(schema_details, indent=2)}

IMPORTANT:
- Use only classes and fields present in Schema Details.
- Do not invent classes.
- Do not invent fields.
- Do not write SPARQL.
- Return only valid JSON.

INSTRUCTIONS:

1. Identify the base entity.
   Usually this is the entity over which records should be compared, such as Investor or investor_id.

2. Identify the entity key.
   This is the field used to connect related records, for example investor_id, goal_id, portfolio_id, holding_id, etc.
   Use only a key visible in Schema Details.

3. Identify grouping.
   If the question says "across X", "by X", "per X", "for each X", or "grouped by X",
   put that field in group_by.
   Group by exactly what the user asks:
   - If the user asks for each investor, holding, goal, cash flow, transaction, or portfolio, group by that entity identity field/profile/name.
   - If the user asks by investment goal, risk tolerance, cash-flow type, source, scenario, segment, time horizon, category, or another attribute, group by that attribute value, not by the owner entity ID.
   - For category/type/attribute group_by fields, preserve missing values as a NULL group.

4. Identify all requested measures.
   A measure is a value the answer must compute or compare.
   Examples: average cash flow, total dividend, risk score, goal match, scenario change,
   rebalancing amount, count of investors.

5. For each measure, map it to source_class, field, formula, per_entity_operation,
   and final_operation.

6. Formula rules:
   If the user asks for "change", "difference", "gap", "movement", or "progress difference",
   infer a formula using available numeric fields only.

7. Aggregation grain rules:
   If the query compares groups using event tables, prefer two-level aggregation:
   first aggregate per entity_key, then aggregate by group_by.

8. Join policy rules:
   - Use "inner_join" when the query asks comparison using related tables and does not mention missing records.
   - Use "left_join" only if the question asks to include entities even when related records are missing.
   - Use "anti_join" for questions containing "without", "never", "no", or "not having".
   - Use "union_required" if the question asks for combined records from alternative sources.

9. Ranking rules:
   If the question asks highest, lowest, top, bottom, maximum, minimum, best, or worst,
   specify ranking.metric, ranking.direction, and ranking.limit.

10. Execution strategy:
   Choose one of:
   - "single_sparql" for simple one-table or safe joins.
   - "preaggregate_sparql" for multi-table aggregation where each event table should be grouped before final grouping.
   Do not output unsupported multi-scan or pandas-merge strategies.
   The current executor supports only one executable SPARQL query.
   For complex multi-table questions, choose preaggregate_sparql and keep the query small.

11. Output schema:
   List the expected final answer columns. Generate and Validate will use this as guidance,
   but executable schema-grounded SPARQL is more important than satisfying a brittle spec shape.

Return JSON in exactly this structure:

{{
  "query_type": "point_lookup|aggregation|comparative|ranking|boolean|set_logic|multi_step",
  "base_entity": "...",
  "entity_key": "...",
  "join_policy": "inner_join|left_join|anti_join|union_required",
  "grain": {{
    "pre_aggregate_by": ["..."],
    "final_group_by": ["..."]
  }},
  "group_by": [
    {{
      "output_name": "group_value",
      "source_class": "...",
      "field": "..."
    }}
  ],
  "filters": [
    {{
      "source_class": "...",
      "field": "...",
      "operator": "=|>|<|>=|<=|contains|not_contains|between|in|not_in",
      "value": "...",
      "value_type": "string|number|date|list"
    }}
  ],
  "measures": [
    {{
      "output_name": "...",
      "source_class": "...",
      "field": "...",
      "formula": null,
      "formula_fields": [],
      "per_entity_operation": "SUM|AVG|COUNT|MIN|MAX|null",
      "final_operation": "SUM|AVG|COUNT|MIN|MAX|null",
      "requires_distinct": false
    }}
  ],
  "ranking": {{
    "required": false,
    "metric": null,
    "direction": null,
    "limit": null
  }},
  "required_classes": ["..."],
  "execution_strategy": "single_sparql|preaggregate_sparql",
  "output_schema": ["..."],
  "reason": "short explanation of how the query was converted into this plan"
}}
"""

    default_spec = {
        "query_type": "multi_step",
        "base_entity": None,
        "entity_key": None,
        "join_policy": "inner_join",
        "grain": {
            "pre_aggregate_by": [],
            "final_group_by": []
        },
        "group_by": [],
        "filters": [],
        "measures": [],
        "ranking": {
            "required": False,
            "metric": None,
            "direction": None,
            "limit": None
        },
        "required_classes": retrieved_tables,
        "execution_strategy": "single_sparql",
        "output_schema": [],
        "reason": "Query_Spec failed to parse model output."
    }

    api_logger.log_call(query, "Query_Spec")
    request = {
        "model": model,
        "messages": build_llm_messages("query_spec", prompt),
    }
    if not model.lower().startswith("gpt-5"):
        request["temperature"] = 0.0
    response = client.chat.completions.create(**request)

    parsed_spec = parse_llm_json(
        response.choices[0].message.content,
        default_spec,
        "Query_Spec",
    )
    if not isinstance(parsed_spec, dict):
        parsed_spec = {**default_spec, "reason": "Query_Spec returned non-dict output."}
    if parsed_spec.get("execution_strategy") in {"decomposed_metric_scan", "post_scan_pandas_merge"}:
        parsed_spec["execution_strategy"] = "preaggregate_sparql"
        parsed_spec["reason"] = (
            f"{parsed_spec.get('reason', '')} Executor supports one SPARQL query; "
            "unsupported decomposed execution was downgraded to preaggregate_sparql."
        ).strip()
    parsed_spec = cleanup_query_spec(parsed_spec, query, retrieved_tables)

    return {"query_spec": parsed_spec}


def cleanup_query_spec(query_spec: Dict[str, Any], query: str, retrieved_tables: list) -> Dict[str, Any]:
    """Normalize LLM Query_Spec output using generic, schema-agnostic execution rules."""
    if not isinstance(query_spec, dict):
        return query_spec

    cleaned = json.loads(json.dumps(query_spec))
    q = normalize_for_compare(query)
    cleanup_notes = []

    if cleaned.get("execution_strategy") not in {"single_sparql", "preaggregate_sparql"}:
        cleaned["execution_strategy"] = "preaggregate_sparql"
        cleanup_notes.append("unsupported execution_strategy was downgraded to preaggregate_sparql")

    if not cleaned.get("required_classes"):
        cleaned["required_classes"] = retrieved_tables
        cleanup_notes.append("required_classes filled from retrieved classes")

    if cleaned.get("base_entity") and cleaned.get("base_entity") not in cleaned.get("required_classes", []):
        cleaned.setdefault("required_classes", []).insert(0, cleaned.get("base_entity"))
        cleanup_notes.append("base_entity added to required_classes")

    distinct_requested = any(marker in q for marker in ["distinct", "unique", "different"])
    for measure in cleaned.get("measures", []) if isinstance(cleaned.get("measures"), list) else []:
        final_operation = str(measure.get("final_operation") or "").upper()
        per_entity_operation = str(measure.get("per_entity_operation") or "").upper()
        output_name = normalize_for_compare(measure.get("output_name", ""))
        if final_operation == "COUNT" or per_entity_operation == "COUNT" or "count" in output_name:
            if measure.get("requires_distinct") and not distinct_requested:
                measure["requires_distinct"] = False
                cleanup_notes.append("COUNT requires_distinct disabled because query did not request distinct/unique values")

    group_by = cleaned.get("group_by", [])
    group_by = group_by if isinstance(group_by, list) else []
    if group_by and any(marker in q for marker in ["for each", " by ", " per ", " across ", "grouped by"]):
        cleaned["preserve_null_groups"] = True
        cleanup_notes.append("group-by query marked to preserve NULL groups")

    month_level_requested = bool(re.search(
        r"\b(per month|for each month|monthly|month of|months of 20\d{2}|for each month of 20\d{2})\b",
        q,
    ))
    if month_level_requested:
        cleaned["month_grain"] = True
        cleanup_notes.append("month-level query marked for YYYY-MM extraction")

    output_schema = cleaned.get("output_schema", [])
    if not isinstance(output_schema, list):
        output_schema = []
    if not output_schema:
        output_schema = []
        for group in group_by:
            if isinstance(group, dict) and group.get("output_name"):
                output_schema.append(group["output_name"])
        for measure in cleaned.get("measures", []) if isinstance(cleaned.get("measures"), list) else []:
            if isinstance(measure, dict) and measure.get("output_name"):
                output_schema.append(measure["output_name"])
        cleaned["output_schema"] = output_schema
        if output_schema:
            cleanup_notes.append("output_schema filled from group_by and measures")

    if cleanup_notes:
        prior_reason = str(cleaned.get("reason", "")).strip()
        cleaned["cleanup_notes"] = cleanup_notes
        cleaned["reason"] = (prior_reason + " Cleanup: " + "; ".join(cleanup_notes)).strip()

    return cleaned
