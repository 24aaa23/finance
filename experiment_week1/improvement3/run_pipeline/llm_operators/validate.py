"""Validate operator: semantic validation of scan output."""

from ..common import (
    Any,
    DETERMINISTIC_EXPLAIN,
    Dict,
    LOCAL_MODEL,
    api_logger,
    json,
    re,
)
from ..clients import build_llm_messages, supports_temperature
from ..utils import normalize_for_compare, parse_llm_json

ID_LIKE_GROUP_FIELDS = {
    "investorid", "investor_id", "investorprofile", "investor_profile",
    "holdingid", "holding_id", "goalid", "goal_id",
    "cashflowid", "cash_flow_id", "transactionid", "transaction_id",
    "portfolioid", "portfolio_id", "accountid", "account_id",
}


def empty_answer_can_be_valid(query: str, query_spec: Dict[str, Any]) -> bool:
    q = normalize_for_compare(query)
    qtype = str(query_spec.get("query_type", "")).lower()

    list_like = any(phrase in q for phrase in [
        "which", "show", "list", "identify", "find", "investors who",
        "holdings that", "records where"
    ])
    numeric_required = any(phrase in q for phrase in [
        "count", "how many", "average", "avg", "sum", "total",
        "highest", "lowest", "maximum", "minimum"
    ])

    return list_like and not numeric_required and qtype in {
        "set_logic", "point_lookup", "ranking", "comparative", "aggregation",
        "filter", "comparison", "multi_step",
    }


def _norm_group_token(value: Any) -> str:
    return re.sub(r"[^a-z0-9_]+", "", str(value or "").replace("-", "_").lower())


def query_spec_requires_null_group_guard(query_spec: Dict[str, Any]) -> bool:
    if not isinstance(query_spec, dict) or not query_spec.get("preserve_null_groups"):
        return False
    group_by = query_spec.get("group_by", [])
    if not isinstance(group_by, list) or not group_by:
        return False

    for group in group_by:
        if not isinstance(group, dict):
            continue
        field = _norm_group_token(group.get("field"))
        output_name = _norm_group_token(group.get("output_name"))
        if field not in ID_LIKE_GROUP_FIELDS and output_name not in ID_LIKE_GROUP_FIELDS:
            return True
    return False


def sparql_has_null_group_guard(sparql: str) -> bool:
    text = str(sparql or "").lower()
    return "optional" in text and "coalesce" in text and '"null"' in text


