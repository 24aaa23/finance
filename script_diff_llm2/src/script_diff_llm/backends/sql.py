import json
import sqlite3
from typing import Dict, Any, Tuple
import os
import re
from pathlib import Path

def parse_llm_json_with_error(raw_text: str, default: Any, context: str) -> Tuple[Any, str]:
    text = (raw_text or "").strip()
    if not text:
        error = "empty response"
        print(f"   [!] Failed to parse JSON for {context}: {error}")
        return default, error

    clean = text.replace("```json", "").replace("```JSON", "").replace("```", "").strip()
    candidates = [clean]
    object_start = clean.find("{")
    object_end = clean.rfind("}")
    if object_start != -1 and object_end > object_start:
        candidates.append(clean[object_start:object_end + 1])

    last_error = ""
    for candidate in candidates:
        try:
            return json.loads(candidate), ""
        except Exception as e:
            last_error = str(e)

    decoder = json.JSONDecoder()
    for start, char in enumerate(clean):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(clean[start:])
            if isinstance(parsed, dict):
                return parsed, ""
        except json.JSONDecodeError as e:
            last_error = str(e)

    preview = clean[:300].replace("\n", " ")
    print(f"   [!] Failed to parse JSON for {context}: {last_error}. Response preview: {preview}")
    return default, last_error

def parse_llm_json(raw_text: str, default: Any, context: str) -> Any:
    parsed, _ = parse_llm_json_with_error(raw_text, default, context)
    return parsed


def _schema_table_names(sql_schema: Dict[str, Any]) -> list[str]:
    return sorted(sql_schema.keys()) if isinstance(sql_schema, dict) else []


def _table_columns(table_schema: Dict[str, Any]) -> set[str]:
    columns = table_schema.get("column_names", [])
    return {str(column) for column in columns} if isinstance(columns, list) else set()


def _collect_query_spec_table_hints(query_spec: Dict[str, Any]) -> set[str]:
    hints: set[str] = set()
    if not isinstance(query_spec, dict):
        return hints
    for key in ("group_by", "measures", "filters"):
        items = query_spec.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source_class") or "").strip()
            if source:
                hints.add(source)
    base_table = str(query_spec.get("base_table") or "").strip()
    if base_table:
        hints.add(base_table)
    return hints


def _collect_query_spec_column_hints(query_spec: Dict[str, Any]) -> set[str]:
    hints: set[str] = set()
    if not isinstance(query_spec, dict):
        return hints
    for key in ("group_by", "measures", "filters"):
        items = query_spec.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            field = str(item.get("field") or "").strip()
            if field:
                hints.add(field.lower())
            output_name = str(item.get("output_name") or "").strip()
            if output_name:
                hints.add(output_name.lower())
    entity_key = str(query_spec.get("entity_key") or "").strip()
    if entity_key:
        hints.add(entity_key.lower())
    output_schema = query_spec.get("output_schema")
    if isinstance(output_schema, list):
        for field in output_schema:
            value = str(field or "").strip()
            if value:
                hints.add(value.lower())
    return hints


def _select_relevant_sql_schema(inputs: Dict[str, Any]) -> Tuple[Dict[str, Any], list[str]]:
    sql_schema = inputs.get("sql_schema") or inputs.get("global_schema") or {}
    if not isinstance(sql_schema, dict) or not sql_schema:
        return {}, []

    query = str(inputs.get("query", "")).lower()
    query_spec = inputs.get("query_spec", {}) if isinstance(inputs.get("query_spec", {}), dict) else {}
    spec_text = json.dumps(query_spec, ensure_ascii=False).lower()
    bound_text = json.dumps(inputs.get("bound_inputs", {}), ensure_ascii=False).lower()
    combined = f"{query} {spec_text} {bound_text}"

    relevant = []
    hinted_tables = _collect_query_spec_table_hints(query_spec)
    hinted_columns = _collect_query_spec_column_hints(query_spec)
    for table_name in hinted_tables:
        if table_name in sql_schema:
            relevant.append(table_name)

    for table_name, table_schema in sql_schema.items():
        if table_name.lower() in combined:
            relevant.append(table_name)
            continue
        for column_name in _table_columns(table_schema):
            column_lower = str(column_name).lower()
            if column_lower in combined or column_lower in hinted_columns:
                relevant.append(table_name)
                break

    relevant = sorted(dict.fromkeys(relevant))
    if not relevant:
        relevant = _schema_table_names(sql_schema)

    return {table_name: sql_schema[table_name] for table_name in relevant}, relevant


def _group_expression(group: dict[str, Any], table_alias: str) -> str | None:
    field = str(group.get("field") or "").strip()
    if not field:
        return None
    strategy = str(group.get("bucket_strategy") or "").strip()
    if not strategy:
        return f'{table_alias}."{field}"'
    boundaries = group.get("bucket_boundaries")
    labels = group.get("bucket_labels")
    if not isinstance(boundaries, list) or len(boundaries) != 2:
        return None
    if not isinstance(labels, list) or len(labels) != 3:
        return None
    low, high = boundaries
    low_label, middle_label, high_label = (_sql_literal(label) for label in labels)
    return (
        f'CASE WHEN {table_alias}."{field}" <= {float(low):g} THEN {low_label} '
        f'WHEN {table_alias}."{field}" <= {float(high):g} THEN {middle_label} '
        f'ELSE {high_label} END'
    )


