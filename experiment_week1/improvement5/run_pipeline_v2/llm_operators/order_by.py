"""Stable, deterministic sorting of explicit column specifications."""

import re
from typing import Any, Dict

import pandas as pd


def _sort_terms(inputs: dict) -> list[dict]:
    value = inputs.get("order_by") or inputs.get("column") or inputs.get("target_column")
    if value is None and inputs.get("limit") is not None:
        return []
    if isinstance(value, str):
        value = value.split(",")
    elif isinstance(value, dict):
        value = [value]
    if not isinstance(value, list) or not value:
        raise ValueError("Order_By requires at least one sort column.")
    terms = []
    for item in value:
        if isinstance(item, str):
            match = re.fullmatch(r"(.+?)\s+(ASC|DESC)", item.strip(), flags=re.I)
            item = {"column": match.group(1), "direction": match.group(2)} if match else {"column": item.strip()}
        if not isinstance(item, dict):
            raise ValueError("Each order_by item must be a column string or an object.")
        column = item.get("column") or item.get("field") or item.get("target_column")
        if not isinstance(column, str) or not column:
            raise ValueError("Each sort item requires a column name.")
        direction = str(item.get("direction") or item.get("order") or inputs.get("direction") or "ASC").upper()
        if direction not in {"ASC", "DESC"}:
            raise ValueError(f"Invalid sort direction for {column}: {direction}")
        nulls = str(item.get("nulls") or inputs.get("nulls") or "last").lower()
        if nulls not in {"first", "last"}:
            raise ValueError("Sort nulls must be 'first' or 'last'.")
        terms.append({"column": column, "direction": direction, "nulls": nulls})
    return terms


def semantic_order_by(inputs: Dict[str, Any], client: Any = None, model: str | None = None) -> Dict[str, Any]:
    """Sort by a string, dict, or list of {column, direction, nulls} terms.

    Ties retain their input order; no extra tie-breaking field is invented.
    Numeric strings sort numerically when every bound value is numeric.
    An optional limit must be a nonnegative integer. Invalid specifications fail.
    """
    if "data" in inputs:
        try:
            terms = _sort_terms(inputs)
            limit = inputs.get("limit")
            if limit is not None:
                if isinstance(limit, bool) or not re.fullmatch(r"\d+", str(limit).strip()):
                    raise ValueError("Order_By limit must be a nonnegative integer.")
                limit = int(limit)
            df = pd.DataFrame(inputs.get("data", []))
            if df.empty and inputs.get("input_schema"):
                df = pd.DataFrame(columns=inputs["input_schema"])
            strict = bool(inputs.get("strict_spec"))
            for term in terms:
                column = term["column"]
                if column not in df.columns and not strict:
                    canonical = re.sub(r"[^a-z0-9]+", "", column.lower())
                    matches = [c for c in df.columns if re.sub(r"[^a-z0-9]+", "", str(c).lower()) == canonical]
                    if len(matches) == 1:
                        column = matches[0]
                        term["column"] = column
                if column not in df.columns and (not df.empty or len(df.columns)):
                    raise ValueError(f"Sort column does not exist: {term['column']}")
            if df.empty:
                return {"data": [], "operator_result": [], "row_count": 0}
            # Repeated stable sorts implement lexicographic ordering, with each
            # key's own null placement, while preserving source values and fields.
            for term in reversed(terms):
                column = term["column"]

                def sort_key(series):
                    numeric = pd.to_numeric(series, errors="coerce")
                    if numeric.notna().sum() == series.notna().sum():
                        return numeric
                    return series.astype("string")

                df = df.sort_values(column, ascending=term["direction"] == "ASC", kind="mergesort",
                                    na_position=term["nulls"], key=sort_key)
            if limit is not None:
                df = df.head(limit)
            rows = df.astype(object).where(pd.notna(df), None).to_dict("records")
            return {"data": rows, "operator_result": rows, "row_count": len(rows)}
        except Exception as exc:
            return {"data": [], "operator_result": [], "row_count": 0,
                    "error": str(exc), "code": "ORDER_BY_ERROR"}

    # Planning-only calls keep the existing LLM interface. Data-mode execution
    # imports no clients and makes no model call.
    from ..common import LOCAL_MODEL, api_logger, json
    from ..clients import build_llm_messages
    from ..utils import parse_llm_json

    prompt = f"""
The next operator is Order_By. Translate the question into explicit post-scan sorting.
Do not write SPARQL. Preserve every requested ordering key, direction, and limit.
Query: {inputs.get('query')}
Schema: {json.dumps(inputs.get('schema_details', {}))}
Output JSON: {{"order_by": [{{"column": "exact_field", "direction": "ASC", "nulls": "last"}}], "limit": null}}
"""
    api_logger.log_call(inputs.get("query"), "Order_By")
    effective_model = model or LOCAL_MODEL
    response = client.chat.completions.create(
        model=effective_model, messages=build_llm_messages("semantic", prompt),
        **({} if effective_model.lower().startswith("gpt-5") else {"temperature": 0.0}),
    )
    return {"sorting_logic": parse_llm_json(response.choices[0].message.content,
                                           {"order_by": [], "limit": None}, "Order_By")}
