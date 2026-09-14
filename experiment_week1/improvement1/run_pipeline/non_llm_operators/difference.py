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

    keys_b = {item[join_key] for item in list_b if join_key in item}

    # Keep items in A where the key is NOT in B
    result = [item for item in list_a if item.get(join_key) not in keys_b]
    return {"difference_data": result, "count": len(result)}