def normalize_value_for_final_answer(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: normalize_value_for_final_answer(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_value_for_final_answer(item) for item in value]
    if isinstance(value, str) and value.strip().upper() in {"NULL", "NONE"}:
        return None
    return value


def is_list_query(query: str) -> bool:
    q = str(query or "").lower()
    return any(marker in q for marker in ["which", "show", "list", "identify", "find"])


def is_count_query(query: str) -> bool:
    q = str(query or "").lower()
    return any(marker in q for marker in [
        "count",
        "how many",
        "number of",
        "total number",
        "frequency",
    ])


def clean_rows_for_final_answer(raw_data: list, query: str) -> list:
    cleaned = []
    for row in raw_data:
        cleaned.append(normalize_value_for_final_answer(row))
    return cleaned


def should_return_structured_json(query: str, raw_data: Any) -> bool:
    if not DETERMINISTIC_EXPLAIN or not isinstance(raw_data, list):
        return False
    if len(raw_data) == 0:
        return False

    if all(isinstance(row, dict) for row in raw_data):
        return True

    row_count = len(raw_data)
    list_output = is_list_query(query)
    table_output = row_count > 1
    return list_output or table_output


def semantic_validate(inputs: Dict[str, Any], client: Any, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    print(f"\n[DEBUG] --- Executing semantic_validate ---")
    data = inputs.get('data', [])
    print(f"[DEBUG] Validating {len(data)} rows for query.")
    if not data:
        query_spec = inputs.get("query_spec", {})
        if empty_answer_can_be_valid(inputs.get("query", ""), query_spec):
            val_dict = {
                "is_valid": True,
                "reason": "Empty result is valid for this filtered/list-style query.",
            }
        else:
            val_dict = {"is_valid": False, "reason": "Data Results are empty. Query failed to retrieve necessary facts."}
        print(f"[DEBUG] Output Validation Result: {val_dict}")
        return {"validation": val_dict, "data": data}

    # Extract the column names (keys) from the first row of data to help the LLM verify fields
    returned_fields = list(data[0].keys()) if data and isinstance(data, list) else []

    # Cap the data sample at 10 rows to prevent blowing up the LLM context window during validation
    data_sample = data[:10] if isinstance(data, list) else data
    query_spec = inputs.get("query_spec", {})
    final_spec = inputs.get("final_spec", {})
    final_execution = inputs.get("final_execution", [])
    has_final_spec = isinstance(final_spec, dict) and bool(final_spec)
    # In the spec-first pipeline, each SPARQL query is intentionally branch-local.
    # It must not be mistaken for the final cross-branch computation.
    generated_sparql = (
        "Branch-local raw retrieval SPARQL is intentionally not used as final-answer evidence. "
        "Judge Final_Spec and Final Execution instead."
        if has_final_spec else inputs.get("sparql", "")
    )
    operator_plan = inputs.get("operator_plan") or (query_spec.get("operator_plan", []) if isinstance(query_spec, dict) else [])
    if not has_final_spec and query_spec_requires_null_group_guard(query_spec) and not sparql_has_null_group_guard(generated_sparql):
        val_dict = {
            "is_valid": False,
            "reason": (
                "Group-by category/type/attribute query is missing OPTIONAL + COALESCE(\"NULL\") "
                "for preserve_null_groups, so NULL groups may be dropped."
            ),
        }
        print(f"[DEBUG] Output Validation Result: {val_dict}")
        return {"validation": val_dict, "data": data}

    prompt = f"""
    The next operator is Validate.
    Assess if the following data results successfully answer the user's original query.
    Use the generated SPARQL and the operator plan as evidence. Do not judge only by row count.

    User Query: "{inputs.get('query')}"
    Query Spec:
    {json.dumps(query_spec, indent=2)}
    Final Spec (when present, this is the cross-branch computation contract):
    {json.dumps(final_spec, indent=2)}
    Final Execution (operators actually run after all branch scans):
    {json.dumps(final_execution, indent=2)}
    Generated SPARQL:
    {generated_sparql}
    Operator Plan (Executed Post-Scan Operators):
    {json.dumps(operator_plan, indent=2)}
    Returned Column Names: {returned_fields}
    Data Results (Sample): {json.dumps(data_sample, indent=2)}

    CRITICAL RULE 1 (EMPTY DATA):
    Empty data is handled before this prompt. For the current validation, inspect only the non-empty returned data sample.

    CRITICAL RULE 2 (SCHEMA & FIELD MATCH - FIX E-02): Beyond checking if data is non-empty, you MUST verify:
    1. Do the returned column names logically match what the query asked for? (e.g., if asking for "sector and allocation", both fields MUST be present).
    2. If the query asked for a specific investor/entity filter, does the data reflect only that entity? Or did it return data for everyone?
    3. If Final Spec is present, judge the final returned rows against it, Final Execution, and the original question. Each raw SPARQL is deliberately branch-local, so NEVER reject a final answer merely because the displayed raw SPARQL lacks another branch's filter, join, aggregation, or intersection. Do not require the last branch Query Spec to contain all final measures. If the query asked for an aggregation (MAX/MIN/SUM/AVG/COUNT) or ranking (Top N), verify if the final returned data sample reflects the aggregation or ranking.
    4. If the query asks for a top/bottom, highest/lowest, maximum/minimum, largest/smallest, best/worst, or ranking-style result, inspect the operator_plan/final rows for ranking logic. SPARQL is allowed to be simple raw retrieval.
    5. If Query Spec has output_schema, do the returned column names satisfy that expected answer shape? IMPORTANT: Do NOT require exact character-for-character column names when aliases clearly correspond (e.g. `logic` corresponds to `hasRebalancingLogic`, `count` corresponds to `action_count` or `holdingCount`, `total_amount` corresponds to `amount`). If the semantics and values are correct, mark is_valid: true.
    6. For entity/list questions, verify the SPARQL anchors the returned entity with `rdf:type` for the requested base entity or required class. If it only uses an ID-like literal property, mark invalid because different classes can share identifier literals.
    7. For missing-required-field questions, rows with null/None values in requested display fields are a strong sign the query matched the wrong class; mark invalid unless the user explicitly asked for those display fields to be missing.

    CRITICAL RULE 3 (OPERATOR-FIRST RANKED AGGREGATION): For superlative or ranking questions, a single returned row can be fully valid when post-scan operators reduce the result:
    - Filter_Aggregate followed by Order_By with limit 1 is a valid way to return one top or bottom group.
    - Order_By ASC supports lowest/minimum/smallest/bottom questions.
    - Order_By DESC supports highest/maximum/largest/top questions.
    - Do NOT require all groups to be returned when the operator plan already selects the final ranked answer.

    If ANY of these logic checks fail, you MUST output "is_valid": false and provide specific, detailed feedback in the "reason" field about which columns/aggregations are wrong.
    If ANY of these fundamental logic checks fail, you MUST output "is_valid": false and provide specific, detailed feedback in the "reason" field about which columns/aggregations are wrong. Otherwise, output "is_valid": true.

    Output strictly a JSON object: {{"is_valid": true/false, "reason": "why"}}
    """

    api_logger.log_call(inputs.get('query'), "Validate")
    request = {
        "model": model,
        "messages": build_llm_messages("explain", prompt),
    }
    if supports_temperature(model):
        request["temperature"] = 0.0
    response = client.chat.completions.create(**request)

    result = response.choices[0].message.content
    val_dict = parse_llm_json(
        result,
        {
            "is_valid": bool(data),
            "reason": "Validator did not return valid JSON; using row-presence fallback.",
        },
        "Validate",
    )
    if not isinstance(val_dict, dict):
        val_dict = {
            "is_valid": bool(data),
            "reason": "Validator returned a non-object response; using row-presence fallback.",
        }
    elif "is_valid" not in val_dict:
        val_dict = {
            "is_valid": bool(data),
            "reason": "Validator returned JSON without is_valid; using row-presence fallback.",
        }

    print(f"[DEBUG] Output Validation Result: {val_dict}")
    return {"validation": val_dict, "data": data}
