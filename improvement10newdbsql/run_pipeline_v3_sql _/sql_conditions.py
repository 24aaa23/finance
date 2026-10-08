"""Canonical condition syntax shared by SQL planning, checks and rendering."""

from datetime import date, datetime
import re


def normalize_condition(predicate):
    """Normalize syntax without changing literals, populations or boundaries.

    Only explicit IS/IS NOT NULL syntax interprets the string NULL as missing.
    Equality to a literal string named NULL remains an ordinary comparison.
    Legacy BETWEEN strings are accepted only for unambiguous ISO date pairs.
    """
    if not isinstance(predicate, dict):
        return predicate
    result = dict(predicate)
    # Accept explicit logical operator/value spelling without guessing any
    # field, value, boundary or population. Only object children are groups.
    logical = str(result.get('operator', '')).strip().lower()
    target = {'and': 'all', 'all': 'all', 'or': 'any', 'any': 'any', 'not': 'not'}.get(logical)
    children = result.get('value', result.get('conditions'))
    valid_children = isinstance(children, dict) if target == 'not' else (
        isinstance(children, list) and bool(children) and all(isinstance(child, dict) for child in children))
    if target and valid_children and not any(key in result for key in ('all', 'any', 'not')):
        result[target] = children
        for key in ('operator', 'value', 'conditions', 'field', 'value_type'):
            result.pop(key, None)
    for key in ("all", "any", "conditions", "filters"):
        if isinstance(result.get(key), list):
            result[key] = [normalize_condition(child) for child in result[key]]
    if isinstance(result.get("not"), dict):
        result["not"] = normalize_condition(result["not"])
    if "field" not in result:
        return result
    operator = " ".join(str(result.get("operator", "=")).strip().lower().replace("_", " ").split())
    operator = {"isnull": "is null", "isnotnull": "is not null", "not null": "is not null"}.get(operator, operator)
    value = result.get("value")
    if operator in {"is", "is not"} and "value" in result and (
        value is None or (isinstance(value, str) and value.strip().upper() == "NULL"
                          and str(result.get("value_type", "")).lower() not in {"string", "text"})
    ):
        operator += " null"
    if operator in {"is null", "is not null"}:
        result.update(operator=operator.replace(" ", "_"), value=None, value_type="null")
    elif operator == "between" and isinstance(value, str):
        endpoint = r"(?:'(?P<{0}q>\d{{4}}-\d{{2}}-\d{{2}})'|(?P<{0}u>\d{{4}}-\d{{2}}-\d{{2}}))"
        match = re.fullmatch(r"\s*" + endpoint.format("a") + r"(?:\s+AND\s+|\s*\|\s*)" + endpoint.format("b") + r"\s*", value, re.IGNORECASE)
        if match:
            endpoints = [match.group("aq") or match.group("au"), match.group("bq") or match.group("bu")]
            try:
                for item in endpoints:
                    date.fromisoformat(item)
            except ValueError:
                pass
            else:
                result.update(operator="between", value=endpoints)
    return result


def raw_condition_errors(predicate):
    """Reject unsupported raw requirements at Decompose, where they originate.

    Do not silently turn LIKE into contains or guess a range from a pattern.
    The existing Decompose retry must express the question using the same
    supported operators that Query_Spec and the raw renderer can execute.
    """
    predicate = normalize_condition(predicate)
    if not isinstance(predicate, dict):
        return ["Raw condition must be an object."]
    for key in ("all", "any", "not", "conditions", "filters"):
        if key not in predicate:
            continue
        children = [predicate[key]] if key == "not" else predicate[key]
        if not isinstance(children, list) or not children:
            return ["Logical raw conditions require nonempty predicate lists."]
        errors = [error for child in children for error in raw_condition_errors(child)]
        if key in {"conditions", "filters"} and str(predicate.get("logic", "and")).lower() not in {"and", "or"}:
            errors.append("Logical raw conditions support only AND/OR.")
        return errors
    operator = " ".join(str(predicate.get("operator", "=")).strip().lower().replace("_", " ").split())
    allowed = {"=", "==", "eq", "equals", "!=", "ne", "<>", "<", "<=", ">", ">=",
               "between", "in", "not in", "contains", "is null", "is not null"}
    if operator not in allowed:
        return [f"Unsupported raw condition operator: {operator}. Use supported raw operators without changing the requested condition."]
    value = predicate.get("value")
    if value is None and operator not in {'is null', 'is not null'}:
        return ['NULL comparisons are UNKNOWN, not presence checks. Use is_null/is_not_null for missing/present values.']
    if operator == "between" and (not isinstance(value, list) or len(value) != 2):
        return ["BETWEEN requires a two-element value array [lower, upper]."]
    if operator in {"in", "not in"} and not isinstance(value, list):
        return ["IN/NOT IN requires a literal value array."]
    if operator not in {"between", "in", "not in", "is null", "is not null"} and isinstance(value, (dict, list)):
        return ["Raw comparison requires a scalar literal. For a comparison between fields, retain both raw operands and move the predicate to stage=final for local calculation."]
    if isinstance(value, str) and re.search(r'^\s*\(?\s*(?:select\b|(?:dateadd|date_diff|datediff)\s*\()', value, re.I):
        return ["Raw filter values cannot contain SQL subqueries or calculation expressions. Retrieve their operands and calculate the boundary at stage=final; never quote SQL as a literal."]
    return date_literal_errors(predicate)


