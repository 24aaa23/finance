"""Difference operator."""

from ..common import Any, Dict


def pre_programmed_difference(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Operator: Set Difference
    Purpose: Finds records in List A that are NOT in List B based on a specific key.
    Expected inputs: 'list_a', 'list_b', 'join_key' (e.g., 'investor_id')
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

    keys_b = {key for item in list_b for key in [row_key(item)] if key is not None}

    # Keep items in A where the key is NOT in B
    result = [item for item in list_a if row_key(item) not in keys_b]
    return {"data": result, "difference_data": result, "count": len(result)}
