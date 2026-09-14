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
    join_keys = join_key if isinstance(join_key, list) else [join_key]

    def row_key(item):
        values = [item.get(key) for key in join_keys if key in item]
        if not values:
            return None
        return tuple(values)

    # Extract keys
    keys_a = {key for item in list_a for key in [row_key(item)] if key is not None}
    keys_b = {key for item in list_b for key in [row_key(item)] if key is not None}

    # Intersect
    intersected_keys = keys_a.intersection(keys_b)

    # Filter original items based on intersection
    result = [item for item in list_a if row_key(item) in intersected_keys]

    return {"data": result, "intersected_data": result, "count": len(result)}
