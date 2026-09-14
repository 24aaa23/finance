"""Math compute operator."""

from ..common import Any, Dict, pd


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