def _deterministic_group_count_sql(inputs: Dict[str, Any]) -> str | None:
    """Compile only explicitly requested distinct entity counts."""
    spec = inputs.get("query_spec")
    schema = inputs.get("sql_schema") or inputs.get("global_schema") or {}
    if not isinstance(spec, dict) or not isinstance(schema, dict) or spec.get("filters") or inputs.get("bound_inputs") or spec.get("predicate_tree"):
        return None
    groups = spec.get("group_by")
    measures = spec.get("measures")
    groups = groups if isinstance(groups, list) else []
    measures = measures if isinstance(measures, list) else []
    if not groups or len(measures) != 1:
        return None
    measure = measures[0]
    if measure.get("population_filters") or measure.get("aggregate_filters") or spec.get("ranking", {}).get("required"):
        return None
    expected_output = [g.get("output_name") for g in groups if isinstance(g, dict)] + [measure.get("output_name")]
    if spec.get("output_schema") and spec["output_schema"] != expected_output:
        return None
    operation = str(
        measure.get("per_entity_operation") or measure.get("final_operation") or ""
    ).upper()
    if operation != "COUNT":
        return None
    entity_key = str(spec.get("entity_key") or "").strip()
    output_measure = str(measure.get("output_name") or "entity_count")
    driver_table = str(groups[0].get("source_class") or "")
    if (
        measure.get("field") not in {entity_key, "*"}
        or measure.get("source_class") != driver_table
        or measure.get("requires_distinct") is not True
        or str(measure.get("final_operation") or "COUNT").upper() != "COUNT"
    ):
        return None
    if not entity_key or not driver_table:
        return None
    if driver_table not in schema or entity_key not in set(schema[driver_table].get("column_names", [])):
        return None

    source_aliases = {driver_table: "g0"}
    joins = []
    select_groups = []
    group_expressions = []
    for group in groups:
        if not isinstance(group, dict):
            return None
        source = str(group.get("source_class") or "")
        field = str(group.get("field") or "")
        if source not in schema or field not in set(schema[source].get("column_names", [])):
            return None
        if entity_key not in set(schema[source].get("column_names", [])):
            return None
        if source not in source_aliases:
            alias = f"g{len(source_aliases)}"
            source_aliases[source] = alias
            join_type = "LEFT JOIN" if spec.get("join_policy") == "left_join" else "INNER JOIN"
            joins.append(
                f'{join_type} "{source}" AS {alias} '
                f'ON g0."{entity_key}" = {alias}."{entity_key}"'
            )
        alias = source_aliases[source]
        expression = _group_expression(group, alias)
        output_name = str(group.get("output_name") or field)
        if not expression:
            return None
        select_groups.append(f'{expression} AS "{output_name}"')
        group_expressions.append(expression)
    return (
        "SELECT " + ", ".join(select_groups)
        + f', COUNT(DISTINCT g0."{entity_key}") AS "{output_measure}" '
        + f'FROM "{driver_table}" AS g0 '
        + " ".join(joins)
        + " GROUP BY " + ", ".join(group_expressions)
        + ";"
    )


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _profile_filter_sql(filters: list[dict[str, Any]], profile_columns: set[str], base_table: str) -> str | None:
    clauses = []
    for item in filters:
        if not isinstance(item, dict):
            return None
        source = str(item.get("source_class") or "")
        if source and source != base_table:
            return None
        field = str(item.get("field") or "")
        if field not in profile_columns:
            return None
        operator = str(item.get("operator") or "=").strip().lower()
        value = item.get("value")
        if item.get("value_type") == "field":
            if not isinstance(value, str) or value not in profile_columns or operator not in {"=", "!=", "<>", ">", ">=", "<", "<="}:
                return None
            clauses.append(f'"{field}" {operator.upper()} "{value}"')
            continue
        if operator in {"=", "!=", "<>", ">", ">=", "<", "<="} and not isinstance(value, list):
            if value is None:
                if operator not in {'=', '!=', '<>'}:
                    return None
                clauses.append(f'"{field}" IS {"NOT " if operator != "=" else ""}NULL')
            else:
                clauses.append(f'"{field}" {operator.upper()} {_sql_literal(value)}')
        elif operator in {"in", "not_in"} and isinstance(value, list) and value:
            if None in value:
                # Do not reinterpret SQL three-valued membership semantics.
                # Leave ambiguous null-containing sets to semantic generation.
                return None
            values = ", ".join(_sql_literal(entry) for entry in value)
            keyword = "NOT IN" if operator == "not_in" else "IN"
            clauses.append(f'"{field}" {keyword} ({values})')
        elif operator in {"is_null", "is null"}:
            clauses.append(f'"{field}" IS NULL')
        elif operator in {"is_not_null", "is not null"}:
            clauses.append(f'"{field}" IS NOT NULL')
        else:
            return None
    return " AND ".join(clauses)