def date_literal_errors(predicate, declared_type=''):
    """Validate typed dates only; never resolve relative-date placeholders."""
    if not isinstance(predicate, dict):
        return []
    operator = str(predicate.get('operator', '=')).lower().replace('_', ' ')
    if operator in {'is null', 'is not null'}:
        return []
    kind = str(predicate.get('value_type', '')).lower()
    declared = str(declared_type).lower()
    if kind not in {'date', 'datetime', 'timestamp'}:
        kind = declared
    if kind not in {'date', 'datetime', 'timestamp'}:
        return []
    value = predicate.get('value')
    values = value if isinstance(value, list) else [value]
    errors = []
    for item in values:
        if item is None:
            continue  # NULL operators/membership semantics checked separately.
        try:
            if not isinstance(item, str):
                raise ValueError('not a string')
            if kind == 'date':
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', item):
                    raise ValueError('not ISO date')
                date.fromisoformat(item)
            else:
                datetime.fromisoformat(item.replace('Z', '+00:00'))
        except ValueError:
            errors.append(f"Invalid {kind} literal for {predicate.get('field')}: {item!r}. Use an actual ISO date/datetime; retrieve operands and calculate relative/latest boundaries in final steps. Do not quote SQL, CURRENT_DATE or placeholders.")
    return errors


def condition_tree(predicate, field_name=lambda value: value):
    """Canonical, order-independent logical tree; OR is never flattened to AND."""
    import json
    item = normalize_condition(predicate)
    for key in ('all', 'any', 'conditions', 'filters'):
        if key in item:
            logic = 'or' if key == 'any' else str(item.get('logic', 'and')).lower() if key in {'conditions', 'filters'} else 'and'
            children = []
            for child in item[key]:
                tree = condition_tree(child, field_name)
                children.extend(tree[1] if tree[0] == logic else [tree])
            unique = sorted(set(children), key=repr)
            return unique[0] if len(unique) == 1 else (logic, tuple(unique))
    if 'not' in item:
        return ('not', condition_tree(item['not'], field_name))
    op = str(item.get('operator', '=')).lower().replace('_', ' ')
    op = {'==': '=', 'eq': '=', 'equals': '=', '<>': '!=', 'ne': '!='}.get(op, op)
    value = item.get('value')
    if value is None:
        op = {'=': 'is null', '!=': 'is not null'}.get(op, op)
    if op in {'is null', 'is not null'}:
        value = None
    if (isinstance(value, (int, float)) and not isinstance(value, bool)) or str(item.get('value_type', '')).lower() in {'number', 'numeric'}:
        from decimal import Decimal, InvalidOperation
        try:
            numeric = Decimal(str(value))
            encoded = 'number:' + str(numeric.normalize()) if numeric.is_finite() else json.dumps(value)
        except (InvalidOperation, ValueError):
            encoded = json.dumps(value, sort_keys=True)
    else:
        encoded = json.dumps(value, sort_keys=True)
    return ('atom', field_name(item.get('field')), op, encoded)


def condition_leaves(predicate):
    if not isinstance(predicate, dict):
        return
    if predicate.get('field'):
        yield predicate
    for key in ('all', 'any', 'conditions', 'filters'):
        for child in predicate.get(key, []):
            yield from condition_leaves(child)
    if isinstance(predicate.get('not'), dict):
        yield from condition_leaves(predicate['not'])


def contradictory_conditions(predicates):
    """Flag impossible same-field AND scopes for planner repair, without rewriting."""
    tree = condition_tree({'all': predicates}) if predicates else ('and', ())
    def inspect(node):
        errors = []
        if node[0] == 'and':
            atoms = [child for child in node[1] if child[0] == 'atom']
            for atom in atoms:
                if atom[2] == 'is null' and any(other[1] == atom[1] and
                        (other[2] == 'is not null' or (other[2] == '=' and other[3] != 'null')) for other in atoms):
                    errors.append(f"Contradictory AND conditions on {atom[1]}: a value/presence condition and IS NULL cannot both hold. Preserve the source's logical grouping using any/all/not; do not flatten OR alternatives into mandatory predicates.")
        if node[0] in {'and', 'or'}:
            for child in node[1]:
                errors.extend(inspect(child))
        return errors
    return inspect(tree)
