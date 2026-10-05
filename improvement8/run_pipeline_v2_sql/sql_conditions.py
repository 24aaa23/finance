"""Canonical condition syntax shared by SQL planning, checks and rendering."""

from datetime import date
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
    if operator == "between" and (not isinstance(value, list) or len(value) != 2):
        return ["BETWEEN requires a two-element value array [lower, upper]."]
    if operator in {"in", "not in"} and not isinstance(value, list):
        return ["IN/NOT IN requires a literal value array."]
    return []
