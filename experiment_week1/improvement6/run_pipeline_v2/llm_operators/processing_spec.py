"""Preserve scanned rows for the single final calculation planner.

The public operator name is retained for DAG/report compatibility. No model call or
branch-local aggregation is needed here: Final_Spec can operate on any raw branch.
"""

from ..common import Any, Dict, LOCAL_MODEL
from ..spec_contracts import flatten_identifiers
from ..spec_runtime import compile_spec


def semantic_build_processing_spec(inputs: Dict[str, Any], client: Any = None, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    rows = inputs.get("data", [])
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        return {"processing_spec": {"contract_errors": ["Scan output must be a list of structured rows."]}}
    query_spec = inputs.get("query_spec") or {}
    fields = list(inputs.get("input_schema") or [])
    for row in rows:
        fields.extend(field for field in row if field not in fields)
    if not fields:
        for retrieval in query_spec.get("retrieval_specs", []):
            for field in flatten_identifiers(retrieval.get("fields")):
                if field not in fields:
                    fields.append(field)
    # Grain is descriptive metadata; do not deduplicate or aggregate these rows.
    grain = flatten_identifiers((inputs.get("subquestion") or {}).get("retrieval_grain"))
    grain = [field for field in grain if field in fields]
    output_id = str(inputs.get("subquestion_id") or query_spec.get("id") or "branch") + "_processed"
    spec = compile_spec({"input": "raw", "steps": [], "output": "raw",
                         "output_id": output_id, "entity_grain": grain,
                         "aggregation_policy": "preserve_rows"}, {"raw": fields})
    return {"processing_spec": spec}
