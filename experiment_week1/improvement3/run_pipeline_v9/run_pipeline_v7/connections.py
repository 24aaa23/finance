"""Carry declared connection keys into raw retrievals; never guess a join."""
import re

from .spec_contracts import flatten_identifiers


def _columns(details):
    columns = {column if isinstance(column, str) else column["name"]:
               {} if isinstance(column, str) else column
               for column in details.get("columns", [])}
    if details.get("subject_field"):
        columns.setdefault(details["subject_field"], {})
    return columns


def _entity_type(source, field, details, columns):
    if field == details.get("subject_field"):
        return source
    match = re.search(r"points to:\s*([^)]+)", str(columns[field].get("datatype", "")))
    return match.group(1).strip() if match else None


def retain_connection_keys(spec, decomposition, schema):
    """Validate declared endpoints, then add this branch's keys as raw fields.

    Optional added properties preserve the original population. The final join
    decides whether missing links exclude rows. This does not discover missing
    sources/paths or establish the meaning of two arbitrary literal identifiers.
    """
    branches = {str(branch["id"]): branch.get("source_class")
                for branch in decomposition.get("subquestions", []) if isinstance(branch, dict) and branch.get("id")}
    required, errors = {}, []
    for join in decomposition.get("answer_requirements", {}).get("joins", []):
        endpoints = []
        for side in ("left", "right"):
            branch = str(join.get(side + "_branch") or "")
            source = branches.get(branch)
            details = schema.get(source, {})
            columns = _columns(details)
            fields = flatten_identifiers(join.get(side + "_on", join.get(side + "_field", [])))
            fields = [field[len(source) + 1:] if source and field.startswith(source + ".") else field for field in fields]
            if not source or not fields or any(field not in columns for field in fields):
                errors.append(f"Connection has an unknown branch/source/key: {branch} {source} {fields}.")
                break
            endpoints.append((branch, source, fields, details, columns))
        if len(endpoints) != 2:
            continue
        left, right = endpoints
        if len(left[2]) != len(right[2]):
            errors.append("Connection needs the same number of left and right keys.")
            continue
        for lfield, rfield in zip(left[2], right[2]):
            ltype = _entity_type(left[1], lfield, left[3], left[4])
            rtype = _entity_type(right[1], rfield, right[3], right[4])
            if ltype and rtype and ltype != rtype:
                errors.append(f"Connection keys identify different entity classes: {ltype} and {rtype}.")
            elif bool(ltype) != bool(rtype):
                # Only reject a proven resource/literal mismatch, not unknown metadata.
                literal_column = right[4][rfield] if ltype else left[4][lfield]
                dtype = str(literal_column.get("datatype", "")).lower()
                if dtype in {"numeric", "categorical_string", "string", "number", "date"}:
                    errors.append("Connection mixes a resource identity with a literal field.")
        for branch, source, fields, _, _ in endpoints:
            required.setdefault((branch, source), []).extend(fields)
    if errors:
        return errors
    branch = str(spec.get("branch_id") or spec.get("id") or "")
    for retrieval in spec.get("retrieval_specs", []):
        source = retrieval.get("class")
        subject = schema.get(source, {}).get("subject_field")
        fields = retrieval.setdefault("fields", [])
        optional = retrieval.setdefault("optional_fields", [])
        for key in required.get((branch, source), []):
            if key not in fields:
                fields.append(key)
                if key != subject and key not in optional:
                    optional.append(key)
        if subject and subject not in fields:
            fields.append(subject)
        if len(spec.get("retrieval_specs", [])) == 1:
            spec["output_schema"] = list(fields)
    return []
