"""Deterministic numeric bucketing operator for declared Processing_Spec steps."""

from ..common import Any, Dict, pd
from ..spec_contracts import boolean_flag
import math


def pre_programmed_bucket(inputs: Dict[str, Any]) -> Dict[str, Any]:
    data = inputs.get("data", [])
    source = inputs.get("input_column") or inputs.get("target_column")
    output = inputs.get("output_column")
    rules = inputs.get("rules", [])
    if not isinstance(data, list) or not isinstance(source, str) or not isinstance(output, str):
        return {"data": [], "operator_result": [], "error": "Bucket requires data, input_column, and output_column."}
    if not isinstance(rules, list) or not rules:
        return {"data": [], "operator_result": [], "error": "Bucket requires one or more declared rules."}
    df = pd.DataFrame(data)
    if df.empty and inputs.get("input_schema"):
        df = pd.DataFrame(columns=inputs["input_schema"])
    if source not in df.columns:
        return {"data": [], "operator_result": [], "error": f"Bucket input column does not exist: {source}"}

    numeric = pd.to_numeric(df[source], errors="coerce")
    if (df[source].notna() & numeric.isna()).any():
        return {"data": [], "error": f"Bucket contains nonnumeric values in: {source}"}
    labels = pd.Series([None] * len(df), index=df.index, dtype="object")
    assigned = pd.Series(False, index=df.index)
    for rule in rules:
        if not isinstance(rule, dict) or "label" not in rule:
            return {"data": [], "operator_result": [], "error": "Every Bucket rule requires a label."}
        lower, upper = rule.get("min"), rule.get("max")
        try:
            lower = float(lower) if lower is not None else None
            upper = float(upper) if upper is not None else None
            if any(v is not None and not math.isfinite(v) for v in (lower, upper)) or (lower is not None and upper is not None and lower > upper):
                raise ValueError("Invalid bounds")
            min_inclusive = boolean_flag(rule.get("min_inclusive", True), "min_inclusive")
            max_inclusive = boolean_flag(rule.get("max_inclusive", True), "max_inclusive")
        except (TypeError, ValueError):
            return {"data": [], "operator_result": [], "error": "Bucket bounds must be numeric or null."}
        mask = numeric.notna()
        if lower is not None:
            mask &= numeric.ge(lower) if min_inclusive else numeric.gt(lower)
        if upper is not None:
            mask &= numeric.le(upper) if max_inclusive else numeric.lt(upper)
        matched = mask & ~assigned
        labels.loc[matched] = rule["label"]
        assigned |= matched
    if "default" in inputs:
        labels.loc[~assigned] = inputs["default"]
    df[output] = labels
    rows = df.where(pd.notna(df), None).to_dict(orient="records")
    return {"data": rows, "operator_result": rows, "row_count": len(rows)}
