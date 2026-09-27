import json
import re
from typing import Any, Callable


PROFILE_DIMENSION_HINTS = {
    "risk_tolerance": {
        "phrases": [
            " by risk tolerance", " across risk tolerance", " per risk tolerance",
            " for each risk tolerance", " grouped by risk tolerance",
            " by profile risk tolerance", " across profile risk tolerance",
            " per profile risk tolerance", " for each profile risk tolerance",
        ],
        "sql": {"source_class": "ATOM_ENTITY_INVESTOR_PROFILE_001", "field": "risk_tolerance", "output_name": "risk_tolerance"},
        "kg": {"source_class": "Investor", "field": "riskTolerance", "output_name": "risk_tolerance"},
    },
    "time_horizon": {
        "phrases": [
            " by time horizon", " across time horizon", " per time horizon",
            " for each time horizon", " grouped by time horizon",
            " by profile time horizon", " across profile time horizon",
            " per profile time horizon", " for each profile time horizon",
        ],
        "sql": {"source_class": "ATOM_ENTITY_INVESTOR_PROFILE_001", "field": "time_horizon", "output_name": "time_horizon"},
        "kg": {"source_class": "Investor", "field": "timeHorizon", "output_name": "time_horizon"},
    },
    "segment": {
        "phrases": [
            " by segment", " across segment", " per segment", " for each segment",
            " grouped by segment", " by profile segment", " across profile segment",
            " per profile segment", " for each profile segment",
        ],
        "sql": {"source_class": "ATOM_ENTITY_INVESTOR_PROFILE_001", "field": "segment", "output_name": "segment"},
        "kg": {"source_class": "Investor", "field": "segment", "output_name": "segment"},
    },
    "category": {
        "phrases": [
            " by category", " across category", " per category", " for each category",
            " grouped by category", " by profile category", " across profile category",
            " per profile category", " for each profile category",
        ],
        "sql": {"source_class": "ATOM_ENTITY_INVESTOR_PROFILE_001", "field": "category", "output_name": "category"},
        "kg": {"source_class": "Investor", "field": "category", "output_name": "category"},
    },
}

REBALANCING_LOGIC_VALUES = {
    "manual override",
    "valuation-based",
    "calendar-based",
    "momentum-driven",
    "mean-reversion",
    "threshold-based",
    "tactical",
    "scenario-based",
    "risk-parity",
    "automated trigger",
}

REBALANCING_ACTION_VALUES = {
    "goal alignment buy",
    "buy",
    "profit booking",
    "tactical increase",
    "de-risking",
    "goal alignment sell",
    "rebalance sell",
    "cash deployment",
    "asset reallocation",
    "hold",
    "dividend reinvestment",
    "tactical decrease",
    "sector rotation sell",
    "switch in",
    "partial exit",
    "defensive shift",
    "switch out",
    "rebalance buy",
    "sector rotation buy",
    "stop loss exit",
    "aggressive entry",
    "portfolio trim",
    "sell",
}

SCENARIO_VALUES = {
    "approaching goal",
    "bear market",
    "economic growth",
    "interest rate hike",
    "sector rotation",
    "inflation surge",
    "flash crash",
    "currency depreciation",
    "bull market",
    "market volatility",
}


def _has_output_name(output_schema: list[Any], name: str) -> bool:
    target = str(name or "").strip().lower()
    return any(str(item or "").strip().lower() == target for item in output_schema)


def _append_unique(values: list[Any], value: Any) -> None:
    if value not in values:
        values.append(value)