def _entity_measure_expression(measure: dict[str, Any], columns: set[str]) -> str | None:
    """Compile only an explicit field or safe arithmetic expression."""
    import ast
    formula = str(measure.get("formula") or "").strip()
    if not formula:
        field = str(measure.get("field") or "").strip()
        return f'"{field}"' if field in columns else None
    try:
        node = ast.parse(formula, mode="eval").body
    except SyntaxError:
        return None
    operations = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/"}

    def render(value):
        if isinstance(value, ast.Name) and value.id in columns:
            return f'"{value.id}"'
        if isinstance(value, ast.Constant) and type(value.value) in {int, float}:
            return str(value.value)
        if isinstance(value, ast.BinOp) and type(value.op) in operations:
            left, right = render(value.left), render(value.right)
            if isinstance(value.op, ast.Div) and left and right:
                return f"(1.0 * {left} / NULLIF({right}, 0))"
            return f"({left} {operations[type(value.op)]} {right})" if left and right else None
        if isinstance(value, ast.UnaryOp) and isinstance(value.op, ast.USub):
            operand = render(value.operand)
            return f"(-{operand})" if operand else None
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id.upper() == "ABS" and len(value.args) == 1:
            operand = render(value.args[0])
            return f"ABS({operand})" if operand else None
        return None

    return render(node)


def _derived_formula_sql(formula: str, aliases: list[str]) -> str | None:
    return _entity_measure_expression({"formula": formula}, set(aliases))


