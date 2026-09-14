"""Set intersection operator."""

from ..common import Any, Dict


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
