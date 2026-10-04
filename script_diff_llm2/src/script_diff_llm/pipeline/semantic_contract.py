import re
from decimal import Decimal, InvalidOperation
from typing import Any


def normalize_semantic_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def normalize_compare_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9.]+", " ", str(value or "").lower()).strip()


def _query_has_multiple_conditions(query: str) -> bool:
    q = f" {normalize_compare_text(query)} "
    return any(marker in q for marker in [" and ", " both ", " also ", " as well as "])


def _has_helper_count_measure(query_spec: dict[str, Any]) -> bool:
    measures = query_spec.get("measures")
    measures = measures if isinstance(measures, list) else []
    for measure in measures:
        if not isinstance(measure, dict):
            continue
        output_name = normalize_semantic_text(measure.get("output_name", ""))
        per_entity_operation = str(measure.get("per_entity_operation") or "").upper()
        final_operation = str(measure.get("final_operation") or "").upper()
        if (
            "count" in output_name
            or per_entity_operation == "COUNT"
            or final_operation == "COUNT"
        ):
            return True
    return False


def empty_answer_can_be_valid(query: str, query_spec: dict[str, Any]) -> bool:
    q = normalize_compare_text(query)
    qtype = str(query_spec.get("query_type", "")).lower()
    list_like = any(phrase in q for phrase in [
        "which", "show", "list", "identify", "find",
        "holdings that", "records where",
    ])
    negative_existence = any(phrase in q for phrase in [
        "missing", "without", "not having", "never", "no ",
    ])
    numeric_required = any(phrase in q for phrase in [
        "count", "how many", "average", "avg", "sum", "total",
        "highest", "lowest", "maximum", "minimum",
    ])
    if not ((list_like or negative_existence) and not numeric_required):
        return False
    if qtype not in {"set_logic", "point_lookup", "ranking", "comparative", "aggregation"}:
        return False

    group_by = query_spec.get("group_by")
    group_by = group_by if isinstance(group_by, list) else []
    ranking = query_spec.get("ranking")
    ranking = ranking if isinstance(ranking, dict) else {}
    filters = query_spec.get("filters")
    filters = filters if isinstance(filters, list) else []
    required_classes = query_spec.get("required_classes")
    required_classes = required_classes if isinstance(required_classes, list) else []
    join_policy = str(query_spec.get("join_policy", "")).lower()

    if group_by or ranking.get("required"):
        return False
    if join_policy in {"anti_join", "union_required"}:
        return False
    if len(required_classes) > 1:
        return False
    if len(filters) > 1 or _query_has_multiple_conditions(query):
        return False
    if _has_helper_count_measure(query_spec):
        return False
    return True


def _equivalent_column(expected: str, actual_columns: list[str]) -> str | None:
    expected_norm = normalize_semantic_text(expected)
    for column in actual_columns:
        actual_norm = normalize_semantic_text(column)
        if actual_norm == expected_norm:
            return column
    return None


def _numeric_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _is_grouped_query(query: str, query_spec: dict[str, Any]) -> bool:
    if query_spec.get("group_by"):
        return True
    q = normalize_compare_text(query)
    return any(marker in q for marker in [" across ", " grouped by ", " for each ", " per ", " by "])


def _is_band_query(query: str, query_spec: dict[str, Any], group_by: list[dict[str, Any]]) -> bool:
    q = normalize_compare_text(query)
    if any(marker in q for marker in [" band", " bands", " bucket", " buckets", " range", " ranges"]):
        return True
    for group in group_by:
        if isinstance(group, dict) and group.get("bucket_strategy"):
            return True
        output_name = str(group.get("output_name", ""))
        if "band" in output_name.lower() or "bucket" in output_name.lower():
            return True
    return False


