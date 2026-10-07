"""Integrate operator."""

import re
from ..common import (
    Any,
    Dict,
    LLMClient,
    LOCAL_MODEL,
    api_logger,
    json,
    pd,
)
from ..clients import build_llm_messages


def _canonical_key(name: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name or "").lower())


def _find_matching_column(df: pd.DataFrame, target_name: str) -> str | None:
    if target_name in df.columns:
        return target_name
    target_canon = _canonical_key(target_name)
    for col in df.columns:
        if _canonical_key(col) == target_canon:
            return str(col)
    return None


def _align_and_find_join_key(frames: list[pd.DataFrame], join_key: str | None) -> str | None:
    if not frames:
        return None

    if join_key:
        matched_cols = [_find_matching_column(df, join_key) for df in frames]
        if all(col is not None for col in matched_cols):
            target_name = matched_cols[0]
            for df, col in zip(frames[1:], matched_cols[1:]):
                if col != target_name:
                    df.rename(columns={col: target_name}, inplace=True)
            return target_name

    col_canon_maps = [{_canonical_key(c): c for c in df.columns} for df in frames]
    common_canons = set.intersection(*(set(m.keys()) for m in col_canon_maps)) if col_canon_maps else set()
    if common_canons:
        id_canons = [c for c in common_canons if "id" in c]
        selected_canon = id_canons[0] if id_canons else sorted(common_canons)[0]
        target_name = col_canon_maps[0][selected_canon]
        for df, m in zip(frames[1:], col_canon_maps[1:]):
            orig_col = m[selected_canon]
            if orig_col != target_name:
                df.rename(columns={orig_col: target_name}, inplace=True)
        return target_name

    return None


