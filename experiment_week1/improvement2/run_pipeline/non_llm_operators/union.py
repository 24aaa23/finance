"""Union operator."""

from ..common import Any, Dict, pd


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
    rows = df_union.to_dict(orient='records')
    return {"data": rows, "union_data": rows, "count": len(df_union)}