def _deterministic_projection_sql(inputs: Dict[str, Any]) -> str | None:
    """Compile a fully explicit single-source projection; otherwise use the LLM.

    No joins, aggregation, ranking, bound inputs, implicit output columns or
    metric reinterpretation are inferred by this fast path.
    """
    spec = inputs.get('query_spec')
    schema = inputs.get('sql_schema') or inputs.get('global_schema') or {}
    if not isinstance(spec, dict) or spec.get('query_type') != 'point_lookup':
        return None
    grain = spec.get('grain') or {}
    if (inputs.get('bound_inputs') or spec.get('predicate_tree') or spec.get('group_by')
            or grain.get('pre_aggregate_by') or grain.get('final_group_by')
            or (spec.get('ranking') or {}).get('required')
            or spec.get('join_policy') in {'anti_join', 'union_required'}):
        return None
    source = spec.get('base_entity')
    if source not in schema or any(s != source for s in spec.get('required_classes', [])):
        return None
    columns = set(schema[source].get('column_names', []))
    identifiers = [source, *columns, *spec.get('output_schema', [])]
    if not all(isinstance(s, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', s) for s in identifiers):
        return None
    predicates = spec.get('filters', [])
    if not isinstance(predicates, list):
        return None
    where = _profile_filter_sql(predicates, columns, source)
    if where is None:
        return None
    projections = {}
    for measure in spec.get('measures', []):
        if not isinstance(measure, dict) or measure.get('source_class', source) != source:
            return None
        if any(measure.get(k) for k in ['per_entity_operation', 'final_operation', 'population_filters',
                                        'aggregate_filters', 'requires_distinct']):
            return None
        if measure.get('operand_kind') == 'aliases' or measure.get('formula_stage') not in (None, 'row'):
            return None
        expression = _entity_measure_expression(measure, columns)
        name = measure.get('output_name')
        if not expression or not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
            return None
        projections[name] = expression
    outputs = spec.get('output_schema')
    if not isinstance(outputs, list) or not outputs:
        return None
    select = []
    for name in outputs:
        expression = projections.get(name) or (f'"{name}"' if name in columns else None)
        if not expression:
            return None
        select.append(f'{expression} AS "{name}"')
    # A projection containing only the declared entity identity represents an
    # entity set, including when its carrier table has several related records.
    key = spec.get('entity_key')
    distinct = bool(key in columns and all(
        (projections.get(name) or f'"{name}"') == f'"{key}"' for name in outputs))
    return 'SELECT ' + ('DISTINCT ' if distinct else '') + ', '.join(select) + f' FROM "{source}"' + (f' WHERE {where}' if where else '') + ';'


def _deterministic_single_source_aggregate_sql(inputs: Dict[str, Any]) -> str | None:
    """Compile explicit one-level aggregates without joins or grain changes."""
    spec = inputs.get('query_spec')
    schema = inputs.get('sql_schema') or inputs.get('global_schema') or {}
    if not isinstance(spec, dict) or spec.get('query_type') != 'aggregation':
        return None
    grain = spec.get('grain') or {}
    if (inputs.get('bound_inputs') or spec.get('predicate_tree') or grain.get('pre_aggregate_by')
            or spec.get('fanout_control', {}).get('required')
            or (spec.get('ranking') or {}).get('required')
            or spec.get('join_policy') in {'anti_join', 'union_required'}):
        return None
    source = spec.get('base_entity')
    if source not in schema or any(s != source for s in spec.get('required_classes', [])):
        return None
    columns = set(schema[source].get('column_names', []))
    if not all(isinstance(name, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name)
               for name in [source, *columns, *spec.get('output_schema', [])]):
        return None
    where = _profile_filter_sql(spec.get('filters', []), columns, source)
    if where is None:
        return None
    projections, grouping = {}, []
    for group in spec.get('group_by', []):
        if (not isinstance(group, dict) or group.get('source_class', source) != source
                or group.get('field') not in columns or group.get('bucket_strategy')):
            return None
        name = group.get('output_name')
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
            return None
        expression = f'"{group["field"]}"'
        projections[name] = expression
        grouping.append(expression)
    measures = spec.get('measures', [])
    if not measures:
        return None
    for measure in measures:
        if not isinstance(measure, dict) or measure.get('source_class', source) != source:
            return None
        if (measure.get('aggregate_filters') or measure.get('population_filters')
                or measure.get('operand_kind') == 'aliases'
                or measure.get('formula_stage') not in (None, 'row')
                or (measure.get('per_entity_operation') and measure.get('final_operation'))):
            return None
        operation = str(measure.get('final_operation') or measure.get('per_entity_operation') or '').upper()
        if operation not in {'COUNT', 'COUNT_DISTINCT', 'SUM', 'AVG', 'MIN', 'MAX'}:
            return None
        name = measure.get('output_name')
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
            return None
        expression = '*' if measure.get('field') == '*' and operation == 'COUNT' else _entity_measure_expression(measure, columns)
        if not expression:
            return None
        distinct = measure.get('requires_distinct') or operation == 'COUNT_DISTINCT'
        if distinct and (operation not in {'COUNT', 'COUNT_DISTINCT'} or expression == '*'):
            return None
        function = 'COUNT' if operation == 'COUNT_DISTINCT' else operation
        projections[name] = f'{function}({"DISTINCT " if distinct else ""}{expression})'
    outputs = spec.get('output_schema')
    if not isinstance(outputs, list) or not outputs or any(name not in projections for name in outputs):
        return None
    return ('SELECT ' + ', '.join(f'{projections[name]} AS "{name}"' for name in outputs)
            + f' FROM "{source}"' + (f' WHERE {where}' if where else '')
            + (' GROUP BY ' + ', '.join(grouping) if grouping else '') + ';')


def _deterministic_entity_group_sql(inputs: Dict[str, Any]) -> str | None:
    """Compile explicit entity-first aggregation over any matching SQL schema."""
    spec = inputs.get("query_spec")
    schema = inputs.get("sql_schema") or inputs.get("global_schema") or {}
    if not isinstance(spec, dict) or not isinstance(schema, dict) or inputs.get("bound_inputs") or spec.get("predicate_tree"):
        return None
    if spec.get("join_policy") not in {"left_join", "inner_join"}:
        return None
    groups = spec.get("group_by")
    measures = spec.get("measures")
    groups = groups if isinstance(groups, list) else []
    measures = measures if isinstance(measures, list) else []
    grain = spec.get("grain") if isinstance(spec.get("grain"), dict) else {}
    if len(groups) != 1 or not measures or not (spec.get("fanout_control", {}).get("required") or grain.get("pre_aggregate_by")):
        return None
    entity_key = str(spec.get("entity_key") or "").strip()
    if not entity_key or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", entity_key):
        return None
    group = groups[0]
    if not isinstance(group, dict) or group.get("bucket_strategy"):
        return None
    profile_table = str(group.get("source_class") or "")
    if str(group.get("source_class") or "") != profile_table or profile_table not in schema:
        return None
    group_field = str(group.get("field") or "").strip()
    group_alias = str(group.get("output_name") or group_field).strip()
    profile_columns = set(schema[profile_table].get("column_names", []))
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", group_alias):
        return None
    if group_field not in profile_columns or entity_key not in profile_columns:
        return None
    filters = spec.get("filters")
    filters = filters if isinstance(filters, list) else []
    where = _profile_filter_sql(filters, profile_columns, profile_table)
    if where is None:
        return None
    if spec.get("preserve_null_groups") is False:
        where = " AND ".join(filter(None, [where, f'"{group_field}" IS NOT NULL']))

    physical_measures = []
    derived_measures = []
    for measure in measures:
        if not isinstance(measure, dict):
            return None
        if str(measure.get("source_class") or "").lower() == "derived" or measure.get("operand_kind") == "aliases":
            derived_measures.append(measure)
        else:
            physical_measures.append(measure)
    if not physical_measures:
        return None

    by_source = {}
    for measure in physical_measures:
        source = str(measure.get("source_class") or "")
        if source not in schema or entity_key not in set(schema[source].get("column_names", [])):
            return None
        # Independent metrics can use different eligible rows in one table.
        population = measure.get("population_filters") or []
        if not isinstance(population, list):
            return None
        eligibility = _profile_filter_sql(population, set(schema[source].get("column_names", [])), source)
        if eligibility is None:
            return None
        aggregate = measure.get("aggregate_filters") or []
        if not isinstance(aggregate, list):
            return None
        by_source.setdefault((source, eligibility, json.dumps(aggregate, sort_keys=True)), []).append(measure)

    ctes = []
    joins = []
    grouped_selects = []
    aliases = []
    final_predicates = []
    for source_index, ((source, eligibility, _), source_measures) in enumerate(by_source.items()):
        cte_name = f"metric_source_{source_index}"
        columns = set(schema[source].get("column_names", []))
        entity_selects = []
        entity_predicates = []
        for measure in source_measures:
            alias = str(measure.get("output_name") or "").strip()
            operation = str(measure.get("per_entity_operation") or "").upper()
            final_operation = str(measure.get("final_operation") or "").upper()
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", alias) or operation not in {"SUM", "AVG", "COUNT", "MIN", "MAX"}:
                return None
            if final_operation not in {"SUM", "AVG", "COUNT", "MIN", "MAX"}:
                return None
            expression = _entity_measure_expression(measure, columns)
            if not expression:
                return None
            distinct = "DISTINCT " if operation == "COUNT" and measure.get("requires_distinct") else ""
            entity_selects.append(f'{operation}({distinct}{expression}) AS "{alias}"')
            outer_value = f'{cte_name}."{alias}"'
            if operation == "COUNT" and measure.get("missing_entity_value") == 0 and spec.get("join_policy") == "left_join":
                outer_value = f"COALESCE({outer_value}, 0)"
            grouped_selects.append(f'{final_operation}({outer_value}) AS "{alias}"')
            aliases.append(alias)
            for predicate in measure.get("aggregate_filters") or []:
                if predicate.get("field") != alias or predicate.get("stage") not in {"entity", "final_group"}:
                    return None
                if predicate["stage"] == "final_group" and predicate.get("scope", "population") != "population":
                    return None
                normalized = {**predicate, "source_class": ""}
                (entity_predicates if predicate["stage"] == "entity" else final_predicates).append(normalized)
        having = _profile_filter_sql(entity_predicates, set(aliases), "")
        if having is None:
            return None
        ctes.append(
            f'{cte_name} AS (SELECT "{entity_key}", ' + ", ".join(entity_selects)
            + f' FROM "{source}"' + (f' WHERE {eligibility}' if eligibility else '')
            + f' GROUP BY "{entity_key}"' + (f' HAVING {having}' if having else '') + ')'
        )
        join_keyword = "INNER JOIN" if spec.get("join_policy") == "inner_join" else "LEFT JOIN"
        if any(p.get("stage") == "entity" and p.get("scope", "population") == "population"
               for m in source_measures for p in m.get("aggregate_filters", [])):
            join_keyword = "INNER JOIN"
        joins.append(
            f'{join_keyword} {cte_name} ON profile_groups."{entity_key}" = {cte_name}."{entity_key}"'
        )

    profile_where = f" WHERE {where}" if where else ""
    ctes.insert(
        0,
        f'profile_groups AS (SELECT DISTINCT "{entity_key}", "{group_field}" AS "{group_alias}" '
        f'FROM "{profile_table}"{profile_where})',
    )
    grouped_cte = (
        'grouped_result AS (SELECT profile_groups."' + group_alias + f'" AS "{group_alias}", '
        + ", ".join(grouped_selects)
        + " FROM profile_groups " + " ".join(joins)
        + f' GROUP BY profile_groups."{group_alias}")'
    )
    ctes.append(grouped_cte)

    result_cte = "grouped_result"
    pending = list(derived_measures)
    while pending:
        progress = False
        for measure in list(pending):
            if measure.get("formula_stage") not in {None, "final_group"}:
                return None
            for predicate in measure.get("aggregate_filters") or []:
                if predicate.get("stage") != "final_group" or predicate.get("field") != measure.get("output_name") or predicate.get("scope", "population") != "population":
                    return None
            alias = str(measure.get("output_name") or "").strip()
            expression = _derived_formula_sql(str(measure.get("formula") or ""), aliases)
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", alias):
                return None
            if not expression:
                continue
            next_cte = f"derived_result_{len(aliases)}"
            ctes.append(f'{next_cte} AS (SELECT *, {expression} AS "{alias}" FROM {result_cte})')
            result_cte = next_cte
            aliases.append(alias)
            pending.remove(measure)
            final_predicates.extend({**p, "source_class": ""} for p in measure.get("aggregate_filters") or [])
            progress = True
        if not progress:
            return None
    output = spec.get("output_schema") or [group_alias, *aliases]
    if not isinstance(output, list) or any(name not in [group_alias, *aliases] for name in output):
        return None
    final_columns = [f'"{name}"' for name in output]
    sql = "WITH " + ",\n".join(ctes) + "\nSELECT " + ", ".join(final_columns) + f" FROM {result_cte}"
    final_where = _profile_filter_sql(final_predicates, set(aliases), "")
    if final_where is None:
        return None
    if final_where:
        sql += f" WHERE {final_where}"
    ranking = spec.get("ranking")
    ranking = ranking if isinstance(ranking, dict) else {}
    if ranking.get("required"):
        metric = str(ranking.get("metric") or "").strip()
        direction = str(ranking.get("direction") or "desc").upper()
        if metric in [group_alias, *aliases] and direction in {"ASC", "DESC"}:
            sql += f' ORDER BY "{metric}" {direction}, "{group_alias}" ASC'
            limit = ranking.get("limit")
            if isinstance(limit, int) and limit > 0:
                sql += f" LIMIT {limit}"
        else:
            return None
    return sql + ";"

def semantic_generate_sql(inputs: Dict[str, Any], client: Any, model: str) -> Dict[str, Any]:
    """
    Generates a SQL query based on the Query_Spec and user query.
    Mirrors the semantic_generate_sparql operator.
    """
    query = inputs.get("query", "")
    root_query = inputs.get("root_query", "") or query
    query_spec = inputs.get("query_spec", {})
    sql_schema = inputs.get("sql_schema") or inputs.get("global_schema", {})
    pruned_sql_schema, relevant_tables = _select_relevant_sql_schema(inputs)
    logic_feedback = inputs.get("logic_feedback", "")
    bound_inputs = inputs.get("bound_inputs", {})
    print(f"[SQL SCHEMA] Relevant tables: {relevant_tables}")

    compiled_projection = _deterministic_projection_sql(inputs) if not logic_feedback else None
    if compiled_projection:
        return {'sql': compiled_projection, 'reasoning': 'Compiled explicit single-source projections and predicates from QuerySpec.',
                'sql_schema_tables': _schema_table_names(sql_schema), 'relevant_tables': relevant_tables,
                'raw_response_preview': '', 'generation_backend': 'deterministic_projection'}
    compiled_aggregate = _deterministic_single_source_aggregate_sql(inputs) if not logic_feedback else None
    if compiled_aggregate:
        return {'sql': compiled_aggregate, 'reasoning': 'Compiled explicit single-source aggregation at the declared grain.',
                'sql_schema_tables': _schema_table_names(sql_schema), 'relevant_tables': relevant_tables,
                'raw_response_preview': '', 'generation_backend': 'deterministic_single_source_aggregate'}

    # A failed compiled query must reach the repair model instead of being
    # reproduced unchanged by the deterministic fast path.
    deterministic_entity_group = _deterministic_entity_group_sql(inputs) if not logic_feedback else None
    if deterministic_entity_group:
        return {
            "sql": deterministic_entity_group,
            "reasoning": "Compiled explicit entity and final-group operations from Query_Spec.",
            "sql_schema_tables": _schema_table_names(sql_schema),
            "relevant_tables": relevant_tables,
            "raw_response_preview": "",
        }

    deterministic_group_count = _deterministic_group_count_sql(inputs) if not logic_feedback else None
    if deterministic_group_count:
        print("[SQL GENERATE] Deterministic grouped-count compiler selected.")
        return {
            "sql": deterministic_group_count,
            "reasoning": "Compiled Query_Spec dimensions and entity count without LLM reinterpretation.",
            "sql_schema_tables": _schema_table_names(sql_schema),
            "relevant_tables": relevant_tables,
            "raw_response_preview": "",
        }


    prompt = f"""
You are the SQL Generate operator. Your task is to generate a valid SQLite SQL query to answer the user's question.

User Query: {query}
Original User Query Context: {root_query}
Query Spec: {json.dumps(query_spec, indent=2)}

SQLite Physical Schema:
{json.dumps(pruned_sql_schema or sql_schema, indent=2)}

CRITICAL SQL SCHEMA RULES:
- Use ONLY tables present in the provided SQLite Physical Schema.
- Use ONLY columns present in those tables.
- Use exact physical table names exactly as they appear in the schema.
- Use exact physical column names exactly as they appear in the schema.
- Never invent semantic table names, convenience aliases, or abstract entity names that do not physically exist.
- Never replace physical SQL names with KG-style or camelCase field names unless those exact names are present in the SQL schema.
- Generate SQLite-compatible SQL.
- Use the entity key or join keys that are actually present in the schema and required by Query Spec.
- Do not confuse KG class/property names with SQLite table/column names.
- Treat User Query and Query Spec as the local subquery scope.
- Use Original User Query Context only for shared context such as the year or the outer question wording.
- Do not add sibling conditions from the original decomposed query unless they are explicitly present in User Query or Query Spec.

Bound Upstream Inputs (Values from previous nodes):
{json.dumps(bound_inputs, indent=2)}
Use these bound inputs in WHERE clauses if provided, matching values to real physical key or dimension columns from the schema.
If Bound Upstream Inputs are non-empty, they are hard constraints from upstream nodes.
Do not recompute a broader universe when the subquery is clearly meant to refine, subtract from, or select within those upstream values.
If an upstream input is a list of entity IDs, labels, categories, or other dimension values, constrain the SQL to those values with IN/NOT IN logic where appropriate.

QUERY SPEC CONTRACT RULES:
- Treat Query Spec as the semantic contract for the SQL query, not as optional guidance.
- Return every field in query_spec["output_schema"] using the same aliases whenever possible.
- Implement every measure in query_spec["measures"].
- Respect per_entity_operation and final_operation exactly.
- If a group_by item uses bucket_strategy, build explicit CASE-based bucket labels and group by those labels rather than the raw numeric field.
- For ranking queries, order by the ranking metric in the specified direction and apply the ranking limit after aggregation.
- For ranking queries, add a deterministic secondary ORDER BY on a stable entity identity column (for example an entity key column) after the primary metric sort unless the Query Spec already requires a different stable tie-break.
- If a group_by item contains bucket_labels and bucket_boundaries, use those exact labels and thresholds. Never invent missing boundaries.
- For a derived measure with formula_stage="final_group", compute the formula from the already aggregated final-group measure aliases in an outer SELECT. Do not average the formula at raw-row or entity grain.
- MIN(alias) and MAX(alias) in a normalization expression refer to window extrema over the complete eligible entity population: use MIN(alias) OVER () and MAX(alias) OVER () before ranking/LIMIT, not a collapsing aggregate or extrema over the top results.
- For an entity-list query, project requested entity fields and prevent duplicate entities caused solely by related-record existence joins. Prefer EXISTS/semijoins or SELECT DISTINCT when only entity fields are requested; preserve child rows when requested.
- Apply population_filters only inside that measure's source aggregation. Metrics from the same table with different filters need separate CTEs. Top-level filters constrain the shared population. Do not apply a numerator-only restriction to the denominator.
- aggregate_filters apply AFTER the declared entity or final-group aggregation. An average-above threshold uses HAVING/an outer predicate on the computed average, never WHERE on each input value. With scope="population", constrain the shared eligible entity universe before computing other metrics; with scope="metric", restrict only that metric. Use operand_kind to distinguish physical columns from derived aliases; formula_stage alone never makes a physical aggregate a derived expression.
- When joining separately grouped aggregates on nullable dimensions, use SQLite null-safe IS (or an equivalent explicit null-safe condition), so a null group retains its metrics. Preserve NOT IN null semantics; add IS NULL only when the question explicitly includes missing values.
- Preserve exact source ownership and stored allowed_values. Do not replace a stored measure with a formula, add category values, or reverse signs without an explicit definition in the question or source metadata.
- Compute internal measure aliases even if they are absent from output_schema, then project only output_schema in its declared order. Apply filters on derived aliases after those aliases have been computed.
- For a grouped gap comparison whose ranking.limit is null, return every group, compute the requested gap column, and ORDER BY that gap; do not add LIMIT 1.
- If query_spec["join_policy"] is "inner_join" for a grouped comparative/aggregation query, join the base grouping table to every pre-aggregated measure CTE with JOIN/INNER JOIN on the entity key. Use this only when the Query Spec explicitly requires an intersection population (for example, "who have both" or "among those with").
- If query_spec["join_policy"] is "left_join" for a grouped comparative/aggregation query, drive the outer query from the base grouping table and LEFT JOIN each pre-aggregated measure CTE on the entity key.
- When using LEFT JOIN for grouped comparative metrics, do NOT convert the joins back to INNER JOIN just because some measures are missing for some entities. Missing measures should stay NULL so AVG/SUM operates over each metric's own population inside the group.

AGGREGATION GRAIN RULES (these decide whether the numbers are right):
- If query_spec["fanout_control"]["required"] is true, or grain.pre_aggregate_by is non-empty,
  you MUST use two-level aggregation. A single flat join is WRONG in that case: joining an entity
  table to one-to-many tables repeats each entity once per related record, so a final AVG or SUM
  is weighted by related-record counts instead of by entity.
- Two-level pattern to follow exactly:
    WITH m1 AS (
      SELECT <entity_key>, <per_entity_operation>(<field>) AS <measure_alias>
      FROM <that measure's own source table>
      GROUP BY <entity_key>
    ),
    m2 AS ( ... one CTE per source and eligible population, grouped by <entity_key> ... )
    SELECT b.<group_field> AS <group_alias>,
           <final_operation>(m1.<measure_alias>) AS <output_alias>,
           <final_operation>(m2.<measure_alias>) AS <output_alias>
    FROM <base entity table> AS b
    <JOIN TYPE FROM query_spec.join_policy> m1 ON b.<entity_key> = m1.<entity_key>
    <JOIN TYPE FROM query_spec.join_policy> m2 ON b.<entity_key> = m2.<entity_key>
    GROUP BY b.<group_field>
- Use JOIN/INNER JOIN in this pattern when join_policy is "inner_join"; use LEFT JOIN only when join_policy is "left_join".
- Build ONE CTE per measure source table. Never aggregate two different source tables in the same
  flat FROM/JOIN chain.
- Apply each measure's per_entity_operation inside its CTE and its final_operation in the outer query.
  When final_operation is AVG, the outer query must use AVG, never SUM.
- For grouped comparative queries without explicit total language, do not collapse per-entity measures
  into group totals unless Query Spec explicitly requires SUM.
- If independent_measure_population is true in Query Spec, each measure's group aggregate must be computed after LEFT JOINing its per-entity CTE to the base grouping table. Do not restrict all metrics to the intersection of measure-source tables.

NULL GROUP RULES:
- If query_spec["preserve_null_groups"] is true, keep the group whose value is NULL as its own output row.
- Do not add "WHERE <group_field> IS NOT NULL" and do not filter it out with an inner join.
- Take the grouping field from the base entity table so entities with no related records still appear.

"""
    if logic_feedback:
        prompt += f"Previous Failure Feedback:\n{logic_feedback}\nFix the query based on this feedback.\n"
        
    prompt += """
Return ONLY a JSON object with this exact structure:
{
  "sql": "SELECT ...",
  "reasoning": "Brief explanation of the SQL logic."
}
Do not include any other text.
"""
    
    request = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}]
    }
    try:
        response = client.chat.completions.create(**request)
        raw_text = response.choices[0].message.content
        result, parse_error = parse_llm_json_with_error(raw_text, {"sql": "", "reasoning": "JSON parse failed"}, "Generate_SQL")
        if "sql" not in result:
            result["sql"] = ""
        result["sql_schema_tables"] = _schema_table_names(sql_schema)
        result["relevant_tables"] = relevant_tables
        result["raw_response_preview"] = (raw_text or "")[:500]
        if parse_error:
            result["parse_error"] = parse_error
        print(f"[SQL GENERATE] Using physical tables: {relevant_tables}")
        print(f"[SQL GENERATE] Generated SQL: {result.get('sql', '')}")
        return result
    except Exception as e:
        print(f"   [!] Generate_SQL API error: {e}")
        return {"sql": "", "reasoning": str(e), "error": str(e)}


