"""Deterministic date-part extraction for spec execution."""

from ..common import Any, Dict, pd


def pre_programmed_date_extract(inputs: Dict[str, Any]) -> Dict[str, Any]:
    data = inputs.get("data", [])
    if not isinstance(data, list):
        return {"data": [], "error": "Date_Extract requires row data."}
    df = pd.DataFrame(data)
    source = str(inputs.get("input_column") or inputs.get("target_column") or "")
    part = str(inputs.get("part") or "").lower()
    output = str(inputs.get("output_column") or part or "date_part")
    if not source or source not in df.columns:
        return {"data": [], "error": f"Date_Extract source field does not exist: {source}"}
    if part not in {"year", "month", "day"}:
        return {"data": [], "error": f"Unsupported date part: {part}"}
    values = pd.to_datetime(df[source], errors="coerce", utc=False)
    if part == "year":
        df[output] = values.dt.strftime("%Y")
    elif part == "month":
        df[output] = values.dt.strftime("%Y-%m")
    else:
        df[output] = values.dt.strftime("%Y-%m-%d")
    rows = df.where(pd.notna(df), None).to_dict(orient="records")
    return {"data": rows, "row_count": len(rows)}
