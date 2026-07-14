import re
import json
from typing import Dict, Any, List

def pre_programmed_math_compute(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Operator: Math Compute
    Purpose: Performs standard financial calculations (sum, average, percentage_diff)
             on extracted DataFrames without needing backend SQL/SPARQL aggregations.
    """
    df = pd.DataFrame(inputs.get("data", []))
    if df.empty:
        return {"computed_value": None, "error": "Empty dataset provided."}

    operation = inputs.get("operation", "").lower()
    col = inputs.get("target_column")

    try:
        #Force the SPARQL string outputs into numeric values
        df[col] = pd.to_numeric(df[col], errors='coerce')

        if operation == "sum":
            result = df[col].sum()
        elif operation == "avg":
            result = df[col].mean()
        elif operation == "percentage_diff" and 'base_col' in inputs:
            base_col = inputs.get('base_col')
            df[base_col] = pd.to_numeric(df[base_col], errors='coerce')
            df['pct_diff'] = ((df[col] - df[base_col]) / df[base_col]) * 100
            result = df.to_dict(orient='records')
        else:
            result = "Unsupported mathematical operation."

        return {"computed_result": result}
    except KeyError:
        return {"error": f"Column {col} not found in data."}

def pre_programmed_set_intersect(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Operator: Set (Intersection)
    Purpose: Intersects two lists of data (e.g., finding investor_ids that appear in both lists).
    Expected inputs: 'list_a' (list of dicts), 'list_b' (list of dicts), 'join_key' (str).
    """
    list_a = inputs.get("list_a", [])
    list_b = inputs.get("list_b", [])
    join_key = inputs.get("join_key", "investor_id")

    # Extract keys
    keys_a = {item[join_key] for item in list_a if join_key in item}
    keys_b = {item[join_key] for item in list_b if join_key in item}

    # Intersect
    intersected_keys = keys_a.intersection(keys_b)

    # Filter original items based on intersection
    result = [item for item in list_a if item.get(join_key) in intersected_keys]

    return {"intersected_data": result, "count": len(result)}

def pre_programmed_union(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Operator: Set Union
    Purpose: Combines two data arrays and drops exact duplicates.
    Expected inputs: 'list_a' (list of dicts), 'list_b' (list of dicts)
    """
    df_a = pd.DataFrame(inputs.get("list_a", []))
    df_b = pd.DataFrame(inputs.get("list_b", []))

    # Concat and drop exact duplicates
    df_union = pd.concat([df_a, df_b]).drop_duplicates().reset_index(drop=True)
    return {"union_data": df_union.to_dict(orient='records'), "count": len(df_union)}

def pre_programmed_difference(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Operator: Set Difference
    Purpose: Finds records in List A that are NOT in List B based on a specific key.
    Expected inputs: 'list_a', 'list_b', 'join_key' (e.g., 'investor_id')
    """
    list_a = inputs.get("list_a", [])
    list_b = inputs.get("list_b", [])
    join_key = inputs.get("join_key", "investor_id")

    keys_b = {item[join_key] for item in list_b if join_key in item}

    # Keep items in A where the key is NOT in B
    result = [item for item in list_a if item.get(join_key) not in keys_b]
    return {"difference_data": result, "count": len(result)}