def semantic_pre_scan_validate_sql(inputs: Dict[str, Any], client: Any, model: str) -> Dict[str, Any]:
    """
    Validates the generated SQL for syntax and logical errors before execution.
    Mirrors semantic_pre_scan_validate.
    """
    sql = inputs.get("sql", "")
    query = inputs.get("query", "")
    root_query = inputs.get("root_query", "") or query
    query_spec = inputs.get("query_spec", {})
    sql_schema = inputs.get("sql_schema") or inputs.get("global_schema", {})
    schema_tables = _schema_table_names(sql_schema)
    
    if not sql:
        return {"pre_scan_validation": {"is_valid": False, "reason": "No SQL provided.", "severity": "hard_error"}}
    # Prepare against the real schema without executing the query. This catches
    # syntax, unknown aliases and illegal HAVING that a model may approve.
    db_path = inputs.get("db_path")
    if db_path and Path(db_path).is_file():
        connection = None
        try:
            connection = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)
            connection.execute("EXPLAIN " + sql).fetchall()
        except sqlite3.Error as error:
            reason = f"SQLite query preparation failed: {error}"
            return {"pre_scan_validation": {"is_valid": False, "severity": "hard_error", "reason": reason,
                    "rewrite_hint": reason + ". Regenerate valid SQL against the supplied physical schema."}}
        finally:
            if connection is not None:
                connection.close()
        
    prompt = f"""
You are the SQL Pre_Scan_Validate operator. Verify if the following SQL query is valid, safe, and logically aligns with the query.

User Query: {query}
Original User Query Context: {root_query}
SQL Query: {sql}
Query Spec: {json.dumps(query_spec, indent=2)}
SQLite Physical Schema:
{json.dumps(sql_schema, indent=2)}

Validate ONLY User Query and Query Spec as this node's executable scope.
Original User Query Context describes the whole DAG, not additional predicates
for this node. Do not reject a subquery for omitting sibling conditions or the
final aggregation/ranking assigned to a downstream node. Upstream bound values
must still constrain this node when supplied. Never broaden its local population.

Check for:
1. Syntax errors
2. Missing or incorrect table/column names based on the provided SQLite Physical Schema
3. Dangerous cartesian products
4. Semantic/KG table or column names that do not physically exist in SQLite
5. Query Spec contract violations:
   - missing output_schema aliases
   - grouped comparative queries that skip the requested final grouping
   - ranking queries missing ORDER BY/LIMIT for the requested metric
   - pre_aggregate_by queries that appear to use one flat multi-table aggregation instead of staged aggregation
   - aggregate_filters incorrectly implemented on input rows rather than on computed entity/final-group aliases
   - population-scope aggregate predicates that fail to constrain other requested metrics to the same eligible entities
   - grouped aggregate joins using ordinary equality on nullable dimension keys and losing null-group metrics
   - NOT IN predicates broadened to include NULL without an explicit missing-value condition in the question

Reject any SQL that uses tables outside this exact list:
{schema_tables}

Return ONLY a JSON object:
{{
  "is_valid": true/false,
  "reason": "Explanation of any issues found, or 'Valid' if none.",
  "severity": "hard_error" | "repairable_warning" | "valid",
  "rewrite_hint": "Instructions for the Generate operator on how to fix it (if invalid)"
}}
"""
    request = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}]
    }
    try:
        response = client.chat.completions.create(**request)
        raw_text = response.choices[0].message.content
        result = parse_llm_json(raw_text, {"is_valid": False, "reason": "JSON parse error", "severity": "hard_error"}, "Pre_Scan_Validate_SQL")
        if "is_valid" not in result:
             result["is_valid"] = False
        return {"pre_scan_validation": result}
    except Exception as e:
        return {"pre_scan_validation": {"is_valid": False, "reason": str(e), "severity": "hard_error"}}