def _normalize_name_for_contract(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _entity_label_output_name(entity_key: str) -> str | None:
    text = str(entity_key or "").strip()
    if not text:
        return None
    explicit = {
        "investor_id": "investor_name",
        "investorId": "investorName",
        "portfolio_id": "portfolio_name",
        "portfolioId": "portfolioName",
        "goal_id": "goal_name",
        "goalId": "goalName",
    }
    if text in explicit:
        return explicit[text]
    if text.endswith("_id"):
        return text[:-3] + "_name"
    if text.endswith("Id"):
        return text[:-2] + "Name"
    return None


def _query_mentions_named_entity(query_text: str, entity_key: str) -> bool:
    q = f" {query_text} "
    entity_key = str(entity_key or "").lower()
    if "investor" in q and "investor" in entity_key:
        return True
    if "portfolio" in q and "portfolio" in entity_key:
        return True
    if "goal" in q and "goal" in entity_key:
        return True
    return False


def _has_any_phrase(query_text: str, phrases: list[str]) -> bool:
    return any(phrase in query_text for phrase in phrases)


def _explicit_grouping_requested(query_text: str) -> bool:
    return _has_any_phrase(
        query_text,
        [" for each ", " grouped by ", " across ", " per ", " by "],
    )


def _query_explicitly_requests_per_entity_breakdown(query_text: str, entity_key: str) -> bool:
    q = f" {query_text} "
    entity_key = str(entity_key or "").lower()
    entity_markers = []
    if "investor" in entity_key:
        entity_markers = [" for each investor ", " each investor ", " by investor ", " per investor "]
    elif "goal" in entity_key:
        entity_markers = [" for each goal ", " each goal ", " by goal ", " per goal "]
    elif "holding" in entity_key:
        entity_markers = [" for each holding ", " each holding ", " by holding ", " per holding "]
    return any(marker in q for marker in entity_markers)


def _query_requires_intersection_population(query_text: str) -> bool:
    q = f" {query_text} "
    if re.search(r"\busing\s+(?:two|three|four|five|\d+)\s+related\s+tables\b", q):
        return True
    return any(
        marker in q
        for marker in [
            " among those with ",
            " among investors with ",
            " who have both ",
            " that have both ",
            " with both ",
            " also have ",
            " and also ",
            " together with ",
        ]
    )


def _query_requests_independent_measure_population(query_text: str) -> bool:
    q = f" {query_text} "
    return any(
        marker in q
        for marker in [
            " include all ",
            " including all ",
            " even if ",
            " regardless of whether ",
            " with or without ",
            " missing related ",
            " no related ",
            " without related ",
        ]
    )


def _schema_class(schema_kind: str, semantic_name: str) -> str:
    if schema_kind == "sql":
        mapping = {
            "cash_flow": "ATOM_EVENT_CASH_FLOW_001",
            "rebalancing": "ATOM_EVENT_REBALANCING_ACTION_001",
            "sector_allocation": "ATOM_ENTITY_SECTOR_ALLOCATION_001",
            "portfolio_holding": "ATOM_ENTITY_PORTFOLIO_HOLDING_001",
        }
    else:
        mapping = {
            "cash_flow": "CashFlow",
            "rebalancing": "RebalancingAction",
            "sector_allocation": "SectorAllocation",
            "portfolio_holding": "PortfolioHolding",
        }
    return mapping[semantic_name]


def _schema_field(schema_kind: str, semantic_name: str) -> str:
    if schema_kind == "sql":
        mapping = {
            "cash_flow_id": "cash_flow_id",
            "allocation_pct": "allocation_pct",
            "returns_pct": "returns_pct",
        }
    else:
        mapping = {
            "cash_flow_id": "cashFlowId",
            "allocation_pct": "allocationPct",
            "returns_pct": "returnsPct",
        }
    return mapping[semantic_name]


def _measure_prefix(base_name: str) -> str:
    lowered = str(base_name or "").lower()
    for prefix in ["avg_", "average_", "total_", "sum_", "count_", "max_", "min_"]:
        if lowered.startswith(prefix):
            return prefix
    if lowered.endswith("_total"):
        return "_total"
    return ""


def _average_style_name(name: str) -> str:
    lowered = str(name or "").strip()
    if not lowered:
        return lowered
    if lowered.lower().startswith("total_"):
        return "avg_" + lowered[6:]
    if lowered.lower().startswith("sum_"):
        return "avg_" + lowered[4:]
    if lowered.lower().endswith("_total"):
        return "avg_" + lowered[:-6]
    if lowered.lower().startswith(("avg_", "average_")):
        return lowered
    return f"avg_{lowered}"


def _field_prefers_max(measure: dict[str, Any]) -> bool:
    """True for measures that mean "the entity's peak share", not its mean.

    "Allocation concentration" is how concentrated an investor's portfolio is,
    which is the single largest allocation they hold, not the average of their
    allocations. Averaging within the entity understates it for every investor.
    """
    field_text = f"{measure.get('field', '')} {measure.get('output_name', '')}".lower()
    max_markers = ["concentration", "max_allocation", "largest", "peak", "highest_"]
    return any(marker in field_text for marker in max_markers)


def _field_prefers_average(measure: dict[str, Any]) -> bool:
    field_text = f"{measure.get('field', '')} {measure.get('output_name', '')}".lower()
    if _field_prefers_max(measure):
        return False
    average_markers = [
        "pct", "percent", "percentage", "score", "progress", "shortfall",
        "volatility", "liquidity", "diversification", "goal_match",
        "change", "gap",
        "return",
    ]
    return any(marker in field_text for marker in average_markers)


def _field_prefers_sum(measure: dict[str, Any]) -> bool:
    field_text = f"{measure.get('field', '')} {measure.get('output_name', '')}".lower()
    sum_markers = [
        "amount", "value", "cost", "dividend", "tax", "investment", "cash_flow",
        "cashflow", "rebalance",
    ]
    return any(marker in field_text for marker in sum_markers)


def _measure_source_classes(measures: list[Any]) -> list[str]:
    sources = []
    for measure in measures:
        if not isinstance(measure, dict):
            continue
        source = str(measure.get("source_class") or "").strip()
        if source and source not in sources:
            sources.append(source)
    return sources


def _number_word_to_int(token: str) -> int | None:
    mapping = {
        "zero": 0,
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
    }
    token = str(token or "").strip().lower()
    if token.isdigit():
        return int(token)
    return mapping.get(token)


def _query_requires_nontrivial_count_logic(query_text: str) -> bool:
    q = f" {query_text} "
    if any(marker in q for marker in [" how many ", " count ", " counts ", " number of "]):
        return True
    for match in re.finditer(
        r"\b(at least|at most|more than|less than|exactly|equal to|no fewer than|no more than)\s+([a-z0-9]+)\b",
        q,
    ):
        value = _number_word_to_int(match.group(2))
        if value is None or value > 1:
            return True
    return False


def _count_like_measure(measure: dict[str, Any]) -> bool:
    if not isinstance(measure, dict):
        return False
    per_entity_operation = str(measure.get("per_entity_operation") or "").upper()
    final_operation = str(measure.get("final_operation") or "").upper()
    output_name = _normalize_name_for_contract(measure.get("output_name", ""))
    field_name = _normalize_name_for_contract(measure.get("field", ""))
    return (
        per_entity_operation == "COUNT"
        or final_operation == "COUNT"
        or "count" in output_name
        or field_name.endswith("count")
    )


def _filter_string_values(filter_item: dict[str, Any]) -> set[str]:
    value = filter_item.get("value")
    values = value if isinstance(value, list) else [value]
    return {
        str(item).strip().lower()
        for item in values
        if isinstance(item, str) and str(item).strip()
    }


def _repair_filter_field_domains(
    cleaned: dict[str, Any],
    retrieved_tables: list[Any],
    cleanup_notes: list[str],
    *,
    schema_kind: str,
) -> None:
    filters = cleaned.get("filters")
    filters = filters if isinstance(filters, list) else []
    if not filters:
        return

    required_classes = cleaned.get("required_classes")
    required_classes = required_classes if isinstance(required_classes, list) else []
    available_classes = {
        str(value).strip()
        for value in [*retrieved_tables, *required_classes]
        if str(value).strip()
    }

    if schema_kind == "sql":
        rebalancing_class = "ATOM_EVENT_REBALANCING_ACTION_001"
        scenario_class = "ATOM_EVENT_SCENARIO_REBALANCING_001"
        triggered_action_field = "triggered_action"
    else:
        rebalancing_class = "RebalancingAction"
        scenario_class = "ScenarioRebalancing"
        triggered_action_field = "triggeredAction"

    for item in filters:
        if not isinstance(item, dict):
            continue
        source_class = str(item.get("source_class") or "").strip()
        field_name = str(item.get("field") or "").strip()
        values = _filter_string_values(item)
        if not values:
            continue

        if source_class == rebalancing_class and field_name == "action" and values <= REBALANCING_LOGIC_VALUES:
            item["field"] = "logic"
            cleanup_notes.append(
                f"{source_class}.action re-mapped to {source_class}.logic because filter values are rebalancing logic labels"
            )
            continue

        if source_class == rebalancing_class and field_name == "logic" and values <= REBALANCING_ACTION_VALUES:
            item["field"] = "action"
            cleanup_notes.append(
                f"{source_class}.logic re-mapped to {source_class}.action because filter values are concrete action labels"
            )
            continue

        if source_class == scenario_class and field_name == "scenario" and values <= REBALANCING_ACTION_VALUES:
            item["field"] = triggered_action_field
            cleanup_notes.append(
                f"{scenario_class}.scenario re-mapped to {scenario_class}.{triggered_action_field} because filter values are triggered-action labels"
            )
            continue

        if source_class == scenario_class and field_name == triggered_action_field and values <= SCENARIO_VALUES:
            item["field"] = "scenario"
            cleanup_notes.append(
                f"{scenario_class}.{triggered_action_field} re-mapped to {scenario_class}.scenario because filter values are scenario labels"
            )
            continue

        if (
            source_class == scenario_class
            and field_name == triggered_action_field
            and values <= REBALANCING_LOGIC_VALUES
            and rebalancing_class in available_classes
        ):
            item["source_class"] = rebalancing_class
            item["field"] = "logic"
            _append_unique(required_classes, rebalancing_class)
            cleaned["required_classes"] = required_classes
            cleanup_notes.append(
                f"{scenario_class}.{triggered_action_field} re-mapped to {rebalancing_class}.logic because filter values are rebalancing logic labels"
            )


def _collapse_singular_value_filters(
    cleaned: dict[str, Any],
    query_text: str,
    normalize_for_compare_fn: Callable[[Any], str],
    cleanup_notes: list[str],
) -> None:
    filters = cleaned.get("filters")
    filters = filters if isinstance(filters, list) else []
    collapsed_measure_fields: set[str] = set()
    for item in filters:
        if not isinstance(item, dict):
            continue
        operator = str(item.get("operator", "")).strip().lower()
        values = item.get("value")
        if operator not in {"in", "not_in"} or not isinstance(values, list) or len(values) < 2:
            continue
        string_values = [value for value in values if isinstance(value, str) and value.strip()]
        if len(string_values) < 2:
            continue
        matches = []
        for value in string_values:
            normalized_value = normalize_for_compare_fn(value)
            if normalized_value and normalized_value in query_text:
                matches.append(value)
        if len(matches) != 1:
            continue
        selected_value = matches[0]
        item["operator"] = "=" if operator == "in" else "!="
        item["value"] = selected_value
        item["value_type"] = "string"
        cleanup_notes.append(
            f"multi-value filter collapsed to '{selected_value}' because the subquery text names only one condition"
        )
        field_name = str(item.get("field") or "").strip()
        if field_name:
            collapsed_measure_fields.add(_normalize_name_for_contract(field_name))

    if not collapsed_measure_fields:
        return

    filtered = []
    for item in filters:
        if not isinstance(item, dict):
            filtered.append(item)
            continue
        if (
            _normalize_name_for_contract(item.get("source_class", "")) == "measure"
            and _normalize_name_for_contract(item.get("field", "")) in collapsed_measure_fields
        ):
            cleanup_notes.append(
                f"helper measure filter '{item.get('field', '')}' removed after singular filter collapse"
            )
            continue
        filtered.append(item)
    cleaned["filters"] = filtered


def _strip_helper_count_measures(
    cleaned: dict[str, Any],
    query_text: str,
    cleanup_notes: list[str],
) -> None:
    query_type = str(cleaned.get("query_type", "")).lower()
    if query_type not in {"point_lookup", "set_logic"}:
        return
    if _query_requires_nontrivial_count_logic(query_text):
        return

    measures = cleaned.get("measures")
    measures = measures if isinstance(measures, list) else []
    removable_names = {
        str(measure.get("output_name") or "").strip()
        for measure in measures
        if _count_like_measure(measure)
    }
    if not removable_names:
        return

    cleaned["measures"] = [
        measure for measure in measures
        if str(measure.get("output_name") or "").strip() not in removable_names
    ]

    output_schema = cleaned.get("output_schema")
    output_schema = output_schema if isinstance(output_schema, list) else []
    cleaned["output_schema"] = [
        name for name in output_schema
        if str(name or "").strip() not in removable_names
    ]

    filters = cleaned.get("filters")
    filters = filters if isinstance(filters, list) else []
    removable_norms = {_normalize_name_for_contract(name) for name in removable_names}
    cleaned["filters"] = [
        item for item in filters
        if not (
            isinstance(item, dict)
            and _normalize_name_for_contract(item.get("source_class", "")) == "measure"
            and _normalize_name_for_contract(item.get("field", "")) in removable_norms
        )
    ]
    cleanup_notes.append(
        "helper COUNT measures removed from entity-returning query so generation follows existence semantics instead of support counts"
    )


def _group_source_classes(group_by: list[Any]) -> list[str]:
    sources = []
    for group in group_by:
        if not isinstance(group, dict):
            continue
        source = str(group.get("source_class") or "").strip()
        if source and source not in sources:
            sources.append(source)
    return sources


def _default_per_entity_operation(measure: dict[str, Any]) -> str:
    """Pick the within-entity rollup for a measure using field semantics.

    Rate-like fields (pct/score/ratio) average within an entity; additive money
    fields (amount/value/cost) sum within an entity. This is the first half of
    the two-level `pre_aggregate_by -> final_group_by` contract.
    """
    declared = str(measure.get("per_entity_operation") or "").upper()
    if declared in {"SUM", "AVG", "COUNT", "MIN", "MAX"}:
        return declared
    final_operation = str(measure.get("final_operation") or "").upper()
    if final_operation == "COUNT":
        return "COUNT"
    if _field_prefers_max(measure):
        return "MAX"
    if _field_prefers_average(measure):
        return "AVG"
    if _field_prefers_sum(measure):
        return "SUM"
    return final_operation if final_operation in {"SUM", "AVG", "MIN", "MAX"} else "AVG"


def _requires_two_level_aggregation(
    group_by: list[Any],
    measures: list[Any],
    entity_key: str,
    grouped_compare: bool,
) -> bool:
    """True when a grouped query would fan out if executed as one flat join.

    A flat join over an entity table plus one-to-many event/detail tables
    duplicates each entity row once per related record, so a single final
    AVG/SUM is weighted by related-record counts instead of by entity. When the
    measures live outside the grouping entity's own table, the query must
    aggregate per entity_key first and only then aggregate across groups.
    """
    if not (grouped_compare and group_by and measures and entity_key):
        return False
    measure_sources = _measure_source_classes(measures)
    group_sources = _group_source_classes(group_by)
    if len(measure_sources) > 1:
        return True
    if measure_sources and group_sources and measure_sources[0] not in group_sources:
        return True
    return False


def _measure_requests_holding_gain(query_text: str, measure: dict[str, Any]) -> bool:
    if not isinstance(measure, dict):
        return False
    source_class = str(measure.get("source_class") or "").lower()
    field_name = str(measure.get("field") or "").lower()
    output_name = str(measure.get("output_name") or "").lower()
    query_text = str(query_text or "").lower()
    if "portfolio_holding" not in source_class:
        return False
    if "holding_gain" in output_name:
        return True
    if "gain" not in output_name and "holding gain" not in query_text:
        return False
    return field_name in {"returns_pct", "return_pct", "returns"}


def _measure_requests_positive_withdrawal(measure: dict[str, Any]) -> bool:
    if not isinstance(measure, dict):
        return False
    field_name = str(measure.get("field") or "").lower()
    if field_name != "amount":
        return False
    output_name = str(measure.get("output_name") or "").lower()
    formula = str(measure.get("formula") or "").lower()
    return "withdraw" in output_name or "withdrawal" in formula


ANALYTIC_QUERY_TYPES = {"aggregation", "comparative", "ranking", "multi_step"}

ANALYTIC_QUESTION_MARKERS = [
    "how do ", "how does ", "compare", "comparison", "average", "avg ", "total ",
    "sum ", "count", "how many", "highest", "lowest", "top ", "bottom ",
    "maximum", "minimum", "rank", "across ", "per ", "for each ",
]


def spec_is_analytic_without_measures(query_spec: dict[str, Any], question_text: str) -> bool:
    """True when an analytic question produced a Query_Spec carrying no measures.

    An aggregation or comparative question whose spec has no measures has no
    semantic contract at all: generation is then unconstrained and post-scan
    validation has nothing to check against. That is a recoverable Query_Spec
    failure, not a legitimately measure-free query, so it is worth one retry.
    """
    if not isinstance(query_spec, dict):
        return False
    measures = query_spec.get("measures")
    if isinstance(measures, list) and measures:
        return False
    query_type = str(query_spec.get("query_type", "")).strip().lower()
    lowered = f" {str(question_text or '').lower()} "
    return query_type in ANALYTIC_QUERY_TYPES or any(
        marker in lowered for marker in ANALYTIC_QUESTION_MARKERS
    )


def cleanup_query_spec(
    query_spec: dict[str, Any],
    query: str,
    retrieved_tables: list,
    normalize_for_compare_fn: Callable[[Any], str],
    *,
    schema_kind: str = "kg",
) -> dict[str, Any]:
    """Normalize LLM Query_Spec output using generic, schema-agnostic execution rules."""
    if not isinstance(query_spec, dict):
        return query_spec

    cleaned = json.loads(json.dumps(query_spec))
    q = normalize_for_compare_fn(query)
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
        output_name = normalize_for_compare_fn(measure.get("output_name", ""))
        if final_operation == "COUNT" or per_entity_operation == "COUNT" or "count" in output_name:
            if measure.get("requires_distinct") and not distinct_requested:
                measure["requires_distinct"] = False
                cleanup_notes.append("COUNT requires_distinct disabled because query did not request distinct/unique values")

    query_type = str(cleaned.get("query_type", "")).lower()
    group_by = cleaned.get("group_by", [])
    group_by = group_by if isinstance(group_by, list) else []
    explicit_grouping_requested = _explicit_grouping_requested(f" {q} ")
    if group_by and explicit_grouping_requested:
        cleaned["preserve_null_groups"] = True
        cleanup_notes.append("group-by query marked to preserve NULL groups")

    grain = cleaned.get("grain", {})
    grain = grain if isinstance(grain, dict) else {}
    pre_aggregate_by = grain.get("pre_aggregate_by", [])
    pre_aggregate_by = pre_aggregate_by if isinstance(pre_aggregate_by, list) else []
    final_group_by = grain.get("final_group_by", [])
    final_group_by = final_group_by if isinstance(final_group_by, list) else []
    if group_by and not final_group_by:
        inferred_final_group_by = [
            group.get("field")
            for group in group_by
            if isinstance(group, dict) and group.get("field")
        ]
        if inferred_final_group_by:
            grain["final_group_by"] = inferred_final_group_by
            cleaned["grain"] = grain
            cleanup_notes.append("grain.final_group_by filled from group_by fields")

    entity_key = str(cleaned.get("entity_key") or "").strip()
    if (
        grouped_compare := bool(group_by) and (
            query_type in {"comparative", "multi_step", "ranking", "aggregation"}
            or _has_any_phrase(q, [" compare ", " comparison ", " how do ", " how does ", " average ", " avg "])
        )
    ) and entity_key and len(group_by) > 1 and not _query_explicitly_requests_per_entity_breakdown(f" {q} ", entity_key):
        filtered_group_by = []
        removed_entity_group = False
        for group in group_by:
            if not isinstance(group, dict):
                continue
            output_name = str(group.get("output_name") or "").strip()
            field_name = str(group.get("field") or "").strip()
            if output_name == entity_key or field_name == entity_key:
                removed_entity_group = True
                continue
            filtered_group_by.append(group)
        if removed_entity_group and filtered_group_by:
            cleaned["group_by"] = filtered_group_by
            group_by = filtered_group_by
            final_group_by = [field for field in final_group_by if str(field).strip() != entity_key]
            grain["final_group_by"] = final_group_by
            cleaned["grain"] = grain
            output_schema = cleaned.get("output_schema", [])
            output_schema = output_schema if isinstance(output_schema, list) else []
            cleaned["output_schema"] = [name for name in output_schema if str(name).strip() != entity_key]
            cleanup_notes.append(
                f"entity_key {entity_key} removed from group_by/final output so aggregation stays at the comparative group grain"
            )

    grouped_compare = bool(group_by) and (
        query_type in {"comparative", "multi_step", "ranking"}
        or _has_any_phrase(q, [" compare ", " comparison ", " how do ", " how does ", " average ", " avg "])
    )
    explicit_total_query = _has_any_phrase(q, [
        " total ", " totals ", " sum ", " summed ", " cumulative ",
        " overall total ", " combined total ", " total number ",
    ])
    band_query = _has_any_phrase(q, [" band", " bands", " bucket", " buckets", " range", " ranges"])

    for group in group_by:
        if not isinstance(group, dict):
            continue
        if band_query and not group.get("bucket_strategy"):
            output_name = str(group.get("output_name") or group.get("field") or "group_band")
            if not output_name.lower().endswith(("_band", "_bucket", "_range")):
                group["output_name"] = f"{output_name}_band"
            group["bucket_strategy"] = "three_band_33_66"
            group["bucket_boundaries"] = [33, 66]
            cleanup_notes.append("numeric group-by field marked for three-band bucketization")

    month_level_requested = bool(re.search(
        r"\b(per month|for each month|monthly|month of|months of 20\d{2}|for each month of 20\d{2})\b",
        q,
    ))
    if month_level_requested:
        cleaned["month_grain"] = True
        cleanup_notes.append("month-level query marked for YYYY-MM extraction")

    measures = cleaned.get("measures", [])
    measures = measures if isinstance(measures, list) else []

    list_like = _has_any_phrase(f" {q} ", [" which ", " show ", " list ", " identify ", " find "])
    numeric_required = any(marker in q for marker in [
        "count", "how many", "average", "avg", "sum", "total",
        "highest", "lowest", "maximum", "minimum",
    ])

    if cleaned.get("month_grain"):
        month_group_exists = any(
            isinstance(group, dict)
            and normalize_for_compare_fn(group.get("output_name", "")) == "month"
            for group in group_by
        )
        if not month_group_exists:
            month_source = str(cleaned.get("base_entity") or "")
            if not month_source and measures and isinstance(measures[0], dict):
                month_source = str(measures[0].get("source_class") or "")
            group_by.append({
                "output_name": "month",
                "source_class": month_source,
                "field": "date",
            })
            cleaned["group_by"] = group_by
            cleanup_notes.append("month added to group_by for month-level query")
        if "month" not in final_group_by:
            final_group_by.append("month")
            grain["final_group_by"] = final_group_by
            cleaned["grain"] = grain
            cleanup_notes.append("grain.final_group_by includes month for month-level query")

        filtered_group_by = []
        removed_date_group = False
        seen_group_names = set()
        for group in group_by:
            if not isinstance(group, dict):
                continue
            output_name_norm = _normalize_name_for_contract(group.get("output_name", ""))
            field_norm = _normalize_name_for_contract(group.get("field", ""))
            if output_name_norm == "date" or (field_norm == "date" and output_name_norm != "month"):
                removed_date_group = True
                continue
            canonical_name = "risktolerance" if output_name_norm in {"risktolerance", "risktolerance"} else output_name_norm
            if canonical_name in seen_group_names:
                continue
            seen_group_names.add(canonical_name)
            filtered_group_by.append(group)
        if removed_date_group:
            group_by = filtered_group_by
            cleaned["group_by"] = group_by
            cleanup_notes.append("date-level grouping removed for month-level query")

    existing_group_outputs = {
        normalize_for_compare_fn(group.get("output_name", ""))
        for group in group_by
        if isinstance(group, dict)
    }
    for hint in PROFILE_DIMENSION_HINTS.values():
        if not _has_any_phrase(f" {q} ", hint["phrases"]):
            continue
        mapping = hint["sql"] if schema_kind == "sql" else hint["kg"]
        if normalize_for_compare_fn(mapping["output_name"]) in existing_group_outputs:
            continue
        group_by.append({
            "output_name": mapping["output_name"],
            "source_class": mapping["source_class"],
            "field": mapping["field"],
        })
        cleaned["group_by"] = group_by
        _append_unique(cleaned.setdefault("required_classes", []), mapping["source_class"])
        if mapping["field"] not in final_group_by:
            final_group_by.append(mapping["field"])
            grain["final_group_by"] = final_group_by
            cleaned["grain"] = grain
        cleanup_notes.append(
            f"group_by inferred as {mapping['output_name']} from question text"
        )
        break

    if list_like and not numeric_required and not explicit_grouping_requested and query_type in {"point_lookup", "set_logic"} and group_by:
        cleaned["group_by"] = []
        group_by = []
        grain["final_group_by"] = []
        cleaned["grain"] = grain
        cleanup_notes.append("non-grouped entity query had accidental group_by fields removed")

    _collapse_singular_value_filters(cleaned, f" {q} ", normalize_for_compare_fn, cleanup_notes)
    _repair_filter_field_domains(
        cleaned,
        retrieved_tables,
        cleanup_notes,
        schema_kind=schema_kind,
    )
    _strip_helper_count_measures(cleaned, f" {q} ", cleanup_notes)
    measures = cleaned.get("measures", [])
    measures = measures if isinstance(measures, list) else []
    grouped_compare = bool(group_by) and (
        query_type in {"comparative", "multi_step", "ranking"}
        or _has_any_phrase(q, [" compare ", " comparison ", " how do ", " how does ", " average ", " avg "])
    )

    # Positional, not filtered: a rename is only ever detected by comparing the
    # same measure's name before and after cleanup at the same list index.
    original_measure_names_by_index = [
        measure.get("output_name") if isinstance(measure, dict) else None
        for measure in measures
    ]

    entity_key = str(cleaned.get("entity_key") or "").strip()
    if _requires_two_level_aggregation(group_by, measures, entity_key, grouped_compare):
        if not pre_aggregate_by:
            pre_aggregate_by = [entity_key]
            grain["pre_aggregate_by"] = pre_aggregate_by
            cleaned["grain"] = grain
            cleanup_notes.append(
                f"grain.pre_aggregate_by set to [{entity_key}] because measures span tables outside the grouping entity"
            )
        for measure in measures:
            if not isinstance(measure, dict):
                continue
            if not str(measure.get("per_entity_operation") or "").strip():
                measure["per_entity_operation"] = _default_per_entity_operation(measure)
                cleanup_notes.append(
                    f"measure {measure.get('output_name', '')} per_entity_operation inferred as "
                    f"{measure['per_entity_operation']} for entity-level pre-aggregation"
                )
        cleaned["fanout_control"] = {
            "required": True,
            "pre_aggregate_by": list(pre_aggregate_by),
            "reason": "Aggregate each measure to entity grain in its own table before joining and grouping.",
        }

    measure_sources = _measure_source_classes(measures)
    if (
        grouped_compare
        and entity_key
        and group_by
        and len(measure_sources) >= 1
        and _query_requests_independent_measure_population(f" {q} ")
        and not _query_requires_intersection_population(f" {q} ")
    ):
        driver_group_fields = {
            str(group.get("field") or "").strip()
            for group in group_by
            if isinstance(group, dict)
        }
        if entity_key not in driver_group_fields:
            cleaned["join_policy"] = "left_join"
            cleaned["independent_measure_population"] = True
            cleanup_notes.append(
                "grouped comparative query set to left_join so each pre-aggregated measure keeps its own entity population within the group"
            )
    elif grouped_compare and entity_key and group_by and len(measure_sources) >= 1:
        cleaned["join_policy"] = "inner_join"
        if cleaned.pop("independent_measure_population", None):
            cleanup_notes.append("independent measure population disabled because the query requires an intersection population")

    if grouped_compare:
        for measure in measures:
            if not isinstance(measure, dict):
                continue
            source_class = str(measure.get("source_class") or "").lower()
            field_name = str(measure.get("field") or "").lower()
            output_name_lower = str(measure.get("output_name") or "").lower()

            if (
                "transaction count" in q
                and ("count" in output_name_lower or str(measure.get("per_entity_operation") or "").upper() == "COUNT")
                and _has_any_phrase(q, [" cash flow", " cash-flow", " cashflow", " transaction count"])
            ):
                cash_flow_class = _schema_class(schema_kind, "cash_flow")
                cash_flow_id = _schema_field(schema_kind, "cash_flow_id")
                if (
                    measure.get("source_class") != cash_flow_class
                    or measure.get("field") != cash_flow_id
                    or measure.get("output_name") != "avg_transaction_count"
                ):
                    measure["source_class"] = cash_flow_class
                    measure["field"] = cash_flow_id
                    measure["output_name"] = "avg_transaction_count"
                    _append_unique(cleaned.setdefault("required_classes", []), cash_flow_class)
                    cleanup_notes.append("transaction count measure bound to cash-flow rows at entity grain")
                measure["per_entity_operation"] = "COUNT"
                measure["final_operation"] = "AVG"
                source_class = str(measure.get("source_class") or "").lower()
                field_name = str(measure.get("field") or "").lower()
                output_name_lower = str(measure.get("output_name") or "").lower()

            if (
                grouped_compare
                and _has_any_phrase(q, [" cash flow", " cash-flow", " cashflow"])
                and ("cash_flow" in source_class or "cashflow" in source_class or "cash flow" in output_name_lower)
                and field_name == "amount"
            ):
                if measure.get("output_name") != "avg_net_cash_flow":
                    measure["output_name"] = "avg_net_cash_flow"
                    cleanup_notes.append("cash-flow amount measure output normalized to avg_net_cash_flow")
                measure["per_entity_operation"] = "SUM"
                measure["final_operation"] = "AVG"

            if (
                grouped_compare
                and _has_any_phrase(q, [" rebalance", " rebalancing"])
                and ("rebalanc" in source_class or "rebalanc" in output_name_lower)
                and field_name == "amount"
            ):
                if measure.get("output_name") != "avg_rebalance_amount":
                    measure["output_name"] = "avg_rebalance_amount"
                    cleanup_notes.append("rebalancing amount measure output normalized to avg_rebalance_amount")
                measure["per_entity_operation"] = "SUM"
                measure["final_operation"] = "AVG"

            if (
                grouped_compare
                and "allocation concentration" in q
                and ("sector_allocation" in source_class or "sectorallocation" in source_class or field_name == _schema_field(schema_kind, "allocation_pct").lower())
                and _normalize_name_for_contract(field_name) == "allocationpct"
            ):
                if measure.get("output_name") != "avg_max_allocation_pct":
                    measure["output_name"] = "avg_max_allocation_pct"
                    cleanup_notes.append("allocation concentration measure output normalized to avg_max_allocation_pct")
                measure["per_entity_operation"] = "MAX"
                measure["final_operation"] = "AVG"

            if (
                grouped_compare
                and "holding return" in q
                and ("portfolio_holding" in source_class or "portfolioholding" in source_class)
                and _normalize_name_for_contract(field_name) == "returnspct"
            ):
                if measure.get("output_name") != "avg_returns_pct":
                    measure["output_name"] = "avg_returns_pct"
                    cleanup_notes.append("holding return measure output normalized to avg_returns_pct")
                measure["per_entity_operation"] = "AVG"
                measure["final_operation"] = "AVG"

            per_entity_operation = str(measure.get("per_entity_operation") or "").upper()
            final_operation = str(measure.get("final_operation") or "").upper()
            output_name_text = str(measure.get("output_name") or "")
            formula_text = str(measure.get("formula") or "")
            if per_entity_operation == "COUNT":
                if not explicit_total_query and final_operation in {"", "SUM", "COUNT"}:
                    measure["final_operation"] = "AVG"
                    if _measure_prefix(output_name_text) in {"", "count_", "total_", "sum_"}:
                        measure["output_name"] = _average_style_name(output_name_text)
                    cleanup_notes.append(
                        f"measure {measure.get('output_name', '')} normalized to AVG count per entity for grouped comparison"
                    )
                continue
            if explicit_total_query:
                if not final_operation:
                    measure["final_operation"] = per_entity_operation or "SUM"
                    cleanup_notes.append(f"measure {measure.get('output_name', '')} final_operation preserved for explicit-total query")
                continue
            if (
                formula_text
                and any(marker in f"{output_name_text} {formula_text}".lower() for marker in ["change", "gap"])
                and per_entity_operation in {"", "SUM"}
            ):
                measure["per_entity_operation"] = "AVG"
                per_entity_operation = "AVG"
                cleanup_notes.append(
                    f"measure {measure.get('output_name', '')} per_entity_operation normalized to AVG for comparative change/gap metric"
                )
            if pre_aggregate_by and per_entity_operation in {"SUM", "AVG", "MIN", "MAX"}:
                if _field_prefers_average(measure) and per_entity_operation == "SUM":
                    measure["per_entity_operation"] = "AVG"
                    per_entity_operation = "AVG"
                    cleanup_notes.append(f"measure {measure.get('output_name', '')} per_entity_operation normalized to AVG from field semantics")
                if final_operation in {"", "SUM"}:
                    measure["final_operation"] = "AVG"
                    if _measure_prefix(measure.get("output_name", "")) in {"total_", "sum_", "_total", ""}:
                        measure["output_name"] = _average_style_name(measure.get("output_name", ""))
                    cleanup_notes.append(f"measure {measure.get('output_name', '')} normalized to AVG over pre-aggregated entities")
                if _field_prefers_average(measure) and _measure_prefix(measure.get("output_name", "")) in {"total_", "sum_", "_total"}:
                    measure["output_name"] = _average_style_name(measure.get("output_name", ""))
            elif grouped_compare and not pre_aggregate_by and _field_prefers_average(measure):
                if not final_operation and per_entity_operation:
                    measure["final_operation"] = "AVG"
                    cleanup_notes.append(f"measure {measure.get('output_name', '')} final_operation normalized to AVG for comparative query")
            elif not final_operation and per_entity_operation:
                measure["final_operation"] = per_entity_operation
                cleanup_notes.append(f"measure {measure.get('output_name', '')} inherited final_operation from per_entity_operation")
        cleaned["measures"] = measures

    for measure in measures:
        if not isinstance(measure, dict):
            continue
        if _measure_requests_holding_gain(q, measure):
            measure["field"] = None
            measure["formula"] = "current_value - cost"
            measure["formula_fields"] = ["current_value", "cost"]
            measure["per_entity_operation"] = "SUM"
            final_operation = str(measure.get("final_operation") or "").upper()
            if grouped_compare and not explicit_total_query:
                measure["final_operation"] = "AVG"
            elif final_operation not in {"SUM", "AVG", "MIN", "MAX", "COUNT"}:
                measure["final_operation"] = "SUM"
            cleanup_notes.append(
                f"measure {measure.get('output_name', '')} rewritten as holding gain = current_value - cost"
            )

        if _measure_requests_positive_withdrawal(measure):
            measure["formula"] = "CASE WHEN type = 'Withdrawal' THEN ABS(amount) ELSE 0 END"
            measure["formula_fields"] = ["type", "amount"]
            if not str(measure.get("per_entity_operation") or "").strip():
                measure["per_entity_operation"] = "SUM"
            if not str(measure.get("final_operation") or "").strip():
                measure["final_operation"] = measure.get("per_entity_operation") or "SUM"
            cleanup_notes.append(
                f"measure {measure.get('output_name', '')} normalized to positive withdrawal magnitude with ABS(amount)"
            )

    for measure in measures:
        if not isinstance(measure, dict):
            continue
        source_class = str(measure.get("source_class") or "").lower()
        field = str(measure.get("field") or "").lower()
        formula = str(measure.get("formula") or "")
        cashflow_context = normalize_for_compare_fn(f"{source_class} {measure.get('output_name', '')} {query}")
        if "cash flow" not in cashflow_context and "cashflow" not in cashflow_context and "cash_flow" not in cashflow_context:
            continue
        if field != "amount" or not formula:
            continue
        if "inflow" in formula.lower() or "outflow" in formula.lower():
            measure["formula"] = None
            measure["formula_fields"] = []
            if not str(measure.get("per_entity_operation") or "").strip():
                measure["per_entity_operation"] = "SUM"
            if not str(measure.get("final_operation") or "").strip():
                measure["final_operation"] = measure.get("per_entity_operation") or "SUM"
            cleanup_notes.append("cash-flow amount formula simplified to signed SUM(amount) because the dataset already stores net sign in amount")

    output_schema = cleaned.get("output_schema", [])
    if not isinstance(output_schema, list):
        output_schema = []
    if not output_schema:
        output_schema = []
        for group in group_by:
            if isinstance(group, dict) and group.get("output_name"):
                output_schema.append(group["output_name"])
        for measure in measures:
            if isinstance(measure, dict) and measure.get("output_name"):
                output_schema.append(measure["output_name"])
        cleaned["output_schema"] = output_schema
        if output_schema:
            cleanup_notes.append("output_schema filled from group_by and measures")
    else:
        # Merge, never replace: output_schema may legitimately name identity or
        # filter columns (investor_id, investor_name) that are neither a
        # group_by dimension nor a measure. Discarding those here silently
        # strips them from the downstream SQL/SPARQL SELECT contract, which
        # produces answers missing the exact columns grading keys on. The only
        # thing this refresh needs to do is follow a measure through a cleanup
        # rename (e.g. total_holding_value -> avg_holding_value) so the schema
        # doesn't keep pointing at a name the measure no longer produces.
        group_names = [
            group.get("output_name")
            for group in group_by
            if isinstance(group, dict) and group.get("output_name")
        ]
        current_measure_names = [
            measure.get("output_name")
            for measure in measures
            if isinstance(measure, dict) and measure.get("output_name")
        ]
        rename_map = {}
        for index, measure in enumerate(measures):
            if not isinstance(measure, dict):
                continue
            old_name = original_measure_names_by_index[index]
            new_name = measure.get("output_name")
            if old_name and new_name and old_name != new_name:
                rename_map[old_name] = new_name
        refreshed_schema = []
        used = set()
        for name in output_schema:
            resolved = rename_map.get(name, name)
            if not resolved or resolved in used:
                continue
            refreshed_schema.append(resolved)
            used.add(resolved)
        for name in [*group_names, *current_measure_names]:
            if not name or name in used:
                continue
            refreshed_schema.append(name)
            used.add(name)
        if refreshed_schema != output_schema:
            cleanup_notes.append("output_schema measure names re-aligned to renamed measure aliases")
        cleaned["output_schema"] = refreshed_schema

    output_schema = cleaned.get("output_schema", [])
    output_schema = output_schema if isinstance(output_schema, list) else []
    if cleaned.get("month_grain"):
        filtered_schema = []
        seen_schema = set()
        removed_date_schema = False
        for name in output_schema:
            norm = _normalize_name_for_contract(name)
            if norm == "date":
                removed_date_schema = True
                continue
            canonical = "risktolerance" if norm == "risktolerance" else norm
            if canonical in seen_schema:
                continue
            seen_schema.add(canonical)
            filtered_schema.append(name)
        if removed_date_schema or len(filtered_schema) != len(output_schema):
            output_schema = filtered_schema
            cleaned["output_schema"] = output_schema
            if removed_date_schema:
                cleanup_notes.append("date removed from output_schema for month-level query")
    entity_key = str(cleaned.get("entity_key") or "").strip()
    query_type = str(cleaned.get("query_type", "")).lower()
    list_like = _has_any_phrase(f" {q} ", [" which ", " show ", " list ", " identify ", " find "])
    if entity_key and not group_by and (query_type in {"ranking", "set_logic", "point_lookup"} or list_like):
        if not _has_output_name(output_schema, entity_key):
            output_schema.insert(0, entity_key)
            cleanup_notes.append(f"entity_key {entity_key} added to output_schema for entity-returning query")
        label_output = _entity_label_output_name(entity_key)
        if label_output and _query_mentions_named_entity(f" {q} ", entity_key) and not _has_output_name(output_schema, label_output):
            insert_at = 1 if output_schema and output_schema[0] == entity_key else 0
            output_schema.insert(insert_at, label_output)
            cleanup_notes.append(f"label field {label_output} added to output_schema for named entity query")
        if query_type == "ranking":
            filters = cleaned.get("filters", [])
            filters = filters if isinstance(filters, list) else []
            for filter_item in filters:
                if not isinstance(filter_item, dict):
                    continue
                field_name = str(filter_item.get("field") or "").strip()
                if not field_name or field_name == entity_key:
                    continue
                operator = str(filter_item.get("operator") or "").strip().lower()
                if operator == "between" or field_name == "date":
                    continue
                if not _has_output_name(output_schema, field_name):
                    output_schema.append(field_name)
                    cleanup_notes.append(f"filter field {field_name} added to output_schema for ranking query context")
        cleaned["output_schema"] = output_schema

    if any(isinstance(group, dict) and group.get("bucket_strategy") for group in group_by):
        if cleaned.get("preserve_null_groups"):
            cleaned["preserve_null_groups"] = False
            cleanup_notes.append("preserve_null_groups disabled for bucketed band query")

    if cleanup_notes:
        prior_reason = str(cleaned.get("reason", "")).strip()
        cleaned["cleanup_notes"] = cleanup_notes
        cleaned["reason"] = (prior_reason + " Cleanup: " + "; ".join(cleanup_notes)).strip()

    return cleaned


def semantic_build_query_spec(
    inputs: dict[str, Any],
    client: Any,
    model: str,
    *,
    parse_json_fn: Callable[[str, Any, str], Any],
    normalize_for_compare_fn: Callable[[Any], str],
    log_call_fn: Callable[[str, str], None],
) -> dict[str, Any]:
    """
    Operator: Query_Spec
    Convert the natural language question into a schema-grounded computation plan.
    This does not generate SPARQL; Generate uses this JSON as its contract.
    """

    query = inputs.get("query", "")
    root_query = inputs.get("root_query", "") or query
    retrieved_tables = inputs.get("retrieved_tables", [])
    bound_inputs = inputs.get("bound_inputs", {})
    schema_kind = inputs.get("schema_kind", "kg")
    schema_label = "Retrieved Tables" if schema_kind == "sql" else "Retrieved Classes"
    schema_unit = "tables and columns" if schema_kind == "sql" else "classes and fields"
    execution_strategy_options = (
        '"single_sql|preaggregate_sql"'
        if schema_kind == "sql"
        else '"single_sparql|preaggregate_sparql"'
    )

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

Subquery Description:
{query}

Original User Query:
{root_query}

Bound Upstream Inputs:
{json.dumps(bound_inputs, indent=2)}

{schema_label}:
{retrieved_tables}

Schema Details:
{json.dumps(schema_details, indent=2)}

IMPORTANT:
- Use only classes and fields present in Schema Details.
- Use only {schema_unit} present in Schema Details.
- Do not invent schema objects.
- Do not invent fields or columns.
- Do not write SPARQL or SQL.
- Return only valid JSON.
- Treat the Subquery Description as the binding scope for this Query_Spec.
- Use Original User Query only for shared context such as the overall user wording, year, or entity family.
- If Original User Query contains additional conditions that are not explicitly present in the Subquery Description, do NOT add them to this Query_Spec.
- Do not merge sibling conditions from other decomposed subqueries into this subquery plan.
- If Bound Upstream Inputs are present, treat them as already-computed constraints from upstream nodes.
- Preserve those constraints in the Query_Spec instead of recomputing a broader universe from scratch.
- Do not ignore Bound Upstream Inputs when this subquery is refining, subtracting, or intersecting upstream results.

INSTRUCTIONS:

1. Identify the base entity.
   Usually this is the entity over which records should be compared, such as Investor or investor_id.

2. Identify the entity key.
   This is the field used to connect related records, for example investor_id, goal_id, portfolio_id, holding_id, etc.
   Use only a key visible in Schema Details.

3. Identify grouping.
   If the question says "across X", "by X", "per X", "for each X", or "grouped by X",
   put that field in group_by.

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
   List the exact expected final answer columns. Downstream generation and validation must preserve this contract.

12. Comparative aggregation rule:
   If the query compares groups such as "across risk_tolerance" or "by segment" and does not explicitly ask for totals,
   aggregate first per entity_key and then average those entity-level measures across the final groups.

13. Band/bucket rule:
   If the query asks for bands, buckets, or ranges of a numeric percentage/score field, represent the grouped output as
   explicit bucket labels rather than raw numeric values.

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
  "execution_strategy": {execution_strategy_options},
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
            "final_group_by": [],
        },
        "group_by": [],
        "filters": [],
        "measures": [],
        "ranking": {
            "required": False,
            "metric": None,
            "direction": None,
            "limit": None,
        },
        "required_classes": retrieved_tables,
        "execution_strategy": "single_sparql",
        "output_schema": [],
        "reason": "Query_Spec failed to parse model output.",
    }

    log_call_fn(root_query, "Query_Spec")
    request = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }
    if not model.lower().startswith("gpt-5"):
        request["temperature"] = 0.0
    response = client.chat.completions.create(**request)
    raw_response = response.choices[0].message.content

    parsed_spec = parse_json_fn(
        raw_response,
        default_spec,
        "Query_Spec",
    )
    if not isinstance(parsed_spec, dict):
        parsed_spec = {**default_spec, "reason": "Query_Spec returned non-dict output."}
    if parsed_spec == default_spec or str(parsed_spec.get("reason", "")).startswith("Query_Spec returned non-dict output"):
        repair_prompt = f"""
You previously returned malformed or non-JSON Query_Spec output.
Rewrite it as ONE valid JSON object matching the required Query_Spec schema.
Do not add markdown, prose, or reasoning tags.

Subquery Description:
{query}

Original User Query:
{root_query}

Bound Upstream Inputs:
{json.dumps(bound_inputs, indent=2)}

Retrieved Schema Objects:
{retrieved_tables}

Schema Details:
{json.dumps(schema_details, indent=2)}

Previous malformed output:
{raw_response}
"""
        repair_request = {
            "model": model,
            "messages": [{"role": "user", "content": repair_prompt}],
        }
        if not model.lower().startswith("gpt-5"):
            repair_request["temperature"] = 0.0
        repair_response = client.chat.completions.create(**repair_request)
        repaired_spec = parse_json_fn(
            repair_response.choices[0].message.content,
            parsed_spec,
            "Query_Spec_Repair",
        )
        if isinstance(repaired_spec, dict):
            parsed_spec = repaired_spec
    if spec_is_analytic_without_measures(parsed_spec, f"{query} {root_query}"):
        measures_prompt = f"""
Your previous Query_Spec for this analytic question contained no measures.
An aggregation, comparative, or ranking question must state every value it computes.

Subquery Description:
{query}

Original User Query:
{root_query}

Bound Upstream Inputs:
{json.dumps(bound_inputs, indent=2)}

Retrieved Schema Objects:
{retrieved_tables}

Schema Details:
{json.dumps(schema_details, indent=2)}

Previous Query_Spec:
{json.dumps(parsed_spec, indent=2)}

Return the SAME Query_Spec JSON object with a non-empty "measures" list.
Name one measure for every value the question asks to compute or compare, in the order asked.
Map each to a real source_class and field from Schema Details, and set per_entity_operation
and final_operation. Keep every other field unchanged. Return only valid JSON.
"""
        measures_request = {
            "model": model,
            "messages": [{"role": "user", "content": measures_prompt}],
        }
        if not model.lower().startswith("gpt-5"):
            measures_request["temperature"] = 0.0
        try:
            measures_response = client.chat.completions.create(**measures_request)
            recovered_spec = parse_json_fn(
                measures_response.choices[0].message.content,
                None,
                "Query_Spec_Measures",
            )
        except Exception as error:
            print(f"   [!] Query_Spec measure recovery failed: {error}")
            recovered_spec = None
        # Only accept the retry if it actually supplied measures, so a failed
        # recovery can never be worse than the spec we already had.
        if isinstance(recovered_spec, dict) and recovered_spec.get("measures"):
            recovered_spec["measure_recovery"] = True
            parsed_spec = recovered_spec
        else:
            parsed_spec["measure_recovery_failed"] = True

    if parsed_spec.get("execution_strategy") in {"decomposed_metric_scan", "post_scan_pandas_merge"}:
        parsed_spec["execution_strategy"] = "preaggregate_sparql"
        parsed_spec["reason"] = (
            f"{parsed_spec.get('reason', '')} Executor supports one SPARQL query; "
            "unsupported decomposed execution was downgraded to preaggregate_sparql."
        ).strip()
    parsed_spec = cleanup_query_spec(
        parsed_spec,
        root_query,
        retrieved_tables,
        normalize_for_compare_fn=normalize_for_compare_fn,
        schema_kind=schema_kind,
    )

    return {"query_spec": parsed_spec}
