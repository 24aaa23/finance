"""Math compute operator."""

from ..common import Any, Dict, pd


def _numeric(series):
    return pd.to_numeric(series, errors="coerce")


def pre_programmed_math_compute(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Operator: Math_Compute
    Performs arithmetic after Scan instead of pushing formulas into SPARQL.

    Supported operations:
    sum, avg, count, min, max, difference, absolute_gap, ratio,
    percentage_diff, percentage_change
    """
    df = pd.DataFrame(inputs.get("data", []))
    if df.empty:
        return {"data": [], "computed_result": None, "error": "Empty dataset provided."}

    operation = str(inputs.get("operation", "")).lower()
    target_column = inputs.get("target_column") or inputs.get("column")
    left_column = inputs.get("left_column") or inputs.get("base_col")
    right_column = inputs.get("right_column") or target_column
    output_column = inputs.get("output_column") or {
        "difference": "difference",
        "absolute_gap": "absolute_gap",
        "ratio": "ratio",
        "percentage_diff": "percentage_diff",
        "percentage_change": "percentage_change",
    }.get(operation, f"{operation}_{target_column}" if target_column else "computed_value")

    try:
        if operation in {"sum", "avg", "average", "count", "min", "max"}:
            if operation == "count":
                result_value = len(df) if not target_column else df[target_column].count()
            else:
                if not target_column or target_column not in df.columns:
                    return {"data": [], "computed_result": None, "error": f"Column {target_column} not found in data."}
                values = _numeric(df[target_column])
                if operation == "sum":
                    result_value = values.sum()
                elif operation in {"avg", "average"}:
                    result_value = values.mean()
                elif operation == "min":
                    result_value = values.min()
                else:
                    result_value = values.max()
            row = {output_column: None if pd.isna(result_value) else result_value}
            return {"data": [row], "computed_result": row}

        if left_column not in df.columns or right_column not in df.columns:
            return {
                "data": [],
                "computed_result": None,
                "error": f"Columns {left_column} and/or {right_column} not found in data.",
            }

        left = _numeric(df[left_column])
        right = _numeric(df[right_column])

        if operation == "difference":
            df[output_column] = left - right
        elif operation == "absolute_gap":
            df[output_column] = (left - right).abs()
        elif operation == "ratio":
            df[output_column] = left / right.replace({0: pd.NA})
        elif operation in {"percentage_diff", "percentage_change"}:
            df[output_column] = ((right - left) / left.replace({0: pd.NA})) * 100
        else:
            return {"data": df.to_dict(orient="records"), "computed_result": "Unsupported mathematical operation."}

        rows = df.where(pd.notna(df), None).to_dict(orient="records")
        return {"data": rows, "computed_result": rows, "row_count": len(rows)}
    except Exception as exc:
        return {"data": [], "computed_result": None, "error": str(exc)}
