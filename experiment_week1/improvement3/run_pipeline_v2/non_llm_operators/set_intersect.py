import re

from ..common import Any, Dict, List


def _canonical_key(name: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name).lower())


def _find_item_val(item: Dict[str, Any], target_key: str) -> Any:
    if not isinstance(item, dict):
        return None
    if target_key in item:
        return item[target_key]
    target_canon = _canonical_key(target_key)
    for k, v in item.items():
        if _canonical_key(k) == target_canon:
            return v
    return None


def _resolve_join_keys(datasets: List[List[Dict[str, Any]]], requested_keys: Any) -> List[str]:
    keys_to_try = [requested_keys] if isinstance(requested_keys, str) else list(requested_keys or [])
    sample_key_sets = []
    for data in datasets:
        if isinstance(data, list) and data:
            keys = set()
            for row in data[:10]:
                if isinstance(row, dict):
                    keys.update(row.keys())
            if keys:
                sample_key_sets.append(keys)

    # 1. Match requested keys canonically across all datasets
    if keys_to_try and sample_key_sets:
        matched_requested = []
        for req in keys_to_try:
            req_canon = _canonical_key(req)
            all_have = True
            for kset in sample_key_sets:
                if not any(_canonical_key(k) == req_canon for k in kset):
                    all_have = False
                    break
            if all_have:
                matched_requested.append(req)
        if matched_requested:
            return matched_requested

    # 2. Auto-detect common keys across datasets
    if sample_key_sets:
        canon_sets = [{_canonical_key(k) for k in kset} for kset in sample_key_sets]
        common_canon = set.intersection(*canon_sets) if canon_sets else set()
        id_keys = [c for c in common_canon if c.endswith("id") or "id" in c]
        chosen_canon = id_keys if id_keys else list(common_canon)
        if chosen_canon:
            first_keys = sample_key_sets[0]
            resolved = []
            for c in chosen_canon:
                for k in first_keys:
                    if _canonical_key(k) == c:
                        resolved.append(k)
                        break
            if resolved:
                return resolved

    return keys_to_try if keys_to_try else ["investor_id"]


def pre_programmed_set_intersect(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Operator: Set (Intersection)
    Purpose: Intersects two lists of data (e.g., finding investor_ids that appear in both lists).
    Expected inputs: 'list_a' (list of dicts), 'list_b' (list of dicts), 'join_key' (str).
    Purpose: Intersects two or more lists of data based on canonical join keys.
    Expected inputs: 'branch_data_lists' OR ('list_a', 'list_b'), 'join_key'.
    """
    branch_data_lists = inputs.get("branch_data_lists")
    list_a = inputs.get("list_a", [])
    list_b = inputs.get("list_b", [])
    if isinstance(branch_data_lists, list) and len(branch_data_lists) >= 2:
        datasets = [b for b in branch_data_lists if isinstance(b, list)]
    else:
        list_a = inputs.get("list_a", [])
        list_b = inputs.get("list_b", [])
        datasets = [list_a if isinstance(list_a, list) else [], list_b if isinstance(list_b, list) else []]

    if not datasets or not any(datasets):
        return {"data": [], "intersected_data": [], "count": 0}

    join_key_input = inputs.get("join_key") or inputs.get("key") or inputs.get("join_keys")
    resolved_keys = _resolve_join_keys(datasets, join_key_input)

    def row_key(item):
        if not isinstance(item, dict):
            return str(item)
        values = []
        for key in resolved_keys:
            val = _find_item_val(item, key)
            if val is not None:
                values.append(str(val).strip())
        if not values:
            return None
        return tuple(values)

    def unique_intersection_rows(rows, intersected_keys):
        """Return one representative row per set key, preserving source order."""
        seen_keys = set()
        result = []
        for item in rows:
            key = row_key(item)
            if key is None or key not in intersected_keys or key in seen_keys:
                continue
            seen_keys.add(key)
            result.append(item)
        return result

    if isinstance(branch_data_lists, list) and len(branch_data_lists) >= 2:
        key_sets = [
            {key for item in branch_data for key in [row_key(item)] if key is not None}
            for branch_data in branch_data_lists
            if isinstance(branch_data, list)
        ]
        if not key_sets:
            return {"data": [], "intersected_data": [], "count": 0}
        intersected_keys = set.intersection(*key_sets)
        result = unique_intersection_rows(branch_data_lists[0], intersected_keys)
        return {"data": result, "intersected_data": result, "count": len(result)}

    key_sets = [
        {key for item in branch_data for key in [row_key(item)] if key is not None}
        for branch_data in datasets
    ]
    if not key_sets or any(len(ks) == 0 for ks in key_sets):
        return {"data": [], "intersected_data": [], "count": 0}

    intersected_keys = set.intersection(*key_sets)
    result = unique_intersection_rows(datasets[0], intersected_keys)
    return {"data": result, "intersected_data": result, "count": len(result)}
