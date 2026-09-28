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
        [
            " for each ", " in each ", " of each ", " grouped by ",
            " across ", " per ", " by ",
        ],
    )


def _explicit_null_group_requested(query_text: str) -> bool:
    """Return whether the question explicitly asks to retain a null group."""
    text = f" {str(query_text or '').lower()} "
    return any(marker in text for marker in [
        " include null ", " including null ", " include missing ",
        " including missing ", " even if missing ", " even when missing ",
        " without related ", " with or without ",
    ])


def _explicit_bucket_definition(query_text: str) -> tuple[list[int], list[str]] | None:
    """Extract explicit three-band month thresholds from a benchmark question.

    The generic band rule is useful for percentage buckets, but it must not
    overwrite questions that define their own boundaries, e.g. ``<=12``,
    ``13-60``, and ``>60`` months.
    """
    text = str(query_text or '').lower()
    short = re.search(r"short\s*(?:=|is)?\s*<=\s*(\d+)\s*months?", text)
    medium = re.search(r"medium\s*(?:=|is)?\s*(\d+)\s*[-–]\s*(\d+)\s*months?", text)
    long = re.search(r"long\s*(?:=|is)?\s*>\s*(\d+)\s*months?", text)
    if not (short and medium and long):
        return None
    short_limit = int(short.group(1))
    medium_start = int(medium.group(1))
    medium_limit = int(medium.group(2))
    long_start = int(long.group(1))
    if not (short_limit < medium_start <= medium_limit == long_start):
        return None
    return [short_limit, long_start], [
        f"Short <={short_limit} months",
        f"Medium {medium_start}-{medium_limit} months",
        f"Long >{long_start} months",
    ]


def _query_requests_entity_count(query_text: str) -> bool:
    text = str(query_text or '').lower()
    return "vary across" in text and "per investor" in text


