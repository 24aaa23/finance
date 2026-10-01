"""Validate the raw SQLite SELECT against its unchanged retrieval contract."""
from ..common import Any, Dict, LOCAL_MODEL
from ..raw_sql import render_raw_sql, canonical_sql_tokens


def semantic_pre_scan_validate(inputs: Dict[str, Any], client: Any, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    query = inputs.get("sparql", "")
    spec = inputs.get("query_spec") or {}

    def reject(reason, stage="Generate"):
        return {"pre_scan_validation": {
            "is_valid": False, "severity": "hard_error", "reason": reason,
            "rewrite_hint": "Regenerate the canonical SQLite SELECT for the active retrieval contract.",
            "repair_stage": stage,
        }}

    if isinstance(spec, dict) and spec.get("contract_errors"):
        return reject("Query_Spec has unresolved contract errors: " + "; ".join(spec["contract_errors"]), "Query_Spec")
    if not isinstance(query, str) or not query.strip():
        return reject("No SQL was generated.")
    retrieval = inputs.get("retrieval_spec") or {}
    if not retrieval and isinstance(spec, dict):
        retrievals = spec.get("retrieval_specs", [])
        if isinstance(retrievals, list) and len(retrievals) == 1:
            retrieval = retrievals[0]
    try:
        canonical = render_raw_sql(retrieval, inputs.get("global_schema", {}))
    except (ValueError, TypeError, AttributeError) as exc:
        return reject("Invalid retrieval contract: " + str(exc), "Query_Spec")
    if canonical is None:
        return reject("The retrieval contract has no physical SQLite binding.", "Query_Spec")
    try:
        if canonical_sql_tokens(query) != canonical_sql_tokens(canonical):
            return reject("SQL differs from the rendered retrieval contract. Preserve its source, fields, duplicates, NULLs and filters; calculations stay in the final plan.")
    except ValueError as exc:
        return reject("Invalid SQL: " + str(exc))
    from ..common import SQLITE_DB_PATH, SQL_SCAN_TIMEOUT_SECONDS
    from ..sqlite_backend import validate_sql_on_sqlite
    validation = validate_sql_on_sqlite(query, inputs.get("sqlite_db_path", SQLITE_DB_PATH), SQL_SCAN_TIMEOUT_SECONDS)
    if validation.get("status") != "success":
        return reject("SQLite could not compile the retrieval: " + validation.get("error_message", "unknown error"))
    return {"pre_scan_validation": {
        "is_valid": True, "severity": "valid",
        "reason": "Canonical raw retrieval and SQLite compilation passed deterministic checks.",
        "rewrite_hint": "", "validation_method": "sqlite_retrieval_contract",
    }}