def semantic_integrate(inputs: Dict[str, Any], client: LLMClient, model: str = LOCAL_MODEL) -> Dict[str, Any]:
    """
    Operator: Integrate
    Merges parallel branch outputs. Uses deterministic row merging when branch
    data and a join_key are available; otherwise falls back to LLM synthesis.
    Merges parallel branch outputs. Uses deterministic relational merging when branch
    data is available; otherwise falls back to LLM synthesis.
    """
    if inputs.get("strict_spec"):
        from ..relational import integrate
        return integrate(inputs)
    branch_data_lists = [
        branch_data
        for branch_data in inputs.get("branch_data_lists", [])
        if isinstance(branch_data, list) and branch_data
    ]
    list_a = inputs.get("list_a", [])
    list_b = inputs.get("list_b", [])
    join_key = inputs.get("join_key")
    strict_spec = bool(inputs.get("strict_spec"))
    original_join_keys = list(join_key) if isinstance(join_key, list) else []
    how = str(inputs.get("join_type") or inputs.get("how") or "inner").lower()
    if how not in {"inner", "left", "right", "outer"}:
        how = "inner"

    if branch_data_lists and not join_key:
        if strict_spec and len(branch_data_lists) > 1:
            return {"data": [], "integrated_data": [], "row_count": 0,
                    "error": "Integrate requires an explicit declared join_key in strict spec mode."}
        rows = []
        for branch_data in branch_data_lists:
            rows.extend(branch_data)
        if rows:
            df = pd.DataFrame(rows).drop_duplicates().reset_index(drop=True)
            merged_rows = df.where(pd.notna(df), None).to_dict(orient="records")
            return {"data": merged_rows, "integrated_data": merged_rows, "row_count": len(merged_rows)}
    if not branch_data_lists and (list_a or list_b):
        if list_a and isinstance(list_a, list):
            branch_data_lists.append(list_a)
        if list_b and isinstance(list_b, list):
            branch_data_lists.append(list_b)

    if branch_data_lists:
        usable_frames = [
            pd.DataFrame(branch_data)
            for branch_data in branch_data_lists
            if branch_data
        ]
        if not usable_frames:
            return {"data": [], "integrated_data": [], "row_count": 0}

        # Final_Spec may declare a composite relational key (for example investorId + sector).
        # Convert it to a temporary deterministic key before using the normal merge path.
        composite_key = None
        if isinstance(join_key, list) and len(join_key) == 1:
            join_key = join_key[0]
        if isinstance(join_key, list) and len(join_key) > 1:
            composite_key = "__aop_composite_join_key__"
            for frame in usable_frames:
                resolved = [str(key) if str(key) in frame.columns else None for key in join_key] if strict_spec else [_find_matching_column(frame, str(key)) for key in join_key]
                if any(column is None for column in resolved):
                    composite_key = None
                    break
                frame[composite_key] = frame[resolved].fillna("").astype(str).agg("\x1f".join, axis=1)
            if composite_key:
                join_key = composite_key

        if strict_spec and isinstance(join_key, str) and join_key not in usable_frames[0].columns:
            return {"data": [], "integrated_data": [], "row_count": 0,
                    "error": f"Declared join key does not exist: {join_key}"}
        effective_key = join_key if strict_spec and isinstance(join_key, str) and all(join_key in frame.columns for frame in usable_frames) else _align_and_find_join_key(usable_frames, join_key)
        if effective_key:
            merged_df = usable_frames[0]
            for next_df in usable_frames[1:]:
                # A grouping value may validly be null.  In particular, Final_Spec can
                # request preserve_null_groups=true, so dropping null keys here would make
                # separately aggregated measures disagree.  Pandas merges matching null
                # group values deterministically; duplicate protection below handles an
                # actual many-to-many input instead of silently deleting a result group.
                # Check for severe duplicate explosion
                if len(merged_df) > 500 and len(next_df) > 500:
                    merged_dupes = merged_df[effective_key].duplicated().sum() / max(1, len(merged_df))
                    next_dupes = next_df[effective_key].duplicated().sum() / max(1, len(next_df))
                    if merged_dupes > 0.8 and next_dupes > 0.8:
                        # High many-to-many: deduplicate next_df to preserve memory
                        next_df = next_df.drop_duplicates(subset=[effective_key])

                overlap_cols = [c for c in next_df.columns if c in merged_df.columns and c != effective_key]
                if overlap_cols:
                    merged_df = pd.merge(merged_df, next_df, on=effective_key, how=how, suffixes=("", "_right"))
                else:
                    merged_df = pd.merge(merged_df, next_df, on=effective_key, how=how)
            if composite_key and composite_key in merged_df.columns:
                merged_df = merged_df.drop(columns=[composite_key])
            if composite_key:
                duplicate_keys = [f"{key}_right" for key in original_join_keys if f"{key}_right" in merged_df.columns]
                if duplicate_keys:
                    merged_df = merged_df.drop(columns=duplicate_keys)
            rows = merged_df.where(pd.notna(merged_df), None).to_dict(orient="records")
            return {"data": rows, "integrated_data": rows, "row_count": len(rows)}

    if join_key and ("list_a" in inputs or "list_b" in inputs):
        if not list_a or not list_b:
            return {"data": [], "integrated_data": [], "row_count": 0}
        df_a = pd.DataFrame(list_a)
        df_b = pd.DataFrame(list_b)
        if join_key in df_a.columns and join_key in df_b.columns:
            if how not in {"inner", "left", "right", "outer"}:
                how = "inner"
            merged_df = pd.merge(df_a, df_b, on=join_key, how=how, suffixes=("_left", "_right"))
            rows = merged_df.where(pd.notna(merged_df), None).to_dict(orient="records")
            return {"data": rows, "integrated_data": rows, "row_count": len(rows)}
        rows = []
        for branch_data in branch_data_lists:
            rows.extend(branch_data)
        if rows:
            df = pd.DataFrame(rows).drop_duplicates().reset_index(drop=True)
            merged_rows = df.where(pd.notna(df), None).to_dict(orient="records")
            return {"data": merged_rows, "integrated_data": merged_rows, "row_count": len(merged_rows)}

    # A missing structured join contract cannot authorize model access to rows.
    return {"data": [], "integrated_data": [], "row_count": 0,
            "error": "Integrate requires a structured local join contract.", "code": "INTEGRATE_ERROR"}