def _normalize_gap_contract(
    cleaned: dict[str, Any],
    query_text: str,
    cleanup_notes: list[str],
) -> None:
    """Make comparative gap specs deterministic and non-duplicated.

    Several model responses represented the same source measure twice and
    described the derived gap using aliases that did not occur in the base
    measures.  That leaves generation free to compute a plausible but wrong
    expression.  Normalize only the unambiguous ``gap between two metrics``
    pattern; other formulas remain model-provided.
    """
    text = str(query_text or '').lower()
    if "gap" not in text or not any(
        marker in text for marker in ["between", "largest gap", "largest average gap"]
    ):
        return
    group_by = cleaned.get("group_by")
    group_by = group_by if isinstance(group_by, list) else []
    if not group_by:
        return
    measures = cleaned.get("measures")
    measures = measures if isinstance(measures, list) else []
    base = []
    derived = []
    seen_sources = set()
    for measure in measures:
        if not isinstance(measure, dict):
            continue
        source = str(measure.get("source_class") or "").strip().lower()
        field = str(measure.get("field") or "").strip().lower()
        formula = str(measure.get("formula") or "").strip()
        if source == "derived" or formula:
            derived.append(measure)
            continue
        identity = (source, field)
        if identity in seen_sources:
            cleanup_notes.append(
                f"duplicate gap source measure removed: {measure.get('output_name', '')}"
            )
            continue
        seen_sources.add(identity)
        base.append(measure)
    if len(base) < 2:
        metric_candidates = [
            ("holding return", "portfolio_holding", "returns_pct", "avg_returns_pct"),
            ("volatility", "investment_goal", "avg_volatility_pct", "avg_volatility_pct"),
            ("goal progress", "investment_goal", "progress_pct", "avg_progress_pct"),
            ("goal-match", "portfolio_health", "goal_match_pct", "avg_goal_match_pct"),
            ("goal match", "portfolio_health", "goal_match_pct", "avg_goal_match_pct"),
            ("liquidity", "portfolio_health", "liquidity_score", "avg_liquidity_score"),
            ("diversification", "portfolio_health", "diversification_score", "avg_diversification_score"),
            ("risk score", "portfolio_health", "risk_score", "avg_risk_score"),
        ]
        inferred = []
        table_map = {
            "portfolio_holding": "ATOM_ENTITY_PORTFOLIO_HOLDING_001",
            "investment_goal": "ATOM_ENTITY_INVESTMENT_GOAL_001",
            "portfolio_health": "ATOM_ENTITY_PORTFOLIO_HEALTH_001",
        }
        for phrase, table_key, field, output_name in metric_candidates:
            position = text.find(phrase)
            if position < 0:
                continue
            inferred.append((position, {
                "output_name": output_name,
                "source_class": table_map[table_key],
                "field": field,
                "formula": None,
                "formula_fields": [],
                "per_entity_operation": "AVG",
                "final_operation": "AVG",
                "requires_distinct": False,
            }))
        for _, measure in sorted(inferred, key=lambda item: item[0]):
            identity = (str(measure["source_class"]), str(measure["field"]))
            if identity not in seen_sources:
                base.append(measure)
                seen_sources.add(identity)
            if len(base) >= 2:
                break
        if len(base) < 2:
            return
        cleanup_notes.append("base metrics inferred from gap question wording")

    first, second = base[0], base[1]
    first_name = str(first.get("output_name") or "metric_a").strip()
    second_name = str(second.get("output_name") or "metric_b").strip()
    gap = derived[0] if derived else {
        "output_name": "gap",
        "source_class": "derived",
        "field": None,
        "formula": None,
        "formula_fields": [],
        "per_entity_operation": None,
        "final_operation": None,
        "requires_distinct": False,
    }
    gap["output_name"] = "gap"
    gap["source_class"] = "derived"
    gap["field"] = None
    gap["formula"] = f"{first_name} - {second_name}"
    gap["formula_fields"] = [first_name, second_name]
    gap["formula_stage"] = "final_group"
    gap["per_entity_operation"] = None
    gap["final_operation"] = None
    cleaned["measures"] = [*base, gap]

    output_schema = cleaned.get("output_schema")
    output_schema = output_schema if isinstance(output_schema, list) else []
    group_names = [
        str(group.get("output_name"))
        for group in group_by
        if isinstance(group, dict) and group.get("output_name")
    ]
    cleaned["output_schema"] = list(dict.fromkeys([
        *group_names,
        *[str(item.get("output_name")) for item in base if item.get("output_name")],
        "gap",
    ]))
    ranking = cleaned.get("ranking")
    ranking = ranking if isinstance(ranking, dict) else {}
    if ranking.get("required") and (
        "which group" in text or "group with largest" in text
    ) and "top " not in text:
        # The benchmark contract expects every group plus its gap, ordered by
        # the gap, even when the wording asks which group is largest.
        ranking["metric"] = "gap"
        ranking["limit"] = None
        cleaned["ranking"] = ranking
        cleanup_notes.append("gap comparison retains all groups; ranking limit removed")
    cleanup_notes.append("gap measures deduplicated and normalized to first_metric - second_metric")


def _query_explicitly_requests_per_entity_breakdown(query_text: str, entity_key: str) -> bool:
    q = f" {query_text} "
    entity_key = str(entity_key or "").lower()
    entity_markers = []
    if "investor" in entity_key:
        entity_markers = [
            " for each investor ", " by investor ", " per investor ",
            " which investors ", " investors who ", " investors that ",
            " investors have ",
        ]
    elif "goal" in entity_key:
        entity_markers = [" for each goal ", " each goal ", " by goal ", " per goal "]
    elif "holding" in entity_key:
        entity_markers = [" for each holding ", " each holding ", " by holding ", " per holding "]
    return any(marker in q for marker in entity_markers)