def _looks_like_bucket_label(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    if text == "null":
        return True
    if text in {"low", "moderate", "medium", "high"}:
        return True
    if any(token in text for token in ["band", "bucket", "range"]):
        return True
    return bool(re.search(r"(<|>|-| to )", text))


def _sorted_by_metric(data: list[dict[str, Any]], metric_column: str, direction: str) -> bool:
    numeric_values = []
    for row in data:
        metric = _numeric_decimal(row.get(metric_column))
        if metric is None:
            return False
        numeric_values.append(metric)
    ordered = sorted(numeric_values, reverse=(direction == "desc"))
    return numeric_values == ordered


def _drop_null_group_rows(query_spec: dict[str, Any], data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove null grouping rows when the Query_Spec excludes them."""
    if query_spec.get("preserve_null_groups", True):
        return data
    group_by = query_spec.get("group_by")
    group_by = group_by if isinstance(group_by, list) else []
    group_names = [
        str(group.get("output_name") or "").strip()
        for group in group_by
        if isinstance(group, dict) and group.get("output_name")
    ]
    if not group_names:
        return data
    filtered = []
    for row in data:
        if not isinstance(row, dict):
            filtered.append(row)
            continue
        is_null_group = any(
            row.get(name) is None or str(row.get(name)).strip().upper() == "NULL"
            for name in group_names
        )
        if not is_null_group:
            filtered.append(row)
    return filtered


def normalize_semantic_result(query: str, query_spec: dict[str, Any], data: Any) -> Any:
    """Preserve backend values; apply only explicit result-shape policies."""
    if not isinstance(data, list):
        return data
    if not all(isinstance(row, dict) for row in data):
        return data
    normalized = [dict(row) for row in data]
    normalized = _drop_null_group_rows(query_spec, normalized)
    return normalized


def validate_semantic_result(query: str, query_spec: dict[str, Any], data: Any) -> dict[str, Any]:
    if not isinstance(data, list):
        return {
            "is_valid": False,
            "severity": "hard_error",
            "reason": "Result data is not a row list.",
            "rewrite_hint": "Return tabular row output as a list of dictionaries.",
        }

    if not data:
        if empty_answer_can_be_valid(query, query_spec):
            return {
                "is_valid": True,
                "severity": "valid",
                "reason": "Empty result is valid for this filtered/list-style query.",
                "rewrite_hint": "",
            }
        return {
            "is_valid": False,
            "severity": "repairable_warning",
            "reason": "Execution returned no rows for a query that expects an answer set.",
            "rewrite_hint": "Preserve the Query_Spec filters and answer shape while retrieving the requested rows.",
        }

    if not all(isinstance(row, dict) for row in data):
        return {
            "is_valid": False,
            "severity": "hard_error",
            "reason": "Result rows are not dictionary-shaped.",
            "rewrite_hint": "Return structured rows with named columns.",
        }

    actual_columns = list(data[0].keys())
    expected_columns = [
        str(column)
        for column in query_spec.get("output_schema", [])
        if str(column).strip()
    ]
    missing_columns = [
        column for column in expected_columns
        if _equivalent_column(column, actual_columns) is None
    ]
    if missing_columns:
        return {
            "is_valid": False,
            "severity": "repairable_warning",
            "reason": f"Result is missing expected output columns: {missing_columns}. Actual columns: {actual_columns}",
            "rewrite_hint": "Keep the Query_Spec output_schema unchanged and return every expected field with matching aliases.",
        }

    if query_spec.get("month_grain"):
        month_column = _equivalent_column("month", actual_columns)
        date_column = _equivalent_column("date", actual_columns)
        if month_column and date_column:
            return {
                "is_valid": False,
                "severity": "repairable_warning",
                "reason": "Month-level query leaked raw date into the final output instead of aggregating to one row per month.",
                "rewrite_hint": "Aggregate at YYYY-MM month grain and remove raw date from the final SELECT/GROUP BY/output schema.",
            }
        if month_column:
            null_month_rows = [
                row for row in data
                if isinstance(row, dict) and (
                    row.get(month_column) is None
                    or str(row.get(month_column)).strip().upper() == "NULL"
                )
            ]
            if null_month_rows:
                return {
                    "is_valid": False,
                    "severity": "repairable_warning",
                    "reason": "Month-level query returned null month rows instead of concrete YYYY-MM buckets.",
                    "rewrite_hint": "Filter out rows with missing dates before month aggregation, or aggregate only rows with a concrete extracted month.",
                }

    group_by = query_spec.get("group_by", [])
    group_by = group_by if isinstance(group_by, list) else []
    ranking = query_spec.get("ranking", {})
    ranking = ranking if isinstance(ranking, dict) else {}
    grouped_query = _is_grouped_query(query, query_spec)
    ranking_required = bool(ranking.get("required"))
    list_like = any(marker in normalize_compare_text(query) for marker in ["which", "show", "list", "identify", "find"])

    if group_by:
        first_group = group_by[0] if isinstance(group_by[0], dict) else {}
        group_column = _equivalent_column(first_group.get("output_name", ""), actual_columns)
        if group_column and _is_band_query(query, query_spec, group_by):
            labels = [row.get(group_column) for row in data]
            numeric_like = sum(_numeric_decimal(value) is not None for value in labels)
            bucket_like = sum(_looks_like_bucket_label(value) for value in labels)
            if len(data) > 12 or (numeric_like and bucket_like < max(1, len(labels) // 3)):
                return {
                    "is_valid": False,
                    "severity": "repairable_warning",
                    "reason": "Band/bucket query returned raw numeric group values instead of bucketed labels.",
                    "rewrite_hint": "Convert the numeric grouping field into explicit bucket labels before aggregation, then group by those labels.",
                }

    if ranking_required:
        entity_key = str(query_spec.get("entity_key", "")).strip()
        if entity_key and _equivalent_column(entity_key, actual_columns) is None:
            return {
                "is_valid": False,
                "severity": "repairable_warning",
                "reason": f"Ranking query is missing the entity identity column '{entity_key}'.",
                "rewrite_hint": "Keep the ranked metric, but also return the entity identity column so the ranked rows identify which entity each score belongs to.",
            }
        metric_name = str(ranking.get("metric", "")).strip()
        metric_column = _equivalent_column(metric_name, actual_columns)
        if not metric_column:
            return {
                "is_valid": False,
                "severity": "repairable_warning",
                "reason": f"Ranking query is missing the ranking metric column '{metric_name}'.",
                "rewrite_hint": "Select the requested ranking metric with the exact Query_Spec alias and rank on that column.",
            }

        limit = ranking.get("limit")
        if isinstance(limit, int) and limit > 0 and len(data) > limit:
            return {
                "is_valid": False,
                "severity": "repairable_warning",
                "reason": f"Ranking query returned {len(data)} rows, exceeding the requested limit {limit}.",
                "rewrite_hint": "Apply the ranking LIMIT after ordering by the requested metric.",
            }

        direction = str(ranking.get("direction", "desc")).strip().lower() or "desc"
        if direction in {"asc", "desc"} and not _sorted_by_metric(data, metric_column, direction):
            return {
                "is_valid": False,
                "severity": "repairable_warning",
                "reason": f"Ranking results are not sorted by '{metric_name}' in {direction} order.",
                "rewrite_hint": "Sort the final result by the ranking metric in the Query_Spec direction and keep a stable tie-break.",
            }

    entity_key = str(query_spec.get("entity_key", "")).strip()
    if list_like and entity_key and not group_by and _equivalent_column(entity_key, actual_columns) is None:
        return {
            "is_valid": False,
            "severity": "repairable_warning",
            "reason": f"Entity-returning query is missing the entity identity column '{entity_key}'.",
            "rewrite_hint": "Return the entity identity column in the final output so each row identifies which entity satisfied the query.",
        }
    if entity_key and not group_by:
        entity_column = _equivalent_column(entity_key, actual_columns)
        if entity_column:
            seen = set()
            duplicates = set()
            for row in data:
                value = row.get(entity_column)
                if value in seen:
                    duplicates.add(value)
                seen.add(value)
            if duplicates:
                return {
                    "is_valid": False,
                    "severity": "repairable_warning",
                    "reason": f"Result contains duplicate entity keys for '{entity_key}': {sorted(duplicates)[:5]}",
                    "rewrite_hint": "Aggregate or deduplicate at the entity_key grain before the final output.",
                }

    return {
        "is_valid": True,
        "severity": "valid",
        "reason": "Result rows satisfy the Query_Spec output shape checks.",
        "rewrite_hint": "",
    }


def should_validate_semantics(query_spec: dict[str, Any]) -> bool:
    if not isinstance(query_spec, dict) or not query_spec:
        return False
    measures = query_spec.get("measures")
    ranking = query_spec.get("ranking")
    group_by = query_spec.get("group_by")
    output_schema = query_spec.get("output_schema")
    query_type = str(query_spec.get("query_type", "")).strip().lower()
    return bool(
        (isinstance(measures, list) and measures)
        or (isinstance(group_by, list) and group_by)
        or (isinstance(output_schema, list) and output_schema)
        or (isinstance(ranking, dict) and ranking.get("required"))
        or query_type in {"aggregation", "comparative", "ranking", "multi_step"}
    )


_IRI_PREFIX = re.compile(r"^https?://", re.IGNORECASE)


def iri_local_name(value: Any, allowed_prefixes: tuple[str, ...] = ()) -> Any:
    """Map an IRI to a local ID only for a declared identity namespace."""
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not _IRI_PREFIX.match(text) or not any(text.startswith(prefix) for prefix in allowed_prefixes):
        return value
    tail = re.split(r"[#/]", text)[-1]
    return tail if tail else value


def normalize_result_iris(data: Any, allowed_prefixes: tuple[str, ...] = ()) -> Any:
    """Apply only source-declared IRI-to-local-ID mappings."""
    if not isinstance(data, list):
        return data
    normalized = []
    for row in data:
        if isinstance(row, dict):
            normalized.append({key: iri_local_name(value, allowed_prefixes) for key, value in row.items()})
        else:
            normalized.append(row)
    return normalized


def set_operation_key(value: Any) -> str:
    """Exact string key; equivalence across backends requires a declared map."""
    return str(value) if value is not None else ""


def _has_staged_aggregation(sql_text: str) -> bool:
    """True when the SQL stages aggregation through a CTE or derived table."""
    lowered = re.sub(r"\s+", " ", str(sql_text or "").lower())
    if not lowered:
        return False
    if re.search(r"\bwith\b\s+[a-z_][a-z0-9_]*\s+as\s*\(", lowered):
        return True
    if re.search(r"\b(from|join)\s*\(\s*select\b", lowered):
        return True
    # SPARQL stages aggregation with a nested sub-SELECT inside a group graph pattern.
    return bool(re.search(r"\{\s*select\b", lowered))


def validate_aggregation_shape(query_spec: dict[str, Any], generated_query: str) -> dict[str, Any]:
    """Deterministic pre-scan check that fan-out control was actually implemented.

    When the Query_Spec demands two-level aggregation, a single flat join over
    one-to-many tables silently weights each entity by its related-record count.
    That produces a plausible-looking but wrong number, so it must be caught
    before the result is accepted rather than after.
    """
    if not isinstance(query_spec, dict):
        return {"is_valid": True, "severity": "valid", "reason": "", "rewrite_hint": ""}

    fanout_control = query_spec.get("fanout_control")
    fanout_control = fanout_control if isinstance(fanout_control, dict) else {}
    grain = query_spec.get("grain") if isinstance(query_spec.get("grain"), dict) else {}
    pre_aggregate_by = grain.get("pre_aggregate_by") or []
    pre_aggregate_by = pre_aggregate_by if isinstance(pre_aggregate_by, list) else []

    if not fanout_control.get("required") or not pre_aggregate_by:
        return {"is_valid": True, "severity": "valid", "reason": "", "rewrite_hint": ""}
    if not str(generated_query or "").strip():
        return {"is_valid": True, "severity": "valid", "reason": "", "rewrite_hint": ""}
    if _has_staged_aggregation(generated_query):
        return {"is_valid": True, "severity": "valid", "reason": "", "rewrite_hint": ""}

    keys = ", ".join(str(key) for key in pre_aggregate_by)
    final_group_by = grain.get("final_group_by") or []
    final_group_by = final_group_by if isinstance(final_group_by, list) else []
    group_text = ", ".join(str(key) for key in final_group_by) or "the requested group"
    return {
        "is_valid": False,
        "severity": "repairable_warning",
        "reason": (
            "Query Spec requires two-level aggregation "
            f"(pre_aggregate_by={pre_aggregate_by}) but the generated query aggregates in a single "
            "flat join, which duplicates entity rows once per related record and skews every aggregate."
        ),
        "rewrite_hint": (
            f"Aggregate each measure to {keys} grain inside its own CTE or derived table using the "
            "measure's per_entity_operation, join those pre-aggregated results to the base entity table "
            f"on {keys}, and only then apply the final_operation grouped by {group_text}."
        ),
    }


def validate_join_population_shape(query_spec: dict[str, Any], generated_query: str) -> dict[str, Any]:
    """Detect grouped comparative SQL that collapses measure populations by inner-joining CTEs.

    For grouped multi-measure comparisons we often want each metric averaged over
    the entities that have that metric, not the strict intersection of every
    source table. An outer GROUP BY over INNER JOINed measure CTEs silently
    changes the denominator for every metric.
    """
    if not isinstance(query_spec, dict):
        return {"is_valid": True, "severity": "valid", "reason": "", "rewrite_hint": ""}
    if not query_spec.get("independent_measure_population"):
        return {"is_valid": True, "severity": "valid", "reason": "", "rewrite_hint": ""}
    group_by = query_spec.get("group_by")
    group_by = group_by if isinstance(group_by, list) else []
    if not group_by:
        return {"is_valid": True, "severity": "valid", "reason": "", "rewrite_hint": ""}
    lowered = re.sub(r"\s+", " ", str(generated_query or "").lower())
    if not lowered:
        return {"is_valid": True, "severity": "valid", "reason": "", "rewrite_hint": ""}
    if " inner join " not in lowered:
        return {"is_valid": True, "severity": "valid", "reason": "", "rewrite_hint": ""}
    if " left join " in lowered:
        # Mixed joins are acceptable here; the contract is specifically about
        # avoiding an all-intersection outer query.
        return {"is_valid": True, "severity": "valid", "reason": "", "rewrite_hint": ""}
    group_names = [str(group.get("output_name") or group.get("field") or "").strip() for group in group_by if isinstance(group, dict)]
    group_text = ", ".join(name for name in group_names if name) or "the requested group"
    return {
        "is_valid": False,
        "severity": "repairable_warning",
        "reason": (
            "Grouped comparative query uses only INNER JOINs across pre-aggregated measure sources, "
            "so every metric is being averaged over the intersection of source populations instead of "
            "its own entities within the group."
        ),
        "rewrite_hint": (
            f"Drive the outer query from the base grouping table and LEFT JOIN each measure CTE on the entity key, "
            f"then GROUP BY {group_text} so AVG/SUM for each metric uses the correct per-measure population."
        ),
    }


def validate_join_policy_shape(query_spec: dict[str, Any], generated_query: str) -> dict[str, Any]:
    """Ensure generated SQL/SPARQL does not silently change population policy."""
    if not isinstance(query_spec, dict):
        return {"is_valid": True, "severity": "valid", "reason": "", "rewrite_hint": ""}
    policy = str(query_spec.get("join_policy") or "").strip().lower()
    if policy not in {"inner_join", "left_join"}:
        return {"is_valid": True, "severity": "valid", "reason": "", "rewrite_hint": ""}
    if not query_spec.get("group_by"):
        return {"is_valid": True, "severity": "valid", "reason": "", "rewrite_hint": ""}
    lowered = re.sub(r"\s+", " ", str(generated_query or "").lower())
    if not lowered:
        return {"is_valid": True, "severity": "valid", "reason": "", "rewrite_hint": ""}
    if policy == "inner_join" and " left join " in f" {lowered} ":
        return {
            "is_valid": False,
            "severity": "repairable_warning",
            "reason": "Query Spec requires inner_join, but generated query uses LEFT JOIN and changes the population.",
            "rewrite_hint": "Use INNER JOIN for every measure CTE when join_policy is inner_join.",
        }
    if policy == "left_join" and " left join " not in f" {lowered} ":
        return {
            "is_valid": False,
            "severity": "repairable_warning",
            "reason": "Query Spec requires left_join, but generated query has no LEFT JOIN.",
            "rewrite_hint": "Drive from the grouping entity and LEFT JOIN each measure CTE.",
        }
    return {"is_valid": True, "severity": "valid", "reason": "", "rewrite_hint": ""}
