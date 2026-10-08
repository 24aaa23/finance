"""Deterministic date-part extraction for spec execution."""

from ..common import Any, Dict, pd

DATE_PARTS = {'year', 'month', 'day', 'quarter', 'quarter_start', 'month_start',
              'year_num', 'month_num', 'day_num', 'fiscal_year', 'fiscal_quarter'}


def pre_programmed_date_extract(inputs: Dict[str, Any]) -> Dict[str, Any]:
    data = inputs.get("data", [])
    if not isinstance(data, list):
        return {"data": [], "error": "Date_Extract requires row data."}
    df = pd.DataFrame(data)
    if df.empty and inputs.get("input_schema"):
        df = pd.DataFrame(columns=inputs["input_schema"])
    source = str(inputs.get("input_column") or inputs.get("target_column") or "")
    part = str(inputs.get("part") or "").lower()
    output = str(inputs.get("output_column") or part or "date_part")
    if not source or source not in df.columns:
        return {"data": [], "error": f"Date_Extract source field does not exist: {source}"}
    if part not in DATE_PARTS:
        return {"data": [], "error": f"Unsupported date part: {part}"}
    values = pd.to_datetime(df[source], errors="coerce", utc=True, format="mixed")
    if (df[source].notna() & values.isna()).any():
        return {"data": [], "error": f"Date_Extract contains invalid dates in: {source}"}
    if part == "year":
        df[output] = values.dt.strftime("%Y")
    elif part == "month":
        df[output] = values.dt.strftime("%Y-%m")
    elif part == 'day':
        df[output] = values.dt.strftime("%Y-%m-%d")
    elif part in {'year_num', 'month_num', 'day_num'}:
        df[output] = getattr(values.dt, part.split('_')[0]).astype('Int64')
    elif part == 'quarter':
        df[output] = values.dt.strftime('%Y') + '-Q' + values.dt.quarter.astype('Int64').astype('string')
    elif part in {'quarter_start', 'month_start'}:
        months = values.dt.month if part == 'month_start' else ((values.dt.month - 1) // 3) * 3 + 1
        dates = pd.to_datetime(pd.DataFrame({'year': values.dt.year, 'month': months, 'day': 1}), errors='coerce')
        df[output] = dates.dt.strftime('%Y-%m-%d')
    else:
        start = inputs.get('fiscal_start_month', 1)
        if isinstance(start, bool) or not isinstance(start, int) or not 1 <= start <= 12:
            return {'data': [], 'error': 'fiscal_start_month must be an integer from 1 to 12.'}
        start_year = values.dt.year - (values.dt.month < start).astype(int)
        df[output] = start_year.astype('Int64') if part == 'fiscal_year' else (((values.dt.month - start) % 12) // 3 + 1).astype('Int64')
    df[output] = df[output].astype(object).where(values.notna(), None)
    rows = df.where(pd.notna(df), None).to_dict(orient="records")
    return {"data": rows, "row_count": len(rows)}
