from typing import Any

import pandas as pd


def pre_programmed_math_compute(inputs: dict[str, Any]) -> dict[str, Any]:
    df = pd.DataFrame(inputs.get("data", []))
    if df.empty:
        return {"computed_value": None, "error": "Empty dataset provided."}

    operation = inputs.get("operation", "").lower()
    column = inputs.get("target_column")
    try:
        df[column] = pd.to_numeric(df[column], errors="coerce")
        if operation == "sum":
            result = df[column].sum()
        elif operation == "avg":
            result = df[column].mean()
        elif operation == "percentage_diff" and "base_col" in inputs:
            base_col = inputs.get("base_col")
            df[base_col] = pd.to_numeric(df[base_col], errors="coerce")
            df["pct_diff"] = ((df[column] - df[base_col]) / df[base_col]) * 100
            result = df.to_dict(orient="records")
        else:
            result = "Unsupported mathematical operation."
        return {"computed_result": result}
    except KeyError:
        return {"error": f"Column {column} not found in data."}


def pre_programmed_set_intersect(inputs: dict[str, Any]) -> dict[str, Any]:
    list_a = inputs.get("list_a", [])
    list_b = inputs.get("list_b", [])
    join_key = inputs.get("join_key", "investor_id")
    keys_a = {item[join_key] for item in list_a if join_key in item}
    keys_b = {item[join_key] for item in list_b if join_key in item}
    intersected_keys = keys_a.intersection(keys_b)
    result = [item for item in list_a if item.get(join_key) in intersected_keys]
    return {"intersected_data": result, "count": len(result)}


def pre_programmed_union(inputs: dict[str, Any]) -> dict[str, Any]:
    df_a = pd.DataFrame(inputs.get("list_a", []))
    df_b = pd.DataFrame(inputs.get("list_b", []))
    df_union = pd.concat([df_a, df_b]).drop_duplicates().reset_index(drop=True)
    return {"union_data": df_union.to_dict(orient="records"), "count": len(df_union)}


def pre_programmed_difference(inputs: dict[str, Any]) -> dict[str, Any]:
    list_a = inputs.get("list_a", [])
    list_b = inputs.get("list_b", [])
    join_key = inputs.get("join_key", "investor_id")
    keys_b = {item[join_key] for item in list_b if join_key in item}
    result = [item for item in list_a if item.get(join_key) not in keys_b]
    return {"difference_data": result, "count": len(result)}
