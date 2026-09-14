"""Math compute operator."""

import re
from ..common import Any, Dict, pd


def _canonical_key(name: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name).lower())


def _find_column(df: pd.DataFrame, col_name: Any) -> Any:
    if not isinstance(col_name, str) or not col_name or df.empty:
        return None
    if col_name in df.columns:
        return col_name
    canon = _canonical_key(col_name)
    for col in df.columns:
        if _canonical_key(col) == canon:
            return col
    for col in df.columns:
        col_canon = _canonical_key(col)
        if canon in col_canon or col_canon in canon:
            return col
    return None


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
    strict_spec = bool(inputs.get("strict_spec"))
    raw_target = inputs.get("target_column") or inputs.get("column") or inputs.get("target_columns")
    raw_left = inputs.get("left_column") or inputs.get("base_col")
    raw_right = inputs.get("right_column") or raw_target

    target_column = _find_column(df, raw_target)
    left_column = _find_column(df, raw_left)
    right_column = _find_column(df, raw_right)

    numeric_cols = [
        c for c in df.columns
        if pd.to_numeric(df[c], errors="coerce").notna().any() and not str(c).lower().endswith("id")
    ]
    if not strict_spec and not target_column and len(numeric_cols) == 1:
        target_column = numeric_cols[0]
    if not strict_spec and (not left_column or not right_column) and len(numeric_cols) >= 2:
        if not left_column:
            left_column = numeric_cols[0]
        if not right_column:
            right_column = numeric_cols[1]

    output_column = inputs.get("output_column") or {
        "difference": "difference",
        "absolute_gap": "absolute_gap",
        "ratio": "ratio",
        "percentage_diff": "percentage_diff",
        "percentage_change": "percentage_change",
    }.get(operation, f"{operation}_{target_column}" if target_column else "computed_value")

    try:
        if operation in {"sum", "avg", "average", "count", "min", "max"}:
            targets = []
            if isinstance(raw_target, list):
                targets = [_find_column(df, c) for c in raw_target if _find_column(df, c)]
            elif target_column:
                targets = [target_column]
            elif numeric_cols and not strict_spec:
                targets = numeric_cols

            if not targets:
                return {"data": [], "computed_result": None, "error": f"No numeric column found for {operation}."}

            row = {}
            for col in targets:
                values = _numeric(df[col])
                if operation == "sum":
                    val = values.sum()
                elif operation in {"avg", "average"}:
                    val = values.mean()
                elif operation == "min":
                    val = values.min()
                elif operation == "max":
                    val = values.max()
                elif operation == "count":
                    val = values.count()
                out_col = f"{operation}_{col}" if len(targets) > 1 else output_column
                row[out_col] = None if pd.isna(val) else val

            return {"data": [row], "computed_result": row, "row_count": 1}

        if not left_column or not right_column or left_column not in df.columns or right_column not in df.columns:
            return {
                "data": [],
                "computed_result": None,
                "error": f"Columns {raw_left} and/or {raw_right} not found in data.",
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