def pre_programmed_scan_sql(inputs: Dict[str, Any], db_path: str) -> Dict[str, Any]:
    sql = inputs.get("sql", "")

    if not sql.strip():
        return {
            "status": "error",
            "error_type": "empty_sql",
            "error_message": "Empty SQL query",
            "data": []
        }
    if not db_path or db_path == ":memory:":
        return {
            "status": "error",
            "error_type": "db_path_error",
            "error_message": f"Invalid SQLite database path for SQL pipeline: {db_path!r}",
            "data": []
        }
    if not os.path.exists(db_path):
        return {
            "status": "error",
            "error_type": "db_path_error",
            "error_message": f"SQLite database file does not exist: {db_path}",
            "data": []
        }

    conn = None

    try:
        conn = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)
        conn.execute("PRAGMA query_only=ON")
    except sqlite3.Error as e:
        return {
            "status": "error",
            "error_type": "db_connection_error",
            "error_message": f"SQLite DB connection error: {e}",
            "data": []
        }

    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(sql)
        rows = cursor.fetchall()
        data = [dict(row) for row in rows]

        return {
            "status": "success",
            "error_type": "",
            "row_count": len(data),
            "data": data,
            "error_message": ""
        }

    except sqlite3.OperationalError as e:
        message = str(e)
        if "no such table" in message.lower():
            error_type = "sql_no_such_table"
        elif "no such column" in message.lower():
            error_type = "sql_no_such_column"
        else:
            error_type = "sql_execution_error"
        return {
            "status": "error",
            "error_type": error_type,
            "error_message": f"SQLite SQL execution error: {e}",
            "data": []
        }

    except sqlite3.Error as e:
        return {
            "status": "error",
            "error_type": "sql_execution_error",
            "error_message": f"SQLite SQL execution error: {e}",
            "data": []
        }

    except Exception as e:
        return {
            "status": "error",
            "error_type": "unexpected_sql_scan_error",
            "error_message": f"{type(e).__name__}: {e}",
            "data": []
        }

    finally:
        if conn is not None:
            conn.close()