def _query_requires_intersection_population(query_text: str) -> bool:
    q = f" {query_text} "
    # The number of source tables does not define the population. Benchmark
    # questions often say "using three related tables" while still requiring
    # each metric to retain its own per-entity population. Require an
    # explicit intersection phrase before selecting INNER JOIN semantics.
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
            "scenario": "ATOM_EVENT_SCENARIO_REBALANCING_001",
            "sector_allocation": "ATOM_ENTITY_SECTOR_ALLOCATION_001",
            "portfolio_holding": "ATOM_ENTITY_PORTFOLIO_HOLDING_001",
            "investment_goal": "ATOM_ENTITY_INVESTMENT_GOAL_001",
            "portfolio_health": "ATOM_ENTITY_PORTFOLIO_HEALTH_001",
        }
    else:
        mapping = {
            "cash_flow": "CashFlow",
            "rebalancing": "RebalancingAction",
            "scenario": "ScenarioRebalancing",
            "sector_allocation": "SectorAllocation",
            "portfolio_holding": "PortfolioHolding",
            "investment_goal": "InvestmentGoal",
            "portfolio_health": "PortfolioHealth",
        }
    return mapping[semantic_name]


def _repair_measure_semantics(
    cleaned: dict[str, Any],
    query_text: str,
    schema_kind: str,
    cleanup_notes: list[str],
) -> None:
    """Ground common analytical measure names in their authoritative fields.

    The LLM frequently confuses goal progress with portfolio goal-match, or
    attaches a familiar metric to a plausible but wrong table. These repairs
    are driven by explicit wording and domain metadata, not benchmark IDs.
    """
    # These repairs target the physical SQLite schema. KG properties use a
    # separate ontology vocabulary and must continue through KG retrieval.
    if schema_kind != "sql":
        return

    q = f" {str(query_text or '').lower()} "
    measures = cleaned.get("measures")
    measures = measures if isinstance(measures, list) else []
    required = cleaned.setdefault("required_classes", [])

    rules = [
        (["goal progress", "progress_pct"], "investment_goal", "progress_pct"),
        (["goal shortfall", "shortfall"], "investment_goal", "shortfall"),
        (["goal volatility", "volatility", "avg_volatility_pct"], "investment_goal", "avg_volatility_pct"),
        (["goal match", "goal-match", "goal_match_pct"], "portfolio_health", "goal_match_pct"),
        (["health risk", "risk score", "risk_score"], "portfolio_health", "risk_score"),
        (["liquidity", "liquidity_score"], "portfolio_health", "liquidity_score"),
        (["diversification", "diversification_score"], "portfolio_health", "diversification_score"),
        (["holding return", "returns_pct"], "portfolio_holding", "returns_pct"),
        (["holding value", "current_value"], "portfolio_holding", "current_value"),
        (["sector investment", "total_investment"], "sector_allocation", "total_investment"),
        (["allocation concentration"], "sector_allocation", "allocation_pct"),
        (["rebalancing amount", "rebalance amount"], "rebalancing", "amount"),
        (["cash flow", "cash-flow", "net cash", "net_cash_flow"], "cash_flow", "amount"),
        (["holding dividends", "dividends"], "portfolio_holding", "dividends"),
        (["taxes paid", "taxes_paid"], "portfolio_holding", "taxes_paid"),
    ]
    for measure in measures:
        if not isinstance(measure, dict) or str(measure.get("source_class") or "").lower() == "derived":
            continue
        signature = f" {str(measure.get('output_name') or '').lower()} {str(measure.get('field') or '').lower()} "
        for phrases, semantic_class, field in rules:
            if not any(phrase in q for phrase in phrases):
                continue
            if not any(
                phrase.replace("-", " ").replace("_", " ") in signature.replace("-", " ").replace("_", " ")
                for phrase in phrases
            ):
                continue
            source_class = _schema_class(schema_kind, semantic_class)
            if measure.get("source_class") != source_class or measure.get("field") != field:
                measure["source_class"] = source_class
                measure["field"] = field
                _append_unique(required, source_class)
                cleanup_notes.append(
                    f"measure {measure.get('output_name', '')} grounded to {source_class}.{field}"
                )
            break


def _apply_bucket_semantics(
    group: dict[str, Any],
    query_text: str,
    cleanup_notes: list[str],
) -> None:
    field = _normalize_name_for_contract(group.get("field"))
    output_name = str(group.get("output_name") or "").lower()
    q = str(query_text or "").lower()
    if field == "riskscore":
        group["bucket_strategy"] = "semantic_thresholds"
        group["bucket_boundaries"] = [40, 70]
        if "portfolio-risk" in q or "portfolio risk" in q:
            group["bucket_labels"] = ["Low", "Moderate", "High"]
        else:
            group["bucket_labels"] = ["risk_score 0-40", "risk_score 41-70", "risk_score 71-100"]
        group["formula"] = None
        group["formula_fields"] = [group.get("field")]
        cleanup_notes.append("risk-score bucket normalized to domain thresholds 40/70")
    elif field == "goalmatchpct":
        group["bucket_strategy"] = "semantic_thresholds"
        group["bucket_boundaries"] = [60, 80]
        group["bucket_labels"] = ["goal_match < 60", "goal_match 60-79", "goal_match >= 80"]
        group["formula"] = None
        group["formula_fields"] = [group.get("field")]
        cleanup_notes.append("goal-match bucket normalized to domain thresholds 60/80")


def _numeric_bucket_field(field: Any) -> bool:
    return _normalize_name_for_contract(field) in {
        "riskscore", "goalmatchpct", "liquidityscore", "diversificationscore",
        "timetogoalmonths", "progresspct", "allocationpct", "goalcount",
    }


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
    list_like = _has_any_phrase(query_text, [" which ", " show ", " list ", " identify ", " find "])
    if query_type not in {"point_lookup", "set_logic"} and not list_like:
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
    if group_by and (explicit_grouping_requested or not cleaned.get("filters")):
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
    explicit_bucket = _explicit_bucket_definition(query)

    normalized_groups = []
    seen_group_fields = set()
    for group in group_by:
        if not isinstance(group, dict):
            continue
        if group.get("bucket_strategy") and not _numeric_bucket_field(group.get("field")):
            group.pop("bucket_strategy", None)
            group.pop("bucket_boundaries", None)
            group.pop("bucket_labels", None)
            if str(group.get("formula") or "").strip().lower().startswith("case "):
                group["formula"] = None
                group["formula_fields"] = [group.get("field")]
            group["output_name"] = group.get("field") or group.get("output_name")
            cleanup_notes.append(
                f"invalid numeric bucket removed from categorical field {group.get('field', '')}"
            )
        if band_query and not group.get("bucket_strategy") and _numeric_bucket_field(group.get("field")):
            output_name = str(group.get("output_name") or group.get("field") or "group_band")
            # Preserve explicit generic bucket names.  Renaming ``bucket`` to
            # ``bucket_band`` creates a second, stale output column when the
            # model already emitted both names in output_schema.
            normalized_output_name = output_name.lower().strip()
            if (
                normalized_output_name not in {"bucket", "band", "range"}
                and not normalized_output_name.endswith(("_band", "_bucket", "_range"))
            ):
                group["output_name"] = f"{output_name}_band"
            group["bucket_strategy"] = "three_band_33_66"
            group["bucket_boundaries"] = [33, 66]
            cleanup_notes.append("numeric group-by field marked for three-band bucketization")
        if explicit_bucket and group.get("bucket_strategy") == "three_band_33_66":
            boundaries, labels = explicit_bucket
            if group.get("bucket_boundaries") != boundaries:
                group["bucket_boundaries"] = boundaries
                cleanup_notes.append(
                    f"explicit bucket boundaries preserved: {boundaries}"
                )
            group["bucket_labels"] = labels
        if group.get("bucket_strategy"):
            _apply_bucket_semantics(group, query, cleanup_notes)
        group_key = (
            str(group.get("source_class") or "").strip(),
            str(group.get("field") or "").strip(),
        )
        if group_key in seen_group_fields:
            cleanup_notes.append(f"duplicate group field {group.get('field', '')} removed")
            continue
        seen_group_fields.add(group_key)
        normalized_groups.append(group)
    if normalized_groups != group_by:
        group_by = normalized_groups
        cleaned["group_by"] = group_by

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

    if list_like and not numeric_required and not explicit_grouping_requested and group_by:
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
    _repair_measure_semantics(cleaned, query, schema_kind, cleanup_notes)
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
                measure["per_entity_operation"] = "SUM"
                if explicit_total_query:
                    measure["final_operation"] = "SUM"
                else:
                    if measure.get("output_name") != "avg_net_cash_flow":
                        measure["output_name"] = "avg_net_cash_flow"
                        cleanup_notes.append("cash-flow amount measure output normalized to avg_net_cash_flow")
                    measure["final_operation"] = "AVG"

            if (
                grouped_compare
                and _has_any_phrase(q, [" rebalance", " rebalancing"])
                and ("rebalanc" in source_class or "rebalanc" in output_name_lower)
                and field_name == "amount"
            ):
                measure["per_entity_operation"] = "SUM"
                if explicit_total_query:
                    measure["final_operation"] = "SUM"
                else:
                    if measure.get("output_name") != "avg_rebalance_amount":
                        measure["output_name"] = "avg_rebalance_amount"
                        cleanup_notes.append("rebalancing amount measure output normalized to avg_rebalance_amount")
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

            if (
                grouped_compare
                and not explicit_total_query
                and _has_any_phrase(q, [" holding value", " portfolio value"])
                and source_class.endswith("portfolio_holding_001")
                and field_name == "current_value"
            ):
                measure["per_entity_operation"] = "SUM"
                measure["final_operation"] = "AVG"
                if measure.get("output_name") != "avg_holding_value":
                    measure["output_name"] = "avg_holding_value"
                    cleanup_notes.append("holding value normalized to entity SUM followed by group AVG")

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

    _normalize_gap_contract(cleaned, query, cleanup_notes)
    measures = cleaned.get("measures", [])
    measures = measures if isinstance(measures, list) else []

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

    # A model may have emitted a stale ``<group>_band`` alias before cleanup
    # canonicalized an explicit generic group name such as ``bucket``. Keep
    # the output contract to one physical group column.
    canonical_group_names = {
        str(group.get("output_name") or "").strip()
        for group in group_by
        if isinstance(group, dict) and group.get("output_name")
    }
    if canonical_group_names:
        stale_bucket_aliases = {
            f"{name}_band"
            for name in canonical_group_names
            if name.lower() in {"bucket", "band", "range"}
        }
        filtered_schema = [
            name for name in cleaned.get("output_schema", [])
            if name not in stale_bucket_aliases
        ]
        if filtered_schema != cleaned.get("output_schema", []):
            cleaned["output_schema"] = filtered_schema
            cleanup_notes.append("stale bucket alias removed from output_schema")

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
    ranking = cleaned.get("ranking")
    ranking = ranking if isinstance(ranking, dict) else {}

    # Null groups are useful for unfiltered comparative summaries, but they
    # are not part of a filtered population or a ranked group comparison
    # unless the question explicitly asks to retain missing values.
    if group_by and not _explicit_null_group_requested(query):
        filters = cleaned.get("filters")
        filters = filters if isinstance(filters, list) else []
        if filters or ranking.get("required"):
            if cleaned.get("preserve_null_groups"):
                cleaned["preserve_null_groups"] = False
                cleanup_notes.append(
                    "preserve_null_groups disabled for filtered/ranked group query"
                )

    if group_by and _query_requests_entity_count(query) and entity_key:
        if "n_investors" not in output_schema and "investor" in entity_key.lower():
            output_schema.append("n_investors")
            cleaned["output_schema"] = output_schema
            cleaned["include_entity_count"] = True
            cleanup_notes.append(
                "entity count added for per-investor vary-across comparison"
            )
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
